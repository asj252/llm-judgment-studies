#!/Volumes/2026General_Space/imperfective/venv/bin/python -I
"""Mac gpujob launcher for Experiment 1 Stage S6 (formal).

Key responsibilities:
1. Fail-closed preflight verification of host_paths_<host_id>.json, mounted HF_HOME,
   s6-s7-execution-manifest.json (binding PLAN-E1.frozen.md and S6/S7 entrypoint SHA256s),
   upstream data/ SHA256s when present or launching live inference, and Stage S5
   cryptographic freeze artifacts (freeze.json, PLAN-E1.frozen.md, c-review.md).
2. Automatic export of HF_HOME and HF_HUB_OFFLINE=1 before importing any runner/tokenizer code.
3. Optional cross-midnight ISO +08:00 --deadline-at enforcement (>= 900 seconds margin).
4. Default in-process streaming-RAM guard ('in_process_streaming') keeping gpujob lock
   file descriptors open in the exact same PID while preventing unmodified Ledger.load() /
   records accumulation from holding 4,160 full raw_response completion_probabilities
   objects (~38-56 GiB CPython RSS) alongside llama-server (~14 GiB Metal) on the 24 GB
   Mac mini:
   - Zero bytes modified in exp1-en/*.py on disk (runner fingerprint 895f4e6f... unchanged).
   - Ledger.commit() writes and fsyncs the 100% full, unmodified row to results.jsonl first,
     then drops dead multi-MB raw_response/topN fields only from the in-memory formal copy.
   - Ledger.load() streams results.jsonl line-by-line (preserving exact tail repair_log
     semantics, full unmodified rows for smoke/dev ledger_digest & determinism checks, and
     slimmed in-memory rows for formal), plus gc.collect() right after admission.check_stage
     before llama-server starts.
"""
import argparse
import gc
import hashlib
import importlib.util
import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_EXP1_ROOT = SCRIPT_DIR.parent / "exp1-en"
EXECUTION_MANIFEST_PATH = SCRIPT_DIR / "s6-s7-execution-manifest.json"
SHANGHAI = timezone(timedelta(hours=8), name="Asia/Shanghai")
DEADLINE_FORMAT = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?\+08:00")
DEFAULT_CONFIG = "qwen3-8b@macmini-m6"
EXPECTED_RUNNER_FP = "895f4e6f51ca3044800eff8ff098970af68f86f54ced061c79c6a5e9ef1900b2"
DEFAULT_FP8 = EXPECTED_RUNNER_FP[:8]
HEX64_RE = re.compile(r"[0-9a-f]{64}")

# Keys never read by exp1-en/run.py validate_records() or exp1-en/gates.py compute()
_FORMAL_DROP_TOP_KEYS = (
    "raw_response",
    "first_topN",
    "prompt_ids",
    "generated_ids",
    "generated_ids_raw",
    "messages",
    "text",
    "errors",
)


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(65536):
            h.update(chunk)
    return h.hexdigest()


def slim_formal_row_in_place(row: dict) -> dict:
    """Drop multi-MB raw_response/token-array/prose fields in memory after full disk commit."""
    for k in _FORMAL_DROP_TOP_KEYS:
        row.pop(k, None)
    parsed = row.get("parsed")
    if isinstance(parsed, dict) and ("object" in parsed or "extra_keys" in parsed):
        cleaned = {k: v for k, v in parsed.items() if k not in ("object", "extra_keys")}
        if "extra_keys" in parsed and isinstance(parsed["extra_keys"], list):
            cleaned["extra_key_count"] = len(parsed["extra_keys"])
        row["parsed"] = cleaned
    q = row.get("q")
    if isinstance(q, dict) and any(k in q for k in ("topN", "prefix_ids", "candidates")):
        row["q"] = {k: v for k, v in q.items() if k not in ("topN", "prefix_ids", "candidates")}
    return row


def _copy_prefix_bytes(src: Path, dst: Path, n_bytes: int) -> None:
    remaining = n_bytes
    with src.open("rb") as r_handle, dst.open("wb") as w_handle:
        while remaining > 0:
            chunk = r_handle.read(min(8 * 1024 * 1024, remaining))
            if not chunk:
                break
            w_handle.write(chunk)
            remaining -= len(chunk)
        w_handle.flush()
        os.fsync(w_handle.fileno())


