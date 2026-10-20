"""分析（PLAN v0.4 第 1、4、5 节；c 第一轮阻断 2、5、6，c 第二轮 B1–B3、S2、S4、Q1；任务书第 6 步）。只用标准库，纯函数为主。

来源：改写自 ../suppression/analysis.py（c 第二至第五轮审过）。沿用：共同完整题集、整簇 bootstrap（每次抽簇带上该簇全部条件，
同一次重复内算统计量）、不插值分位数、bootstrap p、Holm 逐级、B 默认 5000。

数据：cells[(配置, 题号, 呈现, 更新类型, 问法)] = 报告概率（0–100；多估计为加权平均聚合值），只放 r0 轮、status=ok 的记录；
  先验的呈现为 prior、更新类型为 '-'。rep_cells 同样的键放重复轮 r1。pairs[题号] = {"cluster": 图片, "use": …, "source_split": …}。

题级量（PLAN 第 1 节）：Δ = p₁ − p₀；方向化移动 s = Δ × sign（S 为 +1，W 为 −1）；题级 s̄ = (s_S + s_W)/2 = (p_S − p_W)/2。
  **先验相消（v0.4）**：H1、H2、H4b 只要求该对比所需的后验格，不因缺先验而排除题；先验缺失在配套分项里另报
  （v0.3 的「缺先验就排除」已推翻，c 第二轮 B2）。H4a 用到 p₀ 本身（端点指示量），需要先验。

主对比表（冻结；题等权；每个都是「题级贡献」在该对比的共同完整题集上的平均）：
  H1  = mean s̄（直接、陈述）                         所需格：陈述 S、W（直接）               单侧，预测 > 0，阈值 5 点
  H2  = mean [s̄_陈述 − s̄_转述]（直接）                ＋转述 S、W（直接）                      单侧，预测 > 0，阈值 5 点
  H4a = mean [e_直接 − e_多估计]                      两种问法的先验、陈述 S、陈述 W            单侧，预测 > 0，阈值 0.10
        e = ½·1[p₀ 端点] + ¼·1[p_S,陈述 端点] + ¼·1[p_W,陈述 端点]；端点＝≤ 5 或 ≥ 95（v0.3／v0.4；c 第二轮 B1）
  H4b = mean [s̄_多估计 − s̄_直接]（陈述）               两种问法的陈述 S、W                       双侧，阈值 5 点

缺失（PLAN v0.4 第 1、4 节）：
- 题级范围 contrib_range：缺失格逐格代入两端（线性量 0／100；H4a 的端点指示量 0／1，实现为代入 50＝非端点、0＝端点），
  题级贡献对每格线性，逐格取端点即得该题贡献的 [min, max]。
- 点值界限 missing_bounds：预定全样本上题级 min（max）的平均。
- **保守区间**（c 第二轮 B2）：对判定方向 σ，把预定全样本中每题的未知贡献按最不利值（σ>0 取 min，σ<0 取 max）代入，
  在全部预定题上**重做整簇 bootstrap**，取同一水平、同一侧数的 σ 方向界 b_c。
- 保留规则（c 第二轮 B3）：σ·b_c ≤ 0 → 方向不保留（证据不足）；「区间下界超过阈值」只在 σ·b_c > 阈值时保留，
  标「（缺失按最不利值代入）」；「点估计达到阈值」只在 σ·点值最不利界 ≥ 阈值时保留。完整题子集的强度不能被缺失保护升级；
  被降级时判「证据不足」并写出保留下来的结论。无缺失时预定全样本＝完整题子集，判定不变。
- 「完整题子集区间」与「缺失保护」分开输出（complete_subset、missing_protection）。

区间与 p（不插值分位数，与 p 同一套计数）：
  双侧：k = floor(α·B/2)，区间 = [第 k 小, 第 k 大]；p = min(1, 2·min(P(r≤0), P(r≥0)))；「区间不含 0」⇔「p ≤ α」。
  单侧（预测方向 d）：k = floor(α·B)；界 = d>0 时第 k 小，d<0 时第 k 大；p = P(d·r ≤ 0)；「界在预测方向越过 0」⇔「p ≤ α」。
Holm（PLAN 第 5 节）：每个配置一个家族 {H1, H2, H4a, H4b}。按完整题子集的 p 升序（并列保持传入顺序），
  第 rank 个（从 0 起）用 α/(m − rank)；拒绝＝单侧界在预测方向越过 0、或双侧区间不含 0（完整题子集上）；一旦某项未拒绝，
  其后一律「不确定（Holm：前序检验未拒绝）」。拒绝状态按完整题子集定；缺失保护只改最终判定文字。
  单侧检验在反方向越过 0：判「方向相反」，不算拒绝（Holm 由此停止）；另外不论 Holm 是否已停，都输出受缺失保护的反方向描述
  opposite_direction（注明未作确认性拒绝），并进跨配置摘要（c 第二轮 Q1）。
判定用语（PLAN 第 1 节）：方向确定后按该方向取号——近 0 的界 > 阈值 →「区间下界超过阈值」；否则点估计 ≥ 阈值 →
  「点估计达到阈值（区间下界未超过）」；否则「点估计未达阈值」。研究层面只汇总各配置的判定，不作总体确认。
"""
import math
import random
import statistics
from collections import Counter, defaultdict

