"""Exploratory agy spread analysis; registered local data only, no model calls.

Run with python -B to avoid writing import caches in the original dnli directory.
The private upstream module reuses its complete computation and RNG ordering;
only CONFIGS and the data loader are adapted. No upstream source is modified.
"""
from collections import Counter
import importlib.util
import json
import math
from pathlib import Path
import sys

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_agy as run

_spec = importlib.util.spec_from_file_location(
    "_dnli_spread_agy_upstream", HERE.parent / "dnli" / "explore_spread.py")
spread = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(spread)
CONFIGS = (
    "agy:gpt-oss-120b-medium",
    "agy:claude-sonnet-5-5-medium",
    "agy:gemini-3.8-flash-low",
    "agy:gemini-3.8-flash-high",
)


def load_records(config, base=HERE):
    """Validate registered checkpoints, last per unit, then select r0/ok/multi."""
    base = Path(base)
    suffix = run.file_config(config)
    path = base / f"results_formal_{suffix}.jsonl"
    meta = json.loads((base / f"run_meta_formal_{suffix}.json").read_text(encoding="utf-8"))
    frozen = json.loads((base / "analysis_freeze.json").read_text(encoding="utf-8"))["formal"][config]
    if meta["fingerprint_id"] != frozen:
        raise ValueError(f"Run metadata differs from frozen fingerprint: {config}")
    raw = run.load_records(path)
    registered = run.valid_records(raw, meta["sessions"], frozen)
    audit = Counter(selected=0, valid=0, invalid=0, stored_sd_present=0,
                    stored_sd_match=0, stored_sd_mismatch=0, outside_tolerance=0)
    audit.update(parsed_records=len(raw), registered_units=len(registered),
                 excluded_records=len(raw) - len(registered),
                 malformed_lines=sum(bool(line.strip()) for line in path.read_text(encoding="utf-8").splitlines()) - len(raw))
    records, mismatches = {}, []
    for row in registered.values():
        if row.get("config") != config:
            raise ValueError(f"Record config differs from file: {row.get('unit')}")
        if (row.get("round"), row.get("status"), row.get("ask")) != ("r0", "ok", "multi"):
            continue
        audit["selected"] += 1
        unit = (row["key"], row["pres"], row["utype"])
        if unit in records:
            raise ValueError(f"Duplicate analysis unit: {unit}")
        stats = spread.candidate_stats(row["result"])
        if stats is None:
            audit["invalid"] += 1
            continue
        audit["valid"] += 1
        audit["outside_tolerance"] += not 0.95 <= stats["weight_sum"] <= 1.05
        stored = row["result"].get("weighted_sd")
        if isinstance(stored, (int, float)) and math.isfinite(stored):
            audit["stored_sd_present"] += 1
            match = math.isclose(stored, stats["sd"], rel_tol=0, abs_tol=spread.ATOL)
            audit["stored_sd_match" if match else "stored_sd_mismatch"] += 1
            if not match:
                mismatches.append(dict(unit=list(unit), stored=stored, recomputed=stats["sd"]))
        records[unit] = dict(stats, cluster=row["cluster"])
    audit["stored_sd_match_rate"] = (audit["stored_sd_match"] / audit["stored_sd_present"]
                                     if audit["stored_sd_present"] else None)
    return records, dict(audit), mismatches


spread.CONFIGS = CONFIGS
spread.load_records = load_records
compute = spread.compute


def seven_config_rows(output, original):
    """Summary percentages are ratios of means, not means of pairwise ratios."""
    rows = {}
    for config, data in {**original["configs"], **output["configs"]}.items():
        prior = data["cells"]["prior:-"]["sd"]["point"]
        stated = sum(data["cells"][f"stated:{u}"]["sd"]["point"] for u in ("S", "W")) / 2
        change = sum(data["contrasts"][f"change:stated:{u}"]["point"] for u in ("S", "W")) / 2
        difference = data["contrasts"]["reported_minus_stated:pooled"]["point"]
        rows[config] = dict(prior_sd=prior, stated_sd=stated, stated_change=change,
                            stated_change_pct=100 * change / prior if prior else None,
                            reported_minus_stated=difference,
                            reported_minus_stated_pct=100 * difference / stated if stated else None,
                            rho=data["contrasts"]["spearman"]["point"])
    return rows


