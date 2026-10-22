"""Conservative offline recovery for pre-conversation failures and run_meta access denial."""
import argparse
import ast
import datetime as dt
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import uuid

import run_agy as R
from configs import file_config

DAILY_LIMIT = 8
ATTEMPT_SUFFIXES = ('.stream.jsonl', '.stderr.txt', '.attempt.json')

ALLOWED_REASONS = frozenset(('invalid_conversation_id', 'result_schema',
                             'result_num_turns', 'init_missing'))
STDERR_RULES = (
    ('eligibility_tls', r'(?m)^(?=[^\r\n]*Eligibility check)[^\r\n]*TLS handshake timeout'),
    ('eligibility_eof', r'(?m)^(?=[^\r\n]*Eligibility check)[^\r\n]*\bEOF\b'),
    ('eligibility', r'Eligibility check failed'),
    ('authentication', r'Authentication required'),
    ('known_model', r'is not recognized as a known model'),
)
# Only for result.error; stderr must still match STDERR_RULES.
# Wording observed 2026-10-16 when stderr said "Authentication required".
RESULT_ERROR_RULES = (
    ('authentication_result', r'^authentication failed or timed out$'),
)


# result.error and stderr must describe the same kind of failure.
RULE_FAMILY = {'eligibility_tls': 'eligibility', 'eligibility_eof': 'eligibility', 'eligibility': 'eligibility',
               'authentication': 'authentication', 'authentication_result': 'authentication',
               'known_model': 'known_model'}


def consistent_rule(result_error, stderr):
    """Return the stderr rule name if result.error and stderr match rules of the same family."""
    require(isinstance(result_error, str) and isinstance(stderr, str), 'error text missing')
    srule = next((name for name, pattern in STDERR_RULES if re.search(pattern, stderr)), None)
    require(srule is not None, 'stderr not whitelisted')
    rfamilies = {RULE_FAMILY[name] for name, pattern in STDERR_RULES + RESULT_ERROR_RULES
                 if re.search(pattern, result_error)}
    require(bool(rfamilies), 'result error not whitelisted')
    require(RULE_FAMILY[srule] in rfamilies, 'result error and stderr disagree')
    return srule


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def attempt_stop(review):
    """Read both explicit attempt STOP and the existing queue's str(stopped)."""
    if review.get('reason') == 'attempt STOP':
        return review['unit'], None
    stopped = ast.literal_eval(review['reason'])
    require(isinstance(stopped, dict), 'not attempt STOP')
    unit = stopped['unit']
    stop_verdict(stopped['reason'], unit)
    return unit, stopped


def stop_verdict(reason, unit):
    for prefix in ('attempt STOP: ', unit + ': '):
        if reason.startswith(prefix):
            final = ast.literal_eval(reason[len(prefix):])
            require(isinstance(final, dict) and final.get('stop') is True, 'not attempt STOP')
            return final
    raise ValueError('not attempt STOP')


def attempt_time(stem):
    attempt = R.load_json(str(stem) + '.attempt.json', None)
    stamp = attempt.get('meta', {}).get('datetime') if isinstance(attempt, dict) else None
    require(stamp is not None, 'ambiguous_attempt')
    parsed = dt.datetime.fromisoformat(stamp)
    require(parsed.tzinfo is not None, 'ambiguous_attempt')
    return parsed.timestamp()


