# Copied unchanged from ../dnli/test_analysis.py for agy regression.
"""analysis.py 的人工数据测试（PLAN v0.4 第 1、4、5 节；c 第一轮阻断 1、2、5、6；c 第二轮 B1–B3、S2、S4、Q1）。
用法：python -I -X utf8 -B test_analysis.py"""
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import analysis as A  # noqa: E402


def put(cells, cfg, k, ask, p0, sS, sW, rS=None, rW=None):
    """写一题一问法的格：先验 p0、陈述 S／W、转述 S／W（转述缺省等于陈述）。"""
    cells[(cfg, k, "prior", "-", ask)] = p0
    cells[(cfg, k, "stated", "S", ask)] = sS
    cells[(cfg, k, "stated", "W", ask)] = sW
    cells[(cfg, k, "reported", "S", ask)] = sS if rS is None else rS
    cells[(cfg, k, "reported", "W", ask)] = sW if rW is None else rW


def pairs_of(keys, cluster=None):
    return {k: {"cluster": (cluster or {}).get(k, "img-" + k), "use": "formal"} for k in keys}


def full(cfg="agy:claude-sonnet-5-5-low", keys=("a", "b", "c"), d=(50, 80, 20), m=(50, 70, 30)):
    cells = {}
    for k in keys:
        put(cells, cfg, k, "direct", *d)
        put(cells, cfg, k, "multi", *m)
    return cells


class PriorCancellation(unittest.TestCase):
    """先验相消；v0.4 推翻「缺先验就排除」（c 第二轮 B2）。"""

    def test_s_item_equals_delta_definition(self):
        cells = {}
        put(cells, "agy:claude-sonnet-5-5-low", "a", "direct", 37, 81, 12)
        s_S = +1 * A.delta(cells, "agy:claude-sonnet-5-5-low", "a", "stated", "S", "direct")
        s_W = -1 * A.delta(cells, "agy:claude-sonnet-5-5-low", "a", "stated", "W", "direct")
        self.assertAlmostEqual(A.s_item(cells, "agy:claude-sonnet-5-5-low", "a", "stated", "direct"), (s_S + s_W) / 2)

    def test_statistics_do_not_depend_on_prior(self):
        c1, c2 = full(), full()
        for k in ("a", "b", "c"):
            c2[("agy:claude-sonnet-5-5-low", k, "prior", "-", "direct")] = 3.0     # 只改直接问法的先验：H4a 的端点指示量随之改变
            c2[("agy:claude-sonnet-5-5-low", k, "prior", "-", "multi")] = 51.0
        for name in ("H1", "H2", "H4b"):
            self.assertEqual(A.stat(name, c1, ["a", "b", "c"], "agy:claude-sonnet-5-5-low"), A.stat(name, c2, ["a", "b", "c"], "agy:claude-sonnet-5-5-low"))
        self.assertNotEqual(A.stat("H4a", c1, ["a", "b", "c"], "agy:claude-sonnet-5-5-low"), A.stat("H4a", c2, ["a", "b", "c"], "agy:claude-sonnet-5-5-low"))

    def test_missing_prior_does_not_exclude_but_is_reported(self):
        cells = full()
        del cells[("agy:claude-sonnet-5-5-low", "b", "prior", "-", "direct")]
        keys = ["a", "b", "c"]
        for name in ("H1", "H2", "H4b"):
            self.assertEqual(A.common_complete(name, cells, keys, "agy:claude-sonnet-5-5-low"), keys, name)
            self.assertEqual(A.missing_bounds(name, cells, keys, "agy:claude-sonnet-5-5-low")["n_missing_cells"], 0)
        self.assertEqual(A.common_complete("H4a", cells, keys, "agy:claude-sonnet-5-5-low"), ["a", "c"])
        comp = A.companion("H1", cells, keys, "agy:claude-sonnet-5-5-low")["stated_direct"]
        self.assertEqual((comp["n"], comp["n_prior_missing"], comp["n_delta"]), (3, 1, 2))

    def test_c_round2_B2_counterexample(self):
        """c 第二轮 B2：40 对完整、贡献 20；80 对只缺先验，40 对 +50、40 对 −50。v0.3 只用前 40 对并判「区间下界超过阈值」；
        v0.4 用全部 120 对，点估计 6.667，不得判「区间下界超过阈值」。"""
        cells, keys = {}, []
        for i in range(120):
            k = "k%03d" % i
            keys.append(k)
            v = 20 if i < 40 else (50 if i < 80 else -50)
            put(cells, "agy:claude-sonnet-5-5-low", k, "direct", 50, 50 + v, 50 - v)
            if i >= 40:
                del cells[("agy:claude-sonnet-5-5-low", k, "prior", "-", "direct")]
        rows = A.analyse_family([("H1", "agy:claude-sonnet-5-5-low")], cells, keys, pairs_of(keys), B=5000)
        r = rows[0]
        self.assertEqual(r["n_common"], 120)
        self.assertAlmostEqual(r["point"], 20 / 3)
        self.assertNotEqual(r["judgment"]["strength"], "bound_exceeds")
        self.assertNotIn("区间下界超过阈值", r["verdict"])
        lo, hi = r["raw"]["ci95_two_sided"]
        self.assertLess(lo, 0)                                   # c：全部 120 对的 95% 双侧区间约 [−0.75, 14.0]
        self.assertAlmostEqual(hi, 14, delta=1.5)
        self.assertEqual(r["companion"]["stated_direct"]["n_prior_missing"], 80)


