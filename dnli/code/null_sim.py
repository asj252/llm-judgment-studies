"""零效应模拟（v0.6 删除 H3 校准入口）（c 第一轮建议 14、c 第二轮 S5、c 第三轮 N-S1 与 Q2；PLAN v0.5 第 1、5 节）。只用标准库。

用法：
  python -I -X utf8 -B null_sim.py [每情景模拟次数=1000] [B=1000] [输出=null_sim.json]          # 六个零效应情景

零效应的构造：每对一个潜在先验 p₀；同一对的全部后验格（陈述／转述 × S／W × 直接／多估计）在给定 p₀ 时
独立同分布，所以 H1、H2、H4a、H4b 的总体值都恰为 0。每次模拟跑一个配置家族 {H1,H2,H4a,H4b}（Holm），
走 analysis.analyse_family 的完整路径（完整题子集 bootstrap、Holm、缺失保护、反方向描述）。
情景（离散端点、并列 p、不同缺失结构、簇结构）：
  continuous           连续值、无缺失、120 个单题簇
  discrete             35% 的 p₀ 落在 0／100；值取 5 的倍数；后验一半等于 p₀（大量 0 贡献与并列）；无缺失
  discrete_mcar10      discrete ＋ 每格独立 10% 缺失
  discrete_rep_S30     discrete ＋ 只有转述 S 格 30% 缺失（单一条件的缺失）
  discrete_prior30     discrete ＋ 先验格 30% 缺失
  clustered_mcar10     60 簇 × 2 对、簇内共享 p₀ 成分；discrete ＋ 10% 缺失
计数（c 第三轮 N-S1：只用结构化状态 analysis 行的 final_state，不在判定文字里找子串）：
  rejected             Holm 拒绝（完整题子集；单侧在预测方向，双侧任一方向；未被前序停止）
  directional          缺失保护后仍保留方向（retained_strength 不为空）
  retained_<强度>      缺失保护后保留的强度：bound_exceeds／point_reaches／below
  downgraded           Holm 拒绝但缺失保护后强度降低（含方向不保留）；direction_removed 为其中方向不保留的部分
  opposite_description 单侧反方向描述出现（用该行的 Holm 调整水平，不是固定 .05）
  家族：any_rejection（族错误率）、any_directional、tied_p（家族内 p 并列）
限制（c 第三轮四节）：簇情景只共享 p₀，没有模拟同簇题的共同方向偏移；缺失都是随机缺失，不依赖概率值；没有经过多估计解析。
B 用 1000（正式分析 5000），只为控制耗时。
"""
import argparse
import json
import math
import random
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analysis as A  # noqa: E402

N_PAIRS = 120
SCENARIOS = ("continuous", "discrete", "discrete_mcar10", "discrete_rep_S30", "discrete_prior30", "clustered_mcar10")
STRENGTHS = ("bound_exceeds", "point_reaches", "below")


def _r5(x):
    return float(min(100, max(0, 5 * round(x / 5))))


def simulate(scenario, rng):
    """返回 (cells, pairs, keys)。配置按 A.CONFIGS；power_sim.py 也用它。"""
    clustered = scenario.startswith("clustered")
    discrete = scenario != "continuous"
    keys, pairs, cells = [], {}, {}
    n_cl = N_PAIRS // 2 if clustered else N_PAIRS
    cl_eff = [rng.gauss(0, 20) for _ in range(n_cl)]
    for i in range(N_PAIRS):
        k = "k%03d" % i
        c = i // 2 if clustered else i
        keys.append(k)
        pairs[k] = {"cluster": "c%03d" % c, "use": "formal"}
        if discrete and rng.random() < 0.35:
            p0 = rng.choice((0.0, 100.0))
        else:
            p0 = min(100, max(0, 50 + cl_eff[c] * clustered + rng.gauss(0, 20)))
            p0 = _r5(p0) if discrete else p0
        for cfg in A.CONFIGS:
            for ask in A.ASKS:
                cells[(cfg, k, "prior", "-", ask)] = p0 if not discrete else (p0 if rng.random() < 0.5 else _r5(p0 + rng.gauss(0, 10)))
                for pres in A.PRES:
                    for t in A.TYPES:
                        if discrete:
                            v = p0 if rng.random() < 0.5 else _r5(p0 + rng.gauss(0, 15))
                        else:
                            v = min(100.0, max(0.0, p0 + rng.gauss(0, 10)))
                        cells[(cfg, k, pres, t, ask)] = v
    drop = []
    for c in list(cells):
        if scenario.endswith("mcar10") and rng.random() < 0.10:
            drop.append(c)
        elif scenario == "discrete_rep_S30" and c[2] == "reported" and c[3] == "S" and rng.random() < 0.30:
            drop.append(c)
        elif scenario == "discrete_prior30" and c[2] == "prior" and rng.random() < 0.30:
            drop.append(c)
    for c in drop:
        del cells[c]
    return cells, pairs, keys


