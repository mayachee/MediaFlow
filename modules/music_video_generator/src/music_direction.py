"""Restrained, repeatable visual decisions from measured musical cues."""
import math
from pathlib import Path
import numpy as np
from .video_generator import Scene, is_video

STYLES = {
    'cinematic': {'minimum': 6.0, 'target': 8.0, 'maximum': 12.0, 'zoom_low': 1.025, 'zoom_high': 1.075, 'pulse': 0.0015, 'transition': 0.9},
    'balanced': {'minimum': 4.0, 'target': 6.0, 'maximum': 9.0, 'zoom_low': 1.035, 'zoom_high': 1.10, 'pulse': 0.003, 'transition': 0.6},
    'energetic': {'minimum': 2.0, 'target': 3.5, 'maximum': 6.0, 'zoom_low': 1.045, 'zoom_high': 1.12, 'pulse': 0.006, 'transition': 0.3},
}


def style_settings(name):
    if name not in STYLES:
        raise ValueError(f'Unknown direction style: {name}')
    return STYLES[name]


def energy_at(profile, time):
    if not profile or not profile.get('energy_times'):
        return 0.5
    return float(np.interp(time, profile['energy_times'], profile['energy']))


def combined_profile(file_infos, profiles):
    result = {'beats': [], 'onsets': [], 'energy_times': [], 'energy': [], 'tracks': []}
    for info, profile in zip(file_infos, profiles):
        if not profile:
            result['energy_times'].extend([info['start_time'], info['start_time'] + info['duration'] - 1e-6])
            result['energy'].extend([0.5, 0.5])
            continue
        offset = info['start_time']
        for key in ('beats', 'onsets', 'energy_times'):
            result[key].extend(float(value + offset) for value in profile[key])
        result['energy'].extend(profile['energy'])
        result['tracks'].append({'source': str(info['path']), 'start': offset,
                                 'duration': info['duration'], 'tempo_bpm': profile['tempo_bpm']})
    return result


def direct_scene(scene, profile, style='cinematic', index=0, beat_accents=True, respect_motion=False):
    settings = style_settings(style)
    times = np.linspace(scene.start_time, scene.start_time + scene.duration, 12)
    energy = float(np.mean([energy_at(profile, float(time)) for time in times]))
    scene.energy = energy
    scene.zoom_factor = settings['zoom_low'] + (settings['zoom_high'] - settings['zoom_low']) * energy
    if not respect_motion or scene.motion is None:
        scene.motion = ('zoom_in', 'pan_right', 'zoom_out', 'pan_left')[index % 4]
        if energy < 0.1:
            scene.motion = 'still'
    cues = [value for value in profile.get('beats', [])
            if scene.start_time <= value < scene.start_time + scene.duration]
    # Keep accents sparse, bounded, and derived from actual detections.
    selected, last = [], -1.0
    for value in cues:
        local = float(value - scene.start_time)
        if local - last >= 0.4:
            selected.append({'time': local, 'strength': 0.4 + 0.6 * energy_at(profile, value)})
            last = local
    scene.beat_accents = selected[:32] if beat_accents else []
    scene.pulse_strength = settings['pulse'] if beat_accents else 0
    if scene.framing == 'fit' or scene.motion == 'still' or is_video(scene.source_path):
        scene.beat_accents, scene.pulse_strength = [], 0
    return scene


def directed_scenes(sources, file_infos, profile, style='cinematic', fps=30, beat_accents=True, montage=False, focal_points=None):
    settings = dict(style_settings(style))
    if montage:
        settings.update(minimum=min(settings['minimum'], 3), target=min(settings['target'], 4.8),
                        maximum=min(settings['maximum'], 6.5))
    if not sources:
        raise ValueError('Music direction requires visual sources')
    scenes = []
    for track_index, info in enumerate(file_infos):
        start, end = info['start_time'], info['start_time'] + info['duration']
        cursor = start
        while cursor < end - 1 / fps:
            energy = energy_at(profile, cursor)
            target = settings['target'] * (1.25 - 0.5 * energy)
            target = float(np.clip(target, settings['minimum'], settings['maximum']))
            if end - cursor <= settings['maximum']:
                cut = end
            else:
                lower = cursor + settings['minimum']
                upper = min(cursor + settings['maximum'], end - settings['minimum'])
                cues = [value for value in profile.get('beats', []) if lower <= value <= upper]
                if not cues:
                    cues = [value for value in profile.get('onsets', []) if lower <= value <= upper]
                cut = min(cues, key=lambda value: abs(value - cursor - target)) if cues else min(cursor + target, upper)
            index = len(scenes)
            scene = Scene(Path(sources[index % len(sources)]), cursor, cut - cursor, Path(f'temp_scene_{index:03d}.mp4'))
            direct_scene(scene, profile, style, index, beat_accents)
            if montage and not is_video(scene.source_path):
                scene.crop_factor = (1.0, 1.22, 1.35)[index % 3]
                scene.focal_point = tuple((focal_points or {}).get(scene.source_path.name, [0.5, 0.5]))
                # Wide shots establish; closer shots hold focus without a pan cycle.
                scene.motion = 'zoom_in' if scene.crop_factor == 1 else 'still'
            scenes.append(scene)
            cursor = cut
    return scenes
