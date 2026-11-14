"""Measure existing WAV outputs without modifying them. Listening is still required."""
import argparse
import json
import math
import re
import subprocess
from pathlib import Path


def measure(path):
    import numpy as np
    import soundfile as sf
    peak, total_squares, count, clipped = 0.0, 0.0, 0, 0
    with sf.SoundFile(path) as source:
        info = {'file': path.as_posix(), 'duration_seconds': len(source) / source.samplerate,
                'sample_rate': source.samplerate, 'channels': source.channels, 'subtype': source.subtype}
        for block in source.blocks(blocksize=262144, dtype='float64', always_2d=True):
            if not np.isfinite(block).all():
                raise ValueError(f'Non-finite audio samples: {path}')
            peak = max(peak, float(np.max(np.abs(block))))
            total_squares += float(np.sum(block * block))
            count += block.size
            clipped += int(np.sum(np.abs(block) >= 0.9999))
    result = subprocess.run(['ffmpeg', '-nostdin', '-hide_banner', '-i', str(path),
                '-af', 'loudnorm=I=-14:TP=-1.5:LRA=11:print_format=json',
                '-f', 'null', '-'], capture_output=True, text=True, check=True)
    matches = re.findall(r'\{\s*"input_i".*?\}', result.stderr, re.S)
    loudness = json.loads(matches[-1]) if matches else {}
    peak_db = 20 * math.log10(peak) if peak else None
    rms = math.sqrt(total_squares / count) if count else 0
    info.update(peak_dbfs=peak_db, rms_dbfs=20 * math.log10(rms) if rms else None,
                near_full_scale_samples=clipped, sample_count=count,
                integrated_lufs=loudness.get('input_i'), true_peak_dbtp=loudness.get('input_tp'),
                loudness_range_lu=loudness.get('input_lra'))
    warnings = []
    if peak_db is None or peak_db < -50:
        warnings.append('Silent or very quiet output')
    if clipped:
        warnings.append('Near-full-scale samples detected; inspect for clipping')
    if loudness and float(loudness['input_tp']) > -1:
        warnings.append('True peak above -1 dBTP; leave more encoding headroom')
    info['review_notes'] = warnings
    return info


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('files', nargs='+', type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    measurements = [measure(path) for path in args.files]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({'measurements': measurements,
        'scope': 'full-file sample statistics and FFmpeg loudness measurement; does not judge musical performance'}, indent=2), encoding='utf-8')
    for result in measurements:
        print(f"{result['file']}: {result['duration_seconds']:.1f}s, {result['integrated_lufs']} LUFS, {result['true_peak_dbtp']} dBTP, notes={result['review_notes']}")


if __name__ == '__main__':
    main()
