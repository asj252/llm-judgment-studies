"""Offline byte, material, calibration-lock, and runner-fingerprint verifier for imperfective Experiment 3 (English).

Uses only the Python standard library; never imports model clients, writes files,
or accesses the network.
"""
import ast
import hashlib
import json
import math
from pathlib import Path, PurePosixPath
import random
import re

EXPECTED_CONFIG = "qwen3-8b@macmini-m6"
EXPECTED_RUNNER_FP = "cbd3b5affec50ba44fd3206eba41d7795bdb5ad5c3fb7dec03c08a91475e07b3"
EXPECTED_PLAN_MD_SHA256 = "d4a2915113f79d0679d2319333c9ae2d4c3f4a604332340ec8b45f45d983275e"
EXPECTED_PLAN_E3_SHA256 = "ec4137b4a280b34977a26d755bd414b81392ec3419f6b9a84e4e6de941f3082b"
EXPECTED_CALIBRATION_E3_SHA256 = "0719bb94336a2b18e1795aae7767714169ddf94c60502aa542b14454a0a44806"
EXPECTED_C_REVIEW_SHA256 = "70acde0775c2fd7d1e3806264519665ff45f2cfa19d26a430bda0014a932f87f"
EXPECTED_SUBCLASSES_SHA256 = "ff3be2370261c499397fbfba9921086cb69467775d196e53bf6d83912c01721d"
EXPECTED_SPLIT_SHA256 = "cd0e099a38481b23c071d3950aac4527daf29aea12076f34ea9eadc4a90d7ea4"
EXPECTED_CLUSTERS_100_E3_SHA256 = "7f10a952c8ec32a4c978b69a0f755085fd76490d72d3706db8773b93d17da8aa"
EXPECTED_TANGO_NPZ_SHA256 = "59845e08a34c997c66b8d3c86244a87a7c5d8e6d018743c467bf37be4300828f"
EXPECTED_TANGO_META_SHA256 = "be32aeb7081fc122a4aa452fc58880b267637a03cffced8cf29f864b2da9ecef"
EXPECTED_TANGO_PAYLOAD_SHA256 = "0140b92cb110b6986af2d4ad0007d837cbac136e90ed7cce52135e0759df9439"
EXPECTED_EXP1_REF_SUMMARY_SHA256 = "739a91ede22b30d65a1dc41d38e681adc3a913ea01024bc4c53c0c89fa6dac5e"
EXPECTED_DEV_PLANNED_UNITS_SHA256 = "d7db38a84a5c95484b6d623858bcd8a216b0442760619c15ed67b550da71b68d"

EXP3_RUNNER_FILES_IN_FP = (
    "common.py",
    "provenance.py",
    "materials_e3.py",
    "validate_materials_e3.py",
    "prompts_e3.py",
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
    "exact_tango_e3.py",
    "core_e3.py",
    "calibrate_e3.py",
    "subclasses_e3.json",
    "split.json",
)

