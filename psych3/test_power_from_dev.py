"""Synthetic aggregation, scenario and accelerated inference checks."""
import copy
import json
import random
import tempfile
import unittest
from functools import partial
from pathlib import Path
from unittest.mock import patch

import numpy as np
import analysis_psych3 as A
import power_psych3 as P
import power_from_dev as D
from test_analysis_psych3 import fixture


class ArrayRandom:
    def __init__(self, seed):
        self.rng = random.Random(seed)

    def choice(self, pool):
        return self.rng.choice(pool)

    def random(self, size):
        return np.array([self.rng.random() for _ in range(size)])


def development(exp):
    rows = []
    for j in range(5):
        for acc in ('A', 'B') if exp=='C' else ('A',):
            item = fixture(exp)
            item.update(cluster=str(j), item_id=str(j)+acc, acc_set=acc)
            item['cells'] = {k: v+j*.3 for k,v in item['cells'].items()}
            if exp=='D':
                item['unit_groups'] = [[(a,'J',s) for s in A.STATEMENTS] for a in A.ASKS]
                item['unit_groups'] += [[k] for k in item['cells'] if k[1]!='J']
            else:
                item['unit_groups'] = [[k] for k in item['cells']]
            rows.append(item)
    return rows


class DevelopmentPowerTests(unittest.TestCase):
    def test_advice_uses_complete_targets_only(self):
        def scenario(size, effect, complete, protected):
            return dict(n_clusters=size, sd_scale=1.5, effect=effect,
                        hypotheses={'E1': dict(status='simulated', complete_direction=complete,
                        complete_bound=complete, direction_confirmed=protected, bound_exceeds=protected)})
        rows = [scenario(32, 1, .8, 0), scenario(32, 2, .8, 0)]
        before = copy.deepcopy(rows)
        self.assertEqual(D.recommendations(rows, ['E1'], 32, 40)['E1'],
                         dict(action='保留', n_clusters=32))
        self.assertEqual(rows, before)
        rows[1]['hypotheses']['E1']['complete_bound'] = .799
        self.assertEqual(D.recommendations(rows, ['E1'], 32, 40)['E1']['action'],
                         '建议继续模拟至材料上限')
        rows += [scenario(33, 1, .8, 0), scenario(33, 2, .8, 0)]
        self.assertEqual(D.recommendations(rows, ['E1'], 32, 40)['E1'],
                         dict(action='建议扩样', n_clusters=33))
        # Protected success cannot rescue complete-subset failure.
        failed = [scenario(40, e, .1, 1) for e in (1, 2)]
        self.assertEqual(D.recommendations(failed, ['E1'], 32, 40)['E1']['action'], '建议降为描述')
        self.assertIn('无法判定', D.recommendations(rows[:1], ['E1'], 32, 40)['E1']['action'])
        insufficient = [dict(n_clusters=32, sd_scale=1.5, effect=e,
                            hypotheses={'E1': dict(status='开发资料不足')}) for e in (1, 2)]
        self.assertIn('开发资料不足', D.recommendations(insufficient, ['E1'], 32, 40)['E1']['action'])

    def test_summary_starts_with_advice_and_reports_both_rates(self):
        scenarios = [dict(n_clusters=32, sd_scale=1.5, effect=e, hypotheses={'E1': dict(
            status='simulated', complete_direction=.91, complete_bound=.82,
            direction_confirmed=.13, bound_exceeds=.04)}) for e in (0, 1, 2)]
        result = dict(maximum=40, missing_rate=.02, development={'note': 'synthetic'},
                      scenarios=scenarios, recommendations=D.recommendations(scenarios, ['E1'], 32, 40))
        doc = dict(nsim=1000, B=499, seed=41, configurations={'synthetic': dict(
            source=dict(admission=dict(admitted=1, total=1), accounting={'acceptance': True}),
            experiments={'E': result})})
        summary = D.render_summary(doc)
        self.assertTrue(summary.splitlines()[4].startswith('| 配置 | 假设 | 建议 |'))
        self.assertIn('A 已知真值与 C 天花板的降级见', summary.splitlines()[2])
        self.assertIn('[dev_diagnostics_psych3.md](dev_diagnostics_psych3.md)', summary.splitlines()[2])
        self.assertIn('表中「保留」不是最终冻结名单', summary.splitlines()[2])
        self.assertIn('| synthetic | E1 | 保留 | 32 | 0.910 | 0.820 | 0.130 | 0.040 |', summary)
        self.assertIn('## 健全性检查', summary)
        self.assertIn('不影响建议', summary)

    def synthetic_run(self, residual_sd, size):
        # Acceptance 2: replace disk reads only. Keep admission, build_items,
        # prepare, masks, fast_draw, bootstrap, Holm and rate counting real.
        rng = random.Random(140)
        items = []
        for exp in 'ABCDE':
            for j in range(12):
                for acc in ('A', 'B') if exp == 'C' else ('A',):
                    row = fixture(exp)
                    row.update(cluster=str(j), item_id=f'{exp}{j}{acc}', acc_set=acc)
                    for key, value in row['cells'].items():
                        noise = rng.gauss(0, residual_sd)
                        row['cells'][key] = value*np.exp(noise*.05) if exp == 'A' else value+noise
                    if exp == 'D':
                        row['unit_groups'] = [[(a, 'J', s) for s in A.STATEMENTS] for a in A.ASKS]
                        row['unit_groups'] += [[k] for k in row['cells'] if k[1] != 'J']
                    items.append(row)
        manifest, index, records = [], {}, []
        fingerprint = {'synthetic': True}
        fid = D.L.R.sha(json.dumps(fingerprint, sort_keys=True, ensure_ascii=False).encode())
        for item in items:
            exp = item['exp']
            for j, group in enumerate(P.groups(item)):
                key = group[0]
                unit = dict(ask=key[0])
                fields = dict(A=('condition', 'level'), B=('condition', 'k'),
                              C=('format', 'br'), D=('pres', 'stmt'), E=('cell',))[exp]
                unit.update(zip(fields, key[1:]))
                uid = f"{exp}:{item['item_id']}:{j}"
                row = dict(unit_id=uid, exp=exp, item_id=item['item_id'], cluster=item['cluster'],
                           split='dev', round='r0', ask=key[0], parser='synthetic', prompt_sha256='synthetic')
                manifest.append(row)
                material = dict(item, target='P')
                index[uid] = exp, material, unit
                parsed = (dict(ok=True, values={k[2]: item['cells'][k] for k in group})
                          if exp == 'D' and key[1] == 'J' else dict(ok=True, value=item['cells'][key]))
                records.append(dict(row, unit=uid, config='synthetic', status='ok', result=parsed,
                                    session_id='s', fingerprint_id=fid, attempts=[]))
        digest = D.L.R.sha(json.dumps(records, sort_keys=True, ensure_ascii=False).encode())
        metadata = dict(sessions=[dict(session_id='s', closed_ok=True, fingerprint=fingerprint,
                                       fingerprint_id=fid, records_sha256=digest)])
        sizes = dict.fromkeys('ABCDE', size)
        with patch.object(D.L.R, 'build_manifest', return_value=manifest), \
                patch.object(D.L, 'material_index', return_value=index), \
                patch.object(D.L.R, 'load_records', return_value=records), \
                patch.object(D.L, 'read', return_value=metadata), \
                patch.object(D.L, 'sha', return_value='synthetic'), \
                patch.object(D.L.R, 'config_name', side_effect=lambda cfg: cfg), \
                patch.object(D, 'sample_limits', return_value=sizes), \
                patch.object(D, 'START', sizes), patch('builtins.print'):
            return D.run(base=Path('synthetic-only'), nsim=200, B=199, seed=41, configs=['synthetic'])

    def test_end_to_end_zero_residual_effect_recovers_direction(self):
        doc = self.synthetic_run(0, 2)
        for exp, result in doc['configurations']['synthetic']['experiments'].items():
            rows = {r['effect']: r for r in result['scenarios'] if r['sd_scale'] == 1.5}
            for name in result['recommendations']:
                with self.subTest(name=name):
                    ps = [rows[k]['hypotheses'][name]['direction_confirmed'] for k in (0, 1, 2)]
                    self.assertLessEqual(ps[0], A.ALPHA)
                    self.assertGreaterEqual(ps[1], .5)
                    # At n=2 even the complete subset can be empty. Keep the
                    # 2% unit failures and unshifted missing bounds in force.
                    self.assertGreaterEqual(rows[2]['hypotheses'][name]['complete_direction'], .95)
                    self.assertGreaterEqual(ps[2], ps[1])
                    if exp == 'A':
                        self.assertGreaterEqual(ps[2], .99)
        with patch.object(D, 'START', dict.fromkeys('ABCDE', 2)):
            summary = D.sanity_summary(doc)
        self.assertEqual(len([s for s in summary if s.startswith('| synthetic')]), 20)
        self.assertNotIn('未通过', '\n'.join(summary))

    def test_end_to_end_moderate_residual_rates_increase(self):
        doc = self.synthetic_run(2, 32)
        for result in doc['configurations']['synthetic']['experiments'].values():
            for scale in (1., 1.5, 2.):
                rows = {r['effect']: r for r in result['scenarios'] if r['sd_scale'] == scale}
                for name in result['recommendations']:
                    for metric in ('direction_confirmed', 'bound_exceeds',
                                   'complete_direction', 'complete_bound'):
                        ps = [rows[k]['hypotheses'][name][metric] for k in (0, 1, 2)]
                        with self.subTest(name=name, scale=scale, metric=metric):
                            self.assertTrue(all(b >= a-.04 for a,b in zip(ps, ps[1:])), ps)
                    effects = [rows[k]['hypotheses'][name]['realized_effect'] for k in (0, 1, 2)]
                    self.assertAlmostEqual(effects[1]-effects[0], A.SPECS[name]['threshold'])
                    self.assertAlmostEqual(effects[2]-effects[1], A.SPECS[name]['threshold'])

    def test_export_is_formal_formula_and_C_two_accuracy_cluster(self):
        rows = development('C')
        rows[1]['cells'][('direct','probability',1)] += 4
        names = ['C1','C2','C3','C4']
        result = D.contribution_export(rows, names)
        self.assertEqual(result['mode'], 'joint')
        self.assertEqual(result['contributions']['C1'], A.cluster_values(rows,'C1'))
        self.assertAlmostEqual(result['contributions']['C1']['0']['value'],
                               A.mean(A.contribution(i,'C1')['value'] for i in rows[:2]))
        rows[0]['cells'].clear()
        result = D.contribution_export(rows,names)
        self.assertIsNone(result['contributions']['C1']['0']['value'])

    def test_targets_sizes_and_failure_floor(self):
        for exp in 'ABCDE':
            targets = D.targets_for(exp)
            for k in (0,1,2):
                self.assertEqual(targets[str(k)], {n:k*A.SPECS[n]['threshold'] for n in A.SPECS if n[0]==exp})
            self.assertEqual(D.START[exp], dict(A=50,B=90,C=20,D=20,E=32)[exp])
        self.assertEqual(D.targets_for('C')['ceiling'], dict(C1=0,C2=0,C3=0,C4=0))
        manifest = [dict(exp=e, cluster=str(j), split='formal',round='r0') for e,n in [('B',90),('C',20)] for j in range(n)]
        self.assertEqual(D.sample_limits(manifest), dict(A=50,B=90,C=20,D=40,E=40))
        rows = development('D')
        self.assertEqual(P.failure_rate(rows), .02)
        for key in rows[0]['unit_groups'][0]:
            rows[0]['cells'].pop(key)
        self.assertAlmostEqual(P.failure_rate(rows), 1/50)

    def test_fast_draw_matches_reference_joint_and_independent(self):
        for exp in 'ABCDE':
            for independent in (False,True):
                rows = development(exp)
                if independent:
                    for item in rows:
                        if item['cluster'] in ('0','1'):
                            item['cells'].pop(next(iter(item['cells'])))
                before = copy.deepcopy(rows)
                names = [n for n in A.SPECS if n[0]==exp]
                plan = P.prepare(rows,names)
                design = D.mask_design(rows,names,plan)
                targets = D.targets_for(exp)['2']
                reference, latent = P.draw_clusters(rows,names,30,targets,1.5,.12,random.Random(21),plan)
                fast, fast_latent = D.fast_draw(plan,design,names,30,targets,1.5,.12,ArrayRandom(21))
                self.assertEqual(latent,fast_latent)
                for n in names:
                    for cl in reference.get(n,{}):
                        for k in ('value','lower','upper','n_items'):
                            self.assertEqual(reference[n][cl][k],fast[n][cl][k], (exp,n,k))
                with patch.object(A,'bootstrap',D.numpy_bootstrap):
                    full = {n:reference.get(n,{}) for n in names}
                    ref_result = A.analyse_samples(full,names,99,5)
                    fast_result = A.analyse_samples(fast,names,99,5)
                for n in names:
                    for k in ('directional','strength','interval','p'):
                        self.assertEqual(ref_result['complete_subset'][n]['final'][k],fast_result['complete_subset'][n]['final'][k])
                self.assertEqual(rows,before)

    def test_numpy_bootstrap_and_missing_insufficient(self):
        self.assertEqual(D.numpy_bootstrap([],9),[])
        self.assertEqual(D.numpy_bootstrap([7,7],9),[7.]*9)
        rows=development('E')[:1]
        result=D.simulate(rows,['E1','E2','E3','E4'],D.targets_for('E')['1'],8,1.5,2,19,5)
        self.assertTrue(all(v['status']=='开发资料不足' for v in result['hypotheses'].values()))

    def test_scenario_orchestration_keeps_frozen_families_and_ceiling(self):
        manifest = [dict(exp=e, cluster=str(j), split='formal',round='r0')
                    for e,n in [('B',90),('C',20)] for j in range(n)]
        items = [i for e in 'ABCDE' for i in development(e)]
        def simulated(rows,names,targets,size,scale,nsim,B,seed,prepared):
            self.assertEqual(len(names),4)
            if names[0][0]=='D':
                self.assertTrue(all(i['type']=='P' for i in rows))
            return dict(nsim=nsim,B=B,seed=seed,n_clusters=size,sd_scale=scale,targets=targets,
                        hypotheses={n:dict(status='simulated',direction_confirmed=0.,bound_exceeds=0.,
                                           complete_direction=1.,complete_bound=1.) for n in names})
        with patch.object(D.L.R,'build_manifest',return_value=manifest), patch.object(D.L,'material_index',return_value={}), \
                patch.object(D,'load_development',return_value=(items,{})), patch.object(D,'simulate',side_effect=simulated), \
                patch('builtins.print'):
            result=D.run(nsim=3,B=19,configs=['synthetic'])
        for exp,doc in result['configurations']['synthetic']['experiments'].items():
            self.assertEqual(len(doc['scenarios']),12 if exp=='C' else 9)
            self.assertTrue(all(v['action']=='保留' for v in doc['recommendations'].values()))
            self.assertEqual({r['sd_scale'] for r in doc['scenarios']},{1.,1.5,2.})
            if exp=='C':
                for scale in (1.,1.5,2.):
                    zero=next(r for r in doc['scenarios'] if r['effect']==0 and r['sd_scale']==scale)
                    ceiling=next(r for r in doc['scenarios'] if r['effect']=='ceiling' and r['sd_scale']==scale)
                    self.assertEqual(zero['hypotheses'],ceiling['hypotheses'])

    def test_load_reuses_admission_without_freeze_or_general_guard_disable(self):
        with patch.object(D.L,'read') as read, patch.object(D.L,'sha',return_value='synthetic'):
            base=Path('synthetic-development')
            rp=base/'results_dev_qwen3-off.jsonl'
            mp=base/'run_meta_dev_qwen3-off.json'
            fingerprint={'config':'qwen3-off'}
            import json
            fid=D.L.R.sha(json.dumps(fingerprint,sort_keys=True,ensure_ascii=False).encode())
            read.return_value=dict(sessions=[dict(closed_ok=True, fingerprint_id=fid, fingerprint=fingerprint)])
            original=D.L.guard
            with patch.object(D.L,'load_valid',return_value=([],{'admitted':0,'total':0})) as valid, patch.object(D.L,'build_items',return_value=[]):
                rows,source=D.load_development(base,'qwen3-off',[],{})
            valid.assert_called_once_with(rp,mp,fid,'qwen3-off')
            self.assertIs(D.L.guard,original)
            self.assertEqual(rows,[])
            self.assertEqual(set(source['inputs']),{rp.name,mp.name})

    def test_config_selection_and_output_prefix(self):
        import argparse
        self.assertEqual(D.parse_configs('codex, agy:gemini-3.8-flash-low'),
                         ('codex', 'agy:gemini-3.8-flash-low'))
        for value in ('', 'codex,codex', 'agy_gemini-3.8-flash-low', 'unknown'):
            with self.assertRaises(argparse.ArgumentTypeError):
                D.parse_configs(value)
        self.assertEqual(D.output_paths('power_dev', Path('fixture')),
                         [Path('fixture/power_dev_results.json'), Path('fixture/power_dev_summary.md')])
        self.assertEqual(D.CONFIGS[:2], ('qwen3-off', 'codex'))
        self.assertEqual(len(D.CONFIGS), 6)

    def test_agy_uses_normalized_paths_checkpoint_and_original_identity(self):
        import agy_night
        cfg = 'agy:gpt-oss-120b-medium'
        base = Path('synthetic-development')
        fp = {'config': cfg}
        fid = D.L.R.sha(json.dumps(fp, sort_keys=True, ensure_ascii=False).encode())
        meta = dict(sessions=[dict(closed_ok=True, fingerprint_id=fid, fingerprint=fp)])
        with patch.object(D.L, 'read', return_value={'sessions': []}), \
                patch.object(agy_night, 'checkpoint_meta', return_value=meta) as checkpoint, \
                patch.object(D.L, 'sha', return_value='synthetic'), \
                patch.object(D.L, 'load_valid', return_value=([], {})) as valid, \
                patch.object(D.L, 'build_items', return_value=[]) as build:
            D.load_development(base, cfg, [], {}, include_records=True)
        mp = base/'run_meta_dev_agy_gpt-oss-120b-medium.json'
        checkpoint.assert_called_once_with(mp)
        valid.assert_called_once_with(base/'results_dev_agy_gpt-oss-120b-medium.jsonl', mp, fid, cfg)
        self.assertEqual(build.call_args.args[-1], cfg)

    def assert_agy_tail_fails_without_outputs(self, tail, exception, message):
        cfg = 'agy:gpt-oss-120b-medium'
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            name = D.L.R.config_name(cfg)
            rp = base/f'results_dev_{name}.jsonl'
            mp = base/f'run_meta_dev_{name}.json'
            fp = {'config': cfg}
            fid = D.L.R.sha(json.dumps(fp, sort_keys=True, ensure_ascii=False).encode())
            row = dict(unit_id='E:fixture|r0', exp='E', item_id='fixture', cluster='fixture',
                       split='dev', round='r0', ask='direct', parser='fixture', prompt_sha256='fixture')
            manifest = [row]
            index = {row['unit_id']: ('E', {'target': 'P'}, dict(ask='direct', cell='neutral'))}
            record = dict(row, unit=row['unit_id'], config=cfg, session_id='closed',
                          fingerprint_id=fid, status='ok', result=dict(ok=True, value=50), attempts=[])
            # One complete registered unit precedes an interrupted writer's tail.
            clean = json.dumps(record)+'\n'
            meta = dict(sessions=[dict(session_id='closed', closed_ok=True,
                fingerprint=fp, fingerprint_id=fid,
                unit=row['unit_id'], record_sha256=D.L.R.agy_helpers().record_hash(record),
                records_sha256=D.L.R.sha(json.dumps([record], sort_keys=True, ensure_ascii=False).encode()))])
            mp.write_text(json.dumps(meta), encoding='utf-8')
            rp.write_text(clean, encoding='utf-8')
            _, source, records = D.load_development(base, cfg, manifest, index, include_records=True)
            self.assertEqual(records, [record])
            self.assertEqual(source['admission'], dict(total=1, admitted=1, excluded=0))
            rp.write_text(clean+tail, encoding='utf-8')
            prefix = base/'power_tail'
            outputs = D.output_paths(prefix)
            # Keep the CLI, run, checkpoint and load_valid real; only supply the
            # tiny material fixture instead of reading the production banks.
            with patch.object(D, 'run', new=partial(D.run, base=base)), \
                    patch.object(D.L.R, 'build_manifest', return_value=manifest), \
                    patch.object(D.L, 'material_index', return_value=index), \
                    patch.object(D, 'sample_limits', return_value=D.START), \
                    patch('sys.argv', ['power_from_dev.py', '--configs', cfg,
                          '--nsim', '1', '--B', '9', '--output-prefix', str(prefix)]):
                with self.assertRaisesRegex(exception, message) as raised:
                    D.main()
            self.assertIs(type(raised.exception), exception)
            self.assertTrue(all(not path.exists() for path in outputs), outputs)

    def test_agy_unregistered_session_tail_raises_mismatch_without_outputs(self):
        self.assert_agy_tail_fails_without_outputs(
            json.dumps(dict(session_id='unregistered', unit='orphan'))+'\n',
            D.L.Mismatch, 'unregistered result')

    def test_agy_incomplete_json_tail_raises_decode_error_without_outputs(self):
        self.assert_agy_tail_fails_without_outputs(
            '{"session_id": "interrupted", "unit":', json.JSONDecodeError,
            'Expecting value')

    def test_config_order_and_subset_preserve_all_simulation_numbers(self):
        items = [i for exp in 'ABCDE' for i in development(exp)]
        def simulate(rows, names, targets, size, scale, nsim, B, seed, prepared):
            return dict(n_clusters=size, sd_scale=scale, seed=seed,
                        hypotheses={n: dict(status='simulated', complete_direction=1.,
                            complete_bound=1., direction_confirmed=.5, bound_exceeds=.4) for n in names})
        with patch.object(D.L.R, 'build_manifest', return_value=[]), \
                patch.object(D.L, 'material_index', return_value={}), \
                patch.object(D, 'sample_limits', return_value=D.START), \
                patch.object(D, 'load_development', return_value=(items, {})), \
                patch.object(D, 'simulate', side_effect=simulate) as simulation, \
                patch.object(D.time, 'perf_counter', return_value=0), patch('builtins.print'):
            forward = D.run(configs=D.CONFIGS)
            reverse = D.run(configs=D.CONFIGS[::-1])
            subset = D.run(configs=['codex'])
        self.assertEqual(forward['configurations'], reverse['configurations'])
        self.assertEqual(forward['configurations']['codex'], subset['configurations']['codex'])
        self.assertTrue(all(c.args[7] == A.SEED for c in simulation.call_args_list))

    def test_legacy_expansion_grid_is_retained_after_early_success(self):
        def simulated(rows, names, targets, size, scale, nsim, B, seed, prepared):
            return dict(n_clusters=size, sd_scale=scale, hypotheses={n: dict(
                status='simulated', complete_direction=1., complete_bound=1.) for n in names})
        with patch.object(D.L.R, 'build_manifest', return_value=[]), \
                patch.object(D.L, 'material_index', return_value={}), \
                patch.object(D, 'sample_limits', return_value={'E': 34}), \
                patch.object(D, 'START', {'E': 32}), patch.object(D, 'LEGACY_GRID', {'E': 34}), \
                patch.object(D, 'load_development', return_value=(development('E'), {})), \
                patch.object(D, 'simulate', side_effect=simulated), patch('builtins.print'):
            doc = D.run(configs=['codex', D.CONFIGS[2]])
        legacy = doc['configurations']['codex']['experiments']['E']
        agy = doc['configurations'][D.CONFIGS[2]]['experiments']['E']
        self.assertEqual(len(legacy['scenarios']), 27)
        self.assertEqual(len(agy['scenarios']), 9)
        self.assertEqual(legacy['recommendations'], agy['recommendations'])


if __name__=='__main__':
    unittest.main()