CONFIGS = ("qwen3-off", "olmo2", "codex")
ASKS = ("direct", "multi")
PRES = ("stated", "reported")
TYPES = ("S", "W")
SIGN = {"S": +1, "W": -1}
ALPHA = 0.05
B_DEFAULT = 5000
SEED = 20261090
ENDPOINT_LO, ENDPOINT_HI = 5.0, 95.0
H4A_WEIGHTS = (("prior", "-", 0.5), ("stated", "S", 0.25), ("stated", "W", 0.25))
LINEAR_SUBST = (0.0, 100.0)
INDICATOR_SUBST = (50.0, 0.0)          # 代入后的端点指示量分别为 0、1

SPECS = {
    "H1": {"sided": 1, "direction": +1, "min_effect": 5.0, "subst": LINEAR_SUBST,
           "words": {+1: "预测方向（陈述下往标签方向移动）", -1: "方向相反（陈述下往标签反方向移动）"}},
    "H2": {"sided": 1, "direction": +1, "min_effect": 5.0, "subst": LINEAR_SUBST,
           "words": {+1: "预测方向（陈述的方向化移动大于转述）", -1: "方向相反（转述的方向化移动大于陈述）"}},
    "H4a": {"sided": 1, "direction": +1, "min_effect": 0.10, "subst": INDICATOR_SUBST,
            "words": {+1: "预测方向（多估计的聚合端点率较低）", -1: "方向相反（多估计的聚合端点率较高）"}},
    "H4b": {"sided": 2, "direction": 0, "min_effect": 5.0, "subst": LINEAR_SUBST,
            "words": {+1: "多估计 > 直接", -1: "多估计 < 直接"}},
}
STRENGTH_WORDS = {"bound_exceeds": "区间下界超过阈值", "point_reaches": "点估计达到阈值（区间下界未超过）",
                  "below": "点估计未达阈值"}
STRENGTH_RANK = {"below": 0, "point_reaches": 1, "bound_exceeds": 2}
MISSING_SUFFIX = "（缺失按最不利值代入）"
FAMILY_TESTS = ("H1", "H2", "H4a", "H4b")


def is_endpoint(v):
    return v <= ENDPOINT_LO or v >= ENDPOINT_HI


def families_for(configs):
    """冻结的 Holm 家族：每个配置 {H1, H2, H4a, H4b}。"""
    fams = {"config:" + c: [(t, c) for t in FAMILY_TESTS] for c in CONFIGS if c in configs}
    return fams


# ---------------- 题级量 ----------------

def prior_cell(cfg, k, ask):
    return (cfg, k, "prior", "-", ask)


def delta(cells, cfg, k, pres, ut, ask):
    a, b = cells.get(prior_cell(cfg, k, ask)), cells.get((cfg, k, pres, ut, ask))
    return None if a is None or b is None else b - a


def s_item(cells, cfg, k, pres, ask):
    """题级方向化移动 s̄ = (s_S + s_W)/2 = (p_S − p_W)/2（p₀ 相消）。"""
    a, b = cells.get((cfg, k, pres, "S", ask)), cells.get((cfg, k, pres, "W", ask))
    return None if a is None or b is None else (a - b) / 2


def endpoint_item(cells, cfg, k, ask):
    """e = ½·1[p₀ 端点] + ¼·1[陈述 S 端点] + ¼·1[陈述 W 端点]（H4A_WEIGHTS）。"""
    vals = [cells.get((cfg, k, p, t, ask)) for p, t, _ in H4A_WEIGHTS]
    if None in vals:
        return None
    return sum(w * is_endpoint(v) for (_, _, w), v in zip(H4A_WEIGHTS, vals))


def _diff(a, b):
    return None if a is None or b is None else a - b


def contrib(name, cells, k, cfg=None):
    if name == "H1":
        return s_item(cells, cfg, k, "stated", "direct")
    if name == "H2":
        return _diff(s_item(cells, cfg, k, "stated", "direct"), s_item(cells, cfg, k, "reported", "direct"))
    if name == "H4a":
        return _diff(endpoint_item(cells, cfg, k, "direct"), endpoint_item(cells, cfg, k, "multi"))
    if name == "H4b":
        return _diff(s_item(cells, cfg, k, "stated", "multi"), s_item(cells, cfg, k, "stated", "direct"))
    raise ValueError(name)


def _post(cfg, k, pres, ask):
    return [(cfg, k, pres, t, ask) for t in TYPES]


def cells_needed(name, k, cfg=None):
    if name == "H1":
        return _post(cfg, k, "stated", "direct")
    if name == "H2":
        return _post(cfg, k, "stated", "direct") + _post(cfg, k, "reported", "direct")
    if name == "H4a":
        return [(cfg, k, p, t, a) for a in ASKS for p, t, _ in H4A_WEIGHTS]
    if name == "H4b":
        return _post(cfg, k, "stated", "direct") + _post(cfg, k, "stated", "multi")
    raise ValueError(name)


def stat(name, cells, keys, cfg=None):
    vals = [contrib(name, cells, k, cfg) for k in keys]
    if not vals or None in vals:
        return None
    return statistics.fmean(vals)


def common_complete(name, cells, keys, cfg=None):
    return [k for k in keys if all(c in cells for c in cells_needed(name, k, cfg))]


# ---------------- 缺失：题级范围、点值界限 ----------------

