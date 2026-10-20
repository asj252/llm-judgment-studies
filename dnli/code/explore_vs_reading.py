# 探索性（非预注册）：多估计的方向化移动变小，是「平均把分散的候选压向中间」，还是「候选本身也少动了」？
# 对每个 multi unit 计算三种读数：加权平均（预注册读数）、最高权重候选、加权中位数；与直接问法比较 s=(p_S-p_W)/2。
import json, random, statistics, sys
from collections import defaultdict

D = sys.argv[1]


def top(est, w):
    m = max(w)
    tied = [e for e, x in zip(est, w) if x == m]
    return sum(tied) / len(tied)


def wmedian(est, w):
    pairs = sorted(zip(est, w))
    tot = sum(w)
    acc = 0
    for e, x in pairs:
        acc += x
        if acc >= tot / 2:
            return e
    return pairs[-1][0]


out = {}
for cfg in ("qwen3-off", "olmo2", "codex"):
    vals = defaultdict(dict)   # (key, pres) -> {(utype, reading): p}
    cluster = {}
    for line in open(f"{D}/results_formal_{cfg}.jsonl", encoding="utf-8"):
        r = json.loads(line)
        if r["round"] != "r0" or r["status"] != "ok" or r["pres"] == "prior":
            continue
        res = r["result"]
        k = (r["key"], r["pres"])
        cluster[r["key"]] = r["cluster"]
        if r["ask"] == "direct":
            vals[k][(r["utype"], "direct")] = res["value"]
        else:
            est, w = res["estimates"], [max(0.0, x) for x in res["weights"]]
            vals[k][(r["utype"], "mean")] = res["value"]
            vals[k][(r["utype"], "top")] = top(est, w)
            vals[k][(r["utype"], "median")] = wmedian(est, w)
            vals[k][(r["utype"], "spread")] = res["weighted_sd"]
    readings = ("direct", "mean", "top", "median")
    res_cfg = {}
    for pres in ("stated", "reported"):
        rows = []
        for (key, p), v in vals.items():
            if p != pres or not all((u, x) in v for u in "SW" for x in readings):
                continue
            rows.append((cluster[key], {x: (v[("S", x)] - v[("W", x)]) / 2 for x in readings}))
        clusters = defaultdict(list)
        for c, s in rows:
            clusters[c].append(s)
        cl = list(clusters)
        point = {x: statistics.mean(s[x] for _, s in rows) for x in readings}
        rng = random.Random(1)
        boots = defaultdict(list)
        for _ in range(2000):
            samp = [s for c in (rng.choice(cl) for _ in cl) for s in clusters[c]]
            for x in ("mean", "top", "median"):
                boots[x].append(statistics.mean(s[x] - s["direct"] for s in samp))
        ci = {x: sorted(b)[49] for x, b in boots.items()}
        ci_hi = {x: sorted(b)[1949] for x, b in boots.items()}
        res_cfg[pres] = {"n": len(rows), "s": {x: round(point[x], 1) for x in readings},
                         "diff_vs_direct": {x: [round(point[x] - point["direct"], 1), round(ci[x], 1), round(ci_hi[x], 1)]
                                            for x in ("mean", "top", "median")}}
    spreads = [v[(u, "spread")] for v in vals.values() for u in "SW" if (u, "spread") in v]
    res_cfg["mean_candidate_sd"] = round(statistics.mean(spreads), 1)
    out[cfg] = res_cfg
print(json.dumps(out, ensure_ascii=False, indent=1))
