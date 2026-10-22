"""Restore the authorized night baseline, retaining daytime bytes for review.

Windows ReplaceFileW retains the actual displaced version, including writes
after the last recheck. The non-Windows os.replace fallback is only for portable
tests and does not provide that retention guarantee.
"""
import ctypes
from ctypes import wintypes
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time
import uuid


_WINDOWS = os.name == 'nt'


def _replace_file_w(settings, temporary, displaced):
    kernel32 = ctypes.WinDLL('kernel32', use_last_error=True)
    replace = kernel32.ReplaceFileW
    replace.argtypes = (wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                        wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID)
    replace.restype = wintypes.BOOL
    if not replace(str(settings), str(temporary), str(displaced), 0, None, None):
        error = ctypes.get_last_error()
        raise ctypes.WinError(error)


def _replace_settings(temporary, settings, displaced):
    if _WINDOWS:
        try:
            _replace_file_w(settings, temporary, displaced)
            return 'saved'
        except OSError as exc:
            # ReplaceFileW requires an existing target. Do not fall back for
            # sharing violations or any other replacement error.
            if getattr(exc, 'winerror', None) != 2:
                raise
        # Windows rename atomically fails if another writer created the target.
        os.rename(temporary, settings)
        return 'missing'
    # Portability for tests only; cannot capture concurrent displaced bytes.
    if not settings.exists():
        os.link(temporary, settings)  # Atomic no-clobber creation on POSIX too.
        temporary.unlink()
        return 'missing'
    os.replace(temporary, settings)
    return 'unsupported'


def sha(data):
    return hashlib.sha256(data).hexdigest()


def permissions_sha(data):
    try:
        permissions = json.loads(data)['permissions']
        return sha(json.dumps(permissions, sort_keys=True, ensure_ascii=False,
                              separators=(',', ':'), allow_nan=False).encode('utf-8'))
    except (ValueError, KeyError, TypeError, UnicodeError, RecursionError):
        return None


class _RestoreBlocked(ValueError):
    pass


def _archive_displaced(displaced, raw):
    data = displaced.read_bytes()
    archive = raw / 'settings_daytime' / (displaced.stem + '.json')
    archive.parent.mkdir(parents=True, exist_ok=True)
    try:
        stream = archive.open('xb')
    except FileExistsError:
        with archive.open('r+b') as stream:
            if stream.read() != data:
                raise ValueError('displaced archive differs: ' + str(archive))
            os.fsync(stream.fileno())
    else:
        with stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    return archive, data


