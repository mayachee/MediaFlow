"""Create audible demo inputs and try the actual production commands locally."""
import argparse
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipelines.audio_production import loudness
from pipelines.media_quality import probe


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def prepare(folder):
    import numpy as np
    import soundfile as sf
    from PIL import Image, ImageDraw
    inputs = folder / 'input'
    metadata = inputs / 'fixture.json'
    if inputs.exists():
        if not metadata.is_file():
            raise ValueError(f'{inputs} already exists without demo metadata; choose another --output')
        record = json.loads(metadata.read_text(encoding='utf-8'))
        for name, expected in record['hashes'].items():
            path = inputs / name
            if not path.is_file() or digest(path) != expected:
                raise ValueError(f'Demo input changed or missing: {path}. Choose another --output; originals will not be overwritten.')
        return inputs
    artwork = inputs / 'artwork'
    artwork.mkdir(parents=True)
    rate, seconds = 48000, 8
    time = np.arange(rate * seconds) / rate
    music = np.zeros_like(time)
    # Four soft chord plucks plus a melody and quiet, seeded percussion.
    chords = ((57, 60, 64), (53, 57, 60), (60, 64, 67), (55, 59, 62))
    for bar, notes in enumerate(chords):
        local = time - bar * 2
        envelope = np.where((local >= 0) & (local < 2), np.exp(-np.maximum(local, 0) * 1.7), 0)
        for note in notes:
            frequency = 440 * 2 ** ((note - 69) / 12)
            music += 0.15 * envelope * np.sin(2 * np.pi * frequency * time)
    for index, note in enumerate((69, 72, 76, 72, 69, 65, 69, 72, 72, 76, 79, 76, 67, 71, 74, 71)):
        local = time - index * 0.5
        envelope = np.where((local >= 0) & (local < 0.5), np.exp(-np.maximum(local, 0) * 7), 0)
        frequency = 440 * 2 ** ((note - 69) / 12)
        music += 0.12 * envelope * np.sin(2 * np.pi * frequency * time)
    noise = np.random.default_rng(7).normal(0, 1, len(time))
    phase = time % 0.5
    music += 0.015 * noise * np.exp(-phase * 80)
    music *= np.where(time < 4, 0.65, 1.0)
    music *= np.minimum(time / 0.03, 1) * np.minimum((seconds - time) / 0.1, 1)
    music *= 0.2 / np.max(np.abs(music))
    stereo = np.column_stack((music, music))
    sf.write(inputs / 'mix.wav', stereo, rate, subtype='FLOAT')
    sf.write(inputs / 'reference.wav', stereo * 2, rate, subtype='FLOAT')
    for index, color in enumerate(((20, 40, 85), (60, 25, 70))):
        image = Image.new('RGB', (1280, 720), color)
        draw = ImageDraw.Draw(image)
        for x in range(40, 1240):
            amplitude = int(65 + 100 * (0.5 + 0.5 * math.sin(x / 80)))
            draw.line((x, 360 - amplitude, x, 360 + amplitude), fill=(50 + index * 60, 140, 185))
        draw.rectangle((30, 30, 360, 100), fill=(10, 15, 25))
        draw.text((50, 50), f'PRODUCTION DEMO - SCENE {index + 1}', fill='white')
        image.save(artwork / f'{index + 1:02d}.png')
    names = ['mix.wav', 'reference.wav', 'artwork/01.png', 'artwork/02.png']
    metadata.write_text(json.dumps({'description': 'Synthetic 8-second musical phrase; reference is exactly twice the amplitude.',
        'sample_rate': rate, 'seconds': seconds, 'expected_reference_gain_db': 20 * math.log10(2),
        'hashes': {name: digest(inputs / name) for name in names}}, indent=2), encoding='utf-8')
    return inputs


def require(condition, message):
    if not condition:
        raise RuntimeError(message)


def run_command(arguments, log):
    result = subprocess.run([sys.executable, '-u', *[str(p) for p in arguments]],
                            cwd=ROOT, capture_output=True, text=True)
    log.write_text(result.stdout + '\n' + result.stderr, encoding='utf-8')
    if result.returncode:
        raise RuntimeError(f'Command failed; see {log}\n{result.stderr[-1000:]}')
    return result.stdout


def workflow_job(inputs, session, name, extra):
    output = run_command([ROOT / 'workflow.py', '--audio', inputs / 'mix.wav', *extra], session / f'{name}.log')
    line = next((line for line in output.splitlines() if line.startswith('Job saved to: ')), None)
    require(line is not None, 'Workflow returned no job location')
    job = Path(line.removeprefix('Job saved to: ').strip())
    manifest = json.loads((job / 'manifest.json').read_text(encoding='utf-8'))
    require(manifest['status'] == 'completed', f'Job did not complete: {job}')
    require(not manifest['upload_requested'], 'Demo jobs must remain local')
    return job, manifest


