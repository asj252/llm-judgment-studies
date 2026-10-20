"""唯一分析入口（PLAN v0.5 第 1、4、5 节；c 第二轮 B4、S2、S4、Q1、Q2；c 第三轮 N-B1、N-B2、N-S3；任务书第 6 步）。

来源：改写自 ../suppression/analyse.py（c 第三至第五轮审过）。沿用：记录筛选 load_valid（会话已登记、收尾核对通过、未作废、
会话与记录的指纹都＝冻结指纹；同一 unit 取最后一条；与 run.valid_records 断言一致）、冻结 freeze、材料绑定 check_bindings
（在构造概率格之前；不一致抛 MaterialMismatch 拒绝）、按条件的预算报告。

材料与代码绑定（c 第二轮 B4）：
- 当前重算的材料＝split.json、raw/items_text.json、prompts.py、parse.py、run.py 的文件哈希，以及 templates、parse_rules、
  materials_digest；每个冻结会话的指纹明细里这几项都必须等于当前重算值；跨配置的共同材料也必须一致。
- 分析代码：freeze 时把 analysis.py、analyse.py、run.py（分析依赖它的记录读取、有效会话筛选、计划 unit、材料摘要；
  c 第三轮 N-B2）的哈希、分析设置与 bootstrap 次数 B（正式 5000；N-B1）记进 analysis_freeze.json 的 <which>._analysis_code；
  analyse 时代码与设置必须相同。正式分析（final=True）传入的 B 必须等于冻结值；final=False 的结果一律标「诊断」，可改 B。
  要改分析代码就得有意删掉该项再冻结，留下记录。
- 逐条记录：来自哪个配置的结果文件，config 字段就必须是那个配置；unit ＝ 题号|呈现|类型|问法|轮次 与各字段一致且取值合法；
  题号在清单里，簇、use、update_id 与清单一致；r1 只在正式集的重复子集；**prompt_sha256 ＝ 用当前代码与当前题面重新渲染该
  unit 的提示的哈希**。
核账（v0.7）：以三个配置各自的计划 unit 为分母，本地正式集 A+B，codex 正式集仅 A；重复子集保持不变。
报每个配置的有效记录数、ok 数、未尝试数与完成率；
  缺配置、缺 unit 或有计划外 unit → 「部分分析（诊断；不作正式报告）」；analyse(final=True) 遇到这些直接拒绝。
  ok 数只算计划集合内的记录；计划外 unit 不进分析（c 第三轮 N-S3）。缺失率也以计划 unit 为分母。
描述：主对比各行带 companion（同一共同题集上的配套分项，c 第二轮 S2）；全可用格的条件表与端点表注明分母；按 source_split
  分层的点估计（S4）；H2 的解释；候选层；调用间变异；预算与截断；功效情景（开发集）；跨配置判定与反方向描述（Q1）。

用法：
    python -I -X utf8 -B analyse.py freeze <dev|formal> <配置>            # 冻结 B＝5000
    python -I -X utf8 -B analyse.py run <dev|formal> [输出 json] [--final] [--B N]   # --B 只用于诊断
"""
import collections
import hashlib
import json
import statistics
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analysis as A  # noqa: E402
import prompts  # noqa: E402
import run  # noqa: E402

FREEZE = HERE / "analysis_freeze.json"
CONFIGS = run.CONFIGS
CURRENT_FILES = (run.SPLIT_FILE, run.ITEMS_TEXT, "prompts.py", "parse.py", "run.py")
COMMON_MATERIALS = CURRENT_FILES + ("templates", "parse_rules", "materials_digest")
CODE_KEY = "_analysis_code"
PRES_ALL = ("prior",) + run.PRES_POST


class MaterialMismatch(Exception):
    """当前文件与冻结会话记录的材料不一致，或跨配置共同材料不一致，或记录与清单／提示／配置不符：拒绝分析。"""


class Incomplete(Exception):
    """正式报告（final=True）要求计划配置与 unit 全部核账。"""


