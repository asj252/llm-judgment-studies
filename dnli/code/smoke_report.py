"""开发集冒烟报告（PLAN v0.5 第 1、4、6 节；c 第二轮 S1、c 第三轮 N-S2 与 Q1）。只用标准库；只读结果文件。

用法：python -I -X utf8 -B smoke_report.py [输出 json，默认 raw/smoke_report_dev.json]
读 results_dev_<配置>.jsonl 与 run_meta_dev_<配置>.json；每个配置只认收尾核对通过、未作废的会话，且这些会话必须只有一个
指纹（否则拒绝，退出码 2）。只统计计划集合内的 unit（计划外的只计数）。每个配置、每个条件格（问法 × 呈现 × S/W）报：
  计划数、已尝试数、未尝试数；
  已尝试 unit 的首次成功率（分母＝已尝试；首次成功＝第一次尝试的纳入状态为 ok、未截断、解析成功）；
  计划 unit 的首次成功覆盖率（分母＝计划）；
  重试成功率（首次失败的已尝试 unit 里最终 ok 的比例）、尝试截断率、错误类型计数；
  重试后仍缺的 unit 数与缺失率（分母＝计划）。
规则（写死）：
  90% 规则：任一配置「已尝试 unit 的首次成功率」< 90% → STOP；
  2% 规则（PLAN v0.5）：每个配置分别算，分母＝该配置全部计划 unit，分子＝重试后仍缺的 unit（status 不是 ok），
    > 2% → STOP，并列出有缺失的条件格；
  完整性：缺配置、或任一配置有未尝试的计划 unit → 「未完成」，**不得判验收通过**。
结论：有 STOP → 「STOP」（退出码 4，交 a 决定：优先加大重试次数，不放宽保护）；否则未完成 → 「未完成（不得判验收通过）」
  （退出码 5）；否则「验收通过」（退出码 0）。
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analyse as AN  # noqa: E402
import run  # noqa: E402
import parse  # noqa: E402

STOP_FIRST_SUCCESS = 0.90
STOP_MISSING = 0.02
STATUS_PASS, STATUS_STOP, STATUS_INCOMPLETE = "验收通过", "STOP", "未完成（不得判验收通过）"


def first_ok(r):
    a = (r.get("attempts") or [None])[0]
    return bool(a) and a.get("state") == "ok" and not a.get("truncated") and a.get("parsed") is True


def error_type(a):
    if a.get("state") not in (None, "ok"):
        return "state:" + a["state"]
    if a.get("truncated"):
        return "truncated"
    if a.get("parsed") is False:
        err = (a.get("parse") or {}).get("error") or "unknown"
        return err.split(":", 1)[0]
    return None


def cell_of(unit):
    _, pres, ut, ask, _ = unit.split("|")
    return "%s|%s|%s" % (ask, pres, ut)


def _stats(planned_units, rs):
    """planned_units：该格（或该配置）的计划 unit 集合；rs：其中已尝试的有效记录。"""
    n_pl, n_at = len(planned_units), len(rs)
    atts = [a for r in rs for a in r.get("attempts", [])]
    fails = [r for r in rs if not first_ok(r)]
    first = sum(map(first_ok, rs))
    missing = sum(r["status"] != "ok" for r in rs)
    first_atts = [(r.get("attempts") or [{}])[0] for r in rs]
    final_atts = [(r.get("attempts") or [{}])[-1] for r in rs]
    def rates(attempts):
        eligible = lambda a: a.get("state") == "ok" and not a.get("truncated")
        v1_known = [a for a in attempts if "parse_v1" in a]
        weights = [a["parse"]["weight_sum_in_tolerance"] for a in attempts
                   if eligible(a) and a.get("parsed") and
                   (a.get("parse") or {}).get("weight_sum_in_tolerance") is not None]
        n = len(attempts)
        return {"n_outputs": n,
                "v2_parseable_rate": sum(eligible(a) and a.get("parsed") is True for a in attempts) / n if n else None,
                "n_v1_reparsed": len(v1_known),
                "v1_parseable_rate": (sum(eligible(a) and a["parse_v1"]["ok"] for a in v1_known) / n
                                      if n and len(v1_known) == n else None),
                "n_weight_sum_known": len(weights),
                "weight_sum_compliance_rate": sum(weights) / len(weights) if weights else None}
    return {"n_planned": n_pl, "n_attempted": n_at, "n_not_attempted": n_pl - n_at,
            "parsing_first": rates(first_atts), "parsing_after_retry": rates(final_atts),
            "first_success_rate_attempted": first / n_at if n_at else None,
            "first_success_coverage_planned": first / n_pl if n_pl else None,
            "retry_success_rate": (sum(r["status"] == "ok" for r in fails) / len(fails)) if fails else None,
            "attempt_truncation_rate": (sum(bool(a.get("truncated")) for a in atts) / len(atts)) if atts else None,
            "n_missing_after_retry": missing, "missing_rate_planned": missing / n_pl if n_pl else None,
            "errors": dict(Counter(e for e in (error_type(a) for a in atts) if e))}


def smoke_summary(recs_by_cfg, planned):
    """纯函数。recs_by_cfg = {配置: 有效记录}；planned = {配置: 计划 unit 集合}，也兼容共用集合。
    返回 (摘要, 结论)。"""
    plans = planned if isinstance(planned, dict) else {cfg: set(planned) for cfg in run.CONFIGS}
    counts = {cfg: len(plans[cfg]) for cfg in run.CONFIGS}
    out = {"parse_version": run.PARSE_RULES["version"], "planned_configs": list(run.CONFIGS),
           "rules": {"first_success_attempted_min": STOP_FIRST_SUCCESS, "missing_after_retry_max": STOP_MISSING,
                     "missing_denominator": "all planned units of the config",
                     "parseable_denominator": "attempted units; state ok and untruncated required; final attempt after retry",
                     "weight_sum_denominator": "v2 parseable multi outputs with known weight sum; tolerance [0.95,1.05]",
                     "v1_comparison": "same raw outputs and inclusion/truncation rules; null if any source unavailable",
                     "acceptance": "all configs run, no planned unit unattempted, no STOP"},
           "n_planned_per_config": next(iter(counts.values())) if len(set(counts.values())) == 1 else counts,
           "configs": {}, "stop_reasons": [], "incomplete_reasons": [],
           "warnings": []}
    for cfg in run.CONFIGS:
        planned = plans[cfg]
        pl_cells = defaultdict(set)
        for u in planned:
            pl_cells[cell_of(u)].add(u)
        rs_all = recs_by_cfg.get(cfg)
        if rs_all is None:
            out["configs"][cfg] = {"status": "未跑"}
            out["incomplete_reasons"].append("%s 未跑" % cfg)
            continue
        rs = [r for r in rs_all if r["unit"] in planned]
        by_cell = defaultdict(list)
        for r in rs:
            by_cell[cell_of(r["unit"])].append(r)
        cells = {c: _stats(pl_cells[c], by_cell.get(c, [])) for c in sorted(pl_cells)}
        overall = _stats(planned, rs)
        row = {"status": "已跑", "overall": overall, "cells": cells,
               "n_extra_units_ignored": len({r["unit"] for r in rs_all} - planned)}
        fs = overall["first_success_rate_attempted"]
        if fs is not None and fs < STOP_FIRST_SUCCESS:
            out["stop_reasons"].append("%s：已尝试 unit 的首次成功率 %.3f < %.2f" % (cfg, fs, STOP_FIRST_SUCCESS))
        mr = overall["missing_rate_planned"]
        if mr is not None and mr > STOP_MISSING:
            bad = ["%s %d/%d" % (c, s["n_missing_after_retry"], s["n_planned"]) for c, s in cells.items()
                   if s["n_missing_after_retry"]]
            out["stop_reasons"].append("%s：重试后仍缺 %d/%d = %.2f%% > 2%%（缺失所在条件格：%s）" % (
                cfg, overall["n_missing_after_retry"], overall["n_planned"], 100 * mr, "；".join(bad)))
        if overall["n_not_attempted"]:
            out["incomplete_reasons"].append("%s 未尝试 %d/%d 个计划 unit" % (cfg, overall["n_not_attempted"],
                                                                         overall["n_planned"]))
        for c, s in cells.items():
            if s["first_success_rate_attempted"] is not None and s["first_success_rate_attempted"] < STOP_FIRST_SUCCESS:
                out["warnings"].append("%s %s 首次成功率 %.3f" % (cfg, c, s["first_success_rate_attempted"]))
        out["configs"][cfg] = row
    if out["stop_reasons"]:
        status = STATUS_STOP
    elif out["incomplete_reasons"]:
        status = STATUS_INCOMPLETE
    else:
        status = STATUS_PASS
    out["status"] = status
    return out, status


def add_v1_comparison(rs, cfg, base=HERE):
    """同一批原始输出重解析；只附加解析结果，不改变记录纳入。"""
    out = []
    for r in rs:
        copy = dict(r, attempts=[])
        for i, a in enumerate(r.get("attempts", [])):
            tag = "%s__%s__a%d" % (run._safe(r["unit"]), cfg, a.get("attempt", i))
            raw = Path(base) / "raw" / ("run_dev_" + cfg)
            path = raw / (tag + (".last.txt" if cfg == "codex" else ".json"))
            b = dict(a)
            if path.is_file():
                data = path.read_text(encoding="utf-8")
                text = data if cfg == "codex" else json.loads(data)["text"]
                parser = parse.parse_direct_v1 if r["ask"] == "direct" else parse.parse_multi_v1
                b["parse_v1"] = parser(text)
            copy["attempts"].append(b)
        out.append(copy)
    return out


def load_dev(base=HERE):
    recs_by_cfg = {}
    for cfg in run.CONFIGS:
        mp, rp = Path(base) / ("run_meta_dev_%s.json" % cfg), Path(base) / ("results_dev_%s.jsonl" % cfg)
        if not rp.exists():
            continue
        sessions = run.load_json(mp, {"sessions": []})["sessions"]
        fps = {s["fingerprint_id"] for s in sessions if s.get("closed_ok") and not s.get("invalid")}
        if len(fps) != 1:
            raise SystemExit("REFUSED: %s has %d distinct valid fingerprints" % (cfg, len(fps)))
        recs_by_cfg[cfg], _ = AN.load_valid(rp, mp, fps.pop())
        recs_by_cfg[cfg] = add_v1_comparison(recs_by_cfg[cfg], cfg, base)
    return recs_by_cfg


def main():
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE / "raw" / "smoke_report_dev.json"
    try:
        recs = load_dev()
    except SystemExit as e:
        print(e)
        sys.exit(2)
    summary, status = smoke_summary(recs, AN.planned_units(HERE, "dev"))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(summary, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")
    for cfg, row in summary["configs"].items():
        o = row.get("overall") or {}
        print(cfg, row["status"], {k: o.get(k) for k in ("n_attempted", "first_success_rate_attempted",
                                                         "first_success_coverage_planned", "missing_rate_planned")})
    print(status, *(summary["stop_reasons"] + summary["incomplete_reasons"]), sep="\n")
    sys.exit({STATUS_PASS: 0, STATUS_STOP: 4, STATUS_INCOMPLETE: 5}[status])


if __name__ == "__main__":
    main()
