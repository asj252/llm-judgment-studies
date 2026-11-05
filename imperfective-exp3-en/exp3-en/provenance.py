from common import ROOT, read_json, sha256
from prompts_e3 import DIAG_SLOTS, SLOTS

SOURCES = {
    "imperfectiveNLI.json": (
        ROOT / "data" / "imperfectiveNLI.json",
        "ddd01d06b18b9bab24abb5bc92a8eb740bb145123658fa9a10bd86e38b4bdb5a",
    ),
    "run_inference.py.txt": (
        ROOT / "data" / "run_inference.py.txt",
        "5b0fb856ed3ebc0d384ba97887fc3948a09c3269db99572e977d4196ec541880",
    ),
    "clusters_100_e3.json": (
        ROOT / "data" / "clusters_100_e3.json",
        "7f10a952c8ec32a4c978b69a0f755085fd76490d72d3706db8773b93d17da8aa",
    ),
    "subclasses_e3.json": (
        ROOT / "subclasses_e3.json",
        "ff3be2370261c499397fbfba9921086cb69467775d196e53bf6d83912c01721d",
    ),
    "split.json": (
        ROOT / "split.json",
        "cd0e099a38481b23c071d3950aac4527daf29aea12076f34ea9eadc4a90d7ea4",
    ),
    "exact-tango-tables-e3.npz": (
        ROOT / "manifests" / "exact-tango-tables-e3.npz",
        "59845e08a34c997c66b8d3c86244a87a7c5d8e6d018743c467bf37be4300828f",
    ),
    "exp1-bd-reference-summary.json": (
        ROOT / "manifests" / "exp1-bd-reference-summary.json",
        "739a91ede22b30d65a1dc41d38e681adc3a913ea01024bc4c53c0c89fa6dac5e",
    ),
}


def verify_sources():
    out = {}
    for name, (path, expected) in SOURCES.items():
        if not path.is_file():
            raise FileNotFoundError(f"missing source file: {path}")
        actual = sha256(path)
        if actual != expected:
            raise ValueError(f"{name} sha256 mismatch: {actual} != {expected}")
        out[name] = actual
    return out


def load_clusters():
    verify_sources()
    data = read_json(ROOT / "data" / "clusters_100_e3.json")
    return data["clusters"]


def load_items():
    clusters = load_clusters()
    items = []
    for c in clusters:
        cid = c["cluster_id"]
        for slot_name, p_key, h_key in SLOTS:
            items.append({
                "id": f"{slot_name}_{cid}",
                "cluster_id": cid,
                "macro_class": c["macro_class"],
                "macro_subclass": c["macro_subclass"],
                "template_subclass": c["template_subclass"],
                "slot": slot_name,
                "is_diagnostic": False,
                "premise": c[p_key],
                "hypothesis": c[h_key],
                "occ_mod": c["occ_mod"],
                "plan_mod": c["plan_mod"],
                "upstream_d_id": c["upstream_d_id"],
                "upstream_b_id": c["upstream_b_id"],
            })
        for slot_name, p_key, h_key in DIAG_SLOTS:
            items.append({
                "id": f"{slot_name}_{cid}",
                "cluster_id": cid,
                "macro_class": c["macro_class"],
                "macro_subclass": c["macro_subclass"],
                "template_subclass": c["template_subclass"],
                "slot": slot_name,
                "is_diagnostic": True,
                "premise": c[p_key],
                "hypothesis": c[h_key],
                "occ_mod": c["occ_mod"],
                "plan_mod": c["plan_mod"],
                "upstream_d_id": c["upstream_d_id"],
                "upstream_b_id": c["upstream_b_id"],
            })
    return items


def load_exp1_reference_records(stage: str | None = None):
    verify_sources()
    data = read_json(ROOT / "manifests" / "exp1-bd-reference-summary.json")
    if stage == "dev":
        return list(data["dev"])
    if stage == "formal":
        return list(data["formal"])
    return list(data["dev"]) + list(data["formal"])
