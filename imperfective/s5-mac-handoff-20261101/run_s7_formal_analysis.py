"""Cross-platform Stage S7 formal statistical analysis and report builder for Experiment 1.

Supports both macOS (streaming raw/formal/qwen3-8b@macmini-m6/895f4e6f/results.jsonl directly)
and Windows/offline verification (--stage dev --unit-index-json, or explicit isolated
--diagnostic-non-confirmatory runs, or synthetic JSONL test namespaces).

Key guarantees:
1. Enforces single-thread BLAS/OMP guardrails and IEEE-754 binary64 Round-to-Nearest-Even
   + gradual-underflow checks before running any numerical routines.
2. Cryptographically verifies Step 5b's 8 sealed core modules
   (code_sha256 = 4e7030de928ec5a7a9fe398c557795ccd4f34a1693c7cebda475a675386537b1),
   certified exact Tango lookup tables
   (exact_tango_tables_sha256 = 090bfbb5a859238ad05100443b4727c61644e030fd2d5e05359c5d575f4c46bf),
   all 6 exact Fraction left cutpoints, and exp1-en/split.json
   (6821a3b3ad2378d51c683b8abc8a5b45d402b9997e3c8957bcda95cd0ef289b7).
3. Fails closed with PermissionError on any non-'dev' stage unless BOTH:
   - s6-s7-execution-manifest.json matches the live SHA256s of gpu_s6_formal_stage_macos.py
     and run_s7_formal_analysis.py and binds expected_frozen_plan_sha256, and
   - a valid cryptographic S5 freeze record (freeze.json + matching PLAN-E1.frozen.md
     embedding the S6/S7 entrypoint SHA256s + c-review.md, status='pass', c_blockers=0,
     user_confirmed=True, non-dry run_id) is verified first.
4. Locks confirmatory 'formal' runs to config='qwen3-8b@macmini-m6', full runner fingerprint
   895f4e6f..., B=5000, FORMAL_ANALYSIS_SEED=2026110201, and full closed ledger input
   (results.jsonl + sessions.json + mandatory fingerprint.json + mandatory statistics.json).
   Any parameter override or --unit-index-json on formal is rejected unless explicitly isolated
   with --diagnostic-non-confirmatory (which sets confirmatory_valid=False, nulls
   confirmatory_claims_option_iii, and refuses writing to canonical formal output filenames).
5. Uses strict closed whitelists when slimming/exporting ledger rows so zero item prose and
   zero arbitrary model-generated JSON keys (such as parsed['extra_keys'] or parsed['object'])
   can ever enter sanitized unit-index files.
6. Disaggregates all 4 terminal statuses cleanly without conflation:
   overall_unavailable = generation_fail (missing_transport) + semantic_parse_fail (missing_format)
   + scoring_fail (missing_score); strict_protocol = checked_ok + checked_fail + unchecked;
   Task M weight-sum tolerance = known_in_tolerance + known_out_of_tolerance + unknown.
7. Reproduces scheme-a-hybrid-calibration-20261101/results/dev-dry-run.json bit-for-bit
   on dev (seed = 2026110199) and runs formal at pre-registered FORMAL_ANALYSIS_SEED = 2026110201,
   recording Python/NumPy/platform versions, peak RSS MiB, and separate timing for zero-missing
   core/profile vs on-demand Tango table construction.
"""

import os
import sys

os.environ["PYTHONDONTWRITEBYTECODE"] = "1"
sys.dont_write_bytecode = True

SINGLE_THREAD_ENV_VARS = (
    "OPENBLAS_NUM_THREADS",
    "OMP_NUM_THREADS",
    "MKL_NUM_THREADS",
    "NUMEXPR_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
)
for _env_k in SINGLE_THREAD_ENV_VARS:
    os.environ[_env_k] = "1"

import argparse
from fractions import Fraction
import hashlib
import json
import math
from pathlib import Path
import platform
import random
import re
import time
from typing import Any, Dict, Iterable, List, Optional, Tuple

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
IMPERFECTIVE_ROOT = SCRIPT_DIR.parent
DEFAULT_EXP1_ROOT = IMPERFECTIVE_ROOT / "exp1-en"
DEFAULT_STEP5B_ROOT = IMPERFECTIVE_ROOT / "scheme-a-hybrid-calibration-20261101"
EXECUTION_MANIFEST_PATH = SCRIPT_DIR / "s6-s7-execution-manifest.json"
CANONICAL_FORMAL_JSON_NAME = "formal-analysis-results.json"
CANONICAL_FORMAL_REPORT_NAME = "report-s7-formal.md"
CANONICAL_FORMAL_UNIT_INDEX_NAME = "formal-unit-index.json"
PROTECTED_CANONICAL_FORMAL_NAMES_LOWER = frozenset(
    {
        CANONICAL_FORMAL_JSON_NAME.lower(),
        CANONICAL_FORMAL_REPORT_NAME.lower(),
        CANONICAL_FORMAL_UNIT_INDEX_NAME.lower(),
    }
)

for _p in (str(DEFAULT_STEP5B_ROOT / "code"), str(DEFAULT_EXP1_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from core_a import (  # noqa: E402
    NAMES_A,
    RANK_MAIN_HI,
    RANK_MAIN_LO,
    TOL_DUST,
    bootstrap_a,
    compute_bessel_t_constants_decimal,
    compute_observed_a,
    extract_slot_contrasts,
    infer_hybrid_bessel_t_tango_a,
    infer_hybrid_pct_tango_a,
    infer_percentile_a,
    infer_studentized_a,
    prepare_sorted_boot_stats,
    weight_batches,
)
from exact_tango import (  # noqa: E402
    build_certified_tables_for_n,
    certify_all_6_left_cuts,
    infer_exact_tango_slot,
    load_certified_tango_tables,
    verify_ieee754_rn_and_subnormals,
    verify_sealed_left_cuts,
)
from formal_engine import (  # noqa: E402
    DEFAULT_DRY_RUN_SEED,
    RANK_95_HI,
    RANK_95_LO,
    _summarize_boot_interval,
    _summarize_exact_tango_trinary,
    compute_observation_profile,
)
from inputs import (  # noqa: E402
    CONDITIONS_13,
    EXPECTED_SPLIT_SHA256,
    L_GOLD_STANDARDS,
    ClusterSampleA,
    file_sha256,
)
from run_sim import (  # noqa: E402
    SEALED_CORE_MODULES,
    compute_core_code_hashes,
    verify_single_thread_env,
)
import gates as exp1_gates  # noqa: E402
from stats_validation import core as v4_core  # noqa: E402
from stats_validation import studentized as v4_studentized  # noqa: E402

FORMAL_ANALYSIS_SEED = 2026110201
FORMAL_BOOTSTRAP_B = 5000
DEFAULT_CONFIG = "qwen3-8b@macmini-m6"
EXPECTED_RUNNER_FP = "895f4e6f51ca3044800eff8ff098970af68f86f54ced061c79c6a5e9ef1900b2"
EXPECTED_STEP5B_CODE_SHA256 = "4e7030de928ec5a7a9fe398c557795ccd4f34a1693c7cebda475a675386537b1"
EXPECTED_TANGO_TABLES_SHA256 = "090bfbb5a859238ad05100443b4727c61644e030fd2d5e05359c5d575f4c46bf"
EXPECTED_TANGO_PAYLOAD_SHA256 = "696ee99245213ad6e7c9fe13d45b1cd239a6e62462888bba86e54a50f82dd89a"
HEX64_RE = re.compile(r"[0-9a-f]{64}")
VALID_TERMINAL_STATUSES = {"ok", "missing_format", "missing_score", "missing_transport"}

# Closed whitelists derived from exp1-en/{parse.py, protocol.py, score.py, run.py}
ALLOWED_PROTOCOL_REASONS = frozenset({
    "last_line",
    "estimate_lines",
    "estimate_range",
    "weight_sum",
    "loose",
    "none",
    "ambiguous",
    "label_form",
    "fenced",
    "dup_key",
    "json",
    "not_object",
    "no_reasoning",
    "label_first",
    "extra_keys",
    "n_interruptions",
})
ALLOWED_PARSED_FORM_VALUES = frozenset({"exact", "loose", "none", "ambiguous", "json"})
ALLOWED_PARSED_FORMS_ITEMS = frozenset({
    "plain",
    "exact",
    "bold",
    "fullwidth_colon",
    "lowercase_key",
    "other_case_key",
    "space_before_percent",
    "trailing_text",
})
ALLOWED_LABEL_VALUES = frozenset({"True", "False", "Unknown"})
SAFE_ERROR_CODE_RE = re.compile(r"[A-Za-z0-9_:.+-]{1,64}")
SAFE_Q_STATUS_RE = re.compile(r"(?:full|bounded|ready|not_attempted|not_applicable|missing:[A-Za-z0-9_]{1,32})")
COST_CONTRASTS_SPEC = (
    ("M_Z_minus_P_CoT", "M/Z", "P/CoT"),
    ("M_CoT_minus_P_CoT", "M/CoT", "P/CoT"),
    ("P_CoT_minus_P_Z", "P/CoT", "P/Z"),
    ("M_Z_minus_P_Z", "M/Z", "P/Z"),
    ("M_CoT_minus_P_Z", "M/CoT", "P/Z"),
    ("M_CoT_minus_M_Z", "M/CoT", "M/Z"),
    ("L_CoT_minus_L_Z", "L/CoT", "L/Z"),
    ("P_DAP_minus_P_Z", "P/DAP", "P/Z"),
    ("M_DAP_minus_P_Z", "M/DAP", "P/Z"),
    ("M_DAP_minus_P_DAP", "M/DAP", "P/DAP"),
    ("M_DAP_minus_M_Z", "M/DAP", "M/Z"),
    ("M_Z_minus_P_DAP", "M/Z", "P/DAP"),
    ("L_DAP_minus_L_Z", "L/DAP", "L/Z"),
    ("P_CF_minus_P_Z", "P/CF", "P/Z"),
    ("M_CF_minus_P_Z", "M/CF", "P/Z"),
    ("M_CF_minus_P_CF", "M/CF", "P/CF"),
    ("M_CF_minus_M_Z", "M/CF", "M/Z"),
    ("M_Z_minus_P_CF", "M/Z", "P/CF"),
    ("L_CF_minus_L_Z", "L/CF", "L/Z"),
)


def _get_peak_rss_mib() -> Optional[float]:
    """Return process peak RSS / peak working set in MiB across macOS, Linux, and Windows."""
    try:
        if sys.platform == "win32":
            import ctypes
            from ctypes import wintypes

            class PROCESS_MEMORY_COUNTERS(ctypes.Structure):
                _fields_ = [
                    ("cb", wintypes.DWORD),
                    ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t),
                    ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t),
                    ("PeakPagefileUsage", ctypes.c_size_t),
                ]

            pmc = PROCESS_MEMORY_COUNTERS()
            pmc.cb = ctypes.sizeof(PROCESS_MEMORY_COUNTERS)
            k32 = ctypes.windll.kernel32
            get_proc = k32.GetCurrentProcess
            get_proc.argtypes = []
            get_proc.restype = wintypes.HANDLE
            proc = get_proc()
            fn = getattr(k32, "K32GetProcessMemoryInfo", None)
            if fn is None:
                fn = ctypes.windll.psapi.GetProcessMemoryInfo
            fn.argtypes = [wintypes.HANDLE, ctypes.POINTER(PROCESS_MEMORY_COUNTERS), wintypes.DWORD]
            fn.restype = wintypes.BOOL
            if fn(proc, ctypes.byref(pmc), pmc.cb):
                return round(float(pmc.PeakWorkingSetSize) / (1024.0 * 1024.0), 3)
            return None
        else:
            import resource

            ru = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            if sys.platform == "darwin":
                return round(float(ru) / (1024.0 * 1024.0), 3)
            return round(float(ru) / 1024.0, 3)
    except Exception:
        return None


def canonical_digest(value: Any) -> str:
    """Match exp1-en/common.py canonical JSON SHA256."""
    text = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write_text_lf(path: Path, content: str) -> None:
    """Write UTF-8 LF text atomically."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}.{time.time_ns()}")
    with tmp.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(content.replace("\r\n", "\n"))
    os.replace(tmp, path)


def atomic_write_json_lf(path: Path, payload: Any) -> None:
    """Write UTF-8 LF indented JSON atomically."""
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    atomic_write_text_lf(path, serialized)


def build_planned_units_from_split(split_data: dict, stage: str) -> List[dict]:
    """Deterministically reconstruct exp1-en/run.py Context.plan(stage) from split.json."""
    if stage not in split_data or "ids" not in split_data[stage]:
        raise ValueError(f"split.json missing stage '{stage}' ids")
    ids = sorted(split_data[stage]["ids"])
    random.Random(20261091).shuffle(ids)
    return [
        {
            "id": iid,
            "task": task,
            "prompt": prompt,
            "unit_key": f"{iid}/{task}/{prompt}",
            "gold_label": L_GOLD_STANDARDS[iid.split("_", 1)[0]],
        }
        for iid in ids
        for task, prompt in CONDITIONS_13
    ]


def verify_step5b_sealed_engine(
    step5b_root: Path = DEFAULT_STEP5B_ROOT,
    split_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Cross-platform verification of Step 5b's 8 sealed core modules, Tango tables, 6 left cuts, and split.json."""
    step5b_root = Path(step5b_root).resolve()
    code_dir = step5b_root / "code"
    sealed_identity_path = step5b_root / "manifests" / "sealed-run-identity.json"
    tango_npz_path = step5b_root / "manifests" / "exact-tango-tables.npz"
    resolved_split_path = Path(split_path or (DEFAULT_EXP1_ROOT / "split.json")).resolve()

    for label, req_path in (
        ("sealed_identity", sealed_identity_path),
        ("exact_tango_tables", tango_npz_path),
        ("split_json", resolved_split_path),
    ):
        if not req_path.is_file():
            raise FileNotFoundError(f"Step 5b sealed verification failed: {label} missing at {req_path}")

    env_snapshot = verify_single_thread_env()
    ieee_info = verify_ieee754_rn_and_subnormals()
    sealed = json.loads(sealed_identity_path.read_text(encoding="utf-8"))

    if sealed.get("code_sha256") != EXPECTED_STEP5B_CODE_SHA256:
        raise RuntimeError(f"Unexpected sealed-run-identity code_sha256: {sealed.get('code_sha256')}")
    if sealed.get("exact_tango_tables_sha256") != EXPECTED_TANGO_TABLES_SHA256:
        raise RuntimeError("Unexpected sealed-run-identity exact_tango_tables_sha256")
    if sealed.get("exact_tango_tables_payload_sha256") != EXPECTED_TANGO_PAYLOAD_SHA256:
        raise RuntimeError("Unexpected sealed-run-identity exact_tango_tables_payload_sha256")

    if "certified_left_cuts_6" not in sealed or not isinstance(sealed["certified_left_cuts_6"], dict):
        raise ValueError("sealed-run-identity missing certified_left_cuts_6")
    verify_sealed_left_cuts(sealed["certified_left_cuts_6"])
    fresh_cuts = certify_all_6_left_cuts()
    for cut_key, exp_rec in fresh_cuts.items():
        got_rec = sealed["certified_left_cuts_6"].get(cut_key)
        if (
            not isinstance(got_rec, dict)
            or got_rec.get("theta_cut_hex") != exp_rec["theta_cut_hex"]
            or got_rec.get("half_alpha_lo_hex") != exp_rec["half_alpha_lo_hex"]
        ):
            raise RuntimeError(f"Certified left-cut hex mismatch on {cut_key}")

    tango_bundle = load_certified_tango_tables(
        npz_path=tango_npz_path,
        expected_file_sha256=EXPECTED_TANGO_TABLES_SHA256,
        expected_payload_sha256=EXPECTED_TANGO_PAYLOAD_SHA256,
        force_reload=True,
    )

    code_sha, module_shas = compute_core_code_hashes(code_dir)
    if code_sha != EXPECTED_STEP5B_CODE_SHA256:
        raise RuntimeError(f"Step 5b 8-module code_sha256 mismatch: {code_sha} != {EXPECTED_STEP5B_CODE_SHA256}")

    sealed_mods = sealed.get("module_sha256", {})
    if set(sealed_mods.keys()) != set(SEALED_CORE_MODULES):
        raise RuntimeError("Step 5b module_sha256 keys mismatch")
    for mod_name, cur_sha in module_shas.items():
        if sealed_mods.get(mod_name) != cur_sha:
            raise RuntimeError(f"Step 5b sealed module mismatch on {mod_name}: {cur_sha} != {sealed_mods.get(mod_name)}")

    cur_split_sha = file_sha256(resolved_split_path)
    if cur_split_sha != EXPECTED_SPLIT_SHA256 or cur_split_sha != sealed.get("split_sha256"):
        raise RuntimeError(f"split.json SHA256 mismatch: {cur_split_sha} != {EXPECTED_SPLIT_SHA256}")

    return {
        "verified": True,
        "code_sha256": code_sha,
        "module_sha256": module_shas,
        "exact_tango_tables_sha256": tango_bundle["file_sha256"],
        "exact_tango_tables_payload_sha256": tango_bundle["payload_sha256"],
        "split_sha256": cur_split_sha,
        "single_thread_env": env_snapshot,
        "ieee754_rn_subnormals": ieee_info,
    }


