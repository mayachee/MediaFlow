"""Decode only the requested playlist section for local preview generation."""
import json
import math
from pathlib import Path
import shutil
import subprocess


def prepare_preview(files, start, seconds, output):
    if not math.isfinite(start) or not math.isfinite(seconds) or start < 0 or seconds <= 0:
        raise ValueError('Preview start must be nonnegative and seconds must be positive and finite')
    ffmpeg = shutil.which('ffmpeg')
    ffprobe = shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        raise ValueError('ffmpeg and ffprobe must be on PATH for previews')
    cursor, paths, selections = 0.0, [], []
    output.mkdir(parents=True, exist_ok=True)
    for index, source in enumerate(files):
        result = subprocess.run([ffprobe, '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(source)],
                                capture_output=True, text=True, encoding='utf-8', errors='replace', check=True)
        length = float(json.loads(result.stdout)['format']['duration'])
        local_start = max(0, start - cursor)
        overlap = min(cursor + length, start + seconds) - max(cursor, start)
        if overlap > 0:
            destination = output / f'{index:04d}_{source.stem}.wav'
            subprocess.run([ffmpeg, '-nostdin', '-v', 'error', '-y', '-ss', str(local_start), '-i', str(source),
                            '-t', str(overlap), '-vn', '-c:a', 'pcm_s24le', str(destination)],
                           capture_output=True, text=True, encoding='utf-8', errors='replace', check=True)
            paths.append(destination)
            selections.append({'source': str(source.resolve()), 'source_start': local_start, 'seconds': overlap})
        cursor += length
        if cursor >= start + seconds:
            break
    if not paths:
        raise ValueError('Preview starts after the end of the selected audio')
    return paths, selections
