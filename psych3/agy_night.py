"""Four independent psych3 agy workers; no model calls on import.

The adapter boundary deliberately uses BaseException for a resumable pause:
run_psych3 catches Exception and turns it into a persistent scientific STOP.
"""
import argparse
from contextlib import contextmanager
import datetime as dt
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_psych3 as R
from settings_restore import restore_settings

MODELS = ('gpt-oss-120b-medium', 'claude-sonnet-5-5-medium',
          'gemini-3.8-flash-low', 'gemini-3.8-flash-high')
# Shanghai has no DST; fixed offset also works on Windows without tzdata.
SHANGHAI = dt.timezone(dt.timedelta(hours=8), 'Asia/Shanghai')
DAILY_LIMIT = 8


def now():
    return dt.datetime.now(SHANGHAI)


def local(clock):
    value = clock()
    if value.tzinfo is None:
        raise ValueError('clock must be timezone aware')
    return value.astimezone(SHANGHAI)


def admission(clock):
    return local(clock).time() < dt.time(7, 45)


def read(path, default=None):
    path = Path(path)
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default


class Pause(BaseException):
    def __init__(self, reason, until=None):
        self.reason, self.until = reason, until


class BoundarySubject:
    def __init__(self, subject, clock=now):
        self.subject, self.clock = subject, clock
        self.night = local(clock).date()

    def snapshot(self, reported=None):
        if local(self.clock).date() != self.night or not admission(self.clock):
            raise Pause('night admission closed')
        return self.subject.snapshot(reported)

    def attempt(self, *args):
        # Retries of an admitted unit may finish during the grace period.
        if local(self.clock).date() != self.night or local(self.clock).time() >= dt.time(8):
            raise Pause('hard deadline')
        response = self.subject.attempt(*args)
        if local(self.clock).date() != self.night or local(self.clock).time() >= dt.time(8):
            raise Pause('hard deadline; redo unfinished unit')
        return response


def policy(clock=now):
    helpers = R.agy_helpers()

    class NightPolicy(helpers.RetryPolicy):
        def resume_wait(self, progress):
            wake = self.state.get('wake_at')
            if wake and dt.datetime.fromisoformat(wake) > local(clock):
                progress()
                raise Pause('rate backoff', wake)
            self.state['wake_at'] = None
            progress()

    return NightPolicy(now=lambda: local(clock))


@contextmanager
def checkpoint_guard(root, stage, model, clock):
    """Guard the existing atomic commit boundary inside this single-thread worker.

    Journal new session IDs before registration. A separate receipt attests the
    completion of *all* checkpoint IO, including clearing the journal. Publishing
    that immutable evidence does not change the checkpoint completion time.
    """
    metadata = R.paths(root, stage, 'agy:' + model)[1].resolve()
    night = local(clock).date()
    deadline = dt.datetime.combine(night, dt.time(8), SHANGHAI)
    anchor, tick = local(clock), time.monotonic()
    observed = anchor

    def completion():
        nonlocal observed
        # Neither wall-clock rollback nor a slow disk may move completion back.
        observed = max(observed, local(clock),
                       anchor + dt.timedelta(seconds=time.monotonic() - tick))
        return observed

    original = R.save_json
    journal = metadata.with_suffix(metadata.suffix + '.checkpoint.json')
    meta = checkpoint_meta(metadata)
    if journal.exists():
        original(metadata, meta)  # Persist invalidation before allowing resume.
        original(journal, [])
    registered = {s['session_id'] for s in meta['sessions']}

    def save(path, obj):
        if Path(path).resolve() != metadata:
            return original(path, obj)
        stamp = local(clock)
        if stamp.date() != night or stamp.time() >= dt.time(8):
            raise Pause('hard deadline before checkpoint; redo unfinished unit')
        added = {s['session_id'] for s in obj['sessions']} - registered
        if added:
            for session in obj['sessions']:
                if session['session_id'] in added:
                    session['night_checkpoint_deadline'] = deadline.isoformat()
            original(journal, sorted(added))
        result = original(path, obj)
        if added:
            original(journal, [])
            # Sample once after the complete transaction, never before its last
            # replace. Missing evidence (including a kill here) fails closed.
            stamp = completion()
            for session_id in added:
                original(checkpoint_receipt(metadata, session_id),
                         dict(completed_at=stamp.isoformat(), deadline=deadline.isoformat()))
            if stamp >= deadline:
                raise Pause('hard deadline during checkpoint; redo unfinished unit')
            registered.update(added)
        return result

    R.save_json = save
    try:
        yield
    finally:
        R.save_json = original


