"""Exploratory spread analysis; local frozen data only, no model calls."""
from collections import Counter, defaultdict
import json
import math
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
CONFIGS = ("qwen3-off", "olmo2", "codex")
CELLS = (("prior", "-"), ("stated", "S"), ("stated", "W"),
         ("reported", "S"), ("reported", "W"))
B = 2000
SEED = 20261500
ATOL = 1e-9


def candidate_stats(result):
    """Population SD using normalized nonnegative weights; invalid is missing."""
    try:
        x = np.asarray(result["estimates"], dtype=float)
        w = np.asarray(result["weights"], dtype=float)
    except (KeyError, TypeError, ValueError):
        return None
    if (x.shape != (5,) or w.shape != (5,) or not np.isfinite(x).all()
            or not np.isfinite(w).all() or (w < 0).any()
            or (x < 0).any() or (x > 100).any()):
        return None
    total = float(w.sum())
    if not math.isfinite(total) or total <= 0:
        return None
    w = w / total
    mean = float(np.dot(w, x))
    # An anchor avoids tiny roundoff SD for identical candidates.
    centered = x - x[0]
    offset = float(np.dot(w, centered))
    sd = math.sqrt(float(np.dot(w, (centered - offset) ** 2)))
    # Exact endpoint support is missing for relative spread, including when
    # normalized-weight roundoff puts the dot product just inside an endpoint.
    support = x[w > 0]
    endpoint = bool(np.all(support == 0) or np.all(support == 100))
    r = None if endpoint else relative_spread(sd, mean)
    return dict(sd=sd, mean=mean, r=r, range=float(x.max() - x.min()),
                identical=bool(np.all(x == x[0])), weight_sum=total)


def relative_spread(sd, mean):
    """SD divided by the bounded-distribution maximum; endpoints are missing."""
    if mean <= 0 or mean >= 100:
        return None
    value = sd / math.sqrt(mean * (100 - mean))
    if value > 1 + ATOL:
        raise ValueError("Relative spread exceeds its bound")
    return min(value, 1.0)  # Only clip floating-point overshoot.


def load_records(config):
    records = {}
    audit = Counter(selected=0, valid=0, invalid=0, stored_sd_present=0,
                    stored_sd_match=0, stored_sd_mismatch=0, outside_tolerance=0)
    mismatches = []
    for line in (HERE / f"results_formal_{config}.jsonl").read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        if (row.get("round"), row.get("status"), row.get("ask")) != ("r0", "ok", "multi"):
            continue
        audit["selected"] += 1
        unit = (row["key"], row["pres"], row["utype"])
        if unit in records:
            raise ValueError(f"Duplicate unit: {unit}")
        stats = candidate_stats(row["result"])
        if stats is None:
            audit["invalid"] += 1
            continue
        audit["valid"] += 1
        audit["outside_tolerance"] += not 0.95 <= stats["weight_sum"] <= 1.05
        stored = row["result"].get("weighted_sd")
        if isinstance(stored, (int, float)) and math.isfinite(stored):
            audit["stored_sd_present"] += 1
            match = math.isclose(stored, stats["sd"], rel_tol=0, abs_tol=ATOL)
            audit["stored_sd_match" if match else "stored_sd_mismatch"] += 1
            if not match:
                mismatches.append(dict(unit=list(unit), stored=stored, recomputed=stats["sd"]))
        records[unit] = dict(stats, cluster=row["cluster"])
    audit["stored_sd_match_rate"] = (audit["stored_sd_match"] / audit["stored_sd_present"]
                                     if audit["stored_sd_present"] else None)
    return records, dict(audit), mismatches


def specs():
    result = {}
    for pres in ("stated", "reported"):
        for ut in ("S", "W"):
            result[f"change:{pres}:{ut}"] = (("prior", "-"), (pres, ut))
    for ut in ("S", "W"):
        result[f"reported_minus_stated:{ut}"] = (("stated", ut), ("reported", ut))
    result["reported_minus_stated:pooled"] = tuple((p, u) for u in ("S", "W")
                                                   for p in ("stated", "reported"))
    result["spearman"] = (("prior", "-"), ("stated", "S"), ("stated", "W"))
    return result