def contrib_range(name, cells, k, cfg=None):
    """该题贡献在缺失格代入两端后的 (min, max, 缺失格数)；无缺失时 (v, v, 0)。贡献对每格线性，逐格累加斜率即得极值。"""
    need = cells_needed(name, k, cfg)
    missing = [c for c in need if c not in cells]
    if not missing:
        v = contrib(name, cells, k, cfg)
        return v, v, 0
    lo_v, hi_v = SPECS[name]["subst"]
    base = {c: cells[c] for c in need if c in cells}
    for c in missing:
        base[c] = lo_v
    v0 = contrib(name, base, k, cfg)
    mn = mx = v0
    for c in missing:
        t = dict(base)
        t[c] = hi_v
        slope = contrib(name, t, k, cfg) - v0
        if slope > 0:
            mx += slope
        elif slope < 0:
            mn += slope
    return mn, mx, len(missing)


def missing_bounds(name, cells, keys, cfg=None):
    """预定全样本 keys 上统计量的点值界限 [min, max]。"""
    rs = [contrib_range(name, cells, k, cfg) for k in keys]
    if not rs:
        return {"n_missing_cells": 0, "n_pairs_with_missing": 0, "min": None, "max": None,
                "substitution": list(SPECS[name]["subst"])}
    return {"n_missing_cells": sum(r[2] for r in rs), "n_pairs_with_missing": sum(1 for r in rs if r[2]),
            "min": statistics.fmean(r[0] for r in rs), "max": statistics.fmean(r[1] for r in rs),
            "substitution": list(SPECS[name]["subst"])}


# ---------------- bootstrap、区间与 p ----------------

def boot_values(values, pairs, B=B_DEFAULT, seed=SEED):
    """values：{题号: 贡献}。整簇重抽，返回 B 个重复的题等权平均。"""
    by_cl = defaultdict(list)
    for k, v in values.items():
        by_cl[pairs[k]["cluster"]].append(v)
    cls = sorted(by_cl)
    sums = [(math.fsum(by_cl[c]), len(by_cl[c])) for c in cls]
    rng = random.Random(seed)
    reps = []
    for _ in range(B):
        s = n = 0
        for _ in cls:
            a, b = sums[rng.randrange(len(cls))]
            s += a
            n += b
        reps.append(s / n)
    return reps


def cluster_bootstrap(name, cells, keys, pairs, cfg=None, B=B_DEFAULT, seed=SEED):
    """keys 应是共同完整题集。"""
    return boot_values({k: contrib(name, cells, k, cfg) for k in keys}, pairs, B, seed)


def conservative_bootstrap(name, cells, keys, pairs, cfg, sigma, B=B_DEFAULT, seed=SEED):
    """预定全样本 keys：已知贡献照用，未知贡献按 σ 方向最不利值代入（σ>0 取 min，σ<0 取 max），重做整簇 bootstrap。"""
    vals = {}
    for k in keys:
        mn, mx, _ = contrib_range(name, cells, k, cfg)
        vals[k] = mn if sigma > 0 else mx
    return boot_values(vals, pairs, B, seed), statistics.fmean(vals.values())


def boot_p_two(reps):
    n = len(reps)
    le = sum(1 for r in reps if r <= 0) / n
    ge = sum(1 for r in reps if r >= 0) / n
    return min(1.0, 2 * min(le, ge))


def boot_p_one(reps, direction):
    return sum(1 for r in reps if direction * r <= 0) / len(reps)


def order_interval(reps, alpha):
    """双侧不插值区间：k = floor(α·B/2)，[第 k 小, 第 k 大]（从 0 起）。"""
    xs = sorted(reps)
    B = len(xs)
    k = int(math.floor(alpha * B / 2 + 1e-9))
    return xs[k], xs[B - 1 - k]


def one_sided_bound(reps, alpha, direction):
    """单侧不插值界：k = floor(α·B)；direction>0 取第 k 小（下界），<0 取第 k 大（上界）。"""
    xs = sorted(reps)
    B = len(xs)
    k = int(math.floor(alpha * B + 1e-9))
    return xs[k] if direction > 0 else xs[B - 1 - k]


def directional_bound(reps, alpha, sided, sigma):
    """σ 方向上近 0 的界：单侧用单侧界，双侧用双侧区间的那一端。"""
    if sided == 1:
        return one_sided_bound(reps, alpha, sigma)
    lo, hi = order_interval(reps, alpha)
    return lo if sigma > 0 else hi


def p_value(name, reps):
    sp = SPECS[name]
    return boot_p_one(reps, sp["direction"]) if sp["sided"] == 1 else boot_p_two(reps)


def strength_of(sigma, near, point, m):
    if sigma * near > m:
        return "bound_exceeds"
    if sigma * point >= m:
        return "point_reaches"
    return "below"


def judge(name, point, reps, alpha):
    """完整题子集上的判定：rejected（Holm 意义的拒绝）、sign（0＝不确定）、strength、near、label。"""
    sp = SPECS[name]
    out = {"alpha": alpha, "sided": sp["sided"]}
    if point is None or not reps:
        out.update({"rejected": False, "sign": 0, "strength": None, "near": None, "label": "不确定（无共同完整题）"})
        return out
    if sp["sided"] == 1:
        d = sp["direction"]
        b, b_opp = one_sided_bound(reps, alpha, d), one_sided_bound(reps, alpha, -d)
        out.update({"bound": b, "bound_opposite": b_opp})
        if d * b > 0:
            sign, near, rejected = d, b, True
        elif -d * b_opp > 0:
            sign, near, rejected = -d, b_opp, False
        else:
            sign, near, rejected = 0, None, False
    else:
        lo, hi = order_interval(reps, alpha)
        out["interval"] = [lo, hi]
        sign, near = (+1, lo) if lo > 0 else ((-1, hi) if hi < 0 else (0, None))
        rejected = sign != 0
    out.update({"rejected": rejected, "sign": sign, "near": near})
    if sign == 0:
        out.update({"strength": None, "label": "不确定"})
        return out
    st = strength_of(sign, near, point, sp["min_effect"])
    out.update({"strength": st, "label": "%s：%s" % (sp["words"][sign], STRENGTH_WORDS[st])})
    return out