def checkpoint_evidence(root, model, stage, meta):
    sessions = meta.get('sessions')
    fp_id = meta.get('fingerprint_id')
    require(isinstance(sessions, list), 'invalid sessions registry')
    require(isinstance(fp_id, str) and bool(fp_id), 'missing fingerprint_id')
    require(all(isinstance(s, dict) and s.get('closed_ok') and not s.get('invalid')
                and s.get('fingerprint_id') == fp_id
                and isinstance(s.get('unit'), str) and bool(s['unit'])
                and isinstance(s.get('session_id'), str) and bool(s['session_id'])
                for s in sessions), 'invalid registered session')
    units = {s['unit'] for s in sessions}
    require(len(units) == len(sessions)
            and len({s['session_id'] for s in sessions}) == len(sessions),
            'duplicate registered session')
    rp = root / ('results_%s_%s.jsonl' % (stage, file_config('agy:' + model)))
    lines = rp.read_text(encoding='utf-8').splitlines() if rp.exists() else []
    # load_records tolerates crash debris, so parse every physical line first.
    parsed = [json.loads(line) for line in lines]
    require(all(isinstance(r, dict) and isinstance(r.get('unit'), str)
                and bool(r['unit']) for r in parsed), 'invalid result record')
    registered = len(sessions)
    session_ids = {s['session_id'] for s in sessions}
    registered_rows = [(number, record) for number, record in enumerate(parsed, 1)
                       if record.get('session_id') in session_ids]
    require(len(registered_rows) == registered, 'result count mismatch')
    valid = R.valid_records([record for _, record in registered_rows], sessions, fp_id)
    require(len(valid) == registered, 'registered checkpoint filtered out')
    registered_positions = {record['unit']: number for number, record in registered_rows}
    stale_results = []
    for number, record in enumerate(parsed, 1):
        if record.get('session_id') in session_ids:
            continue
        unit = record['unit']
        if registered_positions.get(unit, 0) > number:
            stale_results.append({'unit': unit, 'line_number': number})
        else:
            require(number == len(lines) and unit not in units,
                    'unregistered result not redone later or current last row')
    return registered, len(lines), stale_results


def access_evidence(root, model, row):
    stage = row['stage']
    require(stage in ('dev', 'formal'), 'invalid stage')
    name = r'run_meta_(dev|formal)_agy_' + re.escape(model) + r'\.json'
    match = re.fullmatch(r"\[WinError 5\] .*: '(?P<tmp>.+" + name
                         + r"\.[0-9a-f]{32}\.tmp)' -> '(?P<dst>.+run_meta_\2_agy_"
                         + re.escape(model) + r"\.json)'", row['needs_review']['reason'])
    require(match is not None, 'not run_meta access_denied')
    mp = root / ('run_meta_%s_%s.json' % (stage, file_config('agy:' + model)))
    tmp = Path(match['tmp'])
    require(Path(match['dst']).resolve() == mp.resolve()
            and tmp.parent.resolve() == mp.parent.resolve()
            and tmp.name.startswith(mp.name + '.'),
            'access_denied path mismatch')
    meta = R.load_json(mp, None)
    require(isinstance(meta, dict) and 'stopped' in meta and meta['stopped'] is None,
            'access_denied stopped metadata')
    require(not Path(str(mp) + '.stop.json').exists(), 'persistent stop file')
    registered, lines, stale_results = checkpoint_evidence(root, model, stage, meta)
    return mp, meta, tmp, registered, lines, stale_results


def results_access_evidence(root, model, row):
    stage = row['stage']
    require(stage in ('dev', 'formal'), 'invalid stage')
    match = re.fullmatch(r"\[Errno 13\] Permission denied: '(?P<path>.+)'",
                         row['needs_review']['reason'])
    require(match is not None, 'not results access_denied')
    cfg = file_config('agy:' + model)
    rp = root / ('results_%s_%s.jsonl' % (stage, cfg))
    require(Path(match['path']).resolve() == rp.resolve(), 'results path mismatch')
    mp = root / ('run_meta_%s_%s.json' % (stage, cfg))
    meta = R.load_json(mp, None)
    require(isinstance(meta, dict) and 'stopped' in meta and meta['stopped'] is None,
            'results access_denied stopped metadata')
    require(not Path(str(mp) + '.stop.json').exists(), 'persistent stop file')
    registered, lines, stale_results = checkpoint_evidence(root, model, stage, meta)
    with rp.open('rb') as f:
        while f.read(1024 * 1024):
            pass
    return mp, registered, lines, stale_results, rp


