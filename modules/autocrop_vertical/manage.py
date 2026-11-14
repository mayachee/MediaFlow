"""Scripts Studio adapter for pinned upstream AutoCrop-Vertical."""
import argparse
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[2]
BASE = Path(__file__).resolve().parent
SOURCE = ROOT / 'vendor/autocrop-vertical'
REVISION = 'e02663944597b89b63c7fbfda3ed7166954f5724'
SOURCE_SHA256 = 'eb58997e434422f3032a308aa227f61bc207ec85d284601df6519dd0cb728087'
VENV = BASE / '.venv'
PYTHON = VENV / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
CACHE = BASE / 'work'
MODEL = CACHE / 'yolov8n.pt'
REPOSITORY = 'https://github.com/kamilstanuch/Autocrop-vertical'


def checked(command, **kwargs):
    subprocess.run([str(part) for part in command], check=True, **kwargs)


def read_source():
    path = SOURCE / 'main.py'
    if not path.is_file():
        raise ValueError('AutoCrop source is missing. Run Setup AutoCrop Vertical in Studio.')
    text = path.read_text(encoding='utf-8')
    if hashlib.sha256(text.encode('utf-8')).hexdigest() != SOURCE_SHA256:
        raise ValueError('AutoCrop source differs from the supported revision. Restore the pinned source before running.')
    return text


def environment():
    CACHE.mkdir(parents=True, exist_ok=True)
    return {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUNBUFFERED': '1',
            'YOLO_CONFIG_DIR': str(CACHE / 'settings'), 'YOLO_AUTOINSTALL': 'false'}


def setup():
    SOURCE.mkdir(parents=True, exist_ok=True)
    for name in ['main.py', 'requirements.txt', 'README.md']:
        if not (SOURCE / name).is_file():
            print(f'Downloading pinned AutoCrop {name}...', flush=True)
            url = f'https://raw.githubusercontent.com/kamilstanuch/Autocrop-vertical/{REVISION}/{name}'
            with urllib.request.urlopen(url, timeout=90) as response:
                data = response.read()
            temporary = SOURCE / (name + '.download')
            temporary.write_bytes(data)
            temporary.replace(SOURCE / name)
    read_source()
    if not PYTHON.is_file():
        print('Creating a separate Python environment...', flush=True)
        checked([sys.executable, '-m', 'venv', VENV])
    checked([PYTHON, '-m', 'pip', '--disable-pip-version-check', 'install', '--upgrade', 'pip'])
    print('Installing CPU PyTorch (large download on the first setup)...', flush=True)
    checked([PYTHON, '-m', 'pip', '--disable-pip-version-check', 'install',
             'torch==2.7.1', 'torchvision==0.22.1', '--index-url', 'https://download.pytorch.org/whl/cpu',
             '--extra-index-url', 'https://pypi.org/simple'])
    print('Installing AutoCrop dependencies...', flush=True)
    checked([PYTHON, '-m', 'pip', '--disable-pip-version-check', 'install', '-r', SOURCE / 'requirements.txt'])
    print('Downloading/loading the YOLOv8 nano detector...', flush=True)
    checked([PYTHON, '-u', '-c', "from ultralytics import YOLO; YOLO('yolov8n.pt')"], cwd=CACHE, env=environment())
    if not MODEL.is_file():
        raise RuntimeError('Model download did not produce yolov8n.pt. Retry setup.')
    report = status()
    if not report['ready']:
        raise RuntimeError('Setup is incomplete. Check the status report above.')


def status():
    try:
        read_source()
        source_ok = True
    except (OSError, ValueError):
        source_ok = False
    packages_ok = False
    if PYTHON.is_file():
        code = "import cv2,torch,torchvision,ultralytics,scenedetect,tqdm; print('Dependencies loaded')"
        result = subprocess.run([str(PYTHON), '-c', code], capture_output=True, text=True,
                                encoding='utf-8', errors='replace', env=environment())
        packages_ok = result.returncode == 0
        if not packages_ok:
            print(result.stderr[-4000:])
    checks = dict(source=source_ok, environment=PYTHON.is_file(), dependencies=packages_ok,
                  model=MODEL.is_file(), ffmpeg=bool(shutil.which('ffmpeg')), ffprobe=bool(shutil.which('ffprobe')))
    report = dict(ready=all(checks.values()), checks=checks, revision=REVISION,
                  python=str(PYTHON), model=str(MODEL))
    print(json.dumps(report, indent=2))
    return report


