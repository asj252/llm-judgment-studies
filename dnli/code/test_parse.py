"""parse.py 的人工边界样例（PLAN v0.4 第 4 节；c 第一轮阻断 6、c 第二轮 S1）。用法：python -I -X utf8 test_parse.py

Direct：复制自 ../suppression/test_parse.py 的 E1 类（函数名改为 parse_direct），内容不变。
Multi：多估计问法的新样例。
"""
import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import parse  # noqa: E402


class Direct(unittest.TestCase):
    def ok(self, text, v, forms=None):
        r = parse.parse_direct(text)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["value"], v)
        if forms is not None:
            self.assertEqual(r["forms"], forms)

    def bad(self, text, err):
        r = parse.parse_direct(text)
        self.assertFalse(r["ok"], r)
        self.assertEqual(r["error"], err)

    def test_plain_integer(self):
        self.ok("Reasoning...\nProbability: 70%", 70.0, ["plain"])

    def test_decimal(self):
        self.ok("Probability: 70.5%", 70.5)

    def test_bounds(self):
        self.ok("Probability: 0%", 0.0)
        self.ok("Probability: 100%", 100.0)
        self.ok("Probability: 100.0%", 100.0)

    def test_out_of_range(self):
        self.bad("Probability: 100.5%", "out_of_range")
        self.bad("Probability: 150%", "out_of_range")
        self.bad("Probability: -5%", "out_of_range")

    def test_no_percent(self):
        self.bad("Probability: 0.7", "no_percent")
        self.bad("Probability: 70", "no_percent")
        self.bad("Probability: 1", "no_percent")

    def test_bare_number_without_field(self):
        self.bad("I think 70%.", "no_field")
        self.bad("The answer is 0.7", "no_field")

    def test_malformed(self):
        self.bad("Probability: .5%", "malformed")
        self.bad("Probability: 1e2%", "malformed")
        self.bad("Probability: 70.%", "malformed")

    def test_non_numeric(self):
        self.bad("Probability: NaN%", "no_number")
        self.bad("Probability: inf%", "no_number")
        self.bad("Probability: high", "no_number")
        self.bad("Probability: 70/100", "no_percent")

    def test_multiple_fields(self):
        self.ok("Probability: 60%\n...\nProbability: 70%", 70)
        self.ok("### Probability:\nProbability: 20%", 20)
        self.bad("Probability: 20%\nProbability: heading", "no_number")
        self.bad("Probability: 20%\nProbability: 101%", "out_of_range")

    def test_final_numeric_field_never_falls_back(self):
        self.bad("Probability: 10%\nProbability: 999%", "out_of_range")
        for tail, error in (("20", "no_percent"), (".5%", "malformed"),
                            ("20%-30%", "range_or_extra_number"), ("about 20%", "no_number")):
            self.bad("Probability: 10%\nProbability: " + tail, error)

    def test_range_and_extra_numbers(self):
        self.bad("Probability: 70%-80%", "range_or_extra_number")
        self.bad("Probability: 70% or 80%", "range_or_extra_number")
        self.bad("Probability: 70% (between 60 and 80)", "range_or_extra_number")

    def test_trailing_text_allowed(self):
        self.ok("Probability: 70% (likely)", 70.0, ["trailing_text"])
        self.ok("Probability: 70%.", 70.0, ["plain"])

    def test_forms(self):
        self.ok("**Probability:** 70%", 70.0, ["bold"])
        self.ok("**Probability: 70%**", 70.0, ["bold"])
        self.ok("Probability：70%", 70.0, ["fullwidth_colon"])
        self.ok("Probability: 70 %", 70.0, ["space_before_percent"])
        self.ok("probability: 70%", 70.0, ["lowercase_key"])
        self.ok("PROBABILITY: 70%", 70.0, ["other_case_key"])

    def test_word_probability_without_colon_is_not_field(self):
        self.ok("The probability is high because...\nProbability: 90%", 90.0)

    def test_thinking_skipped(self):
        self.ok("<think>Maybe Probability: 10%</think>\n\nProbability: 95%", 95.0)
        self.ok("Probability: 10% (draft)\n</think>\nProbability: 95%", 95.0)
        self.bad("<think>still thinking Probability: 50%", "thinking_unterminated")
        self.bad("<think>Probability: 50%</think>\nNo field here", "no_field")

    def test_number_on_next_line_not_taken(self):
        self.bad("Probability:\n70%", "no_number")

    def test_final_empty_field_never_falls_back(self):
        for tail in ("", "\n999%", "\n90%", " heading", " NaN%"):
            with self.subTest(tail=tail):
                self.bad("Probability: 10%\nProbability:" + tail, "no_number")
        self.bad("Probability: 10% Probability:", "no_number")
        self.ok("### Probability:\n说明\nProbability: 20%", 20)

    def test_none(self):
        self.bad(None, "no_text")


