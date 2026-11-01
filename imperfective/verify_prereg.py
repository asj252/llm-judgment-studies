"""Offline byte and cryptographic binding verifier for imperfective Experiment 1.

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
EXPECTED_RUNNER_FP = "895f4e6f51ca3044800eff8ff098970af68f86f54ced061c79c6a5e9ef1900b2"
EXPECTED_PLAN_E1_SHA256 = "59aa81d09c30ecc04c5bdb5d5cf26c052a51a2d719f9767b9a8fa256a13fecd6"
EXPECTED_STEP5B_CODE_SHA256 = "4e7030de928ec5a7a9fe398c557795ccd4f34a1693c7cebda475a675386537b1"
EXPECTED_TANGO_NPZ_SHA256 = "090bfbb5a859238ad05100443b4727c61644e030fd2d5e05359c5d575f4c46bf"
EXPECTED_TANGO_PAYLOAD_SHA256 = "696ee99245213ad6e7c9fe13d45b1cd239a6e62462888bba86e54a50f82dd89a"
EXPECTED_SPLIT_SHA256 = "6821a3b3ad2378d51c683b8abc8a5b45d402b9997e3c8957bcda95cd0ef289b7"
EXPECTED_PROMPT_TEMPLATES_SHA256 = "6573fa60c8043f87dda67c616460afcfb60dd75759b4a1c7d6647dd3b614ae3b"

EXP1_RUNNER_FILES_IN_FP = (
    "common.py", "provenance.py", "split.py", "prompts.py", "prompt_parts.py",
    "parse.py", "protocol.py", "score.py", "run.py", "subject.py", "host.py",
    "admission.py", "ledger.py", "gates.py", "deadline.py", "dry_stub.py",
    "check_tokens.py", "split.json",
)

EXP1_FROZEN_SHA256 = {
    "common.py": "012ae4efd15aa2c338f93d994495cd3209bc032657e8178b4e37d52f1858e8de",
    "provenance.py": "6beed0b5791d234f36b20bfc989fea50361a9d1deb845998f60bdbf4013e10a8",
    "split.py": "6a7174420097a1bcb9e41dace3c3b8ac7787f8598b268a0b3f3d8fc97ec65c4b",
    "prompts.py": "f7cdd0fb5e9ec7979d9f6180943c6cc0ae1f1be1df92e6d77d1778a3a7818343",
    "prompt_parts.py": "027a6329088a71bb18fe2d4ac8d4999bec00f34af707092c659d54d5f69b8e41",
    "parse.py": "b44d0c453dc54d03e605dc00e5fa2fa8538c998264f93c028ea397c4e6f5f342",
    "protocol.py": "398669f4bdc20c15878d16520b5558e2de98d45c5584add05bde9aedb8efc61e",
    "score.py": "06a5d845c5a9878640d3562f7f85dc6e9fe8b81a96f9956d6dee96a16c5a6c5e",
    "run.py": "a4c5d3ccaa2fda541e8d48d571a134f295dc238765d80d4f149f84878ad182ef",
    "subject.py": "aed0e039b8594678f652680cdc1f0c061ed81f90cb9e368b88aaa69a98cfe339",
    "host.py": "f66209831b6fd3513269a07bde2b8dbcc0feac8c446868c62a3ce30eb460c147",
    "admission.py": "5e32b7091ee411fd6b46fc74f4f602c7826e262b06c1277e93c2a970f9ce5fd9",
    "ledger.py": "4b2da3e94bb1a6edf4e32943efef226662e3de69ae000302080ee33cc916871a",
    "gates.py": "2b3c57616a2d0135a8eda30fc9e8189a9931f964e54a37c4930ad3c36fe0c718",
    "deadline.py": "1c74b4fb02417719c54e3ce1ddd2341eebaba245f6063628be53e3a0c327e370",
    "dry_stub.py": "c0b7dae1c45bc32446713840ad406a24709fece7a9f127c09486c5e7b954660d",
    "check_tokens.py": "0f8cc6cf08f4942687d80265174ecf99ad371326365f6a59dffe22ff676bb2fe",
    "split.json": EXPECTED_SPLIT_SHA256,
    "host_macos.py": "ff6971a7443b31fcb452c54a93c7806170d6e6908725262503de506ac4d4880b",
    "config_models.json": "64e2eba87ecd4173caa7cce8734e57517bd704a7c217638107e144319acdb1c4",
    "config_assets_macmini-m6.json": "6af91feeafd4d82597133b7eabeea65a4d2296f8e1fbf2fed71c730326703ca1",
    "host_paths_macmini-m6.json": "98a6ce3cb989a723b4833f48dfa4596b79a7d7a140e078cad87feea18f6f4ea4",
    "label_tokens_qwen3-8b.json": "db388dec0a0ecfc93d8bc55e6fa66da460a153bfdd01c1b54f23214b04691259",
    "gpu_preflight_macos.py": "cd613ac6b1fe3b2158f3fb0fb90372452f2139cd998b70dc9c55b02372b06e73",
}

STEP5B_MODULES_SHA256 = {
    "inputs.py": "e0b741ba5cf9425384ea264d8df35125e69a0c2de6718b86cb24f90f8e72e1cf",
    "exact_tango.py": "ee77b072b9afbb2fa729186508e44bc2f689fc5542ca39b90e541dd03e77ce29",
    "core_a.py": "7186dc975a11ac5d6af54d0b336e03e3bff7a3a875d7a444e2d8e250542ecbe7",
    "dgp_a.py": "418398245f6c503fd19146ecc566084ceb155adbd8a5f93c0936b67d5df52832",
    "manifest_a.py": "bb8a3543185e4f94004752fba9106f988e4c92c830a1993fd6afeb1858c5bfef",
    "run_sim.py": "997df243297a1d038d299b6d03f61e9ce9997efbf944fbceec813662f4b17314",
    "summarize_sim.py": "601c248f0e11ed07dc4f83085bdf1d92696aeec04e2ed3a8fef6696ddad2159a",
    "formal_engine.py": "628fa960b06c9079af8eb64066f1a9150e54d451e94fbafc7cbd8c8f886b9b9e",
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


def bindings(exec_manifest, split_data):
    """Yield (config, section, logical_path, expected_sha256) for every frozen binding."""
    cfg = exec_manifest["config"]
    yield cfg, "frozen_plan", "imperfective/s5-mac-handoff-20261101/PLAN-E1.md", exec_manifest["expected_frozen_plan_sha256"]
    for ep_name, digest in sorted(exec_manifest["entrypoints"].items()):
        yield cfg, "entrypoints", "imperfective/s5-mac-handoff-20261101/" + ep_name, digest
    for rel_name, digest in sorted(EXP1_FROZEN_SHA256.items()):
        yield cfg, "exp1_runner", "imperfective/exp1-en/" + rel_name, digest
    yield cfg, "sealed_step5b.split", "imperfective/exp1-en/split.json", exec_manifest["sealed_step5b"]["split_sha256"]
    for mod_name, digest in sorted(STEP5B_MODULES_SHA256.items()):
        yield cfg, "sealed_step5b.module", "imperfective/scheme-a-hybrid-calibration-20261101/code/" + mod_name, digest
    yield (
        cfg,
        "sealed_step5b.tango_npz",
        "imperfective/scheme-a-hybrid-calibration-20261101/manifests/exact-tango-tables.npz",
        exec_manifest["sealed_step5b"]["exact_tango_tables_sha256"],
    )
    for name, digest in sorted(exec_manifest["upstream_data_sha256"].items()):
        yield cfg, "upstream_data_manifest", "imperfective/exp1-en/data/" + name, digest
    for name, digest in sorted(THIRD_PARTY.items()):
        yield cfg, "provenance_s0", "imperfective/exp1-en/data/" + name, digest
    yield cfg, "split_data_sha256", "imperfective/exp1-en/data/imperfectiveNLI.json", split_data["data_sha256"]


def _verify_verbatim_plan_templates(plan_text):
    fence_re = re.compile(r"^[ ]*(`{3,4})text\n(.*?)\n[ ]*\1$", re.M | re.S)
    blocks = [
        "\n".join(ln[7:] if ln.startswith("       ") else ln for ln in m.group(2).split("\n"))
        for m in fence_re.finditer(plan_text)
    ]
    if len(blocks) < 5:
        return None
    reconstructed = {
        "zero-shot": {"system": blocks[0], "user_format": blocks[1]},
        "dap": {"system": blocks[2], "user_format": blocks[1]},
        "cot": {"system": blocks[0], "user_format": blocks[3]},
        "counterfactual": {"system": blocks[0], "user_format": blocks[4]},
    }
    return canonical_digest(reconstructed)


def _recompute_runner_fingerprint(exp1_dir, split_data):
    """Stdlib-only exact reproduction of exp1-en/run.py Context.fp when third-party data are present."""
    items_raw = json.loads((exp1_dir / "data" / "imperfectiveNLI.json").read_text(encoding="utf-8"))
    items = {row["id"]: row for row in items_raw}
    tree = ast.parse((exp1_dir / "data" / "run_inference.py.txt").read_text(encoding="utf-8"))
    templates = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "PROMPT_TEMPLATES" for t in node.targets):
            templates = ast.literal_eval(node.value)
            break
    if templates is None:
        raise ValueError("PROMPT_TEMPLATES literal missing in run_inference.py.txt")

    combinations = (
        ("L", "Z"), ("L", "DAP"), ("L", "CoT"), ("L", "CF"), ("Ps", "Z"),
        ("P", "Z"), ("P", "DAP"), ("P", "CoT"), ("P", "CF"),
        ("M", "Z"), ("M", "DAP"), ("M", "CoT"), ("M", "CF"),
    )
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

    def render_unit(item, task, prompt):
        if task in ("L", "Ps"):
            t = templates[keys[prompt]]
            user = t["user_format"] if task == "L" else ps_user
            return [
                {"role": "system", "content": t["system"]},
                {"role": "user", "content": user.format(premise=item["premise"], hypothesis=item["hypothesis"])},
            ]
        parts = ["Here is a situation: " + terminate(item["premise"])]
        if prompt == "DAP":
            parts.append(rule)
        parts.append("Using common sense, how likely is it that the following statement is true?\nStatement: " + terminate(item["hypothesis"]))
        if prompt in instructions:
            parts.append(instructions[prompt])
        parts.append(ask_direct if task == "P" else ask_multi)
        return [{"role": "user", "content": "\n\n".join(parts)}]

    material = []
    for stage in ("dev", "formal"):
        ids = sorted(split_data[stage]["ids"])
        random.Random(20261091).shuffle(ids)
        for iid in ids:
            for task, prompt in combinations:
                material.append((f"{iid}/{task}/{prompt}", canonical_digest(render_unit(items[iid], task, prompt))))

    model_cfg = json.loads((exp1_dir / "config_models.json").read_text(encoding="utf-8"))["qwen3-8b"]
    assets = json.loads((exp1_dir / "config_assets_macmini-m6.json").read_text(encoding="utf-8"))["models"]["qwen3-8b"]
    sampling = {
        "temperature": 0.0, "top_k": 1, "top_p": 1.0, "min_p": 0.0,
        "samplers": ["temperature", "top_k"], "repeat_penalty": 1.0,
        "presence_penalty": 0.0, "frequency_penalty": 0.0, "dry_multiplier": 0.0,
        "xtc_probability": 0.0, "typical_p": 1.0, "top_n_sigma": -1.0,
        "mirostat": 0, "dynatemp_range": 0.0,
    }
    fp_obj = {
        "files": {f: sha((exp1_dir / f).read_bytes()) for f in EXP1_RUNNER_FILES_IN_FP},
        "model": model_cfg,
        "host_id": "macmini-m6",
        "assets": assets,
        "tokens": sha((exp1_dir / "label_tokens_qwen3-8b.json").read_bytes()),
        "host_implementation": sha((exp1_dir / "host_macos.py").read_bytes()),
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
    exec_manifest = json.loads((here / "s5-mac-handoff-20261101" / "s6-s7-execution-manifest.json").read_text(encoding="utf-8"))
    split_data = json.loads((here / "exp1-en" / "split.json").read_text(encoding="utf-8"))
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

    third_party_paths = {"imperfective/exp1-en/data/" + n for n in THIRD_PARTY}
    for config, section, name, digest in bindings(exec_manifest, split_data):
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

    # Verify execution manifest invariants and PLAN-E1.md embedded hashes & templates
    if exec_manifest.get("config") != EXPECTED_CONFIG:
        errors.append("execution manifest: config mismatch")
    if exec_manifest.get("expected_runner_fingerprint") != EXPECTED_RUNNER_FP:
        errors.append("execution manifest: expected_runner_fingerprint mismatch")
    if exec_manifest.get("expected_frozen_plan_sha256") != EXPECTED_PLAN_E1_SHA256:
        errors.append("execution manifest: expected_frozen_plan_sha256 mismatch")
    if exec_manifest.get("formal_bootstrap_b") != 5000:
        errors.append("execution manifest: formal_bootstrap_b != 5000")
    if exec_manifest.get("formal_analysis_seed") != 2026110201:
        errors.append("execution manifest: formal_analysis_seed != 2026110201")
    if exec_manifest.get("confirmatory_unit_index_input_allowed") is not False:
        errors.append("execution manifest: confirmatory_unit_index_input_allowed must be false")

    plan_e1_path = here / "s5-mac-handoff-20261101" / "PLAN-E1.md"
    if plan_e1_path.is_file():
        plan_txt = plan_e1_path.read_text(encoding="utf-8")
        for ep_name, ep_sha in exec_manifest.get("entrypoints", {}).items():
            if ep_sha not in plan_txt:
                errors.append("PLAN-E1.md missing embedded SHA-256 for " + ep_name)
        tpl_sha = _verify_verbatim_plan_templates(plan_txt)
        if tpl_sha != EXPECTED_PROMPT_TEMPLATES_SHA256 or exec_manifest.get("prompt_templates_canonical_sha256") != EXPECTED_PROMPT_TEMPLATES_SHA256:
            errors.append("PLAN-E1.md verbatim PROMPT_TEMPLATES canonical SHA-256 mismatch")

    # Verify combined Step 5b sealed code_sha256 and sealed-run-identity.json
    combo = hashlib.sha256()
    step5b_code_dir = here / "scheme-a-hybrid-calibration-20261101" / "code"
    all_mods_present = True
    for mod_name in STEP5B_MODULES_SHA256:
        mpath = step5b_code_dir / mod_name
        if not mpath.is_file():
            all_mods_present = False
            break
        combo.update(mod_name.encode("utf-8"))
        combo.update(b"\x00")
        combo.update(mpath.read_bytes())
        combo.update(b"\x00")
    if all_mods_present and combo.hexdigest() != EXPECTED_STEP5B_CODE_SHA256:
        errors.append("Step 5b combined code_sha256 mismatch")

    sealed_id_path = here / "scheme-a-hybrid-calibration-20261101" / "manifests" / "sealed-run-identity.json"
    if sealed_id_path.is_file():
        sealed_id = json.loads(sealed_id_path.read_text(encoding="utf-8"))
        if sealed_id.get("code_sha256") != EXPECTED_STEP5B_CODE_SHA256:
            errors.append("sealed-run-identity.json: code_sha256 mismatch")
        if sealed_id.get("exact_tango_tables_sha256") != EXPECTED_TANGO_NPZ_SHA256:
            errors.append("sealed-run-identity.json: exact_tango_tables_sha256 mismatch")
        if sealed_id.get("exact_tango_tables_payload_sha256") != EXPECTED_TANGO_PAYLOAD_SHA256:
            errors.append("sealed-run-identity.json: exact_tango_tables_payload_sha256 mismatch")

    # Recompute full 5,200-unit runner fingerprint when both third-party data files are present and verified
    fp_status = "requires_third_party_data"
    if required and all(v["status"] == "verified" for v in required.values()):
        try:
            recomputed_fp = _recompute_runner_fingerprint(here / "exp1-en", split_data)
            if recomputed_fp != EXPECTED_RUNNER_FP:
                errors.append(f"runner fingerprint_id mismatch: {recomputed_fp} != {EXPECTED_RUNNER_FP}")
                fp_status = "failed"
            else:
                fp_status = "verified"
        except Exception as exc:
            errors.append(f"runner fingerprint_id recomputation failed: {exc}")
            fp_status = "failed"

    artifacts = [
        dict(path=n, sha256=sorted(v["sha256"]), status=v["status"])
        for n, v in sorted(required.items())
    ]
    return dict(
        ok=not errors,
        public_files=len(check["files"]),
        verified_unique_files=len(set(verified)),
        runner_fingerprint_id=EXPECTED_RUNNER_FP,
        runner_fingerprint_recomputed=fp_status,
        frozen_plan_sha256=EXPECTED_PLAN_E1_SHA256,
        step5b_code_sha256=EXPECTED_STEP5B_CODE_SHA256,
        errors=errors,
        excluded_artifacts=artifacts,
        self_acquisition_required=[a for a in artifacts if a["status"] == "self_acquisition_required"],
        limitations=[
            "ok:true means all listed public file hashes, frozen runner/statistical-engine bindings, and verbatim prompt-template hashes passed; missing third-party data files are reported under self_acquisition_required.",
            "Full 5,200-unit materials and runner fingerprint_id recomputation runs automatically once imperfectiveNLI.json and run_inference.py.txt are placed under imperfective/exp1-en/data/ (see third-party-data.md).",
            "Model GGUF weights, llama-server binary, Hugging Face tokenizer cache, and S3/S4 Mac host admission ledgers are external attestations bound by SHA-256.",
            "release-check.json is an inventory, not a cryptographic timestamp; authenticate against the public preregistration commit on GitHub.",
        ],
    )


if __name__ == "__main__":
    result = verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result["ok"] else 1)
