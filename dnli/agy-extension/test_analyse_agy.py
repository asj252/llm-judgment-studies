import hashlib
import importlib.util
import json
import shutil
from pathlib import Path
from workspace_temp import temporary_directory
import unittest
from unittest.mock import patch
import analysis as A
import analyse
import run_agy as R
from test_run_agy import Subject, CFG

class AnalysisAdapterTests(unittest.TestCase):
    def test_budget_separates_rate_wait_and_retries(self):
        record = dict(config=CFG, pres='prior', utype='-', ask='direct', round='r0',
                      status='ok', n_attempts=2, rate_wait_seconds=300,
                      attempts=[{'state': 'rate_limited'}, {'state': 'ok'}])
        row = next(iter(analyse.budget_report([record]).values()))
        self.assertEqual(row['retry_rate'], 0)
        self.assertEqual(row['retry_count'], 0)
        self.assertEqual(row['rate_limited_attempts'], 1)
        self.assertEqual(row['rate_wait_seconds'], 300)

    def test_all_prompt_hashes_match_main(self):
        spec = importlib.util.spec_from_file_location('main_prompts', R.MAIN / 'prompts.py')
        main = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(main)
        items, split = R.load_all_items()
        for item in items.values():
            for unit in R.units_for(item, item['use'], split):
                actual = R.render_unit(item, unit)
                expected = main.render_item(item, unit[1], unit[2], unit[3])
                self.assertEqual(hashlib.sha256(actual.encode()).hexdigest(), hashlib.sha256(expected.encode()).hexdigest())

    def test_analysis_checkpoint_filter_and_freeze_binding(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            root = Path(tmp)
            items, split = R.load_all_items()
            item = next(it for it in items.values() if it['use'] == 'dev')
            unit = R.base_units(item['key'])[0]
            fp, fp_id = R.fingerprint(R.HERE, CFG, items, split)
            rp = root / ('results_dev_'+R.file_config(CFG)+'.jsonl')
            mp = root / ('run_meta_dev_'+R.file_config(CFG)+'.json')
            with patch.object(R, 'make_schedule', return_value=[unit]):
                self.assertEqual(R.execute('dev', CFG, items, split, Subject(), fp, fp_id, rp, mp, log=lambda _: None), 0)
            valid, drop = analyse.load_valid(rp, mp, fp_id)
            self.assertEqual(len(valid), 1)
            self.assertEqual(drop['excluded'], 0)
            analyse.check_bindings(R.HERE, {CFG: fp}, {CFG: valid})
            self.assertEqual(analyse.freeze('dev', CFG, root, root/'freeze.json', B=30), fp_id)
            bad = dict(fp, **{'parse.py': 'changed'})
            with self.assertRaises(analyse.MaterialMismatch):
                analyse.check_bindings(R.HERE, {CFG: bad}, {CFG: valid})

    def test_effort_descriptive_outside_holm(self):
        configs = R.CONFIGS[:3]
        cells = {(cfg, 'k', p, t, a): (50 if p == 'prior' else (60+i*5 if t == 'S' else 40-i*5))
                 for i, cfg in enumerate(configs) for p in ('prior', 'stated', 'reported')
                 for t in (('-',) if p == 'prior' else ('S', 'W')) for a in ('direct', 'multi')}
        rows = A.effort_differences(cells, {c: ['k'] for c in configs}, {'k': {'cluster': 'c'}}, configs, B=20)
        self.assertEqual(len(rows), 12)
        self.assertTrue(all(not r['in_holm'] for r in rows))
        self.assertEqual(len(A.families_for(configs)), 3)
        self.assertTrue(all(len(v) == 4 for v in A.families_for(configs).values()))

    def test_complete_analysis_entry_diagnostic_and_final_guard(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            root = Path(tmp)
            base = root / 'dnli-agy'
            base.mkdir()
            main = root / 'dnli'
            (main / 'raw').mkdir(parents=True)
            for name in ('split.json', 'raw/items_text.json'):
                shutil.copyfile(R.MAIN / name, main / name)
            for p in R.HERE.glob('*.py'):
                shutil.copyfile(p, base / p.name)
            shutil.copyfile(R.HERE / 'brief-e-agy.md', base / 'brief-e-agy.md')
            (base / 'agent').mkdir()
            shutil.copyfile(R.HERE / 'agent/dnli-subject.md', base / 'agent/dnli-subject.md')
            items, split = R.load_all_items(base)
            fp, fp_id = R.fingerprint(base, CFG, items, split)
            unit = next(R.base_units(k)[0] for k, it in items.items() if it['use'] == 'dev')
            rp = base / ('results_dev_'+R.file_config(CFG)+'.jsonl')
            mp = base / ('run_meta_dev_'+R.file_config(CFG)+'.json')
            with patch.object(R, 'make_schedule', return_value=[unit]):
                R.execute('dev', CFG, items, split, Subject(), fp, fp_id, rp, mp, log=lambda _: None)
            freeze = base / 'freeze.json'
            analyse.freeze('dev', CFG, base, freeze, B=20)
            result = analyse.analyse('dev', base=base, freeze_path=freeze)
            self.assertEqual(result['mode']['mode'], '诊断')
            self.assertEqual(result['accounting']['configs'][CFG]['valid_records'], 1)
            with self.assertRaises(analyse.Incomplete):
                analyse.analyse('dev', base=base, freeze_path=freeze, final=True)

    def test_freeze_rejects_unplanned_config(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            root = Path(tmp)
            with self.assertRaises(SystemExit) as cm:
                analyse.freeze('dev', 'agy:claude-opus-5-5-low', root, root / 'freeze.json', B=20)
            self.assertIn('not in planned configs', str(cm.exception))

    def test_planned_configs_accounting_and_ignored_frozen(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            root = Path(tmp)
            base = root / 'dnli-agy'
            base.mkdir()
            main = root / 'dnli'
            (main / 'raw').mkdir(parents=True)
            for name in ('split.json', 'raw/items_text.json'):
                shutil.copyfile(R.MAIN / name, main / name)
            for p in R.HERE.glob('*.py'):
                shutil.copyfile(p, base / p.name)
            shutil.copyfile(R.HERE / 'brief-e-agy.md', base / 'brief-e-agy.md')
            (base / 'agent').mkdir()
            shutil.copyfile(R.HERE / 'agent/dnli-subject.md', base / 'agent/dnli-subject.md')
            items, split = R.load_all_items(base)
            unit = next(R.base_units(k)[0] for k, it in items.items() if it['use'] == 'dev')
            freeze = base / 'freeze.json'
            with patch.object(R, 'make_schedule', return_value=[unit]):
                for cfg in analyse.PLANNED_CONFIGS[:3]:
                    fp, fp_id = R.fingerprint(base, cfg, items, split)
                    rp = base / ('results_dev_' + R.file_config(cfg) + '.jsonl')
                    mp = base / ('run_meta_dev_' + R.file_config(cfg) + '.json')
                    self.assertEqual(R.execute('dev', cfg, items, split, Subject(), fp, fp_id, rp, mp, log=lambda _: None), 0)
                    analyse.freeze('dev', cfg, base, freeze, B=20)
                res_three = analyse.analyse('dev', base=base, freeze_path=freeze)
                self.assertEqual(set(res_three['accounting']['configs'].keys()), set(analyse.PLANNED_CONFIGS))
                self.assertEqual(res_three['status'], '部分分析（诊断；不作正式报告）')
                self.assertEqual(res_three['accounting']['missing_configs'], [analyse.PLANNED_CONFIGS[3]])
                self.assertEqual(res_three['ignored_frozen_configs'], [])
                with self.assertRaises(analyse.Incomplete):
                    analyse.analyse('dev', base=base, freeze_path=freeze, final=True)

                cfg4 = analyse.PLANNED_CONFIGS[3]
                fp4, fp_id4 = R.fingerprint(base, cfg4, items, split)
                rp4 = base / ('results_dev_' + R.file_config(cfg4) + '.jsonl')
                mp4 = base / ('run_meta_dev_' + R.file_config(cfg4) + '.json')
                self.assertEqual(R.execute('dev', cfg4, items, split, Subject(), fp4, fp_id4, rp4, mp4, log=lambda _: None), 0)
                analyse.freeze('dev', cfg4, base, freeze, B=20)
                res_four = analyse.analyse('dev', base=base, freeze_path=freeze, final=True)
                self.assertEqual(res_four['status'], '完整核账')
                self.assertEqual(res_four['mode']['mode'], '正式')
                self.assertEqual(res_four['accounting']['missing_configs'], [])
                self.assertEqual(set(res_four['accounting']['configs'].keys()), set(analyse.PLANNED_CONFIGS))

                fz_data = json.loads(freeze.read_text(encoding='utf-8'))
                unplanned = 'agy:claude-opus-5-5-low'
                fz_data['dev'][unplanned] = 'fake_fp_id'
                freeze.write_text(json.dumps(fz_data, indent=1) + '\n', encoding='utf-8', newline='\n')
                res_ign = analyse.analyse('dev', base=base, freeze_path=freeze, final=True)
                self.assertEqual(res_ign['ignored_frozen_configs'], [unplanned])
                self.assertEqual(set(res_ign['accounting']['configs'].keys()), set(analyse.PLANNED_CONFIGS))
                self.assertNotIn('config:' + unplanned, res_ign['families'])
                self.assertNotIn('config:' + unplanned, res_ign['families_frozen'])
                self.assertNotIn(unplanned, res_ign['descriptives'])

if __name__ == '__main__':
    unittest.main()