def protected_strength(name, sigma, point_worst, cons_bound):
    """缺失保护下保留的强度（c 第二轮 B3）：σ·b_c ≤ 0 → None（方向不保留）；σ·b_c > 阈值 → bound_exceeds；
    否则 σ·点值最不利界 ≥ 阈值 → point_reaches；否则 below。"""
    m = SPECS[name]["min_effect"]
    if cons_bound is None or sigma * cons_bound <= 0:
        return None
    if sigma * cons_bound > m:
        return "bound_exceeds"
    if point_worst is not None and sigma * point_worst >= m:
        return "point_reaches"
    return "below"


def protect(name, j, cells, planned, pairs, cfg, B=B_DEFAULT, seed=SEED):
    """对完整题子集判定 j 做缺失保护。返回 dict(label, n_missing_cells, point_bounds, conservative_bound, …)。"""
    sigma = j.get("sign", 0)
    pb = missing_bounds(name, cells, planned, cfg)
    out = {"n_missing_cells": pb["n_missing_cells"], "n_pairs_with_missing": pb["n_pairs_with_missing"],
           "point_bounds": [pb["min"], pb["max"]], "substitution": pb["substitution"]}
    if not sigma:
        out.update({"label": j["label"], "retained_strength": None})
        return out
    if pb["n_missing_cells"] == 0:
        out.update({"conservative_bound": j["near"], "label": j["label"], "retained_strength": j["strength"]})
        return out
    sp = SPECS[name]
    reps_c, mean_c = conservative_bootstrap(name, cells, planned, pairs, cfg, sigma, B, seed)
    cb = directional_bound(reps_c, j["alpha"], sp["sided"], sigma)
    u = pb["min"] if sigma > 0 else pb["max"]
    ps = protected_strength(name, sigma, u, cb)
    out.update({"sigma": sigma, "conservative_mean": mean_c, "conservative_bound": cb, "point_worst": u})
    if ps is None:
        out["retained_strength"] = None
        out["label"] = "证据不足（缺失按最不利值代入后区间越过 0；完整题子集判定：%s）" % j["label"]
        return out
    capped = ps if STRENGTH_RANK[ps] <= STRENGTH_RANK[j["strength"]] else j["strength"]
    out["retained_strength"] = capped
    kept = "%s：%s%s" % (sp["words"][sigma], STRENGTH_WORDS[capped], MISSING_SUFFIX)
    if capped == j["strength"]:
        out["label"] = kept
    else:
        out["label"] = "证据不足（缺失保护后不保留「%s」；保留：%s）" % (STRENGTH_WORDS[j["strength"]], kept)
    return out


P_NOTE = ("bootstrap p：双侧 min(1, 2·min(P(r≤0), P(r≥0)))，单侧 P(d·r≤0)；B=5000 时分辨率 0.0002–0.0004，p=0 只表示没有重复"
          "落在 0 或另一侧。区间与界用不插值的次序统计量（双侧 k=floor(α·B/2)，单侧 k=floor(α·B)），与 p 同一套计数。"
          "Holm 的拒绝状态按完整题子集定；最终判定再经缺失保护：缺失贡献按最不利值代入后重做整簇 bootstrap（保守区间），"
          "「区间下界超过阈值（缺失按最不利值代入）」只在保守界严格超过阈值时给出；complete_subset 与 missing_protection 分开列出。"
          "家族区间是 Holm 逐级调整水平后的区间，不是联合置信区间。判定用语里的「区间下界」按判定方向取号。"
          "家族只控制每个配置内 {H1,H2,H4a,H4b} 的错误率；跨配置只作描述。")


def holm_assign(rows, alpha=ALPHA):
    """rows 需含 test、point、reps、p；就地写入 rank、alpha_adj、ci_level、judgment、holm_stopped、raw、verdict_before_bounds。
    只用完整题子集（纯函数，不看缺失）；最终判定由 finalize_rows 加缺失保护。"""
    order = sorted(range(len(rows)), key=lambda i: (rows[i]["p"], i))
    m, failed = len(rows), False
    for rank, i in enumerate(order):
        r = rows[i]
        a_i = alpha / (m - rank)
        r["rank"], r["alpha_adj"], r["ci_level"] = rank, a_i, 1 - a_i
        j = judge(r["test"], r["point"], r["reps"], a_i)
        r["judgment"] = j
        r["raw"] = {"ci95_two_sided": list(order_interval(r["reps"], alpha)) if r["reps"] else None,
                    "one_sided_95": (one_sided_bound(r["reps"], alpha, SPECS[r["test"]]["direction"])
                                     if r["reps"] and SPECS[r["test"]]["sided"] == 1 else None)}
        r["holm_stopped"] = failed
        if failed:
            r["verdict_before_bounds"] = "不确定（Holm：前序检验未拒绝）"
            continue
        if not j["rejected"]:
            failed = True
        r["verdict_before_bounds"] = j["label"]
    return rows


