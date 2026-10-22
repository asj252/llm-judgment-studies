"""Acceptance tests; G=generator, P=parsing, B=bounds in brief-e-conjunction.md."""
import hashlib
import itertools
import json
import random
import unittest
from pathlib import Path

from bounds_d import d1, d2, d3, d4
from gen_d import all_items, generate_items, preview
from parse_d import parse_joint_direct, parse_joint_multi, parse_response
from prompts_d import (ASKS, JOINT_ASKS, NO_TOOLS, STATEMENTS, STRATA,
                       _load_dnli, load_items, render)

ROOT = Path(__file__).resolve().parent
ORDER = ["conj", "a", "disj", "b"]


def direct(values=(10, 80, 90, 20)):
    return "\n".join(f"Statement {k}: {v}%" for k, v in enumerate(values, 1))


def multi(rows=None, weights=None):
    rows = rows if rows is not None else [(10 + i, 70 + i, 90, 20 + i) for i in range(5)]
    weights = weights if weights is not None else [.2] * 5
    return "\n".join(f"Estimate {k}: " + " | ".join(f"S{j} {v}%" for j, v in enumerate(row, 1))
                     + f" | Weight: {w}" for k, (row, w) in enumerate(zip(rows, weights), 1))


class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bank = load_items()
        cls.data = generate_items(cls.bank)
        cls.units = [u for i in cls.data["items"] for u in i["units"]]

    def test_g_counts_grid_metadata(self):
        self.assertEqual(self.data["bank_version"], "v0.2")
        self.assertTrue(any("revised" in item for item in self.bank))
        self.assertEqual(len(self.bank), 42)
        self.assertEqual(len(self.units), 420)
        self.assertEqual(len({u["unit"] for u in self.units}), 420)
        for item in self.data["items"]:
            self.assertEqual(len(item["units"]), 10)
            grid = {(u["pres"], u.get("stmt"), u["ask"]) for u in item["units"]}
            self.assertEqual(grid, {(p, s, a) for p, s in [("S", s) for s in STATEMENTS] + [("J", None)]
                                    for a in ASKS})
            for unit in item["units"]:
                for key in ("item_id", "type", "split", "repeat"):
                    self.assertEqual(unit[key], item[key])
                self.assertEqual("stratum" in unit, unit["type"] == "W")
                self.assertEqual("stmt" in unit, unit["pres"] == "S")
                self.assertEqual("order" in unit, unit["pres"] == "J")

    def test_g_splits_repeats_and_seed_regression(self):
        self.assertEqual(self.data["dev_items"], ["p08", "p17", "p18", "p22", "w04", "w09", "w18"])
        self.assertEqual(self.data["repeat_items"], ["p01", "p13", "p15", "p24", "w10", "w15"])
        for t, stratum, ndev, nformal, nrepeat in [("P", None, 4, 20, 4)] + [("W", s, 1, 5, None) for s in STRATA]:
            selected = [i for i in self.data["items"] if i["type"] == t and i.get("stratum") == stratum]
            self.assertEqual(sum(i["split"] == "dev" for i in selected), ndev)
            self.assertEqual(sum(i["split"] == "formal" for i in selected), nformal)
            if nrepeat is not None:
                self.assertEqual(sum(i["repeat"] for i in selected), nrepeat)
        repeated_w = [i for i in self.data["items"] if i["type"] == "W" and i["repeat"]]
        self.assertEqual(len(repeated_w), 2)
        self.assertEqual(len({i["stratum"] for i in repeated_w}), 2)
        self.assertTrue(all(i["split"] == "formal" for i in self.data["items"] if i["repeat"]))

    def test_g_artifacts_determinism_hashes(self):
        self.assertEqual(self.data, generate_items(load_items()))
        self.assertEqual(self.data, json.loads((ROOT / "items_d.json").read_text(encoding="utf-8")))
        self.assertEqual(preview(self.data), (ROOT / "items_d_preview.md").read_text(encoding="utf-8"))
        self.assertEqual(all_items(self.data), (ROOT / "items_d_all.md").read_text(encoding="utf-8"))
        self.assertEqual(preview(self.data).count("```text"), 20)
        self.assertEqual(all_items(self.data).count("```text"), 42)
        for u in self.units:
            self.assertEqual(u["prompt_sha256"], hashlib.sha256(u["prompt"].encode("utf-8")).hexdigest())

    def test_g_verbatim_bank_statement_blocks_and_order(self):
        # G: exactly one S statement, or four J statements in the recorded order.
        rng = random.Random(20261430)
        for source, item in zip(self.bank, self.data["items"]):
            expected_order = list(STATEMENTS)
            rng.shuffle(expected_order)
            for u in item["units"]:
                blocks = u["prompt"].split("\n\n")
                self.assertEqual(blocks[0], "Here is a situation: " + source["context"])
                lines = blocks[1].splitlines()
                if u["pres"] == "S":
                    self.assertEqual(lines, ["Using common sense, how likely is it that the following statement is true?",
                                             "Statement: " + source[u["stmt"] + "_statement"]])
                else:
                    self.assertEqual(u["order"], expected_order)
                    self.assertEqual(lines, ["Using common sense, how likely is it that each of the following statements is true?"]
                                     + [f"Statement {k}: {source[s + '_statement']}" for k, s in enumerate(expected_order, 1)])
                self.assertTrue(u["prompt"].endswith("\n\n" + NO_TOOLS))

    def test_g_verbatim_tails(self):
        dnli = _load_dnli("prompts")
        self.assertEqual(ASKS, dnli.ASKS)
        plan = (ROOT / "PLAN.md").read_text(encoding="utf-8")
        joint_direct = plan.split("Give a probability for each statement.", 1)[1].split("\n\nDo not use", 1)[0]
        self.assertEqual(JOINT_ASKS["direct"], "Give a probability for each statement." + joint_direct)
        for u in self.units:
            ask = ASKS[u["ask"]] if u["pres"] == "S" else JOINT_ASKS[u["ask"]]
            self.assertTrue(u["prompt"].endswith(ask + "\n\n" + NO_TOOLS))
        joint_multi = (
            "Give 5 estimates, each estimate being a set of probabilities for all four statements, and give each estimate a weight for how likely you think that estimate is; the weights sum to 1.\n\n"
            "At the end of your answer, give the 5 estimates strictly in the following format, one per line:\n"
            "Estimate 1: S1 NN% | S2 NN% | S3 NN% | S4 NN% | Weight: W\n"
            "Estimate 2: S1 NN% | S2 NN% | S3 NN% | S4 NN% | Weight: W\n"
            "Estimate 3: S1 NN% | S2 NN% | S3 NN% | S4 NN% | Weight: W\n"
            "Estimate 4: S1 NN% | S2 NN% | S3 NN% | S4 NN% | Weight: W\n"
            "Estimate 5: S1 NN% | S2 NN% | S3 NN% | S4 NN% | Weight: W\n"
            "where each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign, and each W is a number from 0 to 1 (decimals allowed); the five weights sum to 1."
        )
        self.assertEqual(JOINT_ASKS["multi"], joint_multi)
        for fragment in [joint_multi.split("\n\n")[0], joint_multi.splitlines()[2],
                         "Estimate k: S1 NN% | S2 NN% | S3 NN% | S4 NN% | Weight: W",
                         joint_multi.splitlines()[-1]]:
            self.assertIn(fragment, plan)
        for unit in self.units:
            if unit["pres"] == "J" and unit["ask"] == "multi":
                self.assertTrue(unit["prompt"].endswith(joint_multi + "\n\n" + NO_TOOLS))

    def test_g_invalid_render_inputs(self):
        for args in [("S", "direct", None, None), ("J", "direct", None, ["a"] * 4),
                     ("J", "direct", "b", ORDER), ("X", "direct", None, None),
                     ("S", "other", "a", None)]:
            with self.assertRaises(ValueError):
                render(self.bank[0], args[0], args[1], stmt=args[2], order=args[3])