def _sha_file(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


FORMAL_B = 5000
# 分析代码的绑定对象（c 第三轮 N-B2）：analysis.py、analyse.py，以及分析依赖的 run.py（记录读取、有效会话筛选、计划 unit、
# 材料摘要）。取正在运行的模块文件；测试可以把某项指向改过的副本来做负例。
CODE_PATHS = {"analysis.py": Path(A.__file__), "analyse.py": Path(__file__), "run.py": Path(run.__file__),
              "speech_updates.json": HERE / "speech_updates.json"}


def analysis_code(B=FORMAL_B):
    """当前分析代码与设置的哈希，以及冻结的 bootstrap 次数 B（c 第三轮 N-B1）。"""
    settings = {"H4A_WEIGHTS": A.H4A_WEIGHTS, "endpoint": [A.ENDPOINT_LO, A.ENDPOINT_HI], "alpha": A.ALPHA,
                "seed": A.SEED, "specs": {k: {kk: v[kk] for kk in ("sided", "direction", "min_effect", "subst")}
                                          for k, v in A.SPECS.items()}}
    out = {name: _sha_file(p) for name, p in CODE_PATHS.items()}
    out["settings"] = run._sha(json.dumps(settings, sort_keys=True).encode("utf-8"))
    out["B"] = B
    return out


def session_fp(meta_path, frozen):
    sessions = run.load_json(meta_path, {"sessions": []})["sessions"]
    fps = [s["fingerprint"] for s in sessions
           if s.get("fingerprint_id") == frozen and s.get("closed_ok") and not s.get("invalid")]
    if not fps:
        raise MaterialMismatch("no valid session with frozen fingerprint %s" % frozen)
    if any(f != fps[0] for f in fps):
        raise MaterialMismatch("sessions with the same fingerprint id carry different details")
    return fps[0]


def current_materials(base):
    """当前文件重算的共同材料（清单、题面、prompts.py、parse.py 的文件哈希，模板、解析常量、渲染摘要）。"""
    all_items, split = run.load_all_items(base)
    cur = {rel: _sha_file(Path(base) / rel) for rel in CURRENT_FILES}
    cur["templates"] = run._sha(json.dumps(prompts.templates(), sort_keys=True, ensure_ascii=False).encode("utf-8"))
    cur["parse_rules"] = run._sha(json.dumps(run.PARSE_RULES, sort_keys=True).encode("utf-8"))
    cur["materials_digest"] = run.materials_digest(all_items, split)[0]
    return cur, split, all_items


def _unit_problems(r, cfg, it, rep, all_items):
    probs = []
    if r.get("config") != cfg:
        probs.append("record %s: config %r but comes from the %s results" % (r.get("unit"), r.get("config"), cfg))
    fields = (r.get("key"), r.get("pres"), r.get("utype"), r.get("ask"), r.get("round"))
    if r.get("unit") != "|".join(str(f) for f in fields):
        probs.append("record %s: unit does not match its fields %r" % (r.get("unit"), fields))
        return probs
    if (r["pres"] not in PRES_ALL or r["ask"] not in run.ASKS or r["round"] not in run.ROUNDS
            or (r["pres"] == "prior") != (r["utype"] == "-") or (r["pres"] != "prior" and r["utype"] not in run.TYPES)):
        probs.append("record %s: invalid field values" % r["unit"])
        return probs
    for f in ("cluster", "use"):
        if r.get(f) != it.get(f):
            probs.append("record %s: %s %r != split %r" % (r["unit"], f, r.get(f), it.get(f)))
    want = None if r["pres"] == "prior" else it[r["utype"]]["id"]
    if r.get("update_id") != want:
        probs.append("record %s: update_id %r != split %r" % (r["unit"], r.get("update_id"), want))
    if r["round"] == "r1" and not (it["use"] == "formal" and r["key"] in rep):
        probs.append("record %s: repeat round outside the repeat subset" % r["unit"])
    u = fields
    sha = run._sha(run.render_unit(all_items[r["key"]], u).encode("utf-8"))
    if r.get("prompt_sha256") != sha:
        probs.append("record %s: prompt_sha256 differs from the prompt re-rendered with current code" % r["unit"])
    return probs


def check_bindings(base, fps, recs_by_cfg):
    """1 每个配置冻结会话的明细里，CURRENT_FILES 与模板、解析常量、渲染摘要＝当前重算值；2 跨配置共同材料一致；
    3 逐条记录（配置归属、unit 与字段、清单字段、选句、重复轮、提示哈希）。任一不符抛 MaterialMismatch。"""
    probs = []
    cur, split, all_items = current_materials(base)
    for cfg, fp in fps.items():
        for rel, h in cur.items():
            if fp.get(rel) != h:
                probs.append("%s: %s differs from the frozen session" % (cfg, rel))
    if len(fps) > 1:
        for rel in COMMON_MATERIALS:
            vals = {cfg: fp.get(rel) for cfg, fp in fps.items()}
            if len(set(vals.values())) != 1:
                probs.append("common material %s differs across configs: %s" % (rel, sorted(vals)))
    by = {it["key"]: it for it in split["items"]}
    rep = set(split["repeat_subset"])
    n = 0
    for cfg, recs in recs_by_cfg.items():
        if cfg not in fps:
            probs.append("records for %s without a frozen session" % cfg)
        for r in recs:
            n += 1
            it = by.get(r.get("key"))
            if it is None:
                probs.append("record %s not in current split" % r.get("unit"))
                continue
            probs += _unit_problems(r, cfg, it, rep, all_items)
    if probs:
        raise MaterialMismatch("; ".join(probs[:10]) + (" … (%d problems)" % len(probs) if len(probs) > 10 else ""))
    return {"configs": sorted(fps), "records_checked": n, "current": cur, "common_materials": list(COMMON_MATERIALS)}


def frozen_fp(cfg, which, path=FREEZE):
    return json.loads(Path(path).read_text(encoding="utf-8"))[which][cfg]


def load_valid(results_path, meta_path, frozen):
    """返回 (有效记录列表, 筛除统计)。frozen 为冻结的指纹 ID。（与 ../suppression/analyse.py 相同）"""
    sessions = run.load_json(meta_path, {"sessions": []})["sessions"]
    records = run.load_records(results_path)
    by_id = {s["session_id"]: s for s in sessions}
    drop = collections.Counter()
    keep = {}
    for r in records:
        s = by_id.get(r.get("session_id"))
        if s is None:
            drop["unknown_session"] += 1
        elif s.get("invalid"):
            drop["invalid_session"] += 1
        elif not s.get("closed_ok"):
            drop["session_not_closed_ok"] += 1
        elif s.get("fingerprint_id") != frozen or r.get("fingerprint_id") != frozen:
            drop["other_fingerprint"] += 1
        else:
            if r["unit"] in keep:
                drop["superseded_duplicate"] += 1
            keep[r["unit"]] = r
    out = list(keep.values())
    if set(run.valid_records(records, sessions, frozen)) != set(keep):
        raise RuntimeError("load_valid disagrees with run.valid_records")
    return out, dict(drop)


def budget_report(records):
    """按 (配置, 呈现, 更新类型, 问法, 轮次) 报预算与截断（c 第一轮建议 17）。只用首次尝试的 meta 与全部尝试的截断。"""
    g = collections.defaultdict(list)
    for r in records:
        g[(r["config"], r["pres"], r["utype"], r["ask"], r["round"])].append(r)
    out = {}

    def mean(xs):
        xs = [x for x in xs if x is not None]
        return round(statistics.fmean(xs), 1) if xs else None
    for k, rs in sorted(g.items()):
        a0 = [r["attempts"][0].get("meta", {}) for r in rs if r.get("attempts")]
        atts = [a for r in rs for a in r.get("attempts", [])]
        out["|".join(k)] = {
            "n": len(rs),
            "prompt_tokens": mean(m.get("n_prompt_tokens") for m in a0),
            "budget_mean": mean(m.get("n_predict") for m in a0),
            "budget_min": min((m.get("n_predict") for m in a0 if m.get("n_predict") is not None), default=None),
            "thinking_tokens": mean(m.get("n_thinking_tokens") for m in a0),
            "answer_tokens": mean((m.get("n_out_tokens") or 0) - (m.get("n_thinking_tokens") or 0) for m in a0
                                  if m.get("n_out_tokens") is not None),
            "seconds": mean(m.get("seconds") for m in a0),
            "attempt_truncation_rate": round(sum(bool(a.get("truncated")) for a in atts) / len(atts), 3) if atts else None,
            "retry_rate": round(sum(r.get("n_attempts", 1) > 1 for r in rs) / len(rs), 3),
            "final_missing_rate": round(sum(r["status"] != "ok" for r in rs) / len(rs), 3),
            "nonpositive_budget": sum(1 for a in atts if (a.get("meta") or {}).get("n_predict") is not None
                                      and a["meta"]["n_predict"] <= 0)}
    return out


def planned_units(base, which):
    """返回 {配置: 计划 unit 集合}，与运行调度使用同一配置筛选规则。"""
    items, split, _ = run.load_items(which, base)
    return {cfg: {run.unit_id(u) for u in run.make_schedule(items, which, cfg, split)} for cfg in CONFIGS}


def accounting(planned, recs_by_cfg, frozen_cfgs):
    """以计划配置与计划 unit 为分母的核账（c 第二轮 Q2）。"""
    plans = planned if isinstance(planned, dict) else {c: planned for c in CONFIGS}
    counts = {c: len(plans[c]) for c in CONFIGS}
    out, partial = {"n_planned_units_per_config": next(iter(counts.values())) if len(set(counts.values())) == 1 else counts,
                    "configs": {}}, False
    for cfg in CONFIGS:
        planned = plans[cfg]
        recs = recs_by_cfg.get(cfg, [])
        units = {r["unit"] for r in recs}
        ok = sum(r["status"] == "ok" for r in recs if r["unit"] in planned)      # 只算计划集合内（c 第三轮 N-S3）
        row = {"n_planned_units": len(planned), "frozen": cfg in frozen_cfgs, "valid_records": len(units & planned), "ok": ok,
               "not_attempted": len(planned - units), "extra_units": len(units - planned),
               "completion_rate": len(units & planned) / len(planned) if planned else None,
               "ok_rate_of_planned": ok / len(planned) if planned else None}
        out["configs"][cfg] = row
        partial |= (not row["frozen"]) or row["not_attempted"] > 0 or row["extra_units"] > 0
    out["missing_configs"] = [c for c in CONFIGS if c not in frozen_cfgs]
    out["status"] = "部分分析（诊断；不作正式报告）" if partial else "完整核账"
    return out


def formal_n(cfg):
    """正式集在该配置下的计划对数（PLAN v0.7：本地 240，codex 只跑 block A 的 120；c 第七轮 S1）。"""
    items = json.loads((HERE / run.SPLIT_FILE).read_text(encoding="utf-8"))["items"]
    return sum(1 for it in items if it["use"] == "formal" and (cfg != "codex" or it.get("formal_block") == "A"))


def analyse(which, out_path=None, base=HERE, freeze_path=FREEZE, B=None, final=False):
    """B=None 用冻结的 B。final=True（正式报告）：B 必须等于冻结值、核账必须完整、不得有计划外 unit，否则拒绝；
    final=False 一律标「诊断」，可改 B（c 第三轮 N-B1）。"""
    split = json.loads((Path(base) / run.SPLIT_FILE).read_text(encoding="utf-8"))
    fz_all = json.loads(Path(freeze_path).read_text(encoding="utf-8")).get(which, {})
    frozen_code = fz_all.get(CODE_KEY) or {}
    B_frozen = frozen_code.get("B")
    code_now = analysis_code(B_frozen)
    if frozen_code != code_now:
        raise MaterialMismatch("analysis code or settings differ from the frozen %s: %s" % (
            CODE_KEY, sorted(k for k in set(code_now) | set(frozen_code) if frozen_code.get(k) != code_now.get(k))))
    B = B_frozen if B is None else B
    if final and B != B_frozen:
        raise MaterialMismatch("final analysis must use the frozen B=%s, got B=%s" % (B_frozen, B))
    mode = {"mode": "正式" if final else "诊断", "B": B, "B_frozen": B_frozen,
            "notes": ([] if B == B_frozen else ["B 与冻结值不同（诊断，不能作为正式结果）"])}
    fz = {c: v for c, v in fz_all.items() if c in CONFIGS}
    all_items, _ = run.load_all_items(base)
    planned = {cfg: sorted(run.planned_items(all_items, which, cfg)) for cfg in CONFIGS}
    repeat = sorted(split["repeat_subset"]) if which == "formal" else []
    pairs = {it["key"]: {"cluster": it["cluster"], "use": it["use"], "source_split": it.get("source_split")}
             for it in split["items"]}
    recs_by_cfg, filt, fps = {}, {}, {}
    for cfg in CONFIGS:
        if cfg not in fz:
            continue
        rp = Path(base) / ("results_%s_%s.jsonl" % (which, cfg))
        mp = Path(base) / ("run_meta_%s_%s.json" % (which, cfg))
        v, d = load_valid(rp, mp, fz[cfg])
        fps[cfg] = session_fp(mp, fz[cfg])
        recs_by_cfg[cfg] = v
        filt[cfg] = {"kept": len(v), "dropped": d, "frozen_fingerprint": fz[cfg]}
    binding = check_bindings(base, fps, recs_by_cfg)      # 不一致即拒绝
    pu = planned_units(base, which)
    acct = accounting(pu, recs_by_cfg, set(fz))
    if final and acct["status"] != "完整核账":
        raise Incomplete("final report requires all planned configs and units, and no unit outside the plan: %s"
                         % json.dumps(acct, ensure_ascii=False))
    recs = [r for cfg, v in recs_by_cfg.items() for r in v if r["unit"] in pu[cfg]]
    cells, rep_cells, cand, _ = A.cells_from_records(recs)
    present = sorted(fz)
    fams = {}
    for name, tests in A.families_for(present).items():
        fams[name] = {"members": tests, "rows": A.analyse_family(tests, cells, planned[tests[0][1]], pairs, B=B)}
    desc = {}
    for cfg in present:
        keys = planned[cfg]
        desc[cfg] = {"conditions_all_available": A.condition_table(cells, cfg, keys),
                     "h2_reading": A.h2_reading(cells, cfg, keys),
                     "endpoints_all_available": A.endpoint_table(cells, cfg, keys),
                     "candidates_multi": A.candidate_table(cand, cfg, keys),
                     "repeat_noise": A.repeat_noise(cells, rep_cells, cfg, repeat) if repeat else None,
                     "power_scenarios": A.power_scenarios(cells, cfg, keys, n_formal=formal_n(cfg)) if which == "dev" else None}
        if which == 'formal' and cfg in run.LOCAL:
            desc[cfg]['block_A_codex_comparison'] = A.descriptive_contrasts(cells, cfg, planned['codex'], pairs, B=B)
    out = {"which": which, "mode": mode, "status": acct["status"], "accounting": acct, "p_note": A.P_NOTE, "binding": binding,
           "analysis_code": code_now, "filter": filt,
           "n_planned": len({k for ks in planned.values() for k in ks}),
           "n_planned_by_config": {c: len(ks) for c, ks in planned.items()}, "n_repeat": len(repeat),
           "families_frozen": {k: v["members"] for k, v in fams.items()}, "families": fams,
           "cross_config_summary": A.cross_config_summary(fams), "descriptives": desc,
           "speech_sensitivity": A.speech_sensitivity(cells, planned, pairs, present, split["items"],
               set(json.loads((HERE / "speech_updates.json").read_text(encoding="utf-8"))["update_ids"]), fams, B=B),
           "source_split_strata": A.strata_points(cells, planned, pairs, present),
           "missing": A.missing_rates(recs, {c: pu[c] for c in present}), "budget": budget_report(recs),
           "settings": {"H4A_WEIGHTS": A.H4A_WEIGHTS, "endpoint": [A.ENDPOINT_LO, A.ENDPOINT_HI], "B": B,
                        "seed": A.SEED, "alpha": A.ALPHA}}
    if out_path:
        Path(out_path).write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str) + "\n",
                                  encoding="utf-8", newline="\n")
    return out