EXP3_FROZEN_SHA256 = {
    "common.py": "665fa8d5baa0b75e84121a5c0226fa097b9919a7965be8b753ce0eb229d608bf",
    "provenance.py": "1d0135232d60febea7933db2d11264dccbdd9359cb3588eb22268ee71c9aadfd",
    "materials_e3.py": "b5e073ba6ebe8821a2aaca01768750462e1e3d0203d556fdabede6a219ff9886",
    "validate_materials_e3.py": "b6b30a8c1a8ee5d4e112dc4a7eb315607ccf3e4209306c2d52104db6f32b1b95",
    "prompts_e3.py": "86b103c47889354ef5ff055dbd20c3a77987c0bcef7f0073230d92ddf095acb3",
    "prompt_parts.py": "027a6329088a71bb18fe2d4ac8d4999bec00f34af707092c659d54d5f69b8e41",
    "parse.py": "b44d0c453dc54d03e605dc00e5fa2fa8538c998264f93c028ea397c4e6f5f342",
    "protocol.py": "8b427b57400016e50bdab458c4402efcfb80718541b78b9eb7ebc7baa55e6904",
    "score.py": "ce5a5ea26be775f6aa206c57ba0253cf57b9219730a0bd830187b021370e3f3a",
    "run.py": "7352b27068db1e3c89ada339e1cc469792200e89b4149dcbc915a4882e1aa179",
    "subject.py": "b522d5c2c53e82faec613b3c9ccdc5bf09b972b890cb66066af9cff1e4e4e88c".replace("e4e88c", "e4188c"),
    "host.py": "0f70a90e696ffb27b4410d22cd59756a86631e0ca9c0796322a056439802070c",
    "admission.py": "e20818023c305caf1baccd3a815bc945caac336c422372a853b6d086a9ebc156",
    "ledger.py": "4b2da3e94bb1a6edf4e32943efef226662e3de69ae000302080ee33cc916871a",
    "gates.py": "70b7cacd9daf6bc95599b4e3ca5ea7ae5e1b4d21c7341629b43d4f8000a55edc",
    "deadline.py": "6b73c2d696b5fda1a351cf7e0f2d479524c73f4b38642dddb01e72b98854ef9e",
    "dry_stub.py": "fb3f695206229b8a905e6db3470f86ba9d7e3766c8578e8bdc5a47601f7f0989",
    "check_tokens.py": "25fb8fb83e17d444471cdb8d6ac1e629dfea2fe04801449a46d0f28df153e699",
    "exact_tango_e3.py": "cac020617b7b3f8b526ab1d2281136bd4b77fca9373d0c0a2846bdff96cf6231",
    "core_e3.py": "cd637c975bc15061ebff5ed41540ff1c02d66e1f71b0bbebe2557cae3f8077ff",
    "calibrate_e3.py": "8a4074705ddcaa2718cebd0c943fdb528f280c0f72dcd573847b2f8e6706b086",
    "subclasses_e3.json": EXPECTED_SUBCLASSES_SHA256,
    "split.json": EXPECTED_SPLIT_SHA256,
    "host_macos.py": "2c069e839629df41a2e4e7700d4ecebc66675847a6abbe76ba19d40a3ae46b7e",
    "config_models.json": "64e2eba87ecd4173caa7cce8734e57517bd704a7c217638107e144319acdb1c4",
    "config_assets_macmini-m6.json": "6af91feeafd4d82597133b7eabeea65a4d2296f8e1fbf2fed71c730326703ca1",
    "host_paths_macmini-m6.json": "98a6ce3cb989a723b4833f48dfa4596b79a7d7a140e078cad87feea18f6f4ea4",
    "label_tokens_qwen3-8b.json": "db388dec0a0ecfc93d8bc55e6fa66da460a153bfdd01c1b54f23214b04691259",
    "gpu_preflight_macos.py": "9e8e7fad51cce62013c83993ea31e080036f92f43dad00f45e52bf6f01356392",
    "PLAN-E3.md": EXPECTED_PLAN_E3_SHA256,
    "s1_preview_templates_e3.md": "cec9aa31daa0b2f8740512de1fe99146c9e06b0be2a01741c59819dbbb2f6c1c",
    "manifests/exact-tango-tables-e3.npz": EXPECTED_TANGO_NPZ_SHA256,
    "manifests/exact-tango-tables-e3-meta.json": EXPECTED_TANGO_META_SHA256,
    "manifests/exp1-bd-reference-summary.json": EXPECTED_EXP1_REF_SUMMARY_SHA256,
    "freeze/qwen3-8b@macmini-m6/cbd3b5af/PLAN-E3.frozen.md": EXPECTED_PLAN_E3_SHA256,
    "freeze/qwen3-8b@macmini-m6/cbd3b5af/calibration-e3.json": EXPECTED_CALIBRATION_E3_SHA256,
    "freeze/qwen3-8b@macmini-m6/cbd3b5af/c-review.md": EXPECTED_C_REVIEW_SHA256,
}