def finalize_rows(rows, cells, planned, pairs, B=B_DEFAULT, seed=SEED, planned_by_test=None):
    """缺失保护与反方向描述（PLAN v0.4 第 1、4 节；c 第二轮 B2、Q1）。"""
    for r in rows:
        name, cfg, j = r["test"], r["config"], r["judgment"]
        row_planned = (planned_by_test or {}).get(name, planned)
        sp = SPECS[name]
        r["complete_subset"] = {"n": r["n_common"], "point": r["point"], "p": r["p"], "alpha": r["alpha_adj"],
                                "interval_two_sided": (list(order_interval(r["reps"], r["alpha_adj"])) if r["reps"]
                                                       else None),
                                "judgment": j["label"]}
        if r["holm_stopped"]:
            r["missing_protection"] = protect(name, {"sign": 0, "label": r["verdict_before_bounds"]}, cells, row_planned,
                                              pairs, cfg, B, seed)
            r["verdict"] = r["verdict_before_bounds"]
        else:
            r["missing_protection"] = protect(name, j, cells, row_planned, pairs, cfg, B, seed)
            r["verdict"] = r["missing_protection"]["label"]
        r["opposite_direction"] = None
        opp_strength = None
        if sp["sided"] == 1 and j.get("sign") == -sp["direction"]:
            pr = protect(name, j, cells, row_planned, pairs, cfg, B, seed)
            r["opposite_direction"] = pr["label"] + "（描述；未作确认性拒绝）"
            opp_strength = pr.get("retained_strength")
        # 结构化的最终状态（c 第三轮 N-S1：统计时不要从判定文字里找子串）
        holm = "stopped" if r["holm_stopped"] else ("rejected" if j["rejected"] else "not_rejected")
        kept = r["missing_protection"].get("retained_strength") if holm == "rejected" else None
        r["final_state"] = {"holm": holm, "sign": j.get("sign", 0), "complete_strength": j.get("strength"),
                            "retained_strength": kept, "directional": kept is not None,
                            "downgraded": holm == "rejected" and kept != j.get("strength"),
                            "opposite_retained_strength": opp_strength}
    return rows


def analyse_family(tests, cells, planned, pairs, B=B_DEFAULT, seed=SEED, alpha=ALPHA, planned_by_test=None):
    rows = []
    for name, cfg in tests:
        row_planned = (planned_by_test or {}).get(name, planned)
        keys = common_complete(name, cells, row_planned, cfg)
        point = stat(name, cells, keys, cfg) if keys else None
        reps = cluster_bootstrap(name, cells, keys, pairs, cfg, B=B, seed=seed) if point is not None else []
        rows.append({"test": name, "config": cfg, "sided": SPECS[name]["sided"],
                     "direction": SPECS[name]["direction"], "min_effect": SPECS[name]["min_effect"],
                     "n_planned": len(row_planned), "n_common": len(keys),
                     "n_clusters": len({pairs[k]["cluster"] for k in keys}), "point": point, "reps": reps, "B": B,
                     "p": p_value(name, reps) if reps else 1.0,
                     "companion": companion(name, cells, keys, cfg, row_planned)})
    holm_assign(rows, alpha)
    finalize_rows(rows, cells, planned, pairs, B, seed, planned_by_test)
    for r in rows:
        r.pop("reps")
    return rows


def speech_sensitivity(cells, planned, pairs, configs, split_items, speech_ids, main_families, B=B_DEFAULT, seed=SEED):
    """§5：H1/H2/H4b 去掉任一所选 S/W 属于台词清单的对；四项 Holm 家族保持冻结。"""
    by_cfg = planned if isinstance(planned, dict) else {cfg: planned for cfg in configs}
    union = {k for ks in by_cfg.values() for k in ks}
    excluded = sorted(it["key"] for it in split_items if it["key"] in union
                      and any(it[t]["id"] in speech_ids for t in TYPES))
    out = {"excluded_keys": excluded, "update_ids": sorted(speech_ids),
           "note": "Holm remains {H1,H2,H4a,H4b} per config; H4a retains its main sample; exclusions are not missing cells.",
           "families": {}, "comparison": {}}
    for family, tests in families_for(configs).items():
        cfg = tests[0][1]
        keys = by_cfg[cfg]
        kept = [k for k in keys if k not in set(excluded)]
        plans = {name: kept for name in ("H1", "H2", "H4b")}
        rows = analyse_family(tests, cells, keys, pairs, B, seed, planned_by_test=plans)
        out["families"][family] = {"members": tests, "rows": rows}
        main = {r["test"]: r for r in main_families[family]["rows"]}
        out["comparison"][family] = {r["test"]: {
            "main": {f: main[r["test"]][f] for f in ("point", "n_planned", "n_common", "verdict", "final_state")},
            "sensitivity": {f: r[f] for f in ("point", "n_planned", "n_common", "verdict", "final_state")},
            "conclusion_changed": main[r["test"]]["final_state"] != r["final_state"]}
            for r in rows if r["test"] in plans}
    return out


