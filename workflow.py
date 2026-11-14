"""Connect audio tools and video creation using isolated job directories."""
import argparse
import json
import shutil
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path

from pipelines.media_quality import validate_video
from pipelines.audio_production import (load_preset, export_audio, compare_reference,
                                       split_for_renderer, validate_options)

ROOT = Path(__file__).resolve().parent
AUDIO = {'.mp3', '.wav', '.flac', '.m4a', '.ogg', '.webm', '.mp4', '.aac'}
VISUAL = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.mp4', '.mov', '.mkv', '.webm'}


def run(command, cwd=ROOT):
    subprocess.run([str(part) for part in command], cwd=cwd, check=True)


def require_files(folder, extensions):
    files = sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in extensions)
    if not files:
        raise ValueError(f'No supported files in {folder}')
    return files


def save_manifest(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2), encoding='utf-8')
    temporary.replace(path)


def execute(args):
    # Validate inputs before creating the job or contacting external services.
    validate_options(args)
    preset_name = getattr(args, 'preset', None)
    normalization = getattr(args, 'normalize', 'off')
    reference = getattr(args, 'reference', None)
    timeline_path = getattr(args, 'timeline', None)
    timeline_document = None
    if timeline_path:
        from modules.music_video_generator.src.timeline import load_timeline
        timeline_document = load_timeline(timeline_path)
        if preset_name == 'master':
            raise ValueError('--timeline applies to video or preview exports, not audio-only masters')
    if reference and not reference.is_file():
        raise ValueError(f'Reference audio not found: {reference}')
    if args.upload and preset_name in ('master', 'preview'):
        raise ValueError('Only the video preset can upload; preview and master are local outputs')
    if preset_name != 'preview' and (getattr(args, 'preview_start', 0) or getattr(args, 'preview_seconds', None)):
        raise ValueError('Preview range options require --preset preview')
    images = args.images.resolve()
    visuals = (list(dict.fromkeys(Path(row['source']) for row in timeline_document['scenes']))
               if timeline_document else require_files(images, VISUAL) if preset_name != 'master' else [])
    sources = []
    if args.audio:
        source = args.audio.resolve()
        sources = require_files(source, AUDIO) if source.is_dir() else [source]
        if any(not p.is_file() or p.suffix.lower() not in AUDIO for p in sources):
            raise ValueError('Audio input must be a supported file or directory')
        sources = sources[:args.max_songs]
    metadata = args.metadata.resolve() if args.metadata else None
    if metadata and not metadata.is_file():
        raise ValueError(f'Metadata not found: {metadata}')
    if not shutil.which('ffmpeg'):
        raise ValueError('ffmpeg must be available on PATH')
    if not shutil.which('ffprobe'):
        raise ValueError('ffprobe must be available on PATH')
    if args.instrumental and not Path(args.demucs_python).is_file() and not shutil.which(args.demucs_python):
        raise ValueError('Demucs Python not found; run modules/vocal-remover/run.ps1 install or use --demucs-python')

    job = ROOT / 'runs' / (datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8])
    audio_dir = job / 'audio'
    image_dir = job / 'images'
    audio_dir.mkdir(parents=True)
    image_dir.mkdir()
    manifest = {'status': 'running', 'stage': 'prepare', 'audio': [],
                'effect': args.effect, 'instrumental': args.instrumental,
                'privacy': args.privacy, 'upload_requested': args.upload,
                'preset': preset_name or 'video', 'normalization': normalization}
    manifest_path = job / 'manifest.json'

    def stage(name):
        manifest['stage'] = name
        save_manifest(manifest_path, manifest)
        print(f'[{name}] {job}', flush=True)

    try:
        stage('prepare')
        copied_visuals = {}
        for index, path in enumerate(visuals):
            destination = image_dir / f'{index:04d}{path.suffix.lower()}'
            shutil.copy2(path, destination)
            copied_visuals[str(path)] = str(destination)
        if timeline_document:
            timeline_document = {**timeline_document, 'scenes': [{**row, 'source': copied_visuals[row['source']]}
                                             for row in timeline_document['scenes']]}
        if args.url:
            stage('download')
            run([sys.executable, ROOT / 'modules/automatic_upload/download_mp3.py',
                 '--url', args.url, '--no-mp3', '--output-dir', audio_dir])
            sources = require_files(audio_dir, AUDIO)[:args.max_songs]
        else:
            copied = []
            for index, path in enumerate(sources):
                destination = audio_dir / f'{index:04d}_{path.name}'
                shutil.copy2(path, destination)
                copied.append(destination)
            sources = copied

        processed = job / 'processed'
        processed.mkdir()
        for index, source in enumerate(sources):
            current = source
            if args.instrumental:
                stage(f'separate-{index}')
                run([args.demucs_python, '-m', 'demucs', '--two-stems', 'vocals',
                     '-n', 'htdemucs', '-o', job / 'stems', source])
                current = job / 'stems' / 'htdemucs' / source.stem / 'no_vocals.wav'
                if not current.is_file():
                    raise RuntimeError(f'Missing instrumental: {current}')
            destination = processed / f'{index:04d}_{source.stem}.wav'
            stage(f'process-{index}')
            command = ['ffmpeg', '-nostdin', '-y', '-i', current, '-vn']
            if args.effect != 'original':
                command += ['-af', {'slow': 'atempo=0.5', 'reverse': 'areverse'}[args.effect]]
            codec = 'pcm_f32le' if getattr(args, 'wav_format', '24') == 'float' else 'pcm_s24le'
            run(command + ['-c:a', codec, destination])
            if not destination.is_file() or destination.stat().st_size == 0:
                raise RuntimeError(f'Missing processed audio: {destination}')
            manifest['audio'].append(str(destination))

        if (preset_name or reference or normalization != 'off' or
                getattr(args, 'wav_format', '24') != '24' or getattr(args, 'sample_rate', 48000) != 48000):
            stage('export')
            preset = load_preset(preset_name or 'video')
            sample_rate = getattr(args, 'sample_rate', 48000)
            original_paths = [Path(p) for p in manifest['audio']]
            start = getattr(args, 'preview_start', 0)
            seconds = (getattr(args, 'preview_seconds', None) or preset['seconds']) if preset_name == 'preview' else None
            if start:
                from pipelines.media_quality import duration
                if start >= sum(duration(p) for p in original_paths):
                    raise ValueError('Preview start is beyond the end of the selected audio')
            master, report = export_audio(original_paths, job / 'exports', sample_rate=sample_rate,
                wav_format=getattr(args, 'wav_format', '24'), normalize=normalization,
                target_lufs=getattr(args, 'target_lufs', -16), peak_db=getattr(args, 'peak_db', -1),
                true_peak=getattr(args, 'true_peak', -1.5), allow_limiting=getattr(args, 'allow_limiting', False),
                start=start, seconds=seconds)
            manifest['export'] = report
            if reference:
                stage('reference-comparison')
                manifest['reference_comparison'] = compare_reference(master, reference, job / 'comparison',
                    listen_seconds=getattr(args, 'listen_seconds', 30))
            if preset_name == 'master':
                manifest['status'] = 'completed'
                stage('completed')
                return job
            if preset_name == 'preview':
                if timeline_document and abs(timeline_document.get('planned_seconds', -1) - report['after']['duration_seconds']) > 0.15:
                    from modules.music_video_generator.src.timeline import crop_timeline
                    from pipelines.media_quality import duration
                    infos = [{'duration': duration(p)} for p in original_paths]
                    timeline_document = crop_timeline(timeline_document, infos, start,
                        report['after']['duration_seconds'], preset['video']['fps'])
                processed = job / 'preview-audio'
                processed.mkdir()
                shutil.copy2(master, processed / 'preview.wav')
                render_paths = [processed / 'preview.wav']
            else:
                processed = job / 'render-audio'
                render_paths = split_for_renderer(master, original_paths, processed, sample_rate)
            manifest['audio'] = [str(p) for p in render_paths]

        stage('render')
        import yaml
        config_source = getattr(args, 'config', None) or ROOT / 'modules/music_video_generator/config.yaml'
        config = yaml.safe_load(config_source.read_text(encoding='utf-8'))
        if preset_name:
            config['video'].update(preset['video'])
        if 'export' in manifest:
            config['video']['audio_sample_rate'] = sample_rate
        config['paths'].update(input_audio=str(processed), input_images=str(image_dir), output=str(job / 'video'))
        config_path = job / 'config.yaml'
        config_path.write_text(yaml.safe_dump(config), encoding='utf-8')
        video = job / 'video' / 'music_video.mp4'
        command = [sys.executable, ROOT / 'modules/music_video_generator/main.py', '--config', config_path,
                   '--output', video, '--max-songs', args.max_songs]
        if timeline_document:
            saved_timeline = job / 'timeline.yaml'
            saved_timeline.write_text(yaml.safe_dump(timeline_document), encoding='utf-8')
            manifest['timeline'] = str(saved_timeline)
            command += ['--timeline', saved_timeline]
        run(command)
        if not video.is_file() or video.stat().st_size == 0:
            raise RuntimeError('Renderer did not produce a video')
        manifest['video'] = str(video)
        stage('quality-check')
        manifest['quality'] = validate_video(video, [Path(p) for p in manifest['audio']], config)
        if args.upload:
            stage('upload')
            command = [sys.executable, ROOT / 'modules/automatic_YouTube_upload/youtube_uploader.py',
                       '--video', video, '--privacy', args.privacy]
            if metadata:
                command += ['--metadata', metadata]
            run(command)
            receipt = video.with_suffix('.upload.json')
            if receipt.is_file():
                manifest['upload'] = json.loads(receipt.read_text(encoding='utf-8'))
        manifest['status'] = 'completed'
        stage('completed')
        return job
    except Exception as error:
        manifest.update(status='failed', error=str(error))
        save_manifest(manifest_path, manifest)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument('--audio', type=Path, help='Local audio file or directory')
    source.add_argument('--url', help='YouTube URL to download')
    parser.add_argument('--images', type=Path, default=ROOT / 'modules/music_video_generator/input/images')
    parser.add_argument('--effect', choices=['original', 'slow', 'reverse'], default='original')
    parser.add_argument('--instrumental', action='store_true', help='Remove vocals with Demucs')
    parser.add_argument('--demucs-python', default=str(ROOT / 'modules/vocal-remover/.venv/Scripts/python.exe'))
    parser.add_argument('--max-songs', type=int, default=4)
    parser.add_argument('--metadata', type=Path, help='Existing metadata JSON for the uploader')
    parser.add_argument('--config', type=Path, help='Video YAML configuration; job paths are supplied automatically')
    parser.add_argument('--timeline', type=Path, help='Explicit visual mapping YAML; source paths are relative to that YAML')
    parser.add_argument('--preset', choices=['preview', 'master', 'video'], help='Export preset; explicit video also retains a WAV master')
    parser.add_argument('--reference', type=Path, help='Reference audio for measurements and matched listening clips')
    parser.add_argument('--normalize', choices=['off', 'peak', 'loudness'], default='off')
    parser.add_argument('--allow-limiting', action='store_true', help='Allow dynamic loudness processing; requires --normalize loudness')
    parser.add_argument('--target-lufs', type=float, default=-16)
    parser.add_argument('--peak-db', type=float, default=-1, help='Sample peak target for peak normalization')
    parser.add_argument('--true-peak', type=float, default=-1.5, help='True-peak ceiling for loudness normalization')
    parser.add_argument('--sample-rate', type=int, choices=[44100, 48000, 96000], default=48000)
    parser.add_argument('--wav-format', choices=['24', 'float'], default='24')
    parser.add_argument('--preview-start', type=float, default=0)
    parser.add_argument('--preview-seconds', type=float, help='Preview duration; default 30 seconds')
    parser.add_argument('--listen-seconds', type=float, default=30, help='Maximum length of reference listening clips')
    parser.add_argument('--upload', action='store_true', help='Upload the completed video')
    parser.add_argument('--privacy', choices=['private', 'unlisted', 'public'], default='private')
    args = parser.parse_args()
    if args.max_songs < 1:
        parser.error('--max-songs must be positive')
    try:
        print(f'Job saved to: {execute(args)}')
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f'Workflow failed: {error}', file=sys.stderr)
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
