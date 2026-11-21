"""Read-only public sealed-source, AutoTeX and main-table audit (stdlib only)."""
import sys
sys.dont_write_bytecode = True
import hashlib
from decimal import Decimal, ROUND_HALF_EVEN
import json
import re
import tarfile
from pathlib import Path
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]

def sha(data):
    return hashlib.sha256(data).hexdigest()

def load(path):
    return json.loads(path.read_text(encoding="utf-8"))

def require(ok, detail):
    if not ok:
        raise AssertionError(detail)

def pvalue(value):
    return f"{value:.5e}" if 0 < value < .0001 else f"{value:.4f}"

def fixed(value):
    return str(Decimal(str(round(value, 10))).quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))

def interval(values, scale=1):
    return "[" + ", ".join(fixed(v*scale) for v in values) + "]"

def table_rows(text, tex=False):
    rows = []
    for line in text.splitlines():
        if tex and " & " in line:
            line = line.removesuffix(r" \\")
            cells = line.split(" & ")
            cells = [v.replace(r"\_\allowbreak{}", "_").replace(r"\_", "_") for v in cells]
        elif not tex and line.startswith("| "):
            cells = line.strip("| ").split(" | ")
        else:
            continue
        rows.append([v.strip() for v in cells])
    return rows

def verify():
    checks = load(HERE / "source_checksums.json")
    dirs = ["dnli/v3-release", "imperfective/formal-results", "imperfective/p167-api"]
    dirs += [f"imperfective-exp{n}/formal-results" for n in ("2-zh", "3-en", "4-moore")]
    records = {k:v for d in dirs for k,v in load(ROOT/d/"manifest.json")["files"].items()}
    mapping = {v["source_relpath"]:k for k,v in records.items() if v["source_relpath"]}
    require(len(checks) == 21, "21 sealed sources required")
    sources = {}
    redacted = 0
    # Split forbidden tokens so this public validator itself has no private paths.
    forbidden = ["/home/"+"antigravity", "/"+"Users/", "/"+"Volumes/", "C:"+chr(92)+"Users"+chr(92),
                 ".gemini/"+"remote_cache", "patrol"+"_ctl", "jetski/"+"brain", "keys"+".env"]
    for src, digest in checks.items():
        dst = mapping[src]
        rec = records[dst]
        data = (ROOT/dst).read_bytes()
        require(not Path(src).is_absolute() and src.startswith("connecting-dots/"), src)
        require(rec["source_sha256"] == digest and sha(data) == rec["published_sha256"], src)
        if dst == "imperfective/formal-results/formal-analysis-results.json":
            require(rec["transform_id"] == "redact_abs_paths_opaque" and bool(rec["path_replacements"]), src)
            require(not any(v in data.decode("utf-8") for v in forbidden), "private path")
            redacted += 1
        else:
            require(sha(data) == digest, src)
        sources[Path(src).name] = json.loads(data)
    require(redacted == 1, "20 unchanged + 1 redacted sources required")
    manifest = load(HERE/"arxiv-submission/manifest_arxiv.json")
    expected = manifest["sources"]
    archive = HERE/"arxiv-submission/arxiv-source.tar.gz"
    require(sha(archive.read_bytes()) == manifest["archive"]["sha256"], "archive hash")
    require(archive.stat().st_size == manifest["archive"]["bytes"], "archive size")
    with tarfile.open(archive) as tf:
        members = tf.getmembers()
        require(len(members) == len(expected) == 7 and {m.name for m in members} == set(expected), "AutoTeX members")
        for m in members:
            require(m.isfile() and not Path(m.name).is_absolute() and ".." not in Path(m.name).parts, "unsafe archive member")
            data = tf.extractfile(m).read()
            require(data == (HERE/m.name).read_bytes(), m.name)
            require(sha(data) == expected[m.name]["sha256"] and len(data) == expected[m.name]["bytes"], m.name)
    texts = {n:(HERE/n).read_text(encoding="utf-8") for n in ("manuscript.md", "paper.tex")}
    tables = {n:table_rows(t, n.endswith(".tex")) for n,t in texts.items()}
    def row_check(label, numeric, offset, length):
        for name, rows in tables.items():
            require(any(r[0] == label and len(r) == length and r[offset:offset+len(numeric)] == numeric for r in rows), (name, label, numeric))
    # Main table: point bounds, primary and companion 98.75% CIs, raw/Holm p.
    e1 = sources["formal-analysis-results.json"]["confirmatory_claims_option_iii"]
    for i in range(4):
        primary = e1["primary_hybrid_pct_tango"][i]
        companion = e1["sensitivity_hybrid_bessel_t_tango"][i]
        scale = 100 if i in (0,3) else 1
        values = [fixed(primary["point_lower"]*scale) + ", " + fixed(primary["point_upper"]*scale),
                  interval(primary["ci_9875"],scale), interval(companion["ci_9875"],scale),
                  pvalue(primary["p_raw"]), pvalue(primary["p_holm"])]
        row_check(f"SA{i+1}", values, 2, 8)
    for e in (2,3,4):
        analysis = sources[f"e{e}_formal_analysis.json"]
        for h in (1,2,3,4):
            key = f"E{e}_H{h}"
            primary = analysis["primary_family"]["slots"][key]
            companion = analysis["companion_family"]["slots"][key]
            scale = 100 if h == 4 else 1
            label = key + (" (descriptive)" if (e,h) == (3,3) else "")
            values = [fixed(primary["point_lower"]*scale) + ", " + fixed(primary["point_upper"]*scale),
                      interval(primary.get("descriptive_ci_9875",primary["ci_9875"]),scale),
                      interval(companion.get("descriptive_ci_9875",companion["ci_9875"]),scale),
                      pvalue(primary.get("descriptive_p",primary["p"])), pvalue(primary["p_holm"] if "p_holm" in primary else primary["holm"]["p_holm"])]
            row_check(label, values, 2, 8)
    models = ["all_openai_gpt-4o-mini", "all_aistudio_gemma-4-31b-it", "all_nv_nemotron-3.5-bolt-e4b",
              "all_nv_nemotron-3.5-lightning-30b", "addendum_slice_e2_groq_gpt-oss-120b"]
    summaries = [sources[f"summary_p167_{m}.json"] for m in models]
    require(sum(s["collection_integrity"]["n_planned"] for s in summaries) == 4240, "P16.7 total")
    labels = ["OpenAI 4o-mini", "Gemma 31B", "Nemotron 4B", "Nemotron 30B", "Groq OSS 120B"]
    for label, summary, planned in zip(labels,summaries,[1000,1000,1000,1000,240]):
        c = summary["collection_integrity"]
        require(c["n_planned"] == planned, label)
        counts = c["status_counts"]
        row_check(label, [f'{counts["ok"]}/{planned}', f'{100*c["missing_rate"]:.2f} ({counts["missing_format"]}/{counts["missing_transport"]})'], 1, 3)
    # P16.7 main table: all five models' point bounds and Holm p, by slot.
    slots = 0
    for e in (2,3,4):
        for h in (1,2,3,4):
            if (e,h) == (3,3):
                continue
            key = f"E{e}_H{h}"
            values = []
            for summary in summaries:
                if f"E{e}" not in summary["engines"]:
                    values.append("uncollected")
                    continue
                slot = summary["engines"][f"E{e}"]["primary_family"]["slots"][key]
                scale = 100 if h == 4 else 1
                lo, hi = slot["point_lower"]*scale, slot["point_upper"]*scale
                point = fixed(lo) if lo == hi else interval([lo,hi])
                values.append(point + "; " + pvalue(slot["p_holm"] if "p_holm" in slot else slot["holm"]["p_holm"]))
                slots += 1
            row_check(key, values, 1, 6)
    for text in texts.values():
        require("4,240" in text or "4240" in text, "P16.7 manuscript total")
    print(json.dumps(dict(ok=True, sealed_unchanged=20, mapped_sources=21, autotex_members=7,
                          main_table_rows=16, p167_models=5, p167_units=4240, p167_slot_checks=slots), sort_keys=True))

if __name__ == "__main__":
    verify()
