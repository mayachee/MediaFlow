"""Read-only workspace audit. Does not execute project scripts or contact services."""
import argparse
import ast
import importlib.metadata
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.git', '.kilo', '.venv', 'venv', 'node_modules', '__pycache__', 'runs', 'vendor'}
DISTRIBUTIONS = {
    'numpy': 'numpy', 'PIL': 'Pillow', 'yaml': 'PyYAML', 'librosa': 'librosa',
    'soundfile': 'soundfile', 'yt_dlp': 'yt-dlp', 'playwright': 'playwright',
    'googleapiclient': 'google-api-python-client', 'google_auth_oauthlib': 'google-auth-oauthlib',
    'midiutil': 'MIDIUtil', 'scipy': 'scipy', 'reportlab': 'reportlab',
    'music21': 'music21', 'gtts': 'gTTS', 'pydub': 'pydub', 'requests': 'requests',
    'mido': 'mido',
}


def source_files():
    for current, directories, files in os.walk(ROOT):
        directories[:] = sorted(d for d in directories if d not in SKIP)
        for name in sorted(files):
            path = Path(current) / name
            if path.suffix in {'.py', '.ps1'}:
                yield path


def audit():
    syntax = []
    sources = list(source_files())
    for path in sources:
        if path.suffix != '.py':
            continue
        try:
            ast.parse(path.read_text(encoding='utf-8-sig'), filename=str(path))
            syntax.append({'file': path.relative_to(ROOT).as_posix(), 'status': 'pass'})
        except (SyntaxError, UnicodeError) as error:
            syntax.append({'file': path.relative_to(ROOT).as_posix(), 'status': 'fail', 'error': str(error)})
    powershell_syntax = []
    powershell = shutil.which('pwsh') or shutil.which('powershell')
    if powershell:
        parser_script = """
$paths = [Console]::In.ReadToEnd() | ConvertFrom-Json
$checks = foreach ($path in $paths) {
    $tokens = $null
    $issues = $null
    [System.Management.Automation.Language.Parser]::ParseFile([IO.Path]::GetFullPath($path), [ref]$tokens, [ref]$issues) | Out-Null
    @{file=$path; status=$(if ($issues.Count) {'fail'} else {'pass'}); errors=@($issues | ForEach-Object {$_.Message})}
}
ConvertTo-Json -InputObject @($checks) -Depth 5 -Compress
"""
        result = subprocess.run([powershell, '-NoProfile', '-Command', parser_script],
            cwd=ROOT, input=json.dumps([p.relative_to(ROOT).as_posix() for p in sources if p.suffix == '.ps1']),
            capture_output=True, text=True, timeout=30)
        if result.returncode:
            powershell_syntax = [{'status': 'fail', 'error': result.stderr}]
        else:
            powershell_syntax = json.loads(result.stdout)
    packages = {}
    for module, distribution in DISTRIBUTIONS.items():
        try:
            packages[module] = {'available': importlib.util.find_spec(module) is not None,
                                'version': importlib.metadata.version(distribution)}
        except (ImportError, importlib.metadata.PackageNotFoundError):
            packages[module] = {'available': False}
    commands = {}
    for command in ('ffmpeg', 'ffprobe', 'node'):
        executable = shutil.which(command)
        entry = {'path': executable}
        if executable:
            result = subprocess.run([executable, '-version' if command != 'node' else '--version'],
                                    capture_output=True, text=True, timeout=15)
            entry.update(returncode=result.returncode, version=result.stdout.splitlines()[:1])
        commands[command] = entry
    environments = {}
    for folder in ('music_video_generator', 'vocal-remover', 'automatic_upload'):
        executable = ROOT / 'modules' / folder / '.venv' / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if executable.exists():
            # Only import standard-library discovery helpers in child interpreters.
            probe = "import importlib.util,json; print(json.dumps({n:importlib.util.find_spec(n) is not None for n in ['numpy','librosa','torch','demucs','yaml','soundfile']}))"
            try:
                result = subprocess.run([str(executable), '-c', probe], capture_output=True, text=True, timeout=30)
                environments[folder] = {'returncode': result.returncode,
                    'packages': json.loads(result.stdout) if result.returncode == 0 else {},
                    'interpreter_usable': result.returncode == 0}
                if folder == 'vocal-remover' and result.returncode == 0:
                    runtime = subprocess.run([str(executable), '-m', 'demucs', '--help'],
                                             capture_output=True, text=True, timeout=45)
                    environments[folder]['demucs_runtime'] = {
                        'status': 'pass' if runtime.returncode == 0 else 'fail',
                        'returncode': runtime.returncode,
                        'error': next((line for line in reversed(runtime.stderr.splitlines())
                                       if 'Error' in line), '')}
            except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
                environments[folder] = {'usable': False, 'error': type(error).__name__}
        else:
            environments[folder] = {'usable': False, 'reason': 'no local environment'}
    folder_sources = {}
    for path in sources:
        relative = path.relative_to(ROOT)
        folder = relative.parts[0] if len(relative.parts) > 1 else '(root)'
        folder_sources[folder] = folder_sources.get(folder, 0) + 1
    dependency_check = subprocess.run([sys.executable, '-m', 'pip', 'check'],
                                      capture_output=True, text=True, timeout=30)
    return {'checked_at_utc': datetime.now(timezone.utc).isoformat(), 'python': sys.executable,
            'scope': 'syntax, package presence, executable versions, local environment launch; no services or project execution',
            'syntax': syntax, 'powershell_syntax': powershell_syntax, 'packages': packages, 'commands': commands,
            'dependency_check': {'returncode': dependency_check.returncode,
                                 'details': dependency_check.stdout.splitlines()},
            'environments': environments, 'source_counts': folder_sources,
            'assets': {name: (ROOT / name).exists() for name in (
                'assets/soundfonts/SoundFont.sf2',
                'vendor/fluidsynth-bin/fluidsynth-v2.6.1-win10-x64-cpp11/bin/fluidsynth.exe')}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, help='Optionally save JSON report')
    args = parser.parse_args()
    report = audit()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2), encoding='utf-8')
    failures = [entry for entry in report['syntax'] if entry['status'] == 'fail']
    print(f"Python syntax: {len(report['syntax']) - len(failures)}/{len(report['syntax'])} passed")
    for entry in failures:
        print(entry['file'], entry['error'])
    ps_failures = [entry for entry in report['powershell_syntax'] if entry['status'] == 'fail']
    print(f"PowerShell syntax: {len(report['powershell_syntax']) - len(ps_failures)}/{len(report['powershell_syntax'])} passed")
    print('Packages:', ', '.join(name for name, info in report['packages'].items() if info['available']))
    print('Missing packages:', ', '.join(name for name, info in report['packages'].items() if not info['available']) or 'none')
    print('Tools:', ', '.join(f"{name}={'found' if info['path'] else 'missing'}" for name, info in report['commands'].items()))
    print('Local environments:', json.dumps(report['environments']))
    runtime_failed = report['environments'].get('vocal-remover', {}).get('demucs_runtime', {}).get('status') == 'fail'
    print('Dependency consistency:', 'pass' if report['dependency_check']['returncode'] == 0 else 'conflicts found; see report')
    return bool(failures or ps_failures or runtime_failed or report['dependency_check']['returncode'])


if __name__ == '__main__':
    sys.exit(main())
