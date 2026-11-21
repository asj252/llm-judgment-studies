"""Create once or verify the P16.7 pre-run freeze. Never refresh implicitly."""
import sys
sys.dont_write_bytecode = True
import argparse
import hashlib
import json
from stimuli_p167 import HERE, ROOT, UPSTREAM, COUNTS, build_slice, sha256, verify_upstream

FREEZE = HERE / "analysis_freeze_p167.json"
SCRIPTS = ("configs_p167.py", "stimuli_p167.py", "api_adapter_p167.py",
           "run_p167_slice.py", "analyze_p167.py", "freeze_p167.py")


def canonical_hash(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def freeze_content():
    verify_upstream()
    return dict(schema_version=1, stage="dev", upstream=UPSTREAM,
                scripts={f: sha256(HERE / f) for f in SCRIPTS},
                support_files={f: sha256(HERE / f) for f in ("upstream_hashes.json", "test_p167.py")},
                slices={s: dict(count=COUNTS[s], sha256=canonical_hash(build_slice(s))) for s in COUNTS},
                statistics=dict(B=5000, seeds={"E2": 2026110302, "E3": 2026110402, "E4": 2026110602},
                                e3_demoted_slots=["E3_H3"]))


def verify_freeze():
    if json.loads(FREEZE.read_text(encoding="utf-8")) != freeze_content():
        raise ValueError("Freeze mismatch; do not run or silently refreeze")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if args.verify:
        verify_freeze()
        print("PASS freeze: 30 upstream files, 6 scripts, support files, slices 360/240/400/1000, B=5000, dev seeds, E3_H3 demotion")
    else:
        content = freeze_content()
        with FREEZE.open("x", encoding="utf-8", newline="\n") as handle:
            handle.write(json.dumps(content, ensure_ascii=False, indent=2) + "\n")
        print("Created pre-run freeze:", FREEZE)


if __name__ == "__main__":
    main()
