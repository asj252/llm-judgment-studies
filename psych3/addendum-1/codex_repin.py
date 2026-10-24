"""Manual, repeatable repin steps. Never invokes a subject or runs formal items.

  ..\\suppression\\llm_python.cmd -X utf8 -B codex_repin.py archive-dev
  ..\\suppression\\llm_python.cmd -X utf8 -B codex_repin.py archive-dev --tag v2
  ..\\suppression\\llm_python.cmd -X utf8 -B codex_repin.py refreeze
"""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import tempfile

import analyse_psych3 as analysis
import run_psych3 as runner
import run_codex_psych3_pinned as pinned

HERE = Path(__file__).resolve().parent
ARCHIVE = 'raw/archive_dev_codex_pre_repin_20261023'
OLD_FREEZE = 'raw/archive_freeze_codex_v1.json'
DIFF = 'raw/codex_repin_freeze_diff.json'
DEV_ROOTS = ('results_dev_codex.jsonl', 'run_meta_dev_codex.json', 'raw/run_dev_codex')


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def accepted_dev(base=HERE, *, require_complete=True):
    """Read-only acceptance with current pinned path and fingerprint, no executable calls."""
    base = Path(base)
    rp, mp, _ = runner.paths(base, 'dev', 'codex')
    meta = runner.load_json(mp, {'sessions': []})
    sessions = meta['sessions']
    if meta.get('stopped') or any(s.get('status') == 'running' for s in sessions):
        raise RuntimeError('running/stopped development session requires human review')
    if not sessions:
        if rp.exists() and runner.load_records(rp):
            raise RuntimeError('unregistered development result')
        if require_complete:
            raise RuntimeError('development acceptance required before refreeze')
        return None
    good = [s for s in sessions if s.get('closed_ok') and not s.get('invalid')]
    fids = {s['fingerprint_id'] for s in sessions}
    if not good or len(fids) != 1:
        raise RuntimeError('one accepted development fingerprint required')
    saved = good[0]['fingerprint']
    config = pinned.executable_config(base)
    version = runner.load_json(base / 'codex_pin.json', {})['version']
    sm = saved['subject_meta']
    if (sm['exe'] != config['exe'] or sm['version'] != version or
            sm.get('exe_sha256') != config['sha256'] or
            'model_entry_sha256' in sm or 'model_entry' in sm):
        raise RuntimeError('development must be rerun with the pinned executable, version and stable metadata')
    rows = runner.build_manifest(base)
    fp, fid = runner.fingerprint(rows, 'codex', saved['subject_meta'], base)
    if fids != {fid} or any(s['fingerprint'] != fp for s in sessions):
        raise RuntimeError('development fingerprint differs from current pinned materials')
    records, _ = analysis.load_valid(rp, mp, fid, 'codex', strict=True)
    verdict = analysis.accounting(rows, records, 'dev')
    expected = {r['unit_id'] for r in rows if r['split'] == 'dev'}
    done = {r['unit'] for r in records if r['status'] in ('ok', 'missing', 'tool_contaminated')}
    if done != expected:
        if require_complete:
            raise RuntimeError('complete development acceptance required before refreeze')
        return None
    if not verdict['acceptance']:
        raise RuntimeError('development acceptance failed')
    return dict(fingerprint=fp, fingerprint_id=fid, acceptance=verdict)


def archive_name(tag=None):
    if tag is None:
        return ARCHIVE
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]*', tag):
        raise ValueError('archive tag must contain only letters, digits, underscores or hyphens')
    return 'raw/archive_dev_codex_pre_repin_20261024_' + tag


def no_formal_activity(base):
    rp, mp, _ = runner.paths(base, 'formal', 'codex')
    if (rp.exists() and rp.stat().st_size) or runner.load_json(mp, {}).get('sessions'):
        raise RuntimeError('archive/refreeze must precede every codex formal item/session')