class CounterExamples(unittest.TestCase):
    """c 第一轮阻断 2 的两组反例。"""

    def test_both_types_rise_but_D_positive(self):
        keys = ["k%d" % i for i in range(10)]
        cells = {}
        for k in keys:
            put(cells, "agy:claude-sonnet-5-5-low", k, "direct", 50, 80, 70)
        self.assertAlmostEqual(A.stat("H1", cells, keys, "agy:claude-sonnet-5-5-low"), 5.0)
        t = A.condition_table(cells, "agy:claude-sonnet-5-5-low", keys)
        w = t["stated|direct|W"]
        self.assertEqual((w["mean_delta"], w["reverse_rate"], w["consistent_rate"]), (20.0, 1.0, 0.0))
        pooled = t["stated|direct|pooled"]
        self.assertAlmostEqual(pooled["D_mean_pS_minus_pW"], 10.0)
        self.assertTrue(pooled["note_W_not_falling"])
        comp = A.companion("H1", cells, keys, "agy:claude-sonnet-5-5-low")["stated_direct"]
        self.assertTrue(comp["note_W_not_falling"])
        self.assertAlmostEqual(comp["reverse_rate"], 0.5)
        reps = A.cluster_bootstrap("H1", cells, keys, pairs_of(keys), "agy:claude-sonnet-5-5-low", B=200)
        j = A.judge("H1", 5.0, reps, 0.05)
        self.assertEqual(j["strength"], "point_reaches")
        self.assertIn("点估计达到阈值", j["label"])

    def test_reported_reverses_direction(self):
        keys = ["k%d" % i for i in range(8)]
        cells = {}
        for k in keys:
            put(cells, "agy:claude-opus-5-5-low", k, "direct", 50, 80, 20, rS=10, rW=90)
        self.assertAlmostEqual(A.stat("H2", cells, keys, "agy:claude-opus-5-5-low"), 70.0)
        t = A.condition_table(cells, "agy:claude-opus-5-5-low", keys)
        self.assertAlmostEqual(t["stated|direct|pooled"]["D_mean_pS_minus_pW"]
                               - t["reported|direct|pooled"]["D_mean_pS_minus_pW"], 140.0)
        r = A.h2_reading(cells, "agy:claude-opus-5-5-low", keys)
        self.assertEqual((r["stated"]["mean_abs_delta"], r["reported"]["mean_abs_delta"]), (30.0, 40.0))
        self.assertEqual((r["stated"]["reverse_rate"], r["reported"]["reverse_rate"]), (0.0, 1.0))
        self.assertTrue(r["reading"].startswith("转述改变方向"))
        self.assertIn("不写「打折扣」", r["reading"])
        self.assertTrue(A.companion("H2", cells, keys, "agy:claude-opus-5-5-low")["reading"].startswith("转述改变方向"))

    def test_h2_reading_other_branches(self):
        keys = ["a", "b"]
        cells = {}
        for k in keys:
            put(cells, "agy:claude-sonnet-5-5-low", k, "direct", 50, 80, 20, rS=60, rW=40)
        self.assertEqual(A.h2_reading(cells, "agy:claude-sonnet-5-5-low", keys)["reading"], "转述下方向化移动与绝对移动都较小")
        cells = {}
        # 无反向时 |Δ| 的平均等于 s 的平均；这一支只在两种呈现都有反向、且转述反向率不更高时出现
        put(cells, "agy:claude-sonnet-5-5-low", "a", "direct", 50, 90, 55, rS=30, rW=20)
        put(cells, "agy:claude-sonnet-5-5-low", "b", "direct", 50, 90, 55, rS=30, rW=20)
        self.assertIn("不能写成移动较少", A.h2_reading(cells, "agy:claude-sonnet-5-5-low", keys)["reading"])


