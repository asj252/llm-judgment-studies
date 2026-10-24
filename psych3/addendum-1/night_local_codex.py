"""Nightly and bounded on-demand runs; existing entries own fingerprints.

Run once daily at 00:00 Asia/Shanghai; retry only proven transport failures.
Only attempt admission is limited; an admitted call keeps its native timeout.
"""
import argparse
import ast
import atexit
from contextlib import redirect_stderr, redirect_stdout
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, time, timedelta, timezone
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from threading import Lock
from time import sleep

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import run_psych3 as runner
import run_codex_psych3_pinned as codex_entry
import analyse_psych3 as analysis

SHANGHAI = timezone(timedelta(hours=8), 'Asia/Shanghai')
CUTOFF = time(7, 45)
CONFIGS = ('codex', 'qwen3-off')
WINDOW_MESSAGE = 'psych3 night window: no new attempt at/after 07:45 Asia/Shanghai'
AUTORESUME_LIMIT = 8
TRANSPORT_REASON = (
    r'(request timed out|workspace routing discovery failed|workspace routing discovery timed out|'
    r'stream disconnected before completion)(?:: [^\r\n]+)?')
RECONNECT_ERROR = re.compile(r'Reconnecting\.\.\. [0-9]+/[0-9]+ \(' + TRANSPORT_REASON + r'\)')
HTTPS_FALLBACK_WARNING = re.compile(
    r'Falling back from WebSockets to HTTPS transport\. ' + TRANSPORT_REASON)
# Fixed isolation warning, observed with code_mode_host disabled. Never accept
# arbitrary item errors just because the frozen subject classified call_error.
CODE_MODE_WARNING = ('Code Mode is unavailable because code-mode host is disabled. '
                     'Code mode will fail closed; enable `features.code_mode_host` '
                     'and install `codex-code-mode-host`.')


def autoresume_evidence(base, stage, session):
    """Fail closed on missing, ambiguous or non-transport evidence."""
    if session.get('closed_ok') is not True or session.get('invalid') is not False:
        raise ValueError('session not closed and valid')
    rp, _, rawdir = runner.paths(base, stage, 'codex')
    records = [json.loads(line) for line in rp.read_text(encoding='utf-8').splitlines() if line.strip()]
    stopped = [r for r in records if r.get('session_id') == session['session_id']
               and r.get('status') == 'stopped']
    if len(stopped) != 1:
        raise ValueError('expected exactly one stopped record')
    record = stopped[0]
    attempt = record['attempts'][-1]
    final = attempt['final']
    reasons = final.get('reasons')
    if (final.get('state') != 'call_error' or final.get('stop') is not True
            or final.get('invalidate_session', False)
            or not isinstance(reasons, list) or len(reasons) not in (1, 2)
            or not isinstance(reasons[0], str)
            or not re.fullmatch(r'failure_events=[1-9][0-9]*', reasons[0])
            or session.get('stop_reason') != 'call_error: ' + str(reasons)):
        raise ValueError('not solely failure_events call_error')
    if len(reasons) == 2:
        warning_reason = reasons[1]
        if not isinstance(warning_reason, str) or not warning_reason.startswith('warnings='):
            raise ValueError('unexpected additional reason')
        try:
            warnings = ast.literal_eval(warning_reason[len('warnings='):])
        except (ValueError, SyntaxError) as exc:
            raise ValueError('invalid warnings list') from exc
        if (not isinstance(warnings, list) or not warnings
                or any(not isinstance(w, str) or not HTTPS_FALLBACK_WARNING.fullmatch(w)
                       for w in warnings)):
            raise ValueError('warning reason not whitelisted')
    raw = Path(attempt['raw_path']).resolve()
    if (raw.parent != rawdir.resolve() or raw.suffix != '.json'
            or runner.sha(raw.read_bytes()) != attempt['raw_sha256']):
        raise ValueError('raw attempt integrity/path mismatch')
    # CodexSubject appends one UUID to the runner's unique attempt tag.
    streams = list(rawdir.glob(raw.stem + '__*.events.jsonl'))
    if len(streams) != 1:
        raise ValueError('missing or ambiguous event stream')
    stream = streams[0]
    data = stream.read_bytes()
    messages, warning_ids = [], set()
    for number, line in enumerate(data.decode('utf-8').splitlines()):
        if not line.strip():
            continue
        event = json.loads(line)
        kind = event['type']
        if kind == 'error':
            message = event['message']
            if not isinstance(message, str) or not RECONNECT_ERROR.fullmatch(message):
                raise ValueError('error message not whitelisted')
            messages.append(message)
        elif kind not in ('thread.started', 'turn.started', 'turn.completed',
                          'item.started', 'item.updated', 'item.completed'):
            raise ValueError('unexpected event type')
        item = event.get('item')
        if item is not None:
            item_type = item.get('type') or item.get('item_type')
            if item_type == 'error':
                message = item.get('message')
                if message == CODE_MODE_WARNING:
                    warning_ids.add(item.get('id') or ('line', number))
                elif not isinstance(message, str) or not HTTPS_FALLBACK_WARNING.fullmatch(message):
                    raise ValueError('item error not whitelisted')
            elif item_type not in ('agent_message', 'reasoning'):
                raise ValueError('unexpected item type')
    if len(messages) != int(reasons[0].split('=')[1]) or len(warning_ids) > 1:
        raise ValueError('failure/warning count mismatch')
    return dict(session=session['session_id'], unit=record['unit'], reason=reasons[0],
                messages=messages, events_file=str(stream.relative_to(base)),
                events_sha256=runner.sha(data))


