"""Technical checks for a rendered video before it is marked ready to upload."""
import json
import math
import subprocess
from pathlib import Path


def probe(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                             '-of', 'json', str(path)], capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def duration(path):
    value = float(probe(path)['format']['duration'])
    if not math.isfinite(value) or value <= 0:
        raise ValueError(f'Invalid duration: {path}')
    return value


def validate_video(path, audio_paths, config):
    info = probe(path)
    video = next((s for s in info['streams'] if s['codec_type'] == 'video'), None)
    audio = next((s for s in info['streams'] if s['codec_type'] == 'audio'), None)
    if not video or not audio:
        raise ValueError('Rendered video must contain both video and audio streams')
    expected = sum(duration(source) for source in audio_paths)
    fps = config['video']['fps']
    tolerance = 0.25 + len(audio_paths) / fps
    actual_video = float(video.get('duration', info['format']['duration']))
    actual_audio = float(audio.get('duration', info['format']['duration']))
    if abs(actual_video - expected) > tolerance or abs(actual_audio - expected) > tolerance:
        raise ValueError(f'Rendered duration mismatch: expected {expected:.3f}s, '
                         f'video {actual_video:.3f}s, audio {actual_audio:.3f}s')
    if (video['width'], video['height']) != (config['video']['width'], config['video']['height']):
        raise ValueError('Rendered dimensions do not match configuration')
    numerator, denominator = video['avg_frame_rate'].split('/')
    actual_fps = float(numerator) / float(denominator)
    if abs(actual_fps - fps) > 0.01:
        raise ValueError('Rendered frame rate does not match configuration')
    return {'status': 'passed', 'expected_duration': expected, 'video_duration': actual_video,
            'audio_duration': actual_audio, 'width': video['width'], 'height': video['height'],
            'fps': actual_fps, 'video_codec': video['codec_name'], 'audio_codec': audio['codec_name'],
            'bytes': Path(path).stat().st_size}
