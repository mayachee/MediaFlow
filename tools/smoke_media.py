"""Exercise real local media processing using short synthetic fixtures. No uploads."""
import argparse
import json
import math
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import workflow
from pipelines.media_quality import probe, duration


def tone(path, rate, channels, frequency=440, seconds=1.2):
    import array
    samples = array.array('h')
    for frame in range(int(rate * seconds)):
        value = int(8000 * math.sin(2 * math.pi * frequency * frame / rate))
        samples.extend([value] * channels)
    with wave.open(str(path), 'wb') as output:
        output.setparams((channels, 2, rate, 0, 'NONE', 'not compressed'))
        output.writeframes(samples.tobytes())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'docs/media-smoke.json')
    args = parser.parse_args()
    from PIL import Image
    import yaml
    results = []
    # Fixtures are temporary. Workflow artifacts remain under runs/ for review.
    with tempfile.TemporaryDirectory(prefix='media-smoke-') as temporary:
        folder = Path(temporary)
        audio = folder / 'audio'
        images = folder / 'images'
        audio.mkdir()
        images.mkdir()
        tone(audio / '01_stereo.wav', 44100, 2)
        tone(audio / '02_mono.wav', 22050, 1, 660)
        for index, color in enumerate(('navy', 'darkgreen', 'maroon')):
            Image.new('RGB', (640, 360), color).save(images / f'{index}.png')
        config = yaml.safe_load((ROOT / 'modules/music_video_generator/config.yaml').read_text(encoding='utf-8'))
        config['video'].update(width=320, height=180, fps=24)
        # Timing/render checks are deterministic; beat analysis gets its own test.
        config['beat_detection']['enabled'] = False
        config_path = folder / 'config.yaml'
        config_path.write_text(yaml.safe_dump(config), encoding='utf-8')
        for effect in ('original', 'slow', 'reverse'):
            options = argparse.Namespace(audio=audio, url=None, images=images, config=config_path,
                metadata=None, effect=effect, instrumental=False, demucs_python='',
                max_songs=2, upload=False, privacy='private')
            job = workflow.execute(options)
            manifest = json.loads((job / 'manifest.json').read_text(encoding='utf-8'))
            video = Path(manifest['video'])
            # Decode every frame and audio packet, not just the container header.
            subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(video),
                            '-f', 'null', '-'], capture_output=True, check=True)
            expected = 4.8 if effect == 'slow' else 2.4
            if abs(manifest['quality']['expected_duration'] - expected) > 0.2:
                raise AssertionError(f'{effect} produced an unexpected audio duration')
            results.append({'case': f'two_tracks_{effect}', 'job': str(job.relative_to(ROOT)),
                            'decode': 'passed', 'quality': manifest['quality']})

        # Exercise the single-song multi-image path too.
        options.audio = audio / '01_stereo.wav'
        options.effect = 'original'
        job = workflow.execute(options)
        manifest = json.loads((job / 'manifest.json').read_text(encoding='utf-8'))
        subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', manifest['video'],
                        '-f', 'null', '-'], capture_output=True, check=True)
        results.append({'case': 'one_track_three_images', 'job': str(job.relative_to(ROOT)),
                        'decode': 'passed', 'quality': manifest['quality']})

        config['video'].update(width=1920, height=1080, fps=30)
        config_path.write_text(yaml.safe_dump(config), encoding='utf-8')
        job = workflow.execute(options)
        manifest = json.loads((job / 'manifest.json').read_text(encoding='utf-8'))
        subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', manifest['video'],
                        '-f', 'null', '-'], capture_output=True, check=True)
        results.append({'case': 'full_hd_with_motion', 'job': str(job.relative_to(ROOT)),
                        'decode': 'passed', 'quality': manifest['quality']})
        config['video'].update(width=320, height=180, fps=24)

        # Exercise the batch adapter directly without downloads or credentials.
        from pipelines import batch_pipeline
        batch_output = ROOT / 'runs' / 'smoke-batch'
        batch_output.mkdir(exist_ok=True)
        video = batch_pipeline.generate_batch_video(1, ['tone1', 'tone2'],
                    sorted(audio.glob('*.wav')), sorted(images.glob('*.png'))[:2], batch_output, config)
        from pipelines.media_quality import validate_video
        quality = validate_video(video, sorted(audio.glob('*.wav')), config)
        subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(video),
                        '-f', 'null', '-'], capture_output=True, check=True)
        results.append({'case': 'batch_adapter_two_tracks', 'decode': 'passed', 'quality': quality})

        import array
        rate = 22050
        samples = array.array('h')
        for index in range(rate * 8):
            phase = (index / rate) % 0.5
            envelope = math.exp(-phase * 80) if phase < 0.08 else 0
            samples.append(int(18000 * envelope * math.sin(2 * math.pi * 1000 * index / rate)))
        beat_file = folder / 'beats.wav'
        with wave.open(str(beat_file), 'wb') as output:
            output.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
            output.writeframes(samples.tobytes())
        from src.audio_analyzer import AudioAnalyzer
        beat_duration, beats, tempo = AudioAnalyzer().analyze(str(beat_file))
        if len(beats) < 4 or not 90 < tempo < 150:
            raise AssertionError(f'Beat detection failed: {len(beats)} beats, tempo={tempo}')
        results.append({'case': 'real_beat_detection', 'duration': beat_duration,
                        'beats': len(beats), 'tempo': tempo})

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'cases': results, 'scope': 'synthetic local media; no service calls'}, indent=2), encoding='utf-8')
    print(f'{len(results)} media cases passed. Report: {args.output}')


if __name__ == '__main__':
    main()