def wait_to_resume(minutes, deadline, clock, sleeper):
    """Keep the lock while waiting; a cutoff during backoff is a normal exit."""
    wake = clock() + timedelta(minutes=minutes)
    while True:
        moment = clock()
        if deadline is not None and moment >= deadline:
            return False
        if moment >= wake:
            return True
        end = min(wake, deadline) if deadline is not None else wake
        sleeper(min(60, (end - moment).total_seconds()))


def now():
    return datetime.now(SHANGHAI)


def in_window(moment):
    return moment.astimezone(SHANGHAI).time() < CUTOFF


class WindowSubject:
    """Wrap only attempt; metadata and lifecycle remain with the real adapter."""
    def __init__(self, subject, deadline, clock=now):
        self.subject, self.deadline, self.clock = subject, deadline, clock
        self.window_stopped = False

    def check(self, moment):
        if moment >= self.deadline:
            self.window_stopped = True
            raise RuntimeError(WINDOW_MESSAGE)

    def attempt(self, *args, **kwargs):
        self.check(self.clock())
        return self.subject.attempt(*args, **kwargs)


class OnDemandLimit:
    """Count completed units, not attempts, in this invocation only (one worker)."""
    def __init__(self, *, until=None, max_units=None):
        if until is None and max_units is None:
            raise ValueError('on-demand requires --until or --max-units')
        if max_units is not None and max_units <= 0:
            raise ValueError('--max-units must be positive')
        self.until, self.max_units = until, max_units
        self.completed = 0
        self.reason = None
        self.stop_message = None

    def reached(self, moment):
        if self.reason is None:
            if self.until is not None and moment >= self.until:
                self.reason = 'until'
            elif self.max_units is not None and self.completed >= self.max_units:
                self.reason = 'max_units'
        return self.reason

    def check(self, moment):
        if self.reached(moment):
            self.stop_message = 'psych3 codex on-demand limit: ' + self.reason
            raise RuntimeError(self.stop_message)


class OnDemandSubject(WindowSubject):
    def __init__(self, subject, limit, clock):
        super().__init__(subject, limit.until, clock)
        self.limit = limit

    def check(self, moment):
        self.limit.check(moment)
        super().check(moment)