def archive_dev(base=HERE, *, tag=None):
    """Journal before moving; resume interrupted moves, never rearchive a new dev run."""
    base = Path(base)
    no_formal_activity(base)
    dev_meta = runner.load_json(base / 'run_meta_dev_codex.json', {})
    if any(s.get('status') == 'running' for s in dev_meta.get('sessions', [])):
        raise RuntimeError('running development session cannot be archived')
    target = base / archive_name(tag)
    if not target.resolve().is_relative_to(base.resolve()) or target.is_symlink():
        raise RuntimeError('archive target outside base or linked')
    manifest_path = target / 'manifest.json'
    if manifest_path.exists():
        manifest = runner.load_json(manifest_path, {})
    else:
        roots = [base / name for name in DEV_ROOTS]
        if not all(p.exists() for p in roots):
            raise RuntimeError('all three original development artifacts required for archive-dev')
        files = {}
        for root in roots:
            for p in ([root] if root.is_file() else sorted(root.rglob('*'))):
                if p.is_symlink() or not p.resolve().is_relative_to(base.resolve()):
                    raise RuntimeError('archive refuses links or paths outside base')
                if p.is_file():
                    files[p.relative_to(base).as_posix()] = digest(p)
        manifest = dict(roots=list(DEV_ROOTS), files=files, complete=False)
        runner.save_json(manifest_path, manifest)
    if manifest['roots'] != list(DEV_ROOTS):
        raise RuntimeError('archive manifest roots differ')
    for name, sha in manifest['files'].items():
        if Path(name).is_absolute() or '..' in Path(name).parts:
            raise RuntimeError('unsafe archive manifest path')
        archived = target / name
        source = base / name
        p = archived if archived.exists() else source
        if (manifest['complete'] and not archived.is_file()) or not p.is_file() or digest(p) != sha:
            raise RuntimeError('archive integrity mismatch: ' + name)
    if manifest['complete']:
        return manifest
    for name in manifest['roots']:
        source, dest = base / name, target / name
        if dest.exists():
            if source.exists():
                raise RuntimeError('both source and archive exist: ' + name)
            continue
        # Detect extra files added since the journal was created, before moving.
        actual = {p.relative_to(base).as_posix() for p in
                  ([source] if source.is_file() else source.rglob('*')) if p.is_file()}
        expected = {p for p in manifest['files'] if p == name or p.startswith(name + '/')}
        if actual != expected:
            raise RuntimeError('archive source file list changed: ' + name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        # Verify both absolute targets immediately before the directory move.
        if (source.is_symlink() or dest.is_symlink() or
                not source.resolve().is_relative_to(base.resolve()) or
                not dest.resolve().is_relative_to(target.resolve())):
            raise RuntimeError('archive move outside base or linked')
        shutil.move(str(source), str(dest))
    for name, sha in manifest['files'].items():
        if digest(target / name) != sha:
            raise RuntimeError('archive read-back mismatch: ' + name)
    manifest['complete'] = True
    runner.save_json(manifest_path, manifest)
    return manifest


def field_diff(old, new, prefix=''):
    changes = []
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(old.keys() | new.keys()):
            label = prefix + '.' + key if prefix else key
            if key not in old or key not in new:
                changes.append(dict(field=label, old=old.get(key), new=new.get(key),
                                    old_present=key in old, new_present=key in new))
            else:
                changes.extend(field_diff(old[key], new[key], label))
    elif old != new:
        changes.append(dict(field=prefix, old=old, new=new))
    return changes


def refreeze(base=HERE, *, tag='v2'):
    """Build via the existing freeze on a scratch copy, then atomically install."""
    base = Path(base)
    no_formal_activity(base)
    archive_manifest = base / archive_name(tag) / 'manifest.json'
    if not archive_manifest.exists() or not runner.load_json(archive_manifest, {}).get('complete'):
        raise RuntimeError('completed archive-dev required before refreeze')
    archive_dev(base, tag=tag)  # verify archives without moving the new dev
    pinned.verified_exe(base)
    evidence = accepted_dev(base)
    path = base / 'analysis_freeze_psych3.json'
    before_bytes = path.read_bytes()
    before = json.loads(before_bytes)
    archive = base / OLD_FREEZE
    old = runner.load_json(archive, None) if archive.exists() else before['formal']['codex']
    names = old['hypotheses']
    if len(names) != 11 or len(set(names)) != 11:
        raise RuntimeError('original eleven codex hypotheses required')
    expected_fp = deepcopy(old['fingerprint'])
    config = pinned.executable_config(base)
    expected_fp['subject_meta']['exe'] = config['exe']
    expected_fp['subject_meta'].pop('model_entry_sha256', None)
    expected_fp['subject_meta']['exe_sha256'] = config['sha256']
    if evidence['fingerprint'] != expected_fp:
        fields = ', '.join(c['field'] for c in field_diff(expected_fp, evidence['fingerprint']))
        raise RuntimeError('repin allows only exe, removal of model_entry_sha256 and addition of exe_sha256: ' + fields)
    scratch = deepcopy(before)
    del scratch['formal']['codex']
    with tempfile.TemporaryDirectory(prefix='codex-refreeze-', dir=base / 'raw') as tmp:
        candidate_path = Path(tmp) / path.name
        runner.save_json(candidate_path, scratch)
        new = analysis.freeze('formal', 'codex', base=base, freeze_path=candidate_path,
                              B=5000, names=names)
        candidate = runner.load_json(candidate_path, {})
        if new['hypotheses'] != names or new['code'] != old['code'] or new['materials'] != old['materials']:
            raise RuntimeError('hypotheses, analysis code or materials changed')
        expected_new = deepcopy(old)
        expected_new.update(fingerprint=expected_fp, fingerprint_id=evidence['fingerprint_id'],
                            development_acceptance=evidence['acceptance'])
        if new != expected_new or candidate['formal']['codex'] != new:
            raise RuntimeError('rebuilt codex entry changed outside the refreeze whitelist')
        remaining = deepcopy(candidate)
        del remaining['formal']['codex']
        if remaining != scratch:
            raise RuntimeError('non-codex freeze entries changed')
        if before['formal']['codex'] not in (old, new):
            raise RuntimeError('current codex freeze is neither original nor the rebuilt entry')
        changes = field_diff(old, new)
        # Persist provenance first; a crash before replace is safe to repeat.
        if not archive.exists():
            runner.save_json(archive, old)
        receipt = dict(old_fingerprint_id=old['fingerprint_id'], new_fingerprint_id=new['fingerprint_id'],
                       executable=pinned.executable_config(base), differences=changes)
        diffpath = base / DIFF
        if not diffpath.exists() or runner.load_json(diffpath, {}) != receipt:
            runner.save_json(diffpath, receipt)
        if path.read_bytes() != before_bytes:
            raise RuntimeError('freeze changed concurrently; refusing replacement')
        if candidate != before:
            candidate_path.replace(path)
    return changes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('step', choices=('archive-dev', 'refreeze'))
    parser.add_argument('--tag', help='archive generation (use v2 for the catalog-entry rerun; refreeze defaults to v2)')
    args = parser.parse_args(argv)
    helpers = runner.agy_helpers()
    try:
        # Same cross-process lock for dev, formal and both manual steps.
        with helpers.ModelLock(HERE / 'night_codex.lock'):
            result = (archive_dev(HERE, tag=args.tag) if args.step == 'archive-dev'
                      else refreeze(HERE, tag=args.tag or 'v2'))
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, KeyError, RuntimeError, analysis.Mismatch, helpers.Stop) as exc:
        print(f'REFUSED: {exc}')
        return 2


if __name__ == '__main__':
    sys.exit(main())