def save_report(folder, session, results, error=None):
    record = {'session': str(session), 'checks': results, 'error': error,
              'scope': 'Synthetic local inputs; no downloads, separation models, or uploads.'}
    (session / 'results.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    def link(path):
        return os.path.relpath(path, folder).replace('\\', '/')
    lines = ['# Production demo results', '',
        '[Original mix](input/mix.wav) | [Louder reference](input/reference.wav)', '',
        'The reference contains the same music at twice the amplitude (about +6.02 dB).', '',
        '| Test | Result | Open output |', '|---|---|---|']
    for result in results:
        lines.append(f'| {result["step"]} | {result["result"]} | [Open]({link(result["output"])}) |')
    if error:
        lines += ['', 'A check failed:', '', error]
    lines += ['', f'[Detailed results]({link(session / "results.json")})', '',
        'Listen to the original mix and reference, then the matched clips: the level advantage should disappear.',
        'The preview should play four seconds at 854x480. WAV masters are editable audio, not instrument stems.',
        'New workflow jobs have unique folders. Inputs are checked before reuse and never overwritten.']
    (folder / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--step', choices=['prepare', 'master', 'normalize', 'compare', 'preview', 'video', 'all'], default='all')
    parser.add_argument('--output', type=Path, default=ROOT / 'runs/production-demo')
    args = parser.parse_args()
    folder = args.output.resolve()
    results, session = [], None
    try:
        inputs = prepare(folder)
        session = folder / 'sessions' / (datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:6])
        session.mkdir(parents=True)
        before = {name: digest(inputs / name) for name in ('mix.wav', 'reference.wav')}
        steps = ['master', 'normalize', 'compare', 'preview'] if args.step == 'all' else [args.step]
        for step in steps:
            print(f'[{step}] Running local demo...', flush=True)
            if step == 'prepare':
                artifact, result = inputs / 'mix.wav', 'PASS: generated 8-second audio and artwork'
            elif step in ('master', 'normalize'):
                extra = ['--preset', 'master', '--wav-format', 'float']
                if step == 'normalize':
                    extra += ['--normalize', 'peak', '--peak-db', '-2']
                job, manifest = workflow_job(inputs, session, step, extra)
                export = manifest['export']
                require(export['codec'] == 'pcm_f32le', 'Expected an editable float WAV')
                if step == 'master':
                    import numpy as np
                    import soundfile as sf
                    original, _ = sf.read(inputs / 'mix.wav')
                    master, _ = sf.read(export['master'])
                    require(original.shape == master.shape and np.allclose(original, master, atol=1e-7),
                            'Normalization-off master changed the demo samples')
                    result = 'PASS: float WAV, normalization off, samples preserved'
                else:
                    peak = export['after']['sample_peak_dbfs']
                    require(abs(peak + 2) < 0.05, f'Expected -2 dBFS sample peak; measured {peak}')
                    result = f'PASS: peak {peak:.2f} dBFS; constant gain, no limiting'
                artifact = job / 'exports/export-report.md'
                print(f'  WAV: {export["master"]}', flush=True)
            elif step == 'compare':
                comparison = session / 'comparison'
                run_command([ROOT / 'tools/compare_audio.py', '--mix', inputs / 'mix.wav',
                    '--reference', inputs / 'reference.wav', '--output', comparison, '--listen-seconds', '8'], session / 'compare.log')
                report = json.loads((comparison / 'comparison.json').read_text(encoding='utf-8'))
                difference = report['mix_minus_reference']['integrated_lufs']
                require(abs(difference + 6.02) < 0.15, f'Expected about -6.02 LUFS difference; got {difference}')
                mix_level = loudness(comparison / 'mix-matched.wav')['input_i']
                reference_level = loudness(comparison / 'reference-matched.wav')['input_i']
                require(mix_level is not None and reference_level is not None and abs(mix_level - reference_level) < 0.2,
                        'Matched listening clips are not sufficiently close in loudness')
                artifact = comparison / 'comparison.md'
                result = f'PASS: mix/reference difference {difference:.2f} LU; listening clips matched'
            else:
                preset = 'video' if step == 'video' else 'preview'
                extra = ['--preset', preset, '--images', inputs / 'artwork']
                if preset == 'preview':
                    extra += ['--preview-start', '2', '--preview-seconds', '4']
                job, manifest = workflow_job(inputs, session, step, extra)
                quality = manifest['quality']
                width, height, seconds = (1920, 1080, 8) if step == 'video' else (854, 480, 4)
                require((quality['width'], quality['height']) == (width, height), 'Preset dimensions do not match')
                require(abs(quality['audio_duration'] - seconds) < 0.15, 'Unexpected demo duration')
                artifact = Path(manifest['video'])
                subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(artifact), '-f', 'null', '-'],
                               capture_output=True, check=True)
                result = f'PASS: {width}x{height}, {seconds}s, complete audio/video decode'
            results.append({'step': step, 'result': result, 'output': str(artifact)})
            print(f'  {result}\n  Open: {artifact}', flush=True)
        require(all(digest(inputs / name) == value for name, value in before.items()), 'A source file changed')
        save_report(folder, session, results)
        print(f'\nOpen the demo results: {folder / "README.md"}', flush=True)
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.CalledProcessError) as error:
        if session:
            save_report(folder, session, results, str(error))
        print(f'Demo failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