class EndpointsAndMulti(unittest.TestCase):
    def test_c_round2_B1_counterexample(self):
        """c 第二轮 B1：两种问法先验 50；直接陈述 100/0、转述 50/50；多估计陈述 50/50、转述 100/0 → H4a = 0.5。"""
        cells = {}
        put(cells, "agy:claude-sonnet-5-5-low", "a", "direct", 50, 100, 0, rS=50, rW=50)
        put(cells, "agy:claude-sonnet-5-5-low", "a", "multi", 50, 50, 50, rS=100, rW=0)
        self.assertAlmostEqual(A.stat("H4a", cells, ["a"], "agy:claude-sonnet-5-5-low"), 0.5)

    def test_reported_missing_does_not_affect_h4a(self):
        cells = full()
        before = A.stat("H4a", cells, ["a", "b", "c"], "agy:claude-sonnet-5-5-low")
        for a in A.ASKS:
            for t in A.TYPES:
                del cells[("agy:claude-sonnet-5-5-low", "b", "reported", t, a)]
        self.assertEqual(A.common_complete("H4a", cells, ["a", "b", "c"], "agy:claude-sonnet-5-5-low"), ["a", "b", "c"])
        self.assertEqual(A.stat("H4a", cells, ["a", "b", "c"], "agy:claude-sonnet-5-5-low"), before)
        self.assertEqual(A.missing_bounds("H4a", cells, ["a", "b", "c"], "agy:claude-sonnet-5-5-low")["n_missing_cells"], 0)

    def test_h4a_weights(self):
        cells = {}
        put(cells, "agy:claude-sonnet-5-5-low", "a", "direct", 99, 100, 2)      # 直接：先验、陈述 S、W 都端点 → e = 1
        put(cells, "agy:claude-sonnet-5-5-low", "a", "multi", 98, 60, 40)       # 多估计：只有先验端点 → e = 0.5
        self.assertAlmostEqual(A.endpoint_item(cells, "agy:claude-sonnet-5-5-low", "a", "direct"), 1.0)
        self.assertAlmostEqual(A.endpoint_item(cells, "agy:claude-sonnet-5-5-low", "a", "multi"), 0.5)
        cells[("agy:claude-sonnet-5-5-low", "a", "reported", "W", "multi")] = 5.0   # 转述不进 H4a
        self.assertAlmostEqual(A.endpoint_item(cells, "agy:claude-sonnet-5-5-low", "a", "multi"), 0.5)
        cells[("agy:claude-sonnet-5-5-low", "a", "stated", "W", "multi")] = 5.0     # 边界 5 算端点；陈述 W 权重 1/4
        self.assertAlmostEqual(A.endpoint_item(cells, "agy:claude-sonnet-5-5-low", "a", "multi"), 0.75)
        comp = A.companion("H4a", cells, ["a"], "agy:claude-sonnet-5-5-low")
        self.assertEqual((comp["multi"]["prior|-"], comp["multi"]["stated|S"], comp["multi"]["stated|W"]), (1.0, 0.0, 1.0))
        self.assertAlmostEqual(comp["e_direct_minus_e_multi"], A.stat("H4a", cells, ["a"], "agy:claude-sonnet-5-5-low"))
        tab = A.endpoint_table(cells, "agy:claude-sonnet-5-5-low", ["a"])
        self.assertEqual(tab["multi"]["reported"]["rate"], 0.5)
        self.assertEqual(tab["direct"]["posterior_all"]["rate"], 1.0)

    def test_aggregate_vs_candidate_endpoint(self):
        """c 第一轮阻断 1：聚合值 40.4 不是端点，候选加权端点质量却是 1；H4a 只用聚合值，候选层只作描述。"""
        cells, cand = {}, {}
        put(cells, "agy:claude-sonnet-5-5-low", "a", "multi", 40.4, 40.4, 40.4)
        for c in list(cells):
            cand[c] = {"endpoint_mass": 1.0, "weighted_sd": 47.0}
        self.assertEqual(A.endpoint_item(cells, "agy:claude-sonnet-5-5-low", "a", "multi"), 0.0)
        ct = A.candidate_table(cand, "agy:claude-sonnet-5-5-low", ["a"])
        self.assertEqual((ct["prior"]["n"], ct["stated"]["n"], ct["reported"]["n"]), (1, 2, 2))
        self.assertEqual(ct["stated"]["mean_endpoint_mass"], 1.0)

    def test_h4b_sign_and_companion(self):
        cells = full(d=(50, 90, 10), m=(50, 60, 40))
        self.assertAlmostEqual(A.stat("H4b", cells, ["a", "b", "c"], "agy:claude-sonnet-5-5-low"), 10 - 40)
        comp = A.companion("H4b", cells, ["a", "b", "c"], "agy:claude-sonnet-5-5-low")
        self.assertEqual((comp["stated_direct"]["mean_s_item"], comp["stated_multi"]["mean_s_item"]), (40.0, 10.0))


class CommonCompleteAndBounds(unittest.TestCase):
    def test_cells_needed_per_test(self):
        self.assertEqual(len(A.cells_needed("H1", "k", "c")), 2)
        self.assertEqual(len(A.cells_needed("H2", "k", "c")), 4)
        with self.assertRaises(ValueError):
            A.cells_needed("H3", "k")
        self.assertEqual(len(A.cells_needed("H4a", "k", "c")), 6)
        self.assertFalse(any(c[2] == "reported" for c in A.cells_needed("H4a", "k", "c")))
        self.assertEqual(len(A.cells_needed("H4b", "k", "c")), 4)
        for name in ("H1", "H2", "H4b"):
            self.assertFalse(any(c[2] == "prior" for c in A.cells_needed(name, "k", "c")), name)

    def test_missing_cell_excludes_only_affected_tests(self):
        cells = full()
        del cells[("agy:claude-sonnet-5-5-low", "b", "reported", "S", "direct")]
        keys = ["a", "b", "c"]
        self.assertEqual(A.common_complete("H1", cells, keys, "agy:claude-sonnet-5-5-low"), keys)
        self.assertEqual(A.common_complete("H2", cells, keys, "agy:claude-sonnet-5-5-low"), ["a", "c"])
        self.assertEqual(A.common_complete("H4a", cells, keys, "agy:claude-sonnet-5-5-low"), keys)
        self.assertEqual(A.common_complete("H4b", cells, keys, "agy:claude-sonnet-5-5-low"), keys)

    def test_linear_bounds_by_hand(self):
        cells = {}
        put(cells, "agy:claude-sonnet-5-5-low", "a", "direct", 50, 60, 40)            # s̄ = 10
        put(cells, "agy:claude-sonnet-5-5-low", "b", "direct", 50, 70, 40)
        del cells[("agy:claude-sonnet-5-5-low", "b", "stated", "S", "direct")]        # s̄_b ∈ [(0−40)/2, (100−40)/2] = [−20, 30]
        b = A.missing_bounds("H1", cells, ["a", "b"], "agy:claude-sonnet-5-5-low")
        self.assertEqual((b["n_missing_cells"], b["min"], b["max"]), (1, -5.0, 20.0))
        self.assertEqual(A.contrib_range("H1", cells, "b", "agy:claude-sonnet-5-5-low"), (-20.0, 30.0, 1))

    def test_linear_bounds_two_missing_opposite_slopes(self):
        cells = {}
        put(cells, "agy:claude-sonnet-5-5-low", "a", "direct", 50, 60, 40)
        del cells[("agy:claude-sonnet-5-5-low", "a", "stated", "S", "direct")]
        del cells[("agy:claude-sonnet-5-5-low", "a", "stated", "W", "direct")]
        b = A.missing_bounds("H1", cells, ["a"], "agy:claude-sonnet-5-5-low")
        self.assertEqual((b["min"], b["max"]), (-50.0, 50.0))

    def test_indicator_bounds(self):
        """H4a 的缺失按端点指示量 0／1 代入（不是 0／100——0 与 100 都是端点）。"""
        cells = {}
        put(cells, "agy:claude-sonnet-5-5-low", "a", "direct", 50, 50, 50)
        put(cells, "agy:claude-sonnet-5-5-low", "a", "multi", 50, 50, 50)
        del cells[("agy:claude-sonnet-5-5-low", "a", "stated", "S", "direct")]       # e_直接 ∈ [0, 0.25]
        del cells[("agy:claude-sonnet-5-5-low", "a", "prior", "-", "multi")]          # e_多估计 ∈ [0, 0.5]
        b = A.missing_bounds("H4a", cells, ["a"], "agy:claude-sonnet-5-5-low")
        self.assertEqual(b["substitution"], [50.0, 0.0])
        self.assertAlmostEqual(b["min"], -0.5)
        self.assertAlmostEqual(b["max"], 0.25)


