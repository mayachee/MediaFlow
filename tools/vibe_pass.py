"""Find a similar soundtrack in your licensed music folder and optionally replace video audio."""

import argparse
from dataclasses import dataclass
import math
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipelines.audio_production import checked, finite
from pipelines.media_quality import probe


SAMPLE_RATE = 22050
EXCERPT_SECONDS = 30
FRAME_LENGTH = 2048
HOP_LENGTH = 256
AUDIO_SUFFIXES = {'.aac', '.aif', '.aiff', '.alac', '.flac', '.m4a', '.mp3', '.ogg',
                  '.opus', '.wav', '.wma'}


@dataclass(frozen=True)
class SoundProfile:
    bpm: float
    centroid_hz: float
    dynamics_db: float


def estimate_tempo(magnitudes):
    import numpy as np

    # Positive spectral changes form an onset envelope. Repeated peaks suggest a beat.
    log_magnitudes = np.log1p(magnitudes / (0.01 * magnitudes.max()))
    envelope = np.maximum(0, np.diff(log_magnitudes, axis=0)).mean(axis=1)
    envelope -= envelope.mean()
    frames_per_minute = 60 * SAMPLE_RATE / HOP_LENGTH
    minimum = round(frames_per_minute / 220)
    maximum = min(round(frames_per_minute / 55), len(envelope) // 2)
    if minimum > maximum or np.linalg.norm(envelope) < 1e-4:
        return 0.0

    correlation = np.correlate(envelope, envelope, mode='full')[len(envelope) - 1:]
    lags = np.arange(minimum, maximum + 1)
    strengths = correlation[lags] / correlation[0]
    peaks = (correlation[lags] >= correlation[lags - 1]) & (correlation[lags] >= correlation[lags + 1])
    best = strengths[peaks].max(initial=0)
    if best < 0.25:
        return 0.0
    lag = lags[peaks & (strengths >= 0.95 * best)][0]
    return frames_per_minute / lag


def profile(path):
    import numpy as np

    result = subprocess.run(
        ['ffmpeg', '-nostdin', '-v', 'error', '-i', str(path), '-map', '0:a:0',
         '-t', str(EXCERPT_SECONDS), '-ac', '1', '-ar', str(SAMPLE_RATE), '-f', 'f32le', '-'],
        capture_output=True,
    )
    if result.returncode:
        raise ValueError(result.stderr.decode(errors='replace').strip())
    samples = np.frombuffer(result.stdout, dtype='<f4')
    if len(samples) < SAMPLE_RATE or not np.isfinite(samples).all():
        raise ValueError('Analysis needs at least one second of valid audio')

    frames = np.lib.stride_tricks.sliding_window_view(samples, FRAME_LENGTH)[::HOP_LENGTH]
    rms = np.sqrt(np.mean(np.square(frames, dtype=np.float64), axis=1))
    # Leave out silence so a long intro or tail does not dominate the score.
    active = rms > max(1e-6, float(rms.max()) * 0.01)
    if not active.any():
        raise ValueError('The first 30 seconds are silent')
    magnitudes = np.abs(np.fft.rfft(frames * np.hamming(FRAME_LENGTH), axis=1))
    active_magnitudes = magnitudes[active]
    frequencies = np.fft.rfftfreq(FRAME_LENGTH, d=1 / SAMPLE_RATE)
    centroids = (active_magnitudes * frequencies).sum(axis=1) / active_magnitudes.sum(axis=1)
    loudness = 20 * np.log10(rms[active])
    dynamics = float(np.percentile(loudness, 90) - np.percentile(loudness, 10))
    return SoundProfile(estimate_tempo(magnitudes), max(1.0, float(np.median(centroids))), dynamics)


def distance(reference, candidate):
    if reference.bpm and candidate.bpm:
        tempo_distance = min(1.0, abs(math.log2(candidate.bpm / reference.bpm)))
    else:
        tempo_distance = 0.5 if reference.bpm or candidate.bpm else 0.0
    tone_distance = min(1.0, abs(math.log2(candidate.centroid_hz / reference.centroid_hz)) / 2)
    dynamics_distance = min(1.0, abs(candidate.dynamics_db - reference.dynamics_db) / 20)
    return 0.5 * tempo_distance + 0.3 * tone_distance + 0.2 * dynamics_distance


def rank_tracks(reference_path, library):
    reference = profile(reference_path)
    candidates = [library] if library.is_file() else sorted(
        path for path in library.rglob('*') if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES
    )
    matches = []
    for path in candidates:
        if path.samefile(reference_path):
            continue
        try:
            candidate = profile(path)
        except ValueError as error:
            print(f'Skipped {path.name} ({error})', file=sys.stderr)
            continue
        matches.append((distance(reference, candidate), path, candidate))
    if not matches:
        raise ValueError('Supply a decodable replacement track in --library')
    matches.sort(key=lambda match: match[0])
    return reference, matches


def replace_soundtrack(video, soundtrack, output):
    info = probe(video)
    stream = next((stream for stream in info['streams'] if stream['codec_type'] == 'video'
                   and not stream.get('disposition', {}).get('attached_pic')), None)
    if stream is None:
        raise ValueError('Input needs a video stream')
    seconds = finite(stream.get('duration')) or finite(info['format'].get('duration'))
    if seconds is None or seconds <= 0:
        raise ValueError('Could not determine video duration')
    fade = min(0.4, seconds / 2)
    filters = f'atrim=duration={seconds},asetpts=N/SR/TB,afade=t=out:st={seconds - fade}:d={fade}'
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='vibe-pass-', dir=output.parent) as temp:
        staged = Path(temp) / 'export.mp4'
        checked(['ffmpeg', '-nostdin', '-v', 'error', '-i', video, '-stream_loop', '-1', '-i', soundtrack,
                 '-map', f'0:{stream["index"]}', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac',
                 '-ac', '2', '-ar', '48000', '-b:a', '192k', '-af', filters, '-movflags', '+faststart', staged])
        # Publish only a complete export and fail if another run already wrote this path.
        if os.name == 'nt':
            staged.rename(output)
        else:
            os.link(staged, output)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--video', type=Path, required=True, help='Local video to prepare for YouTube')
    parser.add_argument('--library', type=Path, required=True,
                        help='Folder of music cleared for your YouTube use, or a single cleared track')
    parser.add_argument('--reference', type=Path, help='Optional audio reference instead of the video soundtrack')
    parser.add_argument('--output', type=Path, help='New MP4 with replacement audio. Omit to rank tracks only.')
    args = parser.parse_args()
    video = args.video.resolve()
    reference_path = (args.reference or video).resolve()
    library = args.library.resolve()
    output = args.output.resolve() if args.output else None
    try:
        if not video.is_file() or not reference_path.is_file() or not library.exists():
            raise ValueError('Check the paths to the video, reference, and library')
        if output and (output.suffix.lower() != '.mp4' or output.exists()):
            raise ValueError('--output must be a new .mp4 file')
        if not all(shutil.which(command) for command in ('ffmpeg', 'ffprobe')):
            raise ValueError('Put FFmpeg and ffprobe on PATH')
        reference, matches = rank_tracks(reference_path, library)
        print(f'Reference tempo {reference.bpm:.0f} BPM' if reference.bpm else 'Reference tempo undetected')
        print('Closest tracks (tempo, tone, and dynamics over the first 30 seconds)')
        for index, (_, path, candidate) in enumerate(matches[:5], 1):
            tempo = f'{candidate.bpm:.0f} BPM' if candidate.bpm else 'tempo undetected'
            print(f'{index}. {path} ({tempo})')
        if output:
            replace_soundtrack(video, matches[0][1], output)
            print(f'Exported {output}. Review the upload in YouTube Studio Checks.')
    except ModuleNotFoundError as error:
        parser.exit(1, f'Install the workspace Python dependencies in requirements/workflow.txt ({error}).\n')
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, f'Vibe Pass failed: {error}\n')


if __name__ == '__main__':
    main()
