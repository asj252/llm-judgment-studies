"""Single-configuration psych3 runner. Importing this module never calls a model.

Session/admission semantics adapted from dnli/run.py; agy retry/backoff and
snapshot semantics adapted from dnli-agy/run_agy.py. Legacy adapters are reused.
"""
import argparse
import importlib.util
import json
import os
import random
import sys
import time
import uuid
import unicodedata
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from contextlib import nullcontext
from pathlib import Path
from threading import Event, Lock

# Isolated mode (-I) drops the script directory from sys.path; add it back (as dnli/run.py does).
sys.path.insert(0, str(Path(__file__).resolve().parent))
from manifest import HERE, build_manifest, ids_only, sha, write_manifest  # noqa: E402
import parse_a
import parse_d


def legacy(folder, name):
    """Load a runner under a unique name; retain its own dependency references."""
    path = HERE.parent / folder
    before = list(sys.path)
    # These legacy modules use bare sibling imports. Avoid sharing their names
    # with an embedding program; the loaded module keeps its actual references.
    names = ('parse', 'prompts', 'configs', 'agy_subject', 'workspace_temp')
    saved = {k: sys.modules.pop(k) for k in names if k in sys.modules}
    sys.path.insert(0, str(path))
    try:
        spec = importlib.util.spec_from_file_location('_psych3_' + folder.replace('-', '_') + '_' + name,
                                                      path / (name + '.py'))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path[:] = before
        for k in names:
            sys.modules.pop(k, None)
        sys.modules.update(saved)


DNLI = legacy('dnli', 'run')
Stop = DNLI.Stop
load_json, load_records, valid_records = DNLI.load_json, DNLI.load_records, DNLI.valid_records
BASE_SEED = DNLI.BASE_SEED
FROZEN_MATERIALS = ('a_eligibility.json', 'a_anchors.json', 'a_selfwritten_items.json',
                    'a_split.json', 'b_pairing.json', 'b_canary_log.json',
                    'b_manifest.json', 'conjunction_items.json', 'items_e_draft.json')


def agy_helpers():
    return legacy('dnli-agy', 'run_agy')


