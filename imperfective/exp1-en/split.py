"""Frozen stratified paired split, PLAN section 2 / brief section 3."""
import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, write_json
from provenance import HASHES, load_items, verify_sources

SEED = 20261090
CLASSES = ("Change_of_State", "Creation", "Consumption", "Motion_to_Goal")


def make_split(items):
    by_id = {i["id"]: i for i in items}
    counts = Counter(i["verb_class"] for i in items if i["id"].startswith("A_"))
    floors = {c: 20 * counts[c] // 100 for c in CLASSES}
    order = sorted(CLASSES, key=lambda c: (-(20 * counts[c] % 100), CLASSES.index(c)))
    for c in order[:20 - sum(floors.values())]:
        floors[c] += 1
    if floors != dict(zip(CLASSES, (9, 8, 2, 1))):
        raise ValueError("STOP: split quotas disagree with PLAN")
    rng, telic = random.Random(SEED), []
    for c in CLASSES:
        ks = sorted(i["id"].split("_")[1] for i in items if i["id"].startswith("A_") and i["verb_class"] == c)
        rng.shuffle(ks)
        telic.extend(ks[:floors[c]])
    atelic = [f"{k:03d}" for k in range(1, 101)]
    rng.shuffle(atelic)
    atelic = atelic[:20]
    stages = {}
    for stage in ("dev", "formal"):
        t = sorted(k for k in (f"{n:03d}" for n in range(1, 101)) if (k in telic) == (stage == "dev"))
        a = sorted(k for k in (f"{n:03d}" for n in range(1, 101)) if (k in atelic) == (stage == "dev"))
        ids = sorted([f"{g}_{k}" for k in t for g in "AC"] + [f"{g}_{k}" for k in a for g in "BD"])
        stages[stage] = {"telic_clusters": t, "atelic_clusters": a, "ids": ids,
                         "telic_class_counts": dict(Counter(by_id[f"A_{k}"]["verb_class"] for k in t))}
    smoke = [min(i for i in stages["dev"]["ids"] if i.startswith(g + "_")) for g in "ABCD"]
    stages["smoke"] = {"ids": smoke, "telic_clusters": sorted({i[2:] for i in smoke if i[0] in "AC"}),
                       "atelic_clusters": sorted({i[2:] for i in smoke if i[0] in "BD"}),
                       "telic_class_counts": dict(Counter(by_id[i]["verb_class"] for i in smoke if i[0] == "A"))}
    return {"seed": SEED, "rule": "Paired clusters; largest remainders, fixed class tie order; sorted then shared RNG shuffle; smoke=min dev ID per group.",
            "data_sha256": HASHES["imperfectiveNLI.json"], "class_counts": dict(counts), "quotas": floors, **stages}


if __name__ == "__main__":
    verify_sources()
    result = make_split(load_items())
    write_json(ROOT / "split.json", result)
    print("SPLIT PASS: dev=80 formal=320 smoke=4; quotas=9/8/2/1")
