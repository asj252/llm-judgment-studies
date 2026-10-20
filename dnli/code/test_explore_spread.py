"""Tests of arithmetic, pairing, audit and whole-cluster resampling."""
import itertools
import math
import unittest

import numpy as np
import explore_spread as e


class CandidateTests(unittest.TestCase):
    def test_manual_sd_and_normalization(self):
        result = dict(estimates=[0, 10, 20, 30, 100], weights=[2, 2, 2, 2, 0])
        s = e.candidate_stats(result)
        self.assertAlmostEqual(s["mean"], 15)
        self.assertAlmostEqual(s["sd"], math.sqrt(125))
        self.assertEqual(s["weight_sum"], 8)
        self.assertEqual(s["range"], 100)
        result["weights"] = [0.25, 0.25, 0.25, 0.25, 0]
        self.assertEqual(e.candidate_stats(result)["sd"], s["sd"])

    def test_identical_and_zero_weight(self):
        s = e.candidate_stats(dict(estimates=[37] * 5, weights=[0.1, 0.2, 0.3, 0.4, 0]))
        self.assertEqual(s["sd"], 0)
        self.assertTrue(s["identical"])
        s = e.candidate_stats(dict(estimates=[0, 10, 20, 30, 40], weights=[1, 0, 0, 0, 0]))
        self.assertEqual(s["sd"], 0)
        self.assertFalse(s["identical"])

    def test_invalid_is_missing(self):
        for weights in ([0] * 5, [-1, 1, 1, 1, 1], [float("nan")] * 5, [float("inf")] * 5, [1]):
            self.assertIsNone(e.candidate_stats(dict(estimates=[10] * 5, weights=weights)))
        self.assertIsNone(e.candidate_stats({}))

    def test_stored_sd_agreement_actual_data(self):
        expected = {"qwen3-off": 1200, "olmo2": 1197, "codex": 600}
        for config, n in expected.items():
            with self.subTest(config=config):
                records, audit, mismatches = e.load_records(config)
                self.assertEqual(len(records), n)
                self.assertEqual(audit["stored_sd_present"], n)
                self.assertEqual(audit["stored_sd_match"], n)
                self.assertEqual(audit["stored_sd_match_rate"], 1)
                self.assertEqual(mismatches, [])


