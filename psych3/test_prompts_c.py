"""Mechanical verification of Experiment C materials."""
import hashlib
import importlib.util
import itertools
import json
import random
import unittest
from fractions import Fraction
from pathlib import Path

import prompts_c as p
from gen_c import SEED, all_stories, generate_items, preview

ROOT = Path(__file__).resolve().parent


class PromptTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stories = p.load_stories()
        cls.by_id = {story["id"]: story for story in cls.stories}
        cls.data = generate_items(cls.stories)

    def test_bayes_exact_fractions(self):
        expected = {
            "A": (Fraction(25, 3), Fraction(50), Fraction(1350, 17)),
            "B": (Fraction(1600, 115), Fraction(64), Fraction(960, 11)),
        }
        for acc_set, values in expected.items():
            hit, fa = p.ACCURACY_SETS[acc_set]
            for br, posterior in zip(p.BASE_RATES, values):
                with self.subTest(acc_set=acc_set, br=br):
                    oracle = Fraction(100 * br * hit, br * hit + (100 - br) * fa)
                    self.assertEqual(oracle, posterior)
                    self.assertEqual(p.bayes(br, hit, fa), float(posterior))

    def test_frequency_counts_and_bayes(self):
        expected = {
            "A": ((100, 9900, 90, 990), (1000, 9000, 900, 900),
                  (3000, 7000, 2700, 700)),
            "B": ((100, 9900, 80, 495), (1000, 9000, 800, 450),
                  (3000, 7000, 2400, 350)),
        }
        for acc_set, rows in expected.items():
            hit, fa = p.ACCURACY_SETS[acc_set]
            for br, row in zip(p.BASE_RATES, rows):
                counts = p.frequency_counts(br, hit, fa)
                self.assertEqual(tuple(counts.values()), row)
                self.assertTrue(all(type(value) is int for value in counts.values()))
                self.assertEqual(counts["n_feat"] + counts["n_other"], 10000)
                self.assertLessEqual(counts["n_hit"], counts["n_feat"])
                self.assertLessEqual(counts["n_fa"], counts["n_other"])
                self.assertEqual(p.bayes(br, hit, fa),
                                 float(Fraction(100 * counts["n_hit"],
                                                counts["n_hit"] + counts["n_fa"])))

    def test_reject_noninteger_counts_and_invalid_parameters(self):
        for args in ((1, 90.1, 10), (1, 90, 5.01), (0.001, 90, 10)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                p.frequency_counts(*args)
        for function in (p.frequency_counts, p.bayes):
            for args in ((-1, 90, 10), (1, 101, 10), (1, 90, -1)):
                with self.subTest(function=function, args=args), self.assertRaises(ValueError):
                    function(*args)
        with self.assertRaises(ValueError):
            p.bayes(1, 0, 0)
        for acc_set, format, ask in (("X", "probability", "direct"),
                                     ("A", "other", "direct"),
                                     ("A", "probability", "other")):
            with self.assertRaises(ValueError):
                p.render(self.stories[0], 1, acc_set, format, ask)

    def test_asks_identical_to_dnli(self):
        path = ROOT.parent / "dnli" / "prompts.py"
        spec = importlib.util.spec_from_file_location("dnli_prompts_reference", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(p.ASK_DIRECT, module.ASK_DIRECT)
        self.assertEqual(p.ASK_MULTI, module.ASK_MULTI)

    def test_verbatim_templates_and_complete_frame(self):
        story = self.stories[0]
        probability = (
            "Among adults screened at a regional clinic, 1% have a particular thyroid condition. "
            "Each one is checked with a blood test; a positive result means that the blood test comes back positive. "
            "Of those that have a particular thyroid condition, "
            "90% get a positive result. Of all the others, 10% also get a positive result."
        )
        frequency = (
            "Out of every 10,000 adults screened at a regional clinic, 100 have a particular thyroid condition. "
            "Each one is checked with a blood test; a positive result means that the blood test comes back positive. "
            "Of the 100 that have a particular thyroid condition, "
            "90 get a positive result. Of the other 9,900, 990 also get a positive result."
        )
        for format, text in (("probability", probability), ("frequency", frequency)):
            self.assertEqual(p.situation(story, 1, 90, 10, format), text)
            for ask, tail in p.ASKS.items():
                expected = (
                    f"Here is a situation: {text}\n\n"
                    "Now one of them is picked at random from all those with a positive result: "
                    "an adult whose blood test came back positive. Nothing else is known about this case.\n\n"
                    "Using the information above, how likely is it that the following statement is true?\n"
                    "Statement: This adult has the thyroid condition.\n\n"
                    f"{tail}\n\nDo not use any tools; answer directly."
                )
                self.assertEqual(p.render(story, 1, "A", format, ask), expected)

    def test_positive_and_subject_in_every_prompt(self):
        for story, acc_set, br, format, ask in itertools.product(
                self.stories, p.ACCURACY_SETS, p.BASE_RATES, p.FORMATS, p.ASKS):
            with self.subTest(story=story["id"], acc_set=acc_set, br=br,
                              format=format, ask=ask):
                text = p.render(story, br, acc_set, format, ask)
                self.assertIn(f"a positive result means that {story['positive']}.", text)
                self.assertIn(story["subject"], text)
                self.assertIn(
                    "Now one of them is picked at random from all those with a positive result: "
                    f"{story['subject']}. Nothing else is known about this case.", text)

    def test_grid_split_hashes_and_placeholders(self):
        items = self.data["items"]
        self.assertEqual(len(items), 48)
        self.assertEqual({(item["story"], item["acc_set"]) for item in items},
                         set(itertools.product(self.by_id, p.ACCURACY_SETS)))
        units = [unit for item in items for unit in item["units"]]
        self.assertEqual(len(units), 576)
        self.assertEqual(len({unit["unit_id"] for unit in units}), 576)
        splits = {use: {item["story"] for item in items if item["use"] == use}
                  for use in ("dev", "formal")}
        self.assertEqual(len(splits["dev"]), 4)
        self.assertEqual(len(splits["formal"]), 20)
        self.assertFalse(splits["dev"] & splits["formal"])
        self.assertEqual(splits["dev"] | splits["formal"], set(self.by_id))
        shuffled = list(self.by_id)
        random.Random(20261410).shuffle(shuffled)
        self.assertEqual(SEED, 20261410)
        self.assertEqual(splits["dev"], set(shuffled[:4]))
        self.assertEqual(set(self.data["dev_stories"]), splits["dev"])
        self.assertEqual(set(self.data["formal_stories"]), splits["formal"])
        grid = set(itertools.product(p.BASE_RATES, p.FORMATS, p.ASKS))
        for item in items:
            self.assertEqual(len(item["units"]), 12)
            self.assertEqual({(u["br"], u["format"], u["ask"]) for u in item["units"]}, grid)
            for unit in item["units"]:
                self.assertEqual(unit["story"], item["story"])
                self.assertEqual(unit["acc_set"], item["acc_set"])
                prompt = p.render(self.by_id[unit["story"]], unit["br"],
                                  unit["acc_set"], unit["format"], unit["ask"])
                self.assertNotIn("{", prompt)
                self.assertNotIn("}", prompt)
                self.assertEqual(unit["prompt_sha256"],
                                 hashlib.sha256(prompt.encode("utf-8")).hexdigest())
                self.assertEqual(unit["bayes"],
                                 p.bayes(unit["br"], *p.ACCURACY_SETS[unit["acc_set"]]))

    def test_generated_artifacts_match(self):
        saved = json.loads((ROOT / "items_c.json").read_text(encoding="utf-8"))
        self.assertEqual(saved, self.data)
        self.assertEqual(generate_items(self.stories), self.data)
        text = (ROOT / "items_c_preview.md").read_text(encoding="utf-8")
        self.assertEqual(text, preview(self.stories))
        self.assertEqual(text.count(chr(96) * 3 + "text"), 12)
        self.assertEqual(text.count("Here is a situation:"), 12)
        for format, acc_set, br in itertools.product(p.FORMATS, p.ACCURACY_SETS, p.BASE_RATES):
            self.assertIn(p.render(self.stories[0], br, acc_set, format, "direct"), text)

        all_text = (ROOT / "items_c_all_stories.md").read_text(encoding="utf-8")
        self.assertEqual(all_text, all_stories(self.stories))
        self.assertEqual(all_text.count(chr(96) * 3 + "text"), 24)
        self.assertEqual(all_text.count("Here is a situation:"), 24)
        for story in self.stories:
            self.assertIn(p.render(story, 10, "A", "probability", "direct"), all_text)


if __name__ == "__main__":
    unittest.main()
