"""A brief acceptance checks: A1 loading/review, A2 anchors, A3 wording/grid, A4 parsing, A5-A8 merge."""
import hashlib
import json
import re
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

import gen_a
import parse_a
import prompts_a as p

ROOT = Path(__file__).resolve().parent


def _make_synthetic_questions(anchors_ref):
    special = {
        0: "SYN_ONLY_MARKER_0: How many distinct fjords are on the coast?",
        1: "SYN_ONLY_MARKER_1: How much grain was harvested in 2022 (in metric tons)?",
        11: "SYN_ONLY_MARKER_11: How long is the unmarked trail?",
        31: "SYN_ONLY_MARKER_31: What was the room rate in 2021 (in USD per night)?",
        46: "SYN_ONLY_MARKER_46: What is the fair settlement amount?",
    }
    questions = []
    for i, row in enumerate(anchors_ref):
        q_text = special.get(i, f"SYN_ONLY_MARKER_{i}: What was the synthetic distance in 2020 (in kilometers)?")
        questions.append({
            "question": q_text,
            "true_value": row["true_value"],
            "requirement": "Give a single number.",
            "topic": "synthetic",
        })
    return questions


def _make_fake_selfwritten():
    return [
        {
            "id": f"S{i:02d}",
            "question": f"Synthetic self-written question {i}, in metres?",
            "true_value": 100 + i * 10,
            "unit": "m",
            "time_ref": "fixed",
            "reference_version": f"ref-{i}",
            "status": "verified" if i % 2 == 0 else "verified_after_rewrite",
        }
        for i in range(1, 25)
    ]