def install_formal_streaming_ram_guard(exp1_ledger_mod, exp1_admission_mod, formal_ns: Path) -> None:
    """Install streaming Ledger.load, post-fsync in-memory slimming on formal, and post-admission GC."""
    formal_ns_resolved = Path(formal_ns).resolve()
    orig_commit = exp1_ledger_mod.Ledger.commit
    orig_check_stage = exp1_admission_mod.check_stage
    atomic_json_fn = exp1_ledger_mod.atomic_json
    timestamp_fn = exp1_ledger_mod.timestamp

    def streaming_load(self, repair=False):
        if not self.results.exists():
            return []
        is_formal_ns = Path(self.path).resolve() == formal_ns_resolved
        parsed, seen, previous_seq = [], set(), 0
        repair_offset = None
        corrupt_line = None

        with self.results.open("rb") as handle:
            idx = 0
            while True:
                line_offset = handle.tell()
                line = handle.readline()
                if not line:
                    break
                try:
                    row = json.loads(line.decode("utf-8"))
                    if not line.endswith(b"\n"):
                        raise ValueError("incomplete terminal line")
                except (ValueError, UnicodeError):
                    at_eof = handle.readline() == b""
                    if at_eof and repair:
                        repair_offset = line_offset
                        corrupt_line = line
                        break
                    raise ValueError(f"corrupt ledger line {idx + 1}")

                if not isinstance(row, dict) or type(row.get("commit_seq")) is not int or row["commit_seq"] <= previous_seq:
                    raise ValueError(f"invalid commit_seq at line {idx + 1}")
                previous_seq = row["commit_seq"]
                self.seq = previous_seq
                session = self.sessions.get(row.get("session_id"))
                if not session:
                    raise ValueError("record references unknown session")
                if session["state"] in ("invalid", "open"):
                    idx += 1
                    continue
                key = row["unit_key"]
                if key in seen:
                    raise ValueError("duplicate terminal unit in valid sessions")
                seen.add(key)
                if is_formal_ns:
                    slim_formal_row_in_place(row)
                parsed.append(row)
                idx += 1

        if repair_offset is not None and corrupt_line is not None:
            corrupt = self.results.with_name(self.results.name + ".corrupt-" + uuid.uuid4().hex)
            corrupt.write_bytes(corrupt_line)
            tmp = self.results.with_name("results.repaired.tmp")
            _copy_prefix_bytes(self.results, tmp, repair_offset)
            os.replace(tmp, self.results)
            atomic_json_fn(self.path / "repair_log.json", {"quarantined": corrupt.name, "written_at": timestamp_fn()})

        return parsed

    def guarded_commit(self, row, guard, hook=None):
        committed = orig_commit(self, row, guard, hook)
        if committed and Path(self.path).resolve() == formal_ns_resolved:
            slim_formal_row_in_place(row)
        return committed

    def guarded_check_stage(context, stage):
        orig_valid_records = context.valid_records
        stage_cache = {}

        def cached_valid_records(target_stage):
            if target_stage in ("smoke", "dev"):
                res_file = context.namespace(target_stage) / "results.jsonl"
                stat_key = None
                if res_file.is_file():
                    st = res_file.stat()
                    stat_key = (st.st_size, st.st_mtime_ns, st.st_ino)
                hit = stage_cache.get(target_stage)
                if hit is not None and hit[0] == stat_key:
                    return hit[1]
                rows = orig_valid_records(target_stage)
                stage_cache[target_stage] = (stat_key, rows)
                return rows
            return orig_valid_records(target_stage)

        context.valid_records = cached_valid_records
        try:
            return orig_check_stage(context, stage)
        finally:
            context.valid_records = orig_valid_records
            stage_cache.clear()
            # Release temporary 2.27 GB dev ledger objects before llama-server starts.
            gc.collect()

    exp1_ledger_mod.Ledger.load = streaming_load
    exp1_ledger_mod.Ledger.commit = guarded_commit
    exp1_admission_mod.check_stage = guarded_check_stage