def on_demand_limit(until, max_units, moment):
    local = moment.astimezone(SHANGHAI)
    deadline = None
    if until is not None:
        if (len(until) != 5 or until[2] != ':' or
                any(ch not in '0123456789' for ch in until[:2] + until[3:])):
            raise ValueError('--until must be HH:MM on the current Asia/Shanghai day')
        try:
            cutoff = time(int(until[:2]), int(until[3:]))
        except ValueError as exc:
            raise ValueError('--until must be between 00:00 and 23:59') from exc
        deadline = datetime.combine(local.date(), cutoff, SHANGHAI)
        if deadline <= local:
            raise ValueError('--until must be later today; midnight rollover is not allowed')
    elif max_units is not None:
        deadline = datetime.combine(local.date(), time(23, 59, 59), SHANGHAI)
    return OnDemandLimit(until=deadline, max_units=max_units)


def preflight(cfg, base=HERE):
    """Read-only completion check before constructing either real subject."""
    base = Path(base)
    frozen = runner.load_json(base / 'analysis_freeze_psych3.json', {})['formal'][cfg]
    rows = runner.build_manifest(base)
    fp, fp_id = runner.fingerprint(rows, cfg, frozen['fingerprint']['subject_meta'], base)
    analysis.check_formal_freeze(cfg, fp, fp_id, base)
    rp, mp, _ = runner.paths(base, 'formal', cfg)
    meta = runner.load_json(mp, {'sessions': []})
    sessions = meta['sessions']
    if any(s.get('status') == 'running' for s in sessions):
        raise RuntimeError('running formal session requires human review; do not abandon it automatically')
    if any(s['fingerprint_id'] != fp_id for s in sessions):
        raise RuntimeError('formal session fingerprint differs from freeze')
    if not mp.exists():
        if rp.exists() and runner.load_records(rp):
            raise RuntimeError('unregistered formal result requires human review')
        return False
    records, _ = analysis.load_valid(rp, mp, fp_id, cfg, strict=True)
    done = {r['unit'] for r in records if r['status'] in ('ok', 'missing', 'tool_contaminated')}
    return done == {r['unit_id'] for r in rows if r['split'] == 'formal'}


def preflight_dev(base=HERE):
    from codex_repin import accepted_dev
    return accepted_dev(base, require_complete=False) is not None


def run_config(cfg, base=HERE, clock=now, log=print, *, release_at_exit=False,
               codex_stage='formal', limit=None, sleeper=sleep):
    """Acquire in the configuration child, before reading review/session state."""
    if limit is not None and cfg != 'codex':
        raise ValueError('on-demand supports codex only')
    helpers = runner.agy_helpers()
    lock = helpers.ModelLock(Path(base) / f'night_{cfg}.lock')
    try:
        lock.__enter__()
    except (helpers.Stop, OSError) as exc:
        log(f'REFUSED {cfg}: lock unavailable: {exc}; no records changed')
        return 2
    if release_at_exit:
        # CLI children retain ownership through interpreter shutdown as well.
        atexit.register(lock.__exit__, None, None, None)
    try:
        return run_locked_config(cfg, base, clock, log, codex_stage=codex_stage,
                                 limit=limit, sleeper=sleeper)
    finally:
        # The original main has returned through its subject.close() finally.
        if not release_at_exit:
            lock.__exit__(None, None, None)


