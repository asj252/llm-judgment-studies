"""Deterministic stratified dev/formal split for Experiment 2 (100 Chinese clusters)."""
import hashlib
import json
import random
from pathlib import Path

HERE = Path(__file__).resolve().parent
DATA_FILE = HERE / "data" / "clusters_100_curated.json"
OUT_FILE = HERE / "split.json"

SPLIT_SEED = 2026110202

# Target dev quotas (20 clusters total: 12 Telic + 8 Atelic)
# Note: All 18 user-reviewed seed clusters (T_01..T_10, A_pure_01..04, A_plan_01..04)
# are placed in the 20-cluster development set (plus 1 sampled Creation and 1 sampled
# Change of State cluster) so that S1 preview, S3 diagnostic smoke, and S4 dev
# calibration never touch the 80 holdout formal clusters!
DEV_QUOTAS = {
    ("telic", "Creation"): 5,
    ("telic", "Change of State"): 4,
    ("telic", "Consumption"): 2,
    ("telic", "Motion to Goal"): 1,
    ("atelic", "Pure Unbounded Activity"): 4,
    ("atelic", "Goal-Prone / Planned Activity"): 4,
}

SEED_CLUSTER_IDS = {
    f"T_{i:02d}" for i in range(1, 11)
} | {
    f"A_pure_{i:02d}" for i in range(1, 5)
} | {
    f"A_plan_{i:02d}" for i in range(1, 5)
}


def build_split() -> dict:
    raw_bytes = DATA_FILE.read_bytes()
    data_sha256 = hashlib.sha256(raw_bytes).hexdigest()
    clusters = json.loads(raw_bytes.decode("utf-8"))
    assert len(clusters) == 100, f"Expected 100 clusters, got {len(clusters)}"

    by_stratum: dict[tuple[str, str], list[dict]] = {}
    for c in clusters:
        key = (c["macro_class"], c["subclass"])
        by_stratum.setdefault(key, []).append(c)

    rng = random.Random(SPLIT_SEED)
    dev_ids: list[str] = []
    formal_ids: list[str] = []
    strata_summary: dict[str, dict] = {}

    for key, quota in DEV_QUOTAS.items():
        items = sorted(by_stratum[key], key=lambda x: x["cluster_id"])
        seed_in_stratum = [x["cluster_id"] for x in items if x["cluster_id"] in SEED_CLUSTER_IDS]
        non_seed_in_stratum = [x["cluster_id"] for x in items if x["cluster_id"] not in SEED_CLUSTER_IDS]
        need_extra = quota - len(seed_in_stratum)
        assert need_extra >= 0
        shuffled = list(non_seed_in_stratum)
        rng.shuffle(shuffled)
        chosen_extra = sorted(shuffled[:need_extra])
        stratum_dev = sorted(seed_in_stratum + chosen_extra)
        stratum_formal = [x["cluster_id"] for x in items if x["cluster_id"] not in set(stratum_dev)]
        dev_ids.extend(stratum_dev)
        formal_ids.extend(stratum_formal)
        strata_summary[f"{key[0]}::{key[1]}"] = {
            "total": len(items),
            "dev": len(stratum_dev),
            "formal": len(stratum_formal),
            "dev_cluster_ids": stratum_dev,
        }

    assert len(dev_ids) == 20
    assert len(formal_ids) == 80
    assert set(dev_ids).isdisjoint(set(formal_ids))

    return {
        "schema_version": "exp2-zh-split-v1",
        "split_seed": SPLIT_SEED,
        "source_file": "data/clusters_100_curated.json",
        "source_sha256": data_sha256,
        "counts": {
            "total_clusters": 100,
            "dev_clusters": 20,
            "formal_clusters": 80,
            "dev_main_items": 80,
            "formal_main_items": 320,
            "dev_diagnostic_items": 40,
        },
        "strata": strata_summary,
        "dev_cluster_ids": dev_ids,
        "formal_cluster_ids": formal_ids,
    }


def main() -> int:
    split_obj = build_split()
    out_bytes = (json.dumps(split_obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    OUT_FILE.write_bytes(out_bytes)
    print(f"OK: wrote {OUT_FILE.name} (dev={len(split_obj['dev_cluster_ids'])}, formal={len(split_obj['formal_cluster_ids'])}).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
