"""New agy adapter; admission follows dnli/codex_subject.py concepts.
Stream schema/payload based on tools/agy_dispatch.py, without its resume/tools.
Only result.response counts as final; never admit partial text_delta.
"""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
from workspace_temp import temporary_directory, cleanup_old_directories, cleanup_directory
import logging
import time
import uuid
import shutil
import re
from configs import (RATE_PATTERNS, SAFE_STEP_TYPES, SAFE_STEP_FIELDS, SAFE_USAGE_FIELDS,
                     STEP_TYPE_FIELDS, SAFE_NESTED_FIELDS, TOOL_FIELDS,
                     KNOWN_TOOL_NAMES, validate_rate_patterns)

DEFAULT_SETTINGS = Path.home() / '.gemini' / 'antigravity-cli' / 'settings.json'
AGENT_FILE = Path(__file__).resolve().parent / 'agent' / 'dnli-subject.md'
AGENT_NAME = 'dnli-subject'

class SnapshotError(RuntimeError):
    """Invalid or newly unsupported settings must stop the run persistently."""

def check_workroot(path):
    path = Path(path).resolve()
    if any((parent / '.git').exists() for parent in (path, *path.parents)):
        raise RuntimeError('agy work directory must be outside any git repository')
    return path

def validate_model_name(model):
    if (not isinstance(model, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]*', model)
            or model.endswith('.') or re.fullmatch(r'(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])',
                                                   model.split('.')[0], re.IGNORECASE)):
        raise ValueError('unsafe model name for agy work directory')
    return model

DISCONNECT_PATTERNS = ('disconnected', 'connection reset', 'connection aborted', 'connection closed', 'network error')

def sha(data):
    return hashlib.sha256(data).hexdigest()

