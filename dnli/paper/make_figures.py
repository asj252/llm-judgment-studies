"""Descriptive r0 figures; no model calls or confirmatory inference."""
from __future__ import annotations

import argparse
from collections import defaultdict
from fractions import Fraction
import importlib.util
import hashlib
import json
import math
import os
import shutil
from pathlib import Path
import subprocess
import sys
import tempfile
import textwrap
import uuid

import numpy as np

C_BG = "#F8F8F8"
C_GRID = "#D6D6D6"
C_AXIS = "#000000"
C_V1 = "#57068C"
C_V2 = "#006385"
C_WARN = "#FF5D47"
C_AUX = "#AB82C5"
B = 2000
SEED = 20261490
HERE = Path(__file__).resolve().parent
DATA = HERE.parent / "code"
OUT = HERE / "figures"
CONFIGS = ("qwen3-off", "olmo2", "codex")
AGY_DATA = DATA.parent / "agy-extension"
EXTENSION_CONFIGS = ("agy:gpt-oss-120b-medium", "agy:claude-sonnet-5-5-medium",
                     "agy:gemini-3.8-flash-low", "agy:gemini-3.8-flash-high")
LABELS = {"qwen3-off": "Qwen3（推理关）", "olmo2": "OLMo-2", "codex": "codex"}
PRESENTATIONS = {"stated": "陈述", "reported": "转述"}
ASKS = {"direct": "直接", "multi": "多估计"}
READINGS = {"mean": "加权平均", "top": "最高权重候选", "median": "加权中位数"}
CELLS = (("prior", "-"), ("stated", "S"), ("stated", "W"),
         ("reported", "S"), ("reported", "W"))
CELL_LABELS = ("先验", "陈述加强", "陈述削弱", "转述加强", "转述削弱")
EN_LABELS = {"qwen3-off": "Qwen3-8B (thinking off)", "olmo2": "OLMo-2-7B-Instruct",
             "codex": "codex (gpt-6.1-sol)",
             "agy:gpt-oss-120b-medium": "gpt-oss-120b\n(medium)",
             "agy:claude-sonnet-5-5-medium": "claude-sonnet-5.5\n(medium)",
             "agy:gemini-3.8-flash-low": "gemini-3.8-flash\n(low)",
             "agy:gemini-3.8-flash-high": "gemini-3.8-flash\n(high)"}
EN_ASKS = {"direct": "direct", "multi": "multi-estimate"}
EN_READINGS = {"mean": "weighted mean", "top": "top-weighted candidate", "median": "weighted median"}
EN_CELL_LABELS = ("prior", "stated strengthener", "stated weakener",
                  "reported strengthener", "reported weakener")
EN_NOTES = (
    "Descriptive 95% cluster-bootstrap intervals; each cell uses its own valid pairs. "
    "The dashed line at 5 points is the SESOI for H1 (stated × direct); thresholds for H2 and H4b "
    "apply to condition differences and cannot be read off this line.",
    "Descriptive 95% cluster-bootstrap intervals. Endpoint rates are unweighted proportions within "
    "each condition; multi-estimate uses the weighted-mean reported value. H4a in the text weights "
    "prior 1/2 and stated strengthener and weakener 1/4 each (OLMo-2 on the common complete set).",
    "Stated condition; common complete pairs; descriptive 95% cluster-bootstrap intervals.",
)


