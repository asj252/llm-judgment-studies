"""Run only this module with the specified llm Python from paper/."""
import json
import re
import struct
import subprocess
import sys
import unittest

import numpy as np
import make_figures as mf


class FigureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = mf.compute_data()
        cls.en_data = mf.compute_data(include_extension=True)
        cls.analysis = json.loads((mf.DATA / "analysis_formal.json").read_text(encoding="utf-8"))
        cls.confirmatory = {(r["config"], r["test"]): r
                            for family in cls.analysis["families"].values() for r in family["rows"]}
        if not any((mf.OUT / f"{name}.{ext}").exists() for name in
                   ("fig1_movement", "fig2_endpoints", "fig3_readings") for ext in ("pdf", "png")):
            mf.generate_figures(cls.data)
            (mf.OUT / "figure_data.json").write_text(
                json.dumps(cls.data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        cls.en_output = mf.OUT / "en"
        if not (cls.en_output / "figure_data.json").exists():
            subprocess.run([sys.executable, "-X", "utf8", "-B", str(mf.HERE / "make_figures.py"),
                            "--lang", "en"], check=True)

    def test_h1_points(self):
        for row in self.data["fig1"]:
            if (row["pres"], row["ask"]) == ("stated", "direct"):
                target = self.confirmatory[row["config"], "H1"]
                self.assertAlmostEqual(row["point"], target["point"], delta=1e-9)
                self.assertEqual(row["n"], target["n_common"])

    def test_common_pair_h4b(self):
        for row in self.data["h4b"]:
            target = self.confirmatory[row["config"], "H4b"]
            self.assertAlmostEqual(row["point"], target["point"], delta=1e-9)
            self.assertEqual(row["n"], target["n_common"])

    def test_prior_endpoint_rates(self):
        text = (mf.HERE / "fixtures" / "endpoints.md").read_text(encoding="utf-8").split("## 2b", 1)[1]
        for config in mf.CONFIGS:
            match = re.search(r"^\| " + re.escape(config) + r" \| (\d+)%", text, re.M)
            self.assertIsNotNone(match)
            point = next(r["point"] for r in self.data["fig2"]
                         if (r["config"], r["pres"], r["ask"]) == (config, "prior", "direct"))
            self.assertAlmostEqual(point, int(match[1]) / 100, delta=.01)

    def test_readings_match_sources(self):
        text = (mf.HERE / "fixtures" / "readings.md").read_text(encoding="utf-8")
        for config in mf.CONFIGS:
            mean = next(r for r in self.data["fig3"] if r["config"] == config and r["reading"] == "mean")
            self.assertAlmostEqual(mean["point"], self.confirmatory[config, "H4b"]["point"], delta=1e-9)
            match = re.search(r"^\| " + re.escape(config) + r"（陈述[^\n]+", text, re.M)
            self.assertIsNotNone(match)
            expected = float(match[0].split("|")[5].strip().split()[0].replace("−", "-"))
            top = next(r for r in self.data["fig3"] if r["config"] == config and r["reading"] == "top")
            self.assertEqual(round(top["point"], 1), expected)

    def test_candidate_ties_and_median(self):
        row = {"result": {"value": 50, "estimates": [10, 40, 80], "weights": [.4, .2, .4]}}
        self.assertEqual(mf.read_value(row, "top"), 45)
        self.assertEqual(mf.read_value(row, "median"), 40)

    def test_median_half_weight_boundaries(self):
        # Brief v2 #1: exact lower median, including the c-review failure.
        cases = [([0, 5, 20, 40, 35], [.5, .1, .2, .3, .1], 5),
                 ([80, 10, 40], ["0.3", "0.1", "0.2"], 40),
                 ([90, 20, 70, 10], ["3", "2", "1", "2"], 20)]
        for estimates, weights, expected in cases:
            with self.subTest(estimates=estimates, weights=weights):
                row = {"result": {"estimates": estimates, "weights": weights}}
                self.assertEqual(mf.read_value(row, "median"), expected)
        records = mf.load_records("olmo2")
        row = records["3601978895.jpg#1r1n", "stated", "W", "multi"]
        self.assertEqual(row["result"]["weights"], ["0.5", "0.1", "0.2", "0.3", "0.1"])
        self.assertEqual(mf.read_value(row, "median"), 5)

    def test_fig3_regression(self):
        # Brief v2 #4: all three readings and intervals, with corrected medians.
        # Unchanged values were independently verified in review-figures-codex.md;
        # corrected OLMo-2 median values also come from that review.
        expected = {
            ("qwen3-off", "mean"): (-7.938638519, -9.723056173, -6.179468523),
            ("qwen3-off", "top"): (-4.577708333, -6.386041667, -2.737083333),
            ("qwen3-off", "median"): (-6.721041667, -8.539583333, -4.910416667),
            ("olmo2", "mean"): (-13.708308476, -16.138516437, -11.258539101),
            ("olmo2", "top"): (-14.539215686, -17.040616246, -11.901610644),
            ("olmo2", "median"): (-12.781512605, -15.289915966, -10.176470588),
            ("codex", "mean"): (-2.482416667, -3.161291667, -1.778479167),
            ("codex", "top"): (-2.088958333, -2.780000000, -1.446875000),
            ("codex", "median"): (-2.302083333, -2.993333333, -1.650000000),
        }
        self.assertEqual({(r["config"], r["reading"]) for r in self.data["fig3"]}, set(expected))
        for row in self.data["fig3"]:
            with self.subTest(config=row["config"], reading=row["reading"]):
                for field, value in zip(("point", "low", "high"), expected[row["config"], row["reading"]]):
                    self.assertAlmostEqual(row[field], value, delta=1e-9)
                n = {"qwen3-off": 240, "olmo2": 238, "codex": 120}[row["config"]]
                self.assertEqual((row["n"], row["clusters"]), (n, n))

    def test_noninterpolated_interval(self):
        self.assertEqual(mf.order_interval(np.arange(2000)), (49, 1949))

    def test_cluster_resampling(self):
        # Brief v2 #4: two perfectly correlated observations in each cluster.
        samples = [(0 if i < 10 else 100, f"{i:02}") for i in range(20) for _ in range(2)]
        row = mf.summarize(samples, np.random.default_rng(mf.SEED))
        individual = mf.summarize([(v, f"{i:02}") for i, (v, _) in enumerate(samples)],
                                  np.random.default_rng(mf.SEED))
        self.assertEqual((row["point"], row["n"], row["clusters"]), (50, 40, 20))
        self.assertEqual((row["low"], row["high"]), (30, 70))
        self.assertEqual((individual["low"], individual["high"]), (35, 65))
        self.assertLess(row["low"], individual["low"])
        self.assertGreater(row["high"], individual["high"])
        # Retain the unequal-size check for the observation-weighted point.
        unequal = mf.summarize([(0, "a"), (100, "b"), (100, "b")], np.random.default_rng(mf.SEED))
        self.assertAlmostEqual(unequal["point"], 200 / 3)

    def test_outputs(self):
        self.check_outputs(mf.OUT)

    def test_english_outputs(self):
        self.check_outputs(self.en_output, self.en_data)
        english = json.loads((self.en_output / "figure_data.json").read_text(encoding="utf-8"))
        for figure in ('fig1', 'fig2', 'fig3', 'h4b'):
            self.assertEqual([r for r in english[figure] if r['config'] in mf.CONFIGS], self.data[figure])

    def test_extension_matches_analysis(self):
        analysis = json.loads((mf.AGY_DATA / 'analysis_formal.json').read_text(encoding='utf-8'))
        self.assertEqual(self.en_data['extension_pairs'], analysis['n_planned'])
        self.assertEqual({r['config'] for r in self.en_data['fig1']}, set(mf.CONFIGS + mf.EXTENSION_CONFIGS))
        self.assertEqual({r['config'] for r in self.en_data['fig2']}, set(mf.CONFIGS + mf.EXTENSION_CONFIGS))
        for config in mf.EXTENSION_CONFIGS:
            desc = analysis['descriptives'][config]
            records = mf.load_records(config)
            for row in [r for r in self.en_data['fig1'] if r['config'] == config]:
                target = desc['conditions_all_available'][f"{row['pres']}|{row['ask']}|pooled"]
                self.assertAlmostEqual(row['point'], target['D_mean_pS_minus_pW'] / 2)
                self.assertEqual(row['n'], target['n_D'])
                raw = list(mf.pair_movements(records, row['pres'], row['ask']).values())
                self.assertAlmostEqual(row['point'], sum(v for v, _ in raw) / len(raw))
            for ask in mf.ASKS:
                for pres in ('prior', 'stated', 'reported'):
                    rows = [r for r in self.en_data['fig2'] if (r['config'], r['ask'], r['pres']) == (config, ask, pres)]
                    target = desc['endpoints_all_available'][ask][pres]
                    self.assertEqual(sum(r['n'] for r in rows), target['n'])
                    self.assertAlmostEqual(sum(r['point'] * r['n'] for r in rows) / target['n'], target['rate'])
                    for row in rows:
                        samples = [mf.read_value(r) for unit, r in records.items() if unit[1:] == (pres, row['utype'], ask)]
                        self.assertAlmostEqual(row['point'], sum(v <= 5 or v >= 95 for v in samples) / len(samples))
                        self.assertEqual((row['n'], row['clusters']), (120, 120))

    def test_chinese_data_unchanged(self):
        # Frozen Chinese artifact predates language support; compare all values,
        # including the seed, sample counts and bootstrap interval endpoints.
        stored = json.loads((mf.OUT / "figure_data.json").read_text(encoding="utf-8"))
        self.assertEqual(self.data, stored)

    def check_outputs(self, output, expected=None):
        for name in ("fig1_movement", "fig2_endpoints", "fig3_readings"):
            for ext in ("pdf", "png"):
                content = (output / f"{name}.{ext}").read_bytes()
                self.assertGreater(len(content), 1000)
                self.assertTrue(content.startswith(b"%PDF-" if ext == "pdf" else b"\x89PNG\r\n\x1a\n"))
                if ext == "png":
                    pos = content.index(b"pHYs")
                    x, y, unit = struct.unpack(">IIB", content[pos + 4:pos + 13])
                    self.assertEqual(unit, 1)
                    self.assertAlmostEqual(x * .0254, 300, delta=.1)
                    self.assertEqual(x, y)
        stored = json.loads((output / "figure_data.json").read_text(encoding="utf-8"))
        self.assertEqual(stored, self.data if expected is None else expected)

    def test_utf8_no_question_run(self):
        for path in [mf.HERE / "make_figures.py", mf.HERE / "test_make_figures.py", mf.OUT / "figure_data.json",
                     mf.HERE / "fixtures" / "encoding.md"]:
            self.assertNotIn("?" * 3, path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