def parse_stream(stdout, requested_model=None, expected_cwd=None, expected_agent=AGENT_NAME):
    out = {'results': [], 'tools': [], 'bad_lines': [], 'unknown': [], 'errors': [], 'models': [], 'versions': [], 'usage': [],
           'integrity': [], 'tools_sha256': None, 'permission_mode': None}
    conversation_ids = []
    init_count = 0
    def check_ids(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'conversation_id':
                    if not isinstance(child, str) or not child:
                        out['integrity'].append('invalid_conversation_id')
                    else:
                        conversation_ids.append(child)
                check_ids(child)
        elif isinstance(value, list):
            for child in value:
                check_ids(child)

    def check_states(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'state' and child not in ('ACTIVE', 'DONE'):
                    out['integrity'].append('unknown_state')
                check_states(child)
        elif isinstance(value, list):
            for child in value:
                check_states(child)

    def unsafe_tree(value, in_step=False):
        if isinstance(value, dict):
            typed = any(k.lower() in STEP_TYPE_FIELDS for k in value)
            in_step = in_step or typed
            for key, child in value.items():
                field = key.lower()
                if field == 'usage':
                    if not isinstance(child, dict) or any(
                            k not in SAFE_USAGE_FIELDS or type(v) is not int
                            for k, v in child.items()):
                        return True
                    continue
                if ('tool' in field or field in TOOL_FIELDS or
                        (field == 'denied_actions' and bool(child))):
                    return True
                if field in STEP_TYPE_FIELDS and (
                        not isinstance(child, str) or child not in SAFE_STEP_TYPES):
                    return True
                if in_step and key not in SAFE_NESTED_FIELDS:
                    return True
                # Exact field values only: answer prose is not a tool declaration.
                if isinstance(child, str) and child.lower() in KNOWN_TOOL_NAMES:
                    return True
                if unsafe_tree(child, in_step):
                    return True
        elif isinstance(value, list):
            return any(unsafe_tree(child, in_step) for child in value)
        return False

    def metadata(obj):
        for k, v in obj.items():
            if k in ('model_version', 'version'):
                out['versions'].append(v)
            if k in ('usage', 'token_usage'):
                out['usage'].append(v)
            if isinstance(v, dict):
                metadata(v)
    for line_number, line in enumerate(stdout.splitlines()):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            if not isinstance(obj, dict):
                raise ValueError('not object')
        except ValueError:
            out['bad_lines'].append(line)
            continue
        metadata(obj)
        check_ids(obj)
        event = obj.get('event')
        allowed = {'init': {'event', 'conversation_id', 'init'},
                   'step_update': {'event', 'step_update'}, 'result': {'event', 'result'}}
        if isinstance(event, str) and event in allowed and set(obj) != allowed[event]:
            out['integrity'].append('event_top_level_schema')
        if event != 'init' and 'init' in obj:
            out['integrity'].append('unexpected_init_field')
        if event == 'error' and any(k in obj for k in ('init', 'step_update', 'result')):
            out['integrity'].append('error_payload_field')
        if event == 'init':
            init_count += 1
            if line_number != 0:
                out['integrity'].append('init_not_first')
            if unsafe_tree({k: v for k, v in obj.items() if k != 'init'}):
                out['tools'].append(obj)
            init = obj.get('init')
            init_keys = {'model', 'cwd', 'tools', 'permission_mode'}
            if expected_agent is not None:
                init_keys.add('agent')
            if not isinstance(init, dict) or set(init) != init_keys:
                out['integrity'].append('init_schema')
                continue
            if isinstance(init.get('model'), str):
                out['models'].append(init['model'])
            if not isinstance(obj.get('conversation_id'), str) or not obj['conversation_id']:
                out['integrity'].append('init_conversation_id_missing')
            if expected_agent is not None and init['agent'] != expected_agent:
                out['integrity'].append('reported_agent_mismatch')
            if not isinstance(init['model'], str) or (requested_model is not None and init['model'] != requested_model):
                out['integrity'].append('reported_model_mismatch')
            if not isinstance(init['cwd'], str) or (expected_cwd is not None and
                    os.path.normcase(os.path.abspath(init['cwd'])) != os.path.normcase(os.path.abspath(expected_cwd))):
                out['integrity'].append('reported_cwd_mismatch')
            if not isinstance(init['tools'], list) or any(not isinstance(t, str) for t in init['tools']):
                out['integrity'].append('init_tools_schema')
            else:
                out['tools_sha256'] = sha(json.dumps(sorted(init['tools']), ensure_ascii=False,
                                                    separators=(',', ':')).encode('utf-8'))
            if not isinstance(init['permission_mode'], str):
                out['integrity'].append('init_permission_mode_schema')
            out['permission_mode'] = init['permission_mode']
            # Available tools are declarations, never evidence of tool use.
            continue
        if event == 'error':
            out['errors'].append(obj)
        step = obj.get('step_update')
        if event == 'step_update':
            check_states(step)
            if isinstance(step, dict) and step.get('state') not in ('ACTIVE', 'DONE'):
                out['integrity'].append('unknown_state')
            if isinstance(step, dict) and not isinstance(step.get('conversation_id'), str):
                out['integrity'].append('step_conversation_id_missing')
        unsafe_step = event == 'step_update' and (
            not isinstance(step, dict) or step.get('step_type') not in SAFE_STEP_TYPES or
            any(k not in SAFE_STEP_FIELDS for k in step) or
            unsafe_tree(step, in_step=True))
        if unsafe_step or unsafe_tree(obj) or event in ('tool', 'tool_call', 'tool_use'):
            out['tools'].append(obj)
        if event == 'result':
            result = obj.get('result')
            if not isinstance(result, dict):
                out['bad_lines'].append(line)
            else:
                if set(result) != {'conversation_id', 'status', 'response', 'duration_seconds', 'num_turns', 'usage'}:
                    out['integrity'].append('result_schema')
                if type(result.get('num_turns')) is not int or result['num_turns'] != 1:
                    out['integrity'].append('result_num_turns')
                if not isinstance(result.get('conversation_id'), str):
                    out['integrity'].append('result_conversation_id_missing')
                out['results'].append(result)
        elif event not in ('init', 'step_update', 'error', 'tool', 'tool_call', 'tool_use'):
            out['unknown'].append(event)
    if stdout.strip() and init_count == 0:
        out['integrity'].append('init_missing')
    if init_count > 1:
        out['integrity'].append('multiple_init')
    if len(set(conversation_ids)) > 1:
        out['integrity'].append('conversation_id_mismatch')
    return out

def final_inclusion(r, rate_patterns=RATE_PATTERNS):
    ev = r['events']
    rate_patterns = validate_rate_patterns(rate_patterns)
    # Only stderr and error-event diagnostic text are trusted; never scan tokens/body.
    def error_text(obj):
        parts = []
        for key in ('message', 'error', 'code', 'status', 'detail', 'details'):
            value = obj.get(key)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, dict):
                parts.append(error_text(value))
            elif key == 'code' and value == 429:
                parts.append('429')
        return '\n'.join(parts)
    diagnostic = r['stderr'] + '\n' + '\n'.join(error_text(e) for e in ev['errors'])
    def verdict(state, reasons):
        return {'state': state, 'reasons': reasons, 'include': state == 'ok',
                'stop': state in ('check_failed', 'call_error'),
                'resample': state in ('contaminated', 'disconnect', 'truncated')}
    protocol_failures = {'init_missing', 'init_not_first', 'multiple_init',
                         'event_top_level_schema', 'unexpected_init_field', 'error_payload_field'}
    if protocol_failures.intersection(ev['integrity']):
        return verdict('check_failed', list(dict.fromkeys(ev['integrity'])))
    # Any tool step, including refused/failed tools, voids the attempt.
    if ev['tools']:
        return verdict('contaminated', ['tool_step'])
    if ev['integrity']:
        return verdict('check_failed', list(dict.fromkeys(ev['integrity'])))
    if ev['bad_lines'] or ev['unknown'] or len(ev['results']) > 1 or len(set(ev['models'])) > 1:
        return verdict('check_failed', ['stream_integrity'])
    success = len(ev['results']) == 1 and ev['results'][0].get('status') == 'SUCCESS' and isinstance(
        ev['results'][0].get('response'), str) and bool(ev['results'][0]['response'].strip())
    if success and not ev['models']:
        return verdict('check_failed', ['reported_model_missing_probe_required'])
    if not success and any(re.search(p, diagnostic, re.IGNORECASE) for p in rate_patterns):
        return verdict('rate_limited', ['quota_or_rate_limit'])
    if r['timed_out'] or any(p in diagnostic.lower() for p in DISCONNECT_PATTERNS):
        return verdict('disconnect', ['timeout_or_disconnect'])
    if r['returncode'] != 0 or len(ev['results']) != 1 or ev['errors']:
        return verdict('call_error', ['exit_or_missing_result'])
    result = ev['results'][0]
    if result.get('status') != 'SUCCESS' or not isinstance(result.get('response'), str) or not result['response'].strip():
        return verdict('call_error', ['unsuccessful_or_empty_final'])
    if result.get('truncated') or result.get('finish_reason') in ('length', 'max_tokens', 'MAX_TOKENS'):
        return verdict('truncated', ['truncated'])
    if not ev['models']:
        return verdict('check_failed', ['reported_model_missing_probe_required'])
    return verdict('ok', [])


def _reject_json_constant(name):
    """Settings must be standard JSON: NaN/Infinity/-Infinity are rejected."""
    raise ValueError('non-standard JSON constant: ' + name)


class AgySubject:
    def __init__(self, model, rawdir, command=('agy',), settings=DEFAULT_SETTINGS, timeout=600, rate_patterns=RATE_PATTERNS, workroot=None):
        validate_model_name(model)
        self.model, self.rawdir = model, Path(rawdir)
        if workroot is None:
            local = os.environ.get('LOCALAPPDATA')
            if not local:
                raise RuntimeError('LOCALAPPDATA is required for the agy work directory')
            workroot = Path(local) / 'dnli-agy-work' / model
        self.workroot = check_workroot(workroot)
        self.command, self.settings = list(command), Path(settings).resolve()
        first = Path(self.command[0]).expanduser()
        resolved = str(first.resolve()) if first.is_file() else shutil.which(self.command[0])
        if not resolved:
            raise RuntimeError('agy executable not found')
        self.command[0] = resolved
        self.timeout, self.rate_patterns = timeout, validate_rate_patterns(rate_patterns)
        self.tools_sha256 = self.permission_mode = None
        self.rawdir.mkdir(parents=True, exist_ok=True)
        if os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY'):
            raise RuntimeError('API key environment present; subscription route not verified')
        self.session_dir = self.workroot / ('session-%s-%s' % (os.getpid(), uuid.uuid4().hex))
        self.session_dir.mkdir(parents=True)
        self.closed = False
        self.close_error = None

    def close(self):
        if not self.closed:
            self.close_error = cleanup_directory(self.session_dir, self.workroot, prefix='session-', attempts=1)
            self.closed = True
            if self.close_error:
                logging.getLogger(__name__).warning('agy session cleanup failed: %s', self.close_error)
        return self.close_error

    def snapshot(self, reported_model=None):
        try:
            settings = json.loads(self.settings.read_text(encoding='utf-8'), parse_constant=_reject_json_constant)
        except (OSError, ValueError) as exc:
            raise SnapshotError('check_failed: cannot read settings JSON') from exc
        if not isinstance(settings, dict) or not isinstance(settings.get('permissions'), dict):
            raise SnapshotError('check_failed: settings permissions must be an object')
        settings_keys = sorted(settings)
        if set(settings_keys) - {'colorScheme', 'permissions', 'trustedWorkspaces'}:
            raise SnapshotError('environment_changed: unknown settings keys: ' + ', '.join(settings_keys))
        try:
            permissions_sha256 = sha(json.dumps(settings['permissions'], sort_keys=True,
                ensure_ascii=False, separators=(',', ':'), allow_nan=False).encode('utf-8'))
        except (TypeError, ValueError, UnicodeError) as exc:
            raise SnapshotError('check_failed: cannot hash settings permissions') from exc
        v = subprocess.run(self.command + ['--version'], capture_output=True, timeout=30)
        if v.returncode or not v.stdout.strip():
            raise RuntimeError('cannot obtain agy version')
        return {'agy_version': v.stdout.decode('utf-8', errors='replace').strip(),
                'permissions_sha256': permissions_sha256, 'settings_keys': settings_keys,
                'agent_sha256': sha(AGENT_FILE.read_bytes()),
                'reported_model': reported_model,
                'tools_sha256': self.tools_sha256, 'permission_mode': self.permission_mode}

    def attempt(self, ask, prompt, tag, seed):
        check_workroot(self.workroot)
        if self.closed:
            raise RuntimeError('agy subject is closed')
        stamp = dt.datetime.now().astimezone().isoformat()
        before = self.snapshot()
        cmd = self.command + ['--agent', AGENT_NAME, '--model', self.model, '--print', '', '--output-format', 'stream-json',
                              '--input-format', 'stream-json', '--sandbox']
        payload = json.dumps({'event': 'user', 'message': {'content': prompt}}, ensure_ascii=True) + '\n'
        started = time.monotonic()
        timed_out = False
        kill_tree_error = None
        workroot = self.session_dir
        workroot.mkdir(parents=True, exist_ok=True)
        stale_cleanup_errors = cleanup_old_directories(workroot)
        cleanup_result = {}
        with temporary_directory(prefix='dnli-agy-', dir=workroot, cleanup_result=cleanup_result) as cwd:
            agent = Path(cwd) / '.agents' / 'agents' / 'dnli-subject.md'
            agent.parent.mkdir(parents=True)
            agent.write_bytes(AGENT_FILE.read_bytes())
            check_workroot(cwd)
            proc = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            try:
                timeout = self.timeout
                if getattr(self, 'call_deadline', None) is not None:
                    # Account for version snapshot/process launch time before communicate.
                    timeout = max(0, min(timeout, (self.call_deadline-self.deadline_now()).total_seconds()))
                stdout, stderr = proc.communicate(payload.encode('utf-8'), timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                if os.name == 'nt':
                    try:
                        killed = subprocess.run(['taskkill', '/PID', str(proc.pid), '/T', '/F'], capture_output=True, timeout=30)
                        if killed.returncode != 0:
                            kill_tree_error = 'taskkill returncode=%s: %s' % (killed.returncode, killed.stderr.decode('utf-8', errors='replace'))
                    except (OSError, subprocess.TimeoutExpired) as exc:
                        kill_tree_error = str(exc)
                    if kill_tree_error:
                        proc.kill()
                else:
                    proc.kill()
                try:
                    stdout, stderr = proc.communicate(timeout=10)
                except subprocess.TimeoutExpired as exc:
                    stdout, stderr = exc.output or b'', exc.stderr or b''
                    kill_tree_error = (kill_tree_error or '') + '; output pipes still open after termination'
                    proc.stdout.close()
                    proc.stderr.close()
            stem = self.rawdir / (tag + '_' + uuid.uuid4().hex)
            for suffix, data in (('.stream.jsonl', stdout), ('.stderr.txt', stderr)):
                with open(str(stem) + suffix, 'wb') as f:
                    f.write(data)
                    f.flush()
                    os.fsync(f.fileno())
            r = {'stdout': stdout.decode('utf-8', errors='replace'), 'stderr': stderr.decode('utf-8', errors='replace'),
                 'returncode': proc.returncode, 'timed_out': timed_out}
            r['events'] = parse_stream(r['stdout'], self.model, cwd, AGENT_NAME)
            fin = final_inclusion(r, self.rate_patterns)
            if kill_tree_error:
                fin = {'state': 'check_failed', 'stop': True, 'include': False, 'reasons': ['timeout_tree_cleanup_failed']}
            ev = r['events']
            model = ev['models'][0] if ev['models'] else None
            self.tools_sha256, self.permission_mode = ev['tools_sha256'], ev['permission_mode']
            after = self.snapshot(model)
            if any(before[k] != after[k] for k in ('agy_version', 'permissions_sha256', 'settings_keys', 'agent_sha256')):
                fin = {'state': 'check_failed', 'stop': True, 'include': False, 'reasons': ['environment_changed_during_call']}
            meta = {'datetime': stamp, 'seconds': time.monotonic() - started, 'snapshot': after,
                    'before_snapshot': before, 'model_versions': ev['versions'], 'usage': ev['usage'],
                    'raw_prefix': str(stem.resolve()), 'raw_sha256': {'.stream.jsonl': sha(stdout), '.stderr.txt': sha(stderr)},
                    'returncode': proc.returncode, 'timed_out': timed_out}
            meta['kill_tree_error'] = kill_tree_error
            meta['cleanup_error'] = None
            meta['stale_cleanup_errors'] = stale_cleanup_errors
            Path(str(stem) + '.attempt.json').write_text(json.dumps({'prompt': prompt, 'final': fin, 'meta': meta}, ensure_ascii=False), encoding='utf-8')
        meta['cleanup_error'] = cleanup_result['cleanup_error']
        if meta['cleanup_error']:
            Path(str(stem) + '.attempt.json').write_text(json.dumps({'prompt': prompt, 'final': fin, 'meta': meta}, ensure_ascii=False), encoding='utf-8')
        result = ev['results'][0] if len(ev['results']) == 1 else {}
        return {'text': result.get('response', ''), 'final': fin, 'meta': meta,
                'truncated': fin['state'] == 'truncated'}