def load_records(config):
    records = {}
    root = AGY_DATA if config in EXTENSION_CONFIGS else DATA
    sessions = None
    if config in EXTENSION_CONFIGS:
        analysis = json.loads((root / "analysis_formal.json").read_text(encoding="utf-8"))
        fingerprint = analysis["filter"][config]["frozen_fingerprint"]
        meta = json.loads((root / f"run_meta_formal_{config.replace(':', '_')}.json").read_text(encoding="utf-8"))
        sessions = {s["session_id"]: s for s in meta["sessions"]
                    if s.get("closed_ok") and not s.get("invalid") and s.get("fingerprint_id") == fingerprint}
    with (root / f"results_formal_{config.replace(':', '_')}.jsonl").open(encoding="utf-8") as stream:
        for line in stream:
            row = json.loads(line)
            if sessions is not None:
                session = sessions.get(row.get("session_id"))
                if session is None or row.get("fingerprint_id") != fingerprint:
                    continue
                digest = hashlib.sha256(json.dumps(row, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
                if session.get("unit") != row.get("unit") or session.get("record_sha256") != digest:
                    raise ValueError(f"Extension checkpoint integrity: {row.get('unit')}")
            if row["round"] != "r0" or row["status"] != "ok":
                continue
            value = row["result"].get("value")
            if not isinstance(value, (int, float)) or not math.isfinite(value) or not 0 <= value <= 100:
                continue
            unit = (row["key"], row["pres"], row["utype"], row["ask"])
            if unit in records:
                raise ValueError(f"Duplicate r0 unit: {unit}")
            if "weights" in row["result"]:
                # Preserve original JSON decimal strings for exact median boundaries.
                row["result"]["weights"] = json.loads(line, parse_float=str)["result"]["weights"]
            records[unit] = row
    return records


def read_value(row, reading="mean"):
    result = row["result"]
    if reading == "mean":
        # Parser's normalized weighted mean, also used by H4b.
        return float(result["value"])
    estimates = np.asarray(result["estimates"], dtype=float)
    weights = np.asarray(result["weights"], dtype=float)
    if estimates.shape != weights.shape or not len(weights) or np.any(weights < 0) or weights.sum() <= 0:
        raise ValueError("Invalid candidate weights")
    if reading == "top":
        return float(estimates[weights == weights.max()].mean())
    if reading == "median":
        order = np.argsort(estimates, kind="stable")
        exact_weights = [Fraction(str(w)) for w in result["weights"]]
        total = sum(exact_weights)
        cumulative = Fraction(0)
        # Lower weighted median, comparing unnormalized decimal weights exactly.
        for index in order:
            cumulative += exact_weights[index]
            if 2 * cumulative >= total:
                return float(estimates[index])
    raise ValueError(reading)


def pair_movements(records, pres, ask, reading="mean"):
    pairs = {}
    for key in sorted({unit[0] for unit in records}):
        s = records.get((key, pres, "S", ask))
        w = records.get((key, pres, "W", ask))
        if s is None or w is None:
            continue
        if s["cluster"] != w["cluster"]:
            raise ValueError(f"Pair crosses clusters: {key}")
        pairs[key] = ((read_value(s, reading) - read_value(w, reading)) / 2, s["cluster"])
    return pairs


def paired_difference(records, pres="stated", reading="mean"):
    direct = pair_movements(records, pres, "direct")
    multi = pair_movements(records, pres, "multi", reading)
    samples = []
    for key in sorted(direct.keys() & multi.keys()):
        if direct[key][1] != multi[key][1]:
            raise ValueError(f"Ask conditions cross clusters: {key}")
        samples.append((multi[key][0] - direct[key][0], direct[key][1]))
    return samples


def order_interval(replicates):
    ordered = np.sort(replicates)
    k = math.floor(0.025 * len(ordered))
    if k < 1:
        raise ValueError("Too few bootstrap replicates")
    # Noninterpolated order statistics, zero-based indices 49 and 1949 at B=2000.
    return float(ordered[k - 1]), float(ordered[len(ordered) - k - 1])


def summarize(samples, rng, repeats=B):
    if not samples:
        raise ValueError("Empty analysis cell")
    grouped = defaultdict(list)
    for value, cluster in samples:
        grouped[cluster].append(value)
    clusters = sorted(grouped)
    sums = np.array([sum(grouped[c]) for c in clusters], dtype=float)
    counts = np.array([len(grouped[c]) for c in clusters], dtype=int)
    selected = rng.integers(0, len(clusters), size=(repeats, len(clusters)))
    replicates = sums[selected].sum(axis=1) / counts[selected].sum(axis=1)
    low, high = order_interval(replicates)
    return {"point": float(sum(v for v, _ in samples) / len(samples)),
            "low": low, "high": high, "n": len(samples), "clusters": len(clusters)}


def compute_data(include_extension=False):
    rng = np.random.default_rng(SEED)
    result = {"B": B, "seed": SEED, "fig1": [], "fig2": [], "fig3": [], "h4b": []}
    for config in CONFIGS:
        records = load_records(config)
        for pres in PRESENTATIONS:
            for ask in ASKS:
                pairs = pair_movements(records, pres, ask)
                result["fig1"].append(dict(config=config, pres=pres, ask=ask,
                                           **summarize(list(pairs.values()), rng)))
        for ask in ASKS:
            for pres, utype in CELLS:
                samples = [(float(read_value(row) <= 5 or read_value(row) >= 95), row["cluster"])
                           for unit, row in sorted(records.items())
                           if unit[1:] == (pres, utype, ask)]
                result["fig2"].append(dict(config=config, pres=pres, utype=utype, ask=ask,
                                           **summarize(samples, rng)))
        for reading in READINGS:
            result["fig3"].append(dict(config=config, reading=reading,
                                       **summarize(paired_difference(records, reading=reading), rng)))
        # Common complete pairs, not difference of independently filtered fig1 means.
        result["h4b"].append(dict(config=config,
                                  **summarize(paired_difference(records), rng)))
    if include_extension:
        analysis = json.loads((AGY_DATA / "analysis_formal.json").read_text(encoding="utf-8"))
        result["extension_source"] = "dnli-agy/analysis_formal.json"
        result["extension_pairs"] = analysis["n_planned"]
        for config in EXTENSION_CONFIGS:
            records = load_records(config)
            desc = analysis["descriptives"][config]
            for pres in PRESENTATIONS:
                for ask in ASKS:
                    row = summarize(list(pair_movements(records, pres, ask).values()), rng)
                    source = desc["conditions_all_available"][f"{pres}|{ask}|pooled"]
                    row["point"] = source["D_mean_pS_minus_pW"] / 2
                    result["fig1"].append(dict(config=config, pres=pres, ask=ask, **row))
            for ask in ASKS:
                for pres, utype in CELLS:
                    samples = [(float(read_value(row) <= 5 or read_value(row) >= 95), row["cluster"])
                               for unit, row in sorted(records.items()) if unit[1:] == (pres, utype, ask)]
                    row = summarize(samples, rng)
                    if pres == "prior":
                        row["point"] = desc["endpoints_all_available"][ask]["prior"]["rate"]
                    result["fig2"].append(dict(config=config, pres=pres, utype=utype, ask=ask, **row))
    return result


def plot_figures(data, output=OUT, overwrite=False, lang="zh"):
    # mkdir uses normal inherited Windows ACLs; mkdtemp's 0700 is inaccessible
    # in this workspace sandbox. Keep font cache outside the deliverable folder.
    temp_root = Path(tempfile.gettempdir()).resolve()
    config_dir = temp_root / f"dnli_mplconfig_{uuid.uuid4().hex}"
    config_dir.mkdir()
    previous = os.environ.get("MPLCONFIGDIR")
    os.environ["MPLCONFIGDIR"] = str(config_dir)
    try:
        _plot_figures(data, output, overwrite, lang)
    finally:
        if previous is None:
            os.environ.pop("MPLCONFIGDIR", None)
        else:
            os.environ["MPLCONFIGDIR"] = previous
        if config_dir.resolve().parent != temp_root:
            raise ValueError("Font cache path escaped system temporary directory")
        shutil.rmtree(config_dir)


def _plot_figures(data, output, overwrite, lang="zh"):
    if lang not in ("zh", "en"):
        raise ValueError(lang)
    english = lang == "en"
    labels = EN_LABELS if english else LABELS
    presentations = {p: p for p in PRESENTATIONS} if english else PRESENTATIONS
    asks = EN_ASKS if english else ASKS
    readings = EN_READINGS if english else READINGS
    cell_labels = EN_CELL_LABELS if english else CELL_LABELS
    extended = english and "extension_pairs" in data
    configs = CONFIGS + EXTENSION_CONFIGS if extended else CONFIGS
    extension_note = " Extensions use only 120 Block-A pairs; cross-configuration comparisons are descriptive." if extended else ""
    output.mkdir(parents=True, exist_ok=True)
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D
    from matplotlib import font_manager
    if not english and not any(f.name in ("Microsoft YaHei", "SimHei") for f in font_manager.fontManager.ttflist):
        raise RuntimeError("A requested Chinese font is required")
    plt.rcParams.update({"font.family": ["DejaVu Sans"] if english else ["Microsoft YaHei", "SimHei", "DejaVu Sans"],
                         "axes.unicode_minus": False, "figure.facecolor": C_BG,
                         "axes.facecolor": C_BG, "text.color": C_AXIS,
                         "axes.labelcolor": C_AXIS, "xtick.color": C_AXIS,
                         "ytick.color": C_AXIS, "axes.edgecolor": C_AXIS,
                         "font.size": 11, "pdf.fonttype": 42})

    def style(ax):
        ax.set_axisbelow(True)
        ax.grid(axis="y", color=C_GRID, linewidth=0.8, alpha=0.7)
        ax.spines[["top", "right"]].set_visible(False)

    def point(ax, x, row, color, marker="o", filled=True):
        # Draw intervals independently; never assume the point lies within the percentile interval.
        ax.vlines(x, row["low"], row["high"], color=color, linewidth=1.6)
        ax.plot([x - .025, x + .025], [row["low"]] * 2, color=color, linewidth=1.3)
        ax.plot([x - .025, x + .025], [row["high"]] * 2, color=color, linewidth=1.3)
        ax.plot(x, row["point"], marker=marker, ms=7, linestyle="none",
                color=color, markerfacecolor=color if filled else C_BG, markeredgewidth=1.6)

    def save(fig, name):
        for suffix in ("pdf", "png"):
            target = output / f"{name}.{suffix}"
            if target.exists() and not overwrite:
                raise FileExistsError(f"Refusing to overwrite: {target}")
            fig.savefig(target, dpi=300, facecolor=C_BG, bbox_inches="tight")
        plt.close(fig)

    fig, ax = plt.subplots(figsize=(13, 6.2) if extended else (9, 5.6), layout="constrained")
    style(ax)
    offsets = {("stated", "direct"): -.24, ("stated", "multi"): -.08,
               ("reported", "direct"): .08, ("reported", "multi"): .24}
    for row in data["fig1"]:
        point(ax, configs.index(row["config"]) + offsets[row["pres"], row["ask"]], row,
              C_V2 if row["ask"] == "direct" else C_V1,
              marker="o" if row["ask"] == "direct" else "s", filled=row["pres"] == "stated")
    for level in (0, 5):
        ax.axhline(level, color=C_WARN, linestyle="--", linewidth=1.1)
    if extended:
        ax.axvline(2.5, color=C_AXIS, linestyle=":", linewidth=1)
        ax.text(1, 1.02, "Original three", transform=ax.get_xaxis_transform(), ha="center")
        ax.text(4.5, 1.02, "Extension four (120 pairs each)", transform=ax.get_xaxis_transform(), ha="center")
    ax.set(xticks=range(len(configs)), xticklabels=[labels[c] for c in configs], xlim=(-.5, len(configs)-.5),
           ylabel="Directional movement s (percentage points)" if english else "方向化移动 s（百分点）",
           title="Directional movement\n" if extended else "Directional movement" if english else "图 1  方向化移动")
    if extended:
        ax.tick_params(axis="x", labelsize=9, labelrotation=15)
    handles = [Line2D([], [], marker="o" if a == "direct" else "s", linestyle="none",
                      color=C_V2 if a == "direct" else C_V1,
                      markerfacecolor=(C_V2 if a == "direct" else C_V1) if p == "stated" else C_BG,
                      label=f"{presentations[p]} · {asks[a]}") for p, a in offsets]
    ax.legend(handles=handles, ncol=2, loc="upper left", frameon=False)
    fig.supxlabel(textwrap.fill(EN_NOTES[0] + extension_note, 145 if extended else 110) if english else "描述性 95% 整簇 bootstrap 区间；各格使用本格有效对\n"
                  "虚线 5 点为 H1（陈述×直接）的最小有意义效应；\n"
                  "H2、H4b 的阈值作用于条件差，不能以各点相对此线判定", fontsize=10)
    save(fig, "fig1_movement")

    fig, axes = plt.subplots(2, 4, figsize=(14, 9.5), sharey=True, layout="constrained") if extended else plt.subplots(1, 3, figsize=(13.5, 5.2), sharey=True, layout="constrained")
    if extended:
        axes[0, 3].axis("off")
        axes[0, 3].text(.1, .5, "Original three (upper row)\n\nExtension four (lower row)\n120 Block-A pairs each", transform=axes[0, 3].transAxes, va="center")
        axes = list(axes[0, :3]) + list(axes[1, :])
    for config, ax in zip(configs, axes):
        style(ax)
        for ask in ASKS:
            rows = [next(r for r in data["fig2"] if (r["config"], r["ask"], r["pres"], r["utype"])
                         == (config, ask, p, u)) for p, u in CELLS]
            color = C_V2 if ask == "direct" else C_V1
            marker = "o" if ask == "direct" else "s"
            # Slight offsets keep coincident direct/multi intervals legible.
            xs = np.arange(5) + (-.045 if ask == "direct" else .045)
            ax.plot(xs, [r["point"] for r in rows], color=color, linewidth=1.4, label=asks[ask])
            for x, row in zip(xs, rows):
                point(ax, x, row, color, marker, filled=row["pres"] != "reported")
        ax.set(title=labels[config], ylim=(0, 1), xticks=range(5), xticklabels=cell_labels)
        ax.tick_params(axis="x", labelrotation=30, labelsize=10)
        ax.legend(frameon=False, loc="upper right")
    axes[0].set_ylabel("Endpoint rate" if english else "端点率")
    fig.suptitle("Endpoint rate (reported value ≤ 5 or ≥ 95)" if english else "图 2  端点率（报出值 ≤ 5 或 ≥ 95）")
    fig.supxlabel(textwrap.fill(EN_NOTES[1] + extension_note, 165) if english else "描述性 95% 整簇 bootstrap 区间；多估计使用加权平均报出值\n"
                  "端点率为各条件内的未加权比例；正文 H4a 按先验 1/2、陈述加强与削弱各 1/4 汇总\n"
                  "（OLMo-2 用共同完整子集）", fontsize=10)
    save(fig, "fig2_endpoints")

    fig, ax = plt.subplots(figsize=(9, 5.6), layout="constrained")
    style(ax)
    markers = {"mean": "o", "top": "s", "median": "D"}
    for row in data["fig3"]:
        offset = {"mean": -.19, "top": 0, "median": .19}[row["reading"]]
        point(ax, CONFIGS.index(row["config"]) + offset, row, C_V1, markers[row["reading"]])
    ax.axhline(0, color=C_WARN, linestyle="--", linewidth=1.1)
    ax.set(xticks=range(3), xticklabels=[labels[c] for c in CONFIGS], xlim=(-.5, 2.5),
           ylabel="s (multi-estimate reading) − s (direct), percentage points" if english else "多估计读数的 s − 直接问法的 s（百分点）",
           title="Three readings of multi-estimate responses (exploratory, not pre-specified)" if english else "图 3  多估计的三种读数（探索性，非预注册）")
    ax.legend(handles=[Line2D([], [], color=C_V1, marker=markers[r], linestyle="none", label=readings[r])
                       for r in READINGS], frameon=False, loc="lower right")
    fig.supxlabel(EN_NOTES[2] if english else "陈述条件；共同完整对；描述性 95% 整簇 bootstrap 区间", fontsize=10)
    save(fig, "fig3_readings")


def generate_figures(data, output=OUT, overwrite=False, lang="zh"):
    if importlib.util.find_spec("matplotlib") is not None:
        plot_figures(data, output, overwrite, lang)
    else:
        renderer = os.environ.get("DNLI_FIGURE_PYTHON", str(Path.home() / ".conda/envs/MM/python.exe"))
        if not Path(renderer).is_file():
            raise RuntimeError("matplotlib unavailable; set DNLI_FIGURE_PYTHON to a local Python with matplotlib")
        renderer_root = Path(renderer).resolve().parent
        env = os.environ.copy()
        env["PATH"] = os.pathsep.join([str(renderer_root), str(renderer_root / "Library/bin"),
                                       str(renderer_root / "Scripts"), env.get("PATH", "")])
        subprocess.run([renderer, "-X", "utf8", "-B", str(Path(__file__).resolve()),
                        "--render", "--output", str(output), "--lang", lang] + (["--overwrite"] if overwrite else []),
                       input=json.dumps(data, ensure_ascii=False),
                       encoding="utf-8", check=True, env=env)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--lang", choices=("zh", "en"), default="zh")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing figure and data files")
    args = parser.parse_args()
    if args.output is None:
        args.output = OUT / "en" if args.lang == "en" else OUT
    if args.render:
        plot_figures(json.load(sys.stdin), args.output, args.overwrite, args.lang)
    else:
        targets = [args.output / f"{name}.{ext}"
                   for name in ("fig1_movement", "fig2_endpoints", "fig3_readings")
                   for ext in ("pdf", "png")] + [args.output / "figure_data.json"]
        if not args.overwrite:
            for target in targets:
                if target.exists():
                    raise FileExistsError(target)
        data = compute_data(include_extension=args.lang == "en")
        generate_figures(data, args.output, args.overwrite, args.lang)
        target = args.output / "figure_data.json"
        target.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print("Created three PDF/PNG figure pairs and figure_data.json")


if __name__ == "__main__":
    main()
