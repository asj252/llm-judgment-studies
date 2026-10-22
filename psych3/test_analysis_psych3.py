"""Synthetic acceptance checks for brief-e-analysis.md requirements 1-4, 6-7."""
import copy
import itertools
import json
import math
from pathlib import Path
import unittest
import uuid
import shutil
from unittest.mock import patch

import analysis_psych3 as A
import analyse_psych3 as CLI


def item(exp, cells=None, **kwargs):
    return dict(exp=exp, item_id='x', cluster='x', cells=cells or {}, **kwargs)


def fixture(exp):
    if exp == 'A':
        cells = {(a, f, l): v for a in A.ASKS for f in ('irrelevant', 'informative') for l, v in [('low', 10), ('high', 20)]}
        return item(exp, cells, low=10, high=20, true_value=15)
    if exp == 'B':
        return item(exp, {(a, c, k): v+(2 if a=='multi' else 0) for a in A.ASKS
                         for c, v in [('F', 20), ('HI', 30), ('HP', 45), ('PO', 90)] for k in (1, 2)})
    if exp == 'C':
        i = item(exp, acc_set='A')
        i['cells'] = {(a, f, b): A.bayes(i, b) for a in A.ASKS for f in ('probability', 'frequency') for b in A.BR}
        return i
    if exp == 'D':
        return item(exp, {(a, p, s): v+(3 if a=='multi' and s=='conj' else 0)
                         for a in A.ASKS for p in ('S', 'J')
                         for s, v in [('a', 70), ('b', 20), ('conj', 40 if p=='S' else 25), ('disj', 80)]}, type='P')
    return item(exp, {(a, c): v+(3 if a=='multi' and c.endswith('_T') else 0)
                     for a in A.ASKS for c, v in [('neutral', 50), ('status_T', 65), ('status_O', 45),
                       ('default_T', 55), ('default_O', 45), ('recommend_T', 80), ('recommend_O', 20)]})


class MetricsTests(unittest.TestCase):
    def test_all_twenty_hand_calculated_metrics(self):
        expected = {'A': [1, 0, 0, 0], 'B': [10, 15, 0, -2],
                    'C': [0, 0, 0, 0], 'D': [20, 15, 3, 3], 'E': [20, 10, 3, 3]}
        for exp, values in expected.items():
            for n, truth in enumerate(values, 1):
                with self.subTest(name=f'{exp}{n}'):
                    self.assertAlmostEqual(A.contribution(fixture(exp), f'{exp}{n}')['value'], truth)

    def test_nonzero_asymmetric_A_and_C_directions(self):
        # AI values: direct irrelevant=1, informative=3;
        # multi irrelevant=4, informative=9, hence S: 2 versus 5.
        i = fixture('A')
        for (ask, frame), power in {('direct', 'irrelevant'): 1,
                ('direct', 'informative'): 3, ('multi', 'irrelevant'): 4,
                ('multi', 'informative'): 9}.items():
            i['cells'][(ask, frame, 'low')] = 10
            i['cells'][(ask, frame, 'high')] = 10*2**power
        for j, expected in enumerate((1, 2, 3, 3), 1):
            self.assertAlmostEqual(A.contribution(i, f'A{j}')['value'], expected)
        # At base rates 1,10,30 the direct probability reports are 50,50,50
        # (slope 0); frequency reports equal the base rates (slope 1).
        # Multi probability reports 99,90,70 have logit slope -1.
        i = fixture('C')
        for b in A.BR:
            i['cells'][('direct', 'probability', b)] = 50
            i['cells'][('direct', 'frequency', b)] = b
            i['cells'][('multi', 'probability', b)] = 100-b
        # Bayes truths are 25/3, 50, 1350/17; compute MAE from rational errors.
        direct_error = (abs(50-25/3)+abs(50-50)+abs(50-1350/17))/3
        multi_error = (abs(99-25/3)+abs(90-50)+abs(70-1350/17))/3
        for j, expected in enumerate((1, 1, -1, multi_error-direct_error), 1):
            self.assertNotEqual(expected, 0)
            self.assertAlmostEqual(A.contribution(i, f'C{j}')['value'], expected)

    def test_A_actual_rounded_anchor_distance(self):
        i = fixture('A')
        i.update(low=7, high=16)
        self.assertAlmostEqual(A.contribution(i, 'A1')['value'], math.log(2)/math.log(16/7))

    def test_C_intercept_three_points_and_clipping(self):
        ys = [100/(1+math.exp(-(.4+.7*A.logit(b, 0)))) for b in A.BR]
        r = A.regression(ys)
        self.assertAlmostEqual(r['slope'], .7)
        self.assertAlmostEqual(r['intercept'], .4)
        self.assertTrue(math.isfinite(A.regression([0, 50, 100])['slope']))
        i = fixture('C')
        i['cells'][('direct', 'probability', 10)] = 0
        self.assertAlmostEqual(A.component(i, ('direct', 'error'))[0], 50/3)
        del i['cells'][('direct', 'probability', 10)]
        self.assertIsNone(A.component(i, ('direct', 'probability'))[0])

    def test_C_story_equal_weight_and_paired_completeness(self):
        first = fixture('C')
        second = copy.deepcopy(first)
        second.update(acc_set='B', item_id='second')
        self.assertEqual(A.cluster_values([first, second], 'C1')['x']['n_items'], 2)
        del second['cells'][('direct', 'probability', 1)]
        self.assertIsNone(A.cluster_values([first, second], 'C1')['x']['value'])

    def test_D_W_excluded_from_confirmation(self):
        i = fixture('D')
        i['type'] = 'W'
        self.assertEqual(A.cluster_values([i], 'D1'), {})


