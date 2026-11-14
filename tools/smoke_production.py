"""Exercise presets, reference comparison, and optional normalization locally."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipelines.audio_production import export_audio, analyze_audio, compare_reference
from pipelines.media_quality import probe, duration
import workflow


def main():
    import numpy as np
    import soundfile as sf
    from PIL import Image
    results = []
    output = ROOT / 'runs/production-check'
    # Keep each test run isolated, including original fixtures for inspection.
    import uuid
    output = output / uuid.uuid4().hex[:8]
    output.mkdir(parents=True)
    rate = 48000
    time = np.arange(rate * 6) / rate
    envelope = np.where(time < 3, 0.07, 0.14)
    mix = output / 'mix.wav'
    reference = output / 'reference.wav'
    samples = envelope * np.sin(2 * np.pi * 1000 * time)
    sf.write(mix, np.column_stack((samples, samples)), rate, subtype='FLOAT')
    sf.write(reference, np.column_stack((samples, samples)) * 2, rate, subtype='FLOAT')
    original_hash = hashlib.sha256(mix.read_bytes()).hexdigest()

    master, report = export_audio([mix], output / 'off', wav_format='float')
    actual, actual_rate = sf.read(master, always_2d=True)
    np.testing.assert_allclose(actual, np.column_stack((samples, samples)), atol=1e-7, rtol=1e-6)
    assert actual_rate == rate and report['normalization']['gain_db'] == 0
    results.append({'case': 'normalization_off_preserves_samples', 'status': 'passed'})

    peak_master, peak_report = export_audio([mix], output / 'peak', normalize='peak', peak_db=-2)
    assert abs(peak_report['after']['sample_peak_dbfs'] + 2) < 0.03
    peak_samples, _ = sf.read(peak_master, always_2d=True)
    original_rms = np.sqrt(np.mean(actual[:rate] ** 2)) / np.sqrt(np.mean(actual[-rate:] ** 2))
    peak_rms = np.sqrt(np.mean(peak_samples[:rate] ** 2)) / np.sqrt(np.mean(peak_samples[-rate:] ** 2))
    assert abs(original_rms - peak_rms) < 1e-4
    results.append({'case': 'peak_normalization_preserves_relative_dynamics', 'status': 'passed'})

    normalized, loud_report = export_audio([mix], output / 'loudness', normalize='loudness', target_lufs=-18)
    assert abs(loud_report['after']['integrated_lufs'] + 18) < 0.3
    assert not loud_report['normalization']['limiting']
    results.append({'case': 'gain_only_loudness_target', 'status': 'passed'})

    _, limited_report = export_audio([mix], output / 'limiting', normalize='loudness', target_lufs=-10, allow_limiting=True)
    assert limited_report['normalization']['limiting_allowed']
    assert limited_report['normalization']['processing_type'] in ('linear', 'dynamic')
    assert limited_report['after']['true_peak_dbtp'] <= -1.3
    results.append({'case': 'explicit_two_pass_loudness_mode', 'status': 'passed',
                    'processing_type': limited_report['normalization']['processing_type']})

    comparison = compare_reference(mix, reference, output / 'comparison', listen_seconds=4)
    assert abs(comparison['mix_minus_reference']['integrated_lufs'] + 6.02) < 0.15
    matched_mix = analyze_audio(Path(comparison['matched_listening']['mix']['file']))
    matched_reference = analyze_audio(Path(comparison['matched_listening']['reference']['file']))
    assert abs(matched_mix['integrated_lufs'] - matched_reference['integrated_lufs']) < 0.15
    assert all(clip['gain_db'] <= 0 for clip in comparison['matched_listening'].values())
    results.append({'case': 'reference_difference_and_matched_listening', 'status': 'passed'})

    images = output / 'images'
    images.mkdir()
    Image.new('RGB', (640, 360), 'navy').save(images / 'cover.png')
    def options(**changes):
        values = dict(audio=mix, url=None, images=images, max_songs=1, metadata=None,
            config=None, effect='original', instrumental=False, demucs_python='',
            upload=False, privacy='private', preset='master', normalize='off',
            sample_rate=rate, wav_format='24', preview_start=0, preview_seconds=None,
            allow_limiting=False, target_lufs=-16, peak_db=-1, true_peak=-1.5, listen_seconds=4, reference=None)
        values.update(changes)
        return argparse.Namespace(**values)

    # A master export must not depend on artwork or a functioning renderer.
    job = workflow.execute(options(images=output / 'no-artwork', wav_format='float', reference=reference))
    manifest = json.loads((job / 'manifest.json').read_text())
    assert manifest['status'] == 'completed' and 'video' not in manifest
    assert manifest['export']['codec'] == 'pcm_f32le'
    assert 'reference_comparison' in manifest
    results.append({'case': 'master_preset_without_artwork', 'status': 'passed', 'job': str(job.relative_to(ROOT))})

    job = workflow.execute(options(preset='preview', preview_start=1, preview_seconds=2))
    manifest = json.loads((job / 'manifest.json').read_text())
    assert manifest['quality']['width'] == 854 and manifest['quality']['height'] == 480
    assert abs(manifest['quality']['audio_duration'] - 2) < 0.1
    subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', manifest['video'], '-f', 'null', '-'], capture_output=True, check=True)
    results.append({'case': 'preview_range_and_preset', 'status': 'passed', 'job': str(job.relative_to(ROOT))})

    # Two tracks test that normalization affects the complete bus while the
    # renderer retains song boundaries and the final preset's sample rate.
    audio_folder = output / 'playlist'
    audio_folder.mkdir()
    import shutil
    shutil.copy2(mix, audio_folder / '01.wav')
    shutil.copy2(reference, audio_folder / '02.wav')
    job = workflow.execute(options(audio=audio_folder, max_songs=2, preset='video', normalize='loudness'))
    manifest = json.loads((job / 'manifest.json').read_text())
    assert len(manifest['audio']) == 2
    assert manifest['quality']['width'] == 1920 and manifest['quality']['height'] == 1080
    assert abs(manifest['quality']['audio_duration'] - 12) < 0.15
    streams = probe(manifest['video'])['streams']
    assert int(next(s['sample_rate'] for s in streams if s['codec_type'] == 'audio')) == rate
    subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', manifest['video'], '-f', 'null', '-'], capture_output=True, check=True)
    assert hashlib.sha256(mix.read_bytes()).hexdigest() == original_hash
    results.append({'case': 'video_preset_normalized_playlist', 'status': 'passed', 'job': str(job.relative_to(ROOT))})
    report_path = ROOT / 'docs/production-smoke.json'
    report_path.write_text(json.dumps({'cases': results, 'fixtures': str(output.relative_to(ROOT)),
        'scope': 'Real synthetic local audio/video; no external downloads or uploads'}, indent=2), encoding='utf-8')
    print(f'{len(results)} production checks passed. Report: {report_path}')


if __name__ == '__main__':
    main()
