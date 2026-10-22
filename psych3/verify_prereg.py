"""Offline byte verification. No imports of runners, model clients, or raw data."""
import hashlib
import json
from pathlib import Path, PurePosixPath

THIRD_PARTY = frozenset({
    'b_manifest.json', 'raw_items_a.json', 'raw_items_b.json',
    'raw_manifest.json', 'raw_probcopa_human_clean.jsonl',
})


def sha(data):
    return hashlib.sha256(data).hexdigest()


def bindings(freeze):
    """Yield logical paths and every file binding, including nested night hashes."""
    for config, entry in freeze['formal'].items():
        for section in ('materials', 'fingerprint'):
            for name, digest in entry[section].items():
                if name.endswith(('.py', '.json', '.jsonl', '.md')):
                    yield config, section, 'psych3/' + name, digest
        for name, digest in entry['code']['files'].items():
            yield config, 'code', name.replace('\\', '/'), digest
        yield config, 'manifest_ids', 'psych3/manifest_ids.json', entry['fingerprint']['manifest_ids']
        night = entry['fingerprint'].get('psych3_agy_night', {})
        for key, name in [('python_sha256', 'psych3/agy_night.py'),
                          ('powershell_sha256', 'psych3/agy_night.ps1'),
                          ('recovery_rules_sha256', 'dnli-agy/auto_clear.py')]:
            if key in night:
                yield config, 'psych3_agy_night.' + key, name, night[key]
        baseline = entry['fingerprint'].get('subject_meta', {}).get('baseline', {})
        if 'agent_sha256' in baseline:
            yield config, 'subject_meta.baseline.agent_sha256', 'dnli-agy/agent/dnli-subject.md', baseline['agent_sha256']


def logical(name):
    parts = []
    p = PurePosixPath(name)
    if p.is_absolute() or ':' in name or '\\' in name:
        raise ValueError('unsafe path: ' + name)
    for part in p.parts:
        if part == '..':
            if not parts:
                raise ValueError('path escapes package: ' + name)
            parts.pop()
        else:
            parts.append(part)
    return '/'.join(parts)


def verify(here=None):
    here = Path(here or Path(__file__).resolve().parent)
    root = here.parent.resolve()
    check = json.loads((here / 'release-check.json').read_text(encoding='utf-8'))
    freeze = json.loads((here / 'analysis_freeze_psych3.json').read_text(encoding='utf-8'))
    errors, required, verified = [], {}, []

    def compare(name, expected, label):
        name = logical(name)
        path = root / name
        if path.is_symlink() or root not in path.resolve().parents:
            errors.append(label + ': unsafe path ' + name)
        elif not path.is_file():
            errors.append(label + ': missing ' + name)
        elif sha(path.read_bytes()) != expected:
            errors.append(label + ': SHA-256 mismatch ' + name)
        else:
            verified.append(name)
            return True
        return False

    for item in check['files']:
        compare(item['path'], item['sha256'], 'release manifest')
    for config, section, name, digest in bindings(freeze):
        normalized = logical(name)
        if normalized in {'psych3/' + n for n in THIRD_PARTY}:
            artifact = required.setdefault(normalized, dict(sha256=set(), status='self_acquisition_required'))
            artifact['sha256'].add(digest)
            # Reconstructed copies, when present, must match too.
            path = root / normalized
            if path.exists() or path.is_symlink():
                matched = compare(normalized, digest, config + '/' + section)
                if not matched or artifact['status'] == 'failed':
                    artifact['status'] = 'failed'
                else:
                    artifact['status'] = 'verified'
        else:
            compare(normalized, digest, config + '/' + section)
    for config, entry in freeze['formal'].items():
        digest = sha(json.dumps(entry['fingerprint'], sort_keys=True, ensure_ascii=False).encode('utf-8'))
        if digest != entry['fingerprint_id']:
            errors.append(config + ': fingerprint_id mismatch')
    artifacts = [dict(path=n, sha256=sorted(v['sha256']), status=v['status'])
                 for n, v in sorted(required.items())]
    return dict(ok=not errors, public_files=len(check['files']),
                verified_unique_files=len(set(verified)), errors=errors,
                excluded_artifacts=artifacts,
                self_acquisition_required=[a for a in artifacts if a['status'] == 'self_acquisition_required'],
                limitations=['ok:true means the listed file hashes, available frozen file bindings and six fingerprint IDs passed; missing excluded artifacts are reported separately.',
                             'This verifier does not recompute parse_context, even when raw_manifest.json is present; use the independent calculation in README.md.',
                             'Unlisted files are not checked; ok:true does not establish third-party source authenticity or the historical freeze execution time.',
                             'Model weights, CLI binaries, runtime settings permissions and environment hashes are external attestations.',
                             'release-check.json is an inventory, not a signature; authenticate against the public preregistration commit.'])


if __name__ == '__main__':
    result = verify()
    print(json.dumps(result, ensure_ascii=False, indent=2))
    raise SystemExit(0 if result['ok'] else 1)