def evidence(root, model, row):
    unit, review_stop = attempt_stop(row['needs_review'])
    stage = row['stage']
    require(stage in ('dev', 'formal'), 'invalid stage')
    cfg = file_config('agy:' + model)
    mp = root / ('run_meta_%s_%s.json' % (stage, cfg))
    sp = Path(str(mp) + '.stop.json')
    stop = R.load_json(sp, None)
    meta = R.load_json(mp, None)
    require(isinstance(stop, dict) and stop.get('unit') == unit, 'stop unit mismatch')
    require(meta['stopped'] == stop, 'stop metadata mismatch')
    require(review_stop is None or review_stop == stop, 'review stop mismatch')
    require(stop.get('units', [unit]) == [unit], 'multiple stopped units')
    require(meta.get('active_unit') in (None, unit), 'active unit mismatch')
    prefix = R._safe(unit) + '_a'
    raw = root / 'raw' / ('run_%s_%s' % (stage, cfg))
    # Include incomplete attempts: never fall back to an older complete pair.
    candidates = set()
    for suffix in ATTEMPT_SUFFIXES:
        for path in raw.glob(prefix + '*' + suffix):
            stem = path.name[:-len(suffix)]
            candidates.add(stem)
    require(bool(candidates), 'attempt files missing')
    # Retries are numbered by run_unit; mtime can change when old files are copied.
    numbers = {name: re.fullmatch(re.escape(prefix) + r'(\d+)_.+', name)
               for name in candidates}
    require(all(numbers.values()), 'ambiguous_attempt')
    latest = max(int(match[1]) for match in numbers.values())
    winners = [name for name, match in numbers.items() if int(match[1]) == latest]
    tied_number = len(winners) > 1
    if tied_number:
        try:
            times = {name: attempt_time(raw / name) for name in winners}
        except (ValueError, TypeError, AttributeError, OSError) as exc:
            raise ValueError('ambiguous_attempt') from exc
        winners = [name for name, stamp in times.items() if stamp == max(times.values())]
        require(len(winners) == 1, 'ambiguous_attempt')
    stem = raw / winners[0]
    attempt = R.load_json(str(stem) + '.attempt.json', None)
    final = attempt['final']
    reasons = final.get('reasons')
    require(final.get('state') == 'check_failed' and final.get('stop') is True
            and isinstance(reasons, list) and bool(reasons)
            and set(reasons) <= ALLOWED_REASONS, 'not eligible check_failed reasons')
    require(stop_verdict(stop['reason'], unit) == final,
            'attempt verdict mismatch')
    stream_bytes = Path(str(stem) + '.stream.jsonl').read_bytes()
    events = [json.loads(line) for line in stream_bytes.decode('utf-8').splitlines()]
    require(len(events) == 1 and isinstance(events[0], dict)
            and set(events[0]) == {'event', 'result'} and events[0]['event'] == 'result',
            'not single result event')
    result = events[0]['result']
    require(isinstance(result, dict) and set(result) == {
        'conversation_id', 'status', 'response', 'error', 'duration_seconds',
        'num_turns', 'usage'}, 'invalid result fields')
    usage = result['usage']
    require(isinstance(usage, dict) and set(usage) == {
        'input_tokens', 'output_tokens', 'thinking_tokens', 'cache_read_tokens',
        'total_tokens'} and all(type(v) is int and v == 0 for v in usage.values()),
        'not zero usage')
    duration = result['duration_seconds']
    require(type(duration) in (int, float) and math.isfinite(duration) and duration >= 0,
            'invalid duration_seconds')
    require(result['conversation_id'] == '' and result['status'] == 'ERROR'
            and type(result['num_turns']) is int and result['num_turns'] == 0
            and result['response'] == '',
            'not empty pre-conversation failure')
    stderr = Path(str(stem) + '.stderr.txt').read_text(encoding='utf-8')
    rule = consistent_rule(result['error'], stderr)
    _, _, stale_results = checkpoint_evidence(root, model, stage, meta)
    selection = {'attempt_file': str(Path(str(stem) + '.attempt.json').relative_to(root)),
                 'attempt_time_source': 'meta.datetime' if tied_number else 'attempt_number',
                 'attempt_sort_value': {'number': latest},
                 'stale_results': stale_results}
    if selection['attempt_time_source'] == 'meta.datetime':
        selection['attempt_sort_value']['timestamp'] = times[winners[0]]
    return unit, mp, sp, meta, rule, hashlib.sha256(stream_bytes).hexdigest(), selection


