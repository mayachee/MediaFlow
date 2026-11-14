"""Render one synthetic MIDI note through each bundled FluidSynth installation."""
import json
from pathlib import Path
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipelines.media_quality import probe


def main():
    output = ROOT / 'runs/native-smoke'
    output.mkdir(parents=True, exist_ok=True)
    track = bytes.fromhex('00ff510307a12000c00000903c508360803c0000ff2f00')
    midi = output / 'test.mid'
    midi.write_bytes(b'MThd' + struct.pack('>IHHH', 6, 0, 1, 480) + b'MTrk' + struct.pack('>I', len(track)) + track)
    reports = []
    for folder in (ROOT / 'vendor',):
        executable = folder / 'fluidsynth-bin/fluidsynth-v2.6.1-win10-x64-cpp11/bin/fluidsynth.exe'
        soundfont = ROOT / 'assets/soundfonts/SoundFont.sf2'
        wav = output / 'shared-synth.wav'
        try:
            result = subprocess.run([str(executable), '-ni', '-F', str(wav), '-r', '44100',
                                     '-g', '0.5', str(soundfont), str(midi)],
                                    capture_output=True, text=True, timeout=45)
            if result.returncode != 0 or not wav.is_file():
                raise RuntimeError(f'FluidSynth return code {result.returncode}: {result.stderr[-500:]}')
            info = probe(wav)
            reports.append({'installation': str(folder.relative_to(ROOT)) or '.', 'status': 'pass',
                            'duration': info['format']['duration'], 'bytes': wav.stat().st_size})
        except (OSError, RuntimeError, subprocess.TimeoutExpired, subprocess.CalledProcessError) as error:
            reports.append({'installation': str(folder.relative_to(ROOT)) or '.', 'status': 'fail', 'error': str(error)})
    report_path = ROOT / 'docs/synth-smoke.json'
    report_path.write_text(json.dumps(reports, indent=2), encoding='utf-8')
    print(json.dumps(reports, indent=2))
    return any(report['status'] == 'fail' for report in reports)


if __name__ == '__main__':
    sys.exit(main())