def checkpoint_receipt(metadata, session_id):
    if not isinstance(session_id, str) or len(session_id) != 32 or any(
            c not in '0123456789abcdef' for c in session_id):
        raise ValueError('invalid checkpoint session ID')
    return metadata.with_name(metadata.name + '.checkpoint.' + session_id + '.json')


def checkpoint_meta(metadata):
    """Read through an interrupted commit without counting its sessions."""
    metadata = Path(metadata)
    meta = read(metadata, {'sessions': []})
    pending = read(metadata.with_suffix(metadata.suffix + '.checkpoint.json'), [])
    if not isinstance(pending, list) or any(not isinstance(s, str) for s in pending):
        raise ValueError('invalid checkpoint journal')
    for session in meta['sessions']:
        invalid = session['session_id'] in pending
        if 'night_checkpoint_deadline' in session:
            receipt = read(checkpoint_receipt(metadata, session['session_id']))
            deadline = dt.datetime.fromisoformat(session['night_checkpoint_deadline'])
            invalid |= (not receipt or receipt.get('deadline') != deadline.isoformat()
                        or dt.datetime.fromisoformat(receipt['completed_at']) >= deadline)
        if invalid:
            session.update(invalid=True, closed_ok=False)
    return meta


def checked_records(root, stage, model):
    rp, mp, _ = R.paths(root, stage, 'agy:' + model)
    meta = checkpoint_meta(mp)
    sessions = meta['sessions']
    records = R.agy_helpers().load_records(rp)
    good = [s for s in sessions if s.get('closed_ok') and not s.get('invalid')]
    fingerprints = {s['fingerprint_id'] for s in good}
    if len(fingerprints) > 1:
        raise ValueError('mixed fingerprints')
    for s in good:
        rows = [r for r in records if r.get('session_id') == s['session_id']]
        digest = R.sha(json.dumps(rows, sort_keys=True, ensure_ascii=False).encode('utf-8'))
        if digest != s['records_sha256']:
            raise ValueError('closed session result integrity failed')
        for record in rows:
            for attempt in record.get('attempts', []):
                raw = Path(attempt['raw_path'])
                if R.sha(raw.read_bytes()) != attempt['raw_sha256']:
                    raise ValueError('raw attempt integrity failed')
    valid = R.agy_helpers().valid_records(records, sessions, next(iter(fingerprints), ''))
    return meta, valid


def acceptance(records, expected, stopped=False):
    n = len(expected)
    first = sum(bool(r.get('attempts')) and r['attempts'][0].get('parsed') is True
                for r in records.values())
    missing = sum(r['status'] != 'ok' for r in records.values())
    return {'passed': bool(n) and set(records) == expected and not stopped
            and first * 100 >= 90 * n and missing * 100 <= 2 * n,
            'first': first, 'missing': missing, 'planned': n}


