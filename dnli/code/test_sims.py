"""null_sim.py（结构化计数、v0.6 配置与家族）与 power_sim.py 的测试。用法：python -I -X utf8 -B test_sims.py"""
import sys
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import null_sim as N  # noqa: E402
import power_sim as P  # noqa: E402


class StructuredCounting(unittest.TestCase):
    def test_withdrawn_claim_text_not_counted(self):
        """c 第三轮 N-S1 反例：降级文字引用了「区间下界超过阈值」，保留强度却是 point_reaches——不得计为「超过」。"""
        row = {"verdict": "证据不足（缺失保护后不保留「区间下界超过阈值」；保留：预测方向…：点估计达到阈值…）",
               "p": 0.001, "opposite_direction": None,
               "final_state": {"holm": "rejected", "sign": 1, "complete_strength": "bound_exceeds",
                               "retained_strength": "point_reaches", "directional": True, "downgraded": True,
                               "opposite_retained_strength": None}}
        c = Counter()
        N.count_row(c, row)
        self.assertEqual((c["retained_bound_exceeds"], c["retained_point_reaches"], c["downgraded"], c["directional"]),
                         (0, 1, 1, 1))

    def test_stopped_row_not_rejected(self):
        row = {"verdict": "不确定（Holm：前序检验未拒绝）", "p": 0.9, "opposite_direction": "方向相反…（描述；未作确认性拒绝）",
               "final_state": {"holm": "stopped", "sign": -1, "complete_strength": "below", "retained_strength": None,
                               "directional": False, "downgraded": False, "opposite_retained_strength": "below"}}
        c = Counter()
        N.count_row(c, row)
        self.assertEqual((c["rejected"], c["directional"], c["opposite_description"], c["opposite_retained"]),
                         (0, 0, 1, 1))


class Binomial(unittest.TestCase):
    def test_clopper_pearson(self):
        lo, hi = N.clopper_pearson(72, 1000)
        self.assertAlmostEqual(lo, 0.0568, places=3)                  # c 第三轮：约 5.8%–9.0%
        self.assertAlmostEqual(hi, 0.0898, places=3)
        self.assertEqual(N.clopper_pearson(0, 200)[0], 0.0)
        self.assertAlmostEqual(N.clopper_pearson(0, 200)[1], 1 - 0.025 ** (1 / 200), places=6)
        self.assertEqual(N.clopper_pearson(200, 200)[1], 1.0)


class Entrypoints(unittest.TestCase):
    def test_current_configs_and_family(self):
        import random
        cells, pairs, keys = N.simulate("discrete", random.Random(1))
        self.assertEqual({c[0] for c in cells}, set(N.A.CONFIGS))
        r = N.run_scenario("discrete", 2, 50, 1)
        self.assertEqual(set(r), {"family", "H1", "H2", "H4a", "H4b"})

    def test_power_sim_runs_and_is_deterministic(self):
        a = P.run(10, 0.05, nsim=3, B=50)
        self.assertEqual(a, P.run(10, 0.05, nsim=3, B=50))
        self.assertEqual(set(a), {"complete_bound_exceeds", "rejected", "directional", "final_bound_exceeds"})


if __name__ == "__main__":
    unittest.main()