class MissingTests(unittest.TestCase):
    def test_B_linear_endpoint_substitutions_all_hypotheses(self):
        i = fixture('B')
        for n in ('B1', 'B2', 'B3', 'B4'):
            _, terms = A.expression('B', n)
            for key in terms:
                bad = copy.deepcopy(i)
                del bad['cells'][key]
                bounds = A.contribution(bad, n)
                endpoints = []
                for v in (0, 100):
                    bad['cells'][key] = v
                    endpoints.append(A.contribution(bad, n)['value'])
                self.assertEqual([bounds['lower'], bounds['upper']], [min(endpoints), max(endpoints)])

    def test_C_exact_slope_box_bound(self):
        extremes = [A.regression(v)['slope'] for v in itertools.product((0, 100), repeat=3)]
        self.assertAlmostEqual(A.slope_limit(), max(extremes))
        self.assertAlmostEqual(-A.slope_limit(), min(extremes))
        i = fixture('C')
        i['cells'] = {}
        self.assertAlmostEqual(A.contribution(i, 'C1')['lower'], 1-A.slope_limit())
        self.assertAlmostEqual(A.contribution(i, 'C2')['lower'], -2*A.slope_limit())
        self.assertAlmostEqual(A.contribution(i, 'C4')['upper'],
                               sum(max(A.bayes(i, b), 100-A.bayes(i, b)) for b in A.BR)/3)

    def test_D_endpoints_match_existing_substitution_table(self):
        import bounds_d
        i = fixture('D')
        for key in [('direct', 'S', 'conj'), ('multi', 'S', 'b'), ('direct', 'J', 'a'), ('multi', 'J', 'b')]:
            del i['cells'][key]
        def cell(a, p):
            return {s: i['cells'].get((a, p, s)) for s in A.STATEMENTS}
        self.assertEqual(A.contribution(i, 'D1')['lower'], bounds_d.d1(cell('direct', 'S')))
        self.assertEqual(A.contribution(i, 'D2')['lower'], bounds_d.d2(cell('direct', 'S'), cell('direct', 'J')))
        for n, fn, p in [('D3', bounds_d.d3, 'S'), ('D4', bounds_d.d4, 'J')]:
            r = A.contribution(i, n)
            self.assertEqual((r['lower'], r['upper']), fn(cell('multi', p), cell('direct', p)))

    def test_E_four_term_bounds_exhaustive_observed_preserved(self):
        for name in ('E1', 'E2', 'E3', 'E4'):
            _, terms = A.expression('E', name)
            keys = list(terms)
            for mask in itertools.product((False, True), repeat=len(keys)):
                i = fixture('E')
                missing = [k for k, absent in zip(keys, mask) if absent]
                for k in missing:
                    del i['cells'][k]
                r = A.contribution(i, name)
                brute = []
                for vs in itertools.product((0, 100), repeat=len(missing)):
                    full = copy.deepcopy(i)
                    full['cells'].update(zip(missing, vs))
                    brute.append(A.contribution(full, name)['value'])
                self.assertEqual((r['lower'], r['upper']), (min(brute), max(brute)))
        for n in ('E3', 'E4'):
            r = A.contribution(item('E'), n)
            self.assertEqual((r['lower'], r['upper']), (-200, 200))

    def test_E_reholm_denominator_separate_for_whole_family(self):
        rows = []
        for k in range(10):
            i = fixture('E')
            i.update(item_id=str(k), cluster=str(k))
            rows.append(i)
        full = A.analyse_family(rows, ['E1', 'E2'], B=99)
        self.assertTrue(full['combined'])
        del rows[0]['cells'][('direct', 'status_T')]
        result = A.analyse_family(rows, ['E1', 'E2'], B=99)
        self.assertFalse(result['combined'])
        self.assertEqual(result['complete_subset']['E1']['n_clusters'], 9)
        self.assertEqual(result['missing_protection']['E1']['n_clusters'], 10)
        self.assertIn('E2', result['missing_protection'])

    def test_A_missing_unprotected_annotation(self):
        rows = [fixture('A'), fixture('A')]
        rows[1].update(item_id='y', cluster='y')
        del rows[1]['cells'][('direct', 'irrelevant', 'high')]
        r = A.analyse_family(rows, ['A1'], B=99)
        self.assertIsNone(r['missing_protection'])
        self.assertIn('缺失未受保护', r['complete_subset']['A1']['final']['label'])

    def test_empty_complete_subset_cannot_gain_confirmation(self):
        r = A.analyse_family([item('E')], ['E1'], B=99)
        self.assertFalse(r['complete_subset']['E1']['final']['directional'])
        self.assertEqual(r['complete_subset']['E1']['n_clusters'], 0)

    def test_conservative_p_uses_both_imputed_tails(self):
        self.assertEqual(A.tails([-100, 1, 1, 1], [-1, 100, 100, 100]), (.25, .75))
        rows = [item('E')]
        r = A.analyse_family(rows, ['E1', 'E2', 'E3', 'E4'], B=99)
        self.assertTrue(all(v['p']==1 for v in r['missing_protection'].values()))

    def test_weaker_protected_direction_survives_threshold_downgrade(self):
        rows = []
        for k in range(100):
            i = item('E', {('direct', 'status_T'): 55, ('direct', 'status_O'): 45})
            i.update(item_id=str(k), cluster=str(k))
            rows.append(i)
        for i in rows[:6]:
            del i['cells'][('direct', 'status_T')]
        r = A.analyse_family(rows, ['E1'], B=199)['complete_subset']['E1']
        self.assertEqual(r['strength'], 'bound_exceeds')
        self.assertTrue(r['final']['directional'])
        self.assertNotEqual(r['final']['strength'], 'bound_exceeds')
        self.assertIn('缺失保护：未通过', r['final']['label'])


