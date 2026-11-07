from common import ROOT, read_json, sha256
from prompts_e4 import DIAG_SLOTS, SLOTS

SOURCES = {
    "clusters_100_e4.json": (
        ROOT / "data" / "clusters_100_e4.json",
        "f0a2de8192a1c7321e8903818920036b8dcce1b607644f4c3381a5d41768b3f3",
    ),
    "subclasses_e4.json": (
        ROOT / "subclasses_e4.json",
        "77b1874bba695c33197c8898afa23285186525ed20593f9e9407446fce754bc4",
    ),
    "split.json": (
        ROOT / "split.json",
        "1552968c6b597b37b18eb349ba81f0c08e0faa037d66bfcf468bb2a5d8055731",
    ),
    "exact-tango-tables-e4.npz": (
        ROOT / "manifests" / "exact-tango-tables-e4.npz",
        "e6378b3a1c85bf851ff623e906d50edb0572f2b282a3c66297483ef1a43ea3ff",
    ),
    "exact-tango-tables-e4-meta.json": (
        ROOT / "manifests" / "exact-tango-tables-e4-meta.json",
        "2ecabd0e9158dcc51b03dc1f46da6558602f364ce6fbd9744f2cb44fa83dd9e1",
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
    data = read_json(ROOT / "data" / "clusters_100_e4.json")
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
                "domain_subclass": c["domain_subclass"],
                "topic_label": c["topic_label"],
                "speaker": c["speaker"],
                "slot": slot_name,
                "is_diagnostic": False,
                "premise": c[p_key],
                "hypothesis": c[h_key],
                "local_mod": c["local_mod"],
                "global_mod": c["global_mod"],
            })
        for slot_name, p_key, h_key in DIAG_SLOTS:
            items.append({
                "id": f"{slot_name}_{cid}",
                "cluster_id": cid,
                "domain_subclass": c["domain_subclass"],
                "topic_label": c["topic_label"],
                "speaker": c["speaker"],
                "slot": slot_name,
                "is_diagnostic": True,
                "premise": c[p_key],
                "hypothesis": c[h_key],
                "local_mod": c["local_mod"],
                "global_mod": c["global_mod"],
            })
    return items