class MissingProtection(unittest.TestCase):
    """c 第二轮 B2（保守区间：缺失按最不利值代入后重做整簇 bootstrap）与 B3（阈值相等）。"""

    def test_protected_strength_boundaries(self):
        ps = A.protected_strength
        self.assertEqual(ps("H1", +1, 9.0, 5.0), "point_reaches")       # 「超过」：保守界 = 阈值 → 不保留
        self.assertEqual(ps("H1", +1, 9.0, 5.0001), "bound_exceeds")
        self.assertEqual(ps("H1", +1, 5.0, 4.0), "point_reaches")       # 「达到」：最不利点值 = 阈值 → 保留
        self.assertEqual(ps("H1", +1, 4.9999, 4.0), "below")
        self.assertIsNone(ps("H1", +1, 9.0, 0.0))                        # 保守界 = 0 → 方向不保留
        self.assertEqual(ps("H1", -1, -9.0, -5.0), "point_reaches")     # 负方向
        self.assertEqual(ps("H1", -1, -9.0, -5.0001), "bound_exceeds")
        self.assertEqual(ps("H1", -1, -5.0, -1.0), "point_reaches")
        self.assertEqual(ps("H1", -1, -4.9999, -1.0), "below")
        self.assertIsNone(ps("H1", -1, -9.0, 0.0))
        self.assertEqual(ps("H4a", +1, 0.3, 0.10), "point_reaches")     # H4a 阈值 0.10
        self.assertEqual(ps("H4a", +1, 0.10, 0.05), "point_reaches")
        self.assertEqual(ps("H4a", +1, 0.0999, 0.05), "below")
        self.assertEqual(ps("H4a", +1, 0.3, 0.1001), "bound_exceeds")

    def test_c_round2_B3_example(self):
        """c 第二轮 B3：完整题点估计与 bootstrap 都是 10、缺失点值界限 [5, 20]——旧代码保留「区间下界超过阈值」。
        新规则看保守区间：这里 10 对完整（s̄=10）、10 对缺 S 而 W=0（最不利贡献 0），点值界限 [5, 30]，保守平均 5 → 不得「超过」。"""
        cells, keys = {}, []
        for i in range(20):
            k = "k%02d" % i
            keys.append(k)
            put(cells, "agy:claude-sonnet-5-5-low", k, "direct", 50, 60 if i < 10 else 100, 40 if i < 10 else 0)
            if i >= 10:
                del cells[("agy:claude-sonnet-5-5-low", k, "stated", "S", "direct")]
        r = A.analyse_family([("H1", "agy:claude-sonnet-5-5-low")], cells, keys, pairs_of(keys), B=2000)[0]
        self.assertEqual(r["judgment"]["strength"], "bound_exceeds")
        self.assertEqual(r["missing_protection"]["point_bounds"][0], 5.0)
        self.assertNotIn("区间下界超过阈值（缺失按最不利值代入）", r["verdict"])
        self.assertTrue(r["verdict"].startswith("证据不足"))

    def test_posterior_missing_removes_direction(self):
        cells, keys = {}, []
        for i in range(120):
            k = "k%03d" % i
            keys.append(k)
            put(cells, "agy:claude-sonnet-5-5-low", k, "direct", 50, 90, 50)            # s̄ = 20
            if i >= 40:
                del cells[("agy:claude-sonnet-5-5-low", k, "stated", "S", "direct")]     # 最不利 (0 − 50)/2 = −25
        r = A.analyse_family([("H1", "agy:claude-sonnet-5-5-low")], cells, keys, pairs_of(keys), B=1000)[0]
        self.assertIn("区间下界超过阈值", r["complete_subset"]["judgment"])
        self.assertEqual(r["complete_subset"]["n"], 40)
        self.assertAlmostEqual(r["missing_protection"]["conservative_mean"], (40 * 20 - 80 * 25) / 120)
        self.assertTrue(r["verdict"].startswith("证据不足（缺失按最不利值代入后区间越过 0"))

    def test_retained_with_suffix(self):
        cells, keys = {}, []
        for i in range(120):
            k = "k%03d" % i
            keys.append(k)
            put(cells, "agy:claude-sonnet-5-5-low", k, "direct", 50, 80, 20)            # s̄ = 30
            if i >= 110:
                cells[("agy:claude-sonnet-5-5-low", k, "stated", "W", "direct")] = 0.0
                del cells[("agy:claude-sonnet-5-5-low", k, "stated", "S", "direct")]     # 最不利 (0 − 0)/2 = 0
        r = A.analyse_family([("H1", "agy:claude-sonnet-5-5-low")], cells, keys, pairs_of(keys), B=1000)[0]
        self.assertEqual(r["verdict"], "预测方向（陈述下往标签方向移动）：区间下界超过阈值" + A.MISSING_SUFFIX)
        self.assertGreater(r["missing_protection"]["conservative_bound"], 5)

    def test_downgrade_keeps_point_claim_at_equality(self):
        """100 对完整 s̄=10；20 对缺 S、W=40（最不利 −20）：保守平均恰为 5.0（≥ 5，「达到」保留），保守界 ≤ 5（「超过」不保留）。"""
        cells, keys = {}, []
        for i in range(120):
            k = "k%03d" % i
            keys.append(k)
            put(cells, "agy:claude-sonnet-5-5-low", k, "direct", 50, 60 if i < 100 else 90, 40)
            if i >= 100:
                del cells[("agy:claude-sonnet-5-5-low", k, "stated", "S", "direct")]
        r = A.analyse_family([("H1", "agy:claude-sonnet-5-5-low")], cells, keys, pairs_of(keys), B=2000)[0]
        mp = r["missing_protection"]
        self.assertEqual(mp["point_worst"], 5.0)
        self.assertLessEqual(mp["conservative_bound"], 5.0)
        self.assertGreater(mp["conservative_bound"], 0)
        self.assertEqual(mp["retained_strength"], "point_reaches")
        self.assertTrue(r["verdict"].startswith("证据不足（缺失保护后不保留「区间下界超过阈值」；保留："))
        self.assertIn("点估计达到阈值", r["verdict"])

    def test_structured_final_state(self):
        """c 第三轮 N-S1：降级文字里引用了「区间下界超过阈值」，但结构化状态记的是保留下来的强度。"""
        cells, keys = {}, []
        for i in range(120):
            k = "k%03d" % i
            keys.append(k)
            put(cells, "agy:claude-sonnet-5-5-low", k, "direct", 50, 60 if i < 100 else 90, 40)
            if i >= 100:
                del cells[("agy:claude-sonnet-5-5-low", k, "stated", "S", "direct")]
        r = A.analyse_family([("H1", "agy:claude-sonnet-5-5-low")], cells, keys, pairs_of(keys), B=2000)[0]
        self.assertIn("区间下界超过阈值", r["verdict"])                       # 文字里出现（被撤回的结论）
        fs = r["final_state"]
        self.assertEqual((fs["holm"], fs["complete_strength"], fs["retained_strength"], fs["directional"],
                          fs["downgraded"]), ("rejected", "bound_exceeds", "point_reaches", True, True))
        cells2 = {c: v for c, v in cells.items()}
        for i in range(40, 100):
            del cells2[("agy:claude-sonnet-5-5-low", "k%03d" % i, "stated", "S", "direct")]
        fs2 = A.analyse_family([("H1", "agy:claude-sonnet-5-5-low")], cells2, keys, pairs_of(keys), B=500)[0]["final_state"]
        self.assertEqual((fs2["holm"], fs2["retained_strength"], fs2["directional"]), ("rejected", None, False))

    def test_no_missing_label_unchanged(self):
        cells = full(keys=tuple("k%d" % i for i in range(30)))
        keys = ["k%d" % i for i in range(30)]
        r = A.analyse_family([("H1", "agy:claude-sonnet-5-5-low")], cells, keys, pairs_of(keys), B=200)[0]
        self.assertEqual(r["verdict"], r["judgment"]["label"])
        self.assertNotIn(A.MISSING_SUFFIX, r["verdict"])


