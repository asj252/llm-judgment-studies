"""Small fixtures for the freeze-free development diagnostic entry point."""
import unittest
from unittest.mock import patch

import dev_diagnostics_psych3 as D
from test_analysis_psych3 import fixture


class DiagnosticsTests(unittest.TestCase):
    def test_rates_missing_failed_attempts_weights_and_unknown_refusal(self):
        rows = [None, dict(status='failed', ask='direct', attempts=[dict(parsed=False)]),
                dict(status='ok', ask='multi', result={'weight_sum': .85}, attempts=[
                    dict(parsed=False, truncated=True, state='refusal'),
                    dict(parsed=True, truncated=False)]),
                dict(status='ok', ask='multi', result={'weight_sum': 1.}, attempts=[])]
        r = D.rates(rows)
        self.assertEqual(r['missing_rate'], .5)
        self.assertEqual(r['failed_attempt_rate'], 2/3)
        self.assertEqual(r['truncation_rate'], .5)
        self.assertEqual(r['truncation_observed'], 2)
        self.assertEqual(r['refusal_marked'], 1)
        self.assertIsNone(r['refusal_rate'])
        self.assertEqual(r['weight_compliance_rate'], .5)
        self.assertIsNone(D.rates([None])['truncation_rate'])
        self.assertIsNone(D.rates([None])['weight_compliance_rate'])

    def test_breakdown_keeps_conditions_and_unit_denominators(self):
        manifest = [dict(unit_id=str(n), exp='D', ask='multi', split=split, round='r0')
                    for n, split in enumerate(('dev', 'dev', 'formal'))]
        index = {'0': ('D', {}, dict(pres='J')), '1': ('D', {}, dict(pres='S', stmt='b'))}
        records = [dict(unit='0', status='ok', ask='multi', result={'weight_sum': 1.}, attempts=[])]
        r = D.breakdown(manifest, records, index)
        self.assertEqual(r['by_experiment']['D']['planned'], 2)
        self.assertEqual(r['by_experiment']['D']['missing'], 1)
        self.assertEqual(len(r['by_condition']), 2)
        self.assertEqual(r['by_experiment']['D']['weight_observed'], 1)

    def test_entry_point_reuses_admission_and_diagnostics_without_freeze(self):
        configs = D.P.CONFIGS
        items = [fixture(e) for e in 'ACDE']
        items[0]['cells'].update({(a, 'none', 'none'): 15 for a in D.P.A.ASKS})
        items[2]['cells'][('direct', 'S', 'conj')] = 0
        items[2]['cells'][('direct', 'S', 'b')] = 40
        items[3]['cells'][('direct', 'neutral')] = 70
        acceptance = dict(first_rate=1., missing_rate=0., acceptance=True)
        with patch.object(D.P.L.R, 'build_manifest', return_value=[]), \
                patch.object(D.P.L, 'material_index', return_value={}), \
                patch.object(D.P, 'load_development', return_value=(items, {}, [])) as load, \
                patch.object(D.P.L, 'accounting', return_value=acceptance):
            doc = D.run(configs=configs)
        self.assertEqual(load.call_count, 6)
        self.assertTrue(all(c.kwargs['include_records'] for c in load.call_args_list))
        dev = doc['configurations']['codex']['development']
        self.assertTrue(dev['A']['known_truth'])
        self.assertTrue(dev['C']['ceiling'])
        self.assertTrue(dev['D']['floor'])
        self.assertFalse(doc['neutral']['per_item']['x']['direct']['balanced'])
        text = D.render(doc)
        self.assertIn('不平衡', text)
        self.assertIn('70.000', text)
        for cfg in configs:
            self.assertIn(cfg, text)

    def test_incomplete_neutral_is_undetermined(self):
        item = fixture('E')
        missing = dict(item, cells={})
        r = D.P.A.neutral_across_configs({'one': [item], 'two': [missing]})
        self.assertIsNone(r['per_item']['x']['direct']['balanced'])


if __name__ == '__main__':
    unittest.main()
