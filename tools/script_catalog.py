"""First-party tool catalog and subprocess jobs; never imports discovered scripts."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import uuid
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
SKIP = {'.git', '.codex', '.agents', '.aws', '.kilo', '.venv', 'venv', '__pycache__',
        'vendor', 'runs', 'node_modules', 'output', 'library', 'downloads', 'stems', 'work', 'assets'}


def field(key, label, kind='text', flag=None, default='', required=False, choices=None):
    return dict(key=key, label=label, kind=kind, flag=flag, default=default,
                required=required, choices=choices)


def curated_tools():
    def tool(key, title, category, script, description, fields=(), args=(), cwd='.'):
        return dict(id=key, title=title, category=category, script=script,
                    description=description, fields=list(fields), args=list(args), cwd=cwd,
                    runnable=True, guided=True)
    audio = lambda: field('audio', 'Audio file', 'file', '--audio', required=True)
    timeline = lambda: field('timeline', 'Reviewed timeline (optional)', 'file', '--timeline')
    report = lambda: field('report', 'Reviewed candidates.json', 'file', '--report', required=True)
    tools = [
        tool('cleaner-preview', 'Preview workspace cleanup', 'Setup & maintenance', 'tools/workspace_cleaner.py',
             'List old Python caches and completed Studio logs without changing files. Use the Cleaner toolbar button to review selections, restore Trash, or free space.', [
                 field('days', 'Older than (days)', 'integer', '--days', '7')]),
        tool('autocrop', 'AutoCrop Vertical: reframe video', 'Video & audio', 'modules/autocrop_vertical/manage.py',
             'Reframe a video for YouTube (16:9), Shorts/Reels (9:16), or square/social formats. Detects people per scene. 16:9 + 1080p exports 1920x1080. Run setup once first.', [
                 field('input', 'Source video', 'file', '--input', required=True),
                 field('output_root', 'Output folder', 'newdirectory', '--output-root', 'runs/autocrop-vertical'),
                 field('ratio', 'Format (16:9 = YouTube)', 'choice', '--ratio', '16:9', choices=['16:9', '9:16', '4:5', '1:1']),
                 field('resolution', 'Resolution', 'choice', '--resolution', '1080p', choices=['1080p', '720p', 'native']),
                 field('quality', 'Quality', 'choice', '--quality', 'balanced', choices=['fast', 'balanced', 'high']),
                 field('frame_skip', 'Scene frame skip (0 = all frames)', 'integer', '--frame-skip', '0'),
                 field('plan_only', 'Analyze only; do not encode a video', 'bool', '--plan-only')], ['convert']),
        tool('autocrop-setup', 'Setup AutoCrop Vertical', 'Setup & maintenance', 'modules/autocrop_vertical/manage.py',
             'Install AutoCrop in its own environment and download its person-detection model. First setup needs internet and downloads CPU PyTorch and other dependencies.', args=['setup']),
        tool('autocrop-status', 'Check AutoCrop installation', 'Setup & maintenance', 'modules/autocrop_vertical/manage.py',
             'Check the pinned source, separate environment, model, FFmpeg, and ffprobe.', args=['status']),
        tool('video', 'Create music video / audio master', 'Video & audio', 'workflow.py',
             'Create an isolated video job, preview, or WAV master. Choose your own photos/clips or an exported highlight timeline. Normalization is optional.', [
                 audio(), field('images', 'Photos / clips folder', 'directory', '--images',
                                'modules/music_video_generator/input/images'), timeline(),
                 field('preset', 'Export', 'choice', '--preset', 'preview', choices=['preview', 'video', 'master']),
                 field('preview_start', 'Preview start (seconds)', 'number', '--preview-start'),
                 field('preview_seconds', 'Preview length (seconds)', 'number', '--preview-seconds'),
                 field('reference', 'Reference audio (optional)', 'file', '--reference'),
                 field('normalize', 'Normalization', 'choice', '--normalize', 'off', choices=['off', 'peak', 'loudness']),
                 field('instrumental', 'Remove vocals first (requires Demucs)', 'bool', '--instrumental')]),
        tool('video-window', 'Open simple video creator', 'Video & audio', 'create_video.py',
             'Open the dedicated audio-to-video window.'),
        tool('clips-auto', 'Find & download clips', 'Clip library', 'modules/clip_finder/find_matching_clips.py',
             'Enter any video idea, title, or keywords: nature, cars, sports, gaming, space, or your own topic. Studio searches online and automatically downloads matching clips. Audio is optional.', [
                 dict(field('title', 'Video idea, title, or keywords', flag='--title', required=True), wide=True,
                      placeholder='Example: cinematic forest, mountains and sunrise'),
                 field('download_top', 'Number of clips to download', 'integer', '--download-top', '3', True),
                 field('count', 'Candidates to consider', 'integer', '--count', '12'),
                 field('mood', 'Visual mood', flag='--mood', default='cinematic'),
                 field('keywords', 'Extra keywords (optional)', flag='--keywords'),
                 field('audio', 'Audio file (optional)', 'file', '--audio')], ['--download-mode', 'best-available']),
        tool('clips-search', 'Search online clips (shortlist only)', 'Clip library', 'modules/clip_finder/find_matching_clips.py',
             'Search YouTube using visual story keywords; writes a ranked shortlist. Review the results before downloading.', [
                 field('audio', 'Audio file (optional)', 'file', '--audio'), field('keywords', 'Visual story keywords', flag='--keywords', required=True),
                 field('mood', 'Mood', flag='--mood', default='cinematic'),
                 field('count', 'Results', 'integer', '--count', '10')]),
        tool('clips-download', 'Download reviewed clips', 'Clip library', 'modules/clip_finder/clip_library.py',
             'Download selected ranks from an existing candidates.json into the reusable clip library.', [
                 report(), field('ranks', 'Ranks, separated by spaces', 'integers', '--rank', '1', True)], ['download']),
        tool('clips-list', 'List library assets', 'Clip library', 'modules/clip_finder/clip_library.py',
             'Print saved asset IDs, source details, and verified original paths.', args=['list']),
        tool('clips-import', 'Import local footage', 'Clip library', 'modules/clip_finder/clip_library.py',
             'Copy local footage into the content-addressed library and validate it.', [
                 field('file', 'Video file', 'file', '--file', required=True),
                 field('title', 'Title', flag='--title'), field('source_url', 'Source URL', flag='--source-url'),
                 field('license', 'License / permission notes', flag='--license')], ['import']),
        tool('clips-highlight', 'Select a highlight', 'Clip library', 'modules/clip_finder/clip_library.py',
             'Save an explicitly reviewed range. Copy the asset ID from the library list, then use the returned reference when exporting.', [
                 field('asset', 'Asset ID', flag='--asset', required=True),
                 field('start', 'Start (seconds)', 'number', '--start', '0', True),
                 field('end', 'End (seconds)', 'number', '--end', '5', True),
                 field('note', 'Notes', flag='--note')], ['highlight']),
        tool('clips-export', 'Export highlight timeline', 'Clip library', 'modules/clip_finder/clip_library.py',
             'Combine highlight references in the supplied order. Output must be a new filename; reviewed footage must cover the requested duration.', [
                 field('highlights', 'Highlight references (space separated)', 'tokens', '--highlight', required=True),
                 field('output', 'New timeline JSON', 'savefile', '--output', required=True),
                 field('seconds', 'Required length (seconds, optional)', 'number', '--seconds')], ['export']),
        tool('clip-demo', 'Clip library demo', 'Diagnostics', 'modules/clip_finder/demo_library.py',
             'Generate synthetic footage, choose ranges, export a timeline, and render a tiny local video.'),
        tool('audio-quality', 'Measure audio quality', 'Video & audio', 'tools/audio_quality.py',
             'Measure a local audio file and save its quality report.', [
                 field('file', 'Audio file', 'file', required=True),
                 field('output', 'Report JSON', 'savefile', '--output', required=True)]),
        tool('compare', 'Compare reference track', 'Video & audio', 'tools/compare_audio.py',
             'Compare your mix with a reference track and export matched listening clips.', [
                 field('mix', 'Your mix', 'file', '--mix', required=True),
                 field('reference', 'Reference track', 'file', '--reference', required=True),
                 field('output', 'New comparison folder', 'newdirectory', '--output', required=True)]),
        tool('download-audio', 'Download audio', 'Search & publishing', 'modules/automatic_upload/download_mp3.py',
             'Download audio from one URL into a chosen folder.', [
                 field('url', 'Video URL', flag='--url', required=True),
                 field('output', 'Downloads folder', 'newdirectory', '--output-dir',
                       'modules/automatic_upload/downloads'),
                 field('trim', 'Trim leading / trailing silence', 'bool', '--trim')]),
        tool('youtube', 'Upload video to YouTube', 'Search & publishing',
             'modules/automatic_YouTube_upload/youtube_uploader.py',
             'Upload the selected video using your configured YouTube account. Running this tool performs an upload; private is selected initially.', [
                 field('video', 'Video file', 'file', '--video', required=True),
                 field('title', 'Title', flag='--title'), field('metadata', 'Metadata JSON (optional)', 'file', '--metadata'),
                 field('privacy', 'Privacy', 'choice', '--privacy', 'private', choices=['private', 'unlisted', 'public'])]),
        tool('vocals', 'Separate vocals / instrumental', 'Video & audio', 'modules/vocal-remover/run.ps1',
             'Separate a local audio file using the installed Demucs environment. See the vocal-remover README for setup and known runtime limitations.', [
                 field('file', 'Audio file', 'file', required=True),
                 field('model', 'Model', flag='-Model', default='htdemucs')], ['local']),
        tool('doctor', 'Workspace health check', 'Diagnostics', 'tools/doctor.py',
             'Check tools, syntax, dependencies, and the separation runtime. Writes a health report.', [
                 field('output', 'Report JSON', 'savefile', '--output', 'docs/health-check.json')]),
        tool('tests', 'Run offline workflow tests', 'Diagnostics', None,
             'Run the workspace regression tests without uploading or downloading media.',
             args=['-m', 'unittest', 'discover', '-s', 'tests', '-v']),
        tool('clips-tests', 'Run offline clip tests', 'Diagnostics', None,
             'Test clip ranking, imports, integrity, range selection, and timeline exports.',
             args=['-m', 'unittest', 'discover', '-s', 'modules/clip_finder/tests', '-v']),
    ]
    for name, title in [('soudeni_piano_cover', 'Create cover MIDI'), ('generate_audio', 'Render piano audio'),
                        ('create_full_production', 'Create full orchestration'), ('generate_vocals', 'Generate experimental vocals'),
                        ('generate_pdf', 'Generate score PDF'), ('generate_sheet_music', 'Generate sheet music')]:
        tools.append(tool('soudeni-' + name, title, 'Soudeni project', f'projects/soudeni/{name}.py',
                          'Run this song-specific production step. Outputs are saved alongside the project; read the project README for the required order.',
                          cwd='projects/soudeni'))
    return tools


def discover_scripts(root=ROOT):
    root = Path(root).resolve()
    found = []
    for folder, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(d for d in directories if d not in SKIP and not d.startswith('.')
                                and not (Path(folder) / d).is_symlink())
        for name in sorted(files):
            path = Path(folder) / name
            if path.suffix.lower() not in {'.py', '.ps1', '.cmd', '.bat'} or path.is_symlink():
                continue
            relative = path.relative_to(root)
            parts = relative.parts
            helpers = ('src' in parts or 'tests' in parts or name == '__init__.py' or
                       relative.as_posix() in {'script_manager.py', 'tools/script_catalog.py',
                                               'tools/cleaner_ui.py', 'studio_server.py', 'tools/studio_picker.py',
                                               'pipelines/audio_production.py', 'pipelines/media_quality.py'})
            category = ('Soudeni project' if parts[0] == 'projects' else
                        'Diagnostics' if parts[0] in {'tools', 'tests'} else
                        'Other scripts')
            found.append(dict(id='script:' + relative.as_posix(), title=relative.as_posix(), category=category,
                              script=relative.as_posix(), cwd=str(relative.parent), fields=[], args=[],
                              runnable=not helpers and path.suffix.lower() in {'.py', '.ps1'}, guided=False,
                              description=('Shared code / launcher: view its source or use a guided tool.' if helpers or path.suffix.lower() in {'.cmd', '.bat'}
                                           else 'Standalone script. Read its source or README before running. Supply arguments below, one per line. Interactive scripts open in a separate console.')))
    return found


def build_command(tool, values, extra=(), python=sys.executable, root=ROOT):
    import math
    root = Path(root).resolve()
    if not tool.get('runnable'):
        raise ValueError('This file is shared code. Choose a standalone script or guided tool.')
    cwd = (root / tool['cwd']).resolve()
    cwd.relative_to(root)
    if not cwd.is_dir():
        raise ValueError('Working folder does not exist.')
    script = (root / tool['script']).resolve() if tool['script'] else None
    if script:
        script.relative_to(root)
        if not script.is_file():
            raise ValueError('Script is missing.')
    if script and script.suffix.lower() == '.ps1':
        command = ['powershell.exe', '-NoProfile', '-File', str(script)]
    else:
        command = [str(python), '-u'] + ([str(script)] if script else [])
    command += tool['args']
    if tool['id'] == 'video' and values.get('preset', 'preview') != 'preview':
        if str(values.get('preview_start', '')).strip() or str(values.get('preview_seconds', '')).strip():
            raise ValueError('Clear preview start and length when exporting a full video or WAV master.')
    for item in tool['fields']:
        if tool['id'] == 'video' and item['key'] == 'images' and (values.get('timeline') or values.get('preset') == 'master'):
            continue
        value = values.get(item['key'], item['default'])
        if item['kind'] == 'bool':
            if value:
                command.append(item['flag'])
            continue
        value = str(value).strip()
        if not value:
            if item['required']:
                raise ValueError(f"Choose {item['label']}.")
            continue
        kind = item['kind']
        if kind in {'file', 'directory', 'savefile', 'newdirectory'}:
            path = Path(value).expanduser()
            path = (root / path).resolve() if not path.is_absolute() else path.resolve()
            if kind == 'file' and not path.is_file():
                raise ValueError(f"File not found: {item['label']}")
            if kind == 'directory' and not path.is_dir():
                raise ValueError(f"Folder not found: {item['label']}")
            value = str(path)
        elif kind in {'number', 'integer'}:
            number = float(value) if kind == 'number' else int(value)
            if not math.isfinite(number):
                raise ValueError(f"Enter a finite number for {item['label']}.")
        elif kind == 'choice' and value not in item['choices']:
            raise ValueError(f"Choose a listed option for {item['label']}.")
        tokens = value.split() if kind in {'tokens', 'integers'} else [value]
        if kind == 'integers' and any(int(token) < 1 for token in tokens):
            raise ValueError('Ranks must be positive integers.')
        for token in tokens:
            if item['flag']:
                command.append(item['flag'])
            command.append(token)
    command.extend(str(arg) for arg in extra)
    return command, cwd


class ScriptJob:
    def __init__(self, command, cwd, root=ROOT, console=False):
        self.command, self.cwd, self.root = command, Path(cwd), Path(root)
        self.console = console
        self.folder = self.root / 'runs/script-manager' / (datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
        self.process = None
        self.windows_job = None
        self.cancelled = False
        self.lock = threading.Lock()

    def _assign_windows_job(self):
        if os.name != 'nt':
            return
        # Job objects track children directly, without process enumeration/WMI.
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel.CreateJobObjectW.restype = wintypes.HANDLE
        kernel.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel.TerminateJobObject.argtypes = [wintypes.HANDLE, wintypes.UINT]
        kernel.TerminateJobObject.restype = wintypes.BOOL
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.CloseHandle.restype = wintypes.BOOL
        handle = kernel.CreateJobObjectW(None, None)
        if handle and kernel.AssignProcessToJobObject(handle, wintypes.HANDLE(int(self.process._handle))):
            self.windows_job = (kernel, handle)
        elif handle:
            kernel.CloseHandle(handle)

    def cancel(self):
        with self.lock:
            self.cancelled = True
            process = self.process
            if process and process.poll() is None and self.windows_job:
                kernel, handle = self.windows_job
                if kernel.TerminateJobObject(handle, 1):
                    return
        if process and process.poll() is None:
            if os.name == 'nt':
                subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True,
                               creationflags=subprocess.CREATE_NO_WINDOW)
                if process.poll() is None:
                    process.kill()
            else:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass

    def run(self, on_line=lambda line: None):
        self.folder.mkdir(parents=True)
        cache = self.root / 'runs/.cache/numba'
        cache.mkdir(parents=True, exist_ok=True)
        env = {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUNBUFFERED': '1',
               'NUMBA_CACHE_DIR': str(cache),
               'PYTHONPATH': str(self.root) + os.pathsep + os.environ.get('PYTHONPATH', '')}
        manifest = dict(command=self.command, cwd=str(self.cwd), status='running', log=str(self.folder / 'output.log'))
        def save():
            temporary = self.folder / 'job.tmp'
            temporary.write_text(json.dumps(manifest, indent=2), encoding='utf-8')
            temporary.replace(self.folder / 'job.json')
        save()
        try:
            with (self.folder / 'output.log').open('w', encoding='utf-8') as log:
                with self.lock:
                    if self.cancelled:
                        manifest['status'] = 'cancelled'
                        return manifest
                    self.process = subprocess.Popen(self.command, cwd=self.cwd, env=env,
                        stdin=None if self.console else subprocess.DEVNULL,
                        stdout=None if self.console else subprocess.PIPE,
                        stderr=None if self.console else subprocess.STDOUT,
                        text=True, encoding='utf-8', errors='replace',
                        creationflags=(subprocess.CREATE_NEW_CONSOLE if self.console else subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else 0,
                        start_new_session=os.name != 'nt')
                    self._assign_windows_job()
                with self.process as process:
                    if self.console:
                        line = 'Interactive output is shown in the separate console.\n'
                        log.write(line)
                        on_line(line)
                    else:
                        for line in process.stdout:
                            log.write(line)
                            log.flush()
                            on_line(line)
                    manifest['exit_code'] = process.wait()
                manifest['status'] = ('cancelled' if self.cancelled else
                                      'completed' if manifest['exit_code'] == 0 else 'failed')
        except Exception as error:
            manifest.update(status='failed', error=str(error))
            on_line(f'ERROR: {error}\n')
        finally:
            with self.lock:
                if self.windows_job:
                    kernel, handle = self.windows_job
                    kernel.CloseHandle(handle)
                    self.windows_job = None
            save()
        return manifest
