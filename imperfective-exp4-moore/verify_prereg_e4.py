"""Offline byte, material, calibration-lock, and runner-fingerprint verifier for imperfective Experiment 4 (English Moorean Paradox).

Uses only the Python standard library; never imports model clients, writes files,
or accesses the network.
"""
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import random

EXPECTED_CONFIG = "qwen3-8b@macmini-m6"
EXPECTED_RUNNER_FP = "8c93bc6870a1a00500c3e91c7fd842a100e7d573c33c965963c6ccddec8dce2d"
EXPECTED_PLAN_MD_SHA256 = "d4a2915113f79d0679d2319333c9ae2d4c3f4a604332340ec8b45f45d983275e"
EXPECTED_PLAN_E4_SHA256 = "750339807d4b97a96cf1702eafe73c062e783069851639d3084cbaee3775ad85"
EXPECTED_CALIBRATION_E4_SHA256 = "4de801144abc35dd75b67a768d279a8b5582d8b6d6536e669dbdf26237b604df"
EXPECTED_C_REVIEW_SHA256 = "3621d32131d8e75e9921254a71286471d77464d661e4d40da468cb6f5f169cdf"
EXPECTED_SUBCLASSES_SHA256 = "77b1874bba695c33197c8898afa23285186525ed20593f9e9407446fce754bc4"
EXPECTED_SPLIT_SHA256 = "1552968c6b597b37b18eb349ba81f0c08e0faa037d66bfcf468bb2a5d8055731"
EXPECTED_CLUSTERS_100_E4_SHA256 = "f0a2de8192a1c7321e8903818920036b8dcce1b607644f4c3381a5d41768b3f3"
EXPECTED_TANGO_NPZ_SHA256 = "e6378b3a1c85bf851ff623e906d50edb0572f2b282a3c66297483ef1a43ea3ff"
EXPECTED_TANGO_META_SHA256 = "2ecabd0e9158dcc51b03dc1f46da6558602f364ce6fbd9744f2cb44fa83dd9e1"
EXPECTED_TANGO_PAYLOAD_SHA256 = "b22aafc7e21787ead903540ac8312a48a1444f7c2627c8ce3813703556a04ddf"
EXPECTED_DEV_PLANNED_UNITS_SHA256 = "3424fb693e93d10450be7c4e80a1cd02d70dbcf4f85ccffb7f5574db50dd6f15"
EXPECTED_FORMAL_PLANNED_UNITS_SHA256 = "412e871de206b007ed9339e31525c311a6c81b794e23353082d7110fff216973"

EXP4_RUNNER_FILES_IN_FP = (
    "common.py",
    "provenance.py",
    "curate_100_clusters_e4.py",
    "validate_materials_e4.py",
    "prompts_e4.py",
    "prompt_parts.py",
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
    "exact_tango_e4.py",
    "core_e4.py",
    "calibrate_e4.py",
    "subclasses_e4.json",
    "split.json",
)