def descriptive_contrasts(cells, cfg, keys, pairs, B=B_DEFAULT, seed=SEED):
    """block A 点估计及普通双侧 95% 区间；不形成新的 Holm 家族。"""
    rows = {}
    for name in FAMILY_TESTS:
        complete = common_complete(name, cells, keys, cfg)
        point = stat(name, cells, complete, cfg) if complete else None
        reps = cluster_bootstrap(name, cells, complete, pairs, cfg, B, seed) if complete else []
        bounds = missing_bounds(name, cells, keys, cfg)
        conservative = None
        if keys:
            low, _ = conservative_bootstrap(name, cells, keys, pairs, cfg, 1, B, seed)
            high, _ = conservative_bootstrap(name, cells, keys, pairs, cfg, -1, B, seed)
            conservative = [order_interval(low, ALPHA)[0], order_interval(high, ALPHA)[1]]
        rows[name] = {'n_planned': len(keys), 'n_common': len(complete), 'point': point,
                      'complete_subset_ci95': list(order_interval(reps, ALPHA)) if reps else None,
                      'missing_bounds': bounds, 'conservative_ci95': conservative}
    return {'label': '描述，对照 codex 用', 'formal_block': 'A', 'rows': rows, 'B': B}


# ---------------- 描述量 ----------------

def _rate(xs, pred):
    return sum(1 for x in xs if pred(x)) / len(xs) if xs else None


def _mean(xs):
    xs = [x for x in xs if x is not None]
    return statistics.fmean(xs) if xs else None


def move_summary(cells, cfg, keys, pres, ask):
    """在给定题集上：s̄ 平均、Δ_S、Δ_W（只在先验也有的题上）、方向一致率、反向率、|Δ|、先验缺失数。"""
    moves, absd, dS, dW = [], [], [], []
    for k in keys:
        for t, acc in (("S", dS), ("W", dW)):
            d = delta(cells, cfg, k, pres, t, ask)
            if d is not None:
                acc.append(d)
                moves.append(SIGN[t] * d)
                absd.append(abs(d))
    return {"n": len(keys), "mean_s_item": _mean([s_item(cells, cfg, k, pres, ask) for k in keys]),
            "n_prior_missing": sum(1 for k in keys if prior_cell(cfg, k, ask) not in cells),
            "mean_delta_S": _mean(dS), "mean_delta_W": _mean(dW), "n_delta": len(dS),
            "consistent_rate": _rate(moves, lambda x: x > 0), "reverse_rate": _rate(moves, lambda x: x < 0),
            "mean_abs_delta": _mean(absd),
            "note_S_not_rising": bool(dS) and _mean(dS) <= 0, "note_W_not_falling": bool(dW) and _mean(dW) >= 0}


def endpoint_parts(cells, cfg, keys, ask):
    """H4a 的配套分项：先验、陈述 S、陈述 W 的端点率与 e 的平均（同一题集）。"""
    out = {"n": len(keys)}
    for p, t, w in H4A_WEIGHTS:
        vs = [cells[(cfg, k, p, t, ask)] for k in keys if (cfg, k, p, t, ask) in cells]
        out["%s|%s" % (p, t)] = _rate(vs, is_endpoint)
    out["e_mean"] = _mean([endpoint_item(cells, cfg, k, ask) for k in keys])
    return out


def companion(name, cells, keys, cfg, planned=None):
    """主对比在其共同完整题集上的配套分项（c 第二轮 S2；PLAN v0.4「先验缺失另行报告」）。"""
    out = {"n_common": len(keys)}
    if planned is not None:
        out["n_planned"] = len(planned)
    if name == "H1":
        out["stated_direct"] = move_summary(cells, cfg, keys, "stated", "direct")
    elif name == "H2":
        out["stated_direct"] = move_summary(cells, cfg, keys, "stated", "direct")
        out["reported_direct"] = move_summary(cells, cfg, keys, "reported", "direct")
        out["reading"] = h2_reading(cells, cfg, keys)["reading"] if keys else None
    elif name == "H4a":
        for a in ASKS:
            out[a] = endpoint_parts(cells, cfg, keys, a)
        if keys:
            out["e_direct_minus_e_multi"] = out["direct"]["e_mean"] - out["multi"]["e_mean"]
    elif name == "H4b":
        for a in ASKS:
            out["stated_" + a] = move_summary(cells, cfg, keys, "stated", a)
    return out


def condition_table(cells, cfg, keys):
    """全可用格的条件表（分母是各条件自己的可用题；与主统计量的题集不一定相同——同题集的分项见各行的 companion）。"""
    out = {"_denominator": "each condition's own available pairs (pairs with prior and that posterior)"}
    for pres in PRES:
        for ask in ASKS:
            pooled = []
            for t in TYPES:
                ds = [d for d in (delta(cells, cfg, k, pres, t, ask) for k in keys) if d is not None]
                ss = [SIGN[t] * d for d in ds]
                pooled += ss
                out["%s|%s|%s" % (pres, ask, t)] = {
                    "n": len(ds), "mean_delta": _mean(ds), "mean_s": _mean(ss),
                    "consistent_rate": _rate(ss, lambda x: x > 0), "reverse_rate": _rate(ss, lambda x: x < 0),
                    "tie_rate": _rate(ss, lambda x: x == 0), "mean_abs_delta": _mean([abs(d) for d in ds])}
            dvals = [2 * v for v in (s_item(cells, cfg, k, pres, ask) for k in keys) if v is not None]
            dS = out["%s|%s|S" % (pres, ask)]["mean_delta"]
            dW = out["%s|%s|W" % (pres, ask)]["mean_delta"]
            out["%s|%s|pooled" % (pres, ask)] = {
                "n_moves": len(pooled), "consistent_rate": _rate(pooled, lambda x: x > 0),
                "reverse_rate": _rate(pooled, lambda x: x < 0), "mean_abs_move": _mean([abs(x) for x in pooled]),
                "D_mean_pS_minus_pW": _mean(dvals), "n_D": len(dvals),
                "note_S_not_rising": dS is not None and dS <= 0, "note_W_not_falling": dW is not None and dW >= 0}
    return out