def freeze(which, cfg, base=HERE, freeze_path=FREEZE, B=FORMAL_B):
    """把结果里唯一的有效会话指纹写进冻结文件，并冻结分析代码（analysis.py、analyse.py、run.py、设置）与 bootstrap
    次数 B（正式 5000）；有多个不同指纹的有效会话、已冻结且不同、或分析代码／B 与已冻结的不同，都拒绝。"""
    sessions = run.load_json(Path(base) / ("run_meta_%s_%s.json" % (which, cfg)), {"sessions": []})["sessions"]
    fps = {s["fingerprint_id"] for s in sessions if s.get("closed_ok") and not s.get("invalid")}
    if len(fps) != 1:
        raise SystemExit("STOP: %d distinct valid fingerprints" % len(fps))
    p = Path(freeze_path)
    fz = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    fp = fps.pop()
    w = fz.setdefault(which, {})
    if w.get(cfg) and w[cfg] != fp:
        raise SystemExit("STOP: already frozen to a different fingerprint")
    code = analysis_code(B)
    if w.get(CODE_KEY) and w[CODE_KEY] != code:
        raise SystemExit("STOP: analysis code or B differs from the frozen %s (delete it deliberately to refreeze)"
                         % CODE_KEY)
    w[cfg] = fp
    w[CODE_KEY] = code
    p.write_text(json.dumps(fz, indent=1) + "\n", encoding="utf-8", newline="\n")
    return fp


if __name__ == "__main__":
    argv = sys.argv[1:]
    B_arg = None
    if "--B" in argv:
        i = argv.index("--B")
        B_arg = int(argv[i + 1])
        del argv[i:i + 2]
    args = [a for a in argv if a != "--final"]
    if len(args) >= 3 and args[0] == "freeze":
        print(freeze(args[1], args[2]))
    elif len(args) >= 2 and args[0] == "run":
        analyse(args[1], args[2] if len(args) > 2 else HERE / ("analysis_%s.json" % args[1]),
                B=B_arg, final="--final" in argv)
    else:
        raise SystemExit(__doc__)