class Bootstrap(unittest.TestCase):
    def test_whole_cluster_resampling(self):
        """簇 c1 含两题（s̄ 20 与 0），簇 c2 一题（10）：整簇重抽时每次重复都恰为 10；按题重抽则不会。"""
        cells = {}
        put(cells, "agy:claude-sonnet-5-5-low", "k1", "direct", 50, 70, 30)
        put(cells, "agy:claude-sonnet-5-5-low", "k2", "direct", 50, 50, 50)
        put(cells, "agy:claude-sonnet-5-5-low", "k3", "direct", 50, 60, 40)
        pairs = pairs_of(["k1", "k2", "k3"], {"k1": "c1", "k2": "c1", "k3": "c2"})
        reps = A.cluster_bootstrap("H1", cells, ["k1", "k2", "k3"], pairs, "agy:claude-sonnet-5-5-low", B=300)
        self.assertTrue(all(abs(r - 10) < 1e-12 for r in reps))
        reps2 = A.cluster_bootstrap("H1", cells, ["k1", "k2", "k3"], pairs_of(["k1", "k2", "k3"]), "agy:claude-sonnet-5-5-low", B=300)
        self.assertGreater(max(reps2) - min(reps2), 1)

    def test_c_round3_B_changes_verdict(self):
        """c 第三轮 N-B1（说明性）：120 个独立簇，60 对 H1 贡献 +10、60 对 −10，点估计 0；同一种子下 B=1 与 B=5000
        的判定不同——所以 B 必须冻结（入口的拒绝见 test_analyse）。"""
        cells, keys = {}, []
        for i in range(120):
            k = "k%03d" % i
            keys.append(k)
            v = 10 if i < 60 else -10
            put(cells, "agy:claude-sonnet-5-5-low", k, "direct", 50, 50 + v, 50 - v)
        r1 = A.analyse_family([("H1", "agy:claude-sonnet-5-5-low")], cells, keys, pairs_of(keys), B=1)[0]
        r5 = A.analyse_family([("H1", "agy:claude-sonnet-5-5-low")], cells, keys, pairs_of(keys), B=5000)[0]
        self.assertEqual(r1["point"], 0.0)
        self.assertNotEqual(r1["verdict"], r5["verdict"])
        self.assertEqual(r5["verdict"], "不确定")
        self.assertAlmostEqual(r5["p"], 0.5, delta=0.05)

    def test_deterministic(self):
        cells = full()
        p = pairs_of(["a", "b", "c"])
        self.assertEqual(A.cluster_bootstrap("H2", cells, ["a", "b", "c"], p, "agy:claude-sonnet-5-5-low", B=50),
                         A.cluster_bootstrap("H2", cells, ["a", "b", "c"], p, "agy:claude-sonnet-5-5-low", B=50))

    def test_p_and_bound_agree(self):
        """单侧：「界在预测方向越过 0」⇔「p ≤ α」；双侧：「区间不含 0」⇔「p ≤ α」。400 组含 0 值的随机序列。"""
        rng = random.Random(11)
        for B in (100, 101, 999, 5000):
            for alpha in (0.05, 0.025, 0.0167, 0.0125):
                for _ in range(25):
                    mu = rng.uniform(-0.3, 0.3)
                    reps = [round(rng.gauss(mu, 0.15), 1) for _ in range(B)]
                    for d in (+1, -1):
                        b = A.one_sided_bound(reps, alpha, d)
                        self.assertEqual(d * b > 0, A.boot_p_one(reps, d) <= alpha + 1e-12, (B, alpha, d))
                    lo, hi = A.order_interval(reps, alpha)
                    self.assertEqual(lo > 0 or hi < 0, A.boot_p_two(reps) <= alpha + 1e-12, (B, alpha))