def run_worker(root, model, stage, clock=now, factory=None, rows=None, fingerprint=None):
    """Run a stage using the unchanged first-stage runner and model lock."""
    root = Path(root)
    helpers = R.agy_helpers()
    cfg = 'agy:' + model
    _, _, raw = R.paths(root, stage, cfg)
    with helpers.ModelLock(root / (R.config_name(cfg) + '.lock')):
        if not admission(clock):
            return {'status': 'paused', 'reason': 'night admission closed'}
        subject = None
        try:
            rows = R.build_manifest() if rows is None else rows
            subject = (factory or helpers.AgySubject)(model, raw)
            spec = dict(model=model, baseline=subject.snapshot(), timeout=subject.timeout,
                        rate_patterns=list(subject.rate_patterns))
            fp, fid = fingerprint or R.fingerprint(rows, cfg, spec, base=root)
            # Bind the scheduler rules too, including recovery and window semantics.
            fp = dict(fp, psych3_agy_night=dict(
                python_sha256=R.sha(Path(__file__).read_bytes()),
                powershell_sha256=R.sha(Path(__file__).with_suffix('.ps1').read_bytes()),
                recovery_rules_sha256=R.sha((R.HERE.parent / 'dnli-agy/auto_clear.py').read_bytes()),
                workers=4, timezone='Asia/Shanghai', admission='00:00-07:45',
                hard_stop='08:00', auto_clear_limit=DAILY_LIMIT))
            fid = R.sha(json.dumps(fp, sort_keys=True, ensure_ascii=False).encode('utf-8'))
            if stage == 'formal':
                from analyse_psych3 import check_formal_freeze
                check_formal_freeze(cfg, fp, fid, root)
            with checkpoint_guard(root, stage, model, clock):
                code, _ = R.execute(stage, cfg, rows, BoundarySubject(subject, clock), fp, fid,
                                    base=root, policy=policy(clock))
            meta, valid = checked_records(root, stage, model)
            if code:
                return {'status': 'needs_review', 'reason': str(meta.get('stopped'))}
            expected = {r['unit_id'] for r in rows if r['split'] == stage}
            if stage == 'dev':
                verdict = acceptance(valid, expected, meta.get('stopped'))
                return {'status': 'complete' if verdict['passed'] else 'needs_review',
                        'reason': 'development acceptance', 'acceptance': verdict}
            if set(valid) != expected:
                raise ValueError('formal plan incomplete')
            return {'status': 'complete'}
        except Pause as exc:
            return {'status': 'paused', 'reason': exc.reason, 'skipped_until': exc.until}
        except Exception as exc:
            return {'status': 'needs_review', 'reason': str(exc)}
        finally:
            if subject is not None:
                subject.close()


def preconversation(root, attempt):
    """Adapt dnli-agy.auto_clear evidence to psych3 wrapper attempts."""
    A = R.legacy('dnli-agy', 'auto_clear')
    final = attempt['final']
    A.require(final.get('state') == 'check_failed' and final.get('stop') is True
              and bool(final.get('reasons')) and set(final['reasons']) <= A.ALLOWED_REASONS,
              'not eligible check_failed')
    prefix = Path(attempt['meta']['raw_prefix']).resolve()
    A.require(prefix.is_relative_to(Path(root).resolve() / 'raw'), 'raw path outside psych3')
    stream = Path(str(prefix) + '.stream.jsonl')
    stderr = Path(str(prefix) + '.stderr.txt')
    digests = attempt['meta']['raw_sha256']
    for suffix in ('.stream.jsonl', '.stderr.txt'):
        A.require(R.sha(Path(str(prefix) + suffix).read_bytes()) == digests[suffix],
                  'adapter raw digest mismatch')
    events = [json.loads(line) for line in stream.read_text(encoding='utf-8').splitlines()]
    A.require(len(events) == 1 and set(events[0]) == {'event', 'result'}
              and events[0]['event'] == 'result', 'not single result event')
    result = events[0]['result']
    A.require(set(result) == {'conversation_id', 'status', 'response', 'error',
                             'duration_seconds', 'num_turns', 'usage'}, 'invalid result fields')
    import math
    duration = result['duration_seconds']
    A.require(type(duration) in (int, float) and math.isfinite(duration) and duration >= 0,
              'invalid duration')
    A.require(result['conversation_id'] == '' and result['status'] == 'ERROR'
              and result['response'] == '' and type(result['num_turns']) is int
              and result['num_turns'] == 0, 'not empty pre-conversation failure')
    A.require(set(result['usage']) == {'input_tokens', 'output_tokens', 'thinking_tokens',
                                     'cache_read_tokens', 'total_tokens'}
              and all(type(v) is int and v == 0 for v in result['usage'].values()), 'not zero usage')
    return A.consistent_rule(result['error'], stderr.read_text(encoding='utf-8'))


