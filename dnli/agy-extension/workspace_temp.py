"""Fresh disposable directory with inherited Windows workspace permissions.
Python 3.12 mkdtemp(mode=0o700) can deny sandbox-token access on Windows.
"""
from contextlib import contextmanager
from pathlib import Path
import shutil
import uuid
import time

def cleanup_directory(path, parent, prefix='dnli-agy-', attempts=10):
    """Return an OS cleanup error; unsafe paths still raise immediately."""
    parent = Path(parent).resolve()
    for attempt in range(attempts):
        resolved = Path(path).resolve()
        if resolved.parent != parent or not resolved.name.startswith(prefix):
            raise RuntimeError('temporary cleanup path outside expected parent')
        try:
            shutil.rmtree(resolved)
            return None
        except FileNotFoundError:
            return None
        except OSError as exc:
            error = f'{resolved}: {type(exc).__name__}: {exc}'
            if attempt + 1 < attempts:
                time.sleep(0.5 * (attempt + 1))
    return error


def cleanup_old_directories(parent, prefix='dnli-agy-', limit=20):
    """Sweep owned leftovers once each only when the backlog exceeds limit."""
    parent = Path(parent).resolve()
    try:
        paths = [p for p in parent.iterdir() if p.name.startswith(prefix) and p.is_dir()]
    except OSError as exc:
        return [f'{parent}: {type(exc).__name__}: {exc}']
    errors = []
    if len(paths) > limit:
        for path in paths:
            error = cleanup_directory(path, parent, prefix, attempts=1)
            if error:
                errors.append(error)
    return errors


@contextmanager
def temporary_directory(dir=None, prefix='dnli-agy-', cleanup_result=None):
    """Yield the existing string API; optionally publish cleanup status in a dict."""
    parent = Path(dir or Path.cwd()).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    path = parent / (prefix + uuid.uuid4().hex)
    path.mkdir(mode=0o777)
    if cleanup_result is not None:
        cleanup_result.update(path=str(path), cleanup_error=None)
    try:
        yield str(path)
    finally:
        error = cleanup_directory(path, parent, prefix)
        if cleanup_result is not None:
            cleanup_result['cleanup_error'] = error
