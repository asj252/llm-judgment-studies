"""Exclusive addendum freeze, gated on a successful mechanical OpenAI probe."""
import sys
sys.dont_write_bytecode = True
import argparse
import json
from stimuli_p167 import HERE, UPSTREAM, COUNTS, build_slice, sha256, verify_upstream
import freeze_p167
from freeze_p167 import canonical_hash
from addendum_openai_p167 import ADDENDUM_CONFIGS, ensure_upstream_files

FREEZE = HERE / "analysis_freeze_p167_openai_addendum.json"
SCRIPTS = ("addendum_openai_p167.py", "analyze_p167_addendum.py", "freeze_p167_addendum.py", "test_p167_addendum.py")
PARENT_SHA = "4dcc71812bb3a4c893b4fe5433e65ad450f0fbbb4f438e0b7faba43d6ae34422"


def require_probe():
    summary = json.loads((HERE / "summary_probe12_addendum.json").read_text(encoding="utf-8"))["openai:gpt-4o-mini"]
    if not (summary["raw_recompute_verified"] is True and summary["gate_pass"] is True and summary["n_units"] == 12 and summary["n_first_pass_ok"] >= 11
            and summary["n_final_ok"] == summary["n_logprobs_aligned"] == 12
            and summary["n_target_positions_checked"] == 28 and summary["all_pm_exact_cardinality"] is True
            and summary["min_target_top_logprobs"] == summary["max_target_top_logprobs"] == 20):
        raise ValueError("OpenAI probe gate failed; cannot freeze")


def freeze_content():
    ensure_upstream_files()
    verify_upstream()
    freeze_p167.verify_freeze()
    if sha256(freeze_p167.FREEZE) != PARENT_SHA:
        raise ValueError("Parent freeze SHA-256 mismatch")
    return dict(schema_version=1, stage="dev", parent_freeze_file=freeze_p167.FREEZE.name,
        parent_freeze_sha256=PARENT_SHA, upstream=UPSTREAM,
        original_scripts={f: sha256(HERE/f) for f in freeze_p167.SCRIPTS + ("test_p167.py", "upstream_hashes.json")},
        addendum_scripts={f: sha256(HERE/f) for f in SCRIPTS + ("PLAN-addendum-openai-p167.md",)},
        addendum_configs=ADDENDUM_CONFIGS,
        slices={s: dict(count=COUNTS[s], sha256=canonical_hash(build_slice(s))) for s in COUNTS},
        statistics=dict(B=5000, seeds={"E2": 2026110302, "E3": 2026110402, "E4": 2026110602}, e3_demoted_slots=["E3_H3"]))


def verify_addendum_freeze():
    require_probe()
    if json.loads(FREEZE.read_text(encoding="utf-8")) != freeze_content():
        raise ValueError("Addendum freeze mismatch; do not silently refreeze")
    return True


def main():
    p = argparse.ArgumentParser(description=__doc__)
    group = p.add_mutually_exclusive_group()
    group.add_argument("--verify", action="store_true")
    group.add_argument("--create", action="store_true")
    args = p.parse_args()
    if args.verify or (FREEZE.exists() and not args.create):
        verify_addendum_freeze()
        print("PASS addendum freeze: parent, 30 upstream files, original/addendum scripts, configs, 360/240/400/1000 dev slices, B=5000, seeds")
    else:
        require_probe()
        content = freeze_content()
        with FREEZE.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(content, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
        print("Created pre-run addendum freeze:", FREEZE)


if __name__ == "__main__":
    main()
