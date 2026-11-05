"""Deterministic material builder for Experiment 3 (English Atelic B/D Disambiguation).

Reads upstream `imperfectiveNLI.json` (CC BY-NC 4.0, gitignored in `data/`) and
tracked `subclasses_e3.json` + `split.json` (which contain zero verbatim text
from `imperfectiveNLI.json`), and deterministically constructs the 100 clusters
(`400` main items + `200` diagnostic items) in `data/clusters_100_e3.json`.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
UPSTREAM_SHA256 = "ddd01d06b18b9bab24abb5bc92a8eb740bb145123658fa9a10bd86e38b4bdb5a"
EXP1_SPLIT_SEED = 20261090

DEV_CLUSTER_IDS: tuple[str, ...] = (
    "011", "017", "025", "036", "037", "039", "046", "047", "048", "056",
    "064", "065", "073", "077", "078", "081", "082", "084", "085", "099",
)

A_PLAN_TASK_IDS: tuple[str, ...] = (
    "001", "004", "007", "013", "015", "016", "017", "021", "041", "042",
    "043", "045", "046", "058", "061", "062", "084", "085", "095", "099",
)

A_PLAN_DEG_IDS: tuple[str, ...] = (
    "077", "078", "079", "081",
)

SUBCLASS_MODIFIERS: dict[str, dict[str, str]] = {
    "A_plan_task": {
        "macro_subclass": "A_plan",
        "occ_mod": "for at least a short time",
        "plan_mod": "all the way to completion",
    },
    "A_plan_deg": {
        "macro_subclass": "A_plan",
        "occ_mod": "at least partially",
        "plan_mod": "completely",
    },
    "A_pure": {
        "macro_subclass": "A_pure",
        "occ_mod": "for at least a short time",
        "plan_mod": "throughout the entire period",
    },
}

ALL_MODIFIERS: tuple[str, ...] = (
    "for at least a short time",
    "all the way to completion",
    "at least partially",
    "completely",
    "throughout the entire period",
)


def sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def sha256_file(path: Path) -> str:
    return sha256_bytes(path.read_bytes())


def write_json_lf(path: Path, obj: Any) -> str:
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    raw = text.encode("utf-8")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    return sha256_bytes(raw)


def lower_clause_initial(sentence: str) -> str:
    if sentence.startswith(("I ", "Grandpa ")):
        return sentence
    return sentence[0].lower() + sentence[1:]


def build_subclasses_manifest() -> dict[str, Any]:
    all_ids = [f"{i:03d}" for i in range(1, 101)]
    clusters: dict[str, dict[str, str]] = {}
    for cid in all_ids:
        if cid in A_PLAN_DEG_IDS:
            tsub = "A_plan_deg"
        elif cid in A_PLAN_TASK_IDS:
            tsub = "A_plan_task"
        else:
            tsub = "A_pure"
        spec = SUBCLASS_MODIFIERS[tsub]
        clusters[cid] = {
            "template_subclass": tsub,
            "macro_subclass": spec["macro_subclass"],
            "occ_mod": spec["occ_mod"],
            "plan_mod": spec["plan_mod"],
            "stem_rule": "strip_all_day" if cid == "095" else "verbatim_h_orig",
        }
    return {
        "schema_version": "e3_subclasses_v1",
        "upstream_data_sha256": UPSTREAM_SHA256,
        "modifier_inventory": SUBCLASS_MODIFIERS,
        "counts": {
            "total": 100,
            "A_plan": len(A_PLAN_TASK_IDS) + len(A_PLAN_DEG_IDS),
            "A_plan_task": len(A_PLAN_TASK_IDS),
            "A_plan_deg": len(A_PLAN_DEG_IDS),
            "A_pure": 100 - len(A_PLAN_TASK_IDS) - len(A_PLAN_DEG_IDS),
        },
        "clusters": clusters,
    }


def build_clusters_from_upstream(
    upstream_path: Path | None = None,
    subclasses_manifest: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if upstream_path is None:
        upstream_path = HERE / "data" / "imperfectiveNLI.json"
    actual_sha = sha256_file(upstream_path)
    if actual_sha != UPSTREAM_SHA256:
        raise ValueError(
            f"Upstream imperfectiveNLI.json SHA-256 mismatch: expected {UPSTREAM_SHA256}, got {actual_sha}"
        )
    if subclasses_manifest is None:
        sub_path = HERE / "subclasses_e3.json"
        if sub_path.exists():
            subclasses_manifest = json.loads(sub_path.read_text(encoding="utf-8"))
        else:
            subclasses_manifest = build_subclasses_manifest()

    raw_items = json.loads(upstream_path.read_text(encoding="utf-8"))
    d_map = {x["id"].split("_")[1]: x for x in raw_items if x["id"].startswith("D_")}
    b_map = {x["id"].split("_")[1]: x for x in raw_items if x["id"].startswith("B_")}

    clusters_out: list[dict[str, Any]] = []
    for i in range(1, 101):
        cid = f"{i:03d}"
        d_item = d_map[cid]
        b_item = b_map[cid]
        c_spec = subclasses_manifest["clusters"][cid]
        tsub = c_spec["template_subclass"]
        msub = c_spec["macro_subclass"]
        occ_mod = c_spec["occ_mod"]
        plan_mod = c_spec["plan_mod"]

        p_no_int = d_item["premise"]
        p_int = b_item["premise"]
        h_orig = d_item["hypothesis"]
        if b_item["hypothesis"] != h_orig:
            raise ValueError(f"Cluster {cid} B/D hypothesis mismatch in upstream data")

        if cid == "095":
            if not h_orig.endswith(" all day."):
                raise ValueError(f"Cluster 095 expected ' all day.' suffix in {h_orig!r}")
            h_base = h_orig[:-1].removesuffix(" all day")
        else:
            h_base = h_orig[:-1]

        h_occ = f"{h_base} {occ_mod}."
        h_plan = f"{h_base} {plan_mod}."

        h_plan_clause = lower_clause_initial(h_plan)
        p_diag_pos = f"{p_no_int[:-1]}, and {h_plan_clause}"
        if tsub == "A_plan_deg":
            p_diag_neg = f"{p_no_int[:-1]}, but that ended early and did not happen {plan_mod}."
        else:
            p_diag_neg = f"{p_no_int[:-1]}, but that ended early and did not continue {plan_mod}."

        clusters_out.append({
            "cluster_id": cid,
            "macro_class": "atelic",
            "macro_subclass": msub,
            "template_subclass": tsub,
            "upstream_d_id": d_item["id"],
            "upstream_b_id": b_item["id"],
            "h_orig": h_orig,
            "h_base": h_base,
            "occ_mod": occ_mod,
            "plan_mod": plan_mod,
            "p_no_int": p_no_int,
            "p_int": p_int,
            "h_occ": h_occ,
            "h_plan": h_plan,
            "p_diag_pos": p_diag_pos,
            "p_diag_neg": p_diag_neg,
        })

    return {
        "schema_version": "e3_clusters_100_v1",
        "upstream_data_sha256": UPSTREAM_SHA256,
        "total_clusters": len(clusters_out),
        "clusters": clusters_out,
    }


def build_split_manifest(subclasses_manifest: dict[str, Any]) -> dict[str, Any]:
    all_ids = [f"{i:03d}" for i in range(1, 101)]
    dev_ids = sorted(DEV_CLUSTER_IDS)
    dev_set = set(dev_ids)
    formal_ids = [cid for cid in all_ids if cid not in dev_set]

    def expand_main_ids(cids: list[str]) -> list[str]:
        out: list[str] = []
        for slot in ("NI_OCC", "NI_PLAN", "INT_OCC", "INT_PLAN"):
            for cid in cids:
                out.append(f"{slot}_{cid}")
        return out

    def expand_diag_ids(cids: list[str]) -> list[str]:
        out: list[str] = []
        for dtype in ("DIAG_POS", "DIAG_NEG"):
            for cid in cids:
                out.append(f"{dtype}_{cid}")
        return out

    def count_by_key(cids: list[str], key: str) -> dict[str, int]:
        res: dict[str, int] = {}
        for cid in cids:
            v = subclasses_manifest["clusters"][cid][key]
            res[v] = res.get(v, 0) + 1
        return res

    smoke_clusters = ["011", "017", "077"]

    return {
        "schema_version": "e3_split_v1",
        "seed": EXP1_SPLIT_SEED,
        "rule": (
            "Exact preservation of Experiment 1 (exp1-en/split.json, seed=20261090) "
            "atelic_clusters partition (20 dev clusters, 80 formal clusters); "
            "smoke uses the minimum dev cluster_id from each template_subclass (011, 017, 077)."
        ),
        "upstream_data_sha256": UPSTREAM_SHA256,
        "macro_subclass_counts": {
            "total": count_by_key(all_ids, "macro_subclass"),
            "dev": count_by_key(dev_ids, "macro_subclass"),
            "formal": count_by_key(formal_ids, "macro_subclass"),
        },
        "template_subclass_counts": {
            "total": count_by_key(all_ids, "template_subclass"),
            "dev": count_by_key(dev_ids, "template_subclass"),
            "formal": count_by_key(formal_ids, "template_subclass"),
        },
        "smoke": {
            "cluster_ids": smoke_clusters,
            "main_ids": expand_main_ids(smoke_clusters),
            "diag_ids": expand_diag_ids(smoke_clusters),
        },
        "dev": {
            "cluster_ids": dev_ids,
            "A_plan_clusters": [c for c in dev_ids if subclasses_manifest["clusters"][c]["macro_subclass"] == "A_plan"],
            "A_pure_clusters": [c for c in dev_ids if subclasses_manifest["clusters"][c]["macro_subclass"] == "A_pure"],
            "main_ids": expand_main_ids(dev_ids),
            "diag_ids": expand_diag_ids(dev_ids),
        },
        "formal": {
            "cluster_ids": formal_ids,
            "A_plan_clusters": [c for c in formal_ids if subclasses_manifest["clusters"][c]["macro_subclass"] == "A_plan"],
            "A_pure_clusters": [c for c in formal_ids if subclasses_manifest["clusters"][c]["macro_subclass"] == "A_pure"],
            "main_ids": expand_main_ids(formal_ids),
        },
    }


def main() -> int:
    sub_manifest = build_subclasses_manifest()
    sub_sha = write_json_lf(HERE / "subclasses_e3.json", sub_manifest)
    split_manifest = build_split_manifest(sub_manifest)
    split_sha = write_json_lf(HERE / "split.json", split_manifest)
    clusters_obj = build_clusters_from_upstream(HERE / "data" / "imperfectiveNLI.json", sub_manifest)
    clusters_sha = write_json_lf(HERE / "data" / "clusters_100_e3.json", clusters_obj)
    print(f"subclasses_e3.json SHA-256: {sub_sha}")
    print(f"split.json SHA-256        : {split_sha}")
    print(f"clusters_100_e3.json SHA  : {clusters_sha}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