def auto_clear(root, model, row, clock=now):
    """Only clear independently proven transport/access stops; reserve audit first."""
    root = Path(root)
    stamp = local(clock)
    audit = root / 'raw' / ('psych3_auto_clear_' + stamp.date().isoformat()) / 'audit.jsonl'
    entries = [json.loads(line) for line in audit.read_text(encoding='utf-8').splitlines()] if audit.exists() else []
    ordinal = sum(e['model'] == model for e in entries) + 1
    if ordinal > DAILY_LIMIT:
        return False
    stage = row['stage']
    rp, mp, _ = R.paths(root, stage, 'agy:' + model)
    meta, _ = checked_records(root, stage, model)
    reason = row['needs_review']['reason']
    if meta.get('stopped'):
        if str(meta['stopped']) != reason:
            return False
        stopped = [s for s in meta['sessions'] if s.get('status') == 'stopped']
        if not stopped or stopped[-1].get('stop_reason') != reason:
            return False
        records = R.agy_helpers().load_records(rp)
        candidates = [r for r in records if r.get('session_id') == stopped[-1]['session_id']]
        if len(candidates) != 1 or not candidates[0].get('attempts'):
            return False
        record = candidates[0]
        if R.agy_helpers().record_hash(record) != stopped[-1]['record_sha256']:
            return False
        attempt = record['attempts'][-1]
        if R.sha(Path(attempt['raw_path']).read_bytes()) != attempt['raw_sha256']:
            return False
        kind = preconversation(root, attempt)
    else:
        # Match only the exact psych3 result or atomic metadata replacement paths.
        import re
        match = re.fullmatch(r"\[Errno 13\] Permission denied: '([^']+)'", reason)
        access = bool(match and Path(match[1]).resolve() == rp.resolve())
        match = re.fullmatch(r"\[WinError 5\] [^\r\n]+: '([^']+)' -> '([^']+)'", reason)
        if match:
            tmp, dst = Path(match[1]), Path(match[2])
            access = (dst.resolve() == mp.resolve() and tmp.parent.resolve() == mp.parent.resolve()
                      and re.fullmatch(re.escape(mp.name) + r'\.[0-9a-f]{32}\.tmp', tmp.name) is not None)
        if not access or not mp.exists():
            return False
        # An access error can hide a scientific STOP whose registration failed.
        # Any unregistered result is ambiguous, even if it looks successful.
        registered = {s['session_id'] for s in meta['sessions']}
        try:
            records = ([json.loads(line) for line in rp.read_text(encoding='utf-8').splitlines()
                        if line.strip()] if rp.exists() else [])
        except (OSError, ValueError):
            return False  # The normal resume reader tolerates torn lines; clearing must not.
        if any(not isinstance(r, dict) or r.get('session_id') not in registered for r in records):
            return False
        temporaries = list(mp.parent.glob(mp.name + '.*.tmp'))
        if match and tmp not in temporaries:
            return False  # Missing failed replacement evidence is not proof.
        for candidate in temporaries:
            try:
                staged = read(candidate)
                if (not isinstance(staged, dict) or staged != meta or staged.get('stopped')
                        or any(s.get('status') == 'stopped' or s.get('stop_reason')
                               for s in staged['sessions'])):
                    return False
            except (OSError, ValueError, KeyError, TypeError):
                return False
        kind = 'access_denied'
    dest = audit.parent / (model + '_' + uuid.uuid4().hex)
    dest.mkdir(parents=True)
    # Keep all original data; recovery only changes the persistent stop field.
    for source in (mp, root / 'raw' / 'psych3_agy_queue.json'):
        if source.exists():
            (dest / source.name).write_bytes(source.read_bytes())
    wait = (30, 60, 120)[min(ordinal, 3) - 1]
    with audit.open('a', encoding='utf-8', newline='\n') as stream:
        stream.write(json.dumps(dict(model=model, ordinal=ordinal, kind=kind,
                                     datetime=stamp.isoformat(), wait_minutes=wait,
                                     backup=str(dest.relative_to(root)))) + '\n')
        stream.flush()
        os.fsync(stream.fileno())
    if meta.get('stopped'):
        meta['stopped'] = None
        R.save_json(mp, meta)
    row['needs_review'] = None
    row['skipped_until'] = (stamp + dt.timedelta(minutes=wait)).isoformat()
    return True


