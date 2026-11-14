"""Shared export and reference-analysis tools; source files are never modified."""
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile

from .media_quality import duration, probe

ROOT = Path(__file__).resolve().parents[1]
BANDS = ((20, 80), (80, 250), (250, 1000), (1000, 4000), (4000, 10000), (10000, 20000))
CODECS = {'24': 'pcm_s24le', 'float': 'pcm_f32le'}


def checked(command):
    result = subprocess.run([str(p) for p in command], capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'FFmpeg failed: {result.stderr[-3000:]}')
    return result


def finite(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def load_preset(name):
    presets = json.loads((ROOT / 'config/export-presets.json').read_text(encoding='utf-8'))
    return presets[name]


def validate_options(args):
    values = {'target_lufs': (-70, -5), 'peak_db': (-99, 0), 'true_peak': (-9, 0),
              'preview_start': (0, float('inf')), 'preview_seconds': (0.001, float('inf')),
              'listen_seconds': (1, float('inf'))}
    for name, (low, high) in values.items():
        value = getattr(args, name, None)
        if value is not None and (not math.isfinite(value) or not low <= value <= high):
            raise ValueError(f'{name.replace("_", "-")} must be finite and between {low} and {high}')
    if getattr(args, 'allow_limiting', False) and getattr(args, 'normalize', 'off') != 'loudness':
        raise ValueError('--allow-limiting requires --normalize loudness')
    if getattr(args, 'sample_rate', 48000) not in (44100, 48000, 96000):
        raise ValueError('sample-rate must be 44100, 48000, or 96000')


def split_for_renderer(master, originals, folder, sample_rate):
    """Keep song/visual boundaries after processing the complete playlist bus."""
    folder.mkdir()
    paths, offset = [], 0
    for index, source in enumerate(originals):
        count = round(duration(source) * sample_rate)
        destination = folder / f'{index:04d}.wav'
        selection = f'atrim=start_sample={offset}'
        if index < len(originals) - 1:
            selection += f':end_sample={offset + count}'
        checked(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', master,
                 '-af', selection + ',asetpts=PTS-STARTPTS', '-c:a', 'pcm_f32le', destination])
        paths.append(destination)
        offset += count
    return paths


def loudness(path):
    # The filter's output is discarded: this pass only measures the original.
    result = checked(['ffmpeg', '-nostdin', '-hide_banner', '-i', path, '-map', '0:a:0',
                      '-af', 'loudnorm=I=-16:TP=-1.5:LRA=50:print_format=json', '-f', 'null', '-'])
    matches = re.findall(r'\{\s*"input_i".*?\}', result.stderr, re.S)
    if not matches:
        raise RuntimeError(f'FFmpeg returned no loudness measurements for {path}')
    raw = json.loads(matches[-1])
    return {key: finite(raw[key]) for key in ('input_i', 'input_tp', 'input_lra', 'input_thresh')}


def analyze_audio(path):
    """Stream sample statistics and averaged stereo-channel spectral energy."""
    import numpy as np
    path = Path(path).resolve()
    measurements = loudness(path)
    stream = next(s for s in probe(path)['streams'] if s['codec_type'] == 'audio')
    if int(stream['channels']) > 2:
        raise ValueError('Reference/sample analysis supports mono or stereo; export a stereo mix first')
    rate, block_frames = int(stream['sample_rate']), 8192
    energies = np.zeros(len(BANDS))
    sample_count, squares, peak = 0, 0.0, 0.0
    frequencies = np.fft.rfftfreq(block_frames, 1 / rate)
    masks = [(frequencies >= low) & (frequencies < high) for low, high in BANDS]
    window = np.hanning(block_frames)[:, None]
    # A temporary stderr file prevents deadlock and keeps long audio out of RAM.
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path),
            '-map', '0:a:0', '-vn', '-ar', str(rate), '-ac', '2', '-f', 'f32le', '-'],
            stdout=subprocess.PIPE, stderr=errors)
        try:
            pending = b''
            while True:
                chunk = process.stdout.read(block_frames * 2 * 4 - len(pending))
                pending += chunk
                if len(pending) < block_frames * 2 * 4 and chunk:
                    continue
                if not pending:
                    break
                if len(pending) % 8:
                    raise RuntimeError('Incomplete decoded audio frame')
                samples = np.frombuffer(pending, dtype='<f4').reshape(-1, 2).astype(np.float64)
                pending = b''
                if not np.isfinite(samples).all():
                    raise ValueError('Audio contains non-finite samples')
                sample_count += samples.size
                squares += float(np.sum(samples * samples))
                peak = max(peak, float(np.max(np.abs(samples))))
                padded = np.zeros((block_frames, 2))
                padded[:len(samples)] = samples
                spectrum = np.sum(np.abs(np.fft.rfft(padded * window, axis=0)) ** 2, axis=1)
                for index, mask in enumerate(masks):
                    energies[index] += float(spectrum[mask].sum())
                if not chunk:
                    break
            process.stdout.close()
            if process.wait():
                errors.seek(0)
                raise RuntimeError(errors.read().decode(errors='replace')[-3000:])
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
            process.stdout.close()
    rms = math.sqrt(squares / sample_count) if sample_count else 0
    total = float(energies.sum())
    rms_db = 20 * math.log10(rms) if rms else None
    peak_db = 20 * math.log10(peak) if peak else None
    return {'file': str(path), 'duration_seconds': duration(path), 'analysis_sample_rate': rate,
        'integrated_lufs': measurements['input_i'], 'true_peak_dbtp': measurements['input_tp'],
        'loudness_range_lu': measurements['input_lra'], 'rms_dbfs': rms_db,
        'sample_peak_dbfs': peak_db, 'crest_factor_db': peak_db - rms_db if rms and peak else None,
        'spectral_energy_percent': {f'{low}-{high} Hz': float(energy / total * 100) if total else 0.0
                                    for (low, high), energy in zip(BANDS, energies)}}


