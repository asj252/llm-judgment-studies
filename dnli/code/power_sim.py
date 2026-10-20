"""最不利值代入的代价：H1 在真效应下保留区间结论的比例（PLAN v0.5 第 1 节；c 第三轮 N-S4）。只用标准库。

用法：python -I -X utf8 -B power_sim.py [每格模拟次数=200] [B=1000] [输出=power_sim.json]
这是 PLAN 第 1 节那组数字（缺失 5%：10 点约 14%、20 点约 100%；缺失 10%：约 0% 与 91%）的生成脚本。
阶段 A 第 12 节写报告时用的是临时目录里的同一段代码；这里把它入库，流程照原样：
- 数据分布：null_sim.simulate("discrete", rng)。120 对、各对为独立簇；35% 的 p₀ 在 0／100，其余取 5 的倍数；
  后验一半等于 p₀、一半为 p₀ 加 N(0, 15) 后取 5 的倍数并截到 [0, 100]。
- 效应：只改配置 olmo2 的陈述 × 直接问法：S 格 + eff、W 格 − eff（截到 [0, 100]），所以题级 s̄ 的真效应约为 eff
  （截断使实际值略小）。
- 缺失（**按「每格」定义**）：生成后对字典里的每一格（全部配置、全部条件）独立以概率 miss 删除。一格＝一个 unit，
  所以「每格缺失率」就是冒烟里「某配置重试后仍缺的 unit ÷ 该配置全部计划 unit」的同一口径（PLAN v0.5 的 2% 规则）；
  H1 每题用 2 格，所以受影响的题约占 2·miss。
- 分析：analysis.analyse_family([("H1", "olmo2")])，B＝1000，第 s 次模拟的 bootstrap 种子＝s。
- 随机数：每个 (eff, miss) 组合各自从 random.Random(SEED=7) 重新开始；不同组合用同一串数据（只差效应与缺失）。
- 计数（结构化，读 final_state）：
  complete_bound_exceeds  完整题子集判「区间下界超过阈值」
  rejected                Holm 拒绝（单项家族）
  directional             缺失保护后仍保留方向
  final_bound_exceeds     缺失保护后保留的强度是「区间下界超过阈值」——PLAN 引用的就是这一列
"""
import json
import random
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import analysis as A  # noqa: E402
import null_sim as N  # noqa: E402

SEED = 7
EFFECTS = (10, 20)
MISSING = (0.0, 0.02, 0.05, 0.10)


def run(eff, miss, nsim=200, B=1000):
    rng = random.Random(SEED)
    c = Counter()
    for s in range(nsim):
        cells, pairs, keys = N.simulate("discrete", rng)
        for (cfg, k, p, t, a), v in list(cells.items()):
            if p == "stated" and a == "direct" and cfg == "olmo2":
                cells[(cfg, k, p, t, a)] = min(100, max(0, v + (eff if t == "S" else -eff)))
        for cc in list(cells):
            if rng.random() < miss:
                del cells[cc]
        r = A.analyse_family([("H1", "olmo2")], cells, keys, pairs, B=B, seed=s)[0]
        fs = r["final_state"]
        c["complete_bound_exceeds"] += fs["complete_strength"] == "bound_exceeds"
        c["rejected"] += fs["holm"] == "rejected"
        c["directional"] += fs["directional"]
        c["final_bound_exceeds"] += fs["retained_strength"] == "bound_exceeds"
    return {k: v / nsim for k, v in sorted(c.items())}


def main():
    nsim = int(sys.argv[1]) if len(sys.argv) > 1 else 200
    B = int(sys.argv[2]) if len(sys.argv) > 2 else 1000
    out_path = Path(sys.argv[3]) if len(sys.argv) > 3 else HERE / "power_sim.json"
    t0 = time.monotonic()
    res = {"nsim": nsim, "B": B, "seed": SEED, "missing_definition": "per cell (= per unit), all configs and conditions",
           "configs": list(A.CONFIGS), "hypotheses": list(A.FAMILY_TESTS),
           "note": __doc__.strip(), "results": {}}
    for eff in EFFECTS:
        for miss in MISSING:
            res["results"]["eff=%d|miss=%.2f" % (eff, miss)] = run(eff, miss, nsim, B)
            print(eff, miss, res["results"]["eff=%d|miss=%.2f" % (eff, miss)], flush=True)
    res["seconds"] = round(time.monotonic() - t0, 1)
    out_path.write_text(json.dumps(res, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