class Judgement(unittest.TestCase):
    def test_strength_wording(self):
        self.assertEqual(A.judge("H1", 12.0, [12.0] * 100, 0.05)["strength"], "bound_exceeds")
        self.assertIn("区间下界超过阈值", A.judge("H1", 12.0, [12.0] * 100, 0.05)["label"])
        j = A.judge("H1", 7.4, [2.0] * 10 + [8.0] * 90, 0.05)
        self.assertEqual((j["sign"], j["strength"]), (+1, "point_reaches"))
        self.assertEqual(A.judge("H1", 1.0, [1.0] * 100, 0.05)["strength"], "below")
        self.assertEqual(A.judge("H1", 5.0, [5.0] * 100, 0.05)["strength"], "point_reaches")

    def test_one_sided_opposite_is_not_rejection(self):
        j = A.judge("H2", -8.0, [-8.0] * 100, 0.05)
        self.assertEqual((j["sign"], j["rejected"]), (-1, False))
        self.assertTrue(j["label"].startswith("方向相反"))

    def test_two_sided(self):
        j = A.judge("H4b", -7.0, [-7.0] * 100, 0.05)
        self.assertEqual((j["sign"], j["rejected"]), (-1, True))
        self.assertTrue(j["label"].startswith("多估计 < 直接"))
        j = A.judge("H4b", 3.0, [-1.0] * 3 + [3.0] * 97, 0.05)
        self.assertEqual((j["sign"], j["label"]), (0, "不确定"))
        j = A.judge("H4b", -6.0, [-6.0] * 100, 0.05)
        self.assertIn("多估计 < 直接", j["label"])

    def test_no_data(self):
        self.assertEqual(A.judge("H1", None, [], 0.05)["label"], "不确定（无共同完整题）")