class RelativeSpreadTests(unittest.TestCase):
    def test_manual_relative_spread(self):
        stats = e.candidate_stats(dict(estimates=[0, 10, 20, 30, 100], weights=[2, 2, 2, 2, 0]))
        self.assertAlmostEqual(stats["r"], math.sqrt(125 / (15 * 85)))
        self.assertEqual(e.candidate_stats(dict(estimates=[37] * 5, weights=[1] * 5))["r"], 0)
        # Bernoulli support attains the bound close to either endpoint.
        for probability in (1e-8, 0.01, 0.5, 0.99, 1 - 1e-8):
            with self.subTest(probability=probability):
                stats = e.candidate_stats(dict(estimates=[0, 100, 50, 70, 80],
                                              weights=[1 - probability, probability, 0, 0, 0]))
                self.assertAlmostEqual(stats["r"], 1, places=8)
        for x in ([0, 2, 0, 5, 6], [100, 2, 100, 5, 6], [100] * 5):
            stats = e.candidate_stats(dict(estimates=x, weights=[0.1, 0, 0.2, 0, 0]))
            self.assertIsNone(stats["r"])
        self.assertIsNone(e.relative_spread(0, 0))
        self.assertIsNone(e.relative_spread(0, 100))

    def test_missing_counts_and_ten_bins(self):
        records = {}
        for i, mean in enumerate((0, 5, 10, 90, 100)):
            records[(str(i), "prior", "-")] = dict(mean=mean, sd=i, r=None if mean in (0, 100) else i / 10)
        cells = e.relative_descriptions(records)
        prior = cells["prior:-"]
        self.assertEqual((prior["n"], prior["r_valid"], prior["r_missing"]), (5, 3, 2))
        self.assertEqual(prior["mean_m"], 41)
        self.assertAlmostEqual(prior["mean_r"], 0.2)
        bins = prior["sd_by_m_bin"]
        self.assertEqual(len(bins), 10)
        self.assertEqual([b["n"] for b in bins], [2, 1, 0, 0, 0, 0, 0, 0, 0, 2])
        self.assertEqual(bins[0]["mean_sd"], 0.5)
        self.assertEqual(bins[-1]["mean_sd"], 3.5)
        self.assertIsNone(bins[2]["mean_sd"])
        self.assertIsNone(cells["stated:S"]["mean_m"])
        self.assertIsNone(cells["stated:S"]["mean_r"])

    def test_r_required_cells_and_sensitivity(self):
        requirements = {"change:stated:S": {0, 1}, "change:stated:W": {0, 2},
                        "change:reported:S": {0, 3}, "change:reported:W": {0, 4},
                        "reported_minus_stated:S": {1, 3}, "reported_minus_stated:W": {2, 4},
                        "reported_minus_stated:pooled": {1, 2, 3, 4}}
        for mask in itertools.product((False, True), repeat=5):
            valid = {i for i, ok in enumerate(mask) if ok}
            records = {("pair", *cell): dict(sd=i, r=i / 10 if i in valid else None,
                                             weight_sum=1, cluster="c") for i, cell in enumerate(e.CELLS)}
            for name, required in requirements.items():
                samples = e.contrast_samples(records, name, metric="r")
                self.assertEqual(len(samples), int(required <= valid), (mask, name))
                for bad in range(5):
                    records[("pair", *e.CELLS[bad])]["weight_sum"] = 0.94
                    self.assertEqual(len(e.contrast_samples(records, name, True, metric="r")),
                                     int(required <= valid and bad not in required))
                    records[("pair", *e.CELLS[bad])]["weight_sum"] = 1
        for name, expected in (("change:stated:S", 0.1), ("reported_minus_stated:S", 0.2),
                               ("reported_minus_stated:pooled", 0.2)):
            self.assertAlmostEqual(e.contrast_samples(records, name, metric="r")[0][1], expected)

    def test_actual_r_counts_and_bounds(self):
        output = e.compute_relative()
        for config in e.CONFIGS:
            records, _, _ = e.load_records(config)
            data = output["configs"][config]
            missing = sum(r["r"] is None for r in records.values())
            self.assertEqual(data["audit"]["r_missing_endpoints"], missing)
            self.assertEqual(data["audit"]["r_valid"], len(records) - missing)
            for cell in data["cells"].values():
                self.assertEqual(sum(b["n"] for b in cell["sd_by_m_bin"]), cell["n"])
            for row in records.values():
                if row["r"] is not None:
                    self.assertTrue(0 <= row["r"] <= 1)
            for section in ("contrasts", "sensitivity"):
                for name, summary in data[section].items():
                    keys = {u[0] for u in records}
                    eligible = {key for key in keys if all(
                        (key, *cell) in records and records[(key, *cell)]["r"] is not None
                        and (section != "sensitivity" or 0.95 <= records[(key, *cell)]["weight_sum"] <= 1.05)
                        for cell in e.specs()[name])}
                    self.assertEqual(summary["n"], len(eligible))


