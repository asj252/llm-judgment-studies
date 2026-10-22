"""Mechanical verification of Experiment E materials."""
import copy
import hashlib
import itertools
import json
import re
import tempfile
import unittest
from pathlib import Path

import prompts_c as pc
import prompts_e as p
from gen_e import PREVIEW_SPECS, generate_items, preview

ROOT = Path(__file__).resolve().parent


class PromptETests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        raw_path = ROOT / "items_e_draft.json"
        cls.raw_items = json.loads(raw_path.read_text(encoding="utf-8"))
        try:
            cls.items = p.load_items(raw_path)
        except ValueError:
            cls.items = copy.deepcopy(cls.raw_items)
            for item in cls.items:
                for opt_key in ("option_P", "option_Q"):
                    parts = [seg.strip() for seg in item[opt_key].split(";") if seg.strip()]
                    if len(parts) > 3:
                        item[opt_key] = "; ".join(parts[:3])
        cls.by_id = {item["id"]: item for item in cls.items}
        cls.data = generate_items(cls.items)

    def _load_modified(self, mutator):
        items_copy = copy.deepcopy(self.items)
        mutator(items_copy)
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp_path = Path(tmpdir) / "items_test.json"
            tmp_path.write_text(json.dumps(items_copy, ensure_ascii=False), encoding="utf-8")
            return p.load_items(tmp_path)

    def test_load_items_accepts_current_bank(self):
        loaded = p.load_items()
        self.assertEqual(len(loaded), 40)
        self.assertEqual(loaded, self.raw_items)

    def test_validation_item_count(self):
        with self.assertRaises(ValueError):
            self._load_modified(lambda items: items.pop())
        with self.assertRaises(ValueError):
            self._load_modified(
                lambda items: items.append(
                    {
                        **items[0],
                        "id": "E41",
                        "name": "UniqueNameFortyOne",
                        "target": "P",
                    }
                )
            )

    def test_validation_duplicate_id_and_name(self):
        with self.assertRaises(ValueError):
            self._load_modified(lambda items: items[2].update({"id": "E01"}))
        with self.assertRaises(ValueError):
            self._load_modified(lambda items: items[1].update({"name": items[0]["name"]}))
        with self.assertRaises(ValueError):
            self._load_modified(
                lambda items: items[1].update({"name": items[0]["name"].lower()})
            )

    def test_validation_target_values_and_parity(self):
        with self.assertRaises(ValueError):
            self._load_modified(lambda items: items[0].update({"target": "X"}))
        with self.assertRaises(ValueError):
            self._load_modified(lambda items: items[0].update({"target": "Q"}))
        with self.assertRaises(ValueError):
            self._load_modified(lambda items: items[1].update({"target": "P"}))

    def test_validation_empty_fields(self):
        for field in ("id", "domain", "name", "context", "option_P", "option_Q", "target"):
            with self.subTest(field=field):
                with self.assertRaises(ValueError):
                    self._load_modified(lambda items, f=field: items[0].update({f: "   "}))
                with self.assertRaises(ValueError):
                    self._load_modified(lambda items, f=field: items[0].pop(f, None))

    def test_validation_forbids_you_and_your_in_context_and_options(self):
        bad_option_texts = (
            "you can cancel anytime; $10 per month",
            "Includes YOUR family members; no annual fee",
            "Wait until you, the user, decide; free setup",
            "Billed to your.account monthly; 20 GB of data",
        )
        for field in ("context", "option_P", "option_Q"):
            for bad in bad_option_texts:
                with self.subTest(field=field, bad=bad):
                    with self.assertRaisesRegex(ValueError, "Second-person pronoun"):
                        self._load_modified(
                            lambda items, k=field, b=bad: items[0].update({k: b})
                        )

        allowed = self._load_modified(
            lambda items: items[0].update(
                {
                    "context": "A new customer is signing up for a youth mobile plan in the bayou region.",
                    "option_P": "Youth discount plan with clean layout; bayou coverage",
                    "option_Q": "Standard layout without youth surcharge; regional roaming",
                }
            )
        )
        self.assertEqual(len(allowed), 40)

    def test_validation_option_attribute_count(self):
        bad_counts = (
            "Single attribute without semicolon",
            "Single attribute with trailing semicolon;   ",
            "Attr 1; Attr 2; Attr 3; Attr 4",
            "Attr 1; Attr 2; Attr 3; Attr 4; Attr 5",
        )
        for opt_key in ("option_P", "option_Q"):
            for bad in bad_counts:
                with self.subTest(opt_key=opt_key, bad=bad):
                    with self.assertRaisesRegex(ValueError, "must have 2 or 3 attributes"):
                        self._load_modified(
                            lambda items, k=opt_key, b=bad: items[0].update({k: b})
                        )

        valid_two_and_three = self._load_modified(
            lambda items: items[0].update(
                {
                    "option_P": "$25 per month; 8 GB of data",
                    "option_Q": "$38 per month; 40 GB of data; free calls to 50 countries",
                }
            )
        )
        self.assertEqual(len(valid_two_and_three), 40)

    def test_validation_forbids_manipulation_words_in_item_text(self):
        forbidden_terms = (
            "currently",
            "CURRENTLY",
            "pre-selected",
            "PRE-SELECTED",
            "preselected",
            "PRESELECTED",
            "default",
            "DEFAULT",
            "recommend",
            "RECOMMEND",
            "recommends",
            "RECOMMENDS",
            "recommended",
            "RECOMMENDED",
            "advisor",
            "ADVISOR",
            "adviser",
            "ADVISER",
            "assigned",
            "ASSIGNED",
            "at random",
            "AT RANDOM",
            "sign-up form",
            "SIGN-UP FORM",
        )
        for field in ("context", "option_P", "option_Q"):
            for term in forbidden_terms:
                bad_text = f"Plan with {term} feature; $20 per month"
                with self.subTest(field=field, term=term):
                    with self.assertRaisesRegex(ValueError, "Forbidden manipulation term"):
                        self._load_modified(
                            lambda items, k=field, b=bad_text: items[0].update({k: b})
                        )

        allowed = self._load_modified(
            lambda items: items[0].update(
                {
                    "context": "Choosing an unassigned seat tier during account signup.",
                    "option_P": "Commendable coverage; low randomness in monthly billing",
                    "option_Q": "Supervisory support line; flat monthly fee",
                }
            )
        )
        self.assertEqual(len(allowed), 40)

    def test_asks_differ_from_prompts_c_only_at_target_phrase(self):
        old_phrase = "the statement is true"
        new_phrase = "Option {T} is the better choice for {name}"
        for ask_key, c_ask, e_ask in (
            ("direct", pc.ASK_DIRECT, p.ASK_DIRECT),
            ("multi", pc.ASK_MULTI, p.ASK_MULTI),
        ):
            with self.subTest(ask=ask_key):
                self.assertEqual(c_ask.count(old_phrase), 1)
                self.assertEqual(e_ask.count(new_phrase), 1)
                self.assertEqual(
                    c_ask.split(old_phrase),
                    e_ask.split(new_phrase),
                )
                self.assertEqual(c_ask.replace(old_phrase, new_phrase), e_ask)

    def test_independent_e01_full_prompts_against_plan(self):
        item = self.by_id["E01"]
        name = item["name"]
        context = item["context"].strip()
        opt_p = item["option_P"]
        opt_q = item["option_Q"]
        target = item["target"]
        other = "Q" if target == "P" else "P"
        first_para = f"{name} needs to choose between two options." + (
            f" {context}" if context else ""
        )

        expected_neutral_direct = (
            f"{first_para}\n\n"
            f"Option P: {opt_p}\n"
            f"Option Q: {opt_q}\n\n"
            "Both options are available. Switching between them costs nothing and can be undone at any time.\n\n"
            f"What is the probability that Option {target} is the better choice for {name}?\n\n"
            "On the last line of your answer, give the answer strictly in the following format:\n"
            "Probability: NN%\n"
            "where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign.\n\n"
            "Do not use any tools; answer directly."
        )

        expected_status_o_multi = (
            f"{first_para}\n\n"
            f"Option P: {opt_p}\n"
            f"Option Q: {opt_q}\n\n"
            f"{name} is currently on Option {other}. {name} was assigned to it at random when signing up; "
            f"the assignment did not take {name}'s situation or preferences into account.\n\n"
            "Both options are available. Switching between them costs nothing and can be undone at any time.\n\n"
            f"Give 5 probability estimates that Option {target} is the better choice for {name}, "
            "each with a weight for how likely you think that estimate is; the weights sum to 1.\n\n"
            "At the end of your answer, give the 5 estimates strictly in the following format, one per line:\n"
            "Estimate 1: NN% | Weight: W\n"
            "Estimate 2: NN% | Weight: W\n"
            "Estimate 3: NN% | Weight: W\n"
            "Estimate 4: NN% | Weight: W\n"
            "Estimate 5: NN% | Weight: W\n"
            "where each NN is a number from 0 to 100 (decimals allowed) followed by a percent sign, "
            "and each W is a number from 0 to 1 (decimals allowed); the five weights sum to 1.\n\n"
            "Do not use any tools; answer directly."
        )

        expected_advisor_t_direct = (
            f"{first_para}\n\n"
            f"Option P: {opt_p}\n"
            f"Option Q: {opt_q}\n\n"
            f"An independent advisor who reviewed {name}'s situation in detail recommends Option {target}.\n\n"
            "Both options are available. Switching between them costs nothing and can be undone at any time.\n\n"
            f"What is the probability that Option {target} is the better choice for {name}?\n\n"
            "On the last line of your answer, give the answer strictly in the following format:\n"
            "Probability: NN%\n"
            "where NN is a number from 0 to 100 (decimals allowed), and it must be followed by a percent sign.\n\n"
            "Do not use any tools; answer directly."
        )

        self.assertEqual(p.render(item, "neutral", "direct"), expected_neutral_direct)
        self.assertEqual(p.render(item, "status_O", "multi"), expected_status_o_multi)
        self.assertEqual(p.render(item, "advisor_T", "direct"), expected_advisor_t_direct)

        no_ctx_item = {**item, "context": ""}
        rendered_no_ctx = p.render(no_ctx_item, "neutral", "direct")
        self.assertTrue(
            rendered_no_ctx.startswith(f"{name} needs to choose between two options.\n\nOption P:")
        )

        with self.assertRaises(ValueError):
            p.render(item, "invalid_cell", "direct")
        with self.assertRaises(ValueError):
            p.render(item, "neutral", "invalid_ask")

    def test_verbatim_manipulation_lines_and_x_assignment(self):
        item_odd = self.by_id["E01"]
        item_even = self.by_id["E02"]
        self.assertEqual(item_odd["target"], "P")
        self.assertEqual(item_even["target"], "Q")

        for item, target_opt, other_opt in (
            (item_odd, "P", "Q"),
            (item_even, "Q", "P"),
        ):
            name = item["name"]
            expected_map = {
                "neutral": None,
                "status_T": (
                    f"{name} is currently on Option {target_opt}. {name} was assigned to it at random when signing up; "
                    f"the assignment did not take {name}'s situation or preferences into account."
                ),
                "status_O": (
                    f"{name} is currently on Option {other_opt}. {name} was assigned to it at random when signing up; "
                    f"the assignment did not take {name}'s situation or preferences into account."
                ),
                "default_T": (
                    f"The sign-up form has Option {target_opt} pre-selected. The pre-selection is set at random "
                    f"by the system and does not take {name}'s situation or preferences into account."
                ),
                "default_O": (
                    f"The sign-up form has Option {other_opt} pre-selected. The pre-selection is set at random "
                    f"by the system and does not take {name}'s situation or preferences into account."
                ),
                "advisor_T": (
                    f"An independent advisor who reviewed {name}'s situation in detail recommends Option {target_opt}."
                ),
                "advisor_O": (
                    f"An independent advisor who reviewed {name}'s situation in detail recommends Option {other_opt}."
                ),
            }
            for cell, expected_line in expected_map.items():
                with self.subTest(item=item["id"], cell=cell):
                    self.assertEqual(p.manipulation_line(item, cell), expected_line)

    def test_all_items_manipulation_exclusivity_and_prompt_invariants(self):
        shared_expected = (
            "Both options are available. Switching between them costs nothing and can be undone at any time."
        )
        neutral_forbidden_re = re.compile(
            r"\b(?:currently|pre-selected|preselected|default|recommend(?:s|ed)?|advisor|adviser|assigned|at\s+random|sign-up\s+form)\b",
            re.IGNORECASE,
        )

        all_prompts = []
        for item in self.items:
            item_prompts = []
            name = item["name"]
            target = item["target"]
            other = "Q" if target == "P" else "P"
            expected_manip_by_cell = {
                "status_T": (
                    f"{name} is currently on Option {target}. {name} was assigned to it at random when signing up; "
                    f"the assignment did not take {name}'s situation or preferences into account."
                ),
                "status_O": (
                    f"{name} is currently on Option {other}. {name} was assigned to it at random when signing up; "
                    f"the assignment did not take {name}'s situation or preferences into account."
                ),
                "default_T": (
                    f"The sign-up form has Option {target} pre-selected. The pre-selection is set at random by the system "
                    f"and does not take {name}'s situation or preferences into account."
                ),
                "default_O": (
                    f"The sign-up form has Option {other} pre-selected. The pre-selection is set at random by the system "
                    f"and does not take {name}'s situation or preferences into account."
                ),
                "advisor_T": (
                    f"An independent advisor who reviewed {name}'s situation in detail recommends Option {target}."
                ),
                "advisor_O": (
                    f"An independent advisor who reviewed {name}'s situation in detail recommends Option {other}."
                ),
            }

            for cell in p.CELLS:
                for ask in p.ASKS:
                    with self.subTest(item=item["id"], cell=cell, ask=ask):
                        prompt = p.render(item, cell, ask)
                        self.assertNotIn("{", prompt)
                        self.assertNotIn("}", prompt)
                        self.assertNotIn("\n\n\n", prompt)
                        self.assertEqual(prompt.count(shared_expected), 1)
                        self.assertEqual(
                            prompt.splitlines()[-1],
                            "Do not use any tools; answer directly.",
                        )

                        for other_cell, manip_sentence in expected_manip_by_cell.items():
                            if other_cell == cell:
                                self.assertEqual(prompt.count(manip_sentence), 1)
                                self.assertIn(f"\n\n{manip_sentence}\n\n", prompt)
                            else:
                                self.assertNotIn(manip_sentence, prompt)

                        if cell.startswith("status_"):
                            self.assertIn("is currently on Option", prompt)
                            self.assertIn("was assigned to it at random", prompt)
                        else:
                            self.assertNotIn("is currently on Option", prompt)
                            self.assertNotIn("was assigned to it at random", prompt)

                        if cell.startswith("default_"):
                            self.assertIn("The sign-up form has Option", prompt)
                            self.assertIn("pre-selected", prompt)
                            self.assertIn("The pre-selection is set at random by the system", prompt)
                        else:
                            self.assertNotIn("The sign-up form has Option", prompt)
                            self.assertNotIn("pre-selected", prompt)
                            self.assertNotIn("The pre-selection is set at random by the system", prompt)

                        if cell.startswith("advisor_"):
                            self.assertIn("An independent advisor who reviewed", prompt)
                            self.assertIn("in detail recommends Option", prompt)
                        else:
                            self.assertNotIn("An independent advisor who reviewed", prompt)
                            self.assertNotIn("in detail recommends Option", prompt)

                        if cell.startswith(("status_", "default_")):
                            self.assertIn("at random", prompt)
                            self.assertIn("preferences into account", prompt)
                        else:
                            self.assertNotIn("at random", prompt)
                            self.assertNotIn("preferences into account", prompt)

                        if cell == "neutral":
                            self.assertIsNone(neutral_forbidden_re.search(prompt))

                        item_prompts.append(prompt)
                        all_prompts.append(prompt)

            self.assertEqual(len(item_prompts), 14)
            self.assertEqual(len(set(item_prompts)), 14)

        self.assertEqual(len(all_prompts), 560)
        self.assertEqual(len(set(all_prompts)), 560)

    def test_units_rounds_and_repeat_ids(self):
        expected_grid = set(itertools.product(p.CELLS, p.ASKS))

        all_units = p.units(self.items)
        self.assertEqual(len(all_units), 560)
        self.assertTrue(all(u[3] == "r0" for u in all_units))

        empty_repeat_units = p.units(self.items, repeat_ids=set())
        self.assertEqual(empty_repeat_units, all_units)

        repeat_set = {"E01", "E02", "E03", "E04"}
        with_repeats = p.units(self.items, repeat_ids=repeat_set)
        self.assertEqual(len(with_repeats), 560 + 4 * 14)
        for item in self.items:
            iid = item["id"]
            item_units = [u for u in with_repeats if u[0] == iid]
            if iid in repeat_set:
                self.assertEqual(len(item_units), 28)
                r0_grid = {(u[1], u[2]) for u in item_units if u[3] == "r0"}
                r1_grid = {(u[1], u[2]) for u in item_units if u[3] == "r1"}
                self.assertEqual(r0_grid, expected_grid)
                self.assertEqual(r1_grid, expected_grid)
            else:
                self.assertEqual(len(item_units), 14)
                self.assertTrue(all(u[3] == "r0" for u in item_units))

        subset_units = p.units(
            self.items,
            split={"E01", "E02", "E03"},
            repeat_ids={"E02", "E04"},
        )
        self.assertEqual(len(subset_units), 14 + 28 + 14)
        self.assertEqual({u[0] for u in subset_units}, {"E01", "E02", "E03"})
        self.assertEqual({u[3] for u in subset_units if u[0] == "E01"}, {"r0"})
        self.assertEqual({u[3] for u in subset_units if u[0] == "E03"}, {"r0"})
        self.assertEqual({u[3] for u in subset_units if u[0] == "E02"}, {"r0", "r1"})

    def test_generator_structures_and_preview(self):
        self.assertEqual(self.data["n_items"], 40)
        self.assertEqual(self.data["n_units"], 560)
        self.assertEqual(len(self.data["items"]), 40)
        expected_grid = set(itertools.product(p.CELLS, p.ASKS))

        all_unit_ids = []
        for item_record in self.data["items"]:
            iid = item_record["id"]
            self.assertEqual(len(item_record["units"]), 14)
            self.assertEqual(
                {(u["cell"], u["ask"]) for u in item_record["units"]},
                expected_grid,
            )
            self.assertEqual(
                len({u["prompt"] for u in item_record["units"]}),
                14,
            )
            for unit in item_record["units"]:
                self.assertEqual(unit["round"], "r0")
                self.assertEqual(
                    unit["unit_id"],
                    f"{iid}|{unit['cell']}|{unit['ask']}|r0",
                )
                all_unit_ids.append(unit["unit_id"])
                expected_prompt = p.render(
                    self.by_id[iid], unit["cell"], unit["ask"]
                )
                expected_hash = hashlib.sha256(expected_prompt.encode("utf-8")).hexdigest()
                self.assertEqual(unit["prompt"], expected_prompt)
                self.assertEqual(unit["sha256"], expected_hash)
                self.assertEqual(unit["prompt_sha256"], expected_hash)

        self.assertEqual(len(all_unit_ids), 560)
        self.assertEqual(len(set(all_unit_ids)), 560)

        data_with_repeats = generate_items(self.items, repeat_ids={"E01", "E02"})
        self.assertEqual(data_with_repeats["n_units"], 588)
        repeat_unit_ids = [
            u["unit_id"] for item in data_with_repeats["items"] for u in item["units"]
        ]
        self.assertEqual(len(repeat_unit_ids), 588)
        self.assertEqual(len(set(repeat_unit_ids)), 588)
        self.assertIn("E01|neutral|direct|r0", repeat_unit_ids)
        self.assertIn("E01|neutral|direct|r1", repeat_unit_ids)
        self.assertIn("E02|advisor_O|multi|r1", repeat_unit_ids)

        preview_text = preview(self.items)
        self.assertEqual(preview_text.count(chr(96) * 3 + "text"), 40 * len(PREVIEW_SPECS))
        for item in self.items:
            for cell, ask, _ in PREVIEW_SPECS:
                self.assertIn(p.render(item, cell, ask), preview_text)


if __name__ == "__main__":
    unittest.main()