def table(rows, sep=" | "):
    return "\n".join("Estimate %s: %s%sWeight: %s" % (k, p, sep, w) for k, p, w in rows)


GOOD_ROWS = [(1, "10%", "0.1"), (2, "30%", "0.2"), (3, "50%", "0.4"), (4, "70%", "0.2"), (5, "96%", "0.1")]
GOOD = "Some reasoning about the statement.\n\n" + table(GOOD_ROWS)


class Multi(unittest.TestCase):
    def ok(self, text):
        r = parse.parse_multi(text)
        self.assertTrue(r["ok"], r)
        return r

    def bad(self, text, err):
        r = parse.parse_multi(text)
        self.assertFalse(r["ok"], r)
        self.assertEqual(r["error"], err)
        self.assertIsNone(r["value"])

    def test_good_aggregate_and_candidate_stats(self):
        r = self.ok(GOOD)
        agg = 0.1 * 10 + 0.2 * 30 + 0.4 * 50 + 0.2 * 70 + 0.1 * 96
        self.assertAlmostEqual(r["value"], agg)
        self.assertEqual(r["estimates"], [10.0, 30.0, 50.0, 70.0, 96.0])
        self.assertAlmostEqual(r["endpoint_mass"], 0.1)                 # 只有 96% 是端点
        sd = math.sqrt(sum(w * (p - agg) ** 2 for p, w in zip((10, 30, 50, 70, 96), (.1, .2, .4, .2, .1))))
        self.assertAlmostEqual(r["weighted_sd"], sd)
        self.assertEqual(r["forms"], ["plain"])

    def test_c_counterexample_aggregate_hides_endpoints(self):
        """c 第一轮阻断 1：[0,1,2,99,100]% 等权 → 聚合 40.4%（不是端点），候选端点质量 100%。"""
        rows = [(k, "%d%%" % p, "0.2") for k, p in zip(range(1, 6), (0, 1, 2, 99, 100))]
        r = self.ok(table(rows))
        self.assertAlmostEqual(r["value"], 40.4)
        self.assertFalse(parse.is_endpoint(r["value"]))
        self.assertAlmostEqual(r["endpoint_mass"], 1.0)

    def test_endpoint_boundaries(self):
        self.assertTrue(parse.is_endpoint(5.0))
        self.assertTrue(parse.is_endpoint(95.0))
        self.assertFalse(parse.is_endpoint(5.01))
        self.assertFalse(parse.is_endpoint(94.99))

    def test_weight_sum_tolerance_normalised(self):
        rows = [(1, "20%", "0.2"), (2, "40%", "0.2"), (3, "60%", "0.2"), (4, "80%", "0.2"), (5, "100%", "0.25")]
        r = self.ok(table(rows))                     # 和 1.05：边界内，归一
        self.assertAlmostEqual(r["weight_sum"], 1.05)
        self.assertAlmostEqual(r["value"], (0.2 * (20 + 40 + 60 + 80) + 0.25 * 100) / 1.05)
        rows[4] = (5, "100%", "0.15")                # 和 0.95：边界内
        self.assertTrue(parse.parse_multi(table(rows))["ok"])

    def test_weight_sum_out_of_tolerance(self):
        rows = [(1, "20%", "0.2"), (2, "40%", "0.2"), (3, "60%", "0.2"), (4, "80%", "0.2"), (5, "100%", "0.26")]
        self.assertFalse(self.ok(table(rows))["weight_sum_in_tolerance"])
        rows[4] = (5, "100%", "0.14")
        self.assertFalse(self.ok(table(rows))["weight_sum_in_tolerance"])
        rows = [(k, "50%", "1") for k in range(1, 6)]    # 每个都写 1
        self.assertAlmostEqual(self.ok(table(rows))["value"], 50)

    def test_count(self):
        self.bad(table(GOOD_ROWS[:4]), "n_estimates_4")
        self.bad(table(GOOD_ROWS + [(6, "50%", "0.0")]), "n_estimates_6")
        self.assertEqual(self.ok(table(GOOD_ROWS) + "\n\nFinal:\n" + table(GOOD_ROWS))["value"], self.ok(GOOD)["value"])
        self.bad("Probability: 70%", "n_estimates_0")

    def test_duplicate_and_bad_index(self):
        rows = list(GOOD_ROWS)
        rows[4] = (4, "96%", "0.1")
        self.bad(table(rows), "duplicate_index")
        rows[4] = (6, "96%", "0.1")
        self.bad(table(rows), "bad_index")
        rows[4] = (0, "96%", "0.1")
        self.bad(table(rows), "bad_index")

    def test_equal_values_allowed(self):
        r = self.ok(table([(k, "50%", "0.2") for k in range(1, 6)]))
        self.assertAlmostEqual(r["value"], 50.0)
        self.assertAlmostEqual(r["weighted_sd"], 0.0)

    def test_order_free(self):
        r = self.ok(table(GOOD_ROWS[:1] + list(reversed(GOOD_ROWS[1:]))))
        self.assertAlmostEqual(r["value"], self.ok(GOOD)["value"])
        self.bad(table(list(reversed(GOOD_ROWS))), "n_estimates_1")

    def test_estimate_value_rules(self):
        for val, err in (("0.7", "estimate_no_percent"), ("70", "estimate_no_percent"), ("101%", "estimate_out_of_range"),
                         ("-1%", "estimate_out_of_range"), (".5%", "estimate_malformed"), ("70%-80%",
                         "estimate_range_or_extra_number"), ("high", "estimate_no_number"), ("NN%", "estimate_no_number")):
            rows = list(GOOD_ROWS)
            rows[2] = (3, val, "0.4")
            self.bad(table(rows), err)

    def test_weight_rules(self):
        for w, err in (("40%", "weight_percent"), ("1.4", "weight_out_of_range"), ("-0.1", "weight_out_of_range"),
                       ("2/5", "weight_malformed"), ("4e-1", "weight_malformed"),
                       ("high", "weight_no_number"), ("W", "weight_no_number"), ("0.4 (40%)", "weight_extra_number"),
                       ("", "weight_no_number")):
            rows = list(GOOD_ROWS)
            rows[2] = (3, "50%", w)
            self.bad(table(rows), err)

    def test_weight_without_leading_zero(self):
        """PLAN v0.4 第 4 节、c 第二轮 S1：接受 `.2`；科学计数法与分数仍拒绝。"""
        r = self.ok(table([(k, "%d%%" % (20 * k), ".2") for k in range(1, 6)]))
        self.assertAlmostEqual(r["value"], 60.0)
        self.assertEqual(r["weights"], [0.2] * 5)
        self.ok(table([(1, "10%", "+.2"), (2, "20%", "0.2"), (3, "30%", ".20"), (4, "40%", "0.2"), (5, "50%", ".2")]))
        for w, err in (("2e-1", "weight_malformed"), ("1/5", "weight_malformed"), (".", "weight_no_number"),
                       ("-.2", "weight_out_of_range"), (".2%", "weight_percent")):
            rows = list(GOOD_ROWS)
            rows[2] = (3, "50%", w)
            self.bad(table(rows), err)

    def test_missing_or_multiple_weight_fields(self):
        self.bad(GOOD.replace("Estimate 3: 50% | Weight: 0.4", "Estimate 3: 50%"), "missing_weight")
        self.bad(GOOD.replace("Estimate 3: 50% | Weight: 0.4", "Estimate 3: 50% weight 0.4"), "missing_weight")
        self.bad(GOOD.replace("Weight: 0.4", "Weight: 0.4 | Weight: 0.3"), "multiple_weights")

    def test_two_estimates_on_one_line(self):
        t = GOOD.replace("Estimate 3: 50% | Weight: 0.4", "Estimate 3: 50% | Weight: 0.4 Estimate 6: 1% | Weight: 0")
        self.bad(t, "multiple_estimate_fields_in_line")

    def test_tolerated_forms(self):
        t = GOOD.replace("Estimate 1: 10% | Weight: 0.1", "- **Estimate 1:** 10% | **Weight:** 0.1")
        self.assertEqual(self.ok(t)["forms"], ["bold"])
        t = GOOD.replace("Estimate 1: 10% | Weight: 0.1", "__Estimate 1:__ 10% | __Weight:__ 0.1")
        self.assertTrue(self.ok(t)["ok"])
        self.ok(table(GOOD_ROWS, sep=", "))
        self.ok(table(GOOD_ROWS, sep=" (most plausible) | "))
        self.ok(GOOD.replace("Estimate 2: 30%", "estimate 2：30 %"))
        self.ok(GOOD.replace("Weight: 0.2\nEstimate 3", "Weight: 0.20.\nEstimate 3"))

    def test_prose_mentions_not_counted(self):
        t = "My first estimate is 10%; I underestimate 2: no.\nEstimates 3: none\n" + GOOD
        self.ok(t)

    def test_template_echo_fails(self):
        echo = "\n".join("Estimate %d: NN%% | Weight: W" % k for k in range(1, 6))
        self.bad(echo, "estimate_no_number")

    def test_thinking(self):
        self.assertAlmostEqual(self.ok("<think>" + table(GOOD_ROWS[:3]) + "</think>\n" + GOOD)["value"],
                               self.ok(GOOD)["value"])
        self.bad("<think>" + GOOD, "thinking_unterminated")
        self.bad(None, "no_text")

    def test_parsers_table(self):
        self.assertIs(parse.PARSERS["direct"], parse.parse_direct)
        self.assertIs(parse.PARSERS["multi"], parse.parse_multi)

    def test_positive_sums_07_12_and_zero(self):
        for w, total in (("0.14", 0.7), ("0.24", 1.2)):
            r = self.ok(table([(k, "%d%%" % (20*k), w) for k in range(1,6)]))
            self.assertAlmostEqual(r["value"], 60)
            self.assertAlmostEqual(r["weight_sum"], total)
            self.assertFalse(r["weight_sum_in_tolerance"])
        self.bad(table([(k, "50%", "0") for k in range(1,6)]), "weight_sum_not_positive")

    def test_only_final_five_are_parsed(self):
        self.ok("Estimate 9: no Weight\n" + GOOD)
        self.bad(GOOD + "\n" + table([(k,"20%",".2") for k in (1,2,3,4,6)]), "bad_index")
        self.bad(GOOD + "\n" + table([(k,"20%",".2") for k in (1,2,3,4,4)]), "duplicate_index")

    def test_final_group_missing_colon_counterexample(self):
        old = table([(k, "10%", ".2") for k in range(1, 6)])
        new = table([(k, "90%", ".2") for k in range(1, 6)])
        self.bad(old + "\n" + new.replace("Estimate 5:", "Estimate 5"), "malformed_estimate_field")
        self.bad(old + "\n" + table(GOOD_ROWS[:4]), "n_estimates_4")
        self.bad(old + "\n" + new.replace("Estimate 5:", "**ESTIMATE** 5"), "malformed_estimate_field")

    def test_final_group_trailing_prose(self):
        self.ok(GOOD + "\nThese five estimates are my final answer.")
        self.ok(GOOD + "\nFinal:\n" + GOOD + "\nExplanation follows.")


class Legacy(unittest.TestCase):
    def test_v1_boundaries_preserved(self):
        self.assertEqual(parse.PARSE_VERSION, 2)
        self.assertEqual(parse.parse_direct_v1("Probability: 60%\nProbability: 70%")["error"], "multiple_fields")
        self.assertEqual(parse.parse_multi_v1(GOOD + "\n" + GOOD)["error"], "n_estimates_10")
        self.assertEqual(parse.parse_multi_v1(table(GOOD_ROWS + [(6,"50%","0")]))["error"], "n_estimates_6")
        for w, total in ((".14", "0.7000"),(".24","1.2000")):
            r = parse.parse_multi_v1(table([(k,"50%",w) for k in range(1,6)]))
            self.assertEqual(r["error"], "weight_sum_out_of_tolerance:" + total)
        self.assertTrue(parse.parse_multi_v1(GOOD)["ok"])


if __name__ == "__main__":
    unittest.main()