def run_locked_config(cfg, base, clock, log, *, codex_stage='formal', limit=None, sleeper=sleep):
    """One locked invocation; only proven codex transport failures may resume."""
    stage = codex_stage if cfg == 'codex' else 'formal'
    suffix = '_dev' if stage == 'dev' else ''
    review = Path(base) / 'raw' / ('psych3_night_review_' + cfg + suffix + '.json')
    if review.exists():
        log(f'REFUSED {cfg}: human review required: {review}')
        return 2
    original = runner.execute
    last_session = None

    def execute(which, config, rows, subject, fp, fp_id, **kwargs):
        nonlocal last_session
        wrapped = WindowSubject(subject, deadline, clock) if limit is None else OnDemandSubject(subject, limit, clock)
        original_unit = runner.run_unit

        def counted_unit(*args, **kw):
            record = original_unit(*args, **kw)
            if record['status'] in ('ok', 'missing', 'tool_contaminated'):
                limit.completed += 1
            return record

        try:
            if limit is not None:
                if config != 'codex' or kwargs.get('workers', 1) != 1:
                    raise ValueError('on-demand supports codex with one worker only')
                # Process-local hook; leave fingerprint-bound runner files alone.
                runner.run_unit = counted_unit
            code, session = original(which, config, rows, wrapped, fp, fp_id, **kwargs)
        finally:
            runner.run_unit = original_unit
        last_session = session
        message = (WINDOW_MESSAGE if wrapped.window_stopped else None) if limit is None else limit.stop_message
        if code == 3 and message and session['closed_ok']:
            # A window stop must be the only stopped record in this session.
            rp, _, _ = runner.paths(kwargs.get('base', runner.HERE), which, config)
            stopped = [r for r in runner.load_records(rp)
                       if r.get('session_id') == session['session_id'] and r['status'] == 'stopped']
            if stopped and all(r['attempts'][-1]['meta'].get('error') == message for r in stopped):
                log(f'{cfg}: {message}; session closed_ok=True; resume next invocation')
                return 0, session
        return code, session

    try:
        # This replacement is process-local. Each child uses the original main,
        # including codex version pin/recheck, adapter creation, meta and close.
        runner.execute = execute
        entry = codex_entry.main if cfg == 'codex' else runner.main
        retries = 0
        local = clock().astimezone(SHANGHAI)
        deadline = (limit.until or datetime.combine(local.date(), time(23, 59, 59), SHANGHAI)
                    if limit is not None else datetime.combine(local.date(), CUTOFF, SHANGHAI))
        if limit is not None:
            limit.until = deadline
        audit = None
        while True:
            complete = preflight_dev(base) if stage == 'dev' else preflight(cfg, base)
            if complete:
                log(f'{cfg}: {stage} set already complete and accepted; no subject constructed')
                return 0
            moment = clock()
            if limit is not None and limit.reached(moment):
                log(f'{cfg}: on-demand limit reached before entry: {limit.reason}')
                return 0
            if limit is None and (not in_window(moment) or moment >= deadline):
                log(f'{cfg}: outside 00:00–07:45 Asia/Shanghai; exit until next nightly trigger')
                return 0
            if audit is None:
                audit = Path(base) / 'raw' / f'psych3_codex_autoresume_{local:%Y-%m-%d}' / 'audit.jsonl'
            last_session = None
            code = entry([stage, cfg])
            if code != 3 or cfg != 'codex' or last_session is None:
                break
            try:
                evidence = autoresume_evidence(base, stage, last_session)
            except (ValueError, KeyError, TypeError, IndexError, AttributeError, OSError) as exc:
                log(f'{cfg}: autoresume refused: {exc}')
                break
            if retries >= AUTORESUME_LIMIT:
                log(f'{cfg}: autoresume limit reached ({AUTORESUME_LIMIT})')
                break
            # Count is invocation-local, shared by all its sessions. Reserve the
            # durable audit before waiting or constructing the next subject.
            retries += 1
            minutes = (5, 10, 20)[min(retries, 3) - 1]
            audit.parent.mkdir(parents=True, exist_ok=True)
            with audit.open('a', encoding='utf-8', newline='\n') as stream:
                stream.write(json.dumps(dict(evidence, time=clock().isoformat(), stage=stage,
                                             ordinal=retries, wait_minutes=minutes),
                                        ensure_ascii=False) + '\n')
                stream.flush()
                os.fsync(stream.fileno())
            log(f'{cfg}: transport autoresume {retries}/{AUTORESUME_LIMIT}; wait {minutes} minutes')
            if not wait_to_resume(minutes, deadline, clock, sleeper):
                if limit is not None:
                    limit.reached(clock())
                log(f'{cfg}: cutoff reached during autoresume wait; normal exit')
                return 0
        if code == 0 and stage == 'dev':
            # A cutoff is a successful nightly exit, but is not dev completion.
            if preflight_dev(base):
                log('codex: development acceptance passed; stop here; formal requires manual refreeze and publication')
    except Exception as exc:
        log(f'REFUSED {cfg}: {exc}')
        code = 2
    finally:
        runner.execute = original
    if code:
        runner.save_json(review, dict(config=cfg, code=code, time=clock().isoformat(),
                                      reason='Non-window stop. Human review required before removing this file.'))
        log(f'{cfg}: review latch written: {review}; no automatic retry')
    return code


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--child', choices=CONFIGS, help=argparse.SUPPRESS)
    parser.add_argument('--codex-stage', choices=('dev', 'formal'), default='formal',
                        help='codex only; dev never advances to formal; Qwen3 remains formal')
    parser.add_argument('--codex-only', action='store_true', help='bounded on-demand codex run')
    parser.add_argument('--stage', choices=('dev', 'formal'), help='required with --codex-only')
    parser.add_argument('--until', metavar='HH:MM', help='today, Asia/Shanghai; no new attempt at cutoff')
    parser.add_argument('--max-units', type=int, help='maximum newly completed units this invocation')
    args = parser.parse_args(argv)
    if args.codex_only:
        if args.child or args.stage is None or args.codex_stage != 'formal':
            parser.error('--codex-only requires --stage; do not combine with --child or --codex-stage')
        try:
            limit = on_demand_limit(args.until, args.max_units, now())
        except ValueError as exc:
            parser.error(str(exc))
        logpath = HERE / 'raw' / f'psych3_codex_ondemand_{now():%Y-%m-%d}.log'
        logpath.parent.mkdir(parents=True, exist_ok=True)
        with logpath.open('a', encoding='utf-8', buffering=1) as stream, \
                redirect_stdout(stream), redirect_stderr(stream):
            def log(line):
                stream.write(f'{now().isoformat()} {line}\n')

            log(f'start codex on-demand: stage={args.stage} until={args.until!r} '
                f'max_units={args.max_units!r}; deadline={limit.until}')
            code = 2
            try:
                code = run_config('codex', HERE, now, log, release_at_exit=True,
                                  codex_stage=args.stage, limit=limit)
            finally:
                reason = limit.reason or ('set_complete' if code == 0 else 'refused_or_failed')
                log(f'finished codex on-demand: completed={limit.completed} reason={reason} exit={code}')
        return code
    if args.stage is not None or args.until is not None or args.max_units is not None:
        parser.error('--stage, --until and --max-units require --codex-only')
    if args.child:
        return run_config(args.child, release_at_exit=True, codex_stage=args.codex_stage)
    logpath = HERE / 'raw' / f'psych3_night_local_codex_{now():%Y-%m-%d}.log'
    logpath.parent.mkdir(parents=True, exist_ok=True)
    lock = Lock()
    with logpath.open('a', encoding='utf-8', buffering=1) as stream:
        def log(line):
            with lock:
                stream.write(f'{now().isoformat()} {line}\n')

        def child(cfg):
            command = [sys.executable, '-I', '-X', 'utf8', '-B', '-u', str(Path(__file__).resolve()), '--child', cfg]
            stage = args.codex_stage if cfg == 'codex' else 'formal'
            if stage == 'dev':
                command += ['--codex-stage', 'dev']
            log(f'{cfg}: launching {stage} entry with attempt window')
            try:
                with subprocess.Popen(command, cwd=HERE, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, text=True, encoding='utf-8',
                                      errors='replace', bufsize=1) as proc:
                    for line in proc.stdout:
                        log(f'[{cfg}] {line.rstrip()}')
                    code = proc.wait()
            except OSError as exc:
                log(f'{cfg}: launch failed: {exc}; no retry')
                code = 2
            # Only the child holding the configuration lock may write a latch.
            # In particular, lock contention must not alter the active run.
            log(f'{cfg}: exit={code}')
            return code

        with ThreadPoolExecutor(max_workers=2) as pool:
            codes = list(pool.map(child, CONFIGS))
        log(f'finished; codes={codes}')
    return max(codes)


if __name__ == '__main__':
    sys.exit(main())