class ParserTests(unittest.TestCase):
    def assert_failed(self, result):
        self.assertFalse(result["ok"])
        self.assertEqual(result["values"], dict.fromkeys(STATEMENTS))
        self.assertIsNone(result["estimates"])

    def test_p_joint_direct_four_positive(self):
        cases = [(direct(), {"conj": 10, "a": 80, "disj": 90, "b": 20}),
                 (direct((0, 100, 99.25, .5)), {"conj": 0, "a": 100, "disj": 99.25, "b": .5}),
                 ("reasoning\n" + direct() + "\n\n", {"conj": 10, "a": 80, "disj": 90, "b": 20}),
                 (direct((0, 0, 0, 0)) + "\n" + direct(), {"conj": 10, "a": 80, "disj": 90, "b": 20})]
        for text, expected in cases:
            with self.subTest(text=text):
                result = parse_joint_direct(text, ORDER)
                self.assertTrue(result["ok"])
                self.assertEqual(result["values"], expected)

    def test_p_joint_direct_negative_whole_cell(self):
        for text in ["\n".join(direct().splitlines()[:-1]), direct((101, 80, 90, 20)),
                     direct((-1, 80, 90, 20)), direct().replace("Statement 4", "Statement 3"),
                     direct().replace("10%", "10"), direct() + "\nConclusion", None,
                     direct().replace("10%", "1e1%"), "<think>" + direct(),
                     direct().replace("Statement 1:", "Statement 0:")]:
            with self.subTest(text=text):
                self.assert_failed(parse_joint_direct(text, ORDER))

    def test_p_joint_multi_four_positive(self):
        for text in [multi(), multi(weights=[.4] * 5), "reasoning\n" + multi(),
                     multi(rows=[(0, 100, 100, 0)] * 5, weights=[0, 0, 1, 0, 0])]:
            with self.subTest(text=text):
                result = parse_joint_multi(text, ORDER)
                self.assertTrue(result["ok"])
                self.assertAlmostEqual(sum(result["normalized_weights"]), 1)
                self.assertEqual(len(result["estimates"]["b"]), 5)

    def test_p_joint_multi_negative_whole_cell(self):
        good = multi()
        for text in ["\n".join(good.splitlines()[:-1]), multi(rows=[(101, 80, 90, 20)] * 5),
                     multi(weights=[0] * 5), multi(weights=[-.1, .2, .2, .2, .2]),
                     multi(weights=[0, 2, 3, 4, 1]), multi(weights=[1.01, .2, .2, .2, .2]),
                     multi(weights=[float("nan"), .2, .2, .2, .2]),
                     multi(weights=[float("inf"), .2, .2, .2, .2]),
                     multi(weights=["9" * 400, .2, .2, .2, .2]),
                     good.replace("S1 10%", "S1 %"), good.replace("Estimate 5:", "Estimate 4:"),
                     good.replace("S3 90%", "S3 90"), good.replace("Weight: 0.2", "Weight: 1e-1"),
                     good + "\nEstimate 1: malformed", good + "\nEstimate 6: malformed",
                     good.replace("S4 20%", "S4 -1%")]:
            with self.subTest(text=text):
                self.assert_failed(parse_joint_multi(text, ORDER))

    def test_p_last_group_no_fallback(self):
        self.assertEqual(parse_joint_multi(multi(rows=[(99, 99, 99, 99)] * 5) + "\n" + multi(), ORDER)["values"],
                         parse_joint_multi(multi(), ORDER)["values"])
        self.assert_failed(parse_joint_multi(multi() + "\n" + "\n".join(multi().splitlines()[:4]), ORDER))
        for prefix in ("**Estimate 1:**", "- Estimate 1:", "* Estimate 1:",
                       "1. Estimate 1:", "1) Estimate 1:", "__Estimate 1:__",
                       "**Estimate** 1:", "Estimate 1"):
            with self.subTest(prefix=prefix):
                text = multi() + "\n" + prefix + " malformed"
                self.assert_failed(parse_joint_multi(text, ORDER))
                self.assertFalse(parse_response(text, "S", "multi")["ok"])
        self.assert_failed(parse_joint_direct(direct() + "\nStatement 1: bad", ORDER))

    def test_p_common_weights_mapping_normalization_and_constraint(self):
        rows = [(0, 10, 20, 10), (5, 20, 30, 8), (10, 30, 40, 10), (20, 40, 50, 80), (30, 50, 60, 90)]
        weights = [0, .4, .6, .8, .2]
        result = parse_joint_multi(multi(rows=rows, weights=weights), ORDER)
        self.assertTrue(result["ok"])
        self.assertEqual(result["weights"], weights)
        self.assertEqual(result["weight_sum"], 2)
        self.assertEqual(result["normalized_weights"], [0, .2, .3, .4, .1])
        for index, stmt in enumerate(ORDER):
            self.assertEqual(result["estimates"][stmt], [row[index] for row in rows])
            self.assertAlmostEqual(result["values"][stmt], sum(row[index] * w / 2 for row, w in zip(rows, weights)))
        self.assertLessEqual(result["values"]["conj"], result["values"]["b"])
        for order in itertools.permutations(STATEMENTS):
            parsed = parse_joint_direct(direct(), order)
            self.assertEqual(parsed["values"], dict(zip(order, (10, 80, 90, 20))))
            parsed = parse_joint_multi(multi(), order)
            for index, stmt in enumerate(order):
                self.assertEqual(parsed["estimates"][stmt], [row[index] for row in [(10 + i, 70 + i, 90, 20 + i) for i in range(5)]])

    def test_p_s_exact_v2_and_thinking(self):
        dnli = _load_dnli("parse")
        texts = {"direct": ["Probability: 5%\nProbability: 20%", "Probability: 5%\nProbability:",
                             "<think>wrong</think>Probability: 25%"],
                 "multi": ["\n".join(f"Estimate {k}: {k * 10}% | Weight: .4" for k in range(1, 6)),
                           "Estimate 1: malformed"]}
        for ask, cases in texts.items():
            for text in cases:
                self.assertEqual(parse_response(text, "S", ask), dnli.PARSERS[ask](text))
        self.assertTrue(parse_joint_direct("<think>wrong</think>" + direct(), ORDER)["ok"])
        self.assertTrue(parse_joint_multi("<think>wrong</think>" + multi(), ORDER)["ok"])
        with self.assertRaises(ValueError):
            parse_joint_multi(multi(), ["a"] * 4)


