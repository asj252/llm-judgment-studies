"""Offline fixtures for conservative pre-conversation recovery."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import unittest
from unittest.mock import patch

import auto_clear as A
import run_agy as R
from night_queue import NightPolicy
from workspace_temp import temporary_directory

HERE = Path(__file__).resolve().parent
MODEL = 'gemini-3.8-flash-low'
UNIT = 'item|stated|S|direct|r0'
NOW = dt.datetime(2026, 10, 16, 1, tzinfo=dt.timezone.utc)
DAY = '2026-10-16'
BASELINE = {
    '../dnli/split.json': '3e09db9ac6e10375bf17e6254fbb6ad5992798f2a03a1ba93c4f896b5eeaf39b',
    '../dnli/raw/items_text.json': '54e08df0874587377a259925f49ad8796de6ac4d05c0729fbfa7ae0cf479f67c',
    'prompts.py': '0192adda8087ec9c7515f169ca5cdaf2d01127e4eb6ab87a333c6ab2d1abae87',
    'parse.py': '9c596c1d3b63d9ab5c423461a502af540ba27fb26afc5c0679a158973c5ef8c8',
    'run_agy.py': '6aa83ddb5368d9e82ab297a2704dfaca1f157c278e7a63e20a90f28b301e93f2',
    'agy_subject.py': 'f3e679771636ecf40e535ab1968641cb70ce83b9f6bd3cf61e035d26e3bdd9b3',
    'configs.py': '1d11a0120b355ea14c5d56966be5c62a2f690ce95c4ee41981e4a004be8790d8',
    'workspace_temp.py': 'cd8f154fcd1685aa6104d3dfb5c2994ab8bccc380eba6ca5e0e5e1bd1f33527d',
    'brief-e-agy.md': 'ab73524534e31e3c0340eca4c4515798ef1b1de652883a6cd07a19b418f29a5f',
    'agent/dnli-subject.md': '709c6712f5a898d1f021e047b9fc44a9397f59c5bfa52c6bd790f3cf02ed8cb5',
    'night_queue.py': '8088ef88397d2cd9d4aef2c2b458d399a8b914d7fcb009980ef20beb63d952b5',
}


class AutoClearTests(unittest.TestCase):
    def fixture(self, root, stderr='Eligibility check failed: network timeout'):
        final = {'state': 'check_failed', 'reasons': sorted(A.ALLOWED_REASONS),
                 'include': False, 'stop': True, 'resample': False}
        stop = {'unit': UNIT, 'units': [UNIT], 'reason': UNIT + ': ' + str(final),
                'datetime': NOW.isoformat()}
        state = {'models': {MODEL: {'stage': 'dev', 'needs_review': {
            'reason': str(stop), 'datetime': NOW.isoformat()}, 'skipped_until': None}}}
        mp = root / ('run_meta_dev_agy_' + MODEL + '.json')
        R.save_json(root / 'raw' / 'queue_state.json', state)
        R.save_json(mp, dict(self.checkpoint_fixture(root), stopped=stop))
        R.save_json(str(mp) + '.stop.json', stop)
        raw = root / 'raw' / ('run_dev_agy_' + MODEL)
        raw.mkdir()
        stem = raw / (R._safe(UNIT) + '_a0_abc')
        R.save_json(str(stem) + '.attempt.json', {'final': final})
        event = {'event': 'result', 'result': {'conversation_id': '', 'status': 'ERROR',
                 'num_turns': 0, 'usage': dict.fromkeys(('input_tokens', 'output_tokens',
                 'thinking_tokens', 'cache_read_tokens', 'total_tokens'), 0),
                 'response': '', 'error': stderr, 'duration_seconds': 0.25}}
        stream = Path(str(stem) + '.stream.jsonl')
        stream.write_text(json.dumps(event) + '\n', encoding='utf-8')
        Path(str(stem) + '.stderr.txt').write_text(stderr, encoding='utf-8')
        return mp, stem, event

    def run_clear(self, root, messages=None):
        return A.clear(root, DAY, 30, NOW, log=(messages if messages is not None else []).append)

    def test_whitelist_and_backup(self):
        samples = [('Eligibility check failed: timeout', 'eligibility'),
                   ('Authentication required: refresh failed', 'authentication'),
                   ('x is not recognized as a known model', 'known_model'),
                   ('Eligibility check: TLS handshake timeout', 'eligibility_tls'),
                   ('Eligibility check failed: EOF', 'eligibility_eof')]
        self.assertEqual({name for _, name in samples}, {name for name, _ in A.STDERR_RULES})
        for stderr, rule in samples:
            with self.subTest(rule=rule), temporary_directory(dir=HERE) as tmp:
                root = Path(tmp)
                mp, stem, _ = self.fixture(root, stderr)
                state_bytes = (root / 'raw/queue_state.json').read_bytes()
                meta_bytes = mp.read_bytes()
                stop_bytes = Path(str(mp) + '.stop.json').read_bytes()
                self.assertEqual(self.run_clear(root), 1)
                row = R.load_json(root / 'raw/queue_state.json', {})['models'][MODEL]
                self.assertIsNone(row['needs_review'])
                self.assertEqual(dt.datetime.fromisoformat(row['skipped_until']), NOW + dt.timedelta(minutes=30))
                meta = R.load_json(mp, {})
                self.assertIsNone(meta['stopped'])
                self.assertEqual(meta['sessions'], json.loads(meta_bytes)['sessions'])
                self.assertEqual(meta['fingerprint_id'], 'fixture-fp')
                self.assertFalse(Path(str(mp) + '.stop.json').exists())
                audit = R.load_json(root / ('raw/auto_clear_' + DAY + '/audit.jsonl'), {})
                self.assertEqual(audit['stderr_rule'], rule)
                self.assertEqual(audit['unit'], UNIT)
                self.assertEqual(audit['attempt_file'], str(Path(str(stem) + '.attempt.json').relative_to(root)))
                self.assertEqual(audit['attempt_time_source'], 'attempt_number')
                self.assertEqual(audit['attempt_sort_value'], {'number': 0})
                self.assertEqual(audit['datetime'], NOW.isoformat())
                self.assertEqual(audit['stream_sha256'], hashlib.sha256(Path(str(stem) + '.stream.jsonl').read_bytes()).hexdigest())
                backup = root / audit['backup']
                self.assertEqual((backup / 'queue_state.json').read_bytes(), state_bytes)
                self.assertEqual((backup / mp.name).read_bytes(), meta_bytes)
                self.assertEqual((backup / (mp.name + '.stop.json')).read_bytes(), stop_bytes)
                self.assertEqual(self.run_clear(root), 0)

    def test_explicit_attempt_stop_and_third_clear_allowed(self):
        with temporary_directory(dir=HERE) as tmp:
            root = Path(tmp)
            self.fixture(root, 'EOF during Eligibility check')
            state_path = root / 'raw/queue_state.json'
            state = R.load_json(state_path, {})
            state['models'][MODEL]['needs_review'] = {'reason': 'attempt STOP', 'unit': UNIT}
            R.save_json(state_path, state)
            audit = root / ('raw/auto_clear_' + DAY + '/audit.jsonl')
            audit.parent.mkdir()
            audit.write_text((json.dumps({'model': MODEL}) + '\n') * 2, encoding='utf-8')
            self.assertEqual(self.run_clear(root), 1)
            self.assertEqual(len(audit.read_text(encoding='utf-8').splitlines()), 3)

    def test_real_night_policy_stop(self):
        # Acceptance 1: use the real producer and persistence, with offline input.
        with temporary_directory(dir=HERE) as tmp:
            root = Path(tmp)
            mp, stem, _ = self.fixture(root)
            attempt = R.load_json(str(stem) + '.attempt.json', {})
            attempt['meta'] = {}
            policy = NightPolicy(NOW + dt.timedelta(hours=1), now=lambda: NOW)
            with self.assertRaises(R.Stop) as caught:
                policy.after_attempt(attempt)
            meta = R.load_json(mp, {})
            meta['stopped'] = None
            meta['active_unit'] = UNIT
            R.persist_stop(mp, meta, caught.exception, NOW)
            state_path = root / 'raw/queue_state.json'
            state = R.load_json(state_path, {})
            # Queue.run_model raises str(meta.stopped); Queue.run stores str(exc).
            state['models'][MODEL]['needs_review']['reason'] = str(R.Stop(str(meta['stopped'])))
            R.save_json(state_path, state)
            self.assertEqual(self.run_clear(root), 1)

    def test_strict_stream_rejections(self):
        # Acceptance 2: evidence must independently rule out output/tool activity.
        mutations = {
            'tool_call': lambda e: e['result'].update(tool_call={'name': 'read'}),
            'text_delta': lambda e: e['result'].update(text_delta='partial'),
            'top_extra': lambda e: e.update(tool_call={}),
            'result_extra': lambda e: e['result'].update(extra=None),
            'result_missing': lambda e: e['result'].pop('response'),
            'error_unknown': lambda e: e['result'].update(error='unknown'),
            'error_type': lambda e: e['result'].update(error={}),
            'duration_negative': lambda e: e['result'].update(duration_seconds=-1),
            'duration_string': lambda e: e['result'].update(duration_seconds='0'),
            'duration_bool': lambda e: e['result'].update(duration_seconds=False),
            'duration_nan': lambda e: e['result'].update(duration_seconds=float('nan')),
            'duration_inf': lambda e: e['result'].update(duration_seconds=float('inf')),
            'usage_missing': lambda e: e['result']['usage'].pop('output_tokens'),
            'usage_extra': lambda e: e['result']['usage'].update(extra=0),
            'turns_bool': lambda e: e['result'].update(num_turns=False),
        }
        for field in ('input_tokens', 'output_tokens', 'thinking_tokens',
                      'cache_read_tokens', 'total_tokens'):
            for value in (12, False, 0.0):
                mutations[(field, str(value))] = lambda e, f=field, v=value: e['result']['usage'].update({f: v})
        for event_name in ('tool', 'step_update', 'text_delta', 'init'):
            mutations[event_name + '_event'] = lambda e, n=event_name: e.update(event=n)
        for case, mutate in mutations.items():
            with self.subTest(case=case), temporary_directory(dir=HERE) as tmp:
                root = Path(tmp)
                _, stem, event = self.fixture(root)
                mutate(event)
                Path(str(stem) + '.stream.jsonl').write_text(json.dumps(event), encoding='utf-8')
                before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
                self.assertEqual(self.run_clear(root), 0)
                self.assertEqual(before, {p: p.read_bytes() for p in before})
                self.assertFalse((root / ('raw/auto_clear_' + DAY)).exists())

    def test_attempt_order_ignores_mtime(self):
        # Acceptance 3: higher retry number wins, even if an older file is touched.
        for latest_complete in (True, False):
            with self.subTest(complete=latest_complete), temporary_directory(dir=HERE) as tmp:
                root = Path(tmp)
                _, stem, _ = self.fixture(root)
                for suffix in ('.stream.jsonl', '.stderr.txt', '.attempt.json'):
                    old = Path(str(stem) + suffix)
                    if latest_complete or suffix == '.stream.jsonl':
                        new = Path(str(stem).replace('_a0_', '_a1_') + suffix)
                        new.write_bytes(old.read_bytes())
                    os.utime(old, ns=(old.stat().st_mtime_ns + 10000000000,) * 2)
                self.assertEqual(self.run_clear(root), int(latest_complete))

    def test_ambiguous_attempt_skips(self):
        # Acceptance 3: duplicate highest number or unknown order must fail closed.
        for name in ('_a0_duplicate', '_aunknown'):
            with self.subTest(name=name), temporary_directory(dir=HERE) as tmp:
                root = Path(tmp)
                _, stem, _ = self.fixture(root)
                (stem.parent / (R._safe(UNIT) + name + '.stream.jsonl')).write_text('{}', encoding='utf-8')
                messages = []
                self.assertEqual(self.run_clear(root, messages), 0)
                self.assertIn('ambiguous_attempt', messages[0])
                self.assertIsNotNone(R.load_json(root / 'raw/queue_state.json', {})['models'][MODEL]['needs_review'])

    def test_reject_without_mutation(self):
        cases = ('extra_reason', 'init', 'step_update', 'tokens', 'conversation', 'stderr',
                 'bare_tls', 'bare_eof', 'split_eof', 'limit', 'unit', 'missing',
                 'missing_stderr', 'missing_attempt', 'newer_incomplete', 'bad_json',
                 'wrong_reason', 'wrong_state', 'nonzero_turns', 'response')
        for case in cases:
            with self.subTest(case=case), temporary_directory(dir=HERE) as tmp:
                root = Path(tmp)
                mp, stem, event = self.fixture(root)
                stream = Path(str(stem) + '.stream.jsonl')
                ap = Path(str(stem) + '.attempt.json')
                if case in ('extra_reason', 'wrong_state'):
                    attempt = R.load_json(ap, {})
                    if case == 'extra_reason':
                        attempt['final']['reasons'].append('environment_changed_during_call')
                    else:
                        attempt['final']['state'] = 'call_error'
                    R.save_json(ap, attempt)
                elif case in ('init', 'step_update'):
                    stream.write_text(json.dumps({'event': case}) + '\n' + json.dumps(event), encoding='utf-8')
                elif case in ('tokens', 'conversation', 'nonzero_turns', 'response'):
                    if case == 'tokens': event['result']['usage']['total_tokens'] = 1
                    if case == 'conversation': event['result']['conversation_id'] = 'started'
                    if case == 'nonzero_turns': event['result']['num_turns'] = 1
                    if case == 'response': event['result']['response'] = 'answer'
                    stream.write_text(json.dumps(event), encoding='utf-8')
                elif case in ('stderr', 'bare_tls', 'bare_eof', 'split_eof'):
                    Path(str(stem) + '.stderr.txt').write_text({
                        'stderr': 'unknown error', 'bare_tls': 'TLS handshake timeout',
                        'bare_eof': 'EOF', 'split_eof': 'Eligibility check\nEOF'}[case], encoding='utf-8')
                elif case == 'limit':
                    audit = root / ('raw/auto_clear_' + DAY + '/audit.jsonl')
                    audit.parent.mkdir()
                    audit.write_text((json.dumps({'model': MODEL}) + '\n') * A.DAILY_LIMIT, encoding='utf-8')
                elif case == 'unit':
                    stop = R.load_json(str(mp) + '.stop.json', {})
                    stop['unit'] = 'other'
                    R.save_json(str(mp) + '.stop.json', stop)
                elif case == 'missing': stream.unlink()
                elif case == 'missing_stderr': Path(str(stem) + '.stderr.txt').unlink()
                elif case == 'missing_attempt': ap.unlink()
                elif case == 'newer_incomplete':
                    newer = stem.parent / (R._safe(UNIT) + '_a1_new.stream.jsonl')
                    newer.write_text('{}', encoding='utf-8')
                    os.utime(newer, ns=(stream.stat().st_mtime_ns + 1000000000,) * 2)
                elif case == 'bad_json': stream.write_text('{', encoding='utf-8')
                elif case == 'wrong_reason':
                    state = R.load_json(root / 'raw/queue_state.json', {})
                    state['models'][MODEL]['needs_review']['reason'] = 'environment changed'
                    R.save_json(root / 'raw/queue_state.json', state)
                before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
                logs = []
                self.assertEqual(self.run_clear(root, logs), 0)
                self.assertTrue(logs[0].startswith('AUTO_CLEAR_SKIP ' + MODEL))
                self.assertEqual(before, {p: p.read_bytes() for p in before})
                if case != 'limit':
                    self.assertFalse((root / ('raw/auto_clear_' + DAY)).exists())

    def test_duplicate_attempt_times(self):
        # v4 acceptance 3: same number requires recorded timestamps for every candidate.
        for clock in ('stamp', 'stamp_tie', 'mixed', 'mtime', 'boundary', 'tie',
                      'spread', 'bad_stamp', 'naive_stamp'):
            for latest_valid in (True, False):
                with self.subTest(clock=clock, valid=latest_valid), temporary_directory(dir=HERE) as tmp:
                    root = Path(tmp)
                    _, stem, event = self.fixture(root)
                    newer = Path(str(stem).replace('_abc', '_later'))
                    for suffix in A.ATTEMPT_SUFFIXES:
                        Path(str(newer) + suffix).write_bytes(Path(str(stem) + suffix).read_bytes())
                    for index, base in enumerate((stem, newer)):
                        ap = Path(str(base) + '.attempt.json')
                        data = R.load_json(ap, {})
                        if clock in ('stamp', 'stamp_tie', 'mixed', 'bad_stamp', 'naive_stamp'):
                            data['meta'] = {'datetime': (NOW + dt.timedelta(minutes=index)).isoformat()}
                            if clock == 'stamp_tie':
                                data['meta']['datetime'] = NOW.isoformat()
                            if clock == 'mixed':
                                if index:
                                    data.pop('meta')
                                else:
                                    data['meta']['datetime'] = dt.datetime.fromtimestamp(1000, dt.timezone.utc).isoformat()
                            if clock == 'bad_stamp' and index:
                                data['meta']['datetime'] = 'bad'
                            if clock == 'naive_stamp' and index:
                                data['meta']['datetime'] = NOW.replace(tzinfo=None).isoformat()
                        R.save_json(ap, data)
                        for pos, suffix in enumerate(A.ATTEMPT_SUFFIXES):
                            seconds = 1000 + (0 if clock == 'tie' else index * 60)
                            if clock == 'spread' and index:
                                seconds += pos * 3
                            if clock == 'boundary' and index:
                                seconds += (0, 2, 5)[pos]
                            # Timestamp ordering must win over reversed mtimes.
                            if clock == 'stamp': seconds = 2000 - index * 60
                            os.utime(str(base) + suffix, (seconds, seconds))
                    if not latest_valid:
                        event['result']['response'] = 'started'
                        p = Path(str(newer) + '.stream.jsonl')
                        stamp = p.stat().st_mtime_ns
                        p.write_text(json.dumps(event), encoding='utf-8')
                        os.utime(p, ns=(stamp, stamp))
                    expected = latest_valid and clock == 'stamp'
                    messages = []
                    self.assertEqual(self.run_clear(root, messages), int(expected))
                    if expected:
                        entry = json.loads((root / ('raw/auto_clear_' + DAY + '/audit.jsonl')).read_text(encoding='utf-8'))
                        self.assertEqual(entry['attempt_time_source'], 'meta.datetime')
                        self.assertEqual(entry['attempt_sort_value'], {'number': 0, 'timestamp': (NOW + dt.timedelta(minutes=1)).timestamp()})
                        self.assertTrue(entry['attempt_file'].endswith('_later.attempt.json'))
                    if clock != 'stamp':
                        self.assertIn('ambiguous_attempt', messages[0])

    def checkpoint_fixture(self, root, stage='dev', extra=0):
        record = {'unit': 'previous|stated|S|direct|r0', 'session_id': 'one',
                  'fingerprint_id': 'fixture-fp', 'status': 'finished', 'attempts': [],
                  'prediction': 'S', 'config': 'agy:' + MODEL, 'which': stage}
        session = {'session_id': record['session_id'], 'unit': record['unit'],
                   'closed_ok': True, 'invalid': False, 'fingerprint_id': 'fixture-fp',
                   'record_sha256': R.record_hash(record)}
        records = [record]
        if extra:
            records.append(dict(record, unit=UNIT, session_id='two'))
        rp = root / ('results_%s_agy_%s.jsonl' % (stage, MODEL))
        rp.write_text(''.join(json.dumps(r) + '\n' for r in records), encoding='utf-8')
        return {'sessions': [session], 'fingerprint_id': 'fixture-fp'}

    def test_no_registered_results_yet(self):
        # v4 acceptance 1: the first failed attempt has no checkpoint to verify.
        with temporary_directory(dir=HERE) as tmp:
            root = Path(tmp)
            mp, _, _ = self.fixture(root)
            meta = R.load_json(mp, {})
            meta['sessions'] = []
            R.save_json(mp, meta)
            (root / ('results_dev_agy_' + MODEL + '.jsonl')).unlink()
            self.assertEqual(self.run_clear(root), 1)

    def test_old_crash_rows(self):
        # v5 acceptance 3/4/5: only later registered rows supersede crash debris.
        cases = ('two_redone', 'same_unit_twice', 'redone_and_current',
                 'never_redone', 'registered_before', 'current_and_unredone')
        for access in (True, False, 'results'):
            for case in cases:
                with self.subTest(access=access, case=case), temporary_directory(dir=HERE) as tmp:
                    root = Path(tmp)
                    if access == 'results':
                        mp, rp = self.results_access_fixture(root, stage='formal')
                    elif access:
                        mp, _, rp = self.access_fixture(root, extra=0, stage='formal')
                    else:
                        mp, _, _ = self.fixture(root)
                        rp = root / ('results_dev_agy_' + MODEL + '.jsonl')
                    meta = R.load_json(mp, {})
                    first = R.load_records(rp)[0]
                    second = dict(first, unit='second|stated|S|direct|r0', session_id='second')
                    meta['sessions'].append(dict(meta['sessions'][0], unit=second['unit'],
                                                 session_id=second['session_id'],
                                                 record_sha256=R.record_hash(second)))
                    old_first = dict(first, session_id='old-first')
                    old_second = dict(second, session_id='old-second')
                    current = dict(first, unit=UNIT, session_id='current')
                    if case == 'two_redone':
                        records = [old_first, first, old_second, second]
                        stale = [(first['unit'], 1), (second['unit'], 3)]
                    elif case == 'same_unit_twice':
                        records = [old_first, dict(old_first, session_id='older-first'), first, second]
                        stale = [(first['unit'], 1), (first['unit'], 2)]
                    elif case == 'redone_and_current':
                        records = [old_first, first, old_second, second, current]
                        stale = [(first['unit'], 1), (second['unit'], 3)]
                    elif case == 'never_redone':
                        records = [dict(old_first, unit='never'), first, second]
                    elif case == 'registered_before':
                        records = [first, old_first, second]
                    else:
                        records = [dict(old_first, unit='never'), first, second, current]
                    rp.write_text(''.join(json.dumps(r) + '\n' for r in records), encoding='utf-8')
                    R.save_json(mp, meta)
                    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
                    allowed = case in ('two_redone', 'same_unit_twice', 'redone_and_current')
                    self.assertEqual(self.run_clear(root), int(allowed))
                    audit = root / ('raw/auto_clear_' + DAY + '/audit.jsonl')
                    if allowed:
                        entry = json.loads(audit.read_text(encoding='utf-8'))
                        self.assertEqual(entry['stale_results'], [
                            {'unit': unit, 'line_number': number} for unit, number in stale])
                        self.assertEqual(rp.read_bytes(), before[rp])
                        if access:
                            self.assertEqual(mp.read_bytes(), before[mp])
                            self.assertEqual(entry['registered_count'], 2)
                            self.assertEqual(entry['result_count'], len(records))
                        else:
                            self.assertEqual(R.load_json(mp, {})['sessions'], meta['sessions'])
                    else:
                        self.assertEqual(before, {p: p.read_bytes() for p in before})
                        self.assertFalse(audit.parent.exists())

    def test_checkpoint_integrity_rejections(self):
        # v4 acceptance 1: both clear paths fail closed before audit or mutation.
        cases = ('null_session', 'broken_json', 'extra_not_last', 'extra_registered',
                 'hash', 'invalid', 'fingerprint', 'open', 'missing_fp',
                 'duplicate_session', 'record_fp', 'blank_line', 'raw_hash')
        for access in (True, False, 'results'):
            for case in cases:
                with self.subTest(access=access, case=case), temporary_directory(dir=HERE) as tmp:
                    root = Path(tmp)
                    if access == 'results':
                        mp, rp = self.results_access_fixture(root)
                    elif access:
                        mp, _, rp = self.access_fixture(root)
                    else:
                        mp, _, _ = self.fixture(root)
                        rp = root / ('results_dev_agy_' + MODEL + '.jsonl')
                    meta = R.load_json(mp, {})
                    records = R.load_records(rp)
                    if case == 'null_session': meta['sessions'] = [None]
                    elif case == 'broken_json': rp.write_text('broken-json\n', encoding='utf-8')
                    elif case == 'extra_not_last':
                        records = [dict(records[0], unit='unregistered', session_id='two'), records[0]]
                    elif case == 'extra_registered': records.append(dict(records[0], session_id='other'))
                    elif case == 'hash': meta['sessions'][0]['record_sha256'] = 'bad'
                    elif case == 'invalid': meta['sessions'][0]['invalid'] = True
                    elif case == 'fingerprint': meta['sessions'][0]['fingerprint_id'] = 'bad'
                    elif case == 'open': meta['sessions'][0]['closed_ok'] = False
                    elif case == 'missing_fp': meta.pop('fingerprint_id')
                    elif case == 'duplicate_session': meta['sessions'] *= 2
                    elif case == 'record_fp': records[0]['fingerprint_id'] = 'bad'
                    elif case == 'blank_line': rp.write_text(rp.read_text(encoding='utf-8') + '\n', encoding='utf-8')
                    elif case == 'raw_hash':
                        records[0]['attempts'] = [{'meta': {'raw_prefix': str(root / 'absent'),
                                                         'raw_sha256': {'.stream.jsonl': 'bad'}}}]
                        meta['sessions'][0]['record_sha256'] = R.record_hash(records[0])
                    if case not in ('broken_json', 'blank_line'):
                        rp.write_text(''.join(json.dumps(r) + '\n' for r in records), encoding='utf-8')
                    R.save_json(mp, meta)
                    before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
                    self.assertEqual(self.run_clear(root), 0)
                    self.assertEqual(before, {p: p.read_bytes() for p in before})
                    self.assertFalse((root / ('raw/auto_clear_' + DAY)).exists())

    def test_copied_failure_cannot_supersede_recorded_response(self):
        # v4 acceptance 3/4: copied old trio must never outrank a real response.
        for missing_stamp in (True, False):
            with self.subTest(missing=missing_stamp), temporary_directory(dir=HERE) as tmp:
                root = Path(tmp)
                _, old, event = self.fixture(root)
                latest = Path(str(old).replace('_abc', '_latest'))
                for index, stem in enumerate((old, latest)):
                    for suffix in A.ATTEMPT_SUFFIXES:
                        if index:
                            Path(str(stem) + suffix).write_bytes(Path(str(old) + suffix).read_bytes())
                    attempt = R.load_json(str(stem) + '.attempt.json', {})
                    if index or not missing_stamp:
                        attempt['meta'] = {'datetime': (NOW + dt.timedelta(minutes=index)).isoformat()}
                    R.save_json(str(stem) + '.attempt.json', attempt)
                event['result']['response'] = 'already started'
                Path(str(latest) + '.stream.jsonl').write_text(json.dumps(event), encoding='utf-8')
                for suffix in A.ATTEMPT_SUFFIXES:
                    os.utime(str(old) + suffix, (2000000000, 2000000000))
                logs = []
                self.assertEqual(self.run_clear(root, logs), 0)
                if missing_stamp: self.assertIn('ambiguous_attempt', logs[0])

    def access_fixture(self, root, extra=1, residual=True, stage='dev'):
        mp = root / ('run_meta_%s_agy_%s.json' % (stage, MODEL))
        R.save_json(mp, dict(self.checkpoint_fixture(root, stage, extra), stopped=None))
        tmp = Path(str(mp) + '.' + 'a' * 32 + '.tmp')
        if residual: tmp.write_text('do not promote this', encoding='utf-8')
        rp = root / ('results_%s_agy_%s.jsonl' % (stage, MODEL))
        reason = "[WinError 5] 拒绝访问。: '%s' -> '%s'" % (tmp, mp)
        R.save_json(root / 'raw/queue_state.json', {'models': {MODEL: {
            'stage': stage, 'needs_review': {'reason': reason}, 'skipped_until': None}}})
        return mp, tmp, rp

    def test_access_denied_allowed(self):
        # v3 acceptance 3: unchanged meta/results, optional residual moved only.
        for stage in ('dev', 'formal'):
            for extra in (0, 1):
                for residual in (True, False):
                    with self.subTest(stage=stage, extra=extra, residual=residual), temporary_directory(dir=HERE) as tmpdir:
                        root = Path(tmpdir)
                        mp, tmp, rp = self.access_fixture(root, extra, residual, stage)
                        before = mp.read_bytes(), rp.read_bytes()
                        self.assertEqual(self.run_clear(root), 1)
                        self.assertEqual((mp.read_bytes(), rp.read_bytes()), before)
                        entry = json.loads((root / ('raw/auto_clear_' + DAY + '/audit.jsonl')).read_text(encoding='utf-8'))
                        self.assertEqual(entry['kind'], 'access_denied')
                        self.assertEqual(entry['ordinal'], 1)
                        self.assertEqual(entry['wait_minutes'], 30)
                        self.assertFalse(tmp.exists())
                        self.assertEqual((root / entry['backup'] / tmp.name).exists(), residual)

    def results_access_fixture(self, root, extra=0, stage='dev'):
        mp, _, rp = self.access_fixture(root, extra, residual=False, stage=stage)
        state_path = root / 'raw/queue_state.json'
        state = R.load_json(state_path, {})
        state['models'][MODEL]['needs_review']['reason'] = "[Errno 13] Permission denied: '%s'" % rp
        R.save_json(state_path, state)
        return mp, rp

    def test_results_access_denied_allowed(self):
        # v6 acceptance 1/2/5: matching checkpoint or current last row, read only.
        for stage in ('dev', 'formal'):
            for extra in (0, 1):
                with self.subTest(stage=stage, extra=extra), temporary_directory(dir=HERE) as tmp:
                    root = Path(tmp)
                    mp, rp = self.results_access_fixture(root, extra, stage)
                    state_path = root / 'raw/queue_state.json'
                    before = {p: p.read_bytes() for p in (mp, rp, state_path)}
                    files = {p for p in root.rglob('*') if p.is_file()}
                    self.assertEqual(self.run_clear(root), 1)
                    entry = json.loads((root / ('raw/auto_clear_' + DAY + '/audit.jsonl')).read_text(encoding='utf-8'))
                    self.assertEqual(entry['kind'], 'results_access_denied')
                    self.assertEqual(entry['registered_count'], 1)
                    self.assertEqual(entry['result_count'], 1 + extra)
                    self.assertEqual(entry['stale_results'], [])
                    self.assertEqual(Path(entry['path']), rp)
                    self.assertEqual(mp.read_bytes(), before[mp])
                    self.assertEqual(rp.read_bytes(), before[rp])
                    self.assertTrue(all(p.exists() for p in files))
                    for p in (mp, state_path):
                        self.assertEqual((root / entry['backup'] / p.name).read_bytes(), before[p])
                    row = R.load_json(state_path, {})['models'][MODEL]
                    self.assertIsNone(row['needs_review'])
                    self.assertEqual(row['skipped_until'], (NOW + dt.timedelta(minutes=30)).isoformat())

    # c review r7: the real reason is str(OSError), whose path repr doubles backslashes.
    def test_results_access_denied_real_oserror_string(self):
        for case in ('ok', 'model', 'stage'):
            with self.subTest(case=case), temporary_directory(dir=HERE) as tmp:
                root = Path(tmp)
                mp, rp = self.results_access_fixture(root)
                target = {'ok': rp, 'model': Path(str(rp).replace(MODEL, 'other-model')),
                          'stage': Path(str(rp).replace('results_dev_', 'results_formal_'))}[case]
                reason = str(PermissionError(13, 'Permission denied', str(target)))
                self.assertIn(repr(str(target)), reason)  # doubled backslashes on Windows
                state_path = root / 'raw/queue_state.json'
                state = R.load_json(state_path, {})
                state['models'][MODEL]['needs_review']['reason'] = reason
                R.save_json(state_path, state)
                self.assertEqual(self.run_clear(root), 1 if case == 'ok' else 0)

    def test_results_access_denied_rejected(self):
        # v6 acceptance 1/5: wrong paths, decorated reasons, stops and bad checkpoints.
        cases = ('model', 'stage', 'invalid_stage', 'stream', 'meta_path', 'prefix',
                 'suffix', 'newline', 'stopped', 'missing_stopped', 'stop_file',
                 'missing_meta', 'meta_list', 'unredone', 'bad_hash', 'missing_results')
        for case in cases:
            with self.subTest(case=case), temporary_directory(dir=HERE) as tmp:
                root = Path(tmp)
                mp, rp = self.results_access_fixture(root)
                state_path = root / 'raw/queue_state.json'
                state = R.load_json(state_path, {})
                row = state['models'][MODEL]
                reason = row['needs_review']['reason']
                if case == 'model': reason = reason.replace(MODEL, 'other-model')
                elif case == 'stage': reason = reason.replace('results_dev_', 'results_formal_')
                elif case == 'invalid_stage': row['stage'] = 'done'
                elif case == 'stream': reason = "[Errno 13] Permission denied: '%s'" % (root / 'raw/attempt.stream.jsonl')
                elif case == 'meta_path': reason = "[Errno 13] Permission denied: '%s'" % mp
                elif case == 'prefix': reason = 'extra ' + reason
                elif case == 'suffix': reason += ' extra'
                elif case == 'newline': reason += '\n'
                elif case in ('stopped', 'missing_stopped', 'bad_hash'):
                    meta = R.load_json(mp, {})
                    if case == 'stopped': meta['stopped'] = {}
                    elif case == 'missing_stopped': meta.pop('stopped')
                    else: meta['sessions'][0]['record_sha256'] = 'bad'
                    R.save_json(mp, meta)
                elif case == 'stop_file': R.save_json(str(mp) + '.stop.json', {})
                elif case == 'missing_meta': mp.unlink()
                elif case == 'meta_list': R.save_json(mp, [])
                elif case == 'missing_results': rp.unlink()
                elif case == 'unredone':
                    rp.write_text(json.dumps({'unit': 'never-redone', 'session_id': 'other'}) + '\n'
                                  + rp.read_text(encoding='utf-8'), encoding='utf-8')
                row['needs_review']['reason'] = reason
                R.save_json(state_path, state)
                before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
                self.assertEqual(self.run_clear(root), 0)
                self.assertEqual(before, {p: p.read_bytes() for p in before})
                self.assertFalse((root / ('raw/auto_clear_' + DAY)).exists())

    def test_results_access_denied_read_permission(self):
        # v6 acceptance 1(d)/5: both evidence reads and explicit rb probe fail closed.
        for denied_mode in ('r', 'rb'):
            with self.subTest(mode=denied_mode), temporary_directory(dir=HERE) as tmp:
                root = Path(tmp)
                _, rp = self.results_access_fixture(root)
                before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
                original_open = Path.open
                def guarded_open(path, mode='r', *args, **kwargs):
                    if path == rp and mode == denied_mode:
                        raise PermissionError(13, 'Permission denied', str(path))
                    return original_open(path, mode, *args, **kwargs)
                logs = []
                with patch.object(Path, 'open', guarded_open):
                    self.assertEqual(self.run_clear(root, logs), 0)
                self.assertIn('Permission denied', logs[0])
                self.assertEqual(before, {p: p.read_bytes() for p in before})
                self.assertFalse((root / ('raw/auto_clear_' + DAY)).exists())

    def test_results_access_denied_shared_limit(self):
        # v6 acceptance 3/5: mixed kinds share ordinal, backoff and ninth-attempt cap.
        for previous in (1, 2, 7, 8):
            with self.subTest(previous=previous), temporary_directory(dir=HERE) as tmp:
                root = Path(tmp)
                self.results_access_fixture(root)
                audit = root / ('raw/auto_clear_' + DAY + '/audit.jsonl')
                audit.parent.mkdir()
                entries = [{'model': MODEL, 'kind': ('access_denied', 'pre_conversation',
                            'results_access_denied')[i % 3]} for i in range(previous)]
                audit.write_text(''.join(json.dumps(e) + '\n' for e in entries), encoding='utf-8')
                before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
                self.assertEqual(self.run_clear(root), int(previous < 8))
                actual = [json.loads(line) for line in audit.read_text(encoding='utf-8').splitlines()]
                if previous < 8:
                    wait = 60 if previous == 1 else 120
                    self.assertEqual(actual[-1]['ordinal'], previous + 1)
                    self.assertEqual(actual[-1]['wait_minutes'], wait)
                    row = R.load_json(root / 'raw/queue_state.json', {})['models'][MODEL]
                    self.assertEqual(row['skipped_until'], (NOW + dt.timedelta(minutes=wait)).isoformat())
                else:
                    self.assertEqual(before, {p: p.read_bytes() for p in before})

    def test_access_denied_rejected(self):
        # v3 acceptance 3: reject every mismatch without modifying fixture files.
        for case in ('model', 'stage', 'stopped', 'missing_stopped', 'extra2', 'short',
                     'path', 'other_directory', 'tmp_directory', 'bad_json', 'missing',
                     'bad_hex', 'suffix', 'stop_file', 'sessions_dict', 'sessions_missing',
                     'tmp_stage'):
            with self.subTest(case=case), temporary_directory(dir=HERE) as tmpdir:
                root = Path(tmpdir)
                mp, tmp, rp = self.access_fixture(root)
                state_path = root / 'raw/queue_state.json'
                state = R.load_json(state_path, {})
                row = state['models'][MODEL]
                if case == 'model': row['needs_review']['reason'] = row['needs_review']['reason'].replace(MODEL, 'other-model')
                elif case == 'stage': row['stage'] = 'formal'
                elif case == 'stopped': R.save_json(mp, {'stopped': {}, 'sessions': []})
                elif case == 'missing_stopped': R.save_json(mp, {'sessions': []})
                elif case == 'extra2': rp.write_text('{}\n' * 3, encoding='utf-8')
                elif case == 'short': rp.write_text('', encoding='utf-8')
                elif case == 'path': row['needs_review']['reason'] = row['needs_review']['reason'].replace('run_meta_', 'results_')
                elif case == 'other_directory': row['needs_review']['reason'] = row['needs_review']['reason'].replace(str(root), str(root / 'elsewhere'))
                elif case == 'tmp_directory': row['needs_review']['reason'] = row['needs_review']['reason'].replace(str(tmp), str(root / 'elsewhere' / tmp.name))
                elif case == 'bad_json': mp.write_text('{', encoding='utf-8')
                elif case == 'missing': mp.unlink()
                elif case == 'bad_hex': row['needs_review']['reason'] = row['needs_review']['reason'].replace('a' * 32, 'A' * 32)
                elif case == 'suffix': row['needs_review']['reason'] += ' extra'
                elif case == 'stop_file': R.save_json(str(mp) + '.stop.json', {})
                elif case == 'sessions_dict': R.save_json(mp, {'stopped': None, 'sessions': {'one': {}}})
                elif case == 'sessions_missing': R.save_json(mp, {'stopped': None})
                elif case == 'tmp_stage': row['needs_review']['reason'] = row['needs_review']['reason'].replace(str(tmp), str(tmp).replace('_dev_', '_formal_'))
                R.save_json(state_path, state)
                before = {p: p.read_bytes() for p in root.rglob('*') if p.is_file()}
                self.assertEqual(self.run_clear(root), 0)
                self.assertEqual(before, {p: p.read_bytes() for p in before})
                self.assertFalse((root / ('raw/auto_clear_' + DAY)).exists())

    def test_backoff_and_daily_limit(self):
        # v3 acceptance 2/3: both kinds share eight reservations and backoff.
        self.assertEqual(A.DAILY_LIMIT, 8)
        for ordinal in range(1, 10):
            for minimum in (0, 90):
                with self.subTest(ordinal=ordinal, minimum=minimum), temporary_directory(dir=HERE) as tmp:
                    root = Path(tmp)
                    if ordinal % 2: self.fixture(root)
                    else: self.access_fixture(root)
                    audit = root / ('raw/auto_clear_' + DAY + '/audit.jsonl')
                    audit.parent.mkdir()
                    audit.write_text((json.dumps({'model': MODEL, 'kind': 'access_denied'}) + '\n') * (ordinal - 1), encoding='utf-8')
                    self.assertEqual(A.clear(root, DAY, minimum, NOW, log=lambda _: None), int(ordinal <= 8))
                    entries = [json.loads(line) for line in audit.read_text(encoding='utf-8').splitlines()]
                    if ordinal <= 8:
                        wait = max(minimum, 30 if ordinal == 1 else 60 if ordinal == 2 else 120)
                        self.assertEqual(entries[-1]['ordinal'], ordinal)
                        self.assertEqual(entries[-1]['wait_minutes'], wait)
                        row = R.load_json(root / 'raw/queue_state.json', {})['models'][MODEL]
                        self.assertEqual(dt.datetime.fromisoformat(row['skipped_until']), NOW + dt.timedelta(minutes=wait))
                    else: self.assertEqual(len(entries), ordinal - 1)

    def test_queue_lock_prevents_mutation(self):
        with temporary_directory(dir=HERE) as tmp:
            root = Path(tmp)
            self.fixture(root)
            with R.ModelLock(root / 'raw/queue.lock'):
                with self.assertRaises(R.Stop): self.run_clear(root)

    def test_previous_night_does_not_count(self):
        with temporary_directory(dir=HERE) as tmp:
            root = Path(tmp)
            self.fixture(root)
            audit = root / 'raw/auto_clear_2026-10-15/audit.jsonl'
            audit.parent.mkdir()
            audit.write_text((json.dumps({'model': MODEL}) + '\n') * 3, encoding='utf-8')
            self.assertEqual(self.run_clear(root), 1)

    def test_protected_fingerprint_inputs_unchanged(self):
        for name, digest in BASELINE.items():
            with self.subTest(file=name):
                self.assertEqual(hashlib.sha256((HERE / name).read_bytes()).hexdigest(), digest)


class ResultErrorRuleTests(unittest.TestCase):
    def test_result_error_rule_is_not_a_stderr_rule(self):
        names = {name for name, _ in A.STDERR_RULES}
        self.assertNotIn('authentication_result', names)
        import re
        self.assertTrue(any(re.search(p, 'authentication failed or timed out') for _, p in A.RESULT_ERROR_RULES))
        self.assertFalse(any(re.search(p, 'authentication failed or timed out') for _, p in A.STDERR_RULES))

    def test_rule_families_must_agree(self):
        ok = [("authentication failed or timed out", "Authentication required. Please visit the URL"),
              ("Eligibility check failed: x: TLS handshake timeout", "error: Eligibility check failed: x: TLS handshake timeout"),
              ("invalid model selection: model m is not recognized as a known model", "error: model m is not recognized as a known model")]
        for res, err in ok:
            self.assertIsNotNone(A.consistent_rule(res, err))
        bad = [("authentication failed or timed out", "Eligibility check failed: timeout"),
               ("authentication failed or timed out", "x is not recognized as a known model"),
               ("Eligibility check failed: EOF", "Authentication required"),
               ("authentication failed or timed out", "authentication failed or timed out")]
        for res, err in bad:
            with self.assertRaises(Exception):
                A.consistent_rule(res, err)


if __name__ == '__main__':
    unittest.main()