class Holm(unittest.TestCase):
    def rows(self, spec):
        return [{"test": t, "point": pt, "reps": reps, "p": A.p_value(t, reps)} for t, pt, reps in spec]

    def test_levels_and_step_down(self):
        B = 1000
        rows = self.rows([("H1", 20.0, [20.0] * B), ("H2", 6.0, [-1.0] * 15 + [6.0] * (B - 15)),
                          ("H4a", 0.3, [0.3] * B), ("H4b", 9.0, [9.0] * B)])
        A.holm_assign(rows)
        self.assertEqual(sorted(round(r["alpha_adj"], 6) for r in rows), sorted(round(0.05 / k, 6) for k in (4, 3, 2, 1)))
        h2 = [r for r in rows if r["test"] == "H2"][0]
        self.assertEqual(h2["rank"], 3)
        self.assertTrue(all(r["judgment"]["rejected"] for r in rows))

    def test_stop_after_non_rejection_including_opposite(self):
        B = 1000
        rows = self.rows([("H1", 20.0, [20.0] * B), ("H2", -9.0, [-9.0] * B),
                          ("H4b", 9.0, [-1.0] * 30 + [9.0] * (B - 30))])
        A.holm_assign(rows)
        by = {r["test"]: r for r in rows}
        self.assertEqual(by["H4b"]["verdict_before_bounds"], "不确定")
        self.assertEqual(by["H2"]["verdict_before_bounds"], "不确定（Holm：前序检验未拒绝）")
        self.assertTrue(by["H2"]["holm_stopped"])
        self.assertEqual(by["H2"]["judgment"]["sign"], -1)            # 内部仍识别出反方向

    def test_opposite_direction_shown_after_holm_stop(self):
        """c 第二轮 Q1：前序未拒绝、末项明显反方向 → 最终判定为「Holm 前序未拒绝」，但反方向描述照样输出并进跨配置摘要。"""
        rng = random.Random(9)
        keys = ["k%02d" % i for i in range(60)]
        cells = {}
        for k in keys:
            n = rng.uniform(-10, 10)
            put(cells, "agy:claude-sonnet-5-5-low", k, "direct", 50, 50 + n, 50 + rng.uniform(-10, 10), rS=85, rW=15)
            put(cells, "agy:claude-sonnet-5-5-low", k, "multi", 50, 50 + n, 50 + rng.uniform(-10, 10))
        rows = A.analyse_family(A.families_for(["agy:claude-sonnet-5-5-low"])["config:agy:claude-sonnet-5-5-low"], cells, keys, pairs_of(keys), B=500)
        by = {r["test"]: r for r in rows}
        self.assertEqual(by["H2"]["verdict"], "不确定（Holm：前序检验未拒绝）")
        self.assertTrue(by["H2"]["opposite_direction"].startswith("方向相反"))
        self.assertIn("未作确认性拒绝", by["H2"]["opposite_direction"])
        self.assertEqual((by["H2"]["final_state"]["holm"], by["H2"]["final_state"]["directional"]), ("stopped", False))
        self.assertIsNotNone(by["H2"]["final_state"]["opposite_retained_strength"])
        summ = A.cross_config_summary({"config:agy:claude-sonnet-5-5-low": {"rows": rows}})
        self.assertEqual(summ["H2"]["agy:claude-sonnet-5-5-low"]["opposite_direction"], by["H2"]["opposite_direction"])

    def test_families(self):
        f = A.families_for(["agy:claude-sonnet-5-5-low", "agy:claude-opus-5-5-low"])
        self.assertEqual(f, {"config:agy:claude-sonnet-5-5-low": [(t, "agy:claude-sonnet-5-5-low") for t in ("H1", "H2", "H4a", "H4b")],
                             "config:agy:claude-opus-5-5-low": [(t, "agy:claude-opus-5-5-low") for t in ("H1", "H2", "H4a", "H4b")]})
        self.assertEqual(len(A.families_for(list(A.CONFIGS))), 10)
        self.assertNotIn("H3", A.families_for(A.CONFIGS))

    def test_analyse_family_end_to_end(self):
        rng = random.Random(5)
        keys = ["k%02d" % i for i in range(40)]
        cells = {}
        for k in keys:
            for cfg, eff in (("agy:gemini-3.8-flash-low", 10), ("agy:claude-sonnet-5-5-low", 20)):
                put(cells, cfg, k, "direct", 50, 50 + eff + rng.uniform(-3, 3), 50 - eff + rng.uniform(-3, 3),
                    rS=50 + 2 + rng.uniform(-3, 3), rW=50 - 2 + rng.uniform(-3, 3))
                put(cells, cfg, k, "multi", 50, 50 + eff, 50 - eff)
        del cells[("agy:gemini-3.8-flash-low", "k00", "reported", "W", "direct")]
        rows = A.analyse_family(A.families_for(["agy:gemini-3.8-flash-low"])["config:agy:gemini-3.8-flash-low"], cells, keys, pairs_of(keys), B=400)
        by = {r["test"]: r for r in rows}
        self.assertEqual(by["H2"]["n_common"], 39)
        self.assertEqual(by["H2"]["missing_protection"]["n_missing_cells"], 1)
        self.assertEqual(by["H2"]["companion"]["n_common"], 39)
        self.assertIn("区间下界超过阈值", by["H1"]["verdict"])



class SpeechSensitivity(unittest.TestCase):
    def test_exclusion_planned_denominator_and_four_member_holm(self):
        cells = full(keys=("a","b","c"))
        planned = ["a","b","c"]
        pairs = pairs_of(planned)
        split_items = [{"key":k,"S":{"id":"dev:"+str(i)},"W":{"id":"test:"+str(i)}} for i,k in enumerate(planned)]
        fams = {name:{"rows":A.analyse_family(tests,cells,planned,pairs,B=100)}
                for name,tests in A.families_for(["agy:claude-sonnet-5-5-low"]).items()}
        del cells[("agy:claude-sonnet-5-5-low","a","stated","W","direct")]
        out = A.speech_sensitivity(cells,planned,pairs,["agy:claude-sonnet-5-5-low"],split_items,{"dev:0"},fams,B=100)
        self.assertEqual(out["excluded_keys"],["a"])
        by = {r["test"]:r for r in out["families"]["config:agy:claude-sonnet-5-5-low"]["rows"]}
        self.assertEqual(set(by),set(A.FAMILY_TESTS))
        for name in ("H1","H2","H4b"):
            self.assertEqual(by[name]["n_planned"],2)
            self.assertEqual(by[name]["missing_protection"]["n_missing_cells"],0)
        self.assertEqual(by["H4a"]["n_planned"],3)
        self.assertEqual(set(out["comparison"]["config:agy:claude-sonnet-5-5-low"]),{"H1","H2","H4b"})

    def test_no_hits_exact_main_and_whole_sample_removed(self):
        cells = full(keys=("a",))
        pairs = pairs_of(["a"])
        items = [{"key":"a","S":{"id":"dev:1"},"W":{"id":"test:2"}}]
        fams = {name:{"rows":A.analyse_family(tests,cells,["a"],pairs,B=100)}
                for name,tests in A.families_for(["agy:claude-sonnet-5-5-low"]).items()}
        out = A.speech_sensitivity(cells,["a"],pairs,["agy:claude-sonnet-5-5-low"],items,set(),fams,B=100)
        self.assertEqual(out["families"]["config:agy:claude-sonnet-5-5-low"]["rows"],fams["config:agy:claude-sonnet-5-5-low"]["rows"])
        out = A.speech_sensitivity(cells,["a"],pairs,["agy:claude-sonnet-5-5-low"],items,{"test:2"},fams,B=100)
        self.assertTrue(all(r["point"] is None for r in out["families"]["config:agy:claude-sonnet-5-5-low"]["rows"] if r["test"] != "H4a"))


