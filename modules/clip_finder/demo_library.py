"""Local end-to-end demonstration: import, review ranges, export, and render."""
import json
from pathlib import Path
import subprocess
import sys
import uuid

from clip_library import ClipLibrary, command, checksum


def main():
    folder = Path(__file__).resolve().parent / 'output/library-demo' / uuid.uuid4().hex[:8]
    folder.mkdir(parents=True)
    source = folder / 'original.mp4'
    command(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=red:s=320x180:r=24:d=2',
        '-f', 'lavfi', '-i', 'color=blue:s=320x180:r=24:d=2',
        '-filter_complex', '[0:v][1:v]concat=n=2:v=1:a=0[v]', '-map', '[v]',
        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', source])
    music = folder / 'music.wav'
    command(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=2', music])
    library = ClipLibrary(folder / 'library')
    asset = library.import_file(source, source_url='local-generated-fixture', title='Red then blue test clip', license_info='synthetic test media')
    assert library.import_file(source)['reused']
    first = library.add_highlight(asset['id'], 0.5, 1.5, ['opening'])
    second = library.add_highlight(asset['id'], 2.5, 3.5, ['ending'])
    timeline = folder / 'timeline.json'
    library.export_timeline([first['reference'], second['reference']], timeline, 2)
    # JSON is a YAML-compatible timeline, keeping the library dependency-light.
    module = Path(__file__).resolve().parents[1] / 'music_video_generator'
    config = folder / 'video.json'
    settings = {'video': {'width': 320, 'height': 180, 'fps': 24, 'preset': 'fast', 'crf': 20},
        'image': {'default_duration': 4, 'zoom_factor': 1.05, 'motion': 'still'},
        'beat_detection': {'enabled': False, 'hop_length': 512, 'backtrack': False, 'trim': False},
        'paths': {'input_images': str(folder), 'input_audio': str(folder), 'output': str(folder / 'render')},
        'effects': {'transitions': {'enabled': False}}}
    config.write_text(json.dumps(settings), encoding='utf-8')
    output = folder / 'render/music_video.mp4'
    command([sys.executable, module / 'main.py', '--audio', music, '--timeline', timeline, '--config', config, '--output', output])
    command(['ffmpeg', '-v', 'error', '-xerror', '-i', output, '-f', 'null', '-'])
    plan = json.loads((output.parent / 'scene-plan.json').read_text())
    assert len(plan['scenes']) == 2 and len(plan['provenance']) == 2
    assert checksum(source) == asset['sha256']
    report = {'status': 'passed', 'checks': ['original preserved', 'content deduplicated', 'explicit highlight ranges',
        'timeline exported', 'provenance in renderer plan', 'full output decode'], 'video': str(output),
        'timeline': str(timeline), 'asset_id': asset['id']}
    (folder / 'results.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