def contrast_samples(records, name, sensitivity=False, metric="sd"):
    """One contribution per pair; pooled contrast requires both update types."""
    needed = specs()[name]
    samples = []
    for key in sorted({u[0] for u in records}):
        rows = [records.get((key, *cell)) for cell in needed]
        if any(r is None for r in rows):
            continue
        if metric == "r" and any(r["r"] is None for r in rows):
            continue
        if sensitivity and any(not 0.95 <= r["weight_sum"] <= 1.05 for r in rows):
            continue
        clusters = {r["cluster"] for r in rows}
        if len(clusters) != 1:
            raise ValueError(f"Pair crosses clusters: {key}")
        if name == "spearman":
            value = (rows[0]["sd"], (rows[1]["mean"] - rows[2]["mean"]) / 2)
        elif name.endswith(":pooled"):
            value = ((rows[1][metric] - rows[0][metric]) + (rows[3][metric] - rows[2][metric])) / 2
        else:
            value = rows[1][metric] - rows[0][metric]
        samples.append((key, value, rows[0]["cluster"]))
    return samples


def ranks(values):
    values = np.asarray(values)
    order = np.argsort(values, kind="stable")
    out = np.empty(len(values), dtype=float)
    i = 0
    while i < len(order):
        j = i + 1
        while j < len(order) and values[order[j]] == values[order[i]]:
            j += 1
        out[order[i:j]] = (i + j - 1) / 2 + 1
        i = j
    return out


def spearman(values):
    if len(values) < 2:
        return None
    x, y = (ranks(v) for v in np.asarray(values).T)
    x, y = x - x.mean(), y - y.mean()
    denominator = math.sqrt(float(np.dot(x, x) * np.dot(y, y)))
    return float(np.dot(x, y) / denominator) if denominator else None


def order_interval(replicates):
    # Same order statistics as paper/make_figures.py (49, 1949 at B=2000).
    ordered = sorted(replicates)
    k = math.floor(0.025 * len(ordered))
    if k < 1:
        raise ValueError("Too few bootstrap replicates")
    return [float(ordered[k - 1]), float(ordered[len(ordered) - k - 1])]


def bootstrap_replicates(samples, rng, repeats=B, correlation=False):
    grouped = defaultdict(list)
    for _, value, cluster in samples:
        grouped[cluster].append(value)
    clusters = sorted(grouped)
    selected = rng.integers(0, len(clusters), size=(repeats, len(clusters)))
    if correlation:
        return [spearman([v for i in draw for v in grouped[clusters[i]]]) for draw in selected]
    sums = np.array([sum(grouped[c]) for c in clusters])
    counts = np.array([len(grouped[c]) for c in clusters])
    return (sums[selected].sum(axis=1) / counts[selected].sum(axis=1)).tolist()


def summarize(samples, rng, correlation=False):
    result = dict(n=len(samples), clusters=len({s[2] for s in samples}),
                  point=None, ci95=None, undefined_bootstrap=0)
    if not samples:
        return result
    result["point"] = (spearman([s[1] for s in samples]) if correlation
                       else float(np.mean([s[1] for s in samples])))
    reps = bootstrap_replicates(samples, rng, correlation=correlation)
    result["undefined_bootstrap"] = sum(v is None for v in reps)
    # Do not silently condition the interval on nondegenerate resamples.
    if not result["undefined_bootstrap"]:
        result["ci95"] = order_interval(reps)
    return result


def compute():
    rng = np.random.default_rng(SEED)
    output = dict(exploratory=True, preregistered=False, post_results=True,
                  B=B, seed=SEED, stored_sd_absolute_tolerance=ATOL, configs={})
    for config in CONFIGS:
        records, audit, mismatches = load_records(config)
        data = dict(audit=audit, sd_mismatches=mismatches, contrasts={}, sensitivity={}, cells={})
        for name in specs():
            data["contrasts"][name] = summarize(contrast_samples(records, name), rng, name == "spearman")
            if name != "spearman":
                data["sensitivity"][name] = summarize(contrast_samples(records, name, True), rng)
        for pres, ut in CELLS:
            rows = [(unit, row) for unit, row in sorted(records.items()) if unit[1:] == (pres, ut)]
            cell = {}
            for metric in ("sd", "range", "identical", "sd_zero"):
                cell[metric] = summarize([(u[0], float(r["sd"] == 0) if metric == "sd_zero" else float(r[metric]), r["cluster"]) for u, r in rows], rng)
            cell["all_equal_count"] = sum(r["identical"] for _, r in rows)
            cell["sd_zero_count"] = sum(r["sd"] == 0 for _, r in rows)
            cell["zero_sd_but_not_identical"] = sum(r["sd"] == 0 and not r["identical"] for _, r in rows)
            data["cells"][f"{pres}:{ut}"] = cell
        output["configs"][config] = data
    output["step2"] = compute_relative()
    return output