EXP4_FROZEN_SHA256 = {
    "common.py": "665fa8d5baa0b75e84121a5c0226fa097b9919a7965be8b753ce0eb229d608bf",
    "provenance.py": "571f5272dc0df6a5623077bf7a41dc908f1b3219aba81f674247db8999931c48",
    "curate_100_clusters_e4.py": "07bf41530b2a96fbb53e16391e70b1347f963d3472477260d3541fcfc873123e",
    "validate_materials_e4.py": "eef0f594d2c4574f13430d8ab735aa6f775d50206b0a2f4d49e037aa6d0cb135",
    "prompts_e4.py": "63442bf71ec72a9b1e77a21f8abe4c62d3508cc5d46507ecf351799368971a90",
    "prompt_parts.py": "027a6329088a71bb18fe2d4ac8d4999bec00f34af707092c659d54d5f69b8e41",
    "parse.py": "b44d0c453dc54d03e605dc00e5fa2fa8538c998264f93c028ea397c4e6f5f342",
    "protocol.py": "8b427b57400016e50bdab458c4402efcfb80718541b78b9eb7ebc7baa55e6904",
    "score.py": "ce5a5ea26be775f6aa206c57ba0253cf57b9219730a0bd830187b021370e3f3a",
    "run.py": "a598d2570e74a95517c1dfcc2d98d9c37edef3995391975ac371a18e59cbc69b",
    "subject.py": "b522d5c2c53e82faec613b3c9ccdc5bf09b972b890cb66066af9cff1e4e4188c",
    "host.py": "0f70a90e696ffb27b4410d22cd59756a86631e0ca9c0796322a056439802070c",
    "admission.py": "96f438c73ca6b4f5772943711ee42f49180199bdf14015cdda4b99b7532c5981",
    "ledger.py": "4b2da3e94bb1a6edf4e32943efef226662e3de69ae000302080ee33cc916871a",
    "gates.py": "94e6955d549b3aab26a7a55d4989f8534d0e0edc0143b20ad492c2916278a938",
    "deadline.py": "6b73c2d696b5fda1a351cf7e0f2d479524c73f4b38642dddb01e72b98854ef9e",
    "dry_stub.py": "a92acc4b3cf08908f33ba191baafc4df546f9050290b237317cfa159d937f546",
    "check_tokens.py": "e8076ce55e7c2895a9f1a4e37a3d548c633eef5a34898aaf3d83a6792b77d753",
    "exact_tango_e4.py": "df21fd7a74d4fa1ee96b4b06f7b0d2fc4820f750aa9565a435024b183c85a4c6",
    "core_e4.py": "7c766006ce544402a4655bd52c9f8577c948f7e405e774748eb05691e387940e",
    "calibrate_e4.py": "a4c928e0e86a42eee89aaf603fa310bdc7e50f849c0ec365fd5cf6709b400279",
    "subclasses_e4.json": EXPECTED_SUBCLASSES_SHA256,
    "split.json": EXPECTED_SPLIT_SHA256,
    "host_macos.py": "2c069e839629df41a2e4e7700d4ecebc66675847a6abbe76ba19d40a3ae46b7e",
    "config_models.json": "64e2eba87ecd4173caa7cce8734e57517bd704a7c217638107e144319acdb1c4",
    "config_assets_macmini-m6.json": "6af91feeafd4d82597133b7eabeea65a4d2296f8e1fbf2fed71c730326703ca1",
    "host_paths_macmini-m6.json": "98a6ce3cb989a723b4833f48dfa4596b79a7d7a140e078cad87feea18f6f4ea4",
    "label_tokens_qwen3-8b.json": "db388dec0a0ecfc93d8bc55e6fa66da460a153bfdd01c1b54f23214b04691259",
    "gpu_preflight_macos.py": "9e8e7fad51cce62013c83993ea31e080036f92f43dad00f45e52bf6f01356392",
    "PLAN-E4.md": EXPECTED_PLAN_E4_SHA256,
    "s1_preview_e4.md": "29e6378c6beb1095add94a3b08a661a98f51895dc9d6296f5d9b5af31376932e",
    "test_e4.py": "149ada8e3065341c615b3340053c369793d74c8d9fdf1ff27570cea63a11539a",
    "data/clusters_100_e4.json": EXPECTED_CLUSTERS_100_E4_SHA256,
    "manifests/exact-tango-tables-e4.npz": EXPECTED_TANGO_NPZ_SHA256,
    "manifests/exact-tango-tables-e4-meta.json": EXPECTED_TANGO_META_SHA256,
    "freeze/qwen3-8b@macmini-m6/8c93bc68/PLAN-E4.frozen.md": EXPECTED_PLAN_E4_SHA256,
    "freeze/qwen3-8b@macmini-m6/8c93bc68/calibration-e4.json": EXPECTED_CALIBRATION_E4_SHA256,
    "freeze/qwen3-8b@macmini-m6/8c93bc68/c-review.md": EXPECTED_C_REVIEW_SHA256,
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


def bindings(cal_meta, split_data, subclasses_data):
    """Yield (config, section, logical_path, expected_sha256) for every frozen binding."""
    cfg = EXPECTED_CONFIG
    yield cfg, "overall_plan", "imperfective-exp4-moore/PLAN.md", EXPECTED_PLAN_MD_SHA256
    yield cfg, "frozen_plan", "imperfective-exp4-moore/exp4-moore/PLAN-E4.md", EXPECTED_PLAN_E4_SHA256
    yield (
        cfg,
        "freeze_snapshot.plan",
        "imperfective-exp4-moore/exp4-moore/freeze/qwen3-8b@macmini-m6/8c93bc68/PLAN-E4.frozen.md",
        EXPECTED_PLAN_E4_SHA256,
    )
    yield (
        cfg,
        "freeze_snapshot.calibration",
        "imperfective-exp4-moore/exp4-moore/freeze/qwen3-8b@macmini-m6/8c93bc68/calibration-e4.json",
        EXPECTED_CALIBRATION_E4_SHA256,
    )
    yield (
        cfg,
        "freeze_snapshot.c_review",
        "imperfective-exp4-moore/exp4-moore/freeze/qwen3-8b@macmini-m6/8c93bc68/c-review.md",
        EXPECTED_C_REVIEW_SHA256,
    )
    for rel_name, digest in sorted(EXP4_FROZEN_SHA256.items()):
        yield cfg, "exp4_frozen", "imperfective-exp4-moore/exp4-moore/" + rel_name, digest
    for code_name, digest in sorted(cal_meta.get("code_hashes", {}).items()):
        if code_name == "exact-tango-tables-e4.npz":
            yield cfg, "calibration_code_hashes", "imperfective-exp4-moore/exp4-moore/manifests/" + code_name, digest
        else:
            yield cfg, "calibration_code_hashes", "imperfective-exp4-moore/exp4-moore/" + code_name, digest
    yield (
        cfg,
        "provenance.clusters_100_e4",
        "imperfective-exp4-moore/exp4-moore/data/clusters_100_e4.json",
        EXPECTED_CLUSTERS_100_E4_SHA256,
    )
    yield (
        cfg,
        "provenance.subclasses_e4",
        "imperfective-exp4-moore/exp4-moore/subclasses_e4.json",
        EXPECTED_SUBCLASSES_SHA256,
    )
    yield (
        cfg,
        "provenance.split",
        "imperfective-exp4-moore/exp4-moore/split.json",
        EXPECTED_SPLIT_SHA256,
    )


def _recompute_runner_fingerprint_and_plans(exp4_dir, split_data, subclasses_data):
    """Stdlib-only exact reproduction of exp4-moore/run.py Context.fp and stage plans."""
    import sys

    if str(exp4_dir) not in sys.path:
        sys.path.insert(0, str(exp4_dir))
    import prompts_e4
    import provenance
    import validate_materials_e4

    clusters_doc = json.loads((exp4_dir / "data" / "clusters_100_e4.json").read_text(encoding="utf-8"))
    val_errs = validate_materials_e4.validate_materials(clusters_doc, subclasses_data, split_data)
    if val_errs:
        raise ValueError("validate_materials errors: " + "; ".join(val_errs[:5]))

    items_list = provenance.load_items()
    items = {i["id"]: i for i in items_list}

    combinations = prompts_e4.COMBINATIONS
    diag_combinations = (("L", "Z"), ("P", "Z"), ("M", "Z"))

    def unit_dict(iid, task, prompt):
        item = items[iid]
        return {
            "id": iid,
            "cluster_id": item["cluster_id"],
            "domain_subclass": item["domain_subclass"],
            "topic_label": item["topic_label"],
            "speaker": item["speaker"],
            "slot": item["slot"],
            "is_diagnostic": item["is_diagnostic"],
            "task": task,
            "prompt": prompt,
            "unit_key": f"{iid}/{task}/{prompt}",
        }

    def build_plan(stage):
        main_ids = sorted(split_data[stage]["main_ids"])
        random.Random(2026110691).shuffle(main_ids)
        main_units = [unit_dict(iid, t, p) for iid in main_ids for t, p in combinations]
        if stage in ("smoke", "dev"):
            diag_ids = sorted(split_data[stage]["diag_ids"])
            diag_units = [unit_dict(iid, t, p) for iid in diag_ids for t, p in diag_combinations]
            return main_units + diag_units
        return main_units

    dev_plan = build_plan("dev")
    formal_plan = build_plan("formal")
    material = [
        (
            u["unit_key"],
            canonical_digest(
                prompts_e4.render_unit(items[u["id"]]["premise"], items[u["id"]]["hypothesis"], u["task"], u["prompt"])
            ),
        )
        for u in (dev_plan + formal_plan)
    ]

    model_cfg = json.loads((exp4_dir / "config_models.json").read_text(encoding="utf-8"))["qwen3-8b"]
    assets = json.loads((exp4_dir / "config_assets_macmini-m6.json").read_text(encoding="utf-8"))["models"]["qwen3-8b"]
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
        "files": {f: sha((exp4_dir / f).read_bytes()) for f in EXP4_RUNNER_FILES_IN_FP},
        "model": model_cfg,
        "host_id": "macmini-m6",
        "assets": assets,
        "tokens": sha((exp4_dir / "label_tokens_qwen3-8b.json").read_bytes()),
        "host_implementation": sha((exp4_dir / "host_macos.py").read_bytes()),
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
    exp4_dir = here / "exp4-moore"
    freeze_dir = exp4_dir / "freeze" / "qwen3-8b@macmini-m6" / "8c93bc68"
    cal_meta = json.loads((freeze_dir / "calibration-e4.json").read_text(encoding="utf-8"))
    split_data = json.loads((exp4_dir / "split.json").read_text(encoding="utf-8"))
    subclasses_data = json.loads((exp4_dir / "subclasses_e4.json").read_text(encoding="utf-8"))
    tango_meta = json.loads((exp4_dir / "manifests" / "exact-tango-tables-e4-meta.json").read_text(encoding="utf-8"))
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

    for config, section, name, digest in bindings(cal_meta, split_data, subclasses_data):
        compare(logical(name), digest, config + "/" + section)

    # Verify calibration-e4.json invariants
    if cal_meta.get("schema_version") != "e4_calibration_v1":
        errors.append("calibration-e4.json: schema_version != 'e4_calibration_v1'")
    if cal_meta.get("seed") != 2026110611:
        errors.append("calibration-e4.json: seed != 2026110611")
    if cal_meta.get("r_reps") != 2000 or cal_meta.get("b_draws") != 5000:
        errors.append("calibration-e4.json: r_reps != 2000 or b_draws != 5000")
    if cal_meta.get("n_formal") != 80 or cal_meta.get("n_per_domain") != 20:
        errors.append("calibration-e4.json: formal stratum sizes mismatch")
    if cal_meta.get("total_cells") != 20:
        errors.append("calibration-e4.json: total_cells != 20")
    if cal_meta.get("production_eligible") is not True or cal_meta.get("status") != "pass":
        errors.append("calibration-e4.json: production_eligible or status not pass")
    if cal_meta.get("selected_step") != 2 or cal_meta.get("selected_family") != "hybrid_bessel_t_tango_e4":
        errors.append("calibration-e4.json: selected_step != 2 or selected_family != 'hybrid_bessel_t_tango_e4'")
    if cal_meta.get("companion_family") != "hybrid_pct_tango_e4":
        errors.append("calibration-e4.json: companion_family != 'hybrid_pct_tango_e4'")
    if cal_meta.get("demoted_slots") != []:
        errors.append("calibration-e4.json: demoted_slots != []")
    c2_cells = cal_meta.get("candidate_2_cells")
    if not isinstance(c2_cells, list) or len(c2_cells) != 20 or not all(c.get("cell_passed") is True for c in c2_cells):
        errors.append("calibration-e4.json: candidate_2_cells failed 20/20 cell gate")

    # Verify Tango metadata
    if tango_meta.get("npz_file_sha256") != EXPECTED_TANGO_NPZ_SHA256:
        errors.append("exact-tango-tables-e4-meta.json: npz_file_sha256 mismatch")
    if tango_meta.get("npz_payload_sha256") != EXPECTED_TANGO_PAYLOAD_SHA256:
        errors.append("exact-tango-tables-e4-meta.json: npz_payload_sha256 mismatch")
    if tango_meta.get("supported_ns") != [5, 20, 80]:
        errors.append("exact-tango-tables-e4-meta.json: supported_ns != [5, 20, 80]")

    # Optional check if freeze.json is also present on disk
    freeze_json_path = freeze_dir / "freeze.json"
    freeze_json_status = "recorded_post_push_in_PREREGISTRATION_RECORD"
    if freeze_json_path.is_file():
        frz = json.loads(freeze_json_path.read_text(encoding="utf-8"))
        if (
            frz.get("type") != "freeze"
            or frz.get("status") != "pass"
            or frz.get("config") != EXPECTED_CONFIG
            or frz.get("fingerprint_id") != EXPECTED_RUNNER_FP
            or frz.get("frozen_plan_sha256") != EXPECTED_PLAN_E4_SHA256
            or frz.get("calibration_sha256") != EXPECTED_CALIBRATION_E4_SHA256
            or frz.get("selected_family") != "hybrid_bessel_t_tango_e4"
            or frz.get("demoted_slots") != []
            or frz.get("c_blockers") != 0
            or frz.get("user_confirmed") is not True
            or not str(frz.get("prereg_commit", "")).strip()
            or not str(frz.get("prereg_pushed_at", "")).strip()
        ):
            errors.append("freeze.json invariants mismatch")
            freeze_json_status = "failed"
        else:
            freeze_json_status = "verified"

    # Recompute full 5,320-unit runner fingerprint and planned unit digests
    fp_status = "failed"
    recomputed_info = {}
    try:
        recomputed_info = _recompute_runner_fingerprint_and_plans(exp4_dir, split_data, subclasses_data)
        if recomputed_info["fingerprint_id"] != EXPECTED_RUNNER_FP:
            errors.append(
                f"runner fingerprint_id mismatch: {recomputed_info['fingerprint_id']} != {EXPECTED_RUNNER_FP}"
            )
        elif recomputed_info["dev_planned_units_sha256"] != EXPECTED_DEV_PLANNED_UNITS_SHA256:
            errors.append("recomputed dev_planned_units_sha256 mismatch")
        elif recomputed_info["formal_planned_units_sha256"] != EXPECTED_FORMAL_PLANNED_UNITS_SHA256:
            errors.append("recomputed formal_planned_units_sha256 mismatch")
        elif recomputed_info["dev_planned_units"] != 1160 or recomputed_info["formal_planned_units"] != 4160:
            errors.append("recomputed unit counts mismatch (expected 1160 dev + 4160 formal)")
        else:
            fp_status = "verified"
    except Exception as exc:
        errors.append(f"runner fingerprint_id recomputation failed: {exc}")

    return dict(
        ok=not errors,
        verified_files=len(set(verified)),
        runner_fingerprint_id=EXPECTED_RUNNER_FP,
        runner_fingerprint_recomputed=fp_status,
        recomputed_unit_counts={
            "dev": recomputed_info.get("dev_planned_units"),
            "formal": recomputed_info.get("formal_planned_units"),
            "total": recomputed_info.get("total_rendered_units"),
        },
        frozen_plan_sha256=EXPECTED_PLAN_E4_SHA256,
        calibration_e4_sha256=EXPECTED_CALIBRATION_E4_SHA256,
        selected_family=cal_meta.get("selected_family"),
        companion_family=cal_meta.get("companion_family"),
        demoted_slots=cal_meta.get("demoted_slots"),
        freeze_json_status=freeze_json_status,
        excluded_artifacts=[],
        self_acquisition_required=[],
        errors=errors,
    )


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