def report(output, original):
    f, ci = spread.fmt, spread.interval
    lines = ["探索性、非预注册、看过正式结果后才做。", "", "# agy 多估计候选离散程度", "",
             "只读本地正式结果，不调用模型，不进入 Holm 校正。计算直接复用 ../dnli/explore_spread.py。",
             "先用 analysis_freeze.json 的正式指纹核对 run_meta，再调用 run_agy.valid_records："
             "只取已登记、closed_ok、未 invalid 且指纹一致的会话，核对记录与原始调用哈希，同一 unit 取最后一条；"
             "之后只取 round=r0、status=ok、ask=multi。未登记残行及无法解析的残行均排除。", "",
             "五候选非负权重先归一化，计算总体加权 SD 与均值 m；候选越界、非有限、数组非五项或总权重不为正记缺失。"
             "全距与全同均包含零权重候选。SD 和全距单位为概率点。各对等权，每项只取所需格均有效的对；"
             "合并转述减陈述先在对内平均加强与削弱，要求四格完整。"
             "Spearman ρ 关联先验 SD 与陈述方向化移动（陈述加强均值−陈述削弱均值）/2，并列取平均秩。", "",
             f"整簇 bootstrap，B={spread.B}，种子 {spread.SEED}；抽取原数量的簇，保留簇内全部对，重抽簇按重数计。"
             "95% 区间取排序后第 50、1950 项（从 1 起计，不插值）。相关每次重算秩；出现未定义重抽样则区间缺失。"
             "两步使用独立的同种子随机流，配置与指标顺序沿用原分析。", "",
             "## 七配置汇总", "",
             "原三配置直接读取 ../dnli/explore_spread.json，不重算。陈述变化为加强、削弱各自配对差的等权平均；"
             "其百分比除以本配置先验格平均 SD。转述减陈述使用四格完整对的合并差，其百分比除以陈述加强、削弱两格平均 SD 的等权平均。"
             "均为均值之比，未另算百分比区间；各格及各对比的有效样本可能不同，不能据此作配置间因果比较。", "",
             "| 配置 | 先验 SD | 陈述后验 SD 变化（点） | 占先验 SD（%） | 转述减陈述（点） | 占陈述 SD（%） | ρ |",
             "|---|---:|---:|---:|---:|---:|---:|"]
    for config, row in seven_config_rows(output, original).items():
        lines.append("| " + config + " | " + " | ".join(f(row[k]) for k in (
            "prior_sd", "stated_change", "stated_change_pct", "reported_minus_stated", "reported_minus_stated_pct", "rho")) + " |")
    lines += ["", "## 结果摘要", ""]
    for config, data in output["configs"].items():
        pooled = data["contrasts"]["reported_minus_stated:pooled"]
        rho = data["contrasts"]["spearman"]
        changes = [s["point"] for n, s in data["contrasts"].items() if n.startswith("change:")]
        lines += [f'{config}：四格后验减先验 SD 点值为 {f(min(changes))} 至 {f(max(changes))} 点；'
                  f'转述减陈述合并差为 {f(pooled["point"])} 点，95% 区间 {ci(pooled)}。'
                  f'先验 SD 与陈述方向化移动的 ρ={f(rho["point"])}，区间 {ci(rho)}。', ""]
    lines += ["所有配置每格各 120 个有效单元，重算 SD 全部与存储值一致，原始权重和均在范围内。"
              "当前两个 gemini 文件各 1400 条均通过登记核验；gpt-oss、sonnet 各 1401 条中排除 1 条未登记记录，"
              "未发现不可解析残行。", ""]
    lines += ["", "## 筛选与重算核对", "",
              "| 配置 | 可解析记录 | 登记后 unit | 排除记录 | 不可解析残行 | r0/ok/multi | 候选有效 | 原 SD 一致/可核对 | 权重和范围外 |",
              "|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for config, data in output["configs"].items():
        a = data["audit"]
        lines.append(f'| {config} | {a["parsed_records"]} | {a["registered_units"]} | {a["excluded_records"]} | {a["malformed_lines"]} | {a["selected"]} | {a["valid"]} | {a["stored_sd_match"]}/{a["stored_sd_present"]} | {a["outside_tolerance"]} |')
    lines += ["", "原 SD 核对容差为绝对误差 ≤ 1e-9，以候选重算值为准；不一致明细见 JSON。", "",
              "## 各格描述", "",
              "每格使用自身有效单元；括号为 95% 整簇区间。全同比例和 SD=0 比例不按候选权重加权。", "",
              "| 配置 | 格 | n | 平均 SD（区间） | 平均全距（区间） | 全同比例（区间） | SD=0 比例（区间） | SD=0 但非全同数 |",
              "|---|---|---:|---|---|---|---|---:|"]
    for config, data in output["configs"].items():
        for cell, d in data["cells"].items():
            values = " | ".join(f'{f(d[k]["point"])} {ci(d[k])}' for k in ("sd", "range", "identical", "sd_zero"))
            lines.append(f'| {config} | {spread.LABELS[cell]} | {d["sd"]["n"]} | {values} | {d["zero_sd_but_not_identical"]} |')
    for step, metric in ((output, "SD"), (output["step2"], "r")):
        if metric == "r":
            lines += ["", "## 相对 spread", "",
                      "r = SD / √(m(100−m))，范围 0–1，无量纲；m=0 或 100 时记缺失。"
                      "沿用相同的配对与合并要求，额外排除所需格 r 缺失的对。每格平均 m、平均 r、端点缺失数及 m 十档 SD 描述见 JSON step2。"]
        for section, title in (("contrasts", "主要探索性对比"), ("sensitivity", "权重和敏感度分析")):
            lines += ["", f"## {metric} {title}", ""]
            if section == "sensitivity":
                lines += ["仅保留所需每格原始权重和均在 [0.95, 1.05] 的对，与原分析相同，不另做 ρ 敏感度。", ""]
            lines += ["| 配置 | 对比 | 均值差／ρ | 95% 区间 | 对数 | 簇数 | 未定义重抽样 |", "|---|---|---:|---|---:|---:|---:|"]
            for config, data in step["configs"].items():
                for name, s in data[section].items():
                    label = spread.contrast_label(name).replace("SD", metric)
                    lines.append(f'| {config} | {label} | {f(s["point"])} | {ci(s)} | {s["n"]} | {s["clusters"]} | {s["undefined_bootstrap"]} |')
    lines += ["", "## 相对 spread 的方向核对", ""]
    for config, data in output["step2"]["configs"].items():
        for section, title in (("contrasts", "主要分析"), ("sensitivity", "权重和敏感度")):
            changed = [spread.contrast_label(name) for name, s in data[section].items()
                       if s["point"] is not None and output["configs"][config][section][name]["point"] is not None
                       and agy_sign(s["point"]) != agy_sign(output["configs"][config][section][name]["point"])]
            message = "点值方向改变：" + "、".join(changed) if changed else "七项点值方向均不变"
            lines += [f"{config}（{title}）：{message}。", ""]
    lines += ["", "负差表示候选更集中，正差表示更分散。相对 spread 按给定均值下的 SD 上限缩放；"
              "端点排除也可能改变可用样本。相关只描述关系，不能解释机制；敏感度需结合剩余对数与区间阅读。", ""]
    return "\n".join(lines)


def agy_sign(value):
    return (value > 0) - (value < 0)


def main():
    output = compute()
    original = json.loads((HERE.parent / "dnli" / "explore_spread.json").read_text(encoding="utf-8"))
    text = report(output, original)
    (HERE / "explore_spread_agy.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    (HERE / "explore-spread-agy.md").write_text(text, encoding="utf-8")
    print("Wrote explore_spread_agy.json and explore-spread-agy.md")


if __name__ == "__main__":
    main()
