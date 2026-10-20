import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import agy_subject as S
import run_agy as R
import test_run_agy as T
from workspace_temp import temporary_directory


SETTINGS = {'colorScheme': 'dark', 'permissions': {'allow': ['read', 'write'],
            'deny': ['network', 'shell']}, 'trustedWorkspaces': ['workspace']}


def changes():
    for field, value in (('colorScheme', 'light'), ('trustedWorkspaces', ['other'])):
        changed = copy.deepcopy(SETTINGS)
        changed[field] = value
        yield field, changed, False
    reordered = dict(reversed(list(SETTINGS.items())))
    reordered['permissions'] = dict(reversed(list(SETTINGS['permissions'].items())))
    yield 'key_order', reordered, False
    removed = copy.deepcopy(SETTINGS)
    del removed['colorScheme']
    yield 'removed_top_level_key', removed, True
    for field in ('allow', 'deny'):
        for action in ('add', 'remove', 'modify'):
            changed = copy.deepcopy(SETTINGS)
            values = changed['permissions'][field]
            if action == 'add':
                values.append('extra')
            elif action == 'remove':
                values.pop()
            else:
                values[0] = 'changed'
            yield field + '_' + action, changed, True


class SettingsTests(unittest.TestCase):
    def setUp(self):
        for guard in (patch.object(S, 'check_workroot', side_effect=lambda p: Path(p).resolve()),
                      patch.object(S.subprocess, 'run', return_value=type('Version', (), {
                          'returncode': 0, 'stdout': b'stub-version'})())):
            guard.start()
            self.addCleanup(guard.stop)

    def subject(self, root):
        settings = root / 'settings.json'
        settings.write_text(json.dumps(SETTINGS), encoding='utf-8')
        subject = S.AgySubject('test', root / 'raw', (sys.executable, '-X', 'utf8', '-B',
            str(Path('stub_agy.py').resolve())), settings, workroot=root / 'work')
        self.addCleanup(subject.close)
        return subject

    def write(self, subject, value):
        subject.settings.write_text(json.dumps(value, ensure_ascii=False), encoding='utf-8')

    # c review 10-17: non-standard JSON constants and unencodable strings must stop.
    def test_nonstandard_json_and_lone_surrogate_raise_snapshot_error(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            subject = self.subject(Path(tmp))
            for raw in ('{"colorScheme":"dark","permissions":{"allow":[NaN],"deny":[]},"trustedWorkspaces":[]}',
                        '{"colorScheme":"dark","permissions":{"allow":[Infinity],"deny":[]},"trustedWorkspaces":[]}',
                        '{"colorScheme":"dark","permissions":{"allow":["\\ud800"],"deny":[]},"trustedWorkspaces":[]}'):
                subject.settings.write_text(raw, encoding='utf-8')
                with self.assertRaises(S.SnapshotError):
                    subject.snapshot()

    # Brief 1/3: exact canonical hash, no settings values in snapshots.
    def test_snapshot_canonical_permissions_only(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            subject = self.subject(Path(tmp))
            value = {'deny': ['中文'], 'allow': ['read']}
            self.write(subject, dict(SETTINGS, permissions=value))
            snap = subject.snapshot()
            self.assertEqual(snap['permissions_sha256'], S.sha(json.dumps(value,
                sort_keys=True, ensure_ascii=False, separators=(',', ':')).encode('utf-8')))
            self.assertEqual(snap['settings_keys'], sorted(SETTINGS))
            self.assertEqual(set(snap), {'agy_version', 'permissions_sha256', 'settings_keys',
                'agent_sha256', 'reported_model', 'tools_sha256', 'permission_mode'})
            self.assertNotIn('中文', json.dumps(snap, ensure_ascii=False))

    # Brief 2/3: compare actual snapshots across a local stub call.
    def test_changes_during_call(self):
        for name, changed, stop in changes():
            with self.subTest(name=name), temporary_directory(dir=Path.cwd()) as tmp:
                subject = self.subject(Path(tmp))
                original = subject.snapshot
                def snapshot(model=None):
                    if model is not None:
                        self.write(subject, changed)
                    return original(model)
                with patch.object(subject, 'snapshot', side_effect=snapshot), \
                        patch.dict(S.os.environ, {'DNLI_STUB_MODE': 'ok'}):
                    result = subject.attempt('direct', 'x', name, 0)
                self.assertEqual(result['final']['state'], 'check_failed' if stop else 'ok')
                if stop:
                    self.assertEqual(result['final']['reasons'], ['environment_changed_during_call'])

    # Brief 2/3: both first reported model adoption and established baselines.
    def test_runner_checks_first_model_and_resume(self):
        runner = T.RunnerTests()
        for first_model in (True, False):
            for name, changed, stop in changes():
                with self.subTest(first_model=first_model, name=name), temporary_directory(dir=Path.cwd()) as tmp:
                    root = Path(tmp)
                    real = self.subject(root)
                    sub = T.Subject()
                    sub.snapshot = real.snapshot
                    if first_model:
                        attempt = sub.attempt
                        def change_in_attempt(*args):
                            self.write(real, changed)
                            return attempt(*args)
                        sub.attempt = change_in_attempt
                        units = (T.UNIT,)
                    else:
                        self.assertEqual(runner.execute(root, sub), 0)
                        self.write(real, changed)
                        units = (T.UNIT, ('k', 'prior', '-', 'multi', 'r0'))
                    self.assertEqual(runner.execute(root, sub, units), 3 if stop else 0)

    # Brief 1/3: reject unknown keys even in the initial snapshot; no fallback.
    def test_bad_settings_stop_persistently(self):
        cases = [('broken_json', '{', 'check_failed'),
                 ('bad_utf8', b'\xff', 'check_failed'),
                 ('missing', {}, 'check_failed'), ('root_list', [], 'check_failed'),
                 ('null', {'permissions': None}, 'check_failed'),
                 ('list', {'permissions': []}, 'check_failed'),
                 ('string', {'permissions': 'allow'}, 'check_failed'),
                 ('new_key', dict(SETTINGS, newToolSetting={}), 'environment_changed')]
        runner = T.RunnerTests()
        for name, value, reason in cases:
            for during_call in (False, True):
                with self.subTest(name=name, during_call=during_call), temporary_directory(dir=Path.cwd()) as tmp:
                    root = Path(tmp)
                    real = self.subject(root)
                    sub = T.Subject()
                    sub.snapshot = real.snapshot
                    def corrupt():
                        if isinstance(value, bytes):
                            real.settings.write_bytes(value)
                        elif name == 'broken_json':
                            real.settings.write_text(value, encoding='utf-8')
                        else:
                            self.write(real, value)
                    if during_call:
                        attempt = sub.attempt
                        def corrupt_in_attempt(*args):
                            corrupt()
                            return attempt(*args)
                        sub.attempt = corrupt_in_attempt
                    else:
                        corrupt()
                    self.assertEqual(runner.execute(root, sub), 3)
                    meta = R.load_json(root / (R.file_config(T.CFG) + '.json'), {})
                    self.assertIn(reason, meta['stopped']['reason'])
                    self.assertEqual(meta['sessions'], [])
                    self.assertTrue((root / (R.file_config(T.CFG) + '.json.stop.json')).exists())
                    calls = sub.calls
                    self.write(real, SETTINGS)
                    self.assertEqual(runner.execute(root, sub), 3)
                    self.assertEqual(sub.calls, calls)

    # Brief 1: a failed snapshot preserves previously closed checkpoints.
    def test_failed_snapshot_on_resume_preserves_previous_unit(self):
        runner = T.RunnerTests()
        for changed in ({}, dict(SETTINGS, newToolSetting=True)):
            with self.subTest(changed=changed), temporary_directory(dir=Path.cwd()) as tmp:
                root = Path(tmp)
                real = self.subject(root)
                sub = T.Subject()
                sub.snapshot = real.snapshot
                self.assertEqual(runner.execute(root, sub), 0)
                self.write(real, changed)
                self.assertEqual(runner.execute(root, sub,
                    (T.UNIT, ('k', 'prior', '-', 'multi', 'r0'))), 3)
                meta = R.load_json(root / (R.file_config(T.CFG) + '.json'), {})
                self.assertEqual(len(meta['sessions']), 1)
                self.assertFalse(meta['sessions'][0]['invalid'])
                self.assertEqual(sub.calls, 1)


if __name__ == '__main__':
    unittest.main()