class BootstrapTests(unittest.TestCase):
    def test_whole_cluster_not_row_sampling_and_seed(self):
        samples = [("a", 0, "one"), ("b", 0, "one"), ("c", 10, "two"), ("d", 10, "two")]
        a = e.bootstrap_replicates(samples, np.random.default_rng(e.SEED))
        b = e.bootstrap_replicates(samples, np.random.default_rng(e.SEED))
        self.assertEqual(a, b)
        self.assertEqual(set(a), {0, 5, 10})
        rng = np.random.default_rng(e.SEED)
        individual = np.asarray([0, 0, 10, 10])[rng.integers(0, 4, size=(2000, 4))].mean(axis=1)
        self.assertIn(2.5, individual)
        self.assertNotIn(2.5, a)

    def test_unequal_clusters_keep_pair_weights_and_multiplicity(self):
        samples = [("a", 0, "one"), ("b", 0, "one"), ("c", 10, "two")]
        reps = e.bootstrap_replicates(samples, np.random.default_rng(e.SEED))
        self.assertEqual(set(reps), {0, 10 / 3, 10})
        self.assertAlmostEqual(e.summarize(samples, np.random.default_rng(e.SEED))["point"], 10 / 3)

    def test_noninterpolated_interval(self):
        self.assertEqual(e.order_interval(list(range(2000))), [49, 1949])

    def test_spearman_ties_and_undefined(self):
        self.assertAlmostEqual(e.spearman([(1, 3), (1, 2), (2, 1)]), -math.sqrt(3) / 2)
        self.assertIsNone(e.spearman([(1, 3), (1, 2)]))
        samples = [("a", (1, 3), "a"), ("b", (2, 4), "b")]
        summary = e.summarize(samples, np.random.default_rng(e.SEED), correlation=True)
        self.assertEqual(summary["point"], 1)
        self.assertGreater(summary["undefined_bootstrap"], 0)
        self.assertIsNone(summary["ci95"])


class PairingTests(unittest.TestCase):
    def test_every_missingness_pattern(self):
        cells = [("prior", "-"), ("stated", "S"), ("stated", "W"), ("reported", "S"), ("reported", "W")]
        # Independent expected requirements, indexed in the five-cell fixture.
        requirements = {"change:stated:S": {0, 1}, "change:stated:W": {0, 2},
                        "change:reported:S": {0, 3}, "change:reported:W": {0, 4},
                        "reported_minus_stated:S": {1, 3}, "reported_minus_stated:W": {2, 4},
                        "reported_minus_stated:pooled": {1, 2, 3, 4}, "spearman": {0, 1, 2}}
        for mask in itertools.product((False, True), repeat=5):
            present = {i for i, valid in enumerate(mask) if valid}
            records = {("pair", *cells[i]): dict(sd=i, mean=10*i, weight_sum=1, cluster="c") for i in present}
            for name, required in requirements.items():
                self.assertEqual(len(e.contrast_samples(records, name)), int(required <= present), (mask, name))
                for bad in present:
                    restricted = {k: dict(v) for k, v in records.items()}
                    restricted[("pair", *cells[bad])]["weight_sum"] = 0.94
                    self.assertEqual(len(e.contrast_samples(restricted, name, True)),
                                     int(required <= present and bad not in required), (mask, name, bad))

    def test_contribution_values_and_boundary(self):
        records = {("pair", *cell): dict(sd=i, mean=10*i, weight_sum=0.95 if i % 2 else 1.05, cluster="c")
                   for i, cell in enumerate(e.CELLS)}
        for name, value in (("change:stated:S", 1), ("change:reported:W", 4),
                            ("reported_minus_stated:S", 2), ("reported_minus_stated:pooled", 2),
                            ("spearman", (0, -5))):
            self.assertEqual(e.contrast_samples(records, name, True)[0][1], value)
        records[("pair", "stated", "S")]["cluster"] = "other"
        with self.assertRaises(ValueError):
            e.contrast_samples(records, "spearman")

    def test_actual_counts_independently_from_required_cells(self):
        for config in e.CONFIGS:
            records, _, _ = e.load_records(config)
            keys = {u[0] for u in records}
            for name, needed in e.specs().items():
                for sensitive in (False, True):
                    eligible = {key for key in keys if all((key, *cell) in records and
                                (not sensitive or 0.95 <= records[(key, *cell)]["weight_sum"] <= 1.05)
                                for cell in needed)}
                    samples = e.contrast_samples(records, name, sensitive)
                    self.assertEqual({s[0] for s in samples}, eligible)
                    self.assertEqual(len(samples), len(eligible))


if __name__ == "__main__":
    unittest.main()