class InferenceTests(unittest.TestCase):
    def test_every_family_ties_number_order_and_frozen_m(self):
        for exp in 'ABCDE':
            ps = {exp+str(i): .001 for i in (4, 2, 1, 3)}
            r = A.holm(ps)
            self.assertEqual(list(r), [exp+str(i) for i in range(1, 5)])
            self.assertEqual(r[exp+'1']['alpha'], .05/4)
            reduced = A.holm({exp+'3': .001, exp+'1': .001})
            self.assertEqual(reduced[exp+'1']['alpha'], .025)

    def test_holm_stops_and_boundary_inclusive(self):
        r = A.holm({'E1': .0125, 'E2': .02, 'E3': .021, 'E4': .022})
        self.assertTrue(r['E1']['rejected'])
        self.assertFalse(any(r[n]['rejected'] for n in ('E2', 'E3', 'E4')))

    def test_three_levels_strict_bound_inclusive_point_and_negative_wording(self):
        self.assertEqual(A.decision(6, 5.001, 1, True, 5)['strength'], 'bound_exceeds')
        self.assertEqual(A.decision(5, 5, 1, True, 5)['strength'], 'point_reaches')
        self.assertEqual(A.decision(4.99, 1, 1, True, 5)['strength'], 'point_below')
        self.assertFalse(A.decision(6, 0, 1, True, 5)['directional'])
        self.assertFalse(A.decision(6, 2, 1, False, 5)['directional'])
        self.assertEqual(A.decision(-6, -5.01, -1, True, 5)['label'], '区间上界低于负阈值')

    def test_bootstrap_no_interpolation_and_reproducible(self):
        self.assertEqual(A.interval(list(range(100)), .1), [5, 94])
        self.assertEqual(A.interval(list(range(100)), .1, 1), [10, None])
        self.assertEqual(A.bootstrap([1, 2, 3], 20, 7), A.bootstrap([1, 2, 3], 20, 7))
        self.assertEqual(A.bootstrap([7], 20), [7]*20)


