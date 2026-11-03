"""Offline byte, material, calibration-lock, and runner-fingerprint verifier for imperfective Experiment 2 (Chinese).

Uses only the Python standard library; never imports model clients, writes files,
or accesses the network.
"""
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import random

EXPECTED_CONFIG = "qwen3-8b@macmini-m6"
EXPECTED_RUNNER_FP = "f81940ea79504f533d62d796a10812b2dd8e170f9b95a9d6e813d0d4e736b74b"
EXPECTED_PLAN_MD_SHA256 = "d4a2915113f79d0679d2319333c9ae2d4c3f4a604332340ec8b45f45d983275e"
EXPECTED_PLAN_E2_SHA256 = "81fd2fe12540cc665fa650ffde3224ac95e9d08902af501b6cd2400212bac2c9"
EXPECTED_CALIBRATION_E2_SHA256 = "4ad1af9ccfe15bdc89a3e51b861f9503e1ed77b0e686d72f1954b748aca11d32"
EXPECTED_C_REVIEW_SHA256 = "5cdaf9f192789302f175811f1cbbd1bb3d5524bb7bf63b021c10a9be3455f7b0"
EXPECTED_FREEZE_JSON_SHA256 = "ffa29ab0d5c6455fe878c34c49a3df7044054793ddb1e7538818abc74a3a41ae"
EXPECTED_CLUSTERS_100_SHA256 = "963636a2a74a38f8b8fe6363a079be38f5f2f1b35ef37f1cf3fc89dd7fd6c437"
EXPECTED_SEED_18_SHA256 = "6f31e854e1b34e01315bb8804bc0f70d93995d81cee6fc1e39264fe24ba92db5"
EXPECTED_SPLIT_SHA256 = "6382d84a293107215ab034d565415adc8f0a438d90152f4c2b2e9a8d868c3973"
EXPECTED_TANGO_NPZ_SHA256 = "2eb9bfd0db577301c44e5a49ad5ed1d4296b33031db7b54c78710e11043115a6"
EXPECTED_TANGO_META_SHA256 = "ee65e7218f1e3877c366b37ec4b14373dcd0d6d5f64a38d7492d55c9c9367a03"
EXPECTED_TANGO_PAYLOAD_SHA256 = "18946c579cf191188a7b2c3c9b9ac967a3823e32db4544879933f81741bc323b"
EXPECTED_DEV_PLANNED_UNITS_SHA256 = "ad57fefc7cc34bb31e263aca7ccbeb04dbd11ae835045dd923ccc0c2e1a37c70"

EXP2_RUNNER_FILES_IN_FP = (
    "common.py",
    "provenance.py",
    "validate_materials.py",
    "split_e2.py",
    "prompts_zh.py",
    "parse.py",
    "protocol.py",
    "score.py",
    "run.py",
    "subject.py",
    "host.py",
    "admission.py",
    "ledger.py",
    "gates.py",
    "deadline.py",
    "dry_stub.py",
    "check_tokens.py",
    "exact_tango_e2.py",
    "core_e2.py",
    "calibrate_e2.py",
    "split.json",
)

