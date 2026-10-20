import datetime as dt
import json
from pathlib import Path
from workspace_temp import temporary_directory
import unittest
import concurrent.futures
import subprocess
import sys
from unittest.mock import patch
import run_agy as R

CFG = R.CONFIGS[0]
ITEM = {'key': 'k', 'P': 'P', 'H': 'H', 'U_S': 'S', 'U_W': 'W', 'S_id': 's', 'W_id': 'w', 'use': 'dev', 'cluster': 'c'}
UNIT = ('k', 'prior', '-', 'direct', 'r0')

class Clock:
    def __init__(self):
        self.t = dt.datetime(2026, 10, 13, 23, 59, tzinfo=dt.timezone.utc)
    def now(self):
        return self.t
    def sleep(self, seconds):
        self.t += dt.timedelta(seconds=seconds)

class Subject:
    def __init__(self, states=('ok',), models=('m',)):
        self.states, self.models, self.calls = states, models, 0
    def snapshot(self, reported_model=None):
        return {'agy_version': 'stub', 'permissions_sha256': 'h', 'settings_keys': ['permissions'], 'reported_model': reported_model}
    def attempt(self, *args):
        i = self.calls
        self.calls += 1
        state = self.states[min(i, len(self.states)-1)]
        snap = self.snapshot(self.models[min(i, len(self.models)-1)])
        return {'text': 'Probability: 50%', 'truncated': False,
                'meta': {'snapshot': snap},
                'final': {'state': state, 'stop': state == 'check_failed', 'resample': state in ('contaminated', 'disconnect')}}