class DescriptiveTests(unittest.TestCase):
    def test_spearman_ties_and_degenerate(self):
        self.assertEqual(A.spearman([(1, 2), (1, 2), (3, 4)]), 1)
        self.assertEqual(A.spearman([(1, 4), (2, 3), (3, 1)]), -1)
        self.assertIsNone(A.spearman([(1, 1), (1, 2)]))
    def test_all_experiment_descriptions_and_paired_differences(self):
        r = A.descriptive([fixture(e) for e in 'ABCDE'], B=99)
        self.assertEqual(r['cross_experiment']['B']['e_PO']['difference']['mean'], -2)
        self.assertEqual(r['cross_experiment']['D']['delta_J']['difference']['mean'], 3)
        self.assertIsNone(r['dnli_s'])
        self.assertEqual(len(r['item_details']), 5)

    def test_candidate_weights_and_common_J_weights(self):
        self.assertEqual(A.weighted_mass(dict(estimates=[10, 90], weights=[2, 1]), lambda v: v<50), 2/3)
        i = fixture('D')
        i['results'] = {('multi', 'J', 'conj'): dict(estimates={'conj': [90, 0], 'b': [20, 50]}, weights=[.25, .75])}
        r = A.descriptive([i], B=99)['item_details'][0]['values'][str(('multi', 'J'))]
        self.assertEqual(r['candidate_violation_mass'], .25)

    def test_development_ceilings_and_D_floor(self):
        a, c, d = fixture('A'), fixture('C'), fixture('D')
        a['cells'][('direct', 'none', 'none')] = a['true_value']*1.05
        d['cells'][('direct', 'S', 'conj')] = 0
        r = A.development_diagnostics([a, c, d])
        self.assertTrue(r['A']['known_truth'])
        self.assertTrue(r['C']['ceiling'])
        self.assertTrue(r['D']['floor'])

    def test_A_known_truth_combines_both_unanchored_asks(self):
        rows = []
        for j in range(10):
            i = fixture('A')
            i['cells'][('direct', 'none', 'none')] = 15 if j<8 else 30
            i['cells'][('multi', 'none', 'none')] = 30
            rows.append(i)
        r = A.development_diagnostics(rows)['A']
        self.assertEqual(r['n'], 20)
        self.assertEqual(r['fraction'], .4)
        self.assertFalse(r['known_truth'])
        self.assertEqual(r['descriptive'], [])

    def test_A_log_error_extreme_finite_positive_values(self):
        for y, truth in [(1e-308, 1e308), (1e308, 1e-308)]:
            i = item('A', {('direct', 'none', 'none'): y}, true_value=truth)
            result = A.descriptive([i], B=19)['item_details'][0]['values']
            error = result[str(('direct', 'none', 'none'))]['log_error']
            self.assertTrue(math.isfinite(error))
            self.assertAlmostEqual(error, math.log(y)-math.log(truth))

    def test_E_neutral_per_item_across_and_per_config(self):
        i, j = fixture('E'), fixture('E')
        j['cells'][('direct', 'neutral')] = 80
        r = A.neutral_across_configs({'one': [i], 'two': [j]})
        self.assertEqual(r['per_item']['x']['direct']['mean'], 65)
        self.assertEqual(len(r['per_config']), 2)

    def test_recommendation_control_threshold_denominator_and_missing(self):
        i = fixture('E')
        i['cells'][('multi', 'recommend_T')] = 24
        r = A.recommendation_control([i], B=99)
        self.assertFalse(r['direct']['interpretation_downgrade'])
        self.assertTrue(r['multi']['interpretation_downgrade'])
        self.assertEqual(r['multi']['affected_hypotheses'], ['E3', 'E4'])
        del i['cells'][('direct', 'recommend_T')]
        r = A.recommendation_control([i], B=99)['direct']
        self.assertEqual(r['complete']['n'], 0)
        self.assertEqual(r['missing_bounds'], [-20, 80])
        self.assertEqual(r['note'], '无法评估')

    def test_repeats_kept_out_of_primary_and_call_sd(self):
        i, j = fixture('D'), fixture('D')
        j['cells'][('direct', 'S', 'b')] += 2
        r = A.repeat_description([i], [j])[str(('D', 'direct', 'S', 'b'))]
        self.assertEqual(r['differences'], [2])
        self.assertAlmostEqual(r['call_sd'], math.sqrt(2))


