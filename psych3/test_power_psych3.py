"""Synthetic checks for brief-e-analysis.md requirements 5 and 7."""
import copy
import random
import unittest
from unittest.mock import patch

import analysis_psych3 as A
import power_psych3 as P
from test_analysis_psych3 import fixture


def dev_e(n=30, sd=4):
    rng, rows = random.Random(81), []
    for j in range(n):
        i = fixture('E')
        i.update(item_id=str(j), cluster=str(j))
        for k in i['cells']:
            i['cells'][k] = 50+rng.gauss(0, sd)
        i['unit_groups'] = [[k] for k in i['cells']]
        rows.append(i)
    return rows


def targets(rows, effect, names=('E1',)):
    return {n: effect for n in names}


class PowerTests(unittest.TestCase):
    def test_opposite_rejection_is_not_recovered_target_direction(self):
        # Acceptance 1: exercise actual two-sided inference in both engines,
        # using a controlled draw to isolate counting from sampling noise.
        import power_from_dev as D
        names = ['E1', 'E2', 'E3', 'E4']
        samples = {n: {str(j): dict(value=-20., lower=-20., upper=-20.,
                                    n_items=1, missing_cells=0) for j in range(4)} for n in names}
        latent = dict.fromkeys(names, [-20.]*4)
        for target, expected in ((5., 0.), (-5., 1.), (0., 0.)):
            with patch.object(P, 'draw_clusters', return_value=(samples, latent)), \
                    patch.object(D, 'fast_draw', return_value=(samples, latent)):
                reference = P.simulate(dev_e(), names, dict.fromkeys(names, target), 4, nsim=1, B=99)
                fast = D.simulate(dev_e(), names, dict.fromkeys(names, target), 4, 1.5, 1, 99, 41)
            for result in (reference, fast):
                for row in result['hypotheses'].values():
                    for metric in ('direction_confirmed', 'bound_exceeds', 'complete_direction', 'complete_bound'):
                        self.assertEqual(row[metric], expected)

    def test_statistic_shift_covariance_A_AI_and_C_independent_targets(self):
        for exp, names in [('E', ['E1', 'E2']), ('A', ['A1', 'A2']), ('C', ['C3', 'C4'])]:
            rows = []
            for j in range(4):
                for acc in (('A', 'B') if exp=='C' else ('A',)):
                    i = fixture(exp)
                    i.update(cluster=str(j), item_id=str(j)+acc, acc_set=acc)
                    if exp=='A':
                        i['cells'][('direct', 'irrelevant', 'high')] *= 1+j*.1
                    else:
                        i['cells'][next(iter(i['cells']))] += j
                    rows.append(i)
            original = copy.deepcopy(rows)
            t = {n: 2.3*(j+1) for j, n in enumerate(names)}
            one, latent = P.draw_clusters(rows, names, 20, t, 1, 0, random.Random(6))
            two, _ = P.draw_clusters(rows, names, 20, t, 2, 0, random.Random(6))
            plan = P.prepare(rows, names)
            self.assertEqual(plan['mode'], 'joint')
            vectors = {tuple(round(plan['samples'][n][cl]['value']-plan['means'][n], 9) for n in names)
                       for cl in plan['pools'][names[0]]}
            for j in range(20):
                self.assertIn(tuple(round(latent[n][j]-t[n], 9) for n in names), vectors)
            for n in names:
                for cl in one[n]:
                    self.assertAlmostEqual(two[n][cl]['value']-t[n], 2*(one[n][cl]['value']-t[n]))
            shifted = dict(t, **{names[-1]: 100})
            _, other = P.draw_clusters(rows, names, 20, shifted, 1, 0, random.Random(6))
            self.assertEqual(latent[names[0]], other[names[0]])
            self.assertEqual(rows, original)

    def test_joint_four_marginal_three_and_insufficient_one(self):
        rows = dev_e(5)
        names = ['E1', 'E2']
        del rows[0]['cells'][('direct', 'default_T')]
        plan = P.prepare(rows, names)
        self.assertEqual(plan['mode'], 'joint')
        self.assertEqual(plan['pools']['E1'], ['1', '2', '3', '4'])
        del rows[1]['cells'][('direct', 'default_T')]
        plan = P.prepare(rows, names)
        self.assertEqual(plan['mode'], 'independent')
        self.assertEqual(len(plan['pools']['E1']), 5)
        self.assertEqual(len(plan['pools']['E2']), 3)
        for i in rows[2:4]:
            del i['cells'][('direct', 'default_T')]
        result = P.simulate(rows, names, dict(E1=5, E2=5), 5, nsim=2, B=19)
        self.assertEqual(result['hypotheses']['E2'], dict(status='开发资料不足'))
        self.assertEqual(result['hypotheses']['E1']['status'], 'simulated')
        self.assertIn('失去家族内相关', result['note'])
        self.assertIn('开发资料不足', P.recommendations([dict(result, effect=1)], names, 5, 40)['E2']['action'])

    def test_missing_rate_minimum_and_J_whole_unit(self):
        from unittest.mock import patch
        d = fixture('D')
        d['unit_groups'] = [[(a, 'J', s) for s in A.STATEMENTS] for a in A.ASKS]+[[(a, 'S', s)] for a in A.ASKS for s in A.STATEMENTS]
        rows = []
        for j in range(4):
            i = copy.deepcopy(d)
            i.update(cluster=str(j), item_id=str(j))
            rows.append(i)
        seen = []
        original = A.cluster_values
        def capture(items, name):
            seen.extend(copy.deepcopy(items))
            return original(items, name)
        with patch.object(A, 'cluster_values', side_effect=capture):
            P.draw_clusters(rows, ['D4'], 50, {'D4': 5}, 1, .2, random.Random(6))
        for i in seen:
            for a in A.ASKS:
                self.assertIn(sum((a, 'J', s) in i['cells'] for s in A.STATEMENTS), (0, 4))
        self.assertEqual(P.failure_rate(rows), .02)
        with self.assertRaises(ValueError):
            P.simulate(rows, ['D1'], {'D1': 5}, 10, missing=0)

    def test_requires_statistic_targets_and_sampling_parameters(self):
        rows = dev_e()
        for t, n, scale in [({}, 10, 1), ({'E1': 5}, 0, 1), ({'E1': 5}, 10, 0)]:
            with self.assertRaises(ValueError):
                P.draw_clusters(rows, ['E1'], n, t, scale, .02, random.Random(1))

    def test_C_requires_both_accuracy_items_per_story(self):
        rows = []
        for c in range(4):
            for acc in ('A', 'B'):
                i = fixture('C')
                i.update(cluster=str(c), item_id=str(c)+acc, acc_set=acc)
                rows.append(i)
        del rows[0]['cells'][('direct', 'probability', 1)]
        plan = P.prepare(rows, ['C1'])
        self.assertEqual(len(plan['pools']['C1']), 3)
        self.assertNotIn('0', plan['pools']['C1'])

    def test_null_complete_direction_rate_and_conservative_size(self):
        rows = dev_e(40, 4)
        result = P.simulate(rows, ['E1'], targets(rows, 0), 50, nsim=400, B=199, seed=31)
        r = result['hypotheses']['E1']
        # Percentile bootstrap finite-sample tolerance; protected size can be far
        # below alpha under endpoint completion even when the complete size is .05.
        self.assertGreaterEqual(r['complete_direction'], .015)
        self.assertLessEqual(r['complete_direction'], .095)
        self.assertLessEqual(r['direction_confirmed'], .08)

    def test_two_threshold_effect_complete_and_protected_power(self):
        rows = dev_e(40, .5)
        result = P.simulate(rows, ['E1'], targets(rows, 10), 500, nsim=100, B=99, seed=13)
        self.assertGreaterEqual(result['hypotheses']['E1']['direction_confirmed'], .95)
        self.assertGreaterEqual(result['hypotheses']['E1']['complete_bound'], .95)
        # Either of two required units can fail; full [-100,100] bounds make
        # the protected threshold much harder than the complete-subset one.
        self.assertLessEqual(result['hypotheses']['E1']['bound_exceeds'], .3)

    def test_full_frozen_family_not_four_separate_tests(self):
        # Real bootstrap tails give .0125 < p < .05 for E1: Holm must stop.
        names = ['E1', 'E2', 'E3', 'E4']
        samples = {n: {str(j): dict(value=v, lower=v, upper=v,
                        n_items=1, missing_cells=0)
                       for j, v in enumerate([-10]*3+[7]*12 if n=='E1' else [0]*15)}
                   for n in names}
        def draw(dev, selected, *args):
            return ({n: samples[n] for n in selected},
                    {n: [r['value'] for r in samples[n].values()] for n in selected})
        with patch.object(P, 'draw_clusters', side_effect=draw):
            single = P.simulate(dev_e(), ['E1'], {'E1': 0}, 15, nsim=1, B=999, seed=31)
            full = P.simulate(dev_e(), names, dict.fromkeys(names, 0), 15,
                              nsim=1, B=999, seed=31)
        actual = A.analyse_samples(samples, names, 999, 31)['complete_subset']['E1']
        self.assertGreater(actual['p'], .05/4)
        self.assertLess(actual['p'], .05)
        self.assertEqual(single['hypotheses']['E1']['direction_confirmed'], 1)
        self.assertEqual(full['hypotheses']['E1']['direction_confirmed'], 0)
        self.assertEqual(set(full['hypotheses']), set(names))

    def test_missing_full_legal_domains_all_statistics_unshifted(self):
        for exp in 'ABCDE':
            rows = []
            for j in range(4):
                for acc in (('A', 'B') if exp=='C' else ('A',)):
                    i = fixture(exp)
                    i.update(cluster=str(j), item_id=str(j)+acc, acc_set=acc)
                    rows.append(i)
            names = [exp+str(j) for j in range(1, 5)]
            one, _ = P.draw_clusters(rows, names, 4, dict.fromkeys(names, 10),
                                     1, 1, random.Random(7))
            two, _ = P.draw_clusters(rows, names, 4, dict.fromkeys(names, -150),
                                     2, 1, random.Random(7))
            empty = [dict(i, cells={}) for i in rows]
            for n in names:
                expected = A.cluster_values(empty, n)['0']
                for cl, r in one[n].items():
                    self.assertIsNone(r['value'])
                    self.assertEqual((r['lower'], r['upper']),
                                     (expected['lower'], expected['upper']))
                    self.assertEqual(r, two[n][cl])
            result = A.analyse_samples(one, names, 99)
            if exp=='A':
                self.assertIsNone(result['missing_protection'])
            if exp=='E':
                self.assertEqual((one['E1']['0']['lower'], one['E1']['0']['upper']), (-100, 100))
                self.assertEqual((one['E3']['0']['lower'], one['E3']['0']['upper']), (-200, 200))

    def test_review_E1_all_missing_cannot_support_shifted_positive_effect(self):
        rows = dev_e(4, 0)
        for i in rows:
            i['cells'][('direct', 'status_T')] = 0
            i['cells'][('direct', 'status_O')] = 100
        samples, latent = P.draw_clusters(rows, ['E1'], 32, {'E1': 10},
                                          1.5, 1, random.Random(7))
        self.assertEqual(latent['E1'], [10]*32)
        r = A.analyse_samples(samples, ['E1'], 199)['missing_protection']['E1']
        self.assertEqual(r['interval'], [-100, 100])
        self.assertFalse(r['directional'])

    def test_partial_simulated_missing_also_uses_full_statistic_domain(self):
        samples, _ = P.draw_clusters(dev_e(4, 0), ['E3'], 100, {'E3': 10},
                                    1.5, .2, random.Random(7))
        partial = [r for r in samples['E3'].values() if 0<r['missing_cells']<4]
        self.assertTrue(partial)
        for row in partial:
            self.assertIsNone(row['value'])
            self.assertEqual((row['lower'], row['upper']), (-200, 200))

    def test_review_E1_power_invariant_to_development_level(self):
        def constant_rows(t, o):
            rows = dev_e(4, 0)
            for i in rows:
                i['cells'][('direct', 'status_T')] = t
                i['cells'][('direct', 'status_O')] = o
            return rows
        low = P.simulate(constant_rows(0, 100), ['E1'], {'E1': 10}, 32,
                         nsim=100, B=199, seed=13, missing=.02)
        centered = P.simulate(constant_rows(55, 45), ['E1'], {'E1': 10}, 32,
                              nsim=100, B=199, seed=13, missing=.02)
        self.assertEqual(low['hypotheses'], centered['hypotheses'])
        self.assertLess(low['hypotheses']['E1']['bound_exceeds'], 1)

    def test_recommend_expansion_downgrade_and_missing_scenarios(self):
        def scenario(n, effect, probability):
            return dict(n_clusters=n, effect=effect, sd_scale=1.5,
                        hypotheses={'E1': dict(direction_confirmed=probability, bound_exceeds=probability)})
        rows = [scenario(32, e, .7) for e in (1, 2)]
        self.assertEqual(P.recommendations(rows, ['E1'], 32, 40)['E1']['action'], '建议继续模拟至材料上限')
        rows += [scenario(40, e, .9) for e in (1, 2)]
        self.assertEqual(P.recommendations(rows, ['E1'], 32, 40)['E1']['n_clusters'], 40)
        rows[-1]['hypotheses']['E1']['bound_exceeds'] = .7
        self.assertEqual(P.recommendations(rows, ['E1'], 32, 40)['E1']['action'], '建议降为描述')
        self.assertIn('无法判定', P.recommendations([], ['E1'], 32)['E1']['action'])

    def test_either_missing_target_scenario_cannot_recommend_downgrade(self):
        for effect in (1, 2):
            rows = [dict(n_clusters=40, effect=effect, sd_scale=1.5,
                         hypotheses={'E1': dict(direction_confirmed=.9, bound_exceeds=.9)})]
            self.assertIn('无法判定', P.recommendations(rows, ['E1'], 32, 40)['E1']['action'])

    def test_scenario_grid_statistic_targets(self):
        rows = dev_e(3, .1)
        ts = {str(e): targets(rows, e*5) for e in (0, 1, 2)}
        result = P.run_scenarios(rows, ['E1'], ts, [5], nsim=2, B=19)
        self.assertEqual(len(result['scenarios']), 9)
        self.assertEqual({r['sd_scale'] for r in result['scenarios']}, {1, 1.5, 2})
        self.assertTrue(all(not r.get('target_mismatch') for r in result['scenarios']))
        ts['1']['E1'] = 500
        result = P.run_scenarios(rows, ['E1'], ts, [5], nsim=1, B=19)
        self.assertTrue(all(r['target_mismatch'] for r in result['scenarios'] if r['effect']==1))
        self.assertIn('无法判定', result['recommendations']['E1']['action'])


if __name__ == '__main__':
    unittest.main()