def save_json(path, obj):
    """Atomic metadata replacement, following dnli-agy.save_json."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with tmp.open('w', encoding='utf-8', newline='\n') as stream:
        json.dump(obj, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)


def config_name(cfg):
    if cfg in DNLI.CONFIGS:
        return cfg
    if cfg.startswith('agy:'):
        agy = legacy('dnli-agy', 'agy_subject')
        agy.validate_model_name(cfg[4:])
        return 'agy_' + cfg[4:]
    raise Stop('unknown configuration: ' + cfg)


def validate_workers(cfg, workers):
    config_name(cfg)
    DNLI.validate_workers(cfg, workers)


def make_schedule(rows, which, cfg, exps=None):
    """Fixed configuration seed, shuffled clusters then shuffled within cluster."""
    offset = DNLI.CONFIG_OFFSET.get(cfg, int(sha(cfg.encode())[:8], 16))
    rng = random.Random(BASE_SEED[which] * 10 + offset)
    groups = {}
    for row in rows:
        if row['split'] == which and (exps is None or row['exp'] in exps):
            groups.setdefault((row['exp'], row['cluster']), []).append(row)
    keys = sorted(groups)
    rng.shuffle(keys)
    out = []
    for key in keys:
        group = sorted(groups[key], key=lambda r: r['unit_id'])
        rng.shuffle(group)
        out.extend(group)
    return out


def fingerprint(rows, cfg, subject_meta, base=HERE):
    base = Path(base)
    files = ['manifest.py', 'run_psych3.py', '../dnli/parse.py', '../dnli/run.py',
             *FROZEN_MATERIALS]
    files += [p.name for pattern in ('prompts_*.py', 'parse_*.py') for p in sorted(base.glob(pattern))]
    files += (['../dnli-agy/' + n for n in ('agy_subject.py', 'run_agy.py', 'configs.py',
                                         'workspace_temp.py', 'agent/dnli-subject.md')]
              if cfg.startswith('agy:') else ['../dnli/local_subject.py']
              if cfg in DNLI.LOCAL else ['../dnli/codex_subject.py', '../vs-pilot/subject.py'])
    fp = {f: sha((base / f).read_bytes()) for f in files}
    serialized = (json.dumps(ids_only(rows), ensure_ascii=False, indent=2) + '\n').encode('utf-8')
    if not (base / 'manifest_ids.json').exists() or (base / 'manifest_ids.json').read_bytes() != serialized:
        raise Stop('manifest_ids.json differs from current materials; regenerate manifest')
    # Bind parser-only context separately; the public IDs schema stays stable.
    context = [{k: row[k] for k in ('unit_id', 'quantity_unit', 'order') if k in row}
               for row in rows]
    fp.update(parse_context=sha(json.dumps(context, ensure_ascii=False, sort_keys=True).encode('utf-8')),
              manifest_ids=sha(serialized), config=cfg, subject_meta=subject_meta,
              retry_policy={'parse': 1, 'codex_contamination': 1, 'disconnect_streak': 3,
                            'agy_resample_streak': 3, 'agy_rate': [300, 3600, 21600, 259200]})
    return fp, sha(json.dumps(fp, ensure_ascii=False, sort_keys=True).encode('utf-8'))


def judge_text(row, text, cfg='codex'):
    if cfg.startswith('agy:'):
        if row['parser'] == 'dnli_v2':
            ok, result = agy_helpers().judge_text(row['ask'], text)
            return dict(result, ok=ok)
        normalized = ''.join(' ' if unicodedata.category(ch) == 'Zs' else ch for ch in text)
        raw = judge_text(row, text)
        result = judge_text(row, normalized)
        return dict(result, parse_raw_ok=raw['ok'], normalized=normalized != text)
    if row['parser'] == 'parse_a':
        return parse_a.PARSERS[row['ask']](text, row.get('quantity_unit'))
    if row['parser'] == 'parse_d':
        return parse_d.parse_response(text, 'J', row['ask'], row['order'])
    if row['parser'] != 'dnli_v2':
        raise ValueError('unknown parser')
    return DNLI.parse.PARSERS[row['ask']](text)


def run_unit(cfg, which, row, subj, rawdir, policy=None, progress=lambda: None,
             check_snapshot=lambda snap, uid: None):
    """First admissible value wins; retries retain every attempt, including stops."""
    attempts, parse_left, void_left, streak, last_state = [], 1, 1, 0, None
    record = {k: row[k] for k in ids_only([row])[0]}
    record.update(unit=row['unit_id'], config=cfg, result=None, attempts=attempts)
    agy = cfg.startswith('agy:')
    while True:
        if policy:
            try:
                policy.check_unit_duration()
            except Exception as error:
                exc = Stop(str(error), True)
                record.update(status='stopped', n_attempts=len(attempts))
                exc.record = record
                raise exc from error
        n = len(attempts)
        seed = DNLI.call_seed(cfg, (row['unit_id'],), n, which)
        tag = sha(row['unit_id'].encode())[:24] + '__' + uuid.uuid4().hex + '_a' + str(n)
        try:
            response = subj.attempt(row['ask'], row['prompt'], tag, seed)
        except Exception as exc:
            response = dict(text='', final={'state': 'call_error', 'stop': True},
                            meta={'error': str(exc)}, truncated=False)
        # Wrapper-level transcript: the original adapters also retain their own
        # raw artifacts. No text enters the JSONL or public manifest.
        rawpath = Path(rawdir) / (tag + '.json')
        rawpath.parent.mkdir(parents=True, exist_ok=True)
        save_json(rawpath, {'prompt': row['prompt'], **response})
        fin = response['final']
        state = fin['state']
        att = dict(attempt=n, seed=seed, state=state, final=fin,
                   truncated=response.get('truncated', False), meta=response.get('meta', {}),
                   raw_path=str(rawpath.resolve()), raw_sha256=sha(rawpath.read_bytes()), parsed=None)
        attempts.append(att)
        record['n_attempts'] = len(attempts)
        def stop(message, invalidate=False):
            record['status'] = 'stopped'
            exc = Stop(message, invalidate)
            exc.record = record
            raise exc
        if agy:
            try:
                check_snapshot(response['meta']['snapshot'], row['unit_id'])
            except Exception as exc:
                stop('snapshot: ' + str(exc), True)
        if state == 'rate_limited' and agy:
            try:
                policy.limited(progress)
            except Exception as exc:
                stop(str(exc), True)
            continue
        if policy:
            policy.clear()
        if state == 'disconnect' or (agy and fin.get('resample') and state != 'truncated'):
            streak = streak + 1 if last_state == state else 1
            last_state = state
            if streak >= 3:
                stop('3 consecutive ' + state, agy)
            continue
        streak, last_state = 0, None
        if fin.get('stop'):
            stop(state + ': ' + str(fin.get('reasons', [])),
                 agy or fin.get('invalidate_session', False) or state == 'check_failed')
        if fin.get('resample') and state != 'truncated':
            if void_left:
                void_left -= 1
                continue
            record['status'] = 'tool_contaminated'
            return record
        if state not in ('ok', 'truncated'):
            stop('unrecognized inclusion state: ' + state, True)
        parsed = ({'ok': False, 'error': 'truncated'} if att['truncated'] or state == 'truncated'
                  else judge_text(row, response['text'], cfg))
        att.update(parsed=parsed['ok'], parse=parsed)
        if parsed['ok']:
            record.update(status='ok', result=parsed)
            return record
        if parse_left:
            parse_left -= 1
            continue
        record['status'] = 'missing'
        return record


def paths(base, which, cfg):
    name = config_name(cfg)
    base = Path(base)
    return (base / f'results_{which}_{name}.jsonl', base / f'run_meta_{which}_{name}.json',
            base / 'raw' / f'run_{which}_{name}')


def execute(which, cfg, rows, subj, fp, fp_id, base=HERE, exps=None, workers=1,
            policy=None, log=print):
    validate_workers(cfg, workers)
    if which == 'formal':
        from analyse_psych3 import Mismatch, check_formal_freeze
        try:
            check_formal_freeze(cfg, fp, fp_id, base)
        except Mismatch as exc:
            raise Stop(str(exc)) from exc
    agy = cfg.startswith('agy:')
    if agy and policy is None:
        policy = agy_helpers().RetryPolicy()
    read_records = agy_helpers().load_records if agy else load_records
    rp, mp, rawdir = paths(base, which, cfg)
    rawdir.mkdir(parents=True, exist_ok=True)
    meta = load_json(mp, {'sessions': []})
    if meta.get('stopped'):
        raise Stop('persistent agy stop requires review: ' + str(meta['stopped']))
    sessions = meta['sessions']
    for session in sessions:
        if session.get('status') == 'running':
            session.update(status='abandoned', invalid=True, closed_ok=False)
    save_json(mp, meta)
    if any(s['fingerprint_id'] != fp_id for s in sessions):
        raise Stop('fingerprint differs from registered session')
    records = read_records(rp)
    if not agy and any(r.get('session_id') not in {s['session_id'] for s in sessions} for r in records):
        raise Stop('unregistered result')
    def completed(rs, ss):
        for s in ss:
            if not s.get('closed_ok') or s.get('invalid') or s['fingerprint_id'] != fp_id:
                continue
            registered = [r for r in rs if r.get('session_id') == s['session_id']]
            digest = sha(json.dumps(registered, sort_keys=True, ensure_ascii=False).encode('utf-8'))
            if s.get('records_sha256') != digest:
                raise Stop('closed session result integrity failed')
            for r in registered:
                for attempt in r.get('attempts', []):
                    raw = Path(attempt['raw_path'])
                    if not raw.is_file() or sha(raw.read_bytes()) != attempt['raw_sha256']:
                        raise Stop('raw attempt integrity failed')
        # agy's filter also checks each adapter stream/stderr digest and unit checkpoint.
        if agy:
            helpers = agy_helpers()
            try:
                kept = helpers.valid_records(rs, ss, fp_id)
            except helpers.Stop as exc:
                raise Stop(str(exc)) from exc
        else:
            kept = valid_records(rs, ss, fp_id)
        return {k: r for k, r in kept.items()
                if r['status'] in ('ok', 'missing', 'tool_contaminated')}
    if which == 'formal':
        dr, dm, _ = paths(base, 'dev', cfg)
        dev_meta = load_json(dm, {'sessions': []})
        ds = dev_meta['sessions']
        expected = {r['unit_id'] for r in rows if r['split'] == 'dev'}
        dev = completed(read_records(dr), ds)
        if (dev_meta.get('stopped') or not any(s.get('closed_ok') and not s.get('invalid')
                and s['fingerprint_id'] == fp_id for s in ds)
                or set(dev) != expected):
            raise Stop('complete development set with matching fingerprint required')
        first = sum(bool(rec.get('attempts')) and rec['attempts'][0].get('parsed') is True
                    for rec in dev.values())
        missing = sum(rec['status'] != 'ok' for rec in dev.values())
        n = len(expected)
        if first * 100 < 90 * n or missing * 100 > 2 * n:
            raise Stop(f'development acceptance failed ({cfg}): first parse {first}/{n} '
                       f'({first / n:.2%}, required >=90%); missing {missing}/{n} '
                       f'({missing / n:.2%}, required <=2%)')
        if cfg.startswith('agy:'):
            if meta.get('baseline') not in (None, dev_meta.get('baseline')):
                raise Stop('development/formal environment baselines differ')
            meta['baseline'] = dev_meta.get('baseline')
    done = completed(records, sessions)
    schedule = make_schedule(rows, which, cfg, exps)
    session = dict(session_id=uuid.uuid4().hex, fingerprint=fp, fingerprint_id=fp_id,
                   status='running', closed_ok=False, invalid=False, which=which, config=cfg,
                   workers=workers, started=time.strftime('%Y-%m-%dT%H:%M:%S%z'),
                   schedule_sha256=sha(json.dumps([r['unit_id'] for r in schedule]).encode()),
                   n_schedule=len(schedule), exps=sorted(exps) if exps else list('ABCDE'))
    if not agy:
        sessions.append(session)
    def progress():
        if policy:
            meta['retry_state'] = policy.state
        save_json(mp, meta)
    def check_snapshot(snap, uid):
        baseline = meta.get('baseline')
        if baseline is None:
            meta['baseline'] = dict(snap)
        else:
            # Matches dnli-agy first reported-model enrichment.
            for key, value in snap.items():
                old = baseline.get(key)
                if old is None and key in ('reported_model', 'tools_sha256', 'permission_mode'):
                    baseline[key] = value
                elif value is not None and value != old:
                    raise Stop('environment changed at ' + uid, True)
        progress()
    if policy:
        if meta.get('retry_state'):
            policy.state = meta['retry_state']
    if agy:
        # run_agy semantics: append, read back, register, and close each unit.
        # Unregistered append debris from an interrupted unit is ignored on resume.
        helpers = agy_helpers()
        progress()
        policy.resume_wait(progress)
        for seq, row in enumerate(schedule, 1):
            if row['unit_id'] in done:
                continue
            checkpoint = dict(session, session_id=uuid.uuid4().hex, unit=row['unit_id'])
            meta['active_unit'] = row['unit_id']
            progress()
            started = time.monotonic()
            rec, error = None, None
            try:
                check_snapshot(subj.snapshot((meta.get('baseline') or {}).get('reported_model')),
                               row['unit_id'])
                rec = run_unit(cfg, which, row, subj, rawdir, policy, progress, check_snapshot)
            except Exception as exc:
                error = exc if isinstance(exc, Stop) else Stop(str(exc), True)
                rec = getattr(exc, 'record', None)
            if rec:
                rec.update(session_id=checkpoint['session_id'], fingerprint_id=fp_id,
                           dispatch_seq=seq, wall_seconds=round(time.monotonic() - started, 3))
                with rp.open('a', encoding='utf-8', newline='\n') as stream:
                    if rp.stat().st_size and not rp.read_bytes().endswith(b'\n'):
                        stream.write('\n')
                    stream.write(json.dumps(rec, ensure_ascii=False) + '\n')
                    stream.flush()
                    os.fsync(stream.fileno())
                if helpers.record_hash(read_records(rp)[-1]) != helpers.record_hash(rec):
                    error = Stop('result read-back failed: ' + row['unit_id'], True)
                checkpoint['record_sha256'] = helpers.record_hash(rec)
            checkpoint.update(status='stopped' if error else 'finished',
                              closed_ok=error is None, invalid=error is not None,
                              records_sha256=sha(json.dumps([rec] if rec else [], sort_keys=True,
                                                           ensure_ascii=False).encode('utf-8')))
            sessions.append(checkpoint)
            if error:
                checkpoint['stop_reason'] = str(error)
                meta['stopped'] = str(error)
            else:
                meta['active_unit'] = None
            progress()
            if error:
                return 3, checkpoint
            log(rec['unit_id'] + ' -> ' + rec['status'])
        return 0, sessions[-1] if sessions else session
    progress()
    if policy:
        policy.resume_wait(progress)
    stopped, admission = Event(), Lock()
    pending = iter(r for r in schedule if r['unit_id'] not in done)
    def evaluate(row, seq):
        started = time.monotonic()
        try:
            if cfg.startswith('agy:'):
                check_snapshot(subj.snapshot((meta.get('baseline') or {}).get('reported_model')), row['unit_id'])
            rec = run_unit(cfg, which, row, subj, rawdir, policy, progress, check_snapshot)
            error = None
        except Exception as exc:
            error = exc if isinstance(exc, Stop) else Stop(str(exc), cfg.startswith('agy:'))
            rec = getattr(exc, 'record', None)
            with admission:
                stopped.set()
        if rec:
            rec.update(session_id=session['session_id'], fingerprint_id=fp_id,
                       dispatch_seq=seq, wall_seconds=round(time.monotonic() - started, 3))
        return rec, error
    code, seq = 0, 0
    with ThreadPoolExecutor(max_workers=workers) as pool:
        active = {}
        while True:
            with admission:
                while not stopped.is_set() and len(active) < workers:
                    row = next(pending, None)
                    if row is None:
                        break
                    seq += 1
                    active[pool.submit(evaluate, row, seq)] = seq
            if not active:
                break
            ready, _ = wait(active, return_when=FIRST_COMPLETED)
            for future in sorted(ready, key=active.get):
                active.pop(future)
                rec, error = future.result()
                if rec:
                    with rp.open('a', encoding='utf-8', newline='\n') as stream:
                        stream.write(json.dumps(rec, ensure_ascii=False) + '\n')
                        stream.flush()
                        os.fsync(stream.fileno())
                    log(rec['unit_id'] + ' -> ' + rec['status'])
                if error:
                    code = 3
                    session.update(status='stopped', invalid=session['invalid'] or error.invalidate,
                                   stop_reason=str(error))
                    if cfg.startswith('agy:'):
                        meta['stopped'] = str(error)
    session.update(status='finished' if code == 0 else 'stopped',
                   closed_ok=not session['invalid'], finished=time.strftime('%Y-%m-%dT%H:%M:%S%z'))
    registered = [r for r in load_records(rp) if r.get('session_id') == session['session_id']]
    session['records_sha256'] = sha(json.dumps(registered, sort_keys=True, ensure_ascii=False).encode('utf-8'))
    progress()
    return code, session


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('which', choices=('dev', 'formal'))
    parser.add_argument('config')
    parser.add_argument('--exp', help='comma-separated experiment letters')
    parser.add_argument('--workers', type=int, default=1)
    args = parser.parse_args(argv)
    subj = None
    try:
        validate_workers(args.config, args.workers)
        exps = set(args.exp.split(',')) if args.exp else None
        if exps is not None and not exps <= set('ABCDE'):
            raise Stop('unknown experiment')
        rows = build_manifest()
        # Do not silently replace a frozen manifest during a run.
        if not (HERE / 'manifest_ids.json').exists():
            write_manifest(rows)
        _, _, rawdir = paths(HERE, args.which, args.config)
        helpers = agy_helpers() if args.config.startswith('agy:') else None
        lock = helpers.ModelLock(HERE / (config_name(args.config) + '.lock')) if helpers else nullcontext()
        with lock:
            if helpers:
                subj = helpers.AgySubject(args.config[4:], rawdir)
                subject_meta = dict(model=args.config[4:], baseline=subj.snapshot(),
                                    timeout=subj.timeout, rate_patterns=list(subj.rate_patterns))
                policy = helpers.RetryPolicy()
            else:
                # Legacy adapter methods lazily import their sibling subjects.
                sys.path.insert(0, str(HERE.parent / 'dnli'))
                subj = (DNLI.CodexAdapter(rawdir, Path(os.environ.get('TEMP', '.')) /
                                          ('psych3-work-' + uuid.uuid4().hex))
                        if args.config == 'codex' else DNLI.LocalAdapter(args.config, rawdir))
                subject_meta, policy = subj.meta(), None
            fp, fp_id = fingerprint(rows, args.config, subject_meta)
            code, _ = execute(args.which, args.config, rows, subj, fp, fp_id,
                              exps=exps, workers=args.workers, policy=policy)
            return code
    except (Stop, RuntimeError, ValueError, OSError) as exc:
        print('REFUSED:', exc)
        return 2
    finally:
        target = getattr(subj, 's', subj)
        if target is not None and hasattr(target, 'close'):
            target.close()


if __name__ == '__main__':
    sys.exit(main())