class SecondRoundTests(unittest.TestCase):
    def test_BCD_conservative_Holm_reorders_whole_family(self):
        for exp in 'BCD':
            names = [exp+str(j) for j in range(1, 5)]
            samples = {n: {'x': dict(value=10, lower=10, upper=10, n_items=1, missing_cells=0)} for n in names}
            # One hypothesis has wide missing bounds; its primary p was tied first.
            samples[names[0]]['y'] = dict(value=None, lower=-100, upper=100, n_items=1, missing_cells=1)
            with patch.object(A, 'cluster_values', side_effect=lambda items, n: samples[n]):
                result = A.analyse_family([], names, B=99)
            main, protected = result['complete_subset'], result['missing_protection']
            self.assertFalse(result['combined'])
            self.assertEqual(main[names[0]]['rank'], 1)
            self.assertEqual(protected[names[0]]['rank'], 4)
            self.assertEqual({n: protected[n]['rank'] for n in names},
                             {n: r['rank'] for n, r in A.holm({n: protected[n]['p'] for n in names}).items()})
            self.assertEqual(protected[names[1]]['alpha'], .05/4)
            self.assertTrue(all('final' in main[n] for n in names))
            with patch.object(A, 'cluster_values', side_effect=lambda items, n: {
                    'x': dict(value=10, lower=10, upper=10, n_items=1, missing_cells=0)}):
                self.assertTrue(A.analyse_family([], names, B=19)['combined'])

    def test_C_partial_accuracy_excluded_and_protected_completed_per_hypothesis(self):
        rows = []
        for cl in ('full', 'partial'):
            for acc in ('A', 'B'):
                i = fixture('C')
                i.update(cluster=cl, item_id=cl+acc, acc_set=acc)
                rows.append(i)
        del rows[-1]['cells'][('direct', 'frequency', 1)]
        result = A.analyse_family(rows, ['C1', 'C2'], B=99)
        self.assertEqual(result['complete_subset']['C1']['n_clusters'], 2)
        self.assertEqual(result['complete_subset']['C2']['n_clusters'], 1)
        self.assertEqual(result['missing_protection']['C2']['n_clusters'], 2)
        bounds = A.cluster_values(rows, 'C2')['partial']
        one, two = [A.contribution(i, 'C2') for i in rows[-2:]]
        self.assertAlmostEqual(bounds['lower'], (one['lower']+two['lower'])/2)
        self.assertIsNone(bounds['value'])
        self.assertFalse(result['combined'])
        absent = A.cluster_values(rows[:1], 'C1')['full']
        self.assertIsNone(absent['value'])
        self.assertEqual(absent['n_items'], 2)
        self.assertIsNotNone(absent['lower'])

    def test_A_beyond_anchor_weight_includes_only_strict_crossing(self):
        i = fixture('A')
        i['results'] = {('multi', 'irrelevant', level): dict(estimates=[5, 10, 15, 20, 25], weights=[1, 2, 3, 4, 5])
                        for level in ('low', 'high')}
        values = A.descriptive([i], B=19)['item_details'][0]['values']
        self.assertAlmostEqual(values[str(('multi', 'irrelevant', 'low'))]['candidate_beyond_anchor_mass'], 1/15)
        self.assertAlmostEqual(values[str(('multi', 'irrelevant', 'high'))]['candidate_beyond_anchor_mass'], 5/15)

    def test_A_comparison_first_whole_word_case_and_absence(self):
        for text, expected in [('LOWER then Higher', 'lower'), ('higherness unequal EQUal', 'equal'),
                               ('higher_lower', None), ('no comparison', None), ('(HiGhEr), lower', 'higher')]:
            self.assertEqual(CLI.extract_comparison(text), expected)

    def test_E_balance_inclusive_all_config_direct_mean(self):
        def rows(value, multi=100):
            i = fixture('E')
            i['cells'][('direct', 'neutral')] = value
            i['cells'][('multi', 'neutral')] = multi
            return [i]
        for x, y, expected in [(0, 70, True), (30, 100, True), (0, 69.9, False), (30.1, 100, False)]:
            r = A.neutral_across_configs({'a': rows(x), 'b': rows(y)})
            self.assertEqual(r['per_item']['x']['direct']['balanced'], expected)
            self.assertEqual(r['per_config']['a']['items'][0]['direct'], x)
            self.assertIsNone(r['per_item']['x']['multi']['balanced'])
        self.assertIsNone(A.neutral_across_configs({'a': rows(50), 'b': []})['per_item']['x']['direct']['balanced'])

    def test_B_human_mean_primary_median_secondary_descriptive(self):
        rows = []
        for j in range(3):
            i = fixture('B')
            for k in (1, 2):
                i['cells'][('direct', 'F', k)] = j*10+k
            i['human'] = {k: dict(mean=j*10+k, median=100-j*10-k) for k in (1, 2)}
            rows.append(i)
        r = A.descriptive(rows, B=19)['grouped']['B_F_human_spearman']
        primary, secondary = r[str(('direct', 'mean'))], r[str(('direct', 'median'))]
        self.assertEqual(primary['role'], 'primary')
        self.assertEqual(secondary['role'], 'secondary')
        self.assertAlmostEqual(primary['rho'], 1)
        self.assertAlmostEqual(secondary['rho'], -1)
        self.assertTrue(primary['descriptive_only'] and secondary['descriptive_only'])