class MaterialsA(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.anchors_ref = json.loads((ROOT / 'a_anchors.json').read_text(encoding='utf-8'))
        cls.eligibility = json.loads((ROOT / 'a_eligibility.json').read_text(encoding='utf-8'))
        cls.questions = _make_synthetic_questions(cls.anchors_ref)
        cls.pending = [{'index': i, 'status': 'pending'} for i in range(60)]
        cls.fake_selfwritten = _make_fake_selfwritten()
        cls.selfwritten = p.load_selfwritten()

    def test_a1_loading_and_mechanical_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            q_path = Path(tmp) / "Qsemantic.json"
            q_path.write_text(json.dumps(self.questions), encoding="utf-8")
            loaded = p.load_questions(q_path)
            self.assertEqual(len(loaded), 60)
            q_path.write_text(json.dumps(self.questions[:59]), encoding="utf-8")
            with self.assertRaises(ValueError):
                p.load_questions(q_path)
            bad_row = [dict(self.questions[0])]
            del bad_row[0]["topic"]
            q_path.write_text(json.dumps(bad_row + self.questions[1:]), encoding="utf-8")
            with self.assertRaises(ValueError):
                p.load_questions(q_path)

        self.assertEqual(len(self.questions), 60)
        self.assertTrue(all(p.mechanical_check(q)['finite_positive'] for q in self.questions))
        self.assertEqual(p.mechanical_check(self.questions[1])['unit'], 'metric tons')
        self.assertTrue(p.mechanical_check(self.questions[1])['has_year_or_timepoint'])
        self.assertFalse(p.mechanical_check(self.questions[0])['has_year_or_timepoint'])
        self.assertEqual(p.mechanical_check(self.questions[0])['unit'], 'fjords')
        self.assertIsNone(p.mechanical_check(self.questions[11])['unit'])
        self.assertIsNone(p.mechanical_check(self.questions[46])['unit'])
        self.assertEqual(p.mechanical_check(self.questions[31])['unit'], 'USD per night')
        # No original source anchors or anchoring_item text may affect metadata.
        row = dict(self.questions[11], anchoring_item='in km 2024', low_anchor=1e99)
        self.assertEqual(p.mechanical_check(row), p.mechanical_check(self.questions[11]))

    def test_a2_anchors(self):
        for i, q in enumerate(self.questions):
            a = p.anchors(i, q['true_value'])
            with self.subTest(index=i):
                self.assertGreater(a['low'], 0)
                self.assertGreater(a['high'], a['low'])
                # Ratio closeness must respect the prescribed rounding precision.
                d = Decimal(str(q['true_value']))
                errors = []
                for name, ideal in (('low', d / Decimal('1.5')), ('high', d * Decimal('1.5'))):
                    quantum = (Decimal(1).scaleb(ideal.adjusted() - 2) if d >= 1000 else
                               Decimal(1) if d == d.to_integral_value() else Decimal(1).scaleb(d.as_tuple().exponent))
                    self.assertLessEqual(abs(Decimal(str(a[name])) - ideal), quantum / 2)
                    errors.append(float(quantum / 2))
                low_ideal, high_ideal = float(d / Decimal('1.5')), float(d * Decimal('1.5'))
                self.assertGreaterEqual(a['high'] / a['low'], (high_ideal - errors[1]) / (low_ideal + errors[0]))
                self.assertLessEqual(a['high'] / a['low'], (high_ideal + errors[1]) / (low_ideal - errors[0]))
        cases = [(3, 2, 5), (4.99, 3.33, 7.49), (7.5, 5, 11.3),
                 (67500, 45000, 101000), (1047.0, 698, 1570), (374.0, 249, 561)]
        for v, low, high in cases:
            self.assertEqual((p.anchors(0, v)['low'], p.anchors(0, v)['high']), (low, high))
        for value in (0, -1, float('inf'), float('nan'), True, False, "100", None):
            with self.assertRaises(ValueError):
                p.anchors(0, value)

    def test_a2_synanchors_36_locked_to_a_anchors_json(self):
        eligible_indices = [row['index'] for row in self.eligibility if row['status'] == 'eligible']
        self.assertEqual(len(eligible_indices), 36)
        for idx in eligible_indices:
            expected = self.anchors_ref[idx]
            computed = p.anchors(idx, expected['true_value'])
            self.assertEqual(computed, expected)
            by_str_id = p.anchors(f"A{idx}", expected['true_value'])
            self.assertEqual(by_str_id['low'], expected['low'])
            self.assertEqual(by_str_id['high'], expected['high'])
            self.assertEqual(by_str_id['rounding_rule'], expected['rounding_rule'])

    def test_a3_verbatim_plan(self):
        plan = (ROOT / 'PLAN.md').read_text(encoding='utf-8').split('### 2.5 ')[1].split('## 3 ')[0]
        templates = re.findall(r'```\n(.*?)\n```', plan, re.S)
        self.assertEqual(len(templates), 3)
        for condition, template in zip(('none', 'irrelevant', 'informative'), templates):
            for ask, tail in p.ASKS.items():
                expected = template.replace('{question}', 'Q?').replace('{X}', '123').replace('{数量问法尾段}', tail)
                self.assertEqual(p.render('Q?', condition, ask, None if condition == 'none' else 123), expected)
        for ask in p.ASKS:
            irrelevant = p.render('Q?', 'irrelevant', ask, 123)
            informative = p.render('Q?', 'informative', ask, 123)
            self.assertEqual(irrelevant.count('123'), 2)
            self.assertEqual(informative.count('123'), 2)
            self.assertEqual(irrelevant.split('\n\n')[1:],
                             informative.replace(', taking this information into account.', '.').split('\n\n')[1:])
        direct = re.search(r'数量问法尾段（直接）：(.*?)\n', plan).group(1)
        self.assertEqual(p.ASK_DIRECT, '\n'.join(re.findall(r'`([^`]+)`', direct)))
        multi = re.search(r'数量问法尾段（多估计）：(.*?)\n', plan).group(1)
        quoted = re.findall(r'`([^`]+)`', multi)
        expected = quoted[0] + '\n\n' + quoted[1] + '\n' + ''.join(
            quoted[2].replace(' k:', f' {k}:') + '\n' for k in range(1, 6)) + quoted[3]
        self.assertEqual(p.ASK_MULTI, expected)

    def test_a3_grid_splits_and_eligibility(self):
        self.assertEqual(gen_a.generate_items(self.questions, self.pending)['items'], [])
        data = gen_a.generate_items(self.questions, self.pending, True)
        self.assertEqual(data, gen_a.generate_items(self.questions, self.pending, preview_all=True))
        self.assertEqual(len(data['items']), 60)
        self.assertEqual(sum(i['split'] == 'dev' for i in data['items']), 10)
        self.assertEqual(sum(i['repeat'] for i in data['items']), 8)
        self.assertTrue(all(i['split'] == 'formal' for i in data['items'] if i['repeat']))
        for item in data['items']:
            self.assertEqual(len(item['units']), 20 if item['repeat'] else 10)
            for unit in item['units']:
                self.assertEqual(unit['prompt_sha256'], hashlib.sha256(unit['prompt'].encode('utf-8')).hexdigest())
        decisions = [dict(row, status='eligible' if row['index'] % 2 == 0 else 'ineligible') for row in self.pending]
        selected = gen_a.generate_items(self.questions, decisions, [])
        self.assertEqual([i['index'] for i in selected['items']], list(range(0, 60, 2)))
        with self.assertRaises(ValueError):
            gen_a.generate_items(self.questions, decisions, True)

    def test_a5_load_selfwritten_and_counterexamples(self):
        self.assertEqual(len(self.selfwritten), 24)
        for row in self.selfwritten:
            a = p.anchors(row['id'], row['true_value'])
            self.assertGreater(a['low'], 0)
            self.assertGreater(a['high'], a['low'])

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp) / "bad_selfwritten.json"

            def check_fails(payload):
                tmp_path.write_text(json.dumps(payload), encoding="utf-8")
                with self.assertRaises(ValueError):
                    p.load_selfwritten(tmp_path)

            # Wrong count or type
            check_fails({"not": "a list"})
            check_fails(self.fake_selfwritten[:23])
            check_fails(self.fake_selfwritten + [dict(self.fake_selfwritten[0], id="S99")])
            check_fails(["not a dict"] + self.fake_selfwritten[1:])

            # Duplicate ID
            dup = [dict(r) for r in self.fake_selfwritten]
            dup[1]["id"] = dup[0]["id"]
            check_fails(dup)

            # Invalid ID prefix / format
            for bad_id in ("A01", "C01", "s01", "S", "", " S01", None, 123):
                rows = [dict(r) for r in self.fake_selfwritten]
                rows[0]["id"] = bad_id
                check_fails(rows)

            # Empty or invalid question
            for bad_q in ("", "   ", None, 123):
                rows = [dict(r) for r in self.fake_selfwritten]
                rows[0]["question"] = bad_q
                check_fails(rows)

            # Invalid true_value (non-positive, bool, string, None, or rounding to 0)
            for bad_val in (0, -5, True, False, "100", None):
                rows = [dict(r) for r in self.fake_selfwritten]
                rows[0]["true_value"] = bad_val
                check_fails(rows)
            for non_finite in (float("inf"), float("nan")):
                rows = [dict(r) for r in self.fake_selfwritten]
                rows[0]["true_value"] = non_finite
                with self.assertRaises(ValueError):
                    p.validate_selfwritten(rows)

            # Empty or invalid unit
            for bad_unit in ("", "  ", None, 42):
                rows = [dict(r) for r in self.fake_selfwritten]
                rows[0]["unit"] = bad_unit
                check_fails(rows)

            # Invalid status
            for bad_status in ("pending", "eligible", "ineligible", "rejected", "", None):
                rows = [dict(r) for r in self.fake_selfwritten]
                rows[0]["status"] = bad_status
                check_fails(rows)

    def test_a_selfwritten_anchor_and_split_regression(self):
        expected = {
            'S04': (230000, 517000), 'S06': (203, 458), 'S07': (5230, 11800),
            'S10': (991, 2230), 'S11': (101.49, 228.35), 'S13': (8.2, 18.5),
            'S14': (1270000, 2850000), 'S15': (83, 188), 'S16': (3000000, 6750000),
            'S17': (4230, 9510), 'S18': (73700000, 166000000), 'S21': (63, 141),
            'S22': (110, 248), 'S26': (9990, 22500), 'S29': (350, 788),
            'S31': (808, 1820), 'S33': (174.3, 392.3), 'S36': (32.77, 73.74),
            'S38': (8800, 19800), 'S39': (507, 1140), 'S41': (33, 74),
            'S08': (108, 243), 'S30': (336, 756), 'S34': (77.4, 174.2),
        }
        regenerated = gen_a.generate_items(self.questions, self.eligibility, self.selfwritten)
        stored = json.loads((ROOT / 'items_a_selfwritten.json').read_text(encoding='utf-8'))
        self.assertEqual(gen_a.selfwritten_payload(regenerated), stored)
        self.assertEqual({i['id']: (i['low'], i['high']) for i in stored['items']}, expected)
        self.assertEqual({i['id']: (p.anchors(i['id'], i['true_value'])['low'],
                                   p.anchors(i['id'], i['true_value'])['high'])
                          for i in self.selfwritten}, expected)
        split = json.loads((ROOT / 'a_split.json').read_text(encoding='utf-8'))
        self.assertEqual(gen_a.split_records(regenerated), split)
        self.assertEqual([i['id'] for i in split if i['split'] == 'dev'],
                         ['A12', 'A16', 'A20', 'A34', 'A41', 'A47', 'S10', 'S22', 'S33', 'S34'])
        self.assertEqual([i['id'] for i in split if i['repeat']],
                         ['A18', 'A23', 'A39', 'A43', 'A48', 'S16', 'S36', 'S38'])

    def test_a6_merged_stratified_split_repeat_and_reproducibility(self):
        for sw in (self.fake_selfwritten, self.selfwritten):
            data = gen_a.generate_items(self.questions, self.eligibility, sw)
            again = gen_a.generate_items(self.questions, self.eligibility, sw)
            self.assertEqual(data, again)
            items = data['items']
            self.assertEqual(len(items), 60)

            syn_items = [i for i in items if i['source'] == 'synanchors']
            self_items = [i for i in items if i['source'] == 'selfwritten']
            self.assertEqual(len(syn_items), 36)
            self.assertEqual(len(self_items), 24)
            self.assertTrue(all(re.fullmatch(r"A\d+", i['id']) for i in syn_items))
            self.assertTrue(all(i['id'].startswith("S") for i in self_items))

            # Dev 10 = 6 synanchors + 4 selfwritten; Formal 50 = 30 + 20
            self.assertEqual(sum(i['split'] == 'dev' for i in syn_items), 6)
            self.assertEqual(sum(i['split'] == 'dev' for i in self_items), 4)
            self.assertEqual(sum(i['split'] == 'dev' for i in items), 10)
            self.assertEqual(sum(i['split'] == 'formal' for i in items), 50)

            # Repeat 8 = 5 synanchors + 3 selfwritten, strictly inside formal set
            self.assertEqual(sum(i['repeat'] for i in syn_items), 5)
            self.assertEqual(sum(i['repeat'] for i in self_items), 3)
            self.assertEqual(sum(i['repeat'] for i in items), 8)
            self.assertTrue(all(i['split'] == 'formal' for i in items if i['repeat']))

    def test_a7_unit_ids_unique_and_rounds(self):
        data = gen_a.generate_items(self.questions, self.eligibility, self.fake_selfwritten)
        all_unit_ids = []
        pattern = re.compile(r"^(?:A\d+|S\S+)\|(?:none|irrelevant|informative)\|(?:none|low|high)\|(?:direct|multi)\|r[01]$")
        for item in data['items']:
            expected_rounds = ["r0", "r1"] if item['repeat'] else ["r0"]
            self.assertEqual(len(item['units']), 10 * len(expected_rounds))
            rounds_seen = [u['round'] for u in item['units']]
            self.assertEqual(rounds_seen.count("r0"), 10)
            self.assertEqual(rounds_seen.count("r1"), 10 if item['repeat'] else 0)
            for unit in item['units']:
                uid = unit['unit_id']
                self.assertRegex(uid, pattern)
                self.assertTrue(uid.startswith(f"{item['id']}|"))
                self.assertTrue(uid.endswith(f"|{unit['round']}"))
                all_unit_ids.append(uid)
        self.assertEqual(len(all_unit_ids), 680)
        self.assertEqual(len(set(all_unit_ids)), 680)

    def test_a8_selfwritten_outputs_exclude_synanchors(self):
        data = gen_a.generate_items(self.questions, self.eligibility, self.selfwritten)
        sw_data = gen_a.selfwritten_payload(data)
        self.assertEqual(sw_data['n_items'], 24)
        self.assertEqual(len(sw_data['items']), 24)
        self.assertEqual(sw_data['n_units'], 270)
        for item in sw_data['items']:
            self.assertEqual(item['source'], 'selfwritten')
            self.assertTrue(item['id'].startswith('S'))
            self.assertFalse(item['id'].startswith('A'))
            for unit in item['units']:
                self.assertTrue(unit['unit_id'].startswith('S'))
                self.assertFalse(unit['unit_id'].startswith('A'))

        sw_json = json.dumps(sw_data, ensure_ascii=False)
        self.assertNotIn("SYN_ONLY_MARKER_", sw_json)
        self.assertIsNone(re.search(r'"A\d+', sw_json))

        preview_md = gen_a.preview_selfwritten(self.selfwritten)
        self.assertNotIn("SYN_ONLY_MARKER_", preview_md)
        for row in self.selfwritten:
            self.assertIn(f"## {row['id']} ", preview_md)
            self.assertIn(row['question'], preview_md)
        self.assertEqual(preview_md.count("### 无锚直接 (none, direct)"), 24)
        self.assertEqual(preview_md.count("### 无关锚高直接 (irrelevant, high, direct)"), 24)
        self.assertEqual(preview_md.count("### 有信息锚低多估计 (informative, low, multi)"), 24)

        split_rows = gen_a.split_records(data)
        self.assertEqual(len(split_rows), 60)
        for row in split_rows:
            self.assertEqual(set(row.keys()), {"id", "source", "split", "repeat"})
        split_json = json.dumps(split_rows, ensure_ascii=False)
        self.assertNotIn("SYN_ONLY_MARKER_", split_json)
        self.assertNotIn("question", split_json)


