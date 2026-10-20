"""Offline PowerShell 5.1 launcher checks; never run the real queue or agy."""
import datetime as dt
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest

from workspace_temp import temporary_directory

HERE = Path(__file__).resolve().parent


@unittest.skipUnless(os.name == 'nt' and shutil.which('powershell.exe'), 'Windows PowerShell required')
class LauncherTests(unittest.TestCase):
    def test_append_utf8_both_streams_and_preserve_exit_code(self):
        with temporary_directory(dir=HERE) as tmp:
            # Spaces exercise the cmd quoting used by the actual launcher.
            root = Path(tmp) / 'launcher with spaces'
            root.mkdir()
            (root / 'night_queue.ps1').write_bytes((HERE / 'night_queue.ps1').read_bytes())
            (root / 'auto_clear.py').write_text('raise SystemExit(0)\n', encoding='utf-8')
            wrapper = root / 'stub agy.cmd'
            wrapper.write_text(f'@"{sys.executable}" -X utf8 -B "{HERE / "stub_agy.py"}" %*\n',
                               encoding='utf-8')
            (root / 'night_queue.py').write_text('''import argparse
import subprocess
import sys
ap = argparse.ArgumentParser()
ap.add_argument('--agy', required=True)
ap.add_argument('--deadline', required=True)
ap.add_argument('--quota-skip-hours', type=float, required=True)
a = ap.parse_args()
assert a.quota_skip_hours == 0.25
r = subprocess.run([a.agy, '--version'], capture_output=True, check=True)
assert r.stdout.strip() == b'stub-agy 1.3.3'
print('stdout 中文 ' + a.deadline)
print('stderr 中文 ' + a.deadline, file=sys.stderr)
sys.exit(7 if a.deadline == '08:00' else 0)
''', encoding='utf-8')
            logs = []
            for deadline, code in (('08:00', 7), ('09:00', 0)):
                day = dt.datetime.now().strftime('%Y-%m-%d')
                result = subprocess.run([
                    'powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                    '-File', str(root / 'night_queue.ps1'), '-Deadline', deadline,
                    '-QuotaSkipHours', '0.25', '-Agy', str(wrapper)],
                    capture_output=True, timeout=30)
                self.assertEqual(result.returncode, code, result.stderr.decode('utf-8', errors='replace'))
                log = root / 'raw' / f'night_queue_{day}.log'
                text = log.read_text(encoding='utf-8')
                self.assertIn('stdout 中文 ' + deadline, text)
                self.assertIn('stderr 中文 ' + deadline, text)
                self.assertRegex(text, rf'\d{{4}}-\d{{2}}-\d{{2}}T[^\r\n]+ END exit_code={code}')
                logs.append((log, text))
            if logs[0][0] == logs[1][0]:
                self.assertTrue(logs[1][1].startswith(logs[0][1]))
                self.assertEqual(logs[1][1].count(' START exit_code=pending'), 2)
                self.assertEqual(logs[1][1].count(' END exit_code='), 2)

    def test_disables_agy_auto_update(self):
        text = (Path(__file__).resolve().parent / 'night_queue.ps1').read_text(encoding='utf-8')
        self.assertIn("$env:AGY_CLI_DISABLE_AUTO_UPDATE = 'true'", text)

    def test_round_limits_deadline_and_clear_results(self):
        for mode in ('none', 'max', 'deadline', 'wait_deadline', 'backoff_deadline', 'error'):
            with self.subTest(mode=mode), temporary_directory(dir=HERE) as tmp:
                root = Path(tmp) / 'round tests'
                root.mkdir()
                (root / 'night_queue.ps1').write_bytes((HERE / 'night_queue.ps1').read_bytes())
                (root / 'night_queue.py').write_text("print('STUB_QUEUE')\n", encoding='utf-8')
                clear_code = {'none': 0, 'error': 9}.get(mode, 10)
                (root / 'auto_clear.py').write_text(
                    "print('STUB_CLEAR')\nraise SystemExit(%d)\n" % clear_code, encoding='utf-8')
                if mode == 'backoff_deadline':
                    # v3 acceptance 2/4: persisted backoff wins over minimum 0.
                    (root / 'auto_clear.py').write_text('''import datetime as dt
import json
from pathlib import Path
until = (dt.datetime.now().astimezone() + dt.timedelta(minutes=120)).isoformat()
(Path(__file__).resolve().parent / 'raw/queue_state.json').write_text(json.dumps({'models': {'stub': {
    'stage': 'dev', 'needs_review': None, 'skipped_until': until}}}), encoding='utf-8')
print('STUB_CLEAR')
raise SystemExit(10)
''', encoding='utf-8')
                # Inject a deadline into the copied launcher to avoid wall-clock dependence.
                script = (root / 'night_queue.ps1').read_text(encoding='utf-8')
                if mode in ('deadline', 'wait_deadline', 'backoff_deadline'):
                    offset = -1 if mode == 'deadline' else 2
                    script = script.replace(
                        '$deadlineAt = $started.Date.Add([TimeSpan]::Parse($Deadline))',
                        '$deadlineAt = $started.AddSeconds(%s)' % offset)
                    (root / 'night_queue.ps1').write_text(script, encoding='utf-8')
                result = subprocess.run([
                    'powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                    '-File', str(root / 'night_queue.ps1'), '-Deadline', '23:59:59.9999999',
                    '-RetryWaitMinutes', '0.05' if mode == 'wait_deadline' else '0',
                    '-MaxRounds', '3'], capture_output=True, timeout=30)
                self.assertEqual(result.returncode, 9 if mode == 'error' else 0,
                                 result.stderr.decode('utf-8', errors='replace'))
                text = next((root / 'raw').glob('night_queue_*.log')).read_text(encoding='utf-8')
                rounds = 3 if mode == 'max' else 1
                self.assertEqual(text.count('STUB_QUEUE'), rounds)
                self.assertEqual(text.count(' ROUND '), rounds)
                clears = 2 if mode == 'max' else (0 if mode == 'deadline' else 1)
                self.assertEqual(text.count('STUB_CLEAR'), clears)

    def test_wait_uses_earliest_retryable_model(self):
        with temporary_directory(dir=HERE) as tmp:
            root = Path(tmp)
            (root / 'night_queue.py').write_text("print('STUB_QUEUE')\n", encoding='utf-8')
            (root / 'auto_clear.py').write_text('''import datetime as dt
import json
from pathlib import Path
now = dt.datetime.now().astimezone()
def row(minutes, stage='dev', review=None):
    return {'stage': stage, 'needs_review': review,
            'skipped_until': (now + dt.timedelta(minutes=minutes)).isoformat()}
(Path(__file__).resolve().parent / 'raw/queue_state.json').write_text(json.dumps({'models': {
    'later': row(120), 'earliest': row(60), 'done': row(1, 'done'),
    'review': row(2, review={'reason': 'manual'})}}), encoding='utf-8')
raise SystemExit(10)
''', encoding='utf-8')
            script = (HERE / 'night_queue.ps1').read_text(encoding='utf-8')
            # Observe the real wait selection, then end at the deadline without sleeping.
            script = script.replace(
                '    while ((Get-Date) -lt $wakeAt',
                "    Write-Output ('SELECTED_WAIT=' + ($wakeAt - (Get-Date)).TotalMinutes)\n"
                '    $deadlineAt = Get-Date\n'
                '    while ((Get-Date) -lt $wakeAt')
            (root / 'night_queue.ps1').write_text(script, encoding='utf-8')
            result = subprocess.run([
                'powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                '-File', str(root / 'night_queue.ps1'), '-Deadline', '23:59:59.9999999',
                '-RetryWaitMinutes', '0'], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
            selected = next(line.split('=', 1)[1] for line in result.stdout.decode('utf-8').splitlines()
                            if line.startswith('SELECTED_WAIT='))
            self.assertAlmostEqual(float(selected), 60, delta=0.1)

    def test_cross_round_backoff_without_new_clear(self):
        # v4 acceptance 2: A wakes at 30m; B still gets its turn at 60m.
        with temporary_directory(dir=HERE) as tmp:
            root = Path(tmp)
            script = (HERE / 'night_queue.ps1').read_text(encoding='utf-8')
            self.assertIn('$MaxRounds = 12', script)
            # Virtual clock runs the real outer loop and state selection without sleeping.
            script = script.replace("$started = Get-Date", """$script:clock = [datetime]'2026-10-17T01:00:00'
function Get-Date { return $script:clock }
function Start-Sleep([int]$Milliseconds) {
    $script:clock = $script:clock.AddMilliseconds($Milliseconds)
}
$started = Get-Date""")
            start = script.index('    $commandLine = ', script.index('function Invoke-LoggedPython'))
            end = script.index('\n$exitCode = 0', start)
            script = script[:start] + """    $statePath = Join-Path $logDir 'queue_state.json'
    if ($Arguments.Contains('night_queue.py')) {
        if (-not (Test-Path -LiteralPath $statePath)) {
            $models = [ordered]@{
                A = @{ stage='dev'; needs_review=@{reason='failure'}; skipped_until=$null }
                B = @{ stage='dev'; needs_review=@{reason='failure'}; skipped_until=$null }
                done = @{ stage='done'; needs_review=$null; skipped_until=$started.AddMinutes(1).ToString('o') }
                review = @{ stage='dev'; needs_review=@{reason='manual'}; skipped_until=$started.AddMinutes(2).ToString('o') }
                late = @{ stage='dev'; needs_review=$null; skipped_until=$deadlineAt.ToString('o') }
            }
            @{models=$models} | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $statePath -Encoding UTF8
        } else {
            $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
            foreach ($name in @('A', 'B')) {
                $row = $state.models.$name
                if ($row.stage -ne 'done' -and [datetime]::Parse($row.skipped_until) -le (Get-Date)) {
                    $row.stage = 'done'
                    [Console]::WriteLine('RESUMED=' + $name + ':' + ((Get-Date) - $started).TotalMinutes)
                }
            }
            $state | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $statePath -Encoding UTF8
        }
        [Console]::WriteLine('QUEUE_AT=' + ((Get-Date) - $started).TotalMinutes)
        return 0
    }
    $state = Get-Content -LiteralPath $statePath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($state.models.A.needs_review) {
        $state.models.A.needs_review = $null
        $state.models.B.needs_review = $null
        $state.models.A.skipped_until = $started.AddMinutes(30).ToString('o')
        $state.models.B.skipped_until = $started.AddMinutes(60).ToString('o')
        $state | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath $statePath -Encoding UTF8
        return 10
    }
    return 0
}
""" + script[end:]
            (root / 'night_queue.ps1').write_text(script, encoding='utf-8')
            result = subprocess.run([
                'powershell.exe', '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                '-File', str(root / 'night_queue.ps1'), '-Deadline', '03:00',
                '-RetryWaitMinutes', '5'], capture_output=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr.decode('utf-8', errors='replace'))
            lines = result.stdout.decode('utf-8').splitlines()
            self.assertEqual([s for s in lines if s.startswith('QUEUE_AT=')],
                             ['QUEUE_AT=0', 'QUEUE_AT=30', 'QUEUE_AT=60'])
            self.assertIn('RESUMED=A:30', lines)
            self.assertIn('RESUMED=B:60', lines)


if __name__ == '__main__':
    unittest.main()