def h2_reading(cells, cfg, keys):
    """H2 的解释规则（PLAN 第 1 节）：在 H2 的共同完整题集上，转述下反向率高于陈述 → 「转述改变方向」，不写「打折扣」。
    反向率与 |Δ| 需要先验；只用该题集里先验也有的题，数目另报。"""
    keys = common_complete("H2", cells, keys, cfg)
    res = {"n_common": len(keys)}
    for pres in PRES:
        res[pres] = move_summary(cells, cfg, keys, pres, "direct")
        res[pres]["mean_s"] = res[pres]["mean_s_item"]
    st, rp = res["stated"], res["reported"]
    if not keys or st["reverse_rate"] is None or rp["reverse_rate"] is None:
        res["reading"] = "无共同完整题（或先验全缺）"
    elif rp["reverse_rate"] > st["reverse_rate"]:
        res["reading"] = "转述改变方向（转述下反向率 %.3f > 陈述 %.3f）；不写「打折扣」" % (rp["reverse_rate"], st["reverse_rate"])
    elif rp["mean_s"] < st["mean_s"] and rp["mean_abs_delta"] < st["mean_abs_delta"]:
        res["reading"] = "转述下方向化移动与绝对移动都较小"
    elif rp["mean_s"] < st["mean_s"]:
        res["reading"] = "转述下方向化移动较小，但绝对移动不小于陈述（不能写成移动较少）"
    else:
        res["reading"] = "转述下方向化移动不小于陈述"
    return res


def endpoint_table(cells, cfg, keys):
    """端点率（全可用格；分母各自）：每种问法分别报先验、陈述、转述、后验合并；H4a 同题集的分项见 H4a 行的 companion。"""
    out = {"_denominator": "each cell's own available pairs"}
    for ask in ASKS:
        pri = [cells[prior_cell(cfg, k, ask)] for k in keys if prior_cell(cfg, k, ask) in cells]
        row = {"prior": {"n": len(pri), "rate": _rate(pri, is_endpoint)}}
        allp = []
        for pres in PRES:
            vs = [cells[(cfg, k, pres, t, ask)] for k in keys for t in TYPES if (cfg, k, pres, t, ask) in cells]
            allp += vs
            row[pres] = {"n": len(vs), "rate": _rate(vs, is_endpoint)}
        row["posterior_all"] = {"n": len(allp), "rate": _rate(allp, is_endpoint)}
        es = [e for e in (endpoint_item(cells, cfg, k, ask) for k in keys) if e is not None]
        row["h4a_e"] = {"n": len(es), "mean": _mean(es)}
        out[ask] = row
    return out


def candidate_table(cand, cfg, keys):
    """多估计的候选层描述量（只作描述）：加权端点质量、加权标准差的平均，按先验／陈述／转述。"""
    out = {}
    for pres in ("prior",) + PRES:
        uts = ("-",) if pres == "prior" else TYPES
        xs = [cand[(cfg, k, pres, t, "multi")] for k in keys for t in uts if (cfg, k, pres, t, "multi") in cand]
        out[pres] = {"n": len(xs), "mean_endpoint_mass": _mean([x["endpoint_mass"] for x in xs]),
                     "mean_weighted_sd": _mean([x["weighted_sd"] for x in xs]),
                     "mean_weight_sum": _mean([x.get("weight_sum") for x in xs]),
                     "n_weight_sum_known": sum(x.get("weight_sum_in_tolerance") is not None for x in xs),
                     "weight_sum_in_tolerance_rate": _mean([x.get("weight_sum_in_tolerance") for x in xs])}
    return out


def strata_points(cells, planned, pairs, configs, field="source_split"):
    """按来源切分（dev／test）分层的点估计与共同完整题数，只作描述（c 第二轮 S4）。"""
    by_cfg = planned if isinstance(planned, dict) else {cfg: planned for cfg in configs}
    union = {k for ks in by_cfg.values() for k in ks}
    strata = sorted({pairs[k].get(field) for k in union})
    out = {}
    for sv in strata:
        ks = [k for k in union if pairs[k].get(field) == sv]
        row = {"n_planned": len(ks)}
        for cfg in configs:
            cfg_keys = [k for k in by_cfg[cfg] if pairs[k].get(field) == sv]
            for name in FAMILY_TESTS:
                ck = common_complete(name, cells, cfg_keys, cfg)
                row["%s|%s" % (cfg, name)] = {"n_planned": len(cfg_keys), "n_common": len(ck),
                                               "point": stat(name, cells, ck, cfg) if ck else None}
        out[str(sv)] = row
    return out