def restore_settings(settings, baseline, raw, now, may_write=lambda: True):
    """Return status, audit on restore/recovery, and reason on failure.

    baseline is a descriptor whose path is relative to its own directory.
    All paths are supplied by the caller; now is a datetime, not a clock.
    may_write is checked before the daytime backup and before every replace.
    """
    settings, baseline, raw = Path(settings), Path(baseline), Path(raw)
    temporary = None
    result = None
    phase = 'baseline'
    audit = dict(datetime=now.isoformat(), displaced_sha256=None)
    try:
        descriptor = json.loads(baseline.read_bytes())
        source = baseline.parent / descriptor['path']
        data = source.read_bytes()
        digest = sha(data)
        if digest != descriptor['sha256']:
            raise ValueError('baseline SHA-256 mismatch')
        phase = 'recover displaced settings'
        # scandir propagates directory I/O failures instead of hiding them.
        with os.scandir(settings.parent) as entries:
            pending = sorted(Path(entry.path) for entry in entries
                             if entry.name.startswith(settings.name + '.psych3-displaced-')
                             and entry.name.endswith('.bak'))
        for displaced in pending:
            phase = 'recover displaced settings ' + str(displaced)
            audit['displaced_backup_path'] = str(displaced)
            if not may_write():
                raise _RestoreBlocked('admission closed')
            archive, recovered = _archive_displaced(displaced, raw)
            displaced.unlink()
            audit.setdefault('recovered_displaced', []).append(dict(
                path=str(archive), displaced_backup_path=str(displaced),
                sha256=sha(recovered), permissions_sha256=permissions_sha(recovered)))
            del audit['displaced_backup_path']
        phase = 'read settings'
        try:
            current = settings.read_bytes()
        except FileNotFoundError:
            current = None
        if current == data:
            return (dict(status='no-op', audit=audit) if audit.get('recovered_displaced')
                    else dict(status='no-op'))
        audit.update(daytime_status='missing' if current is None else 'saved',
                     daytime_path=None, daytime_sha256=None,
                     daytime_permissions_sha256=None)
        if current is not None:
            phase = 'daytime backup'
            if not may_write():
                raise _RestoreBlocked('admission closed')
            backup = raw / 'settings_daytime' / (
                'psych3_settings_daytime_' + now.strftime('%Y%m%d-%H%M%S') + '.json')
            backup.parent.mkdir(parents=True, exist_ok=True)
            with backup.open('xb') as stream:
                stream.write(current)
                stream.flush()
                os.fsync(stream.fileno())
            audit.update(daytime_path=str(backup), daytime_sha256=sha(current),
                         daytime_permissions_sha256=permissions_sha(current))
        phase = 'replace settings'
        with tempfile.NamedTemporaryFile(mode='wb', dir=settings.parent,
                                         prefix=settings.name + '.', suffix='.tmp',
                                         delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        for attempt in range(5):
            try:
                latest = settings.read_bytes()
            except FileNotFoundError:
                latest = None
            if latest != current:
                raise _RestoreBlocked('settings changed during restore')
            if not may_write():
                raise _RestoreBlocked('admission closed')
            try:
                displaced = settings.with_name(
                    settings.name + '.psych3-displaced-' +
                    now.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex + '.bak')
                audit['displaced_status'] = _replace_settings(temporary, settings, displaced)
                temporary = None
                break
            except FileExistsError as exc:
                raise _RestoreBlocked('settings created during restore') from exc
            except OSError as exc:
                if getattr(exc, 'winerror', None) == 1177:
                    audit['displaced_backup_path'] = str(displaced)
                    raise _RestoreBlocked(
                        'ReplaceFileW error 1177: ' + str(exc) +
                        '; displaced backup: ' + str(displaced)) from exc
                if attempt == 4:
                    raise
                time.sleep(0.5 * 2 ** attempt)
        if audit['displaced_status'] == 'saved':
            phase = 'archive displaced settings'
            # Keep the same-directory backup on any read/archive failure.
            audit['displaced_path'] = str(displaced)
            audit['displaced_backup_path'] = str(displaced)
            displaced_data = displaced.read_bytes()
            audit.update(displaced_sha256=sha(displaced_data),
                         displaced_permissions_sha256=permissions_sha(displaced_data),
                         displaced_differs=displaced_data != current)
            archive, _ = _archive_displaced(displaced, raw)
            audit['displaced_path'] = str(archive)
            if displaced_data == current:
                archive.unlink()
                audit['displaced_path'] = audit['daytime_path']
            phase = 'displaced backup cleanup'
            try:
                displaced.unlink()
                del audit['displaced_backup_path']
            except OSError as exc:
                # Fail closed: settings is already the baseline and the bytes are
                # archived; the next call's leftover sweep removes the .bak.
                audit['displaced_cleanup_reason'] = str(exc)
                audit['displaced_backup_path'] = str(displaced)
                raise
        phase = 'verify settings'
        audit['restored_sha256'] = sha(settings.read_bytes())
        if audit['restored_sha256'] != digest:
            raise ValueError('restored settings SHA-256 mismatch')
        return dict(status='restored', audit=audit)
    except (OSError, ValueError, KeyError, TypeError, RecursionError) as exc:
        reason = str(exc) if isinstance(exc, _RestoreBlocked) else phase + ': ' + str(exc)
        result = dict(status='failed', reason=reason, audit=audit)
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError as exc:
                if result is not None:
                    result['reason'] += '; temporary cleanup: ' + str(exc)
    return result