class RunnerTests(unittest.TestCase):
    def policy(self, maximum=100):
        clock = Clock()
        return R.RetryPolicy(1, 4, maximum, clock.sleep, clock.now)
    def test_rate_does_not_spend_retry(self):
        sub = Subject(('rate_limited',)*8 + ('ok',))
        p = self.policy()
        r = R.run_unit(CFG, 'dev', ITEM, UNIT, sub, p, lambda: None, lambda *a: None)
        self.assertEqual(r['status'], 'ok')
        self.assertEqual(sub.calls, 9)
        self.assertEqual(sum(v['rate_count'] for v in p.state['daily'].values()), 8)
        self.assertEqual(r['n_retries'], 0)
        self.assertEqual(p.state['retry_count'], 0)

    def test_unit_rate_limit_survives_daily_sleep_and_restart(self):
        p = self.policy(1)
        p.max_unit = 600
        p.limited(lambda: None)
        p.limited(lambda: None)
        restored = self.policy(1)
        restored.max_unit = 600
        restored.state = json.loads(json.dumps(p.state))
        restored.now = p.now
        with self.assertRaisesRegex(R.Stop, 'duration exceeded'):
            restored.limited(lambda: None)

    def test_retry_budget_excludes_rate_waits(self):
        p = self.policy()
        r = R.run_unit(CFG, 'dev', ITEM, UNIT, Subject(('rate_limited', 'contaminated', 'ok')),
                       p, lambda: None, lambda *a: None)
        self.assertEqual(r['n_retries'], 1)
        self.assertEqual(p.state['retry_count'], 1)

    def test_unit_rate_duration_stop_persists_before_another_call(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            root = Path(tmp)
            p = self.policy()
            p.max_unit = 2
            sub = Subject(('rate_limited',))
            with patch.object(R, 'make_schedule', return_value=[UNIT]):
                result = R.execute('dev', CFG, {'k': ITEM}, {}, sub, {}, 'fp',
                                   root/(R.file_config(CFG)+'.jsonl'), root/(R.file_config(CFG)+'.json'),
                                   p, log=lambda _: None)
            self.assertEqual(result, 3)
            self.assertEqual(sub.calls, 2)
            self.assertEqual(self.execute(root, sub), 3)
            self.assertEqual(sub.calls, 2)
    def test_sleep_until_tomorrow_and_resume(self):
        p = self.policy(1)
        p.limited(lambda: None)
        p.limited(lambda: None)
        self.assertEqual(p.now().strftime('%Y-%m-%d %H:%M'), '2026-10-14 00:10')
        wake = (p.now() + dt.timedelta(seconds=5)).isoformat()
        p.state['wake_at'] = wake
        p.resume_wait(lambda: None)
        self.assertEqual(p.now().isoformat(), wake)
    def test_three_consecutive_polluted_or_disconnected(self):
        for state in ('contaminated', 'disconnect'):
            sub = Subject((state,))
            with self.assertRaises(R.Stop):
                R.run_unit(CFG, 'dev', ITEM, UNIT, sub, self.policy(), lambda: None, lambda *a: None)
            self.assertEqual(sub.calls, 3)
    def execute(self, root, sub, units=(UNIT,), cfg=CFG):
        with patch.object(R, 'make_schedule', return_value=list(units)):
            return R.execute('dev', cfg, {'k': ITEM}, {'repeat_subset': []}, sub, {}, 'fp',
                             root / (R.file_config(cfg)+'.jsonl'), root / (R.file_config(cfg)+'.json'), self.policy(), log=lambda _: None)
    def test_resume_orphan_and_independent_models(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            root = Path(tmp)
            sub = Subject()
            self.assertEqual(self.execute(root, sub), 0)
            self.assertEqual(sub.calls, 1)
            self.assertEqual(self.execute(root, sub), 0)
            self.assertEqual(sub.calls, 1)
            self.assertEqual(self.execute(root, Subject(), cfg=R.CONFIGS[1]), 0)
            rp = root / (R.file_config(CFG)+'.jsonl')
            rec = R.load_records(rp)[0]
            rec['session_id'] = 'orphan'
            with rp.open('a', encoding='utf-8') as f:
                f.write(json.dumps(rec)+'\n')
            self.assertEqual(self.execute(root, sub), 0)
            self.assertEqual(sub.calls, 1)
    def test_model_change_stops_preserves_previous(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            root = Path(tmp)
            sub = Subject(models=('m', 'changed'))
            other = ('k', 'prior', '-', 'multi', 'r0')
            self.assertEqual(self.execute(root, sub, (UNIT, other)), 3)
            meta = R.load_json(root / (R.file_config(CFG)+'.json'), {})
            self.assertEqual(len(meta['sessions']), 1)
            self.assertIn('environment_changed', meta['stopped']['reason'])

    def test_pre_unit_settings_or_version_change_stops(self):
        for field in ('permissions_sha256', 'settings_keys', 'agy_version'):
            with temporary_directory(dir=Path.cwd()) as tmp:
                root = Path(tmp)
                other = ('k', 'prior', '-', 'multi', 'r0')
                sub = Subject()
                self.assertEqual(self.execute(root, sub), 0)
                original = sub.snapshot
                with patch.object(sub, 'snapshot', side_effect=lambda m=None: dict(original(m), **{field: 'changed'})):
                    self.assertEqual(self.execute(root, sub, (UNIT, other)), 3)
                self.assertEqual(sub.calls, 1)
    def test_checkpoint_tamper_rejected(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            root = Path(tmp)
            self.execute(root, Subject())
            rp = root / (R.file_config(CFG)+'.jsonl')
            record = R.load_records(rp)[0]
            record['status'] = 'missing'
            sessions = R.load_json(root / (R.file_config(CFG)+'.json'), {})['sessions']
            with self.assertRaises(R.Stop):
                R.valid_records([record], sessions, 'fp')

    def test_startup_invalid_is_persistent_after_bytes_restored(self):
        for mode in ('result', 'raw', 'missing'):
            with self.subTest(mode=mode), temporary_directory(dir=Path.cwd()) as tmp:
                root = Path(tmp)
                sub = Subject()
                rp = root / (R.file_config(CFG)+'.jsonl')
                mp = root / (R.file_config(CFG)+'.json')
                self.assertEqual(self.execute(root, sub), 0)
                record = R.load_records(rp)[0]
                if mode == 'raw':
                    raw = root / 'raw.txt'
                    raw.write_bytes(b'original')
                    record['attempts'][0]['meta'].update(raw_prefix=str(root/'raw'),
                                                        raw_sha256={'.txt': R._sha(b'original')})
                    rp.write_text(json.dumps(record)+'\n', encoding='utf-8')
                    meta = R.load_json(mp, {})
                    meta['sessions'][0]['record_sha256'] = R.record_hash(record)
                    R.save_json(mp, meta)
                    raw.write_bytes(b'changed')
                original = rp.read_bytes()
                if mode == 'result':
                    record['status'] = 'missing'
                    rp.write_text(json.dumps(record)+'\n', encoding='utf-8')
                elif mode == 'missing':
                    rp.write_bytes(b'')
                self.assertEqual(self.execute(root, sub), 3)
                meta = R.load_json(mp, {})
                self.assertTrue(meta['sessions'][0]['invalid'])
                self.assertEqual(meta['stopped']['unit'], R.unit_id(UNIT))
                self.assertTrue(meta['sessions'][0]['invalid_at'])
                self.assertTrue(Path(str(mp)+'.stop.json').exists())
                rp.write_bytes(original)
                if mode == 'raw':
                    raw.write_bytes(b'original')
                self.assertEqual(self.execute(root, sub), 3)
                self.assertEqual(sub.calls, 1)

    def test_same_model_process_lock_and_stale_file(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            lock = Path(tmp) / 'model.lock'
            code = '''import sys
from pathlib import Path
from run_agy import ModelLock, Stop
try:
    with ModelLock(Path(sys.argv[1])):
        print('acquired', flush=True)
        sys.stdin.readline()
except Stop:
    sys.exit(3)
'''
            cmd = [sys.executable, '-X', 'utf8', '-B', '-c', code, str(lock)]
            first = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                self.assertEqual(first.stdout.readline().strip(), b'acquired')
                second = subprocess.run(cmd, input=b'\n', capture_output=True, timeout=10)
                self.assertEqual(second.returncode, 3, second.stderr)
            finally:
                first.kill()
                first.communicate(timeout=10)
            third = subprocess.run(cmd, input=b'\n', capture_output=True, timeout=10)
            self.assertEqual(third.returncode, 0, third.stderr)

    def test_crash_before_checkpoint_redoes_only_unclosed(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            root = Path(tmp)
            original = R.save_json
            def crash(path, obj):
                if obj['sessions']:
                    raise OSError('simulated crash before registry commit')
                return original(path, obj)
            sub = Subject()
            with patch.object(R, 'save_json', side_effect=crash), self.assertRaises(OSError):
                self.execute(root, sub)
            self.assertEqual(self.execute(root, sub), 0)
            self.assertEqual(sub.calls, 2)
            records = R.load_records(root / (R.file_config(CFG)+'.jsonl'))
            self.assertEqual(len(records), 2)

    def test_simultaneous_model_processes_use_stub(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            root = Path(tmp)
            settings = root / 'settings.json'
            settings.write_text('{"permissions": {}}', encoding='utf-8')
            code = '''import sys
from pathlib import Path
from unittest.mock import patch
import run_agy as R
from agy_subject import AgySubject
import agy_subject as S
S.check_workroot = lambda path: Path(path).resolve()
from test_run_agy import ITEM, UNIT
root=Path(sys.argv[1]); cfg=sys.argv[2]
sub=AgySubject(cfg[4:],root/R.file_config(cfg),(sys.executable,'-X','utf8','-B',str(Path('stub_agy.py').resolve())),root/'settings.json',workroot=root/R.file_config(cfg)/'work')
with patch.object(R,'make_schedule',return_value=[UNIT]):
    sys.exit(R.execute('dev',cfg,{'k':ITEM},{'repeat_subset':[]},sub,{},'fp',root/(R.file_config(cfg)+'.jsonl'),root/(R.file_config(cfg)+'.json')))
'''
            def run(cfg):
                return subprocess.run([sys.executable, '-X', 'utf8', '-B', '-c', code, str(root), cfg], capture_output=True, timeout=30)
            with concurrent.futures.ThreadPoolExecutor(2) as pool:
                results = list(pool.map(run, R.CONFIGS[:2]))
            for cfg, result in zip(R.CONFIGS, results):
                self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
                rows = R.load_records(root / (R.file_config(cfg)+'.jsonl'))
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]['config'], cfg)

if __name__ == '__main__':
    unittest.main()