def verify_execution_manifest_payload(
    manifest: dict,
    *,
    live_entrypoint_shas: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Pure in-memory validation of s6-s7-execution-manifest.json payload."""
    if not isinstance(manifest, dict):
        raise PermissionError("Execution manifest must be a JSON object")
    if manifest.get("schema_version") != "exp1-s6-s7-execution-manifest-v1":
        raise PermissionError(f"Unexpected execution manifest schema_version: {manifest.get('schema_version')!r}")
    if manifest.get("config") != DEFAULT_CONFIG:
        raise PermissionError(f"Execution manifest config mismatch: {manifest.get('config')!r}")
    if manifest.get("expected_runner_fingerprint") != EXPECTED_RUNNER_FP:
        raise PermissionError("Execution manifest expected_runner_fingerprint mismatch")
    if manifest.get("expected_fp8") != EXPECTED_RUNNER_FP[:8]:
        raise PermissionError("Execution manifest expected_fp8 mismatch")
    if type(manifest.get("formal_bootstrap_b")) is not int or manifest["formal_bootstrap_b"] != FORMAL_BOOTSTRAP_B:
        raise PermissionError("Execution manifest formal_bootstrap_b must equal integer 5000")
    if type(manifest.get("formal_analysis_seed")) is not int or manifest["formal_analysis_seed"] != FORMAL_ANALYSIS_SEED:
        raise PermissionError("Execution manifest formal_analysis_seed must equal integer 2026110201")
    if manifest.get("confirmatory_unit_index_input_allowed") is not False:
        raise PermissionError("Execution manifest must set confirmatory_unit_index_input_allowed = False")

    plan_sha = str(manifest.get("expected_frozen_plan_sha256", ""))
    if not HEX64_RE.fullmatch(plan_sha):
        raise PermissionError("Execution manifest missing valid 64-hex expected_frozen_plan_sha256")

    entrypoints = manifest.get("entrypoints")
    if not isinstance(entrypoints, dict):
        raise PermissionError("Execution manifest missing entrypoints mapping")
    for ep_name in ("gpu_s6_formal_stage_macos.py", "run_s7_formal_analysis.py"):
        ep_sha = str(entrypoints.get(ep_name, ""))
        if not HEX64_RE.fullmatch(ep_sha):
            raise PermissionError(f"Execution manifest missing valid 64-hex SHA256 for {ep_name}")
        if live_entrypoint_shas is not None:
            got_sha = live_entrypoint_shas.get(ep_name)
            if got_sha != ep_sha:
                raise PermissionError(f"{ep_name} SHA256 {got_sha} disagrees with execution manifest {ep_sha}")

    return manifest


def load_and_verify_execution_manifest(manifest_path: Path = EXECUTION_MANIFEST_PATH) -> Dict[str, Any]:
    """Load s6-s7-execution-manifest.json from disk and verify live S6 & S7 entrypoint SHA256s."""
    manifest_path = Path(manifest_path).resolve()
    if not manifest_path.is_file():
        raise PermissionError(f"S6/S7 execution manifest missing: {manifest_path}")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    s6_path = SCRIPT_DIR / "gpu_s6_formal_stage_macos.py"
    if not s6_path.is_file():
        raise PermissionError(f"Bound S6 launcher missing: {s6_path}")
    live_shas = {
        "gpu_s6_formal_stage_macos.py": file_sha256(s6_path.resolve()),
        "run_s7_formal_analysis.py": file_sha256(Path(__file__).resolve()),
    }
    return verify_execution_manifest_payload(manifest, live_entrypoint_shas=live_shas)


def verify_freeze_and_manifest_payloads(
    freeze: dict,
    frozen_plan_text: str,
    frozen_plan_sha256: str,
    split_data: dict,
    manifest: dict,
    *,
    cfg: str = DEFAULT_CONFIG,
    expected_fp: Optional[str] = EXPECTED_RUNNER_FP,
    live_entrypoint_shas: Optional[Dict[str, str]] = None,
    dev_gate: Optional[dict] = None,
    determinism_rec: Optional[dict] = None,
) -> Dict[str, Any]:
    """Pure in-memory S5 freeze + S6/S7 execution manifest binding verification (zero disk writes/reads)."""
    verify_execution_manifest_payload(manifest, live_entrypoint_shas=live_entrypoint_shas)

    required = {
        "type",
        "status",
        "config",
        "fingerprint_id",
        "source_stage",
        "planned_units_sha256",
        "ledger_digest",
        "written_at",
        "frozen_plan_sha256",
        "c_blockers",
        "c_review_file",
        "user_confirmed",
        "confirmed_at",
    }
    if not isinstance(freeze, dict) or not required <= set(freeze.keys()):
        missing = sorted(required - set(freeze.keys())) if isinstance(freeze, dict) else sorted(required)
        raise PermissionError(f"freeze.json missing required fields: {missing}")
    if freeze.get("type") != "freeze" or freeze.get("status") != "pass":
        raise PermissionError("freeze.json type/status must be 'freeze'/'pass'")
    if freeze.get("config") != cfg or cfg != manifest["config"]:
        raise PermissionError(f"freeze.json config mismatch: {freeze.get('config')!r} != {cfg!r}")
    if str(freeze.get("run_id", "")).startswith("E1-DRY-"):
        raise PermissionError("E1-DRY freeze record forbidden for formal analysis")

    fp_val = str(freeze.get("fingerprint_id", ""))
    if not HEX64_RE.fullmatch(fp_val):
        raise PermissionError("freeze.json fingerprint_id is not a 64-char lowercase hex SHA256")
    if expected_fp is not None and fp_val != expected_fp:
        raise PermissionError(f"freeze.json fingerprint_id mismatch: {fp_val} != {expected_fp}")
    if fp_val != manifest["expected_runner_fingerprint"]:
        raise PermissionError("freeze.json fingerprint_id disagrees with bound execution manifest")

    if freeze.get("source_stage") != "dev":
        raise PermissionError("freeze.json source_stage must equal 'dev'")

    expected_dev_plan_sha = canonical_digest(build_planned_units_from_split(split_data, "dev"))
    if freeze.get("planned_units_sha256") != expected_dev_plan_sha:
        raise PermissionError(
            f"freeze.json planned_units_sha256 mismatch against dev split: "
            f"{freeze.get('planned_units_sha256')} != {expected_dev_plan_sha}"
        )

    ledger_dig = str(freeze.get("ledger_digest", ""))
    if not HEX64_RE.fullmatch(ledger_dig):
        raise PermissionError("freeze.json ledger_digest is not a valid 64-hex SHA256")

    if dev_gate is not None:
        if dev_gate.get("status") != "pass" or dev_gate.get("ledger_digest") != ledger_dig:
            raise PermissionError("freeze.json ledger_digest disagrees with dev/gate.json")
    if determinism_rec is not None:
        if determinism_rec.get("status") != "pass" or determinism_rec.get("ledger_digest") != ledger_dig:
            raise PermissionError("freeze.json ledger_digest disagrees with determinism.json")

    if type(freeze.get("c_blockers")) is not int or freeze["c_blockers"] != 0:
        raise PermissionError("freeze.json c_blockers must be integer 0")
    if freeze.get("user_confirmed") is not True or not str(freeze.get("confirmed_at", "")).strip():
        raise PermissionError("freeze.json requires user_confirmed=True and non-empty confirmed_at")

    if frozen_plan_sha256 != freeze.get("frozen_plan_sha256"):
        raise PermissionError("PLAN-E1.frozen.md SHA256 does not match freeze.json frozen_plan_sha256")
    if frozen_plan_sha256 != manifest["expected_frozen_plan_sha256"]:
        raise PermissionError(
            f"PLAN-E1.frozen.md SHA256 {frozen_plan_sha256} does not match bound execution manifest "
            f"{manifest['expected_frozen_plan_sha256']}"
        )

    for ep_name, ep_sha in manifest["entrypoints"].items():
        if ep_sha not in frozen_plan_text:
            raise PermissionError(f"PLAN-E1.frozen.md does not bind {ep_name} SHA256 {ep_sha}")

    return {
        "freeze_verified": True,
        "frozen_plan_sha256": frozen_plan_sha256,
        "expected_frozen_plan_sha256": manifest["expected_frozen_plan_sha256"],
        "entrypoints_bound": dict(manifest["entrypoints"]),
        "confirmed_at": freeze["confirmed_at"],
        "c_blockers": freeze["c_blockers"],
        "fingerprint_id": fp_val,
        "dev_ledger_digest": ledger_dig,
    }


def verify_s5_freeze_gate(
    exp1_root: Path,
    split_data: dict,
    cfg: str = DEFAULT_CONFIG,
    expected_fp: Optional[str] = EXPECTED_RUNNER_FP,
    *,
    manifest_path: Path = EXECUTION_MANIFEST_PATH,
) -> Dict[str, Any]:
    """Fail-closed cryptographic enforcement of Stage S5 freeze + S6/S7 manifest binding before reading formal data."""
    exp1_root = Path(exp1_root).resolve()
    manifest = load_and_verify_execution_manifest(manifest_path=manifest_path)

    fp_prefix = expected_fp[:8] if expected_fp else None
    cfg_freeze_root = exp1_root / "freeze" / cfg
    if fp_prefix is not None:
        freeze_dir = cfg_freeze_root / fp_prefix
    else:
        candidates = [d for d in cfg_freeze_root.iterdir() if d.is_dir()] if cfg_freeze_root.is_dir() else []
        if len(candidates) != 1:
            raise PermissionError(f"Cannot uniquely locate freeze directory under {cfg_freeze_root}")
        freeze_dir = candidates[0]

    freeze_json_path = freeze_dir / "freeze.json"
    frozen_plan_path = freeze_dir / "PLAN-E1.frozen.md"
    if not freeze_json_path.is_file() or not frozen_plan_path.is_file():
        raise PermissionError(
            f"Execution on formal split forbidden: S5 freeze files missing in {freeze_dir}"
        )

    freeze = json.loads(freeze_json_path.read_text(encoding="utf-8"))
    frozen_plan_text = frozen_plan_path.read_text(encoding="utf-8")
    actual_frozen_plan_sha = file_sha256(frozen_plan_path)

    fp_val = str(freeze.get("fingerprint_id", ""))
    dev_gate = None
    det_rec = None
    if len(fp_val) >= 8:
        dev_gate_path = exp1_root / "raw" / "dev" / cfg / fp_val[:8] / "gate.json"
        if dev_gate_path.is_file():
            dev_gate = json.loads(dev_gate_path.read_text(encoding="utf-8"))
        det_path = exp1_root / "raw" / "admission" / cfg / fp_val[:8] / "determinism.json"
        if det_path.is_file():
            det_rec = json.loads(det_path.read_text(encoding="utf-8"))

    verified_core = verify_freeze_and_manifest_payloads(
        freeze=freeze,
        frozen_plan_text=frozen_plan_text,
        frozen_plan_sha256=actual_frozen_plan_sha,
        split_data=split_data,
        manifest=manifest,
        cfg=cfg,
        expected_fp=expected_fp,
        dev_gate=dev_gate,
        determinism_rec=det_rec,
    )

    c_review_str = str(freeze.get("c_review_file", "")).strip()
    if not c_review_str:
        raise PermissionError("freeze.json c_review_file missing or empty")
    c_review_rel = Path(c_review_str)
    c_review_path = c_review_rel if c_review_rel.is_absolute() else (exp1_root / c_review_rel)
    c_review_resolved = c_review_path.resolve()
    if not c_review_resolved.is_relative_to(exp1_root) or not c_review_resolved.is_file():
        raise PermissionError("freeze.json c_review_file missing or outside exp1-en")

    return {
        **verified_core,
        "freeze_json_path": str(freeze_json_path),
        "freeze_json_sha256": file_sha256(freeze_json_path),
        "c_review_sha256": file_sha256(c_review_resolved),
        "execution_manifest_sha256": file_sha256(Path(manifest_path).resolve()),
    }


def enforce_confirmatory_formal_lock(
    *,
    stage: str,
    cfg: str,
    expected_fp: Optional[str],
    b_reps: int,
    seed: Optional[int],
    allow_non_ok: Optional[bool],
    unit_index_json_path: Optional[Path],
    test_on_demand_tango_grid: Optional[Tuple[int, int]],
    diagnostic_non_confirmatory: bool,
    out_json_path: Optional[Path] = None,
    out_report_path: Optional[Path] = None,
    write_unit_index_path: Optional[Path] = None,
    results_jsonl_path: Optional[Path] = None,
    split_path: Optional[Path] = None,
    manifest_path: Path = EXECUTION_MANIFEST_PATH,
) -> Optional[Dict[str, Any]]:
    """Enforce zero-override parameter/path lock on confirmatory formal runs, and protect all canonical output targets."""
    output_channels = (
        ("out_json", out_json_path, CANONICAL_FORMAL_JSON_NAME.lower()),
        ("out_report", out_report_path, CANONICAL_FORMAL_REPORT_NAME.lower()),
        ("write_unit_index", write_unit_index_path, CANONICAL_FORMAL_UNIT_INDEX_NAME.lower()),
    )
    resolved_targets_lower: Dict[str, str] = {}
    for ch_name, ch_path, _ in output_channels:
        if ch_path is None:
            continue
        norm_target = str(Path(ch_path).resolve()).lower()
        if norm_target in resolved_targets_lower:
            raise PermissionError(
                f"Output channel '{ch_name}' collides with '{resolved_targets_lower[norm_target]}' on {ch_path}"
            )
        resolved_targets_lower[norm_target] = ch_name

    if diagnostic_non_confirmatory or stage != "formal":
        for ch_name, ch_path, _ in output_channels:
            if ch_path is not None and Path(ch_path).name.lower() in PROTECTED_CANONICAL_FORMAL_NAMES_LOWER:
                raise PermissionError(
                    f"Non-confirmatory run (stage={stage!r}, diagnostic_non_confirmatory={diagnostic_non_confirmatory}) "
                    f"refuses writing channel '{ch_name}' to protected canonical formal filename {Path(ch_path).name!r}; "
                    f"protected names (case-insensitive): {sorted(PROTECTED_CANONICAL_FORMAL_NAMES_LOWER)}"
                )
        return None

    for ch_name, ch_path, allowed_canon_lower in output_channels:
        if ch_path is None:
            continue
        bname_lower = Path(ch_path).name.lower()
        if bname_lower in PROTECTED_CANONICAL_FORMAL_NAMES_LOWER and bname_lower != allowed_canon_lower:
            raise PermissionError(
                f"Confirmatory output channel '{ch_name}' cannot target another channel's canonical filename {Path(ch_path).name!r}"
            )

    if Path(manifest_path).resolve() != EXECUTION_MANIFEST_PATH.resolve():
        raise PermissionError(
            f"Confirmatory formal run locked to canonical execution manifest {EXECUTION_MANIFEST_PATH}, got {manifest_path}"
        )
    manifest = load_and_verify_execution_manifest(manifest_path=manifest_path)
    if cfg != DEFAULT_CONFIG:
        raise PermissionError(f"Confirmatory formal run locked to config {DEFAULT_CONFIG!r}, got {cfg!r}")
    if expected_fp != EXPECTED_RUNNER_FP:
        raise PermissionError(f"Confirmatory formal run locked to runner fingerprint {EXPECTED_RUNNER_FP!r}")
    if type(b_reps) is not int or b_reps != FORMAL_BOOTSTRAP_B:
        raise PermissionError(
            f"Confirmatory formal run locked to B={FORMAL_BOOTSTRAP_B}, got b_reps={b_reps!r}; "
            "use --diagnostic-non-confirmatory for non-confirmatory diagnostics"
        )
    if seed is not None and (type(seed) is not int or seed != FORMAL_ANALYSIS_SEED):
        raise PermissionError(
            f"Confirmatory formal run locked to FORMAL_ANALYSIS_SEED={FORMAL_ANALYSIS_SEED}, got seed={seed!r}; "
            "use --diagnostic-non-confirmatory for non-confirmatory diagnostics"
        )
    if allow_non_ok is False:
        raise PermissionError("Confirmatory formal run must allow worst-case bounds on non-ok terminal statuses")
    if unit_index_json_path is not None:
        raise PermissionError(
            "Confirmatory formal run forbids --unit-index-json because it bypasses live ledger closeout verification "
            "(sessions.json, fingerprint.json, statistics.json); pass --diagnostic-non-confirmatory for offline diagnostics"
        )
    if results_jsonl_path is not None:
        raise PermissionError(
            "Confirmatory formal run forbids --results-jsonl path override; ledger must resolve from canonical exp1_root namespace"
        )
    if split_path is not None:
        raise PermissionError(
            "Confirmatory formal run forbids --split path override; split.json must resolve from canonical exp1_root"
        )
    if test_on_demand_tango_grid is not None:
        raise PermissionError("Confirmatory formal run forbids _test_on_demand_tango_grid override")
    return manifest


def validate_stage_split(split_data: dict, stage: str) -> Tuple[List[str], List[str], Dict[str, List[str]], set]:
    """Validate frozen split.json for either 'dev' (20+20) or 'formal' (80+80)."""
    if stage not in ("dev", "formal"):
        raise ValueError(f"Unsupported split stage '{stage}' (expected 'dev' or 'formal')")
    if not isinstance(split_data, dict) or stage not in split_data:
        raise ValueError(f"split.json missing '{stage}' section")

    sec = split_data[stage]
    expected_n = 20 if stage == "dev" else 80
    telic_clusters = sorted(list(sec.get("telic_clusters", [])))
    atelic_clusters = sorted(list(sec.get("atelic_clusters", [])))

    if len(telic_clusters) != expected_n or len(set(telic_clusters)) != expected_n:
        raise ValueError(f"Expected {expected_n} unique telic clusters in {stage}, got {len(telic_clusters)}")
    if len(atelic_clusters) != expected_n or len(set(atelic_clusters)) != expected_n:
        raise ValueError(f"Expected {expected_n} unique atelic clusters in {stage}, got {len(atelic_clusters)}")

    if stage == "formal":
        dev_sec = split_data.get("dev", {})
        if not set(telic_clusters).isdisjoint(set(dev_sec.get("telic_clusters", []))):
            raise ValueError("formal telic_clusters overlap with dev telic_clusters")
        if not set(atelic_clusters).isdisjoint(set(dev_sec.get("atelic_clusters", []))):
            raise ValueError("formal atelic_clusters overlap with dev atelic_clusters")

    group_items = {
        "A": [f"A_{s}" for s in telic_clusters],
        "C": [f"C_{s}" for s in telic_clusters],
        "B": [f"B_{s}" for s in atelic_clusters],
        "D": [f"D_{s}" for s in atelic_clusters],
    }
    sets = [set(group_items[g]) for g in ("A", "B", "C", "D")]
    for i in range(4):
        for j in range(i + 1, 4):
            if not sets[i].isdisjoint(sets[j]):
                raise ValueError("Groups A, B, C, D are not pairwise disjoint")

    all_ids = sets[0] | sets[1] | sets[2] | sets[3]
    if len(all_ids) != 4 * expected_n:
        raise ValueError(f"Expected {4 * expected_n} item IDs in {stage}, got {len(all_ids)}")
    if set(sec.get("ids", [])) != all_ids:
        raise ValueError(f"split.json {stage}['ids'] does not match reconstructed item IDs")

    return telic_clusters, atelic_clusters, group_items, all_ids


def _slim_parsed_whitelist(parsed: Optional[dict]) -> Optional[dict]:
    """Closed-whitelist sanitizer for parsed outputs: strips object prose AND arbitrary extra_keys names."""
    if parsed is None:
        return None
    if not isinstance(parsed, dict):
        raise ValueError("parsed must be dict or None")

    out: Dict[str, Any] = {}
    if "ok" in parsed:
        if parsed["ok"] is not None and not isinstance(parsed["ok"], bool):
            raise ValueError("parsed['ok'] must be bool or None")
        out["ok"] = parsed["ok"]

    if "value" in parsed:
        v = parsed["value"]
        if v is not None:
            if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(float(v)):
                raise ValueError(f"Invalid parsed['value']: {v!r}")
            out["value"] = float(v)
        else:
            out["value"] = None

    if "error" in parsed:
        err = parsed["error"]
        if err is not None:
            if not isinstance(err, str) or not SAFE_ERROR_CODE_RE.fullmatch(err):
                raise ValueError(f"Non-whitelisted parsed['error'] token: {err!r}")
            out["error"] = err
        else:
            out["error"] = None

    if "form" in parsed:
        fm = parsed["form"]
        if fm is not None:
            if not isinstance(fm, str) or fm not in ALLOWED_PARSED_FORM_VALUES:
                raise ValueError(f"Non-whitelisted parsed['form']: {fm!r}")
            out["form"] = fm
        else:
            out["form"] = None

    if "forms" in parsed:
        fms = parsed["forms"]
        if fms is not None:
            if not isinstance(fms, list) or any((not isinstance(x, str) or x not in ALLOWED_PARSED_FORMS_ITEMS) for x in fms):
                raise ValueError(f"Non-whitelisted parsed['forms']: {fms!r}")
            out["forms"] = list(fms)
        else:
            out["forms"] = None

    for list_key in ("estimates", "weights"):
        if list_key in parsed:
            arr = parsed[list_key]
            if arr is not None:
                if not isinstance(arr, list) or any(
                    isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(float(x))
                    for x in arr
                ):
                    raise ValueError(f"Invalid parsed[{list_key!r}]")
                out[list_key] = [float(x) for x in arr]
            else:
                out[list_key] = None

    for float_key in ("weight_sum", "endpoint_mass", "weighted_sd"):
        if float_key in parsed:
            fv = parsed[float_key]
            if fv is not None:
                if isinstance(fv, bool) or not isinstance(fv, (int, float)) or not math.isfinite(float(fv)):
                    raise ValueError(f"Invalid parsed[{float_key!r}]")
                out[float_key] = float(fv)
            else:
                out[float_key] = None

    if "label" in parsed:
        lbl = parsed["label"]
        if lbl is not None:
            if not isinstance(lbl, str) or lbl not in ALLOWED_LABEL_VALUES:
                raise ValueError(f"Non-whitelisted parsed['label']: {lbl!r}")
            out["label"] = lbl
        else:
            out["label"] = None

    for int_key in ("char_start", "n_interruptions"):
        if int_key in parsed:
            iv = parsed[int_key]
            if iv is not None:
                if type(iv) is not int:
                    raise ValueError(f"Invalid parsed[{int_key!r}]: expected int or None")
                out[int_key] = iv
            else:
                out[int_key] = None

    for bool_key in ("weight_sum_in_tolerance", "fenced", "reasoning_ok", "label_last", "label_form", "escape"):
        if bool_key in parsed:
            bv = parsed[bool_key]
            if bv is not None and not isinstance(bv, bool):
                raise ValueError(f"Invalid parsed[{bool_key!r}]: expected bool or None")
            out[bool_key] = bv

    # Convert arbitrary model-generated extra_keys into count + SHA256 digest ONLY (zero raw key strings)
    if "extra_keys" in parsed and parsed["extra_keys"] is not None:
        ek = parsed["extra_keys"]
        if not isinstance(ek, list):
            raise ValueError("parsed['extra_keys'] must be a list")
        ek_strs = [str(x) for x in ek]
        out["extra_key_count"] = len(ek_strs)
        out["extra_keys_sha256"] = canonical_digest(ek_strs) if ek_strs else None
    elif "extra_key_count" in parsed:
        if type(parsed["extra_key_count"]) is not int or parsed["extra_key_count"] < 0:
            raise ValueError("Invalid parsed['extra_key_count']")
        out["extra_key_count"] = parsed["extra_key_count"]
        if "extra_keys_sha256" in parsed:
            eks = parsed["extra_keys_sha256"]
            if eks is not None and (not isinstance(eks, str) or not HEX64_RE.fullmatch(eks)):
                raise ValueError("Invalid parsed['extra_keys_sha256']")
            out["extra_keys_sha256"] = eks

    return out


def _slim_phases_whitelist(phases: Optional[dict]) -> Dict[str, Any]:
    """Closed-whitelist sanitizer for row['phases']."""
    if phases is None:
        return {}
    if not isinstance(phases, dict):
        raise ValueError("phases must be dict or None")
    out: Dict[str, Any] = {}
    if "generation" in phases:
        g = phases["generation"]
        if g not in ("ok", "failed"):
            raise ValueError(f"Invalid phases['generation']: {g!r}")
        out["generation"] = g
    if "parse" in phases:
        p = phases["parse"]
        if p not in ("ok", "failed"):
            raise ValueError(f"Invalid phases['parse']: {p!r}")
        out["parse"] = p
    if "protocol" in phases:
        pr = phases["protocol"]
        if not isinstance(pr, bool):
            raise ValueError(f"Invalid phases['protocol']: {pr!r}")
        out["protocol"] = pr
    if "scoring" in phases:
        sc = phases["scoring"]
        if not isinstance(sc, str) or not SAFE_Q_STATUS_RE.fullmatch(sc):
            raise ValueError(f"Invalid phases['scoring']: {sc!r}")
        out["scoring"] = sc
    return out


def _slim_protocol_whitelist(protocol: Optional[dict]) -> Optional[dict]:
    """Closed-whitelist sanitizer for row['protocol'] enforcing the 16-item ALLOWED_PROTOCOL_REASONS set."""
    if protocol is None:
        return None
    if not isinstance(protocol, dict):
        raise ValueError("protocol must be dict or None")
    if not isinstance(protocol.get("protocol_ok"), bool):
        raise ValueError("protocol['protocol_ok'] must be bool")
    raw_reasons = protocol.get("reasons")
    if not isinstance(raw_reasons, list):
        raise ValueError("protocol['reasons'] must be a list")
    reasons: List[str] = []
    for r in raw_reasons:
        if not isinstance(r, str) or r not in ALLOWED_PROTOCOL_REASONS:
            raise ValueError(f"Non-whitelisted protocol reason: {r!r}")
        reasons.append(r)
    return {"protocol_ok": protocol["protocol_ok"], "reasons": reasons}


def _slim_q_without_topn(q: Optional[dict]) -> Optional[dict]:
    """Closed-whitelist sanitizer for row['q'] preserving [q_L, q_U] & closed q_status while stripping topN/lead text."""
    if q is None:
        return None
    if not isinstance(q, dict):
        raise ValueError("q must be dict or None")
    out: Dict[str, Any] = {}
    if "q_status" in q:
        qs = q["q_status"]
        if qs is None:
            out["q_status"] = None
        elif not isinstance(qs, str) or not SAFE_Q_STATUS_RE.fullmatch(qs):
            raise ValueError(f"Non-whitelisted q['q_status']: {qs!r}")
        else:
            out["q_status"] = qs
    for fkey in ("q_L", "q_U"):
        if fkey in q and q[fkey] is not None:
            fv = q[fkey]
            if isinstance(fv, bool) or not isinstance(fv, (int, float)) or not math.isfinite(float(fv)):
                raise ValueError(f"Invalid q[{fkey!r}]")
            out[fkey] = float(fv)
    if "j" in q and q["j"] is not None:
        if type(q["j"]) is not int:
            raise ValueError("Invalid q['j']")
        out["j"] = q["j"]
    if "lead" in q and isinstance(q["lead"], str):
        out["lead_len"] = len(q["lead"])
        out["has_lead"] = len(q["lead"]) > 0
    elif "lead_len" in q and type(q["lead_len"]) is int:
        out["lead_len"] = q["lead_len"]
        out["has_lead"] = bool(q.get("has_lead", q["lead_len"] > 0))
    return out


# Backward-compatible alias for external callers
_slim_parsed_without_prose = _slim_parsed_whitelist


def validate_and_slim_ledger_stream(
    raw_lines: Iterable[bytes],
    *,
    split_data: dict,
    stage: str,
    sessions: Optional[dict],
    fingerprint_meta: Optional[dict],
    saved_gate: Optional[dict],
    cfg: str = DEFAULT_CONFIG,
    expected_fp: Optional[str] = EXPECTED_RUNNER_FP,
    has_run_lock: bool = False,
    has_paused: bool = False,
    source_label: str = "<in-memory>",
    sessions_sha256: Optional[str] = None,
    fingerprint_sha256: Optional[str] = None,
    gate_file_label: Optional[str] = None,
) -> Tuple[List[dict], Dict[str, Any]]:
    """Pure streaming ledger validator & closed-whitelist sanitizer (supports both disk streams and read-only RAM tests)."""
    if has_run_lock:
        raise RuntimeError(f"Active run.lock present in {source_label}; stage is still running or uncleaned")
    if has_paused:
        raise RuntimeError(f"PAUSED.json present in {source_label}; paused namespace rejected")

    if not isinstance(sessions, dict) or not sessions:
        raise ValueError(f"sessions.json in {source_label} is empty or invalid")
    open_sessions = [sid for sid, meta in sessions.items() if isinstance(meta, dict) and meta.get("state") == "open"]
    if open_sessions:
        raise RuntimeError(f"Unclosed open sessions in {source_label}: {open_sessions}")
    closed_sessions = [sid for sid, meta in sessions.items() if isinstance(meta, dict) and meta.get("state") == "closed"]
    if not closed_sessions:
        raise RuntimeError(f"No closed sessions found in {source_label}")

    if fingerprint_meta is None:
        raise FileNotFoundError(f"Required fingerprint.json missing in {source_label}")
    if not isinstance(fingerprint_meta, dict):
        raise ValueError(f"Invalid fingerprint.json payload in {source_label}")
    if expected_fp is not None and fingerprint_meta.get("fingerprint_id") != expected_fp:
        raise ValueError(
            f"Namespace fingerprint.json mismatch: {fingerprint_meta.get('fingerprint_id')} != {expected_fp}"
        )

    gate_filename = "statistics.json" if stage == "formal" else "gate.json"
    if saved_gate is None:
        raise FileNotFoundError(f"Required stage closeout file {gate_filename} missing in {source_label}")
    if not isinstance(saved_gate, dict):
        raise ValueError(f"Invalid {gate_filename} payload in {source_label}")

    planned_list = build_planned_units_from_split(split_data, stage)
    planned_by_key = {u["unit_key"]: u for u in planned_list}

    file_hasher = hashlib.sha256()
    slim_rows: List[dict] = []
    seen_keys = set()
    previous_seq = 0
    total_lines = 0
    skipped_invalid_session_lines = 0

    for line_idx, raw_line in enumerate(raw_lines, start=1):
        total_lines += 1
        file_hasher.update(raw_line)
        if not raw_line.endswith(b"\n"):
            raise ValueError(f"Incomplete unterminated line at {source_label}:{line_idx}")
        try:
            row = json.loads(raw_line.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise ValueError(f"Corrupt JSON ledger line at {source_label}:{line_idx}") from exc

        if not isinstance(row, dict):
            raise ValueError(f"Non-object ledger line at {line_idx}")
        seq = row.get("commit_seq")
        if type(seq) is not int or seq <= previous_seq:
            raise ValueError(f"Non-monotonic commit_seq at line {line_idx}: {seq} <= {previous_seq}")
        previous_seq = seq

        sid = row.get("session_id")
        session_meta = sessions.get(sid)
        if not isinstance(session_meta, dict):
            raise ValueError(f"Line {line_idx} references unknown session_id {sid!r}")
        if session_meta.get("state") == "invalid":
            skipped_invalid_session_lines += 1
            continue
        if session_meta.get("state") != "closed":
            raise ValueError(f"Unexpected session state {session_meta.get('state')!r} at line {line_idx}")

        if str(row.get("run_id", "")).startswith("E1-DRY-") or row.get("dry") is True:
            raise ValueError(f"Dry-run record forbidden in real analysis at line {line_idx}")

        ukey = row.get("unit_key")
        unit_plan = planned_by_key.get(ukey)
        if unit_plan is None:
            raise ValueError(f"Unexpected unit_key {ukey!r} at line {line_idx}")
        if ukey in seen_keys:
            raise ValueError(f"Duplicate terminal unit_key {ukey!r} across valid sessions")
        seen_keys.add(ukey)

        for k_plan, v_plan in unit_plan.items():
            if row.get(k_plan) != v_plan:
                raise ValueError(f"Unit plan field '{k_plan}' mismatch in {ukey}: {row.get(k_plan)} != {v_plan}")
        if row.get("stage") != stage or row.get("config") != cfg:
            raise ValueError(f"Stage/config mismatch in {ukey}: {row.get('stage')}/{row.get('config')}")
        if expected_fp is not None and row.get("fingerprint_id") != expected_fp:
            raise ValueError(f"Fingerprint mismatch in {ukey}: {row.get('fingerprint_id')} != {expected_fp}")

        iid = str(row["id"])
        grp, suffix = iid.split("_", 1)
        stratum = "telic" if grp in ("A", "C") else "atelic"

        raw_lbl = row.get("label") if row["task"] == "L" else None
        if raw_lbl is not None and (not isinstance(raw_lbl, str) or raw_lbl not in ALLOWED_LABEL_VALUES):
            raise ValueError(f"Invalid row['label'] in {ukey}: {raw_lbl!r}")
        raw_val = row.get("value") if row["task"] != "L" else None
        if raw_val is not None:
            if isinstance(raw_val, bool) or not isinstance(raw_val, (int, float)) or not math.isfinite(float(raw_val)):
                raise ValueError(f"Invalid row['value'] in {ukey}: {raw_val!r}")
            raw_val = float(raw_val)

        slim = {
            "unit_key": str(ukey),
            "id": iid,
            "group": grp,
            "cluster": f"{stratum}:{suffix}",
            "gold_label": str(row["gold_label"]),
            "task": str(row["task"]),
            "prompt": str(row["prompt"]),
            "status": str(row["status"]),
            "phases": _slim_phases_whitelist(row.get("phases")),
            "parsed": _slim_parsed_whitelist(row.get("parsed")),
            "protocol": _slim_protocol_whitelist(row.get("protocol")),
            "q": _slim_q_without_topn(row.get("q")),
            "label": raw_lbl,
            "value": raw_val,
            "n_out_tokens": int(row.get("n_out_tokens", 0)),
            "truncated": bool(row.get("truncated", False)),
            "seconds": float(row.get("seconds", 0.0)),
            "generation_seconds": (
                float(row["generation_seconds"])
                if row.get("generation_seconds") is not None
                else None
            ),
            "session_id": str(sid),
            "commit_seq": int(seq),
            "ledger_line": int(line_idx),
            "raw_tokens_sha256": canonical_digest(row.get("generated_ids_raw", [])),
            "prompt_ids_sha256": canonical_digest(row.get("prompt_ids", [])),
            "text_sha256": (
                hashlib.sha256(row["text"].encode("utf-8")).hexdigest()
                if isinstance(row.get("text"), str)
                else None
            ),
        }
        slim_rows.append(slim)

    if len(slim_rows) != len(planned_list) or seen_keys != set(planned_by_key.keys()):
        raise RuntimeError(
            f"Incomplete stage '{stage}' ledger: {len(slim_rows)} valid records vs {len(planned_list)} planned"
        )

    recomputed_gate = exp1_gates.compute(stage, planned_list, slim_rows)
    if not recomputed_gate["complete"] or recomputed_gate["pause"] is not None or recomputed_gate["status"] != "pass":
        raise RuntimeError(
            f"gates.compute('{stage}') failed completion/pause check: "
            f"status={recomputed_gate['status']}, complete={recomputed_gate['complete']}, pause={recomputed_gate['pause']}"
        )

    for k_chk in ("status", "complete", "pause", "pause_reasons", "executed", "planned", "missing", "cells"):
        if saved_gate.get(k_chk) != recomputed_gate[k_chk]:
            raise RuntimeError(f"Saved {gate_filename} field '{k_chk}' disagrees with recomputed gates.compute")
    if saved_gate.get("config") != cfg:
        raise RuntimeError(f"Saved {gate_filename} config {saved_gate.get('config')!r} != {cfg!r}")
    if expected_fp is not None and saved_gate.get("fingerprint_id") != expected_fp:
        raise RuntimeError(f"Saved {gate_filename} fingerprint_id disagrees with {expected_fp}")
    if stage == "formal" and saved_gate.get("stage") != "formal":
        raise RuntimeError(f"Saved statistics.json stage {saved_gate.get('stage')!r} != 'formal'")

    ledger_meta = {
        "input_mode": "results_jsonl_stream",
        "results_jsonl_path": source_label,
        "results_jsonl_sha256": file_hasher.hexdigest(),
        "sessions_json_sha256": sessions_sha256,
        "fingerprint_json_sha256": fingerprint_sha256,
        "total_jsonl_lines": total_lines,
        "valid_terminal_records": len(slim_rows),
        "skipped_invalid_session_lines": skipped_invalid_session_lines,
        "closed_session_count": len(closed_sessions),
        "gate_file_checked": gate_file_label or gate_filename,
        "gate_summary": {
            "status": recomputed_gate["status"],
            "complete": recomputed_gate["complete"],
            "pause": recomputed_gate["pause"],
            "executed": recomputed_gate["executed"],
            "planned": recomputed_gate["planned"],
            "missing": recomputed_gate["missing"],
        },
        "recomputed_gate_cells": recomputed_gate["cells"],
    }
    return slim_rows, ledger_meta


def stream_stage_ledger_to_slim_rows(
    results_jsonl_path: Path,
    split_data: dict,
    stage: str,
    cfg: str = DEFAULT_CONFIG,
    expected_fp: Optional[str] = EXPECTED_RUNNER_FP,
) -> Tuple[List[dict], Dict[str, Any]]:
    """Stream results.jsonl in binary mode (<100 MiB RSS), enforcing mandatory fingerprint.json & statistics.json/gate.json."""
    results_jsonl_path = Path(results_jsonl_path).resolve()
    ns_dir = results_jsonl_path.parent
    if not results_jsonl_path.is_file():
        raise FileNotFoundError(f"Stage ledger results.jsonl missing: {results_jsonl_path}")

    has_run_lock = (ns_dir / "run.lock").exists()
    has_paused = (ns_dir / "PAUSED.json").exists()
    if has_run_lock:
        raise RuntimeError(f"Active run.lock present in {ns_dir}; stage is still running or uncleaned")
    if has_paused:
        raise RuntimeError(f"PAUSED.json present in {ns_dir}; paused namespace rejected")

    sessions_path = ns_dir / "sessions.json"
    if not sessions_path.is_file():
        raise FileNotFoundError(f"sessions.json missing in {ns_dir}")
    sessions = json.loads(sessions_path.read_text(encoding="utf-8"))

    fp_meta_path = ns_dir / "fingerprint.json"
    if not fp_meta_path.is_file():
        raise FileNotFoundError(f"Required fingerprint.json missing in {ns_dir}")
    fp_meta = json.loads(fp_meta_path.read_text(encoding="utf-8"))

    gate_filename = "statistics.json" if stage == "formal" else "gate.json"
    saved_gate_path = ns_dir / gate_filename
    if not saved_gate_path.is_file():
        raise FileNotFoundError(f"Required stage closeout file {gate_filename} missing in {ns_dir}")
    saved_gate = json.loads(saved_gate_path.read_text(encoding="utf-8"))

    with results_jsonl_path.open("rb") as handle:
        return validate_and_slim_ledger_stream(
            handle,
            split_data=split_data,
            stage=stage,
            sessions=sessions,
            fingerprint_meta=fp_meta,
            saved_gate=saved_gate,
            cfg=cfg,
            expected_fp=expected_fp,
            has_run_lock=False,
            has_paused=False,
            source_label=str(results_jsonl_path),
            sessions_sha256=file_sha256(sessions_path),
            fingerprint_sha256=file_sha256(fp_meta_path),
            gate_file_label=str(saved_gate_path),
        )


def parse_and_validate_stage_units(
    source_rows: List[dict],
    all_ids: set,
    allow_non_ok: bool = True,
) -> Tuple[Dict[str, dict], Dict[str, Any]]:
    """Validate all planned units for dev or formal, disaggregating all 4 terminal statuses cleanly."""
    if not isinstance(source_rows, list):
        raise ValueError("source_rows must be a list of unit dicts")

    expected_unit_keys = {
        f"{iid}/{task}/{prompt}"
        for iid in all_ids
        for task, prompt in CONDITIONS_13
    }

    base_required = {"id", "task", "prompt", "unit_key", "status", "n_out_tokens", "seconds", "truncated"}
    unit_map: Dict[str, dict] = {}
    status_counts = {st: 0 for st in sorted(VALID_TERMINAL_STATUSES)}
    m_rows_checked = 0
    m_total_units = 0
    m_weight_known_in_count = 0
    m_weight_known_out_count = 0
    m_weight_unknown_count = 0
    protocol_reasons_count: Dict[str, int] = {}
    protocol_checked_ok_count = 0
    protocol_fail_count = 0
    protocol_unchecked_count = 0
    missing_score_with_valid_label_count = 0
    semantic_parse_truncated_count = 0
    semantic_parse_untruncated_none_count = 0

    for row in source_rows:
        if not isinstance(row, dict):
            raise ValueError("Unit row is not a dictionary")
        missing_keys = base_required - set(row.keys())
        if missing_keys:
            raise ValueError(f"Unit row missing required keys: {sorted(missing_keys)}")

        item_id = str(row["id"])
        grp = item_id.split("_", 1)[0]
        if "group" in row and row["group"] is not None and str(row["group"]) != grp:
            raise ValueError(f"Row group {row['group']!r} disagrees with item_id {item_id!r}")

        task = str(row["task"])
        prompt = str(row["prompt"])
        unit_key = str(row["unit_key"])
        if unit_key not in expected_unit_keys:
            raise ValueError(f"Unexpected unit_key '{unit_key}'")
        if unit_key in unit_map:
            raise ValueError(f"Duplicate unit_key '{unit_key}'")
        if unit_key != f"{item_id}/{task}/{prompt}":
            raise ValueError(f"Malformed unit_key '{unit_key}'")

        status = str(row["status"])
        if status not in VALID_TERMINAL_STATUSES:
            raise ValueError(f"Unknown terminal status '{status}' in '{unit_key}'")
        if status != "ok" and not allow_non_ok:
            raise ValueError(f"Non-ok status '{status}' in '{unit_key}' rejected when allow_non_ok=False")
        status_counts[status] += 1

        raw_proto = row.get("protocol")
        if raw_proto is None:
            if status != "missing_transport":
                raise ValueError(f"protocol=None is only valid on missing_transport, got status='{status}' in '{unit_key}'")
            protocol_checked = False
            proto_ok: Optional[bool] = None
            reasons: List[str] = []
            protocol_unchecked_count += 1
        else:
            if status == "missing_transport":
                raise ValueError(f"missing_transport must have protocol=None in '{unit_key}'")
            if not isinstance(raw_proto, dict) or not isinstance(raw_proto.get("protocol_ok"), bool):
                raise ValueError(f"protocol must be dict with bool protocol_ok in '{unit_key}'")
            protocol_checked = True
            proto_ok = raw_proto["protocol_ok"]
            reasons = [str(r) for r in raw_proto.get("reasons", [])]
            if not proto_ok and len(reasons) == 0:
                raise ValueError(f"protocol_ok is False with empty reasons in '{unit_key}'")
            if proto_ok and len(reasons) > 0:
                raise ValueError(f"protocol_ok is True with non-empty reasons in '{unit_key}'")
            for r in reasons:
                if r not in ALLOWED_PROTOCOL_REASONS:
                    raise ValueError(f"Non-whitelisted protocol reason {r!r} in '{unit_key}'")
            if proto_ok:
                protocol_checked_ok_count += 1
            else:
                protocol_fail_count += 1
                for r in reasons:
                    protocol_reasons_count[r] = protocol_reasons_count.get(r, 0) + 1

        raw_parsed = row.get("parsed")
        if raw_parsed is None:
            if status != "missing_transport":
                raise ValueError(f"parsed=None is only valid on missing_transport, got status='{status}' in '{unit_key}'")
            parsed: dict = {}
        else:
            if not isinstance(raw_parsed, dict):
                raise ValueError(f"parsed must be dict in '{unit_key}'")
            parsed = _slim_parsed_whitelist(raw_parsed) or {}

        u_seconds = float(row["seconds"])
        raw_g_sec = row.get("generation_seconds")
        if raw_g_sec is None:
            if status != "missing_transport":
                raise ValueError(f"generation_seconds missing on non-transport status '{status}' in '{unit_key}'")
            g_seconds = u_seconds
        else:
            g_seconds = float(raw_g_sec)

        if not (math.isfinite(u_seconds) and u_seconds >= 0.0 and math.isfinite(g_seconds) and g_seconds >= 0.0):
            raise ValueError(f"Invalid timing values in '{unit_key}'")

        is_trunc = bool(row["truncated"])
        if status == "missing_transport" and is_trunc:
            raise ValueError(f"missing_transport cannot have truncated=True in '{unit_key}'")

        unit_entry: Dict[str, Any] = {
            "id": item_id,
            "task": task,
            "prompt": prompt,
            "unit_key": unit_key,
            "group": grp,
            "status": status,
            "n_out_tokens": int(row["n_out_tokens"]),
            "generation_seconds": g_seconds,
            "seconds": u_seconds,
            "truncated": is_trunc,
            "protocol_checked": protocol_checked,
            "protocol_ok": proto_ok,
            "reasons": reasons,
            "q": _slim_q_without_topn(row.get("q")),
        }

        if task == "M":
            m_total_units += 1

        if status == "ok":
            if is_trunc:
                raise ValueError(f"truncated=True cannot have status='ok' in '{unit_key}'")
            if task == "L":
                lbl_row = row.get("label")
                lbl_parsed = parsed.get("label")
                if lbl_row not in ALLOWED_LABEL_VALUES or lbl_parsed not in ALLOWED_LABEL_VALUES or lbl_row != lbl_parsed:
                    raise ValueError(f"Task L invalid/mismatched label in '{unit_key}': {lbl_row!r} vs {lbl_parsed!r}")
                if "ok" in parsed:
                    raise ValueError(f"Task L parsed must not contain 'ok' key in '{unit_key}'")
                q_obj = unit_entry["q"] or {}
                if q_obj.get("q_status") not in ("full", "bounded"):
                    raise ValueError(f"Task L status='ok' requires full/bounded q_status in '{unit_key}'")
                q_l, q_u = float(q_obj["q_L"]), float(q_obj["q_U"])
                if not (math.isfinite(q_l) and math.isfinite(q_u) and 0.0 <= q_l <= q_u <= 1.0):
                    raise ValueError(f"Task L invalid [q_L, q_U] bounds in '{unit_key}': [{q_l}, {q_u}]")
                unit_entry["label"] = lbl_row

            elif task in {"P", "Ps"}:
                if parsed.get("ok") is not True:
                    raise ValueError(f"parsed.ok is not True in '{unit_key}'")
                val_row = row.get("value")
                val_parsed = parsed.get("value")
                if not isinstance(val_row, (int, float)) or not isinstance(val_parsed, (int, float)):
                    raise ValueError(f"Numeric P/Ps value missing in '{unit_key}'")
                v_f, vp_f = float(val_row), float(val_parsed)
                if not math.isfinite(v_f) or v_f < 0.0 or v_f > 100.0 or v_f != vp_f:
                    raise ValueError(f"Invalid P/Ps value in '{unit_key}': {v_f} vs {vp_f}")
                unit_entry["value"] = v_f

            elif task == "M":
                m_rows_checked += 1
                if parsed.get("ok") is not True:
                    raise ValueError(f"M parsed.ok is not True in '{unit_key}'")
                raw_est = parsed.get("estimates")
                raw_wt = parsed.get("weights")
                if not isinstance(raw_est, list) or len(raw_est) != 5:
                    raise ValueError(f"M estimates must be 5 items in '{unit_key}'")
                if not isinstance(raw_wt, list) or len(raw_wt) != 5:
                    raise ValueError(f"M weights must be 5 items in '{unit_key}'")

                estimates = [float(e) for e in raw_est]
                weights = [float(w) for w in raw_wt]
                if any((not math.isfinite(ef)) or ef < 0.0 or ef > 100.0 for ef in estimates):
                    raise ValueError(f"M estimate out of [0, 100] in '{unit_key}'")
                if any((not math.isfinite(wf)) or wf < 0.0 or wf > 1.0 for wf in weights):
                    raise ValueError(f"M weight out of [0, 1] in '{unit_key}'")
                w_sum = sum(weights)
                if w_sum <= 0.0:
                    raise ValueError(f"M weight sum <= 0 in '{unit_key}'")

                w_norm = [w / w_sum for w in weights]
                val_w = sum(w * e for w, e in zip(w_norm, estimates))
                val_u = sum(estimates) / 5.0
                val_u_frac = sum(Fraction(str(e)) for e in estimates) / 5

                val_row = float(row.get("value"))  # type: ignore[arg-type]
                val_parsed = float(parsed.get("value"))  # type: ignore[arg-type]
                if val_w != val_row or val_w != val_parsed:
                    raise ValueError(
                        f"M exact float equality failed in '{unit_key}': recomputed={val_w}, row={val_row}"
                    )
                if not isinstance(parsed.get("weight_sum_in_tolerance"), bool):
                    raise ValueError(f"M status='ok' requires bool weight_sum_in_tolerance in '{unit_key}'")
                w_in_tol = bool(parsed["weight_sum_in_tolerance"])
                unit_entry["value"] = val_row
                unit_entry["val_w"] = val_w
                unit_entry["val_u"] = val_u
                unit_entry["val_u_frac"] = val_u_frac
                unit_entry["estimates"] = estimates
                unit_entry["weights"] = weights
                unit_entry["w_norm"] = w_norm
                unit_entry["weight_sum_in_tolerance"] = w_in_tol
                unit_entry["m_weight_tol_state"] = "known_in" if w_in_tol else "known_out"
                if w_in_tol:
                    m_weight_known_in_count += 1
                else:
                    m_weight_known_out_count += 1
            else:
                raise ValueError(f"Unknown task '{task}'")
        else:
            if status == "missing_format":
                if is_trunc:
                    semantic_parse_truncated_count += 1
                else:
                    semantic_parse_untruncated_none_count += 1
            elif status == "missing_score":
                if task != "L":
                    raise ValueError(f"missing_score is only valid for Task L, got task='{task}' in '{unit_key}'")
                if is_trunc:
                    raise ValueError(f"missing_score cannot have truncated=True in '{unit_key}'")
                lbl_row = row.get("label")
                lbl_parsed = parsed.get("label")
                if lbl_row not in ALLOWED_LABEL_VALUES or lbl_row != lbl_parsed:
                    raise ValueError(f"missing_score requires valid parsed semantic label in '{unit_key}'")
                unit_entry["semantic_label_only"] = str(lbl_row)
                missing_score_with_valid_label_count += 1

            if task == "M":
                w_tol_raw = parsed.get("weight_sum_in_tolerance") if (status != "missing_transport" and not is_trunc) else None
                if isinstance(w_tol_raw, bool):
                    unit_entry["weight_sum_in_tolerance"] = w_tol_raw
                    unit_entry["m_weight_tol_state"] = "known_in" if w_tol_raw else "known_out"
                    if w_tol_raw:
                        m_weight_known_in_count += 1
                    else:
                        m_weight_known_out_count += 1
                else:
                    unit_entry["weight_sum_in_tolerance"] = None
                    unit_entry["m_weight_tol_state"] = "unknown"
                    m_weight_unknown_count += 1

        unit_map[unit_key] = unit_entry

    if set(unit_map.keys()) != expected_unit_keys:
        raise ValueError("Cartesian completeness failure: mismatch between expected and observed unit_keys")

    non_ok_count = len(expected_unit_keys) - status_counts["ok"]
    summary = {
        "total_units": len(expected_unit_keys),
        "status_ok_count": status_counts["ok"],
        "non_ok_count": non_ok_count,
        "status_counts": status_counts,
        "failure_partition": {
            "usable_ok_count": status_counts["ok"],
            "overall_unavailable_count": non_ok_count,
            "generation_fail_count": status_counts["missing_transport"],
            "semantic_parse_fail_count": status_counts["missing_format"],
            "semantic_parse_truncated_count": semantic_parse_truncated_count,
            "semantic_parse_untruncated_none_count": semantic_parse_untruncated_none_count,
            "scoring_fail_count": status_counts["missing_score"],
        },
        "strict_protocol_partition": {
            "checked_ok_count": protocol_checked_ok_count,
            "checked_fail_count": protocol_fail_count,
            "unchecked_count": protocol_unchecked_count,
        },
        "m_weight_sum_tolerance_partition": {
            "total_m_units": m_total_units,
            "known_in_tolerance_count": m_weight_known_in_count,
            "known_out_of_tolerance_count": m_weight_known_out_count,
            "unknown_count": m_weight_unknown_count,
        },
        "m_rows_checked": m_rows_checked,
        "protocol_fail_count": protocol_fail_count,
        "protocol_unchecked_count": protocol_unchecked_count,
        "protocol_reasons_count": protocol_reasons_count,
        "missing_score_with_valid_label_count": missing_score_with_valid_label_count,
    }
    return unit_map, summary


def build_unit_map_for_sealed_profile_engine(unit_map: Dict[str, dict]) -> Dict[str, dict]:
    """Create shallow adapter view for sealed formal_engine so missing_transport (protocol_ok=None) is not bool-negated."""
    adapted: Dict[str, dict] = {}
    for ukey, row in unit_map.items():
        if row.get("protocol_checked") is False:
            adapted[ukey] = {**row, "protocol_ok": True, "reasons": []}
        else:
            adapted[ukey] = row
    return adapted


def compute_four_status_compliance_profile(
    unit_map: Dict[str, dict],
    telic_clusters: List[str],
    atelic_clusters: List[str],
    *,
    b_reps: int,
    seed: int,
    tango_by_n: Dict[int, Dict[str, Any]],
) -> Dict[str, Any]:
    """Disaggregate all 4 terminal statuses, strict_protocol (ok/fail/unchecked), and M weight-sum (in/out/unknown)."""
    n_ac = len(telic_clusters)
    n_bd = len(atelic_clusters)
    rng = np.random.default_rng(np.random.SeedSequence([seed, 0]))
    wt_all = np.empty((b_reps, n_ac), dtype=np.float64)
    wa_all = np.empty((b_reps, n_bd), dtype=np.float64)
    for start, wt, wa in weight_batches(rng, n_ac, n_bd, b=b_reps, batch=256):
        sz = len(wt)
        wt_all[start:start + sz] = wt
        wa_all[start:start + sz] = wa
    wt_norm = wt_all / float(n_ac)
    wa_norm = wa_all / float(n_bd)
    wt_obs = np.full((1, n_ac), 1.0 / n_ac, dtype=np.float64)
    wa_obs = np.full((1, n_bd), 1.0 / n_bd, dtype=np.float64)

    group_clusters = {
        "A": (telic_clusters, wt_obs, wt_norm),
        "C": (telic_clusters, wt_obs, wt_norm),
        "B": (atelic_clusters, wa_obs, wa_norm),
        "D": (atelic_clusters, wa_obs, wa_norm),
    }

    by_condition: Dict[str, Any] = {}
    raw_store: Dict[str, Dict[str, Dict[str, Any]]] = {}

    def _rate_block(vec: np.ndarray, w_o: np.ndarray, w_b: np.ndarray) -> Tuple[dict, float, np.ndarray]:
        pt = float((w_o @ vec)[0])
        bt = w_b @ vec
        return {
            "count": int(np.sum(vec)),
            "n": int(len(vec)),
            "rate": _summarize_boot_interval(pt, pt, bt, bt, (0.0, 1.0)),
        }, pt, bt

    for task, prompt in CONDITIONS_13:
        cond = f"{task}/{prompt}"
        cond_out: Dict[str, Any] = {}
        cond_raw: Dict[str, Dict[str, Any]] = {}

        for grp in ("A", "B", "C", "D"):
            clusters, w_o, w_b = group_clusters[grp]
            rows = [unit_map[f"{grp}_{cid}/{task}/{prompt}"] for cid in clusters]

            v_unavail = np.array([1.0 if r["status"] != "ok" else 0.0 for r in rows], dtype=np.float64)
            v_gen = np.array([1.0 if r["status"] == "missing_transport" else 0.0 for r in rows], dtype=np.float64)
            v_sem = np.array([1.0 if r["status"] == "missing_format" else 0.0 for r in rows], dtype=np.float64)
            v_scr = np.array([1.0 if r["status"] == "missing_score" else 0.0 for r in rows], dtype=np.float64)
            v_trunc = np.array([1.0 if r["truncated"] else 0.0 for r in rows], dtype=np.float64)
            v_p_fail = np.array(
                [1.0 if (r["protocol_checked"] and r["protocol_ok"] is False) else 0.0 for r in rows],
                dtype=np.float64,
            )
            v_p_unchk = np.array([1.0 if not r["protocol_checked"] else 0.0 for r in rows], dtype=np.float64)

            b_unavail, pt_unavail, bt_unavail = _rate_block(v_unavail, w_o, w_b)
            b_gen, pt_gen, bt_gen = _rate_block(v_gen, w_o, w_b)
            b_sem, pt_sem, bt_sem = _rate_block(v_sem, w_o, w_b)
            b_scr, pt_scr, bt_scr = _rate_block(v_scr, w_o, w_b)
            b_trunc, pt_trunc, bt_trunc = _rate_block(v_trunc, w_o, w_b)
            b_p_fail, pt_p_fail, bt_p_fail = _rate_block(v_p_fail, w_o, w_b)
            b_p_unchk, pt_p_unchk, bt_p_unchk = _rate_block(v_p_unchk, w_o, w_b)

            reasons_dict: Dict[str, int] = {"last_line": 0, "estimate_lines": 0, "weight_sum": 0}
            for r in rows:
                if r["protocol_checked"] and r["protocol_ok"] is False:
                    for rsn in r["reasons"]:
                        reasons_dict[rsn] = reasons_dict.get(rsn, 0) + 1

            p_ok_cnt = sum(1 for r in rows if r["protocol_checked"] and r["protocol_ok"] is True)
            p_checked_cnt = p_ok_cnt + b_p_fail["count"]
            b_p_fail["checked_denominator"] = p_checked_cnt
            b_p_fail["checked_ok_count"] = p_ok_cnt
            b_p_fail["unchecked_count"] = b_p_unchk["count"]
            b_p_fail["reason_counts"] = reasons_dict

            grp_entry: Dict[str, Any] = {
                "n": len(rows),
                "usable_ok_count": len(rows) - b_unavail["count"],
                "overall_unavailable": b_unavail,
                "generation_fail": b_gen,
                "semantic_parse_fail": b_sem,
                "scoring_fail": b_scr if task == "L" else {**b_scr, "applicable": False},
                "truncation": b_trunc,
                "strict_protocol_fail": b_p_fail,
                "strict_protocol_unchecked": b_p_unchk,
            }

            raw_rec: Dict[str, Any] = {
                "rows": rows,
                "unavail_vec": v_unavail, "unavail_pt": pt_unavail, "unavail_bt": bt_unavail,
                "gen_vec": v_gen, "gen_pt": pt_gen, "gen_bt": bt_gen,
                "sem_vec": v_sem, "sem_pt": pt_sem, "sem_bt": bt_sem,
                "scr_vec": v_scr, "scr_pt": pt_scr, "scr_bt": bt_scr,
                "trunc_vec": v_trunc, "trunc_pt": pt_trunc, "trunc_bt": bt_trunc,
                "p_fail_vec": v_p_fail, "p_fail_pt": pt_p_fail, "p_fail_bt": bt_p_fail,
                "p_unchk_vec": v_p_unchk, "p_unchk_pt": pt_p_unchk, "p_unchk_bt": bt_p_unchk,
            }

            if task == "M":
                known_in = sum(1 for r in rows if r.get("m_weight_tol_state") == "known_in")
                known_out = sum(1 for r in rows if r.get("m_weight_tol_state") == "known_out")
                unk = sum(1 for r in rows if r.get("m_weight_tol_state") == "unknown")
                in_lo = np.array([1.0 if r.get("m_weight_tol_state") == "known_in" else 0.0 for r in rows], dtype=np.float64)
                in_hi = np.array(
                    [1.0 if r.get("m_weight_tol_state") in ("known_in", "unknown") else 0.0 for r in rows],
                    dtype=np.float64,
                )
                in_pt_lo = float((w_o @ in_lo)[0])
                in_pt_hi = float((w_o @ in_hi)[0])
                in_bt_lo = w_b @ in_lo
                in_bt_hi = w_b @ in_hi
                raw_rec.update(
                    in_pt_lo=in_pt_lo, in_pt_hi=in_pt_hi, in_bt_lo=in_bt_lo, in_bt_hi=in_bt_hi,
                    known_in=known_in, known_out=known_out, unk=unk,
                )
                grp_entry["m_weight_sum_tolerance"] = {
                    "known_in_tolerance_count": known_in,
                    "known_out_of_tolerance_count": known_out,
                    "unknown_count": unk,
                    "in_tolerance_rate": _summarize_boot_interval(in_pt_lo, in_pt_hi, in_bt_lo, in_bt_hi, (0.0, 1.0)),
                    "out_of_tolerance_rate": _summarize_boot_interval(
                        1.0 - in_pt_hi, 1.0 - in_pt_lo, 1.0 - in_bt_hi, 1.0 - in_bt_lo, (0.0, 1.0)
                    ),
                }

            cond_out[grp] = grp_entry
            cond_raw[grp] = raw_rec

        all_rows = cond_raw["A"]["rows"] + cond_raw["B"]["rows"] + cond_raw["C"]["rows"] + cond_raw["D"]["rows"]
        n_all = len(all_rows)
        cond_raw["all"] = {}
        for pfx in ("unavail", "gen", "sem", "scr", "trunc", "p_fail", "p_unchk"):
            cond_raw["all"][f"{pfx}_pt"] = 0.25 * sum(cond_raw[g][f"{pfx}_pt"] for g in ("A", "B", "C", "D"))
            cond_raw["all"][f"{pfx}_bt"] = 0.25 * sum(cond_raw[g][f"{pfx}_bt"] for g in ("A", "B", "C", "D"))

        def _all_block(pfx: str, cnt: int) -> dict:
            pt = cond_raw["all"][f"{pfx}_pt"]
            bt = cond_raw["all"][f"{pfx}_bt"]
            return {
                "count": cnt,
                "n": n_all,
                "rate": _summarize_boot_interval(pt, pt, bt, bt, (0.0, 1.0)),
            }

        all_reasons: Dict[str, int] = {"last_line": 0, "estimate_lines": 0, "weight_sum": 0}
        for r in all_rows:
            if r["protocol_checked"] and r["protocol_ok"] is False:
                for rsn in r["reasons"]:
                    all_reasons[rsn] = all_reasons.get(rsn, 0) + 1

        cnt_unavail = sum(cond_out[g]["overall_unavailable"]["count"] for g in ("A", "B", "C", "D"))
        cnt_gen = sum(cond_out[g]["generation_fail"]["count"] for g in ("A", "B", "C", "D"))
        cnt_sem = sum(cond_out[g]["semantic_parse_fail"]["count"] for g in ("A", "B", "C", "D"))
        cnt_scr = sum(cond_out[g]["scoring_fail"]["count"] for g in ("A", "B", "C", "D"))
        cnt_trunc = sum(cond_out[g]["truncation"]["count"] for g in ("A", "B", "C", "D"))
        cnt_p_fail = sum(cond_out[g]["strict_protocol_fail"]["count"] for g in ("A", "B", "C", "D"))
        cnt_p_unchk = sum(cond_out[g]["strict_protocol_unchecked"]["count"] for g in ("A", "B", "C", "D"))
        cnt_p_ok = n_all - cnt_p_fail - cnt_p_unchk

        all_p_fail_blk = _all_block("p_fail", cnt_p_fail)
        all_p_fail_blk["checked_denominator"] = cnt_p_ok + cnt_p_fail
        all_p_fail_blk["checked_ok_count"] = cnt_p_ok
        all_p_fail_blk["unchecked_count"] = cnt_p_unchk
        all_p_fail_blk["reason_counts"] = all_reasons

        all_scr_blk = _all_block("scr", cnt_scr)
        if task != "L":
            all_scr_blk["applicable"] = False

        all_entry: Dict[str, Any] = {
            "n": n_all,
            "usable_ok_count": n_all - cnt_unavail,
            "overall_unavailable": _all_block("unavail", cnt_unavail),
            "generation_fail": _all_block("gen", cnt_gen),
            "semantic_parse_fail": _all_block("sem", cnt_sem),
            "scoring_fail": all_scr_blk,
            "truncation": _all_block("trunc", cnt_trunc),
            "strict_protocol_fail": all_p_fail_blk,
            "strict_protocol_unchecked": _all_block("p_unchk", cnt_p_unchk),
        }

        if task == "M":
            kin_all = sum(cond_raw[g]["known_in"] for g in ("A", "B", "C", "D"))
            kout_all = sum(cond_raw[g]["known_out"] for g in ("A", "B", "C", "D"))
            unk_all = sum(cond_raw[g]["unk"] for g in ("A", "B", "C", "D"))
            in_pt_lo_all = 0.25 * sum(cond_raw[g]["in_pt_lo"] for g in ("A", "B", "C", "D"))
            in_pt_hi_all = 0.25 * sum(cond_raw[g]["in_pt_hi"] for g in ("A", "B", "C", "D"))
            in_bt_lo_all = 0.25 * sum(cond_raw[g]["in_bt_lo"] for g in ("A", "B", "C", "D"))
            in_bt_hi_all = 0.25 * sum(cond_raw[g]["in_bt_hi"] for g in ("A", "B", "C", "D"))
            all_entry["m_weight_sum_tolerance"] = {
                "known_in_tolerance_count": kin_all,
                "known_out_of_tolerance_count": kout_all,
                "unknown_count": unk_all,
                "in_tolerance_rate": _summarize_boot_interval(
                    in_pt_lo_all, in_pt_hi_all, in_bt_lo_all, in_bt_hi_all, (0.0, 1.0)
                ),
                "out_of_tolerance_rate": _summarize_boot_interval(
                    1.0 - in_pt_hi_all, 1.0 - in_pt_lo_all, 1.0 - in_bt_hi_all, 1.0 - in_bt_lo_all, (0.0, 1.0)
                ),
            }

        cond_out["all"] = all_entry
        by_condition[cond] = cond_out
        raw_store[cond] = cond_raw

    contrasts_out: Dict[str, Any] = {}
    for cname, c1, c2 in COST_CONTRASTS_SPEC:
        c_grp: Dict[str, Any] = {}
        for target in ("all", "A", "B", "C", "D"):
            r1 = raw_store[c1][target]
            r2 = raw_store[c2][target]
            item_out: Dict[str, Any] = {}
            for key_name, pfx in (
                ("overall_unavailable_rate", "unavail"),
                ("generation_fail_rate", "gen"),
                ("semantic_parse_fail_rate", "sem"),
                ("scoring_fail_rate", "scr"),
                ("truncation_rate", "trunc"),
                ("strict_protocol_fail_rate", "p_fail"),
                ("strict_protocol_unchecked_rate", "p_unchk"),
            ):
                d_pt = r1[f"{pfx}_pt"] - r2[f"{pfx}_pt"]
                d_bt = r1[f"{pfx}_bt"] - r2[f"{pfx}_bt"]
                ex = None
                if target in ("A", "B", "C", "D"):
                    d_vec = r1[f"{pfx}_vec"] - r2[f"{pfx}_vec"]
                    ex = _summarize_exact_tango_trinary(d_vec, d_vec, tango_by_n)
                item_out[key_name] = _summarize_boot_interval(d_pt, d_pt, d_bt, d_bt, (-1.0, 1.0), exact_tango=ex)
            c_grp[target] = item_out
        contrasts_out[cname] = c_grp

    return {
        "by_condition": by_condition,
        "contrasts": contrasts_out,
    }


def reconcile_obs_profile_cost_and_format_four_statuses(
    obs_profile: Dict[str, Any],
    four_status_compliance: Dict[str, Any],
) -> None:
    """When non_ok_count > 0, reconcile obs_profile['cost_and_format'] in place so no failure metric is conflated."""
    cf = obs_profile.get("cost_and_format")
    if not isinstance(cf, dict):
        return
    f_by_cond = four_status_compliance["by_condition"]
    for cond, cond_dict in cf.get("by_condition", {}).items():
        src_cond = f_by_cond[cond]
        task = cond.split("/", 1)[0]
        for target in ("A", "B", "C", "D", "all"):
            dst = cond_dict[target]
            src = src_cond[target]
            dst["overall_unavailable"] = src["overall_unavailable"]
            dst["generation_fail"] = src["generation_fail"]
            dst["semantic_parse_fail"] = src["semantic_parse_fail"]
            dst["scoring_fail"] = src["scoring_fail"]
            dst["strict_protocol_unchecked"] = src["strict_protocol_unchecked"]

            # Preserve M weight tolerance keys while fixing out_of_tolerance_count to known_out (not n - known_in)
            sp_dst = dst["strict_protocol_fail"]
            sp_src = src["strict_protocol_fail"]
            sp_dst["count"] = sp_src["count"]
            sp_dst["n"] = sp_src["n"]
            sp_dst["checked_denominator"] = sp_src["checked_denominator"]
            sp_dst["checked_ok_count"] = sp_src["checked_ok_count"]
            sp_dst["unchecked_count"] = sp_src["unchecked_count"]
            sp_dst["rate"] = sp_src["rate"]
            sp_dst["reason_counts"] = sp_src["reason_counts"]
            if task == "M":
                mtol = src["m_weight_sum_tolerance"]
                sp_dst["weight_sum_in_tolerance_count"] = mtol["known_in_tolerance_count"]
                sp_dst["weight_sum_out_of_tolerance_count"] = mtol["known_out_of_tolerance_count"]
                sp_dst["weight_sum_unknown_count"] = mtol["unknown_count"]
                sp_dst["weight_sum_in_tolerance_rate"] = mtol["in_tolerance_rate"]
                sp_dst["weight_sum_out_of_tolerance_rate"] = mtol["out_of_tolerance_rate"]

    f_contrasts = four_status_compliance["contrasts"]
    for cname, c_dict in cf.get("contrasts", {}).items():
        src_c = f_contrasts[cname]
        for target in ("all", "A", "B", "C", "D"):
            dst_t = c_dict[target]
            src_t = src_c[target]
            dst_t["overall_unavailable_rate"] = src_t["overall_unavailable_rate"]
            dst_t["generation_fail_rate"] = src_t["generation_fail_rate"]
            dst_t["semantic_parse_fail_rate"] = src_t["semantic_parse_fail_rate"]
            dst_t["scoring_fail_rate"] = src_t["scoring_fail_rate"]
            dst_t["strict_protocol_fail_rate"] = src_t["strict_protocol_fail_rate"]
            dst_t["strict_protocol_unchecked_rate"] = src_t["strict_protocol_unchecked_rate"]


def build_stage_cluster_arrays(
    unit_map: Dict[str, dict],
    telic_clusters: List[str],
    atelic_clusters: List[str],
) -> Tuple[ClusterSampleA, Optional[np.ndarray], Optional[np.ndarray]]:
    """Build ClusterSampleA (for arbitrary n_ac, n_bd) and legacy V4 [2, n, 2, 13] arrays (when n_ac == n_bd)."""
    n_ac = len(telic_clusters)
    n_bd = len(atelic_clusters)

    ac_cont_lower = np.empty((n_ac, 2, 2), dtype=np.float64)
    ac_cont_upper = np.empty((n_ac, 2, 2), dtype=np.float64)
    bd_cont_lower = np.empty((n_bd, 2, 2), dtype=np.float64)
    bd_cont_upper = np.empty((n_bd, 2, 2), dtype=np.float64)
    bd_l_acc_lower = np.empty((n_bd, 2), dtype=np.float64)
    bd_l_acc_upper = np.empty((n_bd, 2), dtype=np.float64)

    build_v4 = n_ac == n_bd
    v4_lower = np.empty((2, n_ac, 2, 13), dtype=np.float64) if build_v4 else None
    v4_upper = np.empty((2, n_ac, 2, 13), dtype=np.float64) if build_v4 else None

    for i, suffix in enumerate(telic_clusters):
        for role, grp in enumerate(("A", "C")):
            item_id = f"{grp}_{suffix}"
            if build_v4:
                for j, (task, prompt) in enumerate(CONDITIONS_13):
                    row = unit_map[f"{item_id}/{task}/{prompt}"]
                    q = row.get("q") or {}
                    if row["status"] == "ok":
                        if task == "L" and q.get("q_status") in ("full", "bounded"):
                            lo, hi = 100.0 * float(q["q_L"]), 100.0 * float(q["q_U"])
                        elif task in ("P", "Ps", "M"):
                            lo = hi = float(row["value"])
                        else:
                            lo, hi = 0.0, 100.0
                    else:
                        lo, hi = 0.0, 100.0
                    v4_lower[0, i, role, j] = lo  # type: ignore[index]
                    v4_upper[0, i, role, j] = hi  # type: ignore[index]

            r_pcot = unit_map[f"{item_id}/P/CoT"]
            if r_pcot["status"] == "ok":
                ac_cont_lower[i, role, 0] = ac_cont_upper[i, role, 0] = float(r_pcot["value"])
            else:
                ac_cont_lower[i, role, 0], ac_cont_upper[i, role, 0] = 0.0, 100.0

            r_muz = unit_map[f"{item_id}/M/Z"]
            if r_muz["status"] == "ok":
                ac_cont_lower[i, role, 1] = ac_cont_upper[i, role, 1] = float(r_muz["val_u"])
            else:
                ac_cont_lower[i, role, 1], ac_cont_upper[i, role, 1] = 0.0, 100.0

    for i, suffix in enumerate(atelic_clusters):
        for role, grp in enumerate(("B", "D")):
            item_id = f"{grp}_{suffix}"
            if build_v4:
                for j, (task, prompt) in enumerate(CONDITIONS_13):
                    row = unit_map[f"{item_id}/{task}/{prompt}"]
                    q = row.get("q") or {}
                    if row["status"] == "ok":
                        if task == "L" and q.get("q_status") in ("full", "bounded"):
                            lo, hi = 100.0 * float(q["q_L"]), 100.0 * float(q["q_U"])
                        elif task in ("P", "Ps", "M"):
                            lo = hi = float(row["value"])
                        else:
                            lo, hi = 0.0, 100.0
                    else:
                        lo, hi = 0.0, 100.0
                    v4_lower[1, i, role, j] = lo  # type: ignore[index]
                    v4_upper[1, i, role, j] = hi  # type: ignore[index]

            r_mucot = unit_map[f"{item_id}/M/CoT"]
            if r_mucot["status"] == "ok":
                bd_cont_lower[i, role, 0] = bd_cont_upper[i, role, 0] = float(r_mucot["val_u"])
            else:
                bd_cont_lower[i, role, 0], bd_cont_upper[i, role, 0] = 0.0, 100.0

            r_pcot = unit_map[f"{item_id}/P/CoT"]
            if r_pcot["status"] == "ok":
                bd_cont_lower[i, role, 1] = bd_cont_upper[i, role, 1] = float(r_pcot["value"])
            else:
                bd_cont_lower[i, role, 1], bd_cont_upper[i, role, 1] = 0.0, 100.0

        item_d = f"D_{suffix}"
        gold_d = L_GOLD_STANDARDS["D"]
        for ch_idx, p_name in enumerate(("CoT", "Z")):
            r_l = unit_map[f"{item_d}/L/{p_name}"]
            if r_l["status"] == "ok":
                acc_val = 1.0 if r_l["label"] == gold_d else 0.0
                bd_l_acc_lower[i, ch_idx] = bd_l_acc_upper[i, ch_idx] = acc_val
            else:
                bd_l_acc_lower[i, ch_idx], bd_l_acc_upper[i, ch_idx] = 0.0, 1.0

    sample_a = ClusterSampleA(
        ac_cont_lower=ac_cont_lower,
        ac_cont_upper=ac_cont_upper,
        bd_cont_lower=bd_cont_lower,
        bd_cont_upper=bd_cont_upper,
        bd_l_acc_lower=bd_l_acc_lower,
        bd_l_acc_upper=bd_l_acc_upper,
    )
    return sample_a, v4_lower, v4_upper


def _serialize_inf(inf: dict) -> dict:
    out = {}
    for k, v in inf.items():
        out[k] = v.tolist() if isinstance(v, np.ndarray) else v
    return out


def _holm_adjusted_pvalues(p_values: List[float]) -> List[float]:
    """Compute monotone step-down Holm adjusted p-values with stable index tie-breaking."""
    m = len(p_values)
    p_arr = np.asarray(p_values, dtype=np.float64)
    order = np.argsort(p_arr, kind="stable")
    adj_sorted = np.empty(m, dtype=np.float64)
    running_max = 0.0
    for j, idx in enumerate(order):
        val = min(1.0, float((m - j) * p_arr[idx]))
        if val > running_max:
            running_max = val
        adj_sorted[j] = running_max
    out = np.empty(m, dtype=np.float64)
    for j, idx in enumerate(order):
        out[idx] = adj_sorted[j]
    return [float(x) for x in out]


def resolve_plan_e1_slot_claims(
    inf_serialized: dict,
    obs_lo: List[float],
    obs_hi: List[float],
) -> List[Dict[str, Any]]:
    """Apply PLAN-E1.md §4.2 deterministic claim wording to m=4 Scheme A outputs."""
    claims = []
    p_holm_vec = _holm_adjusted_pvalues(list(inf_serialized["p"]))
    ci_source = inf_serialized["ci"] if "ci" in inf_serialized else inf_serialized["ci_9875"]
    for k, slot_name in enumerate(NAMES_A):
        deg = bool(inf_serialized["degenerate"][k])
        rej = bool(inf_serialized["reject"][k])
        dir_code = int(inf_serialized["direction"][k])
        lo_pt = float(obs_lo[k])
        hi_pt = float(obs_hi[k])
        p_raw = float(inf_serialized["p"][k])
        p_holm = float(p_holm_vec[k])
        ci_9875 = list(ci_source[k])

        if deg:
            verdict = "证据不足（重抽分布退化）"
            confirmed_sign = 0
        elif not rej:
            verdict = "未拒绝原假设（证据不足）"
            confirmed_sign = 0
        else:
            if k == 0:
                # SA1 one-sided composite null theta_1 <= 0 vs theta_1 > 0
                if dir_code == 1 and lo_pt >= -TOL_DUST:
                    verdict = "方向确认（θ_1 > 0）"
                    confirmed_sign = 1
                else:
                    verdict = "证据不足（缺失跨零）"
                    confirmed_sign = 0
            else:
                if dir_code == 1 and lo_pt >= -TOL_DUST:
                    verdict = f"方向确认（θ_{k + 1} > 0）"
                    confirmed_sign = 1
                elif dir_code == -1 and hi_pt <= TOL_DUST:
                    verdict = f"方向确认（θ_{k + 1} < 0）"
                    confirmed_sign = -1
                else:
                    verdict = "证据不足（缺失跨零）"
                    confirmed_sign = 0

        claims.append(
            {
                "slot": slot_name,
                "point_lower": lo_pt,
                "point_upper": hi_pt,
                "p_raw": p_raw,
                "p_holm": p_holm,
                "holm_rejected": rej,
                "degenerate": deg,
                "raw_direction_code": dir_code,
                "confirmed_sign": confirmed_sign,
                "ci_9875": ci_9875,
                "verdict_zh": verdict,
            }
        )
    return claims


def _ensure_tango_table_for_n(
    tango_by_n: Dict[int, Dict[str, Any]],
    n: int,
    *,
    workers: int = 4,
    _test_grid_override: Optional[Tuple[int, int]] = None,
    build_events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[int, Dict[str, Any]]:
    """Return tango_by_n guaranteed to contain stratum size n (recording separate build timing if n not in {20, 80})."""
    if n in tango_by_n:
        return tango_by_n
    expanded = dict(tango_by_n)
    if _test_grid_override is not None:
        g_nodes, m_seg = int(_test_grid_override[0]), int(_test_grid_override[1])
    else:
        g_nodes = 2000 if n > 20 else 1200
        m_seg = 2048 if n > 20 else 1024
    t_b0 = time.perf_counter()
    built = build_certified_tables_for_n(n, g_nodes=g_nodes, m_seg=m_seg, workers=workers)
    elapsed = time.perf_counter() - t_b0
    if build_events is not None:
        build_events.append({
            "n": int(n),
            "g_nodes": int(g_nodes),
            "m_seg": int(m_seg),
            "seconds": round(float(elapsed), 6),
        })
    expanded[n] = {
        "n": n,
        "f_plus_zero": built["f_plus_zero"],
        "theta_L": built["theta_L"],
    }
    return expanded


def _run_scheme_a_m4_block(
    sample_a: ClusterSampleA,
    b_reps: int,
    seed: int,
    tango_by_n: Dict[int, Dict[str, Any]],
    *,
    tango_workers: int = 4,
    _test_grid_override: Optional[Tuple[int, int]] = None,
    build_events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Run all 4 m=4 procedures in shared stream SeedSequence([seed, 0])."""
    contrasts = extract_slot_contrasts(sample_a)
    n_ac = len(contrasts["d1_lower"])
    n_bd = len(contrasts["d4_lower"])
    tango_ready = _ensure_tango_table_for_n(
        _ensure_tango_table_for_n(
            tango_by_n,
            n_ac,
            workers=tango_workers,
            _test_grid_override=_test_grid_override,
            build_events=build_events,
        ),
        n_bd,
        workers=tango_workers,
        _test_grid_override=_test_grid_override,
        build_events=build_events,
    )

    rng_boot = np.random.default_rng(np.random.SeedSequence([seed, 0]))
    (obs_lo, obs_hi), (obs_se_lo, obs_se_hi) = compute_observed_a(contrasts)
    (boot_lo, boot_hi), (boot_se_lo, boot_se_hi) = bootstrap_a(contrasts, rng_boot, b=b_reps)
    pre_boot = prepare_sorted_boot_stats(boot_lo, boot_hi, tol=TOL_DUST)

    m4_hybrid_pct = _serialize_inf(
        infer_hybrid_pct_tango_a(
            contrasts, boot_lo, boot_hi, obs_lo, obs_hi, tango_tables=tango_ready, precomputed_boot=pre_boot
        )
    )
    m4_hybrid_bessel = _serialize_inf(
        infer_hybrid_bessel_t_tango_a(
            contrasts, boot_lo, boot_hi, obs_lo, obs_hi, tango_tables=tango_ready, precomputed_boot=pre_boot
        )
    )
    m4_pct = _serialize_inf(infer_percentile_a(boot_lo, boot_hi, obs_lo, obs_hi, precomputed_boot=pre_boot))
    m4_stud = _serialize_inf(
        infer_studentized_a(
            boot_lo, boot_hi, boot_se_lo, boot_se_hi, obs_lo, obs_hi, obs_se_lo, obs_se_hi, precomputed_boot=pre_boot
        )
    )

    ex_sa1 = infer_exact_tango_slot(
        contrasts["d1_lower"], contrasts["d1_upper"], one_sided=True, tables_for_n=tango_ready[n_ac]
    )
    ex_sa4 = infer_exact_tango_slot(
        contrasts["d4_lower"], contrasts["d4_upper"], one_sided=False, tables_for_n=tango_ready[n_bd]
    )

    return {
        "names": list(NAMES_A),
        "n_ac": n_ac,
        "n_bd": n_bd,
        "hybrid_pct_tango": m4_hybrid_pct,
        "hybrid_bessel_t_tango": m4_hybrid_bessel,
        "percentile": m4_pct,
        "studentized": m4_stud,
        "bessel_t_expansion_constants": {
            "active_ac": compute_bessel_t_constants_decimal(n_ac),
            "active_bd": compute_bessel_t_constants_decimal(n_bd),
            "formal_n80_reference": compute_bessel_t_constants_decimal(80),
        },
        "exact_tango_discrete_slots": {
            "SA1": ex_sa1,
            "SA4": ex_sa4,
        },
        "observed_point_lower": obs_lo.tolist(),
        "observed_point_upper": obs_hi.tolist(),
        "observed_se_lower": obs_se_lo.tolist(),
        "observed_se_upper": obs_se_hi.tolist(),
    }


def compute_missingness_companions(
    unit_map: Dict[str, dict],
    telic_clusters: List[str],
    atelic_clusters: List[str],
    val_summary: Dict[str, Any],
    b_reps: int,
    seed: int,
    tango_by_n: Dict[int, Dict[str, Any]],
    *,
    tango_workers: int = 4,
    _test_grid_override: Optional[Tuple[int, int]] = None,
    build_events: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Compute pre-specified PLAN-E1.md §4.2 complete-case and Task-L semantic-label diagnostics when non_ok > 0."""
    if val_summary["non_ok_count"] == 0:
        return {
            "status": "not_triggered_zero_missing",
            "non_ok_count": 0,
            "complete_case_clusters": None,
            "task_l_semantic_label_sa4": None,
        }

    ac_cc = [
        cid
        for cid in telic_clusters
        if all(
            unit_map[f"{grp}_{cid}/{cond}"]["status"] == "ok"
            for grp in ("A", "C")
            for cond in ("P/CoT", "M/Z")
        )
    ]
    bd_cc = [
        cid
        for cid in atelic_clusters
        if all(
            unit_map[f"{grp}_{cid}/{cond}"]["status"] == "ok"
            for grp in ("B", "D")
            for cond in ("M/CoT", "P/CoT")
        )
        and all(unit_map[f"D_{cid}/L/{p}"]["status"] == "ok" for p in ("CoT", "Z"))
    ]

    cc_result: Optional[Dict[str, Any]] = None
    if len(ac_cc) >= 2 and len(bd_cc) >= 2:
        sample_cc, _, _ = build_stage_cluster_arrays(unit_map, ac_cc, bd_cc)
        m4_cc = _run_scheme_a_m4_block(
            sample_cc,
            b_reps=b_reps,
            seed=seed,
            tango_by_n=tango_by_n,
            tango_workers=tango_workers,
            _test_grid_override=_test_grid_override,
            build_events=build_events,
        )
        cc_result = {
            "n_ac_complete": len(ac_cc),
            "n_bd_complete": len(bd_cc),
            "dropped_telic_clusters": [c for c in telic_clusters if c not in set(ac_cc)],
            "dropped_atelic_clusters": [c for c in atelic_clusters if c not in set(bd_cc)],
            "hybrid_pct_tango": m4_cc["hybrid_pct_tango"],
            "hybrid_bessel_t_tango": m4_cc["hybrid_bessel_t_tango"],
            "observed_point_lower": m4_cc["observed_point_lower"],
            "observed_point_upper": m4_cc["observed_point_upper"],
            "primary_claims": resolve_plan_e1_slot_claims(
                m4_cc["hybrid_pct_tango"], m4_cc["observed_point_lower"], m4_cc["observed_point_upper"]
            ),
        }

    # Task L semantic-label-only SA4 companion (triggered if any D_*/L/{CoT,Z} has missing_score with valid label)
    d_missing_score_recovered = 0
    gold_d = L_GOLD_STANDARDS["D"]
    d4_lo = np.empty(len(atelic_clusters), dtype=np.float64)
    d4_hi = np.empty(len(atelic_clusters), dtype=np.float64)
    for idx, cid in enumerate(atelic_clusters):
        bounds_pair = []
        for p_name in ("CoT", "Z"):
            r_l = unit_map[f"D_{cid}/L/{p_name}"]
            if r_l["status"] == "ok":
                v = 1.0 if r_l["label"] == gold_d else 0.0
                bounds_pair.append((v, v))
            elif "semantic_label_only" in r_l:
                d_missing_score_recovered += 1
                v = 1.0 if r_l["semantic_label_only"] == gold_d else 0.0
                bounds_pair.append((v, v))
            else:
                bounds_pair.append((0.0, 1.0))
        d4_lo[idx] = bounds_pair[0][0] - bounds_pair[1][1]
        d4_hi[idx] = bounds_pair[0][1] - bounds_pair[1][0]

    l_sem_diag = None
    if d_missing_score_recovered > 0:
        tango_ready = _ensure_tango_table_for_n(
            tango_by_n,
            len(atelic_clusters),
            workers=tango_workers,
            _test_grid_override=_test_grid_override,
            build_events=build_events,
        )
        l_sem_diag = {
            "recovered_d_units": d_missing_score_recovered,
            "sa4_exact_tango": infer_exact_tango_slot(
                d4_lo, d4_hi, one_sided=False, tables_for_n=tango_ready[len(atelic_clusters)]
            ),
        }

    return {
        "status": "evaluated",
        "non_ok_count": val_summary["non_ok_count"],
        "complete_case_clusters": cc_result,
        "task_l_semantic_label_sa4": l_sem_diag,
    }


def compute_telic_verb_subclass_profile(
    unit_map: Dict[str, dict],
    telic_clusters: List[str],
    items_json_path: Path,
) -> Dict[str, Any]:
    """Compute zero-text descriptive means across the 4 telic verb subclasses when data/imperfectiveNLI.json exists."""
    if not items_json_path.is_file():
        return {"status": "item_metadata_unavailable"}

    raw_items = json.loads(items_json_path.read_text(encoding="utf-8"))
    vclass_by_suffix: Dict[str, str] = {}
    for it in raw_items:
        iid = str(it.get("id", ""))
        if iid.startswith("C_"):
            vclass_by_suffix[iid.split("_", 1)[1]] = str(it.get("verb_class", ""))

    subclasses = ("Change_of_State", "Creation", "Consumption", "Motion_to_Goal")
    out: Dict[str, Any] = {"status": "available", "by_subclass": {}}
    for sc in subclasses:
        cids = [c for c in telic_clusters if vclass_by_suffix.get(c) == sc]
        if not cids:
            continue

        def _bounds_mean(grp: str, task: str, prompt: str, mode: str = "value") -> List[float]:
            los, his = [], []
            for c in cids:
                r = unit_map[f"{grp}_{c}/{task}/{prompt}"]
                if r["status"] == "ok":
                    if mode == "l_true":
                        v = 1.0 if r["label"] == "True" else 0.0
                    elif mode == "l_acc":
                        v = 1.0 if r["label"] == L_GOLD_STANDARDS[grp] else 0.0
                    elif mode == "val_u":
                        v = float(r["val_u"])
                    else:
                        v = float(r["value"])
                    los.append(v)
                    his.append(v)
                else:
                    los.append(0.0)
                    his.append(1.0 if mode.startswith("l_") else 100.0)
            return [float(np.mean(los)), float(np.mean(his))]

        out["by_subclass"][sc] = {
            "n_clusters": len(cids),
            "L_Z_TBR_C": _bounds_mean("C", "L", "Z", "l_true"),
            "L_CoT_TBR_C": _bounds_mean("C", "L", "CoT", "l_true"),
            "L_Z_ACC_A": _bounds_mean("A", "L", "Z", "l_acc"),
            "P_Z_mean_C": _bounds_mean("C", "P", "Z", "value"),
            "P_CoT_mean_C": _bounds_mean("C", "P", "CoT", "value"),
            "M_U_Z_mean_C": _bounds_mean("C", "M", "Z", "val_u"),
            "M_U_CoT_mean_C": _bounds_mean("C", "M", "CoT", "val_u"),
            "P_CoT_C_minus_A": [
                _bounds_mean("C", "P", "CoT", "value")[0] - _bounds_mean("A", "P", "CoT", "value")[1],
                _bounds_mean("C", "P", "CoT", "value")[1] - _bounds_mean("A", "P", "CoT", "value")[0],
            ],
            "M_U_Z_C_minus_A": [
                _bounds_mean("C", "M", "Z", "val_u")[0] - _bounds_mean("A", "M", "Z", "val_u")[1],
                _bounds_mean("C", "M", "Z", "val_u")[1] - _bounds_mean("A", "M", "Z", "val_u")[0],
            ],
        }
    return out


def _fmt_pt(lo: float, hi: float, digits: int = 4) -> str:
    if abs(hi - lo) <= TOL_DUST:
        return f"`{lo:.{digits}f}`"
    return f"`[{lo:.{digits}f}, {hi:.{digits}f}]`"


def _fmt_ci(ci: Optional[List[float]], digits: int = 4) -> str:
    if ci is None:
        return "`None`"
    return f"`[{ci[0]:.{digits}f}, {ci[1]:.{digits}f}]`"


def _fmt_obs_metric(entry: dict, digits: int = 4, use_9875: bool = False) -> str:
    pt = _fmt_pt(float(entry["point_lower"]), float(entry["point_upper"]), digits=digits)
    ci_key = "ci_9875" if use_9875 else "ci_95"
    ci = _fmt_ci(entry.get(ci_key), digits=digits)
    return f"{pt} ({ci})"


def render_s7_markdown_report(res: Dict[str, Any]) -> str:
    """Render 100% JSON-bound Chinese S7 formal (or dev dry-run / isolated diagnostic) report."""
    stage = res["split_name"]
    is_formal = stage == "formal"
    confirmatory_valid = bool(res.get("confirmatory_valid", False))
    if is_formal and confirmatory_valid:
        title_stage = "正式集（`formal`，160 簇 / 4,160 单元）"
    elif is_formal:
        title_stage = "正式集非确认性离线诊断（`formal-diagnostic`，不作确认结论）"
    else:
        title_stage = "开发集干跑（`dev`，40 簇 / 1,040 单元）"

    m4 = res["scheme_a_m4"]
    val_sum = res["validation_summary"]
    sealed = res["sealed_integrity_gates"]
    freeze_info = res["s5_freeze_gate"]
    claims_holder = (
        res["confirmatory_claims_option_iii"]
        if res.get("confirmatory_claims_option_iii") is not None
        else res["non_confirmatory_slot_evaluations"]
    )
    primary_claims = claims_holder["primary_hybrid_pct_tango"]
    sens_claims = claims_holder["sensitivity_hybrid_bessel_t_tango"]
    c_n_ac = m4["bessel_t_expansion_constants"]["active_ac"]["c_n_float"]
    obs = res["observation_profile"]
    fsc = res["four_status_compliance"]
    fpart = val_sum["failure_partition"]
    ppart = val_sum["strict_protocol_partition"]
    mpart = val_sum["m_weight_sum_tolerance_partition"]
    telem = res.get("runtime_telemetry", {})

    lines: List[str] = []
    lines.append(f"# 实验 1（英文 ImperfectiveNLI）S7 {title_stage}统计分析报告")
    lines.append("")
    if not confirmatory_valid:
        lines.append(
            f"> **[非确认性运行边界]**：当前 `analysis_mode = {res.get('analysis_mode')}`，`confirmatory_valid = False`。"
            "本输出仅供管线对账或离线诊断，不构成确认性科学声称。"
        )
        lines.append("")
    lines.append("## 0. 治理身份、S5 冻结核验与选项 III 三层统计声称边界")
    lines.append("")
    lines.append(f"- **受测配置与运行指纹**：`{res['config']}`；运行器完整指纹 `{res['expected_runner_fingerprint']}`。")
    lines.append(
        f"- **数据阶段与四状态完备拆解**：阶段 `{stage}`（终结簇 `n_ac = {m4['n_ac']}`，非终结簇 `n_bd = {m4['n_bd']}`，"
        f"总单元 `{val_sum['total_units']}`）：可用 `ok = {fpart['usable_ok_count']}`，"
        f"总体不可用 `non_ok = {fpart['overall_unavailable_count']}`"
        f"（其中生成失败 `missing_transport = {fpart['generation_fail_count']}`、"
        f"语义解析失败 `missing_format = {fpart['semantic_parse_fail_count']}`"
        f"〔截断 `{fpart['semantic_parse_truncated_count']}` + 未截断无语义值 `{fpart['semantic_parse_untruncated_none_count']}`〕、"
        f"计分失败 `missing_score = {fpart['scoring_fail_count']}`）；"
        f"严格协议检查：合规 `{ppart['checked_ok_count']}`、不合规 `{ppart['checked_fail_count']}`、"
        f"未生成未检查 `{ppart['unchecked_count']}`；"
        f"`M` 任务权重和容差 `[0.95, 1.05]`：已知容差内 `{mpart['known_in_tolerance_count']}`、"
        f"已知超容差 `{mpart['known_out_of_tolerance_count']}`、缺失未知 `{mpart['unknown_count']}`。"
    )
    lines.append(
        f"- **封存统计核心实时核验**：8 模块组合 `code_sha256 = {sealed['code_sha256']}`；"
        f"认证精确 Tango 查表 `exact_tango_tables_sha256 = {sealed['exact_tango_tables_sha256']}`"
        f"（载荷 `{sealed['exact_tango_tables_payload_sha256']}`）；`split.json` `{sealed['split_sha256']}`；"
        f"重抽次数 `B = {res['bootstrap_replicates']}`，预注册随机种子 `seed = {res['seed']}`。"
    )
    if is_formal and freeze_info is not None:
        lines.append(
            f"- **S5 冻结与执行清单绑定核验（通过）**：`freeze.json` SHA256 `{freeze_info['freeze_json_sha256']}`；"
            f"`PLAN-E1.frozen.md` SHA256 `{freeze_info['frozen_plan_sha256']}`；"
            f"`s6-s7-execution-manifest.json` SHA256 `{freeze_info.get('execution_manifest_sha256')}`；"
            f"`c_blockers = {freeze_info['c_blockers']}`；用户确认时间 `{freeze_info['confirmed_at']}`。"
        )
    else:
        lines.append("- **开发集干跑边界**：本次运行在 `dev` 分割上执行，仅作管线逐位复现核验，不构成确认性证据。")

    if telem:
        built_n_list = [b["n"] for b in telem.get("on_demand_tango_table_builds", [])]
        rss_str = f"{telem['peak_rss_mib']:.2f} MiB" if telem.get("peak_rss_mib") is not None else "unavailable"
        lines.append(
            f"- **运行环境、峰值内存与分路径耗时遥测**：Python `{telem.get('python_version')}`，"
            f"NumPy `{telem.get('numpy_version')}`，平台 `{telem.get('platform')}`；"
            f"进程峰值内存 `{rss_str}`；零动态建表主路径（门禁＋流式核账＋`m=4`＋`V4`＋观察剖面）耗时 "
            f"`{telem.get('zero_missing_core_and_profile_seconds', 0.0):.3f} s`，"
            f"缺失触发动态构建 Tango 查表耗时 `{telem.get('on_demand_tango_table_build_seconds', 0.0):.3f} s`"
            f"（动态建表分层样本量 `{built_n_list}`，总耗时 `{telem.get('total_wall_seconds', 0.0):.3f} s`）。"
        )

    lines.append(
        "- **用户特批选项 III 冻结前例外与三层统计声称边界（按 `PLAN-E1.md` §0.3 如实披露）**："
        "主确认程序锁定封存 `hybrid_pct_tango`，预注册敏感度伴随程序锁定封存 `hybrid_bessel_t_tango` "
        f"（当前样本量有限自由度外扩系数 `c_n = {c_n_ac:.12f}`）。在 Step 5b（`P16.4.6`）双银行校准中，"
        "两项混合程序均通过贴边非退化门禁 `D_j = 5 / 5`、双银行功效门禁 `P_j = 17 / 17` 以及 `validation` 全部 `88 / 88` 格"
        "（含 `14 / 14` 个 `2%` 与 `4%` 缺失压力格）的 "
        "`FWER <= 0.05 + 2*MCSE`（最大 `0.0570`）、`FamDirErr <= 0.05 + 2*MCSE`（最大 `0.0570`）、`IndCov9875 >= 0.975`（最小 `0.9785`）、"
        "`SimultCov9875 >= 0.95 - 2*MCSE`（主程序最小 `0.9440`，敏感度伴随最小 `0.9465`）与 `screen05 <= 0.075`（最大 `0.0645`），"
        "但在固定无缓冲单槽原假设尾部筛查 `screen0125 <= 0.01875` 上为 `C_j = 82 / 88`（最大实测 `0.0215`，落入预注册 `branch_id = 4`）。"
        "因此：（1）离散配对三值槽 `SA1, SA4` 享有连续单纯形向外区间算术证明的有限样本认证无条件精确保证；"
        "（2）连续配对均值差槽 `SA2, SA3` 及四槽联合家族仅声称上述 `88 + 56` 格有限模拟实测达到的非参数重抽频率性质，"
        "不声称任意连续总体非渐近精确覆盖；（3）第 2–5 节观察剖面与历史归档指标一律作描述性报告。"
    )
    lines.append("")

    lines.append("## 1. 方案 A（`m = 4`，基于 `M_U`）主确认检验与敏感度伴随结果")
    lines.append("")
    lines.append("| 槽位与对比定义 | 点估计 / 缺失界 | 主程序 `hybrid_pct_tango` 原始 `p` | 主程序 Holm 校正 `p` | 主程序 `98.75%` 区间 | 主程序结论 | 敏感度 `hybrid_bessel_t_tango` Holm `p` | 敏感度 `98.75%` 区间 | 敏感度结论 |")
    lines.append("|---|---:|---:|---:|---|---|---:|---|---|")

    slot_labels = {
        "SA1": "`SA1`：C 组高置信端点率差 `Pr(P/CoT>=95) - Pr(M_U/Z>=95)`（单侧 `H0: θ_1 <= 0`）",
        "SA2": "`SA2`：终结中断敏感度双重差分 `(C-A)_{P/CoT} - (C-A)_{M_U/Z}`（双侧 `H0: θ_2 = 0`）",
        "SA3": "`SA3`：`CoT` 下非终结活动中断双重差分 `(D-B)_{M_U/CoT} - (D-B)_{P/CoT}`（双侧 `H0: θ_3 = 0`）",
        "SA4": "`SA4`：离散 `L` 任务 D 组准确率差 `ACC_D(L/CoT) - ACC_D(L/Z)`（双侧 `H0: θ_4 = 0`）",
    }
    for pc, sc in zip(primary_claims, sens_claims):
        sname = pc["slot"]
        lines.append(
            f"| {slot_labels[sname]} | {_fmt_pt(pc['point_lower'], pc['point_upper'])} | "
            f"`{pc['p_raw']:.6g}` | `{pc['p_holm']:.6g}` | {_fmt_ci(pc['ci_9875'])} | **{pc['verdict_zh']}** | "
            f"`{sc['p_holm']:.6g}` | {_fmt_ci(sc['ci_9875'])} | {sc['verdict_zh']} |"
        )
    lines.append("")

    ex1 = m4["exact_tango_discrete_slots"]["SA1"]
    ex4 = m4["exact_tango_discrete_slots"]["SA4"]
    lines.append(
        f"- **离散精确槽配对三项计数 `(n_+, n_0, n_-)`**："
        f"`SA1` 下界计数 `({ex1['counts_lower']['n_plus']}, {ex1['counts_lower']['n_zero']}, {ex1['counts_lower']['n_minus']})` / "
        f"上界计数 `({ex1['counts_upper']['n_plus']}, {ex1['counts_upper']['n_zero']}, {ex1['counts_upper']['n_minus']})`；"
        f"`SA4` 下界计数 `({ex4['counts_lower']['n_plus']}, {ex4['counts_lower']['n_zero']}, {ex4['counts_lower']['n_minus']})` / "
        f"上界计数 `({ex4['counts_upper']['n_plus']}, {ex4['counts_upper']['n_zero']}, {ex4['counts_upper']['n_minus']})`。"
    )

    miss_comp = res["missingness_companions"]
    if miss_comp["status"] == "not_triggered_zero_missing":
        lines.append("- **缺失伴随诊断**：全阶段 `non_ok_count = 0`，完整簇子集与 `L` 纯语义标签诊断均与上表主结果逐位恒等。")
    else:
        cc = miss_comp.get("complete_case_clusters")
        if cc is not None:
            cc_verdicts = "；".join(f"`{c['slot']}` {c['verdict_zh']} ({_fmt_ci(c['ci_9875'])})" for c in cc["primary_claims"])
            lines.append(
                f"- **完整簇子集伴随诊断（`n_ac = {cc['n_ac_complete']}, n_bd = {cc['n_bd_complete']}`）**：{cc_verdicts}。"
            )
        l_sem = miss_comp.get("task_l_semantic_label_sa4")
        if l_sem is not None:
            ex_l = l_sem["sa4_exact_tango"]
            lines.append(
                f"- **`L` 纯语义标签恢复诊断（恢复 `{l_sem['recovered_d_units']}` 个 `missing_score` 单元）**："
                f"`SA4` 点估计 {_fmt_pt(ex_l['point_lower'], ex_l['point_upper'])}，"
                f"双侧精确 `p = {ex_l['p']:.6g}`，`98.75%` 区间 {_fmt_ci(ex_l['ci_9875'])}。"
            )
    lines.append("")

    lines.append("## 2. 预指定描述性观察剖面：13 个连续表示条件、`M_W - M_U` 与离散 `L` 任务")
    lines.append("")
    lines.append("### 2.1 连续表示条件（`Ps, P, M_U, M_W`）组均值、中断差、分离度与 C 组高端点率（括号内为共享流 `95%` 区间）")
    lines.append("")
    lines.append("| 条件 | `mean_A` | `mean_B` | `mean_C` | `mean_D` | `C - A` | `D - B` | `AUC(D > C)` | `ep_high_C (>=95%)` |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    cond_order = (
        "Ps_Z",
        "P_Z", "P_DAP", "P_CoT", "P_CF",
        "M_U_Z", "M_U_DAP", "M_U_CoT", "M_U_CF",
        "M_W_Z", "M_W_DAP", "M_W_CoT", "M_W_CF",
    )
    for ck in cond_order:
        cd = obs["conditions"][ck]
        lines.append(
            f"| `{ck}` | {_fmt_obs_metric(cd['mean_A'], 2)} | {_fmt_obs_metric(cd['mean_B'], 2)} | "
            f"{_fmt_obs_metric(cd['mean_C'], 2)} | {_fmt_obs_metric(cd['mean_D'], 2)} | "
            f"{_fmt_obs_metric(cd['c_minus_a'], 2)} | {_fmt_obs_metric(cd['d_minus_b'], 2)} | "
            f"{_fmt_obs_metric(cd['auc'], 4)} | {_fmt_obs_metric(cd['ep_high_C'], 4)} |"
        )
    lines.append("")

    lines.append("### 2.2 候选池展开 vs 自报权重配对差（`M_W - M_U`，括号内为共享流 `95%` 区间）")
    lines.append("")
    lines.append("| 提示 | `mean_C (M_W - M_U)` | `C - A (M_W - M_U)` | `AUC (M_W - M_U)` | `ep_high_C (M_W - M_U)` | `ep_high_C` 精确 Tango `95%` 区间 |")
    lines.append("|---|---|---|---|---|---|")
    for p_name in ("Z", "DAP", "CoT", "CF"):
        md = obs["mw_minus_mu_paired_diff"][p_name]
        ex_ep = md["ep_high_C"]["exact_tango"]["ci_95"]
        lines.append(
            f"| `{p_name}` | {_fmt_obs_metric(md['mean_C'], 3)} | {_fmt_obs_metric(md['c_minus_a'], 3)} | "
            f"{_fmt_obs_metric(md['auc'], 4)} | {_fmt_obs_metric(md['ep_high_C'], 4)} | {_fmt_ci(ex_ep, 4)} |"
        )
    lines.append("")

    lines.append("### 2.3 离散标签 `L` 任务四提示准确率、目的论偏见率 `TBR_C` 与 `Δ_AA = ACC_D - TBR_C`")
    lines.append("")
    lines.append("| 提示 | `ACC_A` (False) | `ACC_B` (True) | `ACC_C` (Unknown) | `ACC_D` (True) | `ACC_overall` | `TBR_C` (C 答 True) | `TBR_A` (A 答 True) | `Δ_AA` |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for p_name in ("Z", "DAP", "CoT", "CF"):
        tl = obs["task_l"][p_name]
        ac = tl["accuracies"]
        lines.append(
            f"| `L/{p_name}` | {_fmt_obs_metric(ac['ACC_A'], 4)} | {_fmt_obs_metric(ac['ACC_B'], 4)} | "
            f"{_fmt_obs_metric(ac['ACC_C'], 4)} | {_fmt_obs_metric(ac['ACC_D'], 4)} | "
            f"{_fmt_obs_metric(ac['ACC_overall'], 4)} | {_fmt_obs_metric(tl['tbr_c'], 4)} | "
            f"{_fmt_obs_metric(tl['tbr_a'], 4)} | {_fmt_obs_metric(tl['delta_aa'], 4)} |"
        )
    lines.append("")

    lines.append("## 3. 成本、耗时、截断与四状态严格协议／权重容差拆解剖面（全四组 `all` 汇总）")
    lines.append("")
    lines.append("| 原始条件 | 单元数 | 平均输出 token (`95%` CI) | 最大 token (`/1024`) | 平均秒数 | 截断数 | 总体不可用 | 生成失败 | 语义解析失败 | 计分失败 | 严格协议 (`失败 / 未检查`) | `M` 权重容差 (`内/外/未知`) | 协议原因计数 |")
    lines.append("|---|---:|---|---:|---:|---:|---:|---:|---:|---:|---|---|---|")
    cf_by_cond = obs["cost_and_format"]["by_condition"]
    fsc_by_cond = fsc["by_condition"]
    for task, prompt in CONDITIONS_13:
        cond_str = f"{task}/{prompt}"
        ca = cf_by_cond[cond_str]["all"]
        fa = fsc_by_cond[cond_str]["all"]
        nz_reasons = {k: v for k, v in fa["strict_protocol_fail"]["reason_counts"].items() if v > 0}
        scr_str = f"`{fa['scoring_fail']['count']}`" if task == "L" else "`N/A`"
        if task == "M":
            mt = fa["m_weight_sum_tolerance"]
            mt_str = f"`{mt['known_in_tolerance_count']}/{mt['known_out_of_tolerance_count']}/{mt['unknown_count']}`"
        else:
            mt_str = "`N/A`"
        lines.append(
            f"| `{cond_str}` | `{ca['n']}` | {_fmt_obs_metric(ca['n_out_tokens']['mean'], 1)} | "
            f"`{ca['n_out_tokens']['max']}` (`{ca['n_out_tokens']['max_ratio_to_1024']:.3f}`) | "
            f"`{ca['unit_seconds']['mean']['point_lower']:.2f}` | `{fa['truncation']['count']}` | "
            f"`{fa['overall_unavailable']['count']}` | `{fa['generation_fail']['count']}` | "
            f"`{fa['semantic_parse_fail']['count']}` | {scr_str} | "
            f"`{fa['strict_protocol_fail']['count']} / {fa['strict_protocol_unchecked']['count']}` | "
            f"{mt_str} | `{json.dumps(nz_reasons, ensure_ascii=False)}` |"
        )
    lines.append("")

    vsub = res.get("telic_verb_subclass_profile", {})
    if vsub.get("status") == "available":
        lines.append("## 4. 终结动词四子类描述性分解（无题目原文聚合）")
        lines.append("")
        lines.append("| 动词子类 | 簇数 | `L/Z TBR_C` | `L/CoT TBR_C` | `P/Z mean_C` | `P/CoT mean_C` | `M_U/Z mean_C` | `P/CoT (C-A)` | `M_U/Z (C-A)` |")
        lines.append("|---|---:|---|---|---|---|---|---|---|")
        for sc_name, sc_d in vsub["by_subclass"].items():
            lines.append(
                f"| `{sc_name}` | `{sc_d['n_clusters']}` | {_fmt_pt(*sc_d['L_Z_TBR_C'], 4)} | "
                f"{_fmt_pt(*sc_d['L_CoT_TBR_C'], 4)} | {_fmt_pt(*sc_d['P_Z_mean_C'], 2)} | "
                f"{_fmt_pt(*sc_d['P_CoT_mean_C'], 2)} | {_fmt_pt(*sc_d['M_U_Z_mean_C'], 2)} | "
                f"{_fmt_pt(*sc_d['P_CoT_C_minus_A'], 2)} | {_fmt_pt(*sc_d['M_U_Z_C_minus_A'], 2)} |"
            )
        lines.append("")

    lines.append("## 5. 历史方法与旧版 V4 `m = 10` 描述性归档（仅供透明对账，不作确认性声明）")
    lines.append("")
    pct_m4 = m4["percentile"]
    stud_m4 = m4["studentized"]
    pct_m4_holm = _holm_adjusted_pvalues(list(pct_m4["p"]))
    stud_m4_holm = _holm_adjusted_pvalues(list(stud_m4["p"]))
    lines.append(
        "- **`Scheme A (m = 4)` 历史纯重抽参考**："
        f"`percentile` Holm `p = {[round(float(x), 6) for x in pct_m4_holm]}`，退化标记 `{pct_m4['degenerate']}`；"
        f"`studentized` Holm `p = {[round(float(x), 6) for x in stud_m4_holm]}`，退化标记 `{stud_m4['degenerate']}`。"
    )
    v4 = res["legacy_v4_m10"]
    if v4 is not None:
        v4_pct_holm = _holm_adjusted_pvalues(list(v4["percentile"]["p"]))
        v4_stud_holm = _holm_adjusted_pvalues(list(v4["studentized"]["p"]))
        lines.append("- **旧版 `PLAN.md` §4.1 V4 `m = 10`（已在冻结前因校准与 `ΔAUC` 功效不足降为描述性归档）**：")
        lines.append("")
        lines.append("| 旧假设编号 | 点估计 / 缺失界 | V4 `percentile` Holm `p` | V4 `percentile` `99.5%` 区间 | V4 `studentized` Holm `p` | V4 `studentized` `99.5%` 区间 |")
        lines.append("|---|---:|---:|---|---:|---|")
        for idx_h, hname in enumerate(v4["names"]):
            lines.append(
                f"| `{hname}` | {_fmt_pt(v4['observed_point_lower'][idx_h], v4['observed_point_upper'][idx_h], 4)} | "
                f"`{v4_pct_holm[idx_h]:.6g}` | {_fmt_ci(v4['percentile']['ci'][idx_h], 4)} | "
                f"`{v4_stud_holm[idx_h]:.6g}` | {_fmt_ci(v4['studentized']['ci'][idx_h], 4)} |"
            )
    lines.append("")
    return "\n".join(lines) + "\n"


def run_s7_pipeline(
    *,
    stage: str = "formal",
    cfg: str = DEFAULT_CONFIG,
    expected_fp: Optional[str] = EXPECTED_RUNNER_FP,
    exp1_root: Path = DEFAULT_EXP1_ROOT,
    step5b_root: Path = DEFAULT_STEP5B_ROOT,
    split_path: Optional[Path] = None,
    results_jsonl_path: Optional[Path] = None,
    unit_index_json_path: Optional[Path] = None,
    write_unit_index_path: Optional[Path] = None,
    b_reps: int = FORMAL_BOOTSTRAP_B,
    seed: Optional[int] = None,
    allow_non_ok: Optional[bool] = None,
    tango_workers: int = 4,
    diagnostic_non_confirmatory: bool = False,
    out_json_path: Optional[Path] = None,
    out_report_path: Optional[Path] = None,
    manifest_path: Path = EXECUTION_MANIFEST_PATH,
    _test_on_demand_tango_grid: Optional[Tuple[int, int]] = None,
) -> Dict[str, Any]:
    """Execute complete Stage S7 analysis (or dev dry-run parity / isolated diagnostic run)."""
    t_total_start = time.perf_counter()
    tango_build_events: List[Dict[str, Any]] = []

    exp1_root = Path(exp1_root).resolve()
    step5b_root = Path(step5b_root).resolve()
    resolved_split_path = Path(split_path or (exp1_root / "split.json")).resolve()

    if stage not in ("dev", "formal"):
        raise ValueError(f"stage must be 'dev' or 'formal', got {stage!r}")
    if results_jsonl_path is not None and unit_index_json_path is not None:
        raise ValueError("Provide either results_jsonl_path or unit_index_json_path, not both")

    # 0. Enforce production confirmatory lock on 'formal' before running anything
    enforce_confirmatory_formal_lock(
        stage=stage,
        cfg=cfg,
        expected_fp=expected_fp,
        b_reps=b_reps,
        seed=seed,
        allow_non_ok=allow_non_ok,
        unit_index_json_path=unit_index_json_path,
        test_on_demand_tango_grid=_test_on_demand_tango_grid,
        diagnostic_non_confirmatory=diagnostic_non_confirmatory,
        out_json_path=out_json_path,
        out_report_path=out_report_path,
        write_unit_index_path=write_unit_index_path,
        results_jsonl_path=results_jsonl_path,
        split_path=split_path,
        manifest_path=manifest_path,
    )

    # 1. Verify Step 5b sealed 8 modules, exact Tango tables, 6 left cuts, and split.json
    sealed_gates = verify_step5b_sealed_engine(step5b_root=step5b_root, split_path=resolved_split_path)
    split_data = json.loads(resolved_split_path.read_text(encoding="utf-8"))

    # 2. Enforce cryptographic S5 freeze gate + execution manifest binding BEFORE touching any formal data
    if stage != "dev":
        s5_freeze_gate = verify_s5_freeze_gate(
            exp1_root=exp1_root,
            split_data=split_data,
            cfg=cfg,
            expected_fp=expected_fp,
            manifest_path=manifest_path,
        )
    else:
        s5_freeze_gate = None

    # 3. Validate split structure and load/stream stage units
    telic_clusters, atelic_clusters, group_items, all_ids = validate_stage_split(split_data, stage)

    if unit_index_json_path is not None:
        u_path = Path(unit_index_json_path).resolve()
        if not u_path.is_file():
            raise FileNotFoundError(f"unit_index_json_path not found: {u_path}")
        source_rows = json.loads(u_path.read_text(encoding="utf-8"))
        source_provenance = {
            "input_mode": "unit_index_json",
            "source_path": str(u_path),
            "source_sha256": file_sha256(u_path),
            "split_path": str(resolved_split_path),
            "split_sha256": sealed_gates["split_sha256"],
        }
    else:
        fp8 = expected_fp[:8] if expected_fp else s5_freeze_gate["fingerprint_id"][:8]  # type: ignore[index]
        r_path = (
            Path(results_jsonl_path).resolve()
            if results_jsonl_path is not None
            else (exp1_root / "raw" / stage / cfg / fp8 / "results.jsonl").resolve()
        )
        source_rows, ledger_meta = stream_stage_ledger_to_slim_rows(
            results_jsonl_path=r_path,
            split_data=split_data,
            stage=stage,
            cfg=cfg,
            expected_fp=expected_fp,
        )
        if write_unit_index_path is not None:
            atomic_write_json_lf(Path(write_unit_index_path), source_rows)
        source_provenance = {
            **ledger_meta,
            "split_path": str(resolved_split_path),
            "split_sha256": sealed_gates["split_sha256"],
            "exported_unit_index_path": str(write_unit_index_path) if write_unit_index_path else None,
        }

    effective_allow_non_ok = (stage == "formal") if allow_non_ok is None else bool(allow_non_ok)
    unit_map, val_summary = parse_and_validate_stage_units(
        source_rows, all_ids, allow_non_ok=effective_allow_non_ok
    )
    sample_a, v4_lo, v4_hi = build_stage_cluster_arrays(unit_map, telic_clusters, atelic_clusters)

    active_seed = (FORMAL_ANALYSIS_SEED if stage == "formal" else DEFAULT_DRY_RUN_SEED) if seed is None else int(seed)
    tango_npz_path = step5b_root / "manifests" / "exact-tango-tables.npz"
    tango_by_n = load_certified_tango_tables(
        npz_path=tango_npz_path,
        expected_file_sha256=EXPECTED_TANGO_TABLES_SHA256,
        expected_payload_sha256=EXPECTED_TANGO_PAYLOAD_SHA256,
    )["by_n"]

    # 4. Run Scheme A m=4 confirmatory + sensitivity + historical baselines in SeedSequence([active_seed, 0])
    scheme_a_m4 = _run_scheme_a_m4_block(
        sample_a=sample_a,
        b_reps=b_reps,
        seed=active_seed,
        tango_by_n=tango_by_n,
        build_events=tango_build_events,
    )

    primary_claims = resolve_plan_e1_slot_claims(
        scheme_a_m4["hybrid_pct_tango"],
        scheme_a_m4["observed_point_lower"],
        scheme_a_m4["observed_point_upper"],
    )
    sensitivity_claims = resolve_plan_e1_slot_claims(
        scheme_a_m4["hybrid_bessel_t_tango"],
        scheme_a_m4["observed_point_lower"],
        scheme_a_m4["observed_point_upper"],
    )

    # 5. Run legacy V4 m=10 descriptive archive
    legacy_v4_m10 = None
    if v4_lo is not None and v4_hi is not None:
        rng_v4 = np.random.default_rng(np.random.SeedSequence([active_seed, 0]))
        kernel_v4 = v4_core.JointKernel(v4_lo, v4_hi)
        wt_obs_v4 = np.ones((1, len(telic_clusters)), dtype=float)
        wa_obs_v4 = np.ones((1, len(atelic_clusters)), dtype=float)
        (v4_obs_lo, v4_obs_hi), (v4_obs_se_lo, v4_obs_se_hi) = v4_studentized.statistics_and_se(
            kernel_v4, wt_obs_v4, wa_obs_v4
        )
        (v4_boot_m_lo, v4_boot_m_hi), (v4_boot_se_lo, v4_boot_se_hi) = v4_studentized.bootstrap(
            v4_lo, v4_hi, rng_v4, b=b_reps
        )
        v4_stud_inf = v4_studentized.infer(
            v4_boot_m_lo, v4_boot_m_hi, v4_boot_se_lo, v4_boot_se_hi,
            v4_obs_lo[0], v4_obs_hi[0], v4_obs_se_lo[0], v4_obs_se_hi[0],
        )
        v4_pct_inf = v4_core.infer(v4_boot_m_lo, v4_boot_m_hi, v4_obs_lo[0], v4_obs_hi[0])
        legacy_v4_m10 = {
            "names": list(v4_core.NAMES),
            "studentized": _serialize_inf(v4_stud_inf),
            "percentile": _serialize_inf(v4_pct_inf),
            "observed_point_lower": v4_obs_lo[0].tolist(),
            "observed_point_upper": v4_obs_hi[0].tolist(),
            "observed_se_lower": v4_obs_se_lo[0].tolist(),
            "observed_se_upper": v4_obs_se_hi[0].tolist(),
        }

    # 6. Run sealed formal_engine.compute_observation_profile + disaggregated 4-status compliance profile
    dataset_for_profile = {
        "unit_map": build_unit_map_for_sealed_profile_engine(unit_map),
        "split_info": {
            "telic_clusters": telic_clusters,
            "atelic_clusters": atelic_clusters,
            "group_items": group_items,
            "all_ids": sorted(all_ids),
        },
    }
    obs_profile = compute_observation_profile(
        dataset_for_profile,
        b_reps=b_reps,
        seed=active_seed,
        tango_by_n=tango_by_n,
        exact_tango_npz_path=tango_npz_path,
    )
    four_status_compliance = compute_four_status_compliance_profile(
        unit_map=unit_map,
        telic_clusters=telic_clusters,
        atelic_clusters=atelic_clusters,
        b_reps=b_reps,
        seed=active_seed,
        tango_by_n=tango_by_n,
    )
    # Keep dev (non_ok_count == 0) bit-for-bit identical to Step 5b dev-dry-run.json while reconciling any non_ok > 0
    if val_summary["non_ok_count"] > 0:
        reconcile_obs_profile_cost_and_format_four_statuses(obs_profile, four_status_compliance)

    t_after_core_profile = time.perf_counter()

    # 7. Missingness companions & telic verb-subclass profile
    t_miss0 = time.perf_counter()
    missingness_companions = compute_missingness_companions(
        unit_map=unit_map,
        telic_clusters=telic_clusters,
        atelic_clusters=atelic_clusters,
        val_summary=val_summary,
        b_reps=b_reps,
        seed=active_seed,
        tango_by_n=tango_by_n,
        tango_workers=tango_workers,
        _test_grid_override=_test_on_demand_tango_grid,
        build_events=tango_build_events,
    )
    t_miss_elapsed = time.perf_counter() - t_miss0

    verb_subclass_profile = compute_telic_verb_subclass_profile(
        unit_map=unit_map,
        telic_clusters=telic_clusters,
        items_json_path=exp1_root / "data" / "imperfectiveNLI.json",
    )

    on_demand_build_sec = sum(float(ev["seconds"]) for ev in tango_build_events)
    total_wall_sec = time.perf_counter() - t_total_start
    core_and_profile_sec = max(0.0, t_after_core_profile - t_total_start)

    confirmatory_valid = bool(stage == "formal" and not diagnostic_non_confirmatory)
    analysis_mode = (
        "confirmatory_formal"
        if confirmatory_valid
        else ("diagnostic_non_confirmatory" if diagnostic_non_confirmatory else "dev_dry_run")
    )
    claims_bundle = {
        "primary_hybrid_pct_tango": primary_claims,
        "sensitivity_hybrid_bessel_t_tango": sensitivity_claims,
    }

    return {
        "schema_version": "exp1-s7-formal-analysis-v2",
        "analysis_mode": analysis_mode,
        "confirmatory_valid": confirmatory_valid,
        "split_name": stage,
        "config": cfg,
        "expected_runner_fingerprint": expected_fp,
        "s5_frozen": bool(stage != "dev" and s5_freeze_gate is not None),
        "s5_freeze_gate": s5_freeze_gate,
        "option_iii_governance": {
            "user_decision_date": "2026-11-01",
            "decision": "Option III pre-freeze exception authorizing direct S5 freeze preparation",
            "primary_confirmatory_method": "hybrid_pct_tango",
            "sensitivity_companion_method": "hybrid_bessel_t_tango",
            "step5b_branch_id": 4,
            "step5b_calibration_C_j": "82/88",
            "step5b_degeneracy_D_j": "5/5",
            "step5b_power_P_j": "17/17",
            "step5b_max_screen0125": 0.0215,
            "confirmation_bank_2026110102_used": False,
        },
        "bootstrap_replicates": b_reps,
        "seed": active_seed,
        "sealed_identity_verified": True,
        "sealed_integrity_gates": sealed_gates,
        "runtime_telemetry": {
            "python_version": sys.version.split()[0],
            "python_full_version": sys.version,
            "numpy_version": np.__version__,
            "platform": platform.platform(),
            "machine": platform.machine(),
            "peak_rss_mib": _get_peak_rss_mib(),
            "zero_missing_core_and_profile_seconds": round(float(core_and_profile_sec), 6),
            "missingness_companions_wall_seconds": round(float(t_miss_elapsed), 6),
            "on_demand_tango_table_build_seconds": round(float(on_demand_build_sec), 6),
            "on_demand_tango_table_builds": tango_build_events,
            "total_wall_seconds": round(float(total_wall_sec), 6),
        },
        "observation_rank_policy": {
            "formula_0based": "ceil(q * B) - 1",
            "rank_95_0based_at_B5000": [RANK_95_LO, RANK_95_HI],
            "rank_95_1based_at_B5000": [RANK_95_LO + 1, RANK_95_HI + 1],
            "rank_9875_0based_at_B5000": [RANK_MAIN_LO, RANK_MAIN_HI],
            "rank_9875_1based_at_B5000": [RANK_MAIN_LO + 1, RANK_MAIN_HI + 1],
        },
        "provenance": source_provenance,
        "validation_summary": val_summary,
        "confirmatory_claims_option_iii": claims_bundle if not diagnostic_non_confirmatory else None,
        "non_confirmatory_slot_evaluations": claims_bundle if not confirmatory_valid else None,
        "scheme_a_m4": scheme_a_m4,
        "missingness_companions": missingness_companions,
        "telic_verb_subclass_profile": verb_subclass_profile,
        "legacy_v4_m10": legacy_v4_m10,
        "four_status_compliance": four_status_compliance,
        "observation_profile": obs_profile,
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage", default="formal", choices=("dev", "formal"))
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    parser.add_argument("--expected-fp", default=EXPECTED_RUNNER_FP)
    parser.add_argument("--exp1-root", default=str(DEFAULT_EXP1_ROOT))
    parser.add_argument("--step5b-root", default=str(DEFAULT_STEP5B_ROOT))
    parser.add_argument("--manifest", default=str(EXECUTION_MANIFEST_PATH))
    parser.add_argument("--split", default=None, help="Optional override for exp1-en/split.json")
    parser.add_argument("--results-jsonl", default=None, help="Optional override for stage results.jsonl")
    parser.add_argument(
        "--unit-index-json",
        default=None,
        help="Read stripped unit-index JSON (allowed on dev or with --diagnostic-non-confirmatory only)",
    )
    parser.add_argument("--write-unit-index", default=None, help="Optional output path for stripped unit-index JSON")
    parser.add_argument("--b-reps", type=int, default=FORMAL_BOOTSTRAP_B)
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument(
        "--diagnostic-non-confirmatory",
        action="store_true",
        help="Explicitly isolate non-default parameters or --unit-index-json on formal as non-confirmatory diagnostics",
    )
    parser.add_argument(
        "--out-json",
        default=str(SCRIPT_DIR / "results" / CANONICAL_FORMAL_JSON_NAME),
        help="Output path for S7 JSON results",
    )
    parser.add_argument(
        "--out-report",
        default=str(SCRIPT_DIR / "results" / CANONICAL_FORMAL_REPORT_NAME),
        help="Output path for programmatic S7 Markdown report",
    )
    args = parser.parse_args(argv)

    out_json_path = Path(args.out_json)
    out_report_path = Path(args.out_report)

    res = run_s7_pipeline(
        stage=args.stage,
        cfg=args.config,
        expected_fp=args.expected_fp,
        exp1_root=Path(args.exp1_root),
        step5b_root=Path(args.step5b_root),
        split_path=Path(args.split) if args.split else None,
        results_jsonl_path=Path(args.results_jsonl) if args.results_jsonl else None,
        unit_index_json_path=Path(args.unit_index_json) if args.unit_index_json else None,
        write_unit_index_path=Path(args.write_unit_index) if args.write_unit_index else None,
        b_reps=args.b_reps,
        seed=args.seed,
        diagnostic_non_confirmatory=args.diagnostic_non_confirmatory,
        out_json_path=out_json_path,
        out_report_path=out_report_path,
        manifest_path=Path(args.manifest),
    )

    atomic_write_json_lf(out_json_path, res)
    report_md = render_s7_markdown_report(res)
    atomic_write_text_lf(out_report_path, report_md)

    print(
        json.dumps(
            {
                "ok": True,
                "stage": res["split_name"],
                "analysis_mode": res["analysis_mode"],
                "confirmatory_valid": res["confirmatory_valid"],
                "seed": res["seed"],
                "total_units": res["validation_summary"]["total_units"],
                "status_ok_count": res["validation_summary"]["status_ok_count"],
                "non_ok_count": res["validation_summary"]["non_ok_count"],
                "out_json": str(out_json_path),
                "out_json_sha256": file_sha256(out_json_path),
                "out_report": str(out_report_path),
                "out_report_sha256": file_sha256(out_report_path),
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