def attach_job(process):
    """Contain Windows descendants, including when the supervisor exits abruptly."""
    if os.name != 'nt':
        return
    import ctypes as C
    from ctypes import wintypes as W

    class Basic(C.Structure):
        _fields_ = [('per_process', C.c_int64), ('per_job', C.c_int64),
                    ('flags', W.DWORD), ('minimum', C.c_size_t), ('maximum', C.c_size_t),
                    ('active', W.DWORD), ('affinity', C.c_size_t),
                    ('priority', W.DWORD), ('scheduling', W.DWORD)]

    class IO(C.Structure):
        _fields_ = [(name, C.c_uint64) for name in ('read_ops', 'write_ops', 'other_ops',
                                                  'read_bytes', 'write_bytes', 'other_bytes')]

    class Extended(C.Structure):
        _fields_ = [('basic', Basic), ('io', IO), ('process_memory', C.c_size_t),
                    ('job_memory', C.c_size_t), ('peak_process', C.c_size_t),
                    ('peak_job', C.c_size_t)]

    kernel = C.WinDLL('kernel32', use_last_error=True)
    kernel.CreateJobObjectW.argtypes = [C.c_void_p, W.LPCWSTR]
    kernel.CreateJobObjectW.restype = W.HANDLE
    kernel.SetInformationJobObject.argtypes = [W.HANDLE, C.c_int, C.c_void_p, W.DWORD]
    kernel.AssignProcessToJobObject.argtypes = [W.HANDLE, W.HANDLE]
    kernel.TerminateJobObject.argtypes = [W.HANDLE, W.UINT]
    kernel.CloseHandle.argtypes = [W.HANDLE]
    handle = kernel.CreateJobObjectW(None, None)
    if not handle:
        raise C.WinError(C.get_last_error())
    limits = Extended()
    limits.basic.flags = 0x2000  # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if (not kernel.SetInformationJobObject(handle, 9, C.byref(limits), C.sizeof(limits))
            or not kernel.AssignProcessToJobObject(handle, int(process._handle))):
        error = C.WinError(C.get_last_error())
        kernel.CloseHandle(handle)
        raise error
    process.psych3_job = (kernel, handle)


def close_job(process):
    job = getattr(process, 'psych3_job', None)
    if job:
        kernel, handle = job
        if not kernel.CloseHandle(handle):
            raise OSError('CloseHandle(job) failed')
        process.psych3_job = None


def terminate_tree(process):
    if os.name == 'nt':
        job = getattr(process, 'psych3_job', None)
        if job:
            kernel, handle = job
            if not kernel.TerminateJobObject(handle, 1):
                raise OSError('TerminateJobObject failed')
        else:
            subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], check=True,
                           capture_output=True, timeout=30)
    else:
        os.killpg(process.pid, signal.SIGKILL)
    process.wait(timeout=30)
    close_job(process)