def repeat_noise(cells, rep_cells, cfg, keys):
    """调用间变异：重复轮 r1 − 主轮 r0，按条件；另比较题级 s̄（直接、陈述）的调用间差与题间标准差。"""
    out = {}
    conds = [("prior", "-", a) for a in ASKS] + [(p, t, a) for p in PRES for t in TYPES for a in ASKS]
    for pres, ut, ask in conds:
        ds = [rep_cells[(cfg, k, pres, ut, ask)] - cells[(cfg, k, pres, ut, ask)] for k in keys
              if (cfg, k, pres, ut, ask) in rep_cells and (cfg, k, pres, ut, ask) in cells]
        out["%s|%s|%s" % (pres, ut, ask)] = {
            "n": len(ds), "mean": _mean(ds), "mean_abs": _mean([abs(x) for x in ds]),
            "sd": statistics.stdev(ds) if len(ds) > 1 else None}
    s0 = {k: s_item(cells, cfg, k, "stated", "direct") for k in keys}
    s1 = {k: s_item(rep_cells, cfg, k, "stated", "direct") for k in keys}
    ds = [s1[k] - s0[k] for k in keys if s0[k] is not None and s1[k] is not None]
    between = [v for v in s0.values() if v is not None]
    out["s_item|stated|direct"] = {"n": len(ds), "mean_abs_call_diff": _mean([abs(x) for x in ds]),
                                   "sd_call_diff": statistics.stdev(ds) if len(ds) > 1 else None,
                                   "sd_between_items_r0": statistics.stdev(between) if len(between) > 1 else None}
    return out


def missing_rates(records, planned_units=None):
    """按 (配置, 呈现, 更新类型, 问法, 轮次) 报最终状态计数与缺失率。planned_units：{配置: 计划 unit 集合}，给出时以计划
    unit 为分母，未尝试的计为 not_attempted（c 第二轮 Q2）。"""
    g = defaultdict(Counter)
    seen = defaultdict(set)
    for r in records:
        g[(r["config"], r["pres"], r["utype"], r["ask"], r["round"])][r["status"]] += 1
        seen[r["config"]].add(r["unit"])
    for cfg, units in (planned_units or {}).items():
        for u in units:
            if u not in seen[cfg]:
                k, pres, ut, ask, rnd = u.split("|")
                g[(cfg, pres, ut, ask, rnd)]["not_attempted"] += 1
    return {"|".join(k): {"n": sum(c.values()), "missing_rate": 1 - c["ok"] / sum(c.values()), "status": dict(c)}
            for k, c in sorted(g.items())}


def cells_from_records(records):
    """只取 status=ok 的记录。返回 (cells, rep_cells, cand, pairs)。"""
    cells, rep_cells, cand, pairs = {}, {}, {}, {}
    for r in records:
        pairs[r["key"]] = {"cluster": r["cluster"], "use": r["use"]}
        if r["status"] != "ok":
            continue
        c = (r["config"], r["key"], r["pres"], r["utype"], r["ask"])
        if r["round"] == "r0":
            cells[c] = r["result"]["value"]
            if r["ask"] == "multi":
                cand[c] = {"endpoint_mass": r["result"]["endpoint_mass"], "weighted_sd": r["result"]["weighted_sd"],
                           "weight_sum": r["result"].get("weight_sum"),
                           "weight_sum_in_tolerance": r["result"].get("weight_sum_in_tolerance")}
        else:
            rep_cells[c] = r["result"]["value"]
    return cells, rep_cells, cand, pairs


def cross_config_summary(families):
    """研究层面只作描述（PLAN 第 5 节）：每项假设在各配置上的最终判定与反方向描述（c 第二轮 Q1）。"""
    out = defaultdict(dict)
    for fam in families.values():
        for r in fam.get("rows", []):
            out[r["test"]][r["config"]] = {"verdict": r["verdict"],
                                                                 "opposite_direction": r.get("opposite_direction")}
    return dict(out)


# ---------------- 功效情景（正态近似；阶段 B 用开发集方差填） ----------------

def n_needed(sd, effect, alpha, sided, power=0.80):
    z = statistics.NormalDist()
    za = z.inv_cdf(1 - alpha / sided)
    return math.ceil(((za + z.inv_cdf(power)) * sd / effect) ** 2)


def power_given_n(sd, n, effect, alpha, sided):
    z = statistics.NormalDist()
    se = sd / math.sqrt(n)
    za = z.inv_cdf(1 - alpha / sided)
    p = 1 - z.cdf(za - effect / se)
    if sided == 2:
        p += z.cdf(-za - effect / se)
    return p


def power_scenarios(cells, cfg, keys, n_formal=120, m_family=4, alpha=ALPHA):
    """按开发集的题级贡献标准差，报每项对比在 n_formal 簇时的功效（Holm 首步 α/m 与末步 α）与 80% 功效所需簇数。"""
    out = {}
    for name in FAMILY_TESTS:
        ck = common_complete(name, cells, keys, cfg)
        vals = [contrib(name, cells, k, cfg) for k in ck]
        if len(vals) < 2:
            out[name] = {"n": len(vals)}
            continue
        sd = statistics.stdev(vals)
        sp = SPECS[name]
        row = {"n": len(vals), "mean": statistics.fmean(vals), "sd": sd}
        if sd > 0:
            for lab, a in (("first_step", alpha / m_family), ("last_step", alpha)):
                row[lab] = {"alpha": a, "power_at_n_formal": power_given_n(sd, n_formal, sp["min_effect"], a, sp["sided"]),
                            "n_for_80pct": n_needed(sd, sp["min_effect"], a, sp["sided"])}
        row["n_formal"] = n_formal
        out[name] = row
    return out