class BoundsTests(unittest.TestCase):
    def test_b_d1_table_observed_and_missing(self):
        self.assertEqual(d1({"conj": 30, "b": 20}), 10)
        self.assertEqual(d1({"conj": None, "b": 20}), -20)
        self.assertEqual(d1({"conj": 30, "b": None}), -70)
        self.assertEqual(d1(None), -100)

    def test_b_d2_table_joint_missing_delta_positive_100(self):
        s = {"conj": 30, "b": 20}
        j = {"a": 70, "b": 20, "conj": 10, "disj": 80}
        self.assertEqual(d2(s, j), 20)
        self.assertEqual(d2(s, None), -90)  # Delta_J max = +100.
        self.assertEqual(d2(None, None), -200)
        for stmt in STATEMENTS:
            self.assertEqual(d2(s, dict(j, **{stmt: None})), -90)

    def test_b_d3_table_both_directions_and_crossing_zero(self):
        self.assertEqual(d3({"b": 20, "conj": 30}, {"b": 40, "conj": 20}), (30, 30))
        self.assertEqual(d3({"b": 20}, {"b": 20, "conj": 10}), (-10, 90))
        self.assertEqual(d3({"conj": 0}, {"b": 0, "conj": 30}), (-130, -30))
        self.assertEqual(d3(None, None), (-200, 200))

    def test_b_d4_table_joint_whole_missing(self):
        j = {"a": 70, "b": 20, "conj": 10, "disj": 80}
        self.assertEqual(d4(j, j), (0, 0))
        self.assertEqual(d4(None, j), (-90, 110))
        self.assertEqual(d4(j, None), (-110, 90))
        self.assertEqual(d4(None, None), (-200, 200))
        self.assertEqual(d4(dict(j, a=None), j), (-90, 110))

    def test_b_all_s_missing_patterns_against_feasible_corners(self):
        # B: independent numerical oracle enumerates every missing b/conj corner.
        cells = [dict(zip(("b", "conj"), values)) for values in itertools.product((None, 20, 70), repeat=2)]
        def deltas(cell):
            choices = [(0, 100) if cell[s] is None else (cell[s],) for s in ("b", "conj")]
            return [c - b for b, c in itertools.product(*choices)]
        for m, d in itertools.product(cells, repeat=2):
            expected = [mv - dv for mv in deltas(m) for dv in deltas(d)]
            self.assertEqual(d1(m), min(deltas(m)))
            self.assertEqual(d3(m, d), (min(expected), max(expected)))

    def test_b_invalid_observed_values(self):
        for value in (-1, 101, float("nan"), float("inf")):
            with self.assertRaises(ValueError):
                d1({"b": value})


if __name__ == "__main__":
    unittest.main()