class EntryTests(unittest.TestCase):
    def setUp(self):
        # tempfile's private directory is inaccessible under this Windows token.
        # Use an ordinary workspace directory without changing process/global ACLs.
        self.base = Path(__file__).parent/('test_analysis_tmp_'+uuid.uuid4().hex)
        self.base.mkdir(mode=0o777)
        self.addCleanup(shutil.rmtree, self.base)
        self.fp = {'subject_meta': {'synthetic': 'yes'}}
        self.fid = CLI.R.sha(json.dumps(self.fp, sort_keys=True, ensure_ascii=False).encode())
        self.mp = self.base/'synthetic_metadata.json'
        self.rp = self.base/'synthetic_records.jsonl'
        path_patch = patch.object(CLI, 'paths', return_value=(self.rp, self.mp))
        path_patch.start()
        self.addCleanup(path_patch.stop)
        self.session = dict(session_id='s', closed_ok=True, invalid=False, fingerprint_id=self.fid, fingerprint=self.fp)
        self.save_sessions([self.session])

    def save_sessions(self, sessions):
        self.mp.write_text(json.dumps(dict(sessions=sessions)), encoding='utf-8')

    def test_freeze_refuses_changed_B_code_list_material_and_fingerprint(self):
        with patch.object(CLI, 'input_bindings', return_value={'synthetic': 'hash'}):
            CLI.freeze('dev', 'codex', self.base, B=99)
            CLI.freeze('dev', 'codex', self.base, B=99)
            for kw in [dict(B=100), dict(B=99, names=['E1'])]:
                with self.assertRaises(CLI.Mismatch):
                    CLI.freeze('dev', 'codex', self.base, **kw)
            with patch.object(CLI, 'code_binding', return_value={'changed': True}):
                with self.assertRaises(CLI.Mismatch):
                    CLI.freeze('dev', 'codex', self.base, B=99)
        with patch.object(CLI, 'input_bindings', return_value={'synthetic': 'new'}):
            with self.assertRaises(CLI.Mismatch):
                CLI.freeze('dev', 'codex', self.base, B=99)
        self.save_sessions([dict(self.session, fingerprint_id='changed')])
        with self.assertRaises(CLI.Mismatch):
            CLI.freeze('dev', 'codex', self.base, B=99)

    def test_run_refuses_B_and_code_before_reading_results(self):
        with patch.object(CLI, 'input_bindings', return_value={}):
            CLI.freeze('dev', 'codex', self.base, B=99)
            with self.assertRaisesRegex(CLI.Mismatch, 'B differs'):
                CLI.run('dev', 'codex', self.base, B=100)
            with patch.object(CLI, 'code_binding', return_value={}):
                with self.assertRaises(CLI.Mismatch):
                    CLI.run('dev', 'codex', self.base)

    def test_synthetic_freeze_run_end_to_end_and_material_rejection(self):
        unit = dict(ask='direct', cell='status_T')
        row = dict(unit_id='E:synthetic|r0', exp='E', item_id='i', cluster='c', split='dev',
                   round='r0', ask='direct', parser='synthetic', prompt_sha256='hash')
        rec = dict(row, unit=row['unit_id'], config='codex', status='ok', result=dict(ok=True, value=60),
                   session_id='s', fingerprint_id=self.fid, attempts=[])
        self.rp.write_text(json.dumps(rec)+'\n', encoding='utf-8')
        self.session['records_sha256'] = CLI.R.sha(json.dumps([rec], sort_keys=True, ensure_ascii=False).encode())
        self.save_sessions([self.session])
        (self.base/'manifest_ids.json').write_text(json.dumps([row]), encoding='utf-8')
        with patch.object(CLI, 'input_bindings', return_value={}), \
             patch.object(CLI.R, 'build_manifest', return_value=[row]), \
             patch.object(CLI.R, 'fingerprint', return_value=(self.fp, self.fid)), \
             patch.object(CLI, 'material_index', return_value={row['unit_id']: ('E', {'target': 'P'}, unit)}):
            CLI.freeze('dev', 'codex', self.base, B=19, names=['E1'])
            result = CLI.run('dev', 'codex', self.base)
            self.assertEqual(result['filter']['admitted'], 1)
            self.assertEqual(result['families']['E']['complete_subset']['E1']['n_clusters'], 0)
            with patch.object(CLI, 'input_bindings', return_value={'changed': 'hash'}):
                with self.assertRaises(CLI.Mismatch):
                    CLI.run('dev', 'codex', self.base)

    def test_A_comparison_uses_successful_attempt_full_response(self):
        raw = self.base/'synthetic_attempt.json'
        raw.write_text(json.dumps(dict(text='LOWER in reasoning. Final: higher 20')), encoding='utf-8')
        unit = dict(ask='direct', condition='irrelevant', level='high')
        row = dict(unit_id='A:synthetic', exp='A', item_id='i', cluster='c', split='dev', round='r0', ask='direct', parser='x', prompt_sha256='x')
        rec = dict(row, unit=row['unit_id'], config='codex', status='ok', result=dict(ok=True, value=20),
                   attempts=[dict(parsed=False), dict(parsed=True, raw_path=str(raw), raw_sha256=CLI.sha(raw))])
        out = CLI.build_items([row], [rec], {row['unit_id']: ('A', {}, unit)}, 'dev', 'codex')
        self.assertEqual(out[0]['results'][('direct', 'irrelevant', 'high')]['comparison'], 'lower')
        self.assertNotIn('comparison', rec['result'])

    def test_formal_freeze_before_sessions_and_reject_changes_or_mismatch(self):
        formal_mp = self.base/'formal_metadata.json'
        formal_rp = self.base/'formal_records.jsonl'
        row = dict(unit_id='E:synthetic|r0', exp='E', item_id='i', cluster='c',
                   split='dev', round='r0', ask='direct', parser='x', prompt_sha256='x')
        rec = dict(row, unit=row['unit_id'], config='codex', status='ok',
                   session_id='s', fingerprint_id=self.fid,
                   attempts=[dict(parsed=True)])
        (self.base/'manifest_ids.json').write_text(json.dumps([row]), encoding='utf-8')
        def stage_paths(base, stage, cfg):
            return (self.rp, self.mp) if stage=='dev' else (formal_rp, formal_mp)
        with patch.object(CLI, 'paths', side_effect=stage_paths), \
             patch.object(CLI, 'input_bindings', return_value={}), \
             patch.object(CLI.R, 'build_manifest', return_value=[row]), \
             patch.object(CLI.R, 'fingerprint', return_value=(self.fp, self.fid)), \
             patch.object(CLI, 'load_valid', return_value=([rec], {})) as load:
            with patch.object(CLI, 'accounting', return_value={'acceptance': False}):
                with self.assertRaisesRegex(CLI.Mismatch, 'development acceptance'):
                    CLI.freeze('formal', 'codex', self.base, names=['E1'])
            with patch.object(CLI.R, 'fingerprint', return_value=({'changed': True}, 'wrong')):
                with self.assertRaisesRegex(CLI.Mismatch, 'development fingerprint differs'):
                    CLI.freeze('formal', 'codex', self.base, names=['E1'])
            self.assertFalse(formal_mp.exists())
            frozen = CLI.freeze('formal', 'codex', self.base, names=['E1'])
            self.assertTrue(frozen['development_acceptance']['acceptance'])
            self.assertEqual(frozen['fingerprint_id'], self.fid)
            CLI.freeze('formal', 'codex', self.base, names=['E1'])
            for changes in [dict(names=['E2']), dict(names=['E1'], seed=7)]:
                with self.assertRaisesRegex(CLI.Mismatch, 'already frozen'):
                    CLI.freeze('formal', 'codex', self.base, **changes)
            for bad in [dict(self.session, fingerprint_id='wrong'),
                        dict(self.session, fingerprint={'changed': True})]:
                formal_mp.write_text(json.dumps(dict(sessions=[bad])), encoding='utf-8')
                load.reset_mock()
                with self.assertRaisesRegex(CLI.Mismatch, 'formal session fingerprint'):
                    CLI.run('formal', 'codex', self.base)
                load.assert_not_called()
            # A separate, unfrozen config cannot be frozen after any session.
            with self.assertRaisesRegex(CLI.Mismatch, 'precede every formal session'):
                CLI.freeze('formal', 'other', self.base)

    def test_formal_requires_5000(self):
        with self.assertRaises(CLI.Mismatch):
            CLI.freeze('formal', 'codex', self.base, B=99)

    def test_formal_result_fingerprint_mismatch_is_not_silently_filtered(self):
        self.rp.write_text(json.dumps(dict(unit='u', session_id='s',
                                          fingerprint_id='wrong'))+'\n', encoding='utf-8')
        with self.assertRaisesRegex(CLI.Mismatch, 'formal result fingerprint'):
            CLI.load_valid(self.rp, self.mp, self.fid, 'codex', strict=True)

    def test_closed_qwen3_development_is_readable(self):
        # The Qwen3 block expired once its development run closed (formal freeze reads it).
        for name in ['results_dev_qwen3-off.jsonl', 'run_meta_dev_qwen3-off.json', 'raw/run_dev_qwen3-off/file']:
            CLI.guard(CLI.HERE/name)

    def test_load_valid_runner_admission_and_integrity(self):
        records = [dict(unit='u', session_id='s', fingerprint_id=self.fid, status='ok'),
                   dict(unit='u', session_id='s', fingerprint_id=self.fid, status='missing')]
        self.rp.write_text(''.join(json.dumps(r)+'\n' for r in records), encoding='utf-8')
        self.session['records_sha256'] = CLI.R.sha(json.dumps(records, sort_keys=True, ensure_ascii=False).encode())
        self.save_sessions([self.session])
        kept, stats = CLI.load_valid(self.rp, self.mp, self.fid, 'codex')
        self.assertEqual(kept, [records[-1]])
        self.session['records_sha256'] = 'tampered'
        self.save_sessions([self.session])
        with self.assertRaises(CLI.Mismatch):
            CLI.load_valid(self.rp, self.mp, self.fid, 'codex')

    def test_material_adapter_all_experiments_and_J_shared_values(self):
        for exp, unit, parsed, expected in [
            ('A', dict(ask='direct', condition='none', level='none'), dict(ok=True, value=20), 1),
            ('B', dict(ask='direct', condition='HI', k=1), dict(ok=True, value=20), 1),
            ('C', dict(ask='direct', format='probability', br=1), dict(ok=True, value=20), 1),
            ('D', dict(ask='multi', pres='J'), dict(ok=True, values=dict(a=40, b=30, conj=20, disj=50)), 4),
            ('E', dict(ask='direct', cell='advisor_T'), dict(ok=True, value=20), 1)]:
            row = dict(unit_id=exp+':u', exp=exp, item_id='i', cluster='c', split='dev', round='r0', ask=unit['ask'], parser='synthetic', prompt_sha256='hash')
            rec = dict(row, unit=row['unit_id'], config='codex', status='ok', result=parsed)
            material = dict(target='P') if exp=='E' else {}
            out = CLI.build_items([row], [rec], {row['unit_id']: (exp, material, unit)}, 'dev', 'codex')
            self.assertEqual(len(out[0]['cells']), expected)
            if exp=='E':
                self.assertIn(('direct', 'recommend_T'), out[0]['cells'])
            rec['prompt_sha256'] = 'changed'
            with self.assertRaises(CLI.Mismatch):
                CLI.build_items([row], [rec], {row['unit_id']: (exp, material, unit)}, 'dev', 'codex')


if __name__ == '__main__':
    unittest.main()