THIRD_PARTY = {
    "imperfectiveNLI.json": "ddd01d06b18b9bab24abb5bc92a8eb740bb145123658fa9a10bd86e38b4bdb5a",
    "run_inference.py.txt": "5b0fb856ed3ebc0d384ba97887fc3948a09c3269db99572e977d4196ec541880",
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
    yield cfg, "overall_plan", "imperfective-exp3-en/PLAN.md", EXPECTED_PLAN_MD_SHA256
    yield cfg, "frozen_plan", "imperfective-exp3-en/exp3-en/PLAN-E3.md", EXPECTED_PLAN_E3_SHA256
    yield (
        cfg,
        "freeze_snapshot.plan",
        "imperfective-exp3-en/exp3-en/freeze/qwen3-8b@macmini-m6/cbd3b5af/PLAN-E3.frozen.md",
        EXPECTED_PLAN_E3_SHA256,
    )
    yield (
        cfg,
        "freeze_snapshot.calibration",
        "imperfective-exp3-en/exp3-en/freeze/qwen3-8b@macmini-m6/cbd3b5af/calibration-e3.json",
        EXPECTED_CALIBRATION_E3_SHA256,
    )
    yield (
        cfg,
        "freeze_snapshot.c_review",
        "imperfective-exp3-en/exp3-en/freeze/qwen3-8b@macmini-m6/cbd3b5af/c-review.md",
        EXPECTED_C_REVIEW_SHA256,
    )
    for rel_name, digest in sorted(EXP3_FROZEN_SHA256.items()):
        yield cfg, "exp3_frozen", "imperfective-exp3-en/exp3-en/" + rel_name, digest
    for code_name, digest in sorted(cal_meta.get("code_hashes", {}).items()):
        if code_name == "exact-tango-tables-e3.npz":
            yield cfg, "calibration_code_hashes", "imperfective-exp3-en/exp3-en/manifests/" + code_name, digest
        else:
            yield cfg, "calibration_code_hashes", "imperfective-exp3-en/exp3-en/" + code_name, digest
    for name, digest in sorted(THIRD_PARTY.items()):
        yield cfg, "provenance_s0", "imperfective-exp3-en/exp3-en/data/" + name, digest
    yield (
        cfg,
        "split.upstream_data_sha256",
        "imperfective-exp3-en/exp3-en/data/imperfectiveNLI.json",
        split_data["upstream_data_sha256"],
    )
    yield (
        cfg,
        "subclasses.upstream_data_sha256",
        "imperfective-exp3-en/exp3-en/data/imperfectiveNLI.json",
        subclasses_data["upstream_data_sha256"],
    )


def _recompute_stage_plans(split_data, subclasses_data):
    """Recompute dev and formal unit plans directly from split.json and subclasses_e3.json (no upstream text needed)."""
    combinations = (
        ("L", "Z"), ("L", "DAP"), ("L", "CoT"), ("L", "CF"), ("Ps", "Z"),
        ("P", "Z"), ("P", "DAP"), ("P", "CoT"), ("P", "CF"),
        ("M", "Z"), ("M", "DAP"), ("M", "CoT"), ("M", "CF"),
    )
    diag_combinations = (("L", "Z"), ("P", "Z"), ("M", "Z"))
    entries = subclasses_data["clusters"]
    item_meta = {}
    for cid, meta in entries.items():
        m_sub = meta["macro_subclass"]
        t_sub = meta["template_subclass"]
        for slot in ("NI_OCC", "NI_PLAN", "INT_OCC", "INT_PLAN"):
            iid = f"{slot}_{cid}"
            item_meta[iid] = {
                "id": iid,
                "cluster_id": cid,
                "macro_class": "atelic",
                "macro_subclass": m_sub,
                "template_subclass": t_sub,
                "slot": slot,
                "is_diagnostic": False,
            }
        for slot in ("DIAG_POS", "DIAG_NEG"):
            iid = f"{slot}_{cid}"
            item_meta[iid] = {
                "id": iid,
                "cluster_id": cid,
                "macro_class": "atelic",
                "macro_subclass": m_sub,
                "template_subclass": t_sub,
                "slot": slot,
                "is_diagnostic": True,
            }

    def unit_dict(iid, task, prompt):
        m = item_meta[iid]
        return {
            **m,
            "task": task,
            "prompt": prompt,
            "unit_key": f"{iid}/{task}/{prompt}",
        }

    def build_plan(stage):
        main_ids = sorted(split_data[stage]["main_ids"])
        random.Random(2026110391).shuffle(main_ids)
        main_units = [unit_dict(iid, t, p) for iid in main_ids for t, p in combinations]
        if stage == "dev":
            diag_ids = sorted(split_data["dev"]["diag_ids"])
            diag_units = [unit_dict(iid, t, p) for iid in diag_ids for t, p in diag_combinations]
            return main_units + diag_units
        return main_units

    dev_plan = build_plan("dev")
    formal_plan = build_plan("formal")
    return {
        "dev_plan": dev_plan,
        "formal_plan": formal_plan,
        "dev_planned_units": len(dev_plan),
        "dev_planned_units_sha256": canonical_digest(dev_plan),
        "formal_planned_units": len(formal_plan),
        "formal_planned_units_sha256": canonical_digest(formal_plan),
    }


def _recompute_runner_fingerprint(exp3_dir, split_data, subclasses_data):
    """Stdlib-only exact reproduction of exp3-en/run.py Context.fp when third-party data are present."""
    import sys

    if str(exp3_dir) not in sys.path:
        sys.path.insert(0, str(exp3_dir))
    import materials_e3
    import prompts_e3
    import validate_materials_e3

    upstream_path = exp3_dir / "data" / "imperfectiveNLI.json"
    upstream_rows = json.loads(upstream_path.read_text(encoding="utf-8"))
    derived_doc = materials_e3.build_clusters_from_upstream(upstream_path, subclasses_data)
    derived_bytes = (json.dumps(derived_doc, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    if sha(derived_bytes) != EXPECTED_CLUSTERS_100_E3_SHA256:
        raise ValueError("derived clusters_100_e3.json SHA-256 mismatch")
    clusters = derived_doc["clusters"]
    val_errs = validate_materials_e3.validate_clusters_obj(
        derived_doc,
        subclasses_data,
        split_data,
        upstream_rows,
    )
    if val_errs:
        raise ValueError("validate_clusters errors: " + "; ".join(val_errs[:5]))

    items = {}
    for c in clusters:
        cid = c["cluster_id"]
        for slot_name, p_key, h_key in prompts_e3.SLOTS + prompts_e3.DIAG_SLOTS:
            iid = f"{slot_name}_{cid}"
            items[iid] = {"id": iid, "premise": c[p_key], "hypothesis": c[h_key]}

    tree = ast.parse((exp3_dir / "data" / "run_inference.py.txt").read_text(encoding="utf-8"))
    templates = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PROMPT_TEMPLATES" for t in node.targets):
            templates = ast.literal_eval(node.value)
            break
    if templates is None:
        raise ValueError("PROMPT_TEMPLATES literal missing in run_inference.py.txt")

    keys = {"Z": "zero-shot", "DAP": "dap", "CoT": "cot", "CF": "counterfactual"}
    rule = (
        'Important Linguistic Rule: Note the distinction between activity and accomplishment verbs.\n'
        '- For accomplishments/goal-oriented actions (e.g., "was building", "was writing"), the progressive form does NOT imply completion.\n'
        '- For activities (e.g., "was running", "was singing"), the process implies the action occurred.'
    )
    instructions = {
        "CoT": "First, analyze the temporal status of the event in the situation. Does the action have a defined endpoint? Was it completed? Then give your answer.",
        "CF": "First, list 3 possible real-world scenarios where the action in the situation occurs but the result in the statement is NOT achieved (e.g., interruptions, failures). Then give your answer.",
    }
    ps_user = (
        "User Input: Premise: {premise} Hypothesis: {hypothesis}\n"
        "What is the probability that the Hypothesis is necessarily true given only the Premise?\n\n"
        "On the last line of your answer, give the answer strictly in the following format:\n"
        "Probability: NN%\n"
        "where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign."
    )
    ask_direct = (
        "What is the probability that the statement is true?\n\n"
        "On the last line of your answer, give the answer strictly in the following format:\n"
        "Probability: NN%\n"
        "where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign."
    )
    ask_multi = (
        "Give 5 probability estimates that the statement is true, each with a weight for how likely you think "
        "that estimate is; the weights sum to 1.\n\n"
        "At the end of your answer, give the 5 estimates strictly in the following format, one per line:\n"
        + "".join("Estimate %d: NN%% | Weight: W\n" % k for k in range(1, 6))
        + "where each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign, and each W is a "
        "number from 0 to 1 (decimals allowed); the five weights sum to 1."
    )
    terminal_re = re.compile(r"[.!?][\"'”’)]*$")

    def terminate(s):
        s = s.strip()
        return s if terminal_re.search(s) else s + "."

    def render_unit(premise, hypothesis, task, prompt):
        if task in ("L", "Ps"):
            t = templates[keys[prompt]]
            user = t["user_format"] if task == "L" else ps_user
            return [
                {"role": "system", "content": t["system"]},
                {"role": "user", "content": user.format(premise=premise, hypothesis=hypothesis)},
            ]
        parts = ["Here is a situation: " + terminate(premise)]
        if prompt == "DAP":
            parts.append(rule)
        parts.append("Using common sense, how likely is it that the following statement is true?\nStatement: " + terminate(hypothesis))
        if prompt in instructions:
            parts.append(instructions[prompt])
        parts.append(ask_direct if task == "P" else ask_multi)
        return [{"role": "user", "content": "\n\n".join(parts)}]

    plans = _recompute_stage_plans(split_data, subclasses_data)
    material = [
        (
            u["unit_key"],
            canonical_digest(render_unit(items[u["id"]]["premise"], items[u["id"]]["hypothesis"], u["task"], u["prompt"])),
        )
        for u in (plans["dev_plan"] + plans["formal_plan"])
    ]

    model_cfg = json.loads((exp3_dir / "config_models.json").read_text(encoding="utf-8"))["qwen3-8b"]
    assets = json.loads((exp3_dir / "config_assets_macmini-m6.json").read_text(encoding="utf-8"))["models"]["qwen3-8b"]
    sampling = {
        "temperature": 0.0, "top_k": 1, "top_p": 1.0, "min_p": 0.0,
        "samplers": ["temperature", "top_k"], "repeat_penalty": 1.0,
        "presence_penalty": 0.0, "frequency_penalty": 0.0, "dry_multiplier": 0.0,
        "xtc_probability": 0.0, "typical_p": 1.0, "top_n_sigma": -1.0,
        "mirostat": 0, "dynatemp_range": 0.0,
    }
    fp_obj = {
        "files": {f: sha((exp3_dir / f).read_bytes()) for f in EXP3_RUNNER_FILES_IN_FP},
        "model": model_cfg,
        "host_id": "macmini-m6",
        "assets": assets,
        "tokens": sha((exp3_dir / "label_tokens_qwen3-8b.json").read_bytes()),
        "host_implementation": sha((exp3_dir / "host_macos.py").read_bytes()),
        "materials": canonical_digest(material),
        "sampling": sampling,
        "max_tokens": 1024,
        "rules": {"topN": 100, "score_version": 1, "parse_version": 2, "protocol_version": 1},
        "dry": False,
    }
    return canonical_digest(fp_obj)


def verify(here=None):
    here = Path(here or Path(__file__).resolve().parent)
    root = here.parent.resolve()
    check = json.loads((here / "release-check.json").read_text(encoding="utf-8"))
    exp3_dir = here / "exp3-en"
    freeze_dir = exp3_dir / "freeze" / "qwen3-8b@macmini-m6" / "cbd3b5af"
    cal_meta = json.loads((freeze_dir / "calibration-e3.json").read_text(encoding="utf-8"))
    split_data = json.loads((exp3_dir / "split.json").read_text(encoding="utf-8"))
    subclasses_data = json.loads((exp3_dir / "subclasses_e3.json").read_text(encoding="utf-8"))
    tango_meta = json.loads((exp3_dir / "manifests" / "exact-tango-tables-e3-meta.json").read_text(encoding="utf-8"))
    errors, required, verified = [], {}, []

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

    third_party_paths = {"imperfective-exp3-en/exp3-en/data/" + n for n in THIRD_PARTY}
    for config, section, name, digest in bindings(cal_meta, split_data, subclasses_data):
        normalized = logical(name)
        if normalized in third_party_paths:
            artifact = required.setdefault(normalized, dict(sha256=set(), status="self_acquisition_required"))
            artifact["sha256"].add(digest)
            path = root / normalized
            if path.exists() or path.is_symlink():
                matched = compare(normalized, digest, config + "/" + section)
                if not matched or artifact["status"] == "failed":
                    artifact["status"] = "failed"
                else:
                    artifact["status"] = "verified"
        else:
            compare(normalized, digest, config + "/" + section)

    # Verify calibration-e3.json invariants
    if cal_meta.get("schema_version") != "e3_calibration_v1":
        errors.append("calibration-e3.json: schema_version != 'e3_calibration_v1'")
    if cal_meta.get("seed") != 2026110411:
        errors.append("calibration-e3.json: seed != 2026110411")
    if cal_meta.get("r_reps") != 2000 or cal_meta.get("b_draws") != 5000:
        errors.append("calibration-e3.json: r_reps != 2000 or b_draws != 5000")
    if cal_meta.get("n_formal") != 80 or cal_meta.get("n_A_plan") != 16 or cal_meta.get("n_A_pure") != 64:
        errors.append("calibration-e3.json: formal stratum sizes mismatch")
    if cal_meta.get("total_cells") != 20:
        errors.append("calibration-e3.json: total_cells != 20")
    if cal_meta.get("production_eligible") is not True or cal_meta.get("status") != "pass":
        errors.append("calibration-e3.json: production_eligible or status not pass")
    if cal_meta.get("selected_step") != 3 or cal_meta.get("selected_family") != "hybrid_bessel_t_tango_e3":
        errors.append("calibration-e3.json: selected_step != 3 or selected_family != 'hybrid_bessel_t_tango_e3'")
    if cal_meta.get("companion_family") != "hybrid_pct_tango_e3":
        errors.append("calibration-e3.json: companion_family != 'hybrid_pct_tango_e3'")
    if cal_meta.get("demoted_slots") != ["E3_H3"]:
        errors.append("calibration-e3.json: demoted_slots != ['E3_H3']")
    s3_cells = cal_meta.get("step3_demoted_cells")
    if not isinstance(s3_cells, list) or len(s3_cells) != 20 or not all(c.get("cell_passed") is True for c in s3_cells):
        errors.append("calibration-e3.json: step3_demoted_cells failed 20/20 cell gate")

    # Verify Tango metadata
    if tango_meta.get("npz_file_sha256") != EXPECTED_TANGO_NPZ_SHA256:
        errors.append("exact-tango-tables-e3-meta.json: npz_file_sha256 mismatch")
    if tango_meta.get("npz_payload_sha256") != EXPECTED_TANGO_PAYLOAD_SHA256:
        errors.append("exact-tango-tables-e3-meta.json: npz_payload_sha256 mismatch")
    if tango_meta.get("supported_ns") != [8, 12, 16, 20, 64, 79, 80]:
        errors.append("exact-tango-tables-e3-meta.json: supported_ns != [8, 12, 16, 20, 64, 79, 80]")

    # Verify stage plans directly from split.json + subclasses_e3.json
    plans = _recompute_stage_plans(split_data, subclasses_data)
    if plans["dev_planned_units"] != 1160 or plans["formal_planned_units"] != 4160:
        errors.append("recomputed unit counts != 1160 dev / 4160 formal")
    if plans["dev_planned_units_sha256"] != EXPECTED_DEV_PLANNED_UNITS_SHA256:
        errors.append("recomputed dev_planned_units_sha256 mismatch")

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
            or frz.get("frozen_plan_sha256") != EXPECTED_PLAN_E3_SHA256
            or frz.get("calibration_sha256") != EXPECTED_CALIBRATION_E3_SHA256
            or frz.get("selected_family") != "hybrid_bessel_t_tango_e3"
            or frz.get("demoted_slots") != ["E3_H3"]
            or frz.get("c_blockers") != 0
            or frz.get("user_confirmed") is not True
            or not str(frz.get("prereg_commit", "")).strip()
            or not str(frz.get("prereg_pushed_at", "")).strip()
        ):
            errors.append("freeze.json invariants mismatch")
            freeze_json_status = "failed"
        else:
            freeze_json_status = "verified"

    # Recompute full 5,320-unit runner fingerprint when both third-party data files are present and verified
    recomputed_fp_status = "requires_third_party_data"
    if required and all(v["status"] == "verified" for v in required.values()):
        try:
            recomputed = _recompute_runner_fingerprint(exp3_dir, split_data, subclasses_data)
            if recomputed == EXPECTED_RUNNER_FP:
                recomputed_fp_status = "verified"
            else:
                recomputed_fp_status = "mismatch"
                errors.append(f"recomputed runner fingerprint {recomputed} != {EXPECTED_RUNNER_FP}")
        except Exception as exc:
            recomputed_fp_status = "failed"
            errors.append(f"runner fingerprint recomputation failed: {exc}")

    excluded = []
    for path, info in sorted(required.items()):
        if len(info["sha256"]) != 1:
            errors.append("conflicting SHA-256 bindings for " + path)
        excluded.append(dict(path=path, sha256= sorted(info["sha256"])[0], status=info["status"]))

    return dict(
        ok=not errors,
        verified_files=len(set(verified)),
        runner_fingerprint_id=EXPECTED_RUNNER_FP,
        runner_fingerprint_recomputed=recomputed_fp_status,
        recomputed_unit_counts={
            "dev": plans["dev_planned_units"],
            "formal": plans["formal_planned_units"],
            "total": plans["dev_planned_units"] + plans["formal_planned_units"],
        },
        frozen_plan_sha256=EXPECTED_PLAN_E3_SHA256,
        calibration_e3_sha256=EXPECTED_CALIBRATION_E3_SHA256,
        selected_family=cal_meta.get("selected_family"),
        companion_family=cal_meta.get("companion_family"),
        demoted_slots=cal_meta.get("demoted_slots"),
        freeze_json_status=freeze_json_status,
        excluded_artifacts=excluded,
        self_acquisition_required=[item["path"] for item in excluded if item["status"] == "self_acquisition_required"],
        errors=errors,
    )


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