EXP2_FROZEN_SHA256 = {
    "common.py": "c6a5402078f0ba5142527cc24b7781edf50343b968c07311762d3446ca70d6c3",
    "provenance.py": "7667832714ccac6a8244b91037eb4bd0d2326a8b385aa6c38a34dfcf316053d1",
    "validate_materials.py": "a8a9121deac5bcd68ac99f459b2b986aebef60a82c9cf157108f95a7acbffb95",
    "split_e2.py": "65129cee14beff7b9387950143af8fbd2756913a0a715575dcf4eddbd48121b2",
    "prompts_zh.py": "fef39c2e1e86f4aa62c3d259324cbc3c938af7229f35ce496348fc6b877621b6",
    "parse.py": "b44d0c453dc54d03e605dc00e5fa2fa8538c998264f93c028ea397c4e6f5f342",
    "protocol.py": "398669f4bdc20c15878d16520b5558e2de98d45c5584add05bde9aedb8efc61e",
    "score.py": "edf2ff6ec532e16dc5a29b59c6d82687c2166efc9e5570fb9d0944590129b930",
    "run.py": "d6b4386b420aa4ff7d532afba2de28b815e6cb0d2e4195501e1ed7f05ebd729c",
    "subject.py": "50979add5681415ff732323a82b9cd5a1bb77b6999cf4572cc4403fbd0276061",
    "host.py": "3d3ee96ab72b6817b0bc700b73ef19f52c11376611bdbdce17a70e5324b81cd5",
    "admission.py": "3a5dd974ba9ffa852b5e7981a7a2f562c72047505c3aae1be0f46730a7259faf",
    "ledger.py": "4b2da3e94bb1a6edf4e32943efef226662e3de69ae000302080ee33cc916871a",
    "gates.py": "74e25281424f222af170efce243c475be18e6d7a2813eb7562855cc058e68ca0",
    "deadline.py": "1c74b4fb02417719c54e3ce1ddd2341eebaba245f6063628be53e3a0c327e370",
    "dry_stub.py": "b1f9c31e3d6ff03de9730f7a1ba7179db6e8ee4d59004ca2dec833f1e69dc9a5",
    "check_tokens.py": "c47270a1069416243fb718fb269abceaf9190989e89b255df14669785d722ddf",
    "exact_tango_e2.py": "b30a5c566c41d38c59d59813f5accb745b3c01beafa4e1d342b82dc141218603",
    "core_e2.py": "1c2c38f2edb4e3a5d0d77b95ca65f58ebc50370b7a6818d45e985e9886f670d0",
    "calibrate_e2.py": "17b54efc8ceded1a279dda19ba740581baa788e6b76d206b0cb450d3d4f77168",
    "split.json": EXPECTED_SPLIT_SHA256,
    "host_macos.py": "c347b9ab874532443b1c59441a4a9395f11910e7d242c559a1f2a2365158ef79",
    "config_models.json": "64e2eba87ecd4173caa7cce8734e57517bd704a7c217638107e144319acdb1c4",
    "config_assets_macmini-m6.json": "6af91feeafd4d82597133b7eabeea65a4d2296f8e1fbf2fed71c730326703ca1",
    "host_paths_macmini-m6.json": "98a6ce3cb989a723b4833f48dfa4596b79a7d7a140e078cad87feea18f6f4ea4",
    "label_tokens_qwen3-8b.json": "db388dec0a0ecfc93d8bc55e6fa66da460a153bfdd01c1b54f23214b04691259",
    "gpu_preflight_macos.py": "cd613ac6b1fe3b2158f3fb0fb90372452f2139cd998b70dc9c55b02372b06e73",
    "PLAN-E2.md": EXPECTED_PLAN_E2_SHA256,
    "data/clusters_100_curated.json": EXPECTED_CLUSTERS_100_SHA256,
    "data/seed_clusters_18.json": EXPECTED_SEED_18_SHA256,
    "manifests/exact-tango-tables-e2.npz": EXPECTED_TANGO_NPZ_SHA256,
    "manifests/exact-tango-tables-e2-meta.json": EXPECTED_TANGO_META_SHA256,
    "freeze/qwen3-8b@macmini-m6/f81940ea/PLAN-E2.frozen.md": EXPECTED_PLAN_E2_SHA256,
    "freeze/qwen3-8b@macmini-m6/f81940ea/calibration-e2.json": EXPECTED_CALIBRATION_E2_SHA256,
    "freeze/qwen3-8b@macmini-m6/f81940ea/c-review.md": EXPECTED_C_REVIEW_SHA256,
    "freeze/qwen3-8b@macmini-m6/f81940ea/freeze.json": EXPECTED_FREEZE_JSON_SHA256,
}


def sha(data):
    return hashlib.sha256(data).hexdigest()


def _json_safe(value):
    if isinstance(value, float) and not math.isfinite(value):
        return {"nonfinite": repr(value)}
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_json_safe(v) for v in value]
    return value


