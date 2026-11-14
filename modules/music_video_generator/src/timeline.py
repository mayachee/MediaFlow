"""Explicit visual mapping, relative to the timeline YAML file."""
import math
from pathlib import Path
import yaml

from .video_generator import Scene, VIDEO_EXTENSIONS

MOTIONS = {'still', 'zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'pan_up', 'pan_down', 'alternate'}
VISUAL_EXTENSIONS = VIDEO_EXTENSIONS | {'.jpg', '.jpeg', '.png', '.webp', '.bmp'}


def load_timeline(path):
    path = Path(path).resolve()
    document = yaml.safe_load(path.read_text(encoding='utf-8'))
    if not isinstance(document, dict) or not isinstance(document.get('scenes'), list) or not document['scenes']:
        raise ValueError('Timeline requires a nonempty scenes list')
    rows = []
    for index, item in enumerate(document['scenes']):
        if not isinstance(item, dict) or set(item) - {'source', 'duration', 'track', 'motion', 'framing'}:
            raise ValueError(f'Timeline scene {index + 1}: invalid fields')
        if not isinstance(item.get('source'), str):
            raise ValueError(f'Timeline scene {index + 1}: source is required')
        source = (path.parent / item['source']).resolve()
        if not source.is_file() or source.suffix.lower() not in VISUAL_EXTENSIONS:
            raise ValueError(f'Timeline visual not found or unsupported: {source}')
        if item.get('motion', 'still') not in MOTIONS:
            raise ValueError(f'Timeline scene {index + 1}: unsupported motion')
        if item.get('framing', 'fill') not in {'fill', 'fit'}:
            raise ValueError(f'Timeline scene {index + 1}: framing must be fill or fit')
        if ('duration' in item) == ('track' in item):
            raise ValueError(f'Timeline scene {index + 1}: supply duration or track, not both')
        rows.append({**item, 'source': str(source)})
    result = {'scenes': rows, 'provenance': document.get('provenance', [])}
    if 'planned_seconds' in document:
        result['planned_seconds'] = document['planned_seconds']
    return result


def build_scenes(document, duration, file_infos, fps):
    if 'planned_seconds' in document:
        planned = float(document['planned_seconds'])
        if not math.isfinite(planned) or abs(planned - duration) > 0.15:
            raise ValueError('Reviewed footage timeline length does not match this audio; export a timeline for the selected duration')
    rows = document['scenes']
    tracks = [item.get('track') for item in rows]
    if any(track is not None for track in tracks):
        if any(isinstance(track, bool) or not isinstance(track, int) for track in tracks):
            raise ValueError('Track mapping needs one integer track number per scene')
        if tracks != list(range(1, len(file_infos) + 1)):
            raise ValueError('Track mapping must cover every selected audio file once, in order starting at 1')
    scenes, offset = [], 0.0
    for index, item in enumerate(rows):
        value = item.get('duration')
        if 'track' in item:
            length = file_infos[item['track'] - 1]['duration']
        elif value == 'auto':
            if index != len(rows) - 1:
                raise ValueError('Only the final timeline scene may use duration: auto')
            length = duration - offset
        else:
            if isinstance(value, bool):
                raise ValueError('Scene duration must be numeric')
            try:
                length = float(value)
            except (TypeError, ValueError) as error:
                raise ValueError('Scene duration must be a positive number or final auto') from error
        if not math.isfinite(length) or length < 1 / fps:
            raise ValueError('Every timeline scene must last at least one video frame')
        scenes.append(Scene(Path(item['source']), offset, length, Path(f'temp_scene_{index:03d}.mp4'),
                            motion=item.get('motion'), framing=item.get('framing')))
        offset += length
    if abs(offset - duration) > max(0.02, 1 / fps):
        raise ValueError(f'Timeline totals {offset:.3f}s but selected audio lasts {duration:.3f}s; use final duration: auto')
    scenes[-1].duration += duration - offset
    return scenes


def crop_timeline(document, file_infos, start, length, fps):
    total = sum(info['duration'] for info in file_infos)
    scenes = build_scenes(document, total, file_infos, fps)
    end = min(total, start + length)
    rows = []
    for scene in scenes:
        overlap = min(end, scene.start_time + scene.duration) - max(start, scene.start_time)
        if overlap > 0:
            if overlap < 1 / fps:
                raise ValueError('Preview edge cuts a scene below one frame; adjust the preview range')
            row = {'source': str(scene.source_path), 'duration': overlap}
            if scene.motion is not None:
                row['motion'] = scene.motion
            if scene.framing is not None:
                row['framing'] = scene.framing
            rows.append(row)
    if not rows:
        raise ValueError('Preview does not intersect the visual timeline')
    result = {'scenes': rows, 'provenance': document.get('provenance', [])}
    if 'planned_seconds' in document:
        result['planned_seconds'] = end - start
    return result