def relative_descriptions(records):
    """Cell means and ten equal-width m bins; no bootstrap for descriptions."""
    cells = {}
    for pres, ut in CELLS:
        rows = [r for u, r in records.items() if u[1:] == (pres, ut)]
        valid_r = [r["r"] for r in rows if r["r"] is not None]
        bins = []
        for lower in range(0, 100, 10):
            selected = [r for r in rows if lower <= r["mean"] < lower + 10
                        or (lower == 90 and r["mean"] == 100)]
            bins.append(dict(lower=lower, upper=lower + 10,
                             upper_inclusive=lower == 90, n=len(selected),
                             mean_sd=float(np.mean([r["sd"] for r in selected])) if selected else None))
        cells[f"{pres}:{ut}"] = dict(
            n=len(rows), mean_m=float(np.mean([r["mean"] for r in rows])) if rows else None,
            mean_r=float(np.mean(valid_r)) if valid_r else None,
            r_valid=len(valid_r), r_missing=len(rows) - len(valid_r), sd_by_m_bin=bins)
    return cells


def compute_relative():
    # A separate seeded stream leaves every first-step result unchanged.
    rng = np.random.default_rng(SEED)
    output = dict(metric="r = SD / sqrt(m * (100 - m))", B=B, seed=SEED, configs={})
    for config in CONFIGS:
        records, audit, _ = load_records(config)
        cells = relative_descriptions(records)
        data = dict(contrasts={}, sensitivity={}, cells=cells,
                    audit=dict(selected=audit["selected"], invalid_candidates=audit["invalid"],
                               r_valid=sum(c["r_valid"] for c in cells.values()),
                               r_missing_endpoints=sum(c["r_missing"] for c in cells.values())))
        for name in specs():
            if name == "spearman":
                continue
            data["contrasts"][name] = summarize(contrast_samples(records, name, metric="r"), rng)
            data["sensitivity"][name] = summarize(contrast_samples(records, name, True, metric="r"), rng)
        output["configs"][config] = data
    return output


LABELS = {"prior:-": "先验", "stated:S": "陈述加强", "stated:W": "陈述削弱",
          "reported:S": "转述加强", "reported:W": "转述削弱"}


def contrast_label(name):
    if name == "spearman":
        return "先验 SD 与陈述方向化移动的 Spearman ρ"
    if name.startswith("change:"):
        return LABELS[name.split(":", 1)[1]] + "：后验减先验 SD"
    return "转述减陈述后验 SD（" + {"S": "加强", "W": "削弱", "pooled": "两类型平均"}[name.split(":")[-1]] + "）"


def fmt(value):
    return "不可计算" if value is None else f"{value:.4f}"


def interval(summary):
    return "不可计算" if summary["ci95"] is None else "[" + ", ".join(fmt(v) for v in summary["ci95"]) + "]"


