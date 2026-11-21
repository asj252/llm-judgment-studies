"""Read-only, hash-checked upstream loading and deterministic dev slices."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
from functools import lru_cache

# Upstream imports must never create files in frozen directories.
sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
UPSTREAM = json.loads((HERE / "upstream_hashes.json").read_text(encoding="utf-8"))
COUNTS = {"slice_e1_e3": 360, "slice_e2": 240, "slice_e4": 400, "all": 1000}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def resolve_upstream(relpath):
    path = ROOT / relpath
    if path.exists():
        return path
    folder = str(relpath).split("/", 1)[0]
    if folder in ("exp2-zh", "exp3-en", "exp4-moore"):
        return ROOT.parent / ("imperfective-" + folder) / relpath
    return path


def verify_upstream():
    if len(UPSTREAM) != 30:
        raise ValueError("Expected exactly 30 upstream dependencies")
    for path, expected in UPSTREAM.items():
        if len(expected) != 64 or sha256(resolve_upstream(path)) != expected:
            raise ValueError(f"Upstream SHA-256 mismatch: {path}")
    return True


def read_json(path):
    return json.loads(resolve_upstream(path).read_text(encoding="utf-8"))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


@lru_cache(None)
def upstream_modules():
    verify_upstream()
    aliases = ("parse", "protocol", "prompt_parts", "common", "prompts_e3",
               "prompts_e4", "exact_tango_e2", "exact_tango_e3", "exact_tango_e4")
    saved = {n: sys.modules.get(n) for n in aliases}
    try:
        mods = {}
        for n in ("parse", "protocol", "prompt_parts"):
            mods[n] = _load(n, resolve_upstream("exp3-en/" + n + ".py"))
        _load("common", resolve_upstream("exp1-en/common.py"))
        for key, path in (("e1", "exp1-en/prompts.py"), ("e2", "exp2-zh/prompts_zh.py"),
                          ("e3", "exp3-en/prompts_e3.py"), ("e4", "exp4-moore/prompts_e4.py")):
            name = f"prompts_{key}" if key in ("e3", "e4") else f"_p167_{key}"
            mods[key] = _load(name, resolve_upstream(path))
        for e, folder in (("e2", "exp2-zh"), ("e3", "exp3-en"), ("e4", "exp4-moore")):
            mods["tango_" + e] = _load("exact_tango_" + e, resolve_upstream(f"{folder}/exact_tango_{e}.py"))
            mods["core_" + e] = _load("_p167_core_" + e, resolve_upstream(f"{folder}/core_{e}.py"))
        return mods
    finally:
        for n, value in saved.items():
            if value is None:
                sys.modules.pop(n, None)
            else:
                sys.modules[n] = value


def clusters_and_ids(exp):
    folder, data = {"E2": ("exp2-zh", "clusters_100_curated.json"),
                    "E3": ("exp3-en", "clusters_100_e3.json"),
                    "E4": ("exp4-moore", "clusters_100_e4.json")}[exp]
    clusters = read_json(f"{folder}/data/{data}")
    if isinstance(clusters, dict):
        clusters = clusters["clusters"]
    split = read_json(f"{folder}/split.json")
    ids = split["dev_cluster_ids"] if exp == "E2" else split["dev"]["cluster_ids"]
    return clusters, sorted(ids)


def build_slice(name):
    verify_upstream()
    if name == "all":
        return sum((build_slice(s) for s in ("slice_e1_e3", "slice_e2", "slice_e4")), [])
    exp = {"slice_e1_e3": "E3", "slice_e2": "E2", "slice_e4": "E4"}[name]
    mods = upstream_modules()
    renderer = mods[exp.lower()]
    clusters, ids = clusters_and_ids(exp)
    by_id = {c["cluster_id"]: c for c in clusters}
    conditions = {
        "E3": (("L", "Z"), ("L", "CoT"), ("P", "Z"), ("M", "Z")),
        "E2": (("L", "CoT"), ("P", "Z"), ("M", "Z")),
        "E4": (("L", "CoT"), ("P", "Z"), ("P", "CoT"), ("M", "Z"), ("M", "CF")),
    }[exp]
    out = []
    for cid in ids:
        c = by_id[cid]
        for slot, pkey, hkey in renderer.SLOTS:
            for task, prompt in conditions:
                engine_key = f"{cid}__{slot}/{task}/{prompt}"
                row = dict(unit_key=f"{exp}/{engine_key}", engine_unit_key=engine_key,
                           exp=exp, cluster_id=cid, slot=slot, task=task, prompt=prompt,
                           messages=renderer.render_unit(c[pkey], c[hkey], task, prompt))
                if exp == "E3":
                    row.update(subclass=c["template_subclass"], macro_subclass=c["macro_subclass"])
                elif exp == "E2":
                    row.update(macro_class=c["macro_class"], subclass=c["subclass"],
                               macro_group="T" if c["macro_class"] == "telic" else "A")
                else:
                    row["domain_subclass"] = c["domain_subclass"]
                out.append(row)
    if exp == "E3":
        items = {r["id"]: r for r in read_json("exp3-en/data/imperfectiveNLI.json")}
        ids = sorted(i for i in read_json("exp1-en/split.json")["dev"]["ids"] if i.startswith("C_"))
        for iid in ids:
            for task, prompt in (("P", "CoT"), ("M", "Z")):
                key = f"{iid}/{task}/{prompt}"
                out.append(dict(unit_key=f"E1/{key}", engine_unit_key=key, exp="E1",
                                cluster_id=iid.split("_")[1], slot="C", id=iid,
                                task=task, prompt=prompt,
                                messages=mods["e1"].render_unit(items[iid], task, prompt)))
    if len(out) != COUNTS[name] or len({r["unit_key"] for r in out}) != len(out):
        raise ValueError(f"Slice count/uniqueness failed: {name}")
    return out
