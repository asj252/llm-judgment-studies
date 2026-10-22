"""Offline settings restoration tests; no user settings or model calls."""
import datetime as dt
from contextlib import closing, ExitStack
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import Mock, patch

import agy_night as N
import settings_restore as S


_NATIVE_REPLACE_FILE_W = S._replace_file_w


class RestoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        # Portable stand-in for the atomic Windows primitive. Race tests inject
        # the other writer immediately before this primitive captures bytes.
        def replace_file(settings, source, displaced):
            if not settings.exists():
                error = OSError('target missing')
                error.winerror = 2
                raise error
            displaced.write_bytes(settings.read_bytes())
            os.replace(source, settings)
        for patcher in (patch.object(S, '_WINDOWS', True),
                        patch.object(S, '_replace_file_w', side_effect=replace_file)):
            patcher.start()
            self.addCleanup(patcher.stop)
        self.raw = self.root / 'raw'
        self.settings = self.root / 'settings.json'
        self.baseline = self.root / 'descriptor.json'
        self.source = self.root / 'baseline.json'
        self.data = b'{"permissions":{"z":true,"a":[]}}\r\n'
        self.daytime = b'{ "permissions": {"allow":["daytime"]}, "other": 1 }\n'
        self.source.write_bytes(self.data)
        self.baseline.write_text(json.dumps(dict(path=self.source.name,
                                                sha256=S.sha(self.data))), encoding='utf-8')
        self.settings.write_bytes(self.daytime)
        self.now = dt.datetime.fromisoformat('2026-10-20T01:02:03+08:00')

    def restore(self):
        return S.restore_settings(self.settings, self.baseline, self.raw, self.now)

    def test_identical_is_noop_without_writes(self):
        self.settings.write_bytes(self.data)
        before = self.settings.stat()
        with patch.object(S, '_replace_settings') as replace:
            self.assertEqual(self.restore(), {'status': 'no-op'})
        replace.assert_not_called()
        self.assertEqual(self.settings.stat().st_mtime_ns, before.st_mtime_ns)
        self.assertFalse(self.raw.exists())

    def test_restore_preserves_bytes_and_audit(self):
        result = self.restore()
        self.assertEqual(result['status'], 'restored')
        audit = result['audit']
        backup = self.raw / 'settings_daytime/psych3_settings_daytime_20261020-010203.json'
        self.assertEqual(backup.read_bytes(), self.daytime)
        self.assertEqual(self.settings.read_bytes(), self.data)
        self.assertEqual(audit, dict(datetime=self.now.isoformat(), daytime_status='saved',
                                    daytime_path=str(backup), daytime_sha256=S.sha(self.daytime),
                                    daytime_permissions_sha256=S.sha(b'{"allow":["daytime"]}'),
                                    restored_sha256=S.sha(self.data),
                                    displaced_status='saved', displaced_differs=False,
                                    displaced_path=str(backup),
                                    displaced_sha256=S.sha(self.daytime),
                                    displaced_permissions_sha256=S.permissions_sha(self.daytime)))
        self.assertEqual(list(backup.parent.iterdir()), [backup])
        self.assertFalse(list(self.root.glob('*.bak')))
        self.assertEqual(self.source.read_bytes(), self.data)
        self.assertFalse(list(self.root.glob('settings.json.*.tmp')))

    def test_invalid_json_is_backed_up(self):
        self.settings.write_bytes(b'\xff{broken')
        result = self.restore()
        self.assertEqual(result['status'], 'restored')
        self.assertIsNone(result['audit']['daytime_permissions_sha256'])
        self.assertEqual(Path(result['audit']['daytime_path']).read_bytes(), b'\xff{broken')
        self.assertEqual(self.settings.read_bytes(), self.data)

    def test_last_window_writer_is_archived(self):
        other = b'{"permissions":{"allow":["B"]}}\r\n'
        primitive = S._replace_file_w.side_effect
        def concurrent(settings, temporary, displaced):
            settings.write_bytes(other)
            primitive(settings, temporary, displaced)
        with patch.object(S, '_replace_file_w', side_effect=concurrent):
            result = self.restore()
        self.assertEqual(result['status'], 'restored')
        audit = result['audit']
        self.assertTrue(audit['displaced_differs'])
        self.assertEqual(audit['displaced_sha256'], S.sha(other))
        self.assertEqual(audit['displaced_permissions_sha256'], S.permissions_sha(other))
        self.assertEqual(Path(audit['displaced_path']).read_bytes(), other)
        self.assertEqual(Path(audit['displaced_path']).parent, self.raw / 'settings_daytime')
        self.assertEqual(Path(audit['daytime_path']).read_bytes(), self.daytime)
        self.assertEqual(len(list((self.raw / 'settings_daytime').iterdir())), 2)
        self.assertEqual(self.settings.read_bytes(), self.data)
        self.assertFalse(list(self.root.glob('*.bak')))

    def test_primitive_transient_and_persistent_failure(self):
        for persistent in (False, True):
            with self.subTest(persistent=persistent):
                self.setUp()
                primitive = S._replace_file_w.side_effect
                def replace(*args):
                    if persistent or mocked.call_count == 1:
                        raise PermissionError('sharing violation')
                    return primitive(*args)
                with patch.object(S, '_replace_file_w', side_effect=replace) as mocked, \
                        patch.object(S.time, 'sleep') as sleep:
                    result = self.restore()
                self.assertEqual(result['status'], 'failed' if persistent else 'restored')
                self.assertEqual(mocked.call_count, 5 if persistent else 2)
                self.assertEqual(sleep.call_count, 4 if persistent else 1)
                self.assertEqual(self.settings.read_bytes(), self.daytime if persistent else self.data)
                self.assertFalse(list(self.root.glob('*.tmp')))
                self.assertFalse(list(self.root.glob('*.bak')))
                self.assertIn('displaced_sha256', result['audit'])

    def test_displaced_backup_cleanup_failure_is_audited(self):
        unlink = Path.unlink
        def cleanup(path, *args, **kwargs):
            if path.suffix == '.bak':
                raise PermissionError('backup cleanup blocked')
            return unlink(path, *args, **kwargs)
        with patch.object(Path, 'unlink', cleanup):
            result = self.restore()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('displaced backup cleanup', result['reason'])
        self.assertEqual(self.settings.read_bytes(), self.data)
        audit = result['audit']
        self.assertIn('backup cleanup blocked', audit['displaced_cleanup_reason'])
        self.assertEqual(Path(audit['displaced_backup_path']).read_bytes(), self.daytime)
        self.assertEqual(audit['displaced_sha256'], S.sha(self.daytime))
        self.assertEqual(Path(audit['displaced_path']).read_bytes(), self.daytime)
        # The next call sweeps the leftover .bak before its no-op check.
        again = self.restore()
        self.assertEqual(again['status'], 'no-op')
        self.assertEqual(len(again['audit']['recovered_displaced']), 1)
        self.assertFalse(list(self.root.glob('*.bak')))

    def test_displaced_archive_failure_keeps_atomic_backup(self):
        original = Path.open
        def opened(path, *args, **kwargs):
            if path.parent.name == 'settings_daytime' and 'psych3-displaced-' in path.name:
                raise OSError('archive blocked')
            return original(path, *args, **kwargs)
        with patch.object(Path, 'open', opened):
            result = self.restore()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('archive displaced settings', result['reason'])
        self.assertEqual(Path(result['audit']['displaced_path']).read_bytes(), self.daytime)
        self.assertEqual(result['audit']['displaced_sha256'], S.sha(self.daytime))
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_non_windows_portability_fallback(self):
        with patch.object(S, '_WINDOWS', False), \
                patch.object(S.os, 'replace', wraps=os.replace) as replace:
            result = self.restore()
        self.assertEqual(result['status'], 'restored')
        self.assertEqual(result['audit']['displaced_status'], 'unsupported')
        self.assertIsNone(result['audit']['displaced_sha256'])
        replace.assert_called_once()
        self.assertEqual(self.settings.read_bytes(), self.data)

    def test_native_wrapper_reports_last_error(self):
        primitive = Mock(return_value=0)
        kernel32 = Mock(ReplaceFileW=primitive)
        with patch.object(S.ctypes, 'WinDLL', return_value=kernel32, create=True), \
                patch.object(S.ctypes, 'get_last_error', return_value=32, create=True), \
                patch.object(S.ctypes, 'WinError', return_value=PermissionError('error 32'),
                             create=True) as winerror:
            with self.assertRaisesRegex(PermissionError, 'error 32'):
                _NATIVE_REPLACE_FILE_W(self.settings, self.source, self.root / 'backup.bak')
        primitive.assert_called_once_with(str(self.settings), str(self.source),
                                          str(self.root / 'backup.bak'), 0, None, None)
        winerror.assert_called_once_with(32)

    @unittest.skipUnless(os.name == 'nt', 'requires Windows ReplaceFileW')
    def test_native_windows_replace_file_w(self):
        # All paths are in this test's tempfile directory, including the target.
        with patch.object(S, '_replace_file_w', _NATIVE_REPLACE_FILE_W):
            result = self.restore()
        self.assertEqual(result['status'], 'restored', result)
        self.assertEqual(self.settings.read_bytes(), self.data)
        self.assertFalse(result['audit']['displaced_differs'])
        self.assertEqual(result['audit']['displaced_sha256'], S.sha(self.daytime))
        self.assertEqual(Path(result['audit']['displaced_path']).read_bytes(), self.daytime)
        self.assertFalse(list(self.root.glob('*.bak')))

    def test_missing_settings(self):
        self.settings.unlink()
        result = self.restore()
        self.assertEqual(result['status'], 'restored')
        self.assertEqual(result['audit']['daytime_status'], 'missing')
        self.assertEqual(result['audit']['displaced_status'], 'missing')
        self.assertIsNone(result['audit']['displaced_sha256'])
        self.assertIsNone(result['audit']['daytime_path'])
        self.assertIsNone(result['audit']['daytime_sha256'])
        self.assertIsNone(result['audit']['daytime_permissions_sha256'])
        self.assertFalse(self.raw.exists())
        self.assertEqual(self.settings.read_bytes(), self.data)

    def test_missing_target_created_at_atomic_move_is_preserved(self):
        self.settings.unlink()
        other = b'{"permissions":{"allow":["B"]}}'
        rename = os.rename
        def raced(source, target):
            target.write_bytes(other)
            if os.name != 'nt':
                raise FileExistsError('Windows rename target exists')
            return rename(source, target)
        with patch.object(S.os, 'rename', side_effect=raced) as move, \
                patch.object(S.time, 'sleep') as sleep:
            result = self.restore()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('settings created during restore', result['reason'])
        move.assert_called_once()
        sleep.assert_not_called()
        self.assertEqual(self.settings.read_bytes(), other)
        self.assertFalse(list(self.root.glob('*.tmp')))
        self.now += dt.timedelta(minutes=30)
        result = self.restore()
        self.assertEqual(result['status'], 'restored')
        self.assertEqual(Path(result['audit']['daytime_path']).read_bytes(), other)

    def test_portable_missing_target_link_is_no_clobber(self):
        self.settings.unlink()
        link = os.link
        def raced(source, target):
            target.write_bytes(b'B')
            return link(source, target)
        with patch.object(S, '_WINDOWS', False), \
                patch.object(S.os, 'link', side_effect=raced):
            result = self.restore()
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(self.settings.read_bytes(), b'B')
        self.assertFalse(list(self.root.glob('*.tmp')))

    def test_1177_fails_immediately_and_next_call_recovers_then_restores(self):
        def partial(settings, temporary, displaced):
            os.rename(settings, displaced)
            error = OSError('replacement move failed')
            error.winerror = 1177
            raise error
        with patch.object(S, '_replace_file_w', side_effect=partial) as replace, \
                patch.object(S.time, 'sleep') as sleep:
            result = self.restore()
        self.assertEqual(result['status'], 'failed')
        replace.assert_called_once()
        sleep.assert_not_called()
        displaced = Path(result['audit']['displaced_backup_path'])
        self.assertIn('1177', result['reason'])
        self.assertIn(str(displaced), result['reason'])
        self.assertEqual(displaced.read_bytes(), self.daytime)
        self.assertFalse(self.settings.exists())
        self.assertFalse(list(self.root.glob('*.tmp')))
        self.now += dt.timedelta(minutes=30)
        result = self.restore()
        self.assertEqual(result['status'], 'restored')
        recovered = result['audit']['recovered_displaced'][0]
        self.assertEqual(Path(recovered['path']).read_bytes(), self.daytime)
        self.assertEqual(recovered['sha256'], S.sha(self.daytime))
        self.assertEqual(recovered['permissions_sha256'], S.permissions_sha(self.daytime))
        self.assertFalse(displaced.exists())
        self.assertEqual(self.settings.read_bytes(), self.data)

    def test_archive_failure_is_recovered_before_noop_and_queue_audits_it(self):
        with patch.object(S, '_archive_displaced', side_effect=OSError('archive blocked')):
            first = self.restore()
        self.assertEqual(first['status'], 'failed')
        displaced = Path(first['audit']['displaced_backup_path'])
        self.assertEqual(displaced.read_bytes(), self.daytime)
        self.assertEqual(self.settings.read_bytes(), self.data)
        self.now += dt.timedelta(minutes=30)
        with patch.object(S, '_replace_settings') as replace:
            state = self.queue().run()
        replace.assert_not_called()
        self.assertEqual(state['settings_restore_failures'], [])
        recovered = state['settings_restores'][0]['recovered_displaced'][0]
        self.assertEqual(Path(recovered['path']).read_bytes(), self.daytime)
        self.assertFalse(displaced.exists())
        self.assertEqual(state, N.read(self.raw / 'psych3_agy_queue.json'))

    def test_recovery_existing_archive_identical_or_different(self):
        self.settings.write_bytes(self.data)
        displaced = self.root / 'settings.json.psych3-displaced-old.bak'
        displaced.write_bytes(self.daytime)
        archive = self.raw / 'settings_daytime' / (displaced.stem + '.json')
        archive.parent.mkdir(parents=True)
        archive.write_bytes(b'different')
        result = self.restore()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('archive differs', result['reason'])
        self.assertTrue(displaced.exists())
        archive.write_bytes(self.daytime)
        result = self.restore()
        self.assertEqual(result['status'], 'no-op')
        self.assertEqual(result['audit']['recovered_displaced'][0]['path'], str(archive))
        self.assertEqual(archive.read_bytes(), self.daytime)
        self.assertFalse(displaced.exists())

    def test_recovery_failures_never_spawn(self):
        for mode in ('scan', 'read', 'write', 'fsync', 'unlink'):
            with self.subTest(mode=mode), ExitStack() as stack:
                self.setUp()
                self.settings.write_bytes(self.data)
                displaced = self.root / 'settings.json.psych3-displaced-old.bak'
                displaced.write_bytes(self.daytime)
                (self.root / 'legacy.json').write_text(json.dumps(
                    {'models': {m: {'stage': 'done'} for m in N.MODELS}}), encoding='utf-8')
                if mode == 'scan':
                    stack.enter_context(patch.object(S, 'os', Mock(wraps=S.os)))
                    stack.enter_context(patch.object(S.os, 'scandir', side_effect=OSError('recovery scan blocked')))
                elif mode in ('read', 'write'):
                    original = Path.open
                    def opened(path, *args, **kwargs):
                        if (path == displaced if mode == 'read' else
                                path.parent.name == 'settings_daytime'):
                            raise OSError('recovery blocked ' + mode)
                        return original(path, *args, **kwargs)
                    stack.enter_context(patch.object(Path, 'open', opened))
                elif mode == 'fsync':
                    stack.enter_context(patch.object(S, 'os', Mock(wraps=S.os)))
                    stack.enter_context(patch.object(S.os, 'fsync', side_effect=OSError('recovery fsync blocked')))
                else:
                    original = Path.unlink
                    def unlink(path, *args, **kwargs):
                        if path == displaced:
                            raise OSError('recovery unlink blocked')
                        return original(path, *args, **kwargs)
                    stack.enter_context(patch.object(Path, 'unlink', unlink))
                spawn = Mock()
                state = self.queue(spawn=spawn).run()
                spawn.assert_not_called()
                self.assertEqual(state['settings_restores'], [])
                failure = state['settings_restore_failures'][0]
                self.assertIn('recover displaced settings', failure['reason'])
                if mode != 'scan':
                    self.assertIn(str(displaced), failure['reason'])
                self.assertTrue(displaced.exists())
                self.assertEqual(self.settings.read_bytes(), self.data)

    def test_recovery_only_matches_displaced_prefix_and_follows_baseline_check(self):
        displaced = self.root / 'settings.json.psych3-displaced-old.bak'
        displaced.write_bytes(self.daytime)
        unrelated = self.root / 'other.json.psych3-displaced-old.bak'
        unrelated.write_bytes(b'untouched')
        self.source.write_bytes(b'wrong baseline')
        self.assertEqual(self.restore()['status'], 'failed')
        self.assertTrue(displaced.exists())
        self.assertFalse(self.raw.exists())
        self.source.write_bytes(self.data)
        self.settings.write_bytes(self.data)
        self.assertEqual(self.restore()['status'], 'no-op')
        self.assertTrue(unrelated.exists())
        self.assertFalse(displaced.exists())

    def test_invalid_baseline_never_touches_settings(self):
        for kind in ('mismatch', 'missing-source', 'missing-descriptor', 'broken-descriptor'):
            with self.subTest(kind=kind):
                self.setUp()
                if kind == 'mismatch':
                    self.source.write_bytes(b'{}')
                elif kind == 'missing-source':
                    self.source.unlink()
                elif kind == 'missing-descriptor':
                    self.baseline.unlink()
                else:
                    self.baseline.write_bytes(b'{broken')
                before = self.settings.stat().st_mtime_ns
                self.assertEqual(self.restore()['status'], 'failed')
                self.assertEqual(self.settings.read_bytes(), self.daytime)
                self.assertEqual(self.settings.stat().st_mtime_ns, before)
                self.assertFalse(self.raw.exists())

    def test_replace_failure_retries_and_cleans_temporary(self):
        with patch.object(S, '_replace_settings', side_effect=PermissionError('locked')) as replace, \
                patch.object(S.time, 'sleep') as sleep:
            result = self.restore()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('replace settings', result['reason'])
        self.assertEqual(replace.call_count, 5)
        self.assertEqual(sleep.call_count, 4)
        self.assertEqual(self.settings.read_bytes(), self.daytime)
        self.assertFalse(list(self.root.glob('settings.json.*.tmp')))
        self.assertEqual(Path(result['audit']['daytime_path']).read_bytes(), self.daytime)

    def test_transient_replace_error_recovers_in_same_directory(self):
        original = S._replace_settings
        def replace(source, target, displaced):
            self.assertEqual(Path(source).parent, self.settings.parent)
            if replace_mock.call_count == 1:
                raise OSError('busy')
            return original(source, target, displaced)
        with patch.object(S, '_replace_settings', side_effect=replace) as replace_mock, \
                patch.object(S.time, 'sleep'):
            self.assertEqual(self.restore()['status'], 'restored')
        self.assertEqual(replace_mock.call_count, 2)

    def test_backup_collision_fails_without_overwrite(self):
        result = self.restore()
        self.settings.write_bytes(b'new daytime')
        self.assertEqual(self.restore()['status'], 'failed')
        self.assertEqual(self.settings.read_bytes(), b'new daytime')
        self.assertEqual(Path(result['audit']['daytime_path']).read_bytes(), self.daytime)

    def test_post_replace_verification_failure(self):
        original = S._replace_settings
        def corrupt(source, target, displaced):
            status = original(source, target, displaced)
            Path(target).write_bytes(b'changed by another process')
            return status
        with patch.object(S, '_replace_settings', side_effect=corrupt):
            result = self.restore()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('verify settings', result['reason'])

    def test_concurrent_changes_stop_retry_including_missing(self):
        for initial in (self.daytime, None):
            with self.subTest(initial=initial):
                self.setUp()
                if initial is None:
                    self.settings.unlink()
                def replace(*args):
                    self.settings.write_bytes(b'concurrent daytime edit')
                    raise PermissionError('busy')
                with patch.object(S, '_replace_settings', side_effect=replace) as mocked, \
                        patch.object(S.time, 'sleep'):
                    result = self.restore()
                self.assertEqual(result['status'], 'failed')
                self.assertEqual(result['reason'], 'settings changed during restore')
                self.assertEqual(mocked.call_count, 1)
                self.assertEqual(self.settings.read_bytes(), b'concurrent daytime edit')
                self.assertFalse(list(self.root.glob('settings.json.*.tmp')))
                if initial is not None:
                    self.assertEqual(Path(result['audit']['daytime_path']).read_bytes(), initial)

    def test_admission_closes_before_backup_or_replace(self):
        for checks in ([False], [True, False]):
            with self.subTest(checks=checks):
                self.setUp()
                with patch.object(S, '_replace_settings') as replace:
                    result = S.restore_settings(self.settings, self.baseline, self.raw,
                                                self.now, may_write=Mock(side_effect=checks))
                self.assertEqual(result['status'], 'failed')
                self.assertEqual(result['reason'], 'admission closed')
                replace.assert_not_called()
                self.assertEqual(self.settings.read_bytes(), self.daytime)
                self.assertFalse(list(self.root.glob('settings.json.*.tmp')))
                self.assertEqual(self.raw.exists(), len(checks) == 2)

    def test_input_recursion_is_audited_and_interrupt_propagates(self):
        with patch.object(S.json, 'loads', side_effect=RecursionError('deep input')):
            result = self.restore()
        self.assertEqual(result['status'], 'failed')
        self.assertIn('deep input', result['reason'])
        with patch.object(S.json, 'loads', side_effect=RecursionError):
            self.assertIsNone(S.permissions_sha(b'{}'))
        with patch.object(S, '_replace_settings', side_effect=KeyboardInterrupt), \
                patch.object(S.Path, 'unlink', side_effect=OSError('cleanup blocked')):
            with self.assertRaises(KeyboardInterrupt):
                self.restore()

    def test_io_failures_and_queue_never_spawn(self):
        for mode in ('backup-write', 'backup-fsync', 'temporary-write',
                     'temporary-fsync', 'cleanup', 'race', 'recursion'):
            for queue in (False, True):
                with self.subTest(mode=mode, queue=queue), ExitStack() as stack:
                    self.setUp()
                    # Keep restore I/O faults out of Queue's audit persistence.
                    stack.enter_context(patch.object(S, 'os', Mock(wraps=S.os)))
                    spawn = Mock()
                    # Make spawn reachable if restoration accidentally succeeds.
                    (self.root / 'legacy.json').write_text(json.dumps(
                        {'models': {m: {'stage': 'done'} for m in N.MODELS}}), encoding='utf-8')
                    if mode == 'backup-write':
                        original = Path.open
                        def opened(path, *args, **kwargs):
                            stream = original(path, *args, **kwargs)
                            if path.parent.name == 'settings_daytime':
                                proxy = Mock(wraps=stream)
                                proxy.write.side_effect = OSError('backup write blocked')
                                # Use a real context manager so failure closes the file.
                                return closing(proxy)
                            return stream
                        stack.enter_context(patch.object(Path, 'open', opened))
                    elif mode in ('backup-fsync', 'temporary-fsync'):
                        effects = [OSError('backup fsync blocked')] if mode == 'backup-fsync' else [None, OSError('temporary fsync blocked')]
                        stack.enter_context(patch.object(S.os, 'fsync', side_effect=effects))
                    elif mode == 'temporary-write':
                        original = S.tempfile.NamedTemporaryFile
                        def temporary(*args, **kwargs):
                            stream = original(*args, **kwargs)
                            proxy = Mock(wraps=stream)
                            proxy.name = stream.name
                            proxy.write.side_effect = OSError('temporary write blocked')
                            return closing(proxy)
                        stack.enter_context(patch.object(S.tempfile, 'NamedTemporaryFile', temporary))
                    elif mode == 'cleanup':
                        stack.enter_context(patch.object(S, '_replace_settings', side_effect=PermissionError('replace blocked')))
                        stack.enter_context(patch.object(Path, 'unlink', side_effect=OSError('unlink blocked')))
                    elif mode == 'race':
                        def replace(*args):
                            self.settings.write_bytes(b'concurrent edit')
                            raise PermissionError('busy')
                        stack.enter_context(patch.object(S, '_replace_settings', side_effect=replace))
                    else:
                        stack.enter_context(patch.object(S, 'sha', side_effect=RecursionError('deep input')))
                    stack.enter_context(patch.object(S.time, 'sleep'))
                    if queue:
                        state = self.queue(spawn=spawn).run()
                        self.assertEqual(len(state['settings_restore_failures']), 1)
                        result = dict(status='failed', **state['settings_restore_failures'][0])
                    else:
                        result = self.restore()
                    self.assertEqual(result['status'], 'failed')
                    spawn.assert_not_called()
                    self.assertEqual(self.settings.read_bytes(), b'concurrent edit' if mode == 'race' else self.daytime)
                    if mode == 'cleanup':
                        self.assertIn('replace blocked', result['reason'])
                        self.assertIn('temporary cleanup: unlink blocked', result['reason'])
                    else:
                        self.assertFalse(list(self.root.glob('settings.json.*.tmp')))
                    if mode in ('temporary-write', 'temporary-fsync', 'cleanup', 'race'):
                        self.assertEqual(Path(result['audit']['daytime_path']).read_bytes(), self.daytime)

    def test_queue_crosses_deadline_during_retry(self):
        self.now = self.now.replace(hour=7, minute=44, second=59)
        (self.root / 'legacy.json').write_text(json.dumps(
            {'models': {m: {'stage': 'done'} for m in N.MODELS}}), encoding='utf-8')
        spawn = Mock()
        def advance(*args):
            self.now += dt.timedelta(seconds=1)
        with patch.object(S, 'os', Mock(wraps=S.os)), \
                patch.object(S, '_replace_settings', side_effect=PermissionError('busy')) as replace, \
                patch.object(S.time, 'sleep', side_effect=advance):
            state = self.queue(spawn=spawn).run()
        self.assertEqual(replace.call_count, 1)
        self.assertEqual(state['settings_restore_failures'][0]['reason'], 'admission closed')
        spawn.assert_not_called()
        self.assertEqual(self.settings.read_bytes(), self.daytime)
        self.assertFalse(list(self.root.glob('settings.json.*.tmp')))

    def test_queue_save_failure_never_spawns(self):
        for status in ('restored', 'failed', 'no-op'):
            with self.subTest(status=status):
                self.setUp()
                if status == 'failed':
                    self.source.unlink()
                elif status == 'no-op':
                    self.settings.write_bytes(self.data)
                (self.root / 'legacy.json').write_text(json.dumps(
                    {'models': {m: {'stage': 'done'} for m in N.MODELS}}), encoding='utf-8')
                spawn = Mock()
                q = self.queue(spawn=spawn)
                with patch.object(q, 'save', side_effect=OSError('queue save blocked')):
                    with self.assertRaisesRegex(OSError, 'queue save blocked'):
                        q.run()
                spawn.assert_not_called()

    def queue(self, spawn=None, clock=None):
        return N.Queue(self.root, clock=clock or (lambda: self.now), settings=self.settings,
                       baseline=self.baseline, dnli_state=self.root / 'legacy.json', spawn=spawn)

    def test_queue_restore_snapshot_save_before_spawn(self):
        (self.root / 'legacy.json').write_text(json.dumps(
            {'models': {m: {'stage': 'done'} for m in N.MODELS}}), encoding='utf-8')
        def spawn(*args):
            self.assertEqual(self.settings.read_bytes(), self.data)
            snapshot = self.raw / 'psych3_settings_snapshot_2026-10-20.json'
            self.assertEqual(snapshot.read_bytes(), self.daytime)
            state = N.read(self.raw / 'psych3_agy_queue.json')
            self.assertEqual(len(state['settings_restores']), 1)
            self.assertEqual(state['settings_restore_failures'], [])
            raise RuntimeError('offline launch sentinel')
        spawn_mock = Mock(side_effect=spawn)
        self.queue(spawn=spawn_mock).run()
        self.assertEqual(spawn_mock.call_count, 4)

    def test_queue_failure_never_spawns_and_persists_reason(self):
        self.source.unlink()
        spawn = Mock()
        state = self.queue(spawn=spawn).run()
        spawn.assert_not_called()
        self.assertEqual(state['settings_restores'], [])
        self.assertEqual(len(state['settings_restore_failures']), 1)
        self.assertEqual(state, N.read(self.raw / 'psych3_agy_queue.json'))
        self.assertIn('baseline', state['settings_restore_failures'][0]['reason'])
        self.assertEqual(state['settings_restore_failures'][0]['datetime'], self.now.isoformat())

    def test_queue_closed_admission_never_restores(self):
        for time in ('07:45:00', '08:00:00'):
            with self.subTest(time=time), patch.object(N, 'restore_settings') as restore:
                clock = lambda: dt.datetime.fromisoformat('2026-10-20T' + time + '+08:00')
                spawn = Mock()
                self.queue(spawn=spawn, clock=clock).run()
                restore.assert_not_called()
                spawn.assert_not_called()
        self.assertEqual(self.settings.read_bytes(), self.daytime)

    def test_queue_handles_invalid_or_missing_settings_and_noop(self):
        for content in (b'{broken', None, self.data):
            with self.subTest(content=content):
                self.setUp()
                if content is None:
                    self.settings.unlink()
                else:
                    self.settings.write_bytes(content)
                state = self.queue().run()  # Missing legacy queue prevents launches.
                self.assertEqual(self.settings.read_bytes(), self.data)
                self.assertEqual(len(state['settings_restores']), int(content != self.data))
                self.assertEqual(state['settings_restore_failures'], [])

    def test_queue_old_state_defaults_and_invalid_audit_lists(self):
        q = self.queue()
        q.path.parent.mkdir(parents=True)
        old = dict(version=1, models={}, quota_events=[], gemini_quota_pairs=[])
        N.R.save_json(q.path, old)
        q.load()
        self.assertEqual(q.state['settings_restores'], [])
        self.assertEqual(q.state['settings_restore_failures'], [])
        for key in ('settings_restores', 'settings_restore_failures'):
            N.R.save_json(q.path, dict(old, **{key: {}}))
            before = q.path.read_bytes()
            with self.assertRaises(ValueError):
                q.run()
            self.assertEqual(q.path.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
