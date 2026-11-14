"""Render viewable examples and verify blends, motion, framing, and mapping."""
import json
import os
from pathlib import Path
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.demo_production import prepare, workflow_job, require
from modules.music_video_generator.src.video_generator import VideoGenerator, Scene
from pipelines.media_quality import validate_video


def frame(path, time, width=320, height=180):
    import numpy as np
    result = subprocess.run(['ffmpeg', '-v', 'error', '-ss', str(time), '-i', str(path),
        '-frames:v', '1', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True)
    return np.frombuffer(result.stdout, dtype=np.uint8).reshape(height, width, 3).astype(float)


def decode(path):
    subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(path), '-f', 'null', '-'],
                   capture_output=True, check=True)


def main():
    import numpy as np
    import yaml
    from PIL import Image, ImageDraw
    output = ROOT / 'runs/video-editing-demo' / uuid.uuid4().hex[:8]
    output.mkdir(parents=True)
    fixtures = prepare(output / 'fixtures')
    config = yaml.safe_load((ROOT / 'modules/music_video_generator/config.yaml').read_text(encoding='utf-8'))
    config['video'].update(width=320, height=180, fps=24)
    config['beat_detection']['enabled'] = False
    config['effects']['transitions'].update(enabled=True, type='crossfade', duration=0.5)
    results = []

    colors = []
    for index, color in enumerate(('red', 'blue', 'lime')):
        source = output / f'color-{index}.png'
        Image.new('RGB', (640, 360), color).save(source)
        colors.append(source)
    generator = VideoGenerator(config)
    scene_files = []
    for index, source in enumerate(colors):
        scene = Scene(source, index * 8 / 3, 8 / 3, output / f'color-scene-{index}.mp4', motion='still')
        generator.generate_scene_video(scene)
        scene_files.append(scene.output_file)
    video = output / 'true-crossfade.mp4'
    generator.concatenate_videos(scene_files, video, fixtures / 'mix.wav')
    quality = validate_video(video, [fixtures / 'mix.wav'], config)
    middle = frame(video, 8 / 3).mean(axis=(0, 1))
    require(middle[0] > 60 and middle[2] > 60 and middle[1] < 30,
            f'Expected a purple red/blue blend at the boundary, got {middle}')
    require(abs(quality['video_duration'] - 8) < 0.1, 'Crossfade shortened the full audio timeline')
    decode(video)
    results.append({'case': 'true_blend_without_shortening', 'video': str(video), 'quality': quality,
                    'boundary_rgb': middle.tolist()})

    wide = Image.new('RGB', (960, 540), '#17365c')
    draw = ImageDraw.Draw(wide)
    for x in range(0, 960, 60):
        draw.rectangle((x, 0, x + 20, 540), fill=(x % 255, 150, 210))
    for y in range(0, 540, 60):
        draw.line((0, y, 959, y), fill='white', width=4)
    wide.save(output / 'wide.png')
    portrait = Image.new('RGB', (160, 320), 'lime')
    portrait.paste('red', (0, 0, 160, 30))
    portrait.paste('blue', (0, 290, 160, 320))
    portrait.save(output / 'portrait.png')
    clip = output / 'clip.mp4'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'testsrc2=size=160x120:rate=24',
                    '-t', '0.5', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(clip)], capture_output=True, check=True)
    timeline = output / 'timeline.yaml'
    timeline.write_text(yaml.safe_dump({'scenes': [
        {'source': 'wide.png', 'duration': 2, 'motion': 'zoom_in', 'framing': 'fill'},
        {'source': 'wide.png', 'duration': 2, 'motion': 'pan_right', 'framing': 'fill'},
        {'source': 'portrait.png', 'duration': 2, 'motion': 'still', 'framing': 'fit'},
        {'source': 'clip.mp4', 'duration': 'auto', 'framing': 'fill'}]}), encoding='utf-8')
    config_path = output / 'config.yaml'
    config_path.write_text(yaml.safe_dump(config), encoding='utf-8')
    job, manifest = workflow_job(fixtures, output, 'mapped', ['--config', config_path, '--timeline', timeline])
    mapped_video = Path(manifest['video'])
    plan = json.loads((mapped_video.parent / 'scene-plan.json').read_text(encoding='utf-8'))
    require([s['motion'] for s in plan['scenes']] == ['zoom_in', 'pan_right', 'still', 'still'], 'Motion mapping changed')
    require(all(Path(s['source']).is_relative_to(job / 'images') for s in plan['scenes']), 'Mapped artwork was not isolated in the job')
    require(np.abs(frame(mapped_video, 0.4) - frame(mapped_video, 1.4)).mean() > 1, 'Zoom did not visibly move')
    require(np.abs(frame(mapped_video, 2.6) - frame(mapped_video, 3.4)).mean() > 1, 'Pan did not visibly move')
    fitted = frame(mapped_video, 5)
    require(fitted[:, :60].mean() < 5, 'Fit mode cropped the portrait instead of letterboxing')
    require(fitted[5, 160, 0] > 150 and fitted[175, 160, 2] > 150, 'Portrait edges were lost')
    require(np.abs(frame(mapped_video, 6.6) - frame(mapped_video, 6.85)).mean() > 2, 'Source clip did not continue playing/looping')
    decode(mapped_video)
    results.append({'case': 'mapped_zoom_pan_fit_and_looped_clip', 'video': str(mapped_video), 'scene_plan': str(mapped_video.parent / 'scene-plan.json')})

    preview_job, preview = workflow_job(fixtures, output, 'preview', ['--config', config_path, '--timeline', timeline,
        '--preset', 'preview', '--preview-start', '1', '--preview-seconds', '4'])
    preview_plan = json.loads((Path(preview['video']).parent / 'scene-plan.json').read_text(encoding='utf-8'))
    require([round(s['duration'], 3) for s in preview_plan['scenes']] == [1, 2, 1], 'Preview did not crop the visual timeline')
    require(abs(preview['quality']['audio_duration'] - 4) < 0.1, 'Preview length is wrong')
    decode(Path(preview['video']))
    results.append({'case': 'preview_crops_audio_and_visual_mapping', 'video': preview['video']})

    hd_config = json.loads(json.dumps(config))
    hd_config['video'].update(width=1920, height=1080, fps=30)
    hd = VideoGenerator(hd_config)
    hd_files = []
    for index, source in enumerate(colors[:2]):
        scene = Scene(source, index * 2, 2, output / f'hd-scene-{index}.mp4', motion='still')
        hd.generate_scene_video(scene)
        hd_files.append(scene.output_file)
    hd_audio = output / 'four-seconds.wav'
    subprocess.run(['ffmpeg', '-v', 'error', '-y', '-i', str(fixtures / 'mix.wav'), '-t', '4', str(hd_audio)], capture_output=True, check=True)
    hd_video = output / '1080p-crossfade.mp4'
    hd.concatenate_videos(hd_files, hd_video, hd_audio)
    hd_quality = validate_video(hd_video, [hd_audio], hd_config)
    decode(hd_video)
    results.append({'case': '1080p_odd_frame_crossfade', 'video': str(hd_video), 'quality': hd_quality})
    record = {'status': 'passed', 'cases': results, 'timeline': str(timeline), 'config': str(config_path)}
    (ROOT / 'docs/video-editing-smoke.json').write_text(json.dumps(record, indent=2), encoding='utf-8')
    lines = ['# Video editing demo', '', 'All four render checks passed.', '']
    for result in results:
        relative = os.path.relpath(result['video'], output).replace('\\', '/')
        lines.append(f'- {result["case"]}: [{Path(result["video"]).name}]({relative})')
    lines += ['', f'Timeline: `{timeline}`', '', 'Red/blue scenes blend to purple; the mapped example demonstrates motion, a complete portrait, and a looping clip.']
    (output / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(f'4 video editing checks passed. Open: {output / "README.md"}')


if __name__ == '__main__':
    main()