def count_row(c, r):
    """按结构化状态累加一行的计数。"""
    fs = r["final_state"]
    c["sims"] += 1
    c["rejected"] += fs["holm"] == "rejected"
    c["directional"] += fs["directional"]
    for st in STRENGTHS:
        c["retained_" + st] += fs["retained_strength"] == st
    c["downgraded"] += fs["downgraded"]
    c["direction_removed"] += fs["holm"] == "rejected" and fs["retained_strength"] is None
    c["opposite_description"] += r["opposite_direction"] is not None
    c["opposite_retained"] += fs["opposite_retained_strength"] is not None
    c["p_zero"] += r["p"] == 0


def run_scenario(scenario, nsim, B, seed):
    rng = random.Random(seed)
    cnt = defaultdict(Counter)
    for s in range(nsim):
        cells, pairs, keys = simulate(scenario, rng)
        fam = A.analyse_family(A.families_for(["olmo2"])["config:olmo2"], cells, keys, pairs, B=B, seed=1000 + s)
        ps = [r["p"] for r in fam]
        f = cnt["family"]
        f["sims"] += 1
        f["any_rejection"] += any(r["final_state"]["holm"] == "rejected" for r in fam)
        f["any_directional"] += any(r["final_state"]["directional"] for r in fam)
        f["tied_p"] += len(set(ps)) < len(ps)
        for r in fam:
            count_row(cnt[r["test"]], r)
    return {k: {kk: (v / c["sims"] if kk != "sims" else v) for kk, v in c.items()} for k, c in cnt.items()}


# ---------------- 二项区间（Clopper–Pearson，精确） ----------------

def _binom_cdf(x, n, p):
    """P(X ≤ x)。"""
    if x < 0:
        return 0.0
    if x >= n:
        return 1.0
    if p <= 0:
        return 1.0
    if p >= 1:
        return 0.0
    lp, lq = math.log(p), math.log1p(-p)
    terms = [math.lgamma(n + 1) - math.lgamma(i + 1) - math.lgamma(n - i + 1) + i * lp + (n - i) * lq
             for i in range(x + 1)]
    m = max(terms)
    return min(1.0, math.exp(m) * math.fsum(math.exp(t - m) for t in terms))


def clopper_pearson(x, n, level=0.95):
    a = (1 - level) / 2

    def bisect(go_up):
        lo, hi = 0.0, 1.0
        for _ in range(100):
            mid = (lo + hi) / 2
            if go_up(mid):
                lo = mid
            else:
                hi = mid
        return (lo + hi) / 2
    # 下界：P(X ≥ x | p) = a（随 p 递增）；上界：P(X ≤ x | p) = a（随 p 递减）
    lower = 0.0 if x == 0 else bisect(lambda p: 1 - _binom_cdf(x - 1, n, p) < a)
    upper = 1.0 if x == n else bisect(lambda p: _binom_cdf(x, n, p) > a)
    return lower, upper


def main_scenarios(nsim, B, out_path):
    res = {"nsim": nsim, "B": B, "n_pairs": N_PAIRS, "alpha": A.ALPHA, "counting": "structured final_state (N-S1)",
           "configs": list(A.CONFIGS), "hypotheses": list(A.FAMILY_TESTS),
           "note": __doc__.split("计数")[0].strip(), "scenarios": {}}
    for i, sc in enumerate(SCENARIOS):
        t0 = time.monotonic()
        res["scenarios"][sc] = run_scenario(sc, nsim, B, 20261100 + i)
        res["scenarios"][sc]["seconds"] = round(time.monotonic() - t0, 1)
        print(sc, json.dumps({k: (v.get("rejected", v.get("any_rejection")) if isinstance(v, dict) else v)
                              for k, v in res["scenarios"][sc].items()}, ensure_ascii=False), flush=True)
    out_path.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


def main():
    nsim = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    B = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    main_scenarios(nsim, B, Path(sys.argv[3]) if len(sys.argv) > 3 else HERE / "null_sim.json")


if __name__ == "__main__":
    main()