def report(output):
    lines = ["探索性，非预注册，看过正式结果后才定。", "", "# 多估计候选离散程度", "",
             "只使用三份正式结果中 round=r0、status=ok、ask=multi 的记录，不调用模型。"
             "本分析不进入 Holm 校正，也不改动确认性结果。", "",
             "每个单元先归一化五个非负候选权重，再计算总体加权 SD 和加权均值；"
             "总权重不为正、非有限数值、候选不在 0–100 或数组不满足五项时视为缺失。"
             "全距为五个候选的最大值减最小值，包含零权重候选。全同按五个候选数值完全相同计；"
             "另报 SD=0 比例并核对其中是否包含非全同候选；零权重候选可以造成两者不等价。SD 与全距单位均为概率点。", "",
             "每项只保留所需格均有效的情境—假设对，各对等权。两类型合并先在每对内平均加强、削弱差值，"
             "要求四个后验格均有效。相关使用先验 SD 与陈述方向化移动 s̄=(加强加权均值−削弱加权均值)/2，"
             "要求先验及陈述两后验格；Spearman 对并列值用平均秩。", "",
             f"区间为整簇 bootstrap（cluster），B={B:,}，种子 {SEED}；每次抽取与原样本相同数量的簇，"
             "保留所抽簇全部有效对，重复抽中的簇按重数计入，再计算对等权统计量。"
             "95% 区间采用排序后第 50、1950 项（从 1 起计），与 paper/make_figures.py 一致，不插值。"
             "相关每次重算秩；若重抽样产生未定义相关，则不报告该相关区间，并列出次数。", "",
             "## 数据与重算核对", "", "| 配置 | 筛选单元 | 有效单元 | 缺失单元 | 原 SD 有效 | SD 一致数 | 一致率 | 权重和范围外 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for config, data in output["configs"].items():
        a = data["audit"]
        lines.append(f'| {config} | {a["selected"]} | {a["valid"]} | {a["invalid"]} | {a["stored_sd_present"]} | {a["stored_sd_match"]} | {a["stored_sd_match_rate"]:.2%} | {a["outside_tolerance"]} ({a["outside_tolerance"]/a["valid"]:.2%}) |')
    lines += ["", "一致采用绝对误差 ≤ 1e-9；所有结果以重算 SD 为准。不一致单元明细保存在 JSON 的 sd_mismatches。", ""]
    for section, title in (("contrasts", "主要探索性对比"), ("sensitivity", "权重和敏感度分析")):
        lines += ["## " + title, ""]
        if section == "sensitivity":
            lines += ["仅保留该项对比所需每个单元原始权重和均落在 [0.95, 1.05] 的对；表中报告剩余对数。", ""]
        lines += ["| 配置 | 对比 | 均值／ρ | 95% 区间 | 对数 | 簇数 | 未定义重抽样 |", "|---|---|---:|---|---:|---:|---:|"]
        for config, data in output["configs"].items():
            for name, s in data[section].items():
                lines.append(f'| {config} | {contrast_label(name)} | {fmt(s["point"])} | {interval(s)} | {s["n"]} | {s["clusters"]} | {s["undefined_bootstrap"]} |')
        lines.append("")
    lines += ["## 各格离散程度与全同比例", "", "每格使用自身有效单元，比例不按候选权重加权；括号内为相应 95% 整簇区间。", "",
              "| 配置 | 格 | 单元数 | 平均 SD（区间） | 平均全距（区间） | 五候选全同（区间） | SD=0 比例（区间） | SD=0 但非全同数 |",
              "|---|---|---:|---|---|---|---:|---:|"]
    for config, data in output["configs"].items():
        for cell, d in data["cells"].items():
            s, r, z = d["sd"], d["range"], d["identical"]
            lines.append(f'| {config} | {LABELS[cell]} | {s["n"]} | {fmt(s["point"])} {interval(s)} | {fmt(r["point"])} {interval(r)} | {d["all_equal_count"]}/{z["n"]} = {z["point"]:.2%} {interval(z)} | {d["sd_zero_count"]}/{s["n"]} = {d["sd_zero"]["point"]:.2%} {interval(d["sd_zero"])} | {d["zero_sd_but_not_identical"]} |')
    lines += ["", "OLMo-2 的权重和范围外单元占 74.44%；敏感度分析四格更新前后对比分别仅余 27、19、14、13 对，转述减陈述加强、削弱分别余 32、18 对，两类型合并仅余 3 对。", "", "## 方向与大小", ""]
    for config, data in output["configs"].items():
        changes = [s["point"] for n, s in data["contrasts"].items() if n.startswith("change:")]
        pooled = data["contrasts"]["reported_minus_stated:pooled"]
        direction = "更分散" if pooled["point"] > 0 else "更集中" if pooled["point"] < 0 else "相同"
        lines.append(f'{config}：四格后验减先验的平均 SD 差落在 {min(changes):.4f} 至 {max(changes):.4f} 点；'
                     f'转述减陈述的两类型平均差为 {pooled["point"]:.4f} 点（点值方向为候选{direction}），区间 {interval(pooled)}。')
        lines.append("")
    lines += ["负的后验减先验差表示更新后候选更集中，正值表示更分散。"
              "上述结果只描述候选分布；相关为描述性关系，不能解释因果或机制。"
              "权重和筛选改变可用对的组成，敏感度结果应结合剩余对数阅读。", ""]
    return "\n".join(lines)


def report_relative(output):
    lines = ["", "## 第二步：按均值位置归一化的相对离散", "",
             "探索性，非预注册，看过正式结果后才定。相对离散 r = SD / √(m(100−m))，"
             "m 为该单元候选的归一权重加权均值；r 无量纲，范围为 0–1。"
             "m 为 0 或 100 时 r 记缺失；这不同于候选数据本身无效。"
             "该归一化按给定均值下的 SD 上限缩放，不是对其他分布差异的统计控制。", "",
             "沿用第一步的配对要求、各对等权、两类型先在对内平均、整簇 bootstrap、"
             f"B={B:,}、种子 {SEED} 和不插值的第 50、1950 项区间。"
             "仅保留所需格 r 均非缺失的对；敏感度另要求所需格原始权重和均在 [0.95, 1.05]。"
             "第二步使用独立的同种子随机流，第一步结果保持不变。", "",
             "### 相对离散缺失核对", "",
             "| 配置 | 候选数据无效 | r 有效 | 均值端点导致 r 缺失 |",
             "|---|---:|---:|---:|"]
    for config, data in output["step2"]["configs"].items():
        a = data["audit"]
        lines.append(f'| {config} | {a["invalid_candidates"]} | {a["r_valid"]} | {a["r_missing_endpoints"]} |')
    for section, title in (("contrasts", "主要相对离散对比"), ("sensitivity", "相对离散权重和敏感度")):
        lines += ["", "### " + title, "",
                  "| 配置 | 对比 | 平均 r 差 | 95% 区间 | 对数 | 簇数 | 与第一步 SD 点值方向比较 |",
                  "|---|---|---:|---|---:|---:|---|"]
        for config, data in output["step2"]["configs"].items():
            for name, summary in data[section].items():
                old = output["configs"][config][section][name]["point"]
                point = summary["point"]
                direction = ("不可比较" if old is None or point is None else
                             "不变" if np.sign(old) == np.sign(point) else "改变")
                label = contrast_label(name).replace("SD", "r")
                lines.append(f'| {config} | {label} | {fmt(point)} | {interval(summary)} | {summary["n"]} | {summary["clusters"]} | {direction} |')
    lines += ["", "### 方向比较与描述", ""]
    for config, data in output["step2"]["configs"].items():
        for section, label in (("contrasts", "主要分析"), ("sensitivity", "权重和敏感度")):
            changed = [contrast_label(n).replace("SD", "r") for n, v in data[section].items()
                       if v["point"] is not None and output["configs"][config][section][n]["point"] is not None
                       and np.sign(v["point"]) != np.sign(output["configs"][config][section][n]["point"])]
            message = "点值方向改变的对比为：" + "、".join(changed) + "；其余对比方向不变。" if changed else "七项对比的点值方向均不变。"
            lines.append(f"{config}（{label}）：{message}")
            lines.append("")
    lines += ["正的 r 差表示相对于给定均值下的最大 SD，候选更分散；负值表示相对更集中。"
              "方向比较只比较点值符号，不代表区间排除零；排除端点也改变了部分对比的可用样本，"
              "因此方向变化不能全部归于归一化。OLMo-2 的权重和敏感度样本很少，"
              "应结合表中剩余对数与区间阅读。", "",
              "各配置每格的平均 m、平均 r、有效数和端点缺失数，以及按 m 分十档的平均 SD，"
              "保存在 JSON 的 step2.configs.<配置>.cells。每格均值使用自身有效单元，平均 r 排除端点缺失；"
              "十档为 [0,10)、[10,20)、…、[90,100]，空档的平均 SD 记缺失，不绘图。", ""]
    return "\n".join(lines)


def main():
    json_path, md_path = HERE / "explore_spread.json", HERE / "explore-spread.md"
    output = compute()
    base_report = report(output)
    prefix = base_report.encode("utf-8")
    if json_path.exists():
        previous = json.loads(json_path.read_text(encoding="utf-8"))
        previous.pop("step2", None)
        first_step = {k: v for k, v in output.items() if k != "step2"}
        if previous != first_step:
            raise ValueError("First-step JSON changed; refusing to write")
    if md_path.exists():
        existing = md_path.read_bytes()
        newline = "\r\n" if b"\r\n" in existing else "\n"
        prefix = existing[:len(base_report.replace("\n", newline).encode("utf-8"))]
        if prefix.decode("utf-8").replace("\r\n", "\n") != base_report:
            raise ValueError("First-step report changed; refusing to write")
    texts = [json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
             (prefix + report_relative(output).encode("utf-8")).decode("utf-8").replace("\r\n", "\n")]
    if any(("?" * 3) in text for text in texts):
        raise ValueError("Encoding corruption")
    for path, text in zip((json_path, md_path), texts):
        path.write_text(text, encoding="utf-8")
        assert ("?" * 3) not in path.read_text(encoding="utf-8")
    print("Updated second step; first-step JSON and report verified unchanged")


if __name__ == "__main__":
    main()