def gain_plan(mode, stats, target_lufs=-16.0, peak_db=-1.0, true_peak=-1.5):
    if mode == 'off':
        return {'mode': 'off', 'gain_db': 0.0, 'limiting': False}
    if mode == 'peak':
        measured = stats.get('sample_peak_dbfs')
        if measured is None:
            raise ValueError('Cannot peak-normalize silent audio')
        return {'mode': mode, 'gain_db': peak_db - measured, 'limiting': False,
                'target_peak_dbfs': peak_db}
    if stats.get('integrated_lufs') is None or stats.get('true_peak_dbtp') is None:
        raise ValueError('Audio is silent or too short for reliable loudness normalization')
    desired = target_lufs - stats['integrated_lufs']
    gain = min(desired, true_peak - stats['true_peak_dbtp'])
    return {'mode': mode, 'gain_db': gain, 'limiting': False, 'target_lufs': target_lufs,
            'true_peak_ceiling_dbtp': true_peak, 'gain_limited_by_headroom': gain < desired - 0.01,
            'note': 'Constant gain preserves dynamics; the loudness target may be unreachable without limiting.'}


def export_audio(sources, folder, *, sample_rate=48000, wav_format='24',
                 normalize='off', target_lufs=-16.0, peak_db=-1.0, true_peak=-1.5,
                 allow_limiting=False, start=0.0, seconds=None):
    if not sources:
        raise ValueError('At least one audio source is required')
    if wav_format not in CODECS or normalize not in ('off', 'peak', 'loudness'):
        raise ValueError('Unsupported WAV format or normalization mode')
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    program = folder / 'program-original.wav'
    master = folder / 'master.wav'
    command = ['ffmpeg', '-nostdin', '-y', '-v', 'error']
    filters = []
    for index, source in enumerate(sources):
        command += ['-i', source]
        filters.append(f'[{index}:a:0]aformat=sample_fmts=fltp:sample_rates={sample_rate}:'
                       f'channel_layouts=stereo,asetpts=PTS-STARTPTS[a{index}]')
    labels = ''.join(f'[a{index}]' for index in range(len(sources)))
    filters.append(f'{labels}concat=n={len(sources)}:v=0:a=1[out]')
    command += ['-filter_complex', ';'.join(filters), '-map', '[out]']
    if start:
        command += ['-ss', str(start)]
    if seconds:
        command += ['-t', str(seconds)]
    checked(command + ['-ar', str(sample_rate), '-c:a', 'pcm_f32le', program])
    before = analyze_audio(program)
    plan = gain_plan(normalize, before, target_lufs, peak_db, true_peak)
    command = ['ffmpeg', '-nostdin', '-y', '-v', 'error', '-i', program, '-map', '0:a:0']
    if normalize == 'loudness' and allow_limiting:
        stats = loudness(program)
        # A two-pass filter can fall back to dynamic limiting. That is explicit
        # consent here, rather than an implicit change to the gain-only mode.
        lra = max(11.0, min(50.0, stats['input_lra'] or 0))
        filter_text = (f'loudnorm=I={target_lufs}:TP={true_peak}:LRA={lra}:linear=true:'
            f'measured_I={stats["input_i"]}:measured_TP={stats["input_tp"]}:'
            f'measured_LRA={stats["input_lra"]}:measured_thresh={stats["input_thresh"]}:print_format=json')
        command[command.index('error')] = 'info'
        command += ['-af', filter_text]
        plan.update(limiting_allowed=True, gain_db=None,
                    note='Two-pass loudnorm may use dynamic limiting to meet the selected targets.')
        plan.pop('gain_limited_by_headroom', None)
    elif normalize != 'off':
        command += ['-af', f'volume={plan["gain_db"]}dB']
    result = checked(command + ['-ar', str(sample_rate), '-c:a', CODECS[wav_format], master])
    if normalize == 'loudness' and allow_limiting:
        matches = re.findall(r'\{\s*"input_i".*?\}', result.stderr, re.S)
        if not matches:
            raise RuntimeError('Normalization completed without a processing-type report')
        processing_type = json.loads(matches[-1])['normalization_type']
        plan.update(processing_type=processing_type, limiting=processing_type == 'dynamic')
    after = analyze_audio(master)
    stream = next(s for s in probe(master)['streams'] if s['codec_type'] == 'audio')
    report = {'source_files': [str(Path(p).resolve()) for p in sources],
        'sample_rate': int(stream['sample_rate']), 'codec': stream['codec_name'],
        'selection': {'start_seconds': start, 'maximum_seconds': seconds},
        'normalization': plan, 'before': before, 'after': after,
        'master': str(master.resolve()), 'original_program': str(program.resolve())}
    (folder / 'export-report.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    def display(value):
        return 'n/a' if value is None else f'{value:.2f}'
    summary = ['# Audio export', '', f'File: `{master.name}`',
        f'Format: {sample_rate} Hz stereo, {stream["codec_name"]}',
        f'Normalization: {normalize}; limiting: {plan["limiting"]}', '',
        '| Measurement | Before | After |', '|---|---:|---:|']
    for key in ('integrated_lufs', 'true_peak_dbtp', 'sample_peak_dbfs', 'loudness_range_lu'):
        summary.append(f'| {key} | {display(before[key])} | {display(after[key])} |')
    if plan.get('note'):
        summary += ['', plan['note']]
    summary += ['', 'Original input files and the unnormalized float program are retained.']
    (folder / 'export-report.md').write_text('\n'.join(summary) + '\n', encoding='utf-8')
    return master, report


def compare_reference(mix, reference, folder, *, listen_seconds=30.0):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    mix_stats, reference_stats = analyze_audio(mix), analyze_audio(reference)
    for stats in (mix_stats, reference_stats):
        if stats['integrated_lufs'] is None or stats['true_peak_dbtp'] is None:
            raise ValueError('Reference comparison needs measurable non-silent audio in both files')
    keys = ('integrated_lufs', 'true_peak_dbtp', 'loudness_range_lu', 'crest_factor_db')
    differences = {key: mix_stats[key] - reference_stats[key]
                   if mix_stats[key] is not None and reference_stats[key] is not None else None for key in keys}
    spectral = {key: mix_stats['spectral_energy_percent'][key] - value
                for key, value in reference_stats['spectral_energy_percent'].items()}
    # Attenuation only: put both at a common level that has true-peak headroom.
    selections = {}
    for label, source in (('mix', mix), ('reference', reference)):
        selection = folder / f'{label}-selection.wav'
        checked(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', source, '-map', '0:a:0',
                 '-t', str(listen_seconds), '-ar', '48000', '-ac', '2', '-c:a', 'pcm_f32le', selection])
        stats = loudness(selection)
        if stats['input_i'] is None or stats['input_tp'] is None:
            raise ValueError(f'{label} listening selection is silent or too short; choose different input excerpts')
        selections[label] = (selection, stats)
    level = min(stats['input_i'] + min(0, -1.5 - stats['input_tp']) for _, stats in selections.values())
    clips = {}
    for label, (source, stats) in selections.items():
        destination = folder / f'{label}-matched.wav'
        gain = level - stats['input_i']
        checked(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-i', source, '-map', '0:a:0',
                 '-t', str(listen_seconds), '-af', f'volume={gain}dB', '-ar', '48000',
                 '-ac', '2', '-c:a', 'pcm_s24le', destination])
        clips[label] = {'file': str(destination.resolve()), 'gain_db': gain}
    report = {'mix': mix_stats, 'reference': reference_stats, 'mix_minus_reference': differences,
        'spectral_difference_percentage_points': spectral, 'matched_listening': clips,
        'common_loudness_lufs': level, 'listen_maximum_seconds': listen_seconds,
        'scope': 'Full-file analysis; listening clips start at zero and use separately measured excerpt loudness. '
                 'Frequency bands summarize channel-averaged energy, not an EQ prescription or musical score.'}
    (folder / 'comparison.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    lines = ['# Reference comparison', '', f'Mix: `{Path(mix).name}`', f'Reference: `{Path(reference).name}`', '',
             '| Measurement | Mix | Reference | Difference |', '|---|---:|---:|---:|']
    for key in keys:
        values = [mix_stats[key], reference_stats[key], differences[key]]
        rendered = ['n/a' if value is None else f'{value:.2f}' for value in values]
        lines.append(f'| {key} | ' + ' | '.join(rendered) + ' |')
    lines += ['', '## Frequency balance', '', '| Band | Mix energy % | Reference energy % | Difference (points) |',
              '|---|---:|---:|---:|']
    for band, difference in spectral.items():
        lines.append(f'| {band} | {mix_stats["spectral_energy_percent"][band]:.2f} | '
                     f'{reference_stats["spectral_energy_percent"][band]:.2f} | {difference:+.2f} |')
    lines += ['', '[Mix listening clip](mix-matched.wav) · [Reference listening clip](reference-matched.wav)', '',
              report['scope'], '', 'Listen for balance, phrasing, artifacts, and tonal intent. No automatic EQ was applied.']
    (folder / 'comparison.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return report
