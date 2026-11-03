"""S0: pinned data/source validation and item loader for Experiment 2 (Chinese)."""
from collections import Counter
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import ROOT, sha256, write_text
from prompts_zh import DIAG_SLOTS, SLOTS
from validate_materials import REQUIRED_KEYS, validate_clusters

HASHES = {
    "clusters_100_curated.json": "963636a2a74a38f8b8fe6363a079be38f5f2f1b35ef37f1cf3fc89dd7fd6c437",
    "seed_clusters_18.json": "6f31e854e1b34e01315bb8804bc0f70d93995d81cee6fc1e39264fe24ba92db5",
}
SPLIT_SHA256 = "6382d84a293107215ab034d565415adc8f0a438d90152f4c2b2e9a8d868c3973"
TANGO_NPZ_SHA256 = "2eb9bfd0db577301c44e5a49ad5ed1d4296b33031db7b54c78710e11043115a6"

EXPECTED_SUBCLASS_COUNTS = {
    ("telic", "Creation"): 26,
    ("telic", "Change of State"): 18,
    ("telic", "Consumption"): 10,
    ("telic", "Motion to Goal"): 6,
    ("atelic", "Pure Unbounded Activity"): 20,
    ("atelic", "Goal-Prone / Planned Activity"): 20,
}


def verify_sources(data_dir=ROOT / "data", root_dir=ROOT):
    data_dir = Path(data_dir)
    root_dir = Path(root_dir)
    for name, expected in HASHES.items():
        actual = sha256(data_dir / name)
        if actual != expected:
            raise ValueError(f"STOP: sha256 mismatch: {name}: {actual} != {expected}")
    split_actual = sha256(root_dir / "split.json")
    if split_actual != SPLIT_SHA256:
        raise ValueError(f"STOP: sha256 mismatch: split.json: {split_actual} != {SPLIT_SHA256}")
    tango_actual = sha256(root_dir / "manifests" / "exact-tango-tables-e2.npz")
    if tango_actual != TANGO_NPZ_SHA256:
        raise ValueError(f"STOP: sha256 mismatch: exact-tango-tables-e2.npz: {tango_actual} != {TANGO_NPZ_SHA256}")
    return {**HASHES, "split.json": split_actual, "exact-tango-tables-e2.npz": tango_actual}


def load_clusters(path=ROOT / "data" / "clusters_100_curated.json"):
    clusters = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(clusters, list) or len(clusters) != 100:
        raise ValueError("STOP: expected 100 clusters")
    for c in clusters:
        if not isinstance(c, dict) or set(c.keys()) != set(REQUIRED_KEYS):
            raise ValueError(f"STOP: invalid cluster keys: {c!r}")
    errors = validate_clusters(clusters)
    if errors:
        raise ValueError("STOP: cluster validation failed: " + "; ".join(errors[:5]))
    counts = Counter((c["macro_class"], c["subclass"]) for c in clusters)
    if dict(counts) != EXPECTED_SUBCLASS_COUNTS:
        raise ValueError(f"STOP: subclass counts mismatch: {dict(counts)}")
    return clusters


def load_items(path=ROOT / "data" / "clusters_100_curated.json"):
    clusters = load_clusters(path)
    items = []
    for c in clusters:
        cid = c["cluster_id"]
        for is_diag, slot_list in ((False, SLOTS), (True, DIAG_SLOTS)):
            for slot_name, p_key, h_key in slot_list:
                item_id = f"{cid}__{slot_name}"
                items.append({
                    "id": item_id,
                    "cluster_id": cid,
                    "macro_class": c["macro_class"],
                    "subclass": c["subclass"],
                    "vp_label": c["vp_label"],
                    "verb_root": c["verb_root"],
                    "comp_marker": c["comp_marker"],
                    "temporal_anchor": c["temporal_anchor"],
                    "agent": c["agent"],
                    "slot": slot_name,
                    "is_diagnostic": is_diag,
                    "premise": c[p_key],
                    "hypothesis": c[h_key],
                })
    if len(items) != 600:
        raise ValueError(f"STOP: expected 600 expanded items (400 main + 200 diagnostic), got {len(items)}")
    return items


def main():
    hashes = verify_sources()
    clusters = load_clusters()
    items = load_items()
    lines = [
        "# 实验 2（中文版）数据与来源核对（S0）",
        "",
        "## 1. 锁定资产 SHA-256",
    ]
    for name, val in hashes.items():
        lines.append(f"- `{name}`：`{val}`")
    lines.extend([
        "",
        "## 2. 簇与条目结构核验",
        f"- 事件簇总数：`{len(clusters)}`（终结类 `60` 簇：建造/创制 `26`、状态改变 `18`、消耗 `10`、趋向目标位移 `6`；非终结活动类 `40` 簇：纯无界活动 `20`、带常见计划活动 `20`）。",
        f"- 展开条目总数：`{len(items)}`（主实验题 `400` 条 + 诊断语境题 `200` 条）。",
        "- `validate_materials.py` 机械与形态校验：`100/100` 簇零错误通过。",
        "",
    ])
    write_text(ROOT / "data-provenance.md", "\n".join(lines))
    print(f"S0 PASS: hashes, cluster validation, subclass quotas; {len(clusters)} clusters, {len(items)} items")


if __name__ == "__main__":
    main()