def canonical_digest(value):
    payload = json.dumps(_json_safe(value), ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha(payload.encode("utf-8"))


def logical(name):
    parts = []
    p = PurePosixPath(name)
    if p.is_absolute() or ":" in name or "\\" in name:
        raise ValueError("unsafe path: " + name)
    for part in p.parts:
        if part == "..":
            if not parts:
                raise ValueError("path escapes package: " + name)
            parts.pop()
        else:
            parts.append(part)
    return "/".join(parts)


def bindings(freeze_meta, cal_meta, split_data):
    """Yield (config, section, logical_path, expected_sha256) for every frozen binding."""
    cfg = freeze_meta["config"]
    yield cfg, "overall_plan", "imperfective-exp2-zh/PLAN.md", EXPECTED_PLAN_MD_SHA256
    yield cfg, "frozen_plan", "imperfective-exp2-zh/exp2-zh/PLAN-E2.md", freeze_meta["frozen_plan_sha256"]
    yield (
        cfg,
        "freeze_snapshot.plan",
        "imperfective-exp2-zh/exp2-zh/freeze/qwen3-8b@macmini-m6/f81940ea/PLAN-E2.frozen.md",
        freeze_meta["frozen_plan_sha256"],
    )
    yield (
        cfg,
        "freeze_snapshot.calibration",
        "imperfective-exp2-zh/exp2-zh/freeze/qwen3-8b@macmini-m6/f81940ea/calibration-e2.json",
        freeze_meta["calibration_sha256"],
    )
    for rel_name, digest in sorted(EXP2_FROZEN_SHA256.items()):
        yield cfg, "exp2_frozen", "imperfective-exp2-zh/exp2-zh/" + rel_name, digest
    for code_name, digest in sorted(cal_meta.get("code_hashes", {}).items()):
        if code_name == "exact-tango-tables-e2.npz":
            yield cfg, "calibration_code_hashes", "imperfective-exp2-zh/exp2-zh/manifests/" + code_name, digest
        else:
            yield cfg, "calibration_code_hashes", "imperfective-exp2-zh/exp2-zh/" + code_name, digest
    yield (
        cfg,
        "split.source_sha256",
        "imperfective-exp2-zh/exp2-zh/data/clusters_100_curated.json",
        split_data["source_sha256"],
    )


def _recompute_runner_fingerprint_and_plans(exp2_dir, split_data):
    """Stdlib-only exact reproduction of exp2-zh/run.py Context.fp and stage plans."""
    import sys

    if str(exp2_dir) not in sys.path:
        sys.path.insert(0, str(exp2_dir))
    import prompts_zh
    import provenance
    import validate_materials

    clusters = provenance.load_clusters(exp2_dir / "data" / "clusters_100_curated.json")
    val_errs = validate_materials.validate_clusters(clusters)
    if val_errs:
        raise ValueError("validate_clusters errors: " + "; ".join(val_errs[:5]))
    items_list = provenance.load_items(exp2_dir / "data" / "clusters_100_curated.json")
    items = {i["id"]: i for i in items_list}

    combinations = prompts_zh.COMBINATIONS
    diag_combinations = (("L", "Z"), ("P", "Z"), ("M", "Z"))
    slots = prompts_zh.SLOTS
    diag_slots = prompts_zh.DIAG_SLOTS

    def unit_dict(iid, task, prompt):
        item = items[iid]
        return {
            "id": iid,
            "cluster_id": item["cluster_id"],
            "macro_class": item["macro_class"],
            "subclass": item["subclass"],
            "slot": item["slot"],
            "is_diagnostic": item["is_diagnostic"],
            "task": task,
            "prompt": prompt,
            "unit_key": f"{iid}/{task}/{prompt}",
        }

    def build_plan(stage):
        cids = sorted(split_data[f"{stage}_cluster_ids"])
        main_ids = sorted(f"{cid}__{slot_name}" for cid in cids for slot_name, _, _ in slots)
        random.Random(2026110291).shuffle(main_ids)
        main_units = [unit_dict(iid, t, p) for iid in main_ids for t, p in combinations]
        if stage == "dev":
            diag_ids = sorted(f"{cid}__{slot_name}" for cid in cids for slot_name, _, _ in diag_slots)
            diag_units = [unit_dict(iid, t, p) for iid in diag_ids for t, p in diag_combinations]
            return main_units + diag_units
        return main_units

    dev_plan = build_plan("dev")
    formal_plan = build_plan("formal")
    material = [
        (
            u["unit_key"],
            canonical_digest(
                prompts_zh.render_unit(items[u["id"]]["premise"], items[u["id"]]["hypothesis"], u["task"], u["prompt"])
            ),
        )
        for u in (dev_plan + formal_plan)
    ]

    model_cfg = json.loads((exp2_dir / "config_models.json").read_text(encoding="utf-8"))["qwen3-8b"]
    assets = json.loads((exp2_dir / "config_assets_macmini-m6.json").read_text(encoding="utf-8"))["models"]["qwen3-8b"]
    sampling = {
        "temperature": 0.0,
        "top_k": 1,
        "top_p": 1.0,
        "min_p": 0.0,
        "samplers": ["temperature", "top_k"],
        "repeat_penalty": 1.0,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
        "dry_multiplier": 0.0,
        "xtc_probability": 0.0,
        "typical_p": 1.0,
        "top_n_sigma": -1.0,
        "mirostat": 0,
        "dynatemp_range": 0.0,
    }
    fp_obj = {
        "files": {f: sha((exp2_dir / f).read_bytes()) for f in EXP2_RUNNER_FILES_IN_FP},
        "model": model_cfg,
        "host_id": "macmini-m6",
        "assets": assets,
        "tokens": sha((exp2_dir / "label_tokens_qwen3-8b.json").read_bytes()),
        "host_implementation": sha((exp2_dir / "host_macos.py").read_bytes()),
        "materials": canonical_digest(material),
        "sampling": sampling,
        "max_tokens": 1024,
        "rules": {"topN": 100, "score_version": 1, "parse_version": 2, "protocol_version": 1},
        "dry": False,
    }
    return {
        "fingerprint_id": canonical_digest(fp_obj),
        "dev_planned_units": len(dev_plan),
        "dev_planned_units_sha256": canonical_digest(dev_plan),
        "formal_planned_units": len(formal_plan),
        "formal_planned_units_sha256": canonical_digest(formal_plan),
        "total_rendered_units": len(material),
    }


def verify(here=None):
    here = Path(here or Path(__file__).resolve().parent)
    root = here.parent.resolve()
    check = json.loads((here / "release-check.json").read_text(encoding="utf-8"))
    exp2_dir = here / "exp2-zh"
    freeze_dir = exp2_dir / "freeze" / "qwen3-8b@macmini-m6" / "f81940ea"
    freeze_meta = json.loads((freeze_dir / "freeze.json").read_text(encoding="utf-8"))
    cal_meta = json.loads((freeze_dir / "calibration-e2.json").read_text(encoding="utf-8"))
    split_data = json.loads((exp2_dir / "split.json").read_text(encoding="utf-8"))
    tango_meta = json.loads((exp2_dir / "manifests" / "exact-tango-tables-e2-meta.json").read_text(encoding="utf-8"))
    errors, verified = [], []

    def compare(name, expected, label, expected_bytes=None):
        name = logical(name)
        path = root / name
        if path.is_symlink() or root not in path.resolve().parents:
            errors.append(label + ": unsafe path " + name)
        elif not path.is_file():
            errors.append(label + ": missing " + name)
        else:
            raw = path.read_bytes()
            if expected_bytes is not None and len(raw) != expected_bytes:
                errors.append(label + ": byte-count mismatch " + name)
                return False
            if sha(raw) != expected:
                errors.append(label + ": SHA-256 mismatch " + name)
                return False
            verified.append(name)
            return True
        return False

    for item in check["files"]:
        compare(item["path"], item["sha256"], "release manifest", expected_bytes=item.get("bytes"))

    for config, section, name, digest in bindings(freeze_meta, cal_meta, split_data):
        compare(logical(name), digest, config + "/" + section)

    # Verify freeze.json invariants
    if freeze_meta.get("type") != "freeze" or freeze_meta.get("status") != "pass":
        errors.append("freeze.json: type/status must be freeze/pass")
    if freeze_meta.get("config") != EXPECTED_CONFIG:
        errors.append("freeze.json: config mismatch")
    if freeze_meta.get("fingerprint_id") != EXPECTED_RUNNER_FP:
        errors.append("freeze.json: fingerprint_id mismatch")
    if freeze_meta.get("frozen_plan_sha256") != EXPECTED_PLAN_E2_SHA256:
        errors.append("freeze.json: frozen_plan_sha256 mismatch")
    if freeze_meta.get("calibration_sha256") != EXPECTED_CALIBRATION_E2_SHA256:
        errors.append("freeze.json: calibration_sha256 mismatch")
    if freeze_meta.get("selected_family") != "hybrid_bessel_t_tango_e2":
        errors.append("freeze.json: selected_family must be hybrid_bessel_t_tango_e2")
    if freeze_meta.get("demoted_slots") != []:
        errors.append("freeze.json: demoted_slots must be []")
    if freeze_meta.get("c_blockers") != 0 or freeze_meta.get("user_confirmed") is not True:
        errors.append("freeze.json: c_blockers==0 and user_confirmed==True required")
    if freeze_meta.get("planned_units_sha256") != EXPECTED_DEV_PLANNED_UNITS_SHA256:
        errors.append("freeze.json: planned_units_sha256 mismatch")

    # Verify calibration-e2.json invariants
    if cal_meta.get("status") != "pass" or cal_meta.get("production_eligible") is not True:
        errors.append("calibration-e2.json: status==pass and production_eligible==True required")
    if cal_meta.get("selected_step") != 2 or cal_meta.get("selected_family") != "hybrid_bessel_t_tango_e2":
        errors.append("calibration-e2.json: selected_step==2 and selected_family==hybrid_bessel_t_tango_e2 required")
    if cal_meta.get("companion_family") != "hybrid_pct_tango_e2" or cal_meta.get("demoted_slots") != []:
        errors.append("calibration-e2.json: companion_family/demoted_slots mismatch")
    if cal_meta.get("r_reps") != 2000 or cal_meta.get("b_draws") != 5000 or cal_meta.get("seed") != 2026110311:
        errors.append("calibration-e2.json: r_reps/b_draws/seed mismatch")
    if cal_meta.get("candidate_2_passed_all_16") is not True or len(cal_meta.get("candidate_2_cells", [])) != 16:
        errors.append("calibration-e2.json: candidate_2 must pass all 16 cells")

    # Verify exact-tango-tables-e2-meta.json invariants
    if tango_meta.get("npz_file_sha256") != EXPECTED_TANGO_NPZ_SHA256:
        errors.append("exact-tango-tables-e2-meta.json: npz_file_sha256 mismatch")
    if tango_meta.get("npz_payload_sha256") != EXPECTED_TANGO_PAYLOAD_SHA256:
        errors.append("exact-tango-tables-e2-meta.json: npz_payload_sha256 mismatch")
    if tango_meta.get("supported_ns") != [8, 12, 16, 32, 48]:
        errors.append("exact-tango-tables-e2-meta.json: supported_ns mismatch")

    # Recompute full 5,320-unit runner fingerprint and planned unit digests
    fp_status = "failed"
    recomputed_info = {}
    try:
        recomputed_info = _recompute_runner_fingerprint_and_plans(exp2_dir, split_data)
        if recomputed_info["fingerprint_id"] != EXPECTED_RUNNER_FP:
            errors.append(
                f"runner fingerprint_id mismatch: {recomputed_info['fingerprint_id']} != {EXPECTED_RUNNER_FP}"
            )
        elif recomputed_info["dev_planned_units_sha256"] != EXPECTED_DEV_PLANNED_UNITS_SHA256:
            errors.append("recomputed dev_planned_units_sha256 mismatch")
        elif recomputed_info["dev_planned_units"] != 1160 or recomputed_info["formal_planned_units"] != 4160:
            errors.append("recomputed unit counts mismatch (expected 1160 dev + 4160 formal)")
        else:
            fp_status = "verified"
    except Exception as exc:
        errors.append(f"runner fingerprint_id recomputation failed: {exc}")

    return dict(
        ok=not errors,
        public_files=len(check["files"]),
        verified_unique_files=len(set(verified)),
        runner_fingerprint_id=EXPECTED_RUNNER_FP,
        runner_fingerprint_recomputed=fp_status,
        recomputed_unit_counts={
            "dev": recomputed_info.get("dev_planned_units"),
            "formal": recomputed_info.get("formal_planned_units"),
            "total": recomputed_info.get("total_rendered_units"),
        },
        frozen_plan_sha256=EXPECTED_PLAN_E2_SHA256,
        calibration_sha256=EXPECTED_CALIBRATION_E2_SHA256,
        freeze_json_sha256=EXPECTED_FREEZE_JSON_SHA256,
        selected_family=freeze_meta.get("selected_family"),
        companion_family=cal_meta.get("companion_family"),
        demoted_slots=freeze_meta.get("demoted_slots"),
        errors=errors,
        self_acquisition_required=[],
        limitations=[
            "ok:true means all listed public file hashes, 100 authored Chinese event clusters (600 items), S4 16-cell calibration lock (hybrid_bessel_t_tango_e2), S5 freeze.json, and full 5,320-unit runner fingerprint_id recomputation passed.",
            "Model GGUF weights, llama-server binary, Hugging Face tokenizer cache, and S3/S4 Mac host raw ledgers are external attestations bound by SHA-256.",
            "release-check.json is an inventory, not a cryptographic timestamp; authenticate against the public preregistration commit on GitHub.",
        ],
    )


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