def clear(root, log_date, retry_wait_minutes=30, now=None, log=print):
    root = Path(root)
    require(retry_wait_minutes >= 0, 'negative retry wait')
    require(dt.date.fromisoformat(log_date).isoformat() == log_date, 'invalid log date')
    now = now or dt.datetime.now().astimezone()
    raw = root / 'raw'
    raw.mkdir(parents=True, exist_ok=True)
    count = 0
    with R.ModelLock(raw / 'queue.lock'):
        state_path = raw / 'queue_state.json'
        state = R.load_json(state_path, {'models': {}})
        backup = raw / ('auto_clear_' + log_date)
        audit_path = backup / 'audit.jsonl'
        audit = [json.loads(line) for line in audit_path.read_text(encoding='utf-8').splitlines()
                 if line.strip()] if audit_path.exists() else []
        for model, row in state['models'].items():
            if row.get('needs_review') is None:
                continue
            try:
                ordinal = sum(a['model'] == model for a in audit) + 1
                require(ordinal <= DAILY_LIMIT, 'nightly limit reached')
                wait = max(retry_wait_minutes, (30, 60, 120)[min(ordinal, 3) - 1])
                reason = row['needs_review']['reason']
                access = reason.startswith('[WinError 5]')
                if access:
                    mp, meta, tmp, registered, lines, stale_results = access_evidence(root, model, row)
                    details = {'kind': 'access_denied', 'registered_count': registered,
                               'result_count': lines, 'tmp': str(tmp),
                               'stale_results': stale_results}
                elif reason.startswith('[Errno 13]'):
                    mp, registered, lines, stale_results, rp = results_access_evidence(root, model, row)
                    details = {'kind': 'results_access_denied', 'registered_count': registered,
                               'result_count': lines, 'stale_results': stale_results,
                               'path': str(rp)}
                else:
                    unit, mp, sp, meta, rule, digest, selection = evidence(root, model, row)
                    details = {'kind': 'pre_conversation', 'unit': unit,
                               'stderr_rule': rule, 'stream_sha256': digest, **selection}
            except (R.Stop, ValueError, SyntaxError, KeyError, TypeError, AttributeError, OSError) as exc:
                log('AUTO_CLEAR_SKIP %s %s' % (model, str(exc).replace('\n', ' ')))
                continue
            dest = backup / (model + '_' + uuid.uuid4().hex)
            dest.mkdir(parents=True)
            for source in (state_path, mp):
                shutil.copy2(source, dest / source.name)
            # Reserve the audit/count before mutation; a partial failure fails closed.
            entry = dict(details, model=model, datetime=now.isoformat(),
                         ordinal=ordinal, wait_minutes=wait,
                         backup=str(dest.relative_to(root)))
            with audit_path.open('a', encoding='utf-8', newline='\n') as f:
                f.write(json.dumps(entry, ensure_ascii=False) + '\n')
                f.flush()
                os.fsync(f.fileno())
            audit.append(entry)
            if access:
                if tmp.exists():
                    tmp.rename(dest / tmp.name)
            elif details['kind'] == 'pre_conversation':
                meta['stopped'] = None
                R.save_json(mp, meta)
                sp.rename(dest / sp.name)
            row['needs_review'] = None
            row['skipped_until'] = (now + dt.timedelta(minutes=wait)).isoformat()
            R.save_json(state_path, state)
            count += 1
            log('AUTO_CLEAR %s %s ordinal=%d wait_minutes=%s' %
                (model, details['kind'], ordinal, wait))
    return count


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    ap.add_argument('--log-date', required=True)
    ap.add_argument('--retry-wait-minutes', type=float, default=30)
    args = ap.parse_args()
    count = clear(args.root, args.log_date, args.retry_wait_minutes)
    print('AUTO_CLEAR_COUNT %d' % count)
    # 0 = none; 10 = at least one cleared; other codes are errors.
    return 10 if count else 0


if __name__ == '__main__':
    raise SystemExit(main())