class StrataRepeatPower(unittest.TestCase):
    def test_strata(self):
        cells = full(keys=("a", "b", "c", "d"))
        pairs = {k: {"cluster": k, "source_split": "dev" if k in "ab" else "test"} for k in "abcd"}
        cells[("agy:claude-sonnet-5-5-low", "c", "stated", "S", "direct")] = 20.0
        st = A.strata_points(cells, list("abcd"), pairs, ["agy:claude-sonnet-5-5-low"])
        self.assertEqual(st["dev"]["agy:claude-sonnet-5-5-low|H1"], {"n_planned": 2, "n_common": 2, "point": 30.0})
        self.assertEqual(st["test"]["agy:claude-sonnet-5-5-low|H1"]["point"], (0 + 30) / 2)

    def test_repeat_noise(self):
        cells, rep = full(keys=("a", "b")), full(keys=("a", "b"))
        rep[("agy:claude-sonnet-5-5-low", "a", "stated", "S", "direct")] = 90.0
        r = A.repeat_noise(cells, rep, "agy:claude-sonnet-5-5-low", ["a", "b"])
        self.assertAlmostEqual(r["stated|S|direct"]["mean_abs"], 5.0)
        self.assertAlmostEqual(r["s_item|stated|direct"]["mean_abs_call_diff"], 2.5)

    def test_power_matches_c_order_of_magnitude(self):
        self.assertIn(A.n_needed(13.4, 5.0, 0.0125, 2), (80, 81))
        self.assertAlmostEqual(A.power_given_n(13.4, 80, 5.0, 0.0125, 2), 0.80, delta=0.01)

    def test_power_scenarios_shape(self):
        rng = random.Random(2)
        keys = ["k%d" % i for i in range(30)]
        cells = {}
        for k in keys:
            put(cells, "agy:claude-sonnet-5-5-low", k, "direct", 50, 60 + rng.uniform(-10, 10), 40 + rng.uniform(-10, 10))
            put(cells, "agy:claude-sonnet-5-5-low", k, "multi", 50, 60 + rng.uniform(-10, 10), 40 + rng.uniform(-10, 10))
        ps = A.power_scenarios(cells, "agy:claude-sonnet-5-5-low", keys)
        self.assertEqual(set(ps), {"H1", "H2", "H4a", "H4b"})
        self.assertEqual(ps["H1"]["first_step"]["alpha"], 0.0125)


class Records(unittest.TestCase):
    def test_cells_and_missing_with_planned_denominator(self):
        recs = [{"key": "a", "cluster": "img", "use": "formal", "config": "agy:claude-sonnet-5-5-low", "pres": "stated", "utype": "S",
                 "ask": "multi", "round": rnd, "status": "ok", "unit": "a|stated|S|multi|" + rnd,
                 "result": {"value": v, "endpoint_mass": 0.2, "weighted_sd": 3.0}}
                for rnd, v in (("r0", 60.0), ("r1", 65.0))] + \
               [{"key": "b", "cluster": "img2", "use": "formal", "config": "agy:claude-sonnet-5-5-low", "pres": "prior", "utype": "-",
                 "ask": "direct", "round": "r0", "status": "missing", "result": None, "unit": "b|prior|-|direct|r0"}]
        cells, rep, cand, pairs = A.cells_from_records(recs)
        self.assertEqual(cells, {("agy:claude-sonnet-5-5-low", "a", "stated", "S", "multi"): 60.0})
        self.assertEqual(rep, {("agy:claude-sonnet-5-5-low", "a", "stated", "S", "multi"): 65.0})
        self.assertEqual(cand[("agy:claude-sonnet-5-5-low", "a", "stated", "S", "multi")]["endpoint_mass"], 0.2)
        mr = A.missing_rates(recs, {"agy:claude-sonnet-5-5-low": {"a|stated|S|multi|r0", "a|stated|S|multi|r1", "b|prior|-|direct|r0",
                                              "c|prior|-|direct|r0"}})
        self.assertEqual(mr["agy:claude-sonnet-5-5-low|prior|-|direct|r0"]["status"], {"missing": 1, "not_attempted": 1})
        self.assertEqual(mr["agy:claude-sonnet-5-5-low|prior|-|direct|r0"]["missing_rate"], 1.0)


if __name__ == "__main__":
    unittest.main()