def output_dimensions(ratio, resolution):
    if resolution == 'native':
        return None
    short = {'1080p': 1080, '720p': 720}[resolution]
    return {'16:9': (short * 16 // 9, short), '9:16': (short, short * 16 // 9),
            '4:5': (short, short * 5 // 4), '1:1': (short, short)}[ratio]


def adapt_source(text, model=Path('yolov8n.pt'), dimensions=None):
    """Apply small compatibility fixes in a per-job copy, preserving upstream."""
    replacements = [
        ('    target_center_x = (target_box[0] + target_box[2]) / 2\n'
         '    crop_height = frame_height\n'
         '    crop_width = int(crop_height * ASPECT_RATIO)',
         '    target_center_x = (target_box[0] + target_box[2]) / 2\n'
         '    target_center_y = (target_box[1] + target_box[3]) / 2\n'
         '    crop_width = min(frame_width, max(1, int(frame_height * ASPECT_RATIO)))\n'
         '    crop_height = min(frame_height, max(1, int(frame_width / ASPECT_RATIO)))'),
        ('    return x1, y1, x2, y2',
         '    x1 = max(0, min(frame_width - crop_width, int(target_center_x - crop_width / 2)))\n'
         '    y1 = max(0, min(frame_height - crop_height, int(target_center_y - crop_height / 2)))\n'
         '    return x1, y1, x1 + crop_width, y1 + crop_height'),
        ('                    scale_factor = OUTPUT_WIDTH / original_width\n'
         '                    scaled_height = int(original_height * scale_factor)\n'
         '                    scaled_frame = cv2.resize(frame, (OUTPUT_WIDTH, scaled_height))',
         '                    scale_factor = min(OUTPUT_WIDTH / original_width, OUTPUT_HEIGHT / original_height)\n'
         '                    scaled_height = max(1, min(OUTPUT_HEIGHT, int(original_height * scale_factor)))\n'
         '                    scaled_width = max(1, min(OUTPUT_WIDTH, int(original_width * scale_factor)))\n'
         '                    scaled_frame = cv2.resize(frame, (scaled_width, scaled_height))'),
        ('                    output_frame[y_offset:y_offset + scaled_height, :] = scaled_frame',
         '                    x_offset = (OUTPUT_WIDTH - scaled_width) // 2\n'
         '                    output_frame[y_offset:y_offset + scaled_height, x_offset:x_offset + scaled_width] = scaled_frame'),
        ('scene_manager.get_scene_list()', 'scene_manager.get_scene_list(start_in_scene=True)'),
        ("YOLO('yolov8n.pt')", f'YOLO({str(model)!r})'),
        ('    ffmpeg_process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)',
         '    ffmpeg_process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)\n'
         '    import threading\n'
         '    _stderr_chunks = []\n'
         '    def _drain_encoder_stderr():\n'
         '        for chunk in iter(lambda: ffmpeg_process.stderr.read(65536), b""):\n'
         '            _stderr_chunks.append(chunk)\n'
         '    _stderr_thread = threading.Thread(target=_drain_encoder_stderr, daemon=True)\n'
         '    _stderr_thread.start()'),
        ('    stderr_output = ffmpeg_process.stderr.read().decode()',
         '    _stderr_thread.join()\n    stderr_output = b"".join(_stderr_chunks).decode("utf-8", errors="replace")'),
    ]
    if dimensions:
        replacements.append(('    OUTPUT_HEIGHT = original_height', f'    OUTPUT_HEIGHT = {dimensions[1]}'))
    for before, after in replacements:
        if text.count(before) != 1:
            raise ValueError('The supported upstream patch no longer matches. Check the pinned source revision.')
        text = text.replace(before, after)
    return text


def probe(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
                            check=True, capture_output=True, text=True, encoding='utf-8')
    data = json.loads(result.stdout)
    video = next((stream for stream in data['streams'] if stream.get('codec_type') == 'video'), None)
    if not video or not video.get('width') or not video.get('height'):
        raise ValueError('Input must contain a readable video stream.')
    seconds = float(data.get('format', {}).get('duration', 0))
    if not math.isfinite(seconds) or seconds <= 0:
        raise ValueError('Video duration must be positive and finite.')
    return dict(width=video['width'], height=video['height'], duration=seconds,
                audio=any(stream.get('codec_type') == 'audio' for stream in data['streams']))


def validate_output(before, after, ratio):
    requested = tuple(int(value) for value in ratio.split(':'))
    expected_width = after['height'] * requested[0] / requested[1]
    if abs(after['width'] - expected_width) > 2:
        raise RuntimeError('Output aspect ratio does not match the requested format.')
    if abs(after['duration'] - before['duration']) > max(0.25, before['duration'] * 0.005):
        raise RuntimeError('Output duration differs from the source.')
    if before['audio'] != after['audio']:
        raise RuntimeError('Output audio stream does not match the source.')


def convert(args):
    source = args.input.expanduser().resolve()
    if not source.is_file():
        raise ValueError('Choose an existing video file.')
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise ValueError('FFmpeg and ffprobe must be on PATH.')
    if not PYTHON.is_file() or not MODEL.is_file():
        raise ValueError('Run Setup AutoCrop Vertical in Studio first.')
    if args.frame_skip < 0:
        raise ValueError('Scene frame skip cannot be negative.')
    dimensions = output_dimensions(args.ratio, args.resolution)
    text = adapt_source(read_source(), dimensions=dimensions)
    before = probe(source)
    output_root = args.output_root.expanduser().resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    folder = output_root / (datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
    folder.mkdir()
    # Ultralytics removes apostrophes from model path strings. A local basename
    # works even when the Windows account or output directory contains one.
    local_model = folder / 'yolov8n.pt'
    try:
        os.link(MODEL, local_model)
    except OSError:
        shutil.copy2(MODEL, local_model)
    output = folder / ('youtube.mp4' if args.ratio == '16:9' else 'vertical.mp4')
    runtime = folder / 'autocrop_runtime.py'
    runtime.write_text(text, encoding='utf-8')
    report = dict(status='running', source=str(source), output=str(output), revision=REVISION,
                  ratio=args.ratio, resolution=args.resolution, quality=args.quality, plan_only=args.plan_only, input_media=before,
                  patches=['single scene support', 'Windows model path compatibility', 'concurrent FFmpeg error drain',
                           'landscape crop bounds', 'fit without stretching', 'output resolution'])
    def save():
        temporary = folder / 'result.tmp'
        temporary.write_text(json.dumps(report, indent=2), encoding='utf-8')
        temporary.replace(folder / 'result.json')
    save()
    print(f'AutoCrop job folder: {folder}', flush=True)
    command = [PYTHON, '-u', runtime, '--input', source, '--output', output,
               '--ratio', args.ratio, '--quality', args.quality,
               '--frame-skip', str(args.frame_skip), '--encoder', 'auto']
    if args.plan_only:
        command.append('--plan-only')
    try:
        checked(command, cwd=folder, env=environment())
        if not args.plan_only:
            after = probe(output)
            validate_output(before, after, args.ratio)
            if dimensions and (after['width'], after['height']) != dimensions:
                raise RuntimeError('Output dimensions do not match the chosen resolution.')
            checked(['ffmpeg', '-v', 'error', '-xerror', '-i', output, '-f', 'null', '-'])
            report.update(output_media=after, validation='full decode, ratio, duration, audio presence')
        report['status'] = 'planned' if args.plan_only else 'completed'
        print(f'Analysis complete: {folder}' if args.plan_only else f'Video ready: {output}', flush=True)
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        save()
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    sub.add_parser('setup', help='Install isolated CPU dependencies and detector model')
    sub.add_parser('status', help='Check installation and external tools')
    run = sub.add_parser('convert', help='Analyze or convert an existing video')
    run.add_argument('--input', type=Path, required=True)
    run.add_argument('--output-root', type=Path, default=ROOT / 'runs/autocrop-vertical')
    run.add_argument('--ratio', choices=['16:9', '9:16', '4:5', '1:1'], default='9:16')
    run.add_argument('--resolution', choices=['native', '1080p', '720p'], default='native')
    run.add_argument('--quality', choices=['fast', 'balanced', 'high'], default='balanced')
    run.add_argument('--frame-skip', type=int, default=0)
    run.add_argument('--plan-only', action='store_true')
    args = parser.parse_args()
    try:
        if args.action == 'setup':
            setup()
        elif args.action == 'status':
            return 0 if status()['ready'] else 1
        else:
            convert(args)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'AutoCrop failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
