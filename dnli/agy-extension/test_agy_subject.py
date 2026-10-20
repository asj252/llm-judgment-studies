import json
import os
from pathlib import Path
import sys
from workspace_temp import temporary_directory
import unittest
from unittest.mock import patch
import agy_subject as S
import workspace_temp as W

class AdapterTests(unittest.TestCase):
    def setUp(self):
        # No writes outside dnli-agy during offline subprocess tests.
        guard = patch.object(S, "check_workroot", side_effect=lambda path: Path(path).resolve())
        guard.start()
        self.addCleanup(guard.stop)

    def judge(self, events, stderr='', returncode=0):
        for e in events:
            if e.get('event') == 'step_update' and isinstance(e.get('step_update'), dict):
                e['step_update'].setdefault('conversation_id', 'c')
                e['step_update'].setdefault('state', 'DONE')
        stdout = '\n'.join(json.dumps(e) for e in events)
        return S.final_inclusion({'stdout': stdout, 'stderr': stderr, 'returncode': returncode,
                                  'timed_out': False, 'events': S.parse_stream(stdout)})['state']

    def good(self, response='Probability: 50%', **fields):
        return [{'event': 'init', 'conversation_id': 'c', 'init': {
                    'model': 'm', 'cwd': str(Path.cwd()), 'tools': ['search_web'],
                    'permission_mode': 'request-review', 'agent': 'dnli-subject'}}, {'event': 'result',
                'result': dict({'conversation_id': 'c', 'status': 'SUCCESS',
                    'response': response, 'duration_seconds': 0.1, 'num_turns': 1,
                    'usage': {}}, **fields)}]

    def test_fail_closed_steps_and_denied_actions(self):
        for step in ({'step_type': 'tool_call', 'name': 'search_web'},
                     {'step_type': 'mystery'}, {'step_type': 'response', 'function': 'read_url'},
                     {'step_type': 'response', 'message': {'name': 'search_web'}},
                     {'step_type': 'response', 'other': {'tool': 'search_web'}}):
            self.assertEqual(self.judge(self.good()[:1] + [{'event': 'step_update', 'step_update': step}] + self.good()[1:]), 'contaminated')
        self.assertEqual(self.judge(self.good(denied_actions=['search_web'])), 'contaminated')
        self.assertEqual(self.judge(self.good()[:1] + [{'event': 'step_update', 'step_update': {
            'step_type': 'agent_response', 'text_delta': 'Thinking'}}] + self.good()[1:]), 'ok')

    def test_trusted_rate_diagnostics_and_integrity_priority(self):
        self.assertEqual(self.judge(self.good(usage={'input_tokens': 1429})), 'ok')
        self.assertEqual(self.judge(self.good('quota 429 rate limit')), 'ok')
        self.assertEqual(self.judge(self.good(), stderr='RESOURCE_EXHAUSTED 429'), 'ok')
        self.assertEqual(self.judge([{'event': 'unknown', 'message': 'quota exceeded'}]), 'check_failed')
        self.assertEqual(self.judge([{'event': 'unknown'}], stderr='429'), 'check_failed')
        self.assertEqual(self.judge([{'event': 'result', 'result': 'quota exceeded'}], stderr='429'), 'check_failed')
        self.assertEqual(self.judge(self.good() + self.good(), stderr='429'), 'check_failed')
        self.assertEqual(self.judge([], stderr='input_tokens=1429 quota'), 'call_error')
        self.assertEqual(self.judge([{'event': 'error', 'message': 'quota exceeded'}]), 'check_failed')
        self.assertEqual(self.judge([{'event': 'error', 'code': 429}]), 'check_failed')
        self.assertEqual(self.judge([], stderr='RESOURCE_EXHAUSTED 429', returncode=1), 'rate_limited')

    def test_recursive_step_schema_fail_closed(self):
        children = [
            {'step_type': 'tool_call', 'command': 'curl https://example.com', 'status': 'SUCCESS'},
            {'step_type': 'unknown_nested_step', 'text': 'Thinking'},
            {'type': 'unknown_nested_step'}, {'kind': 'tool_call'},
            {'message_type': 'unknown'}, {'content_type': 'unknown'},
            {'step_type': ['response']},
            {'step_type': 'response', 'unregistered': {'text': 'Thinking'}},
            {'unregistered': 'Thinking'},
        ]
        for child in children:
            for nested in (child, [child], {'content': [{'message': [child]}]}):
                with self.subTest(nested=nested):
                    event = {'event': 'step_update', 'step_update': {
                        'step_type': 'response', 'message': nested}}
                    self.assertEqual(self.judge(self.good()[:1] + [event] + self.good()[1:]), 'contaminated')
        safe = {'event': 'step_update', 'step_update': {
            'step_type': 'agent_response', 'text_delta': 'Thinking about search_web and quota.',
            'usage': {'input_tokens': 1, 'output_tokens': 2}}}
        self.assertEqual(self.judge(self.good()[:1] + [safe] + self.good()[1:]), 'ok')

    def test_recursive_tool_markers_across_all_events(self):
        markers = [{'command': 'curl https://example.com'}, {'url': 'https://example.com'},
                   {'query': 'example'}, {'function': 'read_url'}, {'action': 'execute'},
                   {'name': 'search_web'}, {'tool_call': {}}, {'denied_actions': ['read_url']},
                   {'arbitrary': 'search_web'}, {'step_type': 'mystery'}, {'type': 'tool_call'}]
        for marker in markers:
            for index in (0, 1):
                with self.subTest(marker=marker, index=index):
                    events = self.good()
                    target = events[0] if index == 0 else events[1]['result']
                    target['extra'] = [{'content': [marker]}]
                    self.assertEqual(self.judge(events), 'check_failed' if index == 0 else 'contaminated')
        # Pollution keeps priority over an otherwise credible rate-limit diagnostic.
        self.assertEqual(self.judge(self.good()[:1] + [{'event': 'error', 'details': [
            {'message': {'step_type': 'tool_call'}}]}], stderr='429'), 'contaminated')

    def test_rate_patterns_validation(self):
        for patterns in ([], '', '429', {}, [None], [''], [' '], [429]):
            with self.subTest(patterns=patterns), self.assertRaises(ValueError):
                S.validate_rate_patterns(patterns)
        with self.assertRaises(Exception):
            S.validate_rate_patterns(['['])

    def test_subprocess_matrix(self):
        with temporary_directory(dir=Path.cwd()) as root:
            root = Path(root)
            settings = root / 'settings.json'
            settings.write_text('{"permissions": {}}', encoding='utf-8')
            subject = S.AgySubject('test', root / 'raw', (sys.executable, '-X', 'utf8', '-B', str(Path('stub_agy.py').resolve())), settings, timeout=0.2, workroot=root / 'work')
            for mode, state in [('ok', 'ok'), ('search_web', 'contaminated'), ('read_url', 'contaminated'),
                                ('rate', 'rate_limited'), ('empty', 'call_error'), ('timeout', 'disconnect')]:
                with self.subTest(mode=mode), patch.dict(os.environ, {'DNLI_STUB_MODE': mode}):
                    r = subject.attempt('direct', 'Probability: NN%', mode, 1)
                    if mode == 'timeout' and r['meta'].get('kill_tree_error'):
                        state = 'check_failed'
                    self.assertEqual(r['final']['state'], state)
                    self.assertTrue(Path(r['meta']['raw_prefix'] + '.stream.jsonl').exists())
                    self.assertTrue(Path(r['meta']['raw_prefix'] + '.stderr.txt').exists())
            self.assertEqual(settings.read_text(encoding='utf-8'), '{"permissions": {}}')

    def test_cleanup_retry_preserves_output_and_admission(self):
        for failures, error_type in ((2, PermissionError), (10, PermissionError), (10, OSError)):
            with self.subTest(failures=failures, error_type=error_type), temporary_directory(dir=Path.cwd()) as tmp:
                root = Path(tmp)
                settings = root / 'settings.json'
                settings.write_text('{"permissions": {}}', encoding='utf-8')
                subject = S.AgySubject('test', root / 'output',
                    (sys.executable, '-X', 'utf8', '-B', str(Path('stub_agy.py').resolve())), settings, workroot=root / 'work')
                original = W.shutil.rmtree
                calls = []
                def remove(path):
                    calls.append(path)
                    record_path, = subject.rawdir.glob('*.attempt.json')
                    record = json.loads(record_path.read_text(encoding='utf-8'))
                    prefix = record['meta']['raw_prefix']
                    stdout = Path(prefix + '.stream.jsonl').read_bytes()
                    stderr = Path(prefix + '.stderr.txt').read_bytes()
                    self.assertIn(b'Probability: 50%', stdout)
                    self.assertEqual(record['meta']['raw_sha256'], {
                        '.stream.jsonl': S.sha(stdout), '.stderr.txt': S.sha(stderr)})
                    self.assertTrue(record['final']['include'])
                    if len(calls) <= failures:
                        raise error_type('simulated directory lock')
                    return original(path)
                with patch.dict(os.environ, {'DNLI_STUB_MODE': 'ok'}), \
                        patch.object(W.shutil, 'rmtree', side_effect=remove), \
                        patch.object(W.time, 'sleep') as sleep:
                    result = subject.attempt('direct', 'Probability: NN%', 'cleanup', 1)
                self.assertEqual(len(calls), min(failures + 1, 10))
                self.assertEqual([c.args[0] for c in sleep.call_args_list],
                                 [0.5 * i for i in range(1, len(calls))])
                self.assertLessEqual(sum(c.args[0] for c in sleep.call_args_list), 30)
                self.assertTrue(result['final']['include'])
                self.assertEqual(result['text'], 'Probability: 50%')
                error = result['meta']['cleanup_error']
                if failures == 10:
                    self.assertIn(str(calls[-1]), error)
                    self.assertTrue(calls[-1].exists())
                else:
                    self.assertIsNone(error)
                    self.assertFalse(calls[-1].exists())
                saved = json.loads(Path(result['meta']['raw_prefix'] + '.attempt.json').read_text(encoding='utf-8'))
                self.assertEqual(saved['meta'], result['meta'])

    def test_stale_cleanup_threshold(self):
        for count in (20, 21):
            with self.subTest(count=count), temporary_directory(dir=Path.cwd()) as tmp:
                root = Path(tmp)
                for i in range(count):
                    (root / f'dnli-agy-{i}').mkdir()
                (root / 'unrelated').mkdir()
                with patch.object(W.shutil, 'rmtree', side_effect=PermissionError('locked')) as remove, \
                        patch.object(W.time, 'sleep') as sleep:
                    errors = W.cleanup_old_directories(root)
                self.assertEqual(remove.call_count, count if count > 20 else 0)
                self.assertEqual(len(errors), remove.call_count)
                sleep.assert_not_called()
                self.assertTrue((root / 'unrelated').exists())

    def test_attempt_records_stale_cleanup_failure_and_continues(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            root = Path(tmp)
            settings = root / 'settings.json'
            settings.write_text('{"permissions": {}}', encoding='utf-8')
            subject = S.AgySubject('test', root / 'output',
                (sys.executable, '-X', 'utf8', '-B', str(Path('stub_agy.py').resolve())), settings, workroot=root / 'work')
            work = subject.session_dir
            old = [work / f'dnli-agy-old-{i}' for i in range(21)]
            for path in old:
                path.mkdir()
            original = W.shutil.rmtree
            seen = []
            def remove(path):
                if path in old:
                    self.assertFalse(list(subject.rawdir.glob('*.stream.jsonl')))
                    seen.append(path)
                    raise PermissionError('old directory locked')
                self.assertEqual(len(seen), 21)
                return original(path)
            with patch.dict(os.environ, {'DNLI_STUB_MODE': 'ok'}), \
                    patch.object(W.shutil, 'rmtree', side_effect=remove):
                result = subject.attempt('direct', 'Probability: NN%', 'stale', 1)
            self.assertTrue(result['final']['include'])
            self.assertIsNone(result['meta']['cleanup_error'])
            self.assertEqual(len(result['meta']['stale_cleanup_errors']), 21)
            for path in old:
                self.assertTrue(any(str(path) in e for e in result['meta']['stale_cleanup_errors']))
            saved = json.loads(Path(result['meta']['raw_prefix'] + '.attempt.json').read_text(encoding='utf-8'))
            self.assertEqual(saved['meta'], result['meta'])

    def test_cleanup_unsafe_path_still_raises(self):
        with temporary_directory(dir=Path.cwd()) as tmp:
            root = Path(tmp)
            for path in (root / 'wrong-prefix', root.parent / 'dnli-agy-outside'):
                with self.subTest(path=path), patch.object(W.shutil, 'rmtree') as remove:
                    with self.assertRaisesRegex(RuntimeError, 'outside expected parent'):
                        W.cleanup_directory(path, root)
                    remove.assert_not_called()

    def test_admission_integrity(self):
        def judge(events):
            stdout = '\n'.join(json.dumps(e) for e in events)
            return S.final_inclusion({'stdout': stdout, 'stderr': '', 'returncode': 0,
                                      'timed_out': False, 'events': S.parse_stream(stdout)})['state']
        init, good = self.good()
        self.assertEqual(judge([init, good, good]), 'check_failed')
        self.assertEqual(judge([good]), 'check_failed')
        self.assertEqual(judge([init, {'event': 'result', 'result': dict(good['result'], truncated=True)}]), 'check_failed')
        self.assertEqual(judge([init, {'event': 'mystery'}, good]), 'check_failed')

if __name__ == '__main__':
    unittest.main()