class Queue:
    def __init__(self, root=R.HERE, clock=now, sleep=time.sleep, spawn=None,
                 kill=terminate_tree, dnli_state=None, settings=None, baseline=None):
        self.root, self.clock, self.sleep = Path(root), clock, sleep
        self.spawn, self.kill = spawn or self.launch, kill
        self.dnli_state = Path(dnli_state) if dnli_state else R.HERE.parent / 'dnli-agy/raw/queue_state.json'
        self.settings = Path(settings) if settings else Path.home() / '.gemini/antigravity-cli/settings.json'
        self.baseline = Path(baseline) if baseline is not None else self.root / 'agy_settings_baseline.json'
        self.path = self.root / 'raw/psych3_agy_queue.json'
        self.active = {}
        self.night = local(clock).date()

    def load(self):
        state = read(self.path, {'version': 1, 'models': {}, 'quota_events': [], 'gemini_quota_pairs': []})
        if (not isinstance(state, dict) or state.get('version') != 1
                or not isinstance(state.get('models'), dict)
                or not isinstance(state.get('quota_events'), list)
                or not isinstance(state.get('gemini_quota_pairs'), list)):
            raise ValueError('invalid psych3 queue state')
        for key in ('settings_restores', 'settings_restore_failures'):
            if not isinstance(state.setdefault(key, []), list):
                raise ValueError('invalid ' + key)
        for event in state['quota_events']:
            if (not isinstance(event, dict) or event.get('model') not in MODELS
                    or not isinstance(event.get('datetime'), str)
                    or dt.datetime.fromisoformat(event['datetime']).tzinfo is None):
                raise ValueError('invalid quota event')
        for pair in state['gemini_quota_pairs']:
            if (not isinstance(pair, dict) or not isinstance(pair.get('models'), list)
                    or len(pair['models']) != 2 or set(pair['models']) != set(MODELS[2:])
                    or dt.datetime.fromisoformat(pair['datetime']).tzinfo is None):
                raise ValueError('invalid gemini quota pair')
        for model in MODELS:
            row = state['models'].setdefault(model, dict(stage='dev', needs_review=None,
                                                         skipped_until=None))
            if not isinstance(row, dict) or row.get('stage') not in ('dev', 'formal', 'done'):
                raise ValueError('invalid model state: ' + model)
            if not {'stage', 'needs_review', 'skipped_until'} <= row.keys():
                raise ValueError('incomplete model state: ' + model)
            review = row['needs_review']
            if review is not None and (not isinstance(review, dict) or not isinstance(review.get('reason'), str)):
                raise ValueError('invalid needs_review: ' + model)
            if row.get('skipped_until'):
                value = dt.datetime.fromisoformat(row['skipped_until'])
                if value.tzinfo is None:
                    raise ValueError('naive skipped_until')
        self.state = state

    def save(self):
        R.save_json(self.path, self.state)

    def dnli_done(self, model):
        state = read(self.dnli_state)
        # Missing/unknown/malformed legacy state cannot establish completion.
        return (isinstance(state, dict) and isinstance(state.get('models'), dict)
                and isinstance(state['models'].get(model), dict)
                and state['models'][model].get('stage') == 'done')

    def launch(self, model, stage):
        result = self.root / 'raw' / ('psych3_worker_' + model + '_' + uuid.uuid4().hex + '.json')
        log = self.root / 'raw' / ('psych3_worker_' + model + '.log')
        gate = result.with_suffix('.ready')
        with log.open('ab') as stream:
            process = subprocess.Popen([sys.executable, '-I', str(Path(__file__).resolve()),
                                        '--root', str(self.root.resolve()), '--worker', model,
                                        '--stage', stage, '--outcome', str(result.resolve()),
                                        '--gate', str(gate.resolve())],
                                       stdout=stream, stderr=subprocess.STDOUT,
                                       start_new_session=os.name != 'nt',
                                       creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0)
        try:
            attach_job(process)
            gate.write_text('ready', encoding='utf-8')
        except BaseException:
            process.kill()  # Gate is closed: no model or descendants were started.
            process.wait(timeout=30)
            close_job(process)
            raise
        return process, result

    def quota_event(self, model, result):
        if result.get('reason') != 'rate backoff':
            return
        stamp = local(self.clock)
        for event in self.state['quota_events']:
            if ('gemini' in model and 'gemini' in event['model'] and event['model'] != model
                    and 0 <= (stamp - dt.datetime.fromisoformat(event['datetime'])).total_seconds() <= 600):
                self.state['gemini_quota_pairs'].append(dict(models=[event['model'], model],
                                                            datetime=stamp.isoformat()))
        self.state['quota_events'].append(dict(model=model, datetime=stamp.isoformat(),
                                              skipped_until=result.get('skipped_until')))

    def tick(self):
        stamp = local(self.clock)
        for model, (process, output) in list(self.active.items()):
            row = self.state['models'][model]
            if stamp.date() != self.night or stamp.time() >= dt.time(8):
                # Do not trust an outcome racing with the deadline; checkpoints
                # already closed remain valid, the in-flight unit stays unregistered.
                if process.poll() is None:
                    self.kill(process)
                row.update(last_exit='hard_deadline', worker=None)
            elif process.poll() is None:
                continue
            else:
                close_job(process)
                try:
                    result = read(output)
                except (OSError, ValueError) as exc:
                    result = dict(status='needs_review', reason='invalid worker outcome: ' + str(exc))
                if process.returncode != 0 or not isinstance(result, dict):
                    result = dict(status='needs_review', reason='worker failed without valid outcome')
                if (result.get('status') not in ('complete', 'needs_review', 'paused')
                        or (result.get('status') == 'needs_review' and not isinstance(result.get('reason'), str))):
                    result = dict(status='needs_review', reason='invalid worker outcome schema')
                if result.get('status') == 'paused' and result.get('skipped_until'):
                    try:
                        if dt.datetime.fromisoformat(result['skipped_until']).tzinfo is None:
                            raise ValueError('naive wake time')
                    except (ValueError, TypeError):
                        result = dict(status='needs_review', reason='invalid worker wake time')
                row['worker'] = None
                row['last_outcome'] = result
                if result['status'] == 'complete':
                    row['stage'] = 'formal' if row['stage'] == 'dev' else 'done'
                elif result['status'] == 'needs_review':
                    row['needs_review'] = dict(reason=result['reason'], datetime=stamp.isoformat())
                elif result['status'] == 'paused':
                    row['skipped_until'] = result.get('skipped_until')
                    self.quota_event(model, result)
                else:
                    raise ValueError('unknown worker status')
            close_job(process)
            del self.active[model]
            self.save()
        if stamp.date() != self.night or not admission(self.clock):
            return
        for model in MODELS:
            row = self.state['models'][model]
            if model in self.active or row['stage'] == 'done':
                continue
            if row.get('needs_review'):
                try:
                    with R.agy_helpers().ModelLock(self.root / (R.config_name('agy:' + model) + '.lock')):
                        auto_clear(self.root, model, row, self.clock)
                except Exception as exc:
                    row['auto_clear_refused'] = str(exc)
                self.save()
                if row.get('needs_review'):
                    continue
            until = row.get('skipped_until')
            if until and dt.datetime.fromisoformat(until) > stamp:
                continue
            if not self.dnli_done(model):
                row['last_exit'] = 'dnli_not_done'
                continue
            if not admission(self.clock):
                break
            try:
                self.active[model] = self.spawn(model, row['stage'])
            except Exception as exc:
                row['needs_review'] = dict(reason='worker launch: ' + str(exc), datetime=stamp.isoformat())
                self.save()
                continue
            row['worker'] = dict(pid=self.active[model][0].pid, started=stamp.isoformat())
            self.save()

    def run(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with R.agy_helpers().ModelLock(self.root / 'raw/psych3_agy_queue.lock'):
            self.load()  # Refuse corruption before snapshot or state replacement.
            if not admission(self.clock):
                return self.state
            snapshot = self.root / 'raw' / ('psych3_settings_snapshot_' + local(self.clock).date().isoformat() + '.json')
            if not snapshot.exists():
                try:
                    data = self.settings.read_bytes()
                except FileNotFoundError:
                    data = None
                if data is not None:
                    with snapshot.open('xb') as stream:
                        stream.write(data)
            result = restore_settings(self.settings, self.baseline, self.root / 'raw',
                                      local(self.clock), may_write=lambda: admission(self.clock))
            if result['status'] == 'failed':
                self.state['settings_restore_failures'].append(dict(
                    datetime=local(self.clock).isoformat(), reason=result['reason'],
                    audit=result.get('audit')))
            elif (result['status'] == 'restored'
                  or result.get('audit', {}).get('recovered_displaced')):
                self.state['settings_restores'].append(result['audit'])
            self.save()
            print('PSYCH3_SETTINGS_RESTORE ' + json.dumps(result, ensure_ascii=False), flush=True)
            if result['status'] == 'failed':
                return self.state
            try:
                while True:
                    self.tick()
                    if not self.active:
                        # Task Scheduler retries later for quota/recovery/coexistence.
                        break
                    self.sleep(1)
            finally:
                failures = []
                for model, (process, _) in list(self.active.items()):
                    try:
                        if process.poll() is None:
                            self.kill(process)
                    except Exception as exc:
                        failures.append(model + ': ' + str(exc))
                        self.state['models'][model]['needs_review'] = dict(
                            reason='tree cleanup failed: ' + str(exc), datetime=local(self.clock).isoformat())
                    finally:
                        try:
                            close_job(process)
                        except Exception as exc:
                            failures.append(model + ': job close: ' + str(exc))
                    self.state['models'][model]['worker'] = None
                self.active.clear()
                self.save()
                if failures:
                    raise RuntimeError('; '.join(failures))
            return self.state


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=R.HERE)
    parser.add_argument('--worker', choices=MODELS)
    parser.add_argument('--stage', choices=('dev', 'formal'))
    parser.add_argument('--outcome', type=Path)
    parser.add_argument('--gate', type=Path)
    args = parser.parse_args(argv)
    os.environ['AGY_CLI_DISABLE_AUTO_UPDATE'] = 'true'
    if args.worker:
        if not args.stage or not args.outcome:
            parser.error('worker requires stage and outcome')
        if args.gate:
            end = time.monotonic() + 30
            while not args.gate.exists():
                if time.monotonic() >= end:
                    raise RuntimeError('supervisor did not release worker gate')
                time.sleep(.02)
        R.save_json(args.outcome, run_worker(args.root, args.worker, args.stage))
    else:
        state = Queue(args.root).run()
        print('PSYCH3_AGY_SUMMARY ' + json.dumps(state['models'], ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