class ParserA(unittest.TestCase):
    def multi(self, values=None, weights=None):
        return '\n'.join(f'Estimate {k}: {v} | Weight: {w}' for k, v, w in
                         zip(range(1, 6), values or ['1e3'] * 5, weights or ['.2'] * 5))

    def test_a4_direct_legal_and_illegal(self):
        for text, unit, expected in [('Estimate: 1.2e6', None, 1200000), ('Estimate: .5 km', 'km', .5),
                                     ('Estimate: 3.25', None, 3.25), ('Estimate: 12\nEstimate: 14', None, 14),
                                     ('<think>Estimate: 1</think>Estimate: 2', None, 2)]:
            self.assertEqual(parse_a.parse_direct(text, unit)['value'], expected)
        for text in ('1,000', '1-2', '1 to 2', '0', '-2', 'nan', 'inf', '1e999', '1 km', '2 extra', '2,', ''):
            self.assertFalse(parse_a.parse_direct('Estimate: ' + text)['ok'], text)
        self.assertFalse(parse_a.parse_direct('Estimate: 1 miles', 'km')['ok'])
        self.assertFalse(parse_a.parse_direct('Estimate: 2\nEstimate:')['ok'])
        self.assertFalse(parse_a.parse_direct('<think>Estimate: 2')['ok'])

    def test_a4_last_group_and_weights(self):
        self.assertTrue(parse_a.parse_multi(self.multi())['ok'])
        self.assertAlmostEqual(parse_a.parse_multi(self.multi())['value'], 1000)
        self.assertTrue(parse_a.parse_multi(self.multi(weights=['.1'] * 5))['ok'])
        self.assertFalse(parse_a.parse_multi(self.multi(weights=['.1'] * 5))['weight_sum_in_tolerance'])
        self.assertFalse(parse_a.parse_multi(self.multi(weights=['1.1'] + ['0'] * 4))['ok'])
        self.assertFalse(parse_a.parse_multi(self.multi(weights=['0'] * 5))['ok'])
        self.assertTrue(parse_a.parse_multi('Estimate 1: bad\n' + self.multi())['ok'])
        self.assertFalse(parse_a.parse_multi(self.multi() + '\nEstimate 1')['ok'])
        self.assertFalse(parse_a.parse_multi(self.multi() + '\nEstimate 6: 1 | Weight: 0')['ok'])
        for bad in ('1,000', '1-2', '1e999', '0', '1 miles'):
            self.assertFalse(parse_a.parse_multi(self.multi(values=[bad] * 5), 'km')['ok'])
        for bad in ('-1', '1.01', '1e-1', '20%', '1/5'):
            self.assertFalse(parse_a.parse_multi(self.multi(weights=[bad] * 5))['ok'])
        self.assertTrue(parse_a.parse_multi(self.multi(values=['1 km'] * 5), 'km')['ok'])


if __name__ == '__main__':
    unittest.main()
