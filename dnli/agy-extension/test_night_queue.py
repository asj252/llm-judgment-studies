import datetime as dt
from pathlib import Path
import unittest
from unittest.mock import patch
import night_queue as N
import run_agy as R
from test_run_agy import Subject, ITEM, UNIT
from workspace_temp import temporary_directory

class Clock:
    def __init__(self, hour=0, minute=0):
        self.t = dt.datetime(2026, 10, 13, hour, minute, tzinfo=dt.timezone(dt.timedelta(hours=8)))
    def now(self):
        return self.t
    def sleep(self, s):
        self.t += dt.timedelta(seconds=s)

class NightTests(unittest.TestCase):
    def test_deadline_and_grace_redo(self):
        for overrun in (False, True):
            with temporary_directory(dir=Path.cwd()) as tmp:
                clock = Clock(7, 59)
                policy = N.NightPolicy(N.deadline_today(clock.now(), '08:00'), now=clock.now, sleep=clock.sleep, timeout=3600)
                sub = Subject()
                original = sub.attempt
                def attempt(*args):
                    self.assertEqual(sub.timeout, 960)
                    clock.sleep(961 if overrun else 61)
                    return original(*args)
                sub.attempt = attempt
                root = Path(tmp)
                other = ('k', 'prior', '-', 'direct', 'r1')
                with patch.object(R, 'make_schedule', return_value=[UNIT, other]):
                    code = R.execute('dev', 'agy:'+N.MODELS[0],
                        {'k': ITEM}, {}, sub, {}, 'fp', root/'r.jsonl', root/'m.json', policy, lambda _: None)
                self.assertEqual(code, 4)
                self.assertEqual(sub.calls, 1)
                meta = R.load_json(root/'m.json', {})
                self.assertFalse(meta.get('stopped'))
                self.assertEqual(len(meta['sessions']), 0 if overrun else 1)
                if overrun:
                    clock.t += dt.timedelta(days=1)
                    p2 = N.NightPolicy(N.deadline_today(clock.now(), '23:00'), now=clock.now, sleep=clock.sleep)
                    with patch.object(R, 'make_schedule', return_value=[UNIT]):
                        self.assertEqual(R.execute('dev', 'agy:'+N.MODELS[0], {'k': ITEM}, {}, Subject(),
                            {}, 'fp', root/'r.jsonl', root/'m.json', p2, lambda _: None), 0)

    def test_wait_interrupted_and_persisted(self):
        clock = Clock(7, 59)
        p = N.NightPolicy(N.deadline_today(clock.now(), '08:00'), now=clock.now, sleep=clock.sleep)
        saved = []
        with self.assertRaises(R.Pause):
            p.limited(lambda: saved.append(dict(p.state)))
        self.assertEqual(clock.now().hour, 8)
        self.assertEqual(p.state['wake_at'], '2026-10-13T08:04:00+08:00')
        self.assertEqual(p.state['daily']['2026-10-13']['wait_seconds'], 60)
        self.assertTrue(saved)

    def test_execute_persists_deadline_wait(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            root, clock = Path(tmp), Clock(7, 59)
            p = N.NightPolicy(N.deadline_today(clock.now(), '08:00'), now=clock.now, sleep=clock.sleep)
            with patch.object(R, 'make_schedule', return_value=[UNIT]):
                code = R.execute('dev', 'agy:'+N.MODELS[0], {'k': ITEM}, {}, Subject(('rate_limited',)),
                                 {}, 'fp', root/'r.jsonl', root/'m.json', p, lambda _: None)
            self.assertEqual(code, 4)
            meta = R.load_json(root/'m.json', {})
            self.assertTrue(meta['retry_state']['wake_at'])
            self.assertEqual(meta['retry_state']['daily']['2026-10-13']['wait_seconds'], 60)
            self.assertFalse(meta.get('stopped'))
            self.assertFalse(meta['sessions'])

    def test_registered_quota_diagnostic_only(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            prefix = str(Path(tmp)/'call')
            Path(prefix+'.stderr.txt').write_text('subscription budget exhausted', encoding='utf-8')
            Path(prefix+'.stream.jsonl').write_text('', encoding='utf-8')
            clock = Clock()
            p = N.NightPolicy(N.deadline_today(clock.now(), '08:00'), now=clock.now,
                             exhausted_patterns=('subscription budget exhausted',))
            r = {'meta': {'raw_prefix': prefix}, 'final': {'state': 'rate_limited'}}
            with self.assertRaises(R.Pause) as exc:
                p.after_attempt(r)
            self.assertEqual(exc.exception.code, 5)
            Path(prefix+'.stderr.txt').write_text('429', encoding='utf-8')
            Path(prefix+'.stream.jsonl').write_text('{"event":"error","usage":{"text":"subscription budget exhausted"}}', encoding='utf-8')
            p.after_attempt(r)

    def test_queue_lock_and_unavailable_early_end(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            q = self.queue(Path(tmp), Clock())
            q.state_path.parent.mkdir(parents=True, exist_ok=True)
            with R.ModelLock(Path(tmp)/'raw'/'queue.lock'), self.assertRaises(R.Stop):
                self.runq(q)
            for row in q.state['models'].values():
                row['needs_review'] = {'reason': 'review'}
            q.save()
            with patch.object(q, 'factory', side_effect=AssertionError('must not call')):
                self.runq(q)
            self.assertEqual(q.state['nights'][-1]['completed'], {})

    def test_quota_threshold_during_wait(self):
        clock = Clock()
        p = N.NightPolicy(N.deadline_today(clock.now(), '08:00'), quota_hours=.01,
                          now=clock.now, sleep=clock.sleep)
        with self.assertRaises(R.Pause) as raised:
            p.limited(lambda: None)
        self.assertEqual(raised.exception.code, 5)
        self.assertEqual(N.next_monday(clock.now()).isoformat(), '2026-10-19T00:00:00+08:00')
        self.assertEqual(N.next_monday(dt.datetime(2026, 10, 19, tzinfo=clock.now().tzinfo)).day, 26)

    def queue(self, root, clock, subjects=None, **kwargs):
        subjects = subjects or {}
        def factory(model, *args, **kw):
            return subjects.setdefault(model, Subject())
        q = N.Queue(root, now=clock.now, sleep=clock.sleep, factory=factory, log=lambda _: None, **kwargs)
        # Bind deterministic synthetic fingerprints; no experiment materials/calls.
        return q

    def runq(self, q):
        with patch.object(R, 'fingerprint', return_value=({}, 'fp')), patch.object(R, 'make_schedule', return_value=[UNIT]):
            return q.run({'k': ITEM}, {})

    def test_all_complete_and_dev_gate(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            clock = Clock()
            subjects = {m: Subject() for m in N.MODELS}
            q = self.queue(Path(tmp), clock, subjects)
            state = self.runq(q)
            self.assertTrue(all(r['stage'] == 'done' for r in state['models'].values()))
            self.assertTrue(all(s.calls == 2 for s in subjects.values()))
            self.runq(q)
            self.assertTrue(all(s.calls == 2 for s in subjects.values()))

    def test_failed_acceptance_switch_and_manual_clear(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            root, clock = Path(tmp), Clock()
            subjects = {N.MODELS[0]: Subject(('contaminated', 'ok'))}
            q = self.queue(root, clock, subjects)
            state = self.runq(q)
            self.assertTrue(state['models'][N.MODELS[0]]['needs_review'])
            self.assertEqual(state['models'][N.MODELS[1]]['stage'], 'done')
            self.assertEqual(subjects[N.MODELS[0]].calls, 2)  # no formal
            for row in state['models'].values():
                row['needs_review'] = {'reason': 'manual review'}
            q.save()
            self.runq(q)
            self.assertEqual(subjects[N.MODELS[0]].calls, 2)
            # a authorizes a new development boundary: invalidate failed acceptance checkpoint.
            rp, mp = q.paths(N.MODELS[0], 'dev')
            meta = R.load_json(mp, {})
            meta['sessions'][0]['invalid'] = True
            R.save_json(mp, meta)
            q.state['models'][N.MODELS[0]]['needs_review'] = None
            q.save()
            self.runq(q)
            self.assertEqual(q.state['models'][N.MODELS[0]]['stage'], 'done')

    def test_quota_skip_switch_expire_resume(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            root, clock = Path(tmp), Clock()
            subjects = {N.MODELS[0]: Subject(('rate_limited',))}
            q = self.queue(root, clock, subjects, quota_hours=.01)
            state = self.runq(q)
            self.assertEqual(state['models'][N.MODELS[0]]['skipped_until'], '2026-10-19T00:00:00+08:00')
            self.assertEqual(state['models'][N.MODELS[1]]['stage'], 'done')
            calls = subjects[N.MODELS[0]].calls
            self.runq(q)
            self.assertEqual(subjects[N.MODELS[0]].calls, calls)
            clock.t = dt.datetime(2026, 10, 19, tzinfo=clock.now().tzinfo)
            subjects[N.MODELS[0]] = Subject()
            q = self.queue(root, clock, subjects, quota_hours=.01)
            self.runq(q)
            self.assertEqual(q.state['models'][N.MODELS[0]]['stage'], 'done')
            self.assertEqual(subjects[N.MODELS[0]].calls, 2)

    def test_stop_switch(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            q = self.queue(Path(tmp), Clock(), {N.MODELS[0]: Subject(('check_failed',))})
            state = self.runq(q)
            self.assertTrue(state['models'][N.MODELS[0]]['needs_review'])
            self.assertEqual(state['models'][N.MODELS[1]]['stage'], 'done')

    def test_acceptance_boundaries(self):
        records = {str(i): {'status': 'ok', 'attempts': [{'state': 'ok', 'parsed': i < 90}]} for i in range(100)}
        self.assertTrue(N.acceptance(records, set(records))['passed'])
        records['0']['status'] = records['1']['status'] = 'missing'
        self.assertTrue(N.acceptance(records, set(records))['passed'])
        records['2']['status'] = 'missing'
        self.assertFalse(N.acceptance(records, set(records))['passed'])
        self.assertFalse(N.acceptance(records, set(records), True)['passed'])
        self.assertFalse(N.acceptance(records, set(records)|{'new'})['passed'])

if __name__ == '__main__':
    unittest.main()