def load_and_verify_execution_manifest(manifest_path: Path = EXECUTION_MANIFEST_PATH) -> dict:
    """Verify cycle-free S6/S7 execution manifest against on-disk entrypoint SHA256s."""
    manifest_path = Path(manifest_path).resolve()
    if not manifest_path.is_file():
        raise PermissionError(f"S6/S7 execution manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("schema_version") != "exp1-s6-s7-execution-manifest-v1":
        raise PermissionError(f"Unexpected execution manifest schema_version: {manifest.get('schema_version')!r}")
    if manifest.get("config") != DEFAULT_CONFIG:
        raise PermissionError("Execution manifest config mismatch")
    if manifest.get("expected_runner_fingerprint") != EXPECTED_RUNNER_FP:
        raise PermissionError("Execution manifest expected_runner_fingerprint mismatch")
    if manifest.get("expected_fp8") != DEFAULT_FP8:
        raise PermissionError("Execution manifest expected_fp8 mismatch")

    entrypoints = manifest.get("entrypoints")
    if not isinstance(entrypoints, dict):
        raise PermissionError("Execution manifest missing entrypoints mapping")
    s6_expected = str(entrypoints.get("gpu_s6_formal_stage_macos.py", ""))
    s7_expected = str(entrypoints.get("run_s7_formal_analysis.py", ""))
    if not (HEX64_RE.fullmatch(s6_expected) and HEX64_RE.fullmatch(s7_expected)):
        raise PermissionError("Execution manifest entrypoints missing valid 64-hex SHA256")

    s6_actual = _sha256(Path(__file__).resolve())
    s7_file = SCRIPT_DIR / "run_s7_formal_analysis.py"
    if not s7_file.is_file():
        raise PermissionError(f"Bound S7 analysis script missing: {s7_file}")
    s7_actual = _sha256(s7_file.resolve())
    if s6_actual != s6_expected:
        raise PermissionError(
            f"gpu_s6_formal_stage_macos.py SHA256 {s6_actual} disagrees with execution manifest {s6_expected}"
        )
    if s7_actual != s7_expected:
        raise PermissionError(
            f"run_s7_formal_analysis.py SHA256 {s7_actual} disagrees with execution manifest {s7_expected}"
        )

    plan_expected = str(manifest.get("expected_frozen_plan_sha256", ""))
    if not HEX64_RE.fullmatch(plan_expected):
        raise PermissionError("Execution manifest missing valid expected_frozen_plan_sha256")
    return manifest


def verify_upstream_data_files(exp1_root: Path, manifest: dict) -> None:
    """Verify git-excluded exp1-en/data/{imperfectiveNLI.json, run_inference.py.txt} SHA256s."""
    upstream = manifest.get("upstream_data_sha256")
    if not isinstance(upstream, dict) or not upstream:
        raise PermissionError("Execution manifest missing upstream_data_sha256")
    data_dir = Path(exp1_root).resolve() / "data"
    if not data_dir.is_dir():
        raise FileNotFoundError(f"Upstream data directory missing: {data_dir}")
    for fname, exp_sha in upstream.items():
        fpath = data_dir / fname
        if not fpath.is_file():
            raise FileNotFoundError(f"Upstream data file missing: {fpath}")
        got_sha = _sha256(fpath)
        if got_sha != exp_sha:
            raise PermissionError(f"Upstream data SHA256 mismatch on {fname}: {got_sha} != {exp_sha}")


def verify_prefreeze_and_env(
    exp1_root: Path,
    cfg: str,
    expected_fp8: str,
    *,
    manifest_path: Path = EXECUTION_MANIFEST_PATH,
    require_upstream_data: bool = False,
) -> dict:
    """Fail-closed check of execution manifest, host_paths, HF_HOME target, and S5 freeze snapshot."""
    exp1_root = Path(exp1_root).resolve()
    if cfg != DEFAULT_CONFIG:
        raise PermissionError(f"S6 formal launch locked to config {DEFAULT_CONFIG!r}, got {cfg!r}")
    if expected_fp8 != DEFAULT_FP8:
        raise PermissionError(f"S6 formal launch locked to fp8 {DEFAULT_FP8!r}, got {expected_fp8!r}")
    model_key, host_id = cfg.split("@")
    if not model_key or not host_id:
        raise ValueError("invalid config components")

    manifest = load_and_verify_execution_manifest(manifest_path=manifest_path)

    run_py = exp1_root / "run.py"
    if not run_py.is_file():
        raise FileNotFoundError(f"exp1-en runner missing: {run_py}")

    host_paths_file = exp1_root / f"host_paths_{host_id}.json"
    if not host_paths_file.is_file():
        raise FileNotFoundError(f"host paths file missing: {host_paths_file}")
    host_paths = json.loads(host_paths_file.read_text(encoding="utf-8"))
    if host_paths.get("host_id") != host_id:
        raise ValueError("host_id mismatch in host_paths file")
    hf_home_raw = host_paths.get("hf_home")
    if not isinstance(hf_home_raw, str) or not hf_home_raw.strip():
        raise ValueError("hf_home missing in host_paths file")
    hf_home_path = Path(hf_home_raw)
    if not hf_home_path.is_dir():
        raise FileNotFoundError(f"hf_home directory not mounted or missing: {hf_home_path}")

    if require_upstream_data or (exp1_root / "data").exists():
        verify_upstream_data_files(exp1_root, manifest)

    freeze_dir = exp1_root / "freeze" / cfg / expected_fp8
    freeze_json_path = freeze_dir / "freeze.json"
    frozen_plan_path = freeze_dir / "PLAN-E1.frozen.md"
    if not freeze_json_path.is_file() or not frozen_plan_path.is_file():
        raise PermissionError(
            f"S5 freeze artifacts missing in {freeze_dir}; refusing to launch formal stage"
        )

    freeze = json.loads(freeze_json_path.read_text(encoding="utf-8"))
    if freeze.get("type") != "freeze" or freeze.get("status") != "pass":
        raise PermissionError("freeze.json type/status is not 'freeze'/'pass'")
    if freeze.get("config") != cfg:
        raise PermissionError(f"freeze.json config mismatch: {freeze.get('config')!r} != {cfg!r}")
    fp_full = str(freeze.get("fingerprint_id", ""))
    if fp_full != EXPECTED_RUNNER_FP:
        raise PermissionError(f"freeze.json fingerprint_id {fp_full!r} != {EXPECTED_RUNNER_FP!r}")
    if str(freeze.get("run_id", "")).startswith("E1-DRY-"):
        raise PermissionError("E1-DRY freeze evidence forbidden in real formal launch")
    if freeze.get("source_stage") != "dev":
        raise PermissionError("freeze.json source_stage must equal 'dev'")
    if type(freeze.get("c_blockers")) is not int or freeze["c_blockers"] != 0:
        raise PermissionError("freeze.json requires integer c_blockers == 0")
    if freeze.get("user_confirmed") is not True or not str(freeze.get("confirmed_at", "")).strip():
        raise PermissionError("freeze.json lacks explicit user_confirmed=True and confirmed_at")

    actual_plan_sha = _sha256(frozen_plan_path)
    if actual_plan_sha != freeze.get("frozen_plan_sha256"):
        raise PermissionError("PLAN-E1.frozen.md SHA256 does not match freeze.json frozen_plan_sha256")
    if actual_plan_sha != manifest["expected_frozen_plan_sha256"]:
        raise PermissionError(
            f"PLAN-E1.frozen.md SHA256 {actual_plan_sha} does not match bound execution manifest "
            f"{manifest['expected_frozen_plan_sha256']}"
        )

    frozen_plan_text = frozen_plan_path.read_text(encoding="utf-8")
    for ep_name, ep_sha in manifest["entrypoints"].items():
        if ep_sha not in frozen_plan_text:
            raise PermissionError(f"PLAN-E1.frozen.md does not bind {ep_name} SHA256 {ep_sha}")

    c_review_rel = freeze.get("c_review_file")
    if not isinstance(c_review_rel, str) or not c_review_rel.strip():
        raise PermissionError("freeze.json missing c_review_file")
    c_review_path = Path(c_review_rel)
    if not c_review_path.is_absolute():
        c_review_path = exp1_root / c_review_path
    c_review_resolved = c_review_path.resolve()
    if not c_review_resolved.is_relative_to(exp1_root) or not c_review_resolved.is_file():
        raise PermissionError("freeze.json c_review_file missing or outside exp1-en namespace")

    paused_path = exp1_root / "raw" / "formal" / cfg / expected_fp8 / "PAUSED.json"
    if paused_path.exists():
        raise RuntimeError(f"formal namespace contains PAUSED.json: {paused_path}")

    return {
        "exp1_root": exp1_root,
        "run_py": run_py,
        "host_id": host_id,
        "hf_home": str(hf_home_path.resolve()),
        "fingerprint_id": fp_full,
        "manifest": manifest,
    }


def run_formal_in_process(
    checked: dict,
    *,
    stage: str,
    cfg: str,
    host_module_name: str = "host_macos.py",
    deadline_at: str | None = None,
) -> dict:
    """Execute exp1-en/run.py run_stage('formal') in-process with streaming-RAM guard active."""
    exp1_root: Path = checked["exp1_root"]
    verify_upstream_data_files(exp1_root, checked["manifest"])
    if str(exp1_root) not in sys.path:
        sys.path.insert(0, str(exp1_root))

    import admission as exp1_admission  # type: ignore[import-not-found]
    from deadline import deadline_epoch  # type: ignore[import-not-found]
    import ledger as exp1_ledger  # type: ignore[import-not-found]
    import run as exp1_run  # type: ignore[import-not-found]

    host_file = exp1_root / host_module_name
    if not host_file.resolve().is_relative_to(exp1_root) or not host_file.is_file():
        raise ValueError(f"Host adapter missing or outside exp1-en: {host_file}")
    spec = importlib.util.spec_from_file_location("experiment_host", host_file)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load host module spec: {host_file}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    host = module.make_host(checked["host_id"])

    context = exp1_run.Context(cfg, dry=False, host=host, host_file=host_file)
    if context.fp != checked["fingerprint_id"]:
        raise RuntimeError(
            f"Live runner fingerprint {context.fp} disagrees with freeze.json {checked['fingerprint_id']}"
        )

    install_formal_streaming_ram_guard(
        exp1_ledger_mod=exp1_ledger,
        exp1_admission_mod=exp1_admission,
        formal_ns=context.namespace(stage),
    )
    result = exp1_run.run_stage(context, stage, deadline=deadline_epoch(deadline_at))
    print(json.dumps(result, ensure_ascii=False, allow_nan=False), flush=True)
    return result


def main(
    argv=None,
    *,
    now=None,
    execv=None,
    in_process_runner=None,
    exp1_root=None,
    env=None,
    python_executable=None,
    manifest_path=None,
):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="formal", choices=("formal",))
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--expected-fp8", default=DEFAULT_FP8)
    parser.add_argument("--host-module", default="host_macos.py")
    parser.add_argument(
        "--launch-mode",
        default="in_process_streaming",
        choices=("in_process_streaming", "execv"),
        help="Default 'in_process_streaming' prevents 38-56 GiB formal RAM accumulation on 24 GB Mac mini",
    )
    parser.add_argument(
        "--deadline-at",
        default=None,
        help="Optional full ISO datetime with +08:00 timezone (e.g. 2026-11-03T12:00:00+08:00)",
    )
    args = parser.parse_args(argv)

    try:
        if args.deadline_at is not None:
            if not DEADLINE_FORMAT.fullmatch(args.deadline_at):
                raise ValueError("deadline-at must be a full ISO datetime with +08:00 timezone")
            deadline = datetime.fromisoformat(args.deadline_at)
            current = datetime.now(SHANGHAI) if now is None else now()
            if current.tzinfo is None or current.utcoffset() is None:
                raise ValueError("current time must have a timezone")
            current = current.astimezone(SHANGHAI)
            if current >= deadline - timedelta(seconds=900):
                raise ValueError("deadline has less than the required 15-minute margin")

        live_unmocked = (
            (args.launch_mode == "in_process_streaming" and in_process_runner is None)
            or (args.launch_mode == "execv" and execv is None)
        )
        checked = verify_prefreeze_and_env(
            exp1_root=Path(exp1_root) if exp1_root is not None else DEFAULT_EXP1_ROOT,
            cfg=args.config,
            expected_fp8=args.expected_fp8,
            manifest_path=Path(manifest_path) if manifest_path is not None else EXECUTION_MANIFEST_PATH,
            require_upstream_data=live_unmocked,
        )
    except (ValueError, OverflowError, OSError, PermissionError, RuntimeError) as exc:
        print(json.dumps({"ok": False, "detail": {"reason": f"{type(exc).__name__}: {exc}"}}, ensure_ascii=False))
        return 1

    target_env = os.environ if env is None else env
    target_env["HF_HOME"] = checked["hf_home"]
    target_env["HF_HUB_OFFLINE"] = "1"

    if args.launch_mode == "in_process_streaming":
        runner_fn = run_formal_in_process if in_process_runner is None else in_process_runner
        runner_fn(
            checked,
            stage=args.stage,
            cfg=args.config,
            host_module_name=args.host_module,
            deadline_at=args.deadline_at,
        )
        return 0

    py_exe = sys.executable if python_executable is None else str(python_executable)
    command = [
        py_exe,
        "-I",
        "-X",
        "utf8",
        "-B",
        str(checked["run_py"]),
        args.stage,
        args.config,
        "--host-module",
        args.host_module,
    ]
    if args.deadline_at is not None:
        command.extend(["--deadline", args.deadline_at])

    # os.execv keeps this PID and gpujob's inheritable lock file descriptors alive.
    (os.execv if execv is None else execv)(py_exe, command)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
