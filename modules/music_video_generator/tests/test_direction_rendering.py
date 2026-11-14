import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import wave

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.audio_analyzer import AudioAnalyzer
from src.video_generator import VideoGenerator, Scene
from src.preview import prepare_preview


def probe(path):
    result = subprocess.run(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', str(path)],
                            capture_output=True, text=True, check=True)
    return json.loads(result.stdout)


def synth(path, seconds=8):
    rate = 22050
    time = np.arange(int(seconds * rate)) / rate
    phase = time % 0.5
    levels = np.where(time < seconds / 2, 0.1, 0.45)
    samples = levels * np.exp(-phase * 45) * np.sin(2 * np.pi * 1200 * time)
    samples += 0.01 * np.sin(2 * np.pi * 110 * time)
    with wave.open(str(path), 'wb') as output:
        output.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        output.writeframes((samples * 32767).astype('<i2').tobytes())


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg and ffprobe required')
class DirectionRenderingTests(unittest.TestCase):
    def test_real_beats_energy_and_preview_selection(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            source = folder / 'test.wav'
            synth(source)
            analyzer = AudioAnalyzer()
            duration, beats, _ = analyzer.analyze(str(source))
            profile = analyzer.profile(source)
            self.assertIsNotNone(profile, 'Librosa analysis must succeed; a duration fallback is not music analysis')
            self.assertGreater(len(beats), 6)
            early = [v for t, v in zip(profile['energy_times'], profile['energy']) if 1 <= t <= 3]
            late = [v for t, v in zip(profile['energy_times'], profile['energy']) if 5 <= t <= 7]
            self.assertGreater(np.mean(late), np.mean(early) + 0.2)
            paths, selection = prepare_preview([source], 2, 3, folder / 'selection')
            self.assertAlmostEqual(float(probe(paths[0])['format']['duration']), 3, places=2)
            self.assertEqual(selection[0]['source_start'], 2)

    def test_bounded_crossfades_keep_all_frames_and_audio(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            config = {'video': {'width': 160, 'height': 90, 'fps': 24, 'preset': 'ultrafast'},
                      'image': {'motion': 'still'},
                      'effects': {'transitions': {'enabled': True, 'type': 'crossfade', 'duration': 0.2,
                          'maximum_inputs': 2, 'per_boundary': [0, 0.2, 0, 0.2, 0, 0.2]}}}
            generator = VideoGenerator(config)
            clips = []
            for index, color in enumerate(('red', 'blue', 'lime')):
                source = folder / f'{index}.png'
                Image.new('RGB', (160, 90), color).save(source)
                scene = Scene(source, 0, 0.5, folder / f'{index}.mp4')
                generator.generate_scene_video(scene)
                clips.append(scene.output_file)
            source = folder / 'audio.wav'
            synth(source, seconds=3.5)
            output = folder / 'batched.mp4'
            generator.concatenate_videos([clips[n % 3] for n in range(7)], output, source)
            info = probe(output)
            video = next(stream for stream in info['streams'] if stream['codec_type'] == 'video')
            self.assertEqual(int(video['nb_frames']), 84)
            self.assertAlmostEqual(float(video['duration']), 3.5, places=2)
            self.assertTrue(any(s['codec_type'] == 'audio' for s in info['streams']))
            plan = json.loads((folder / 'transitions.json').read_text())
            self.assertTrue(plan['batched'])
            self.assertEqual(plan['maximum_inputs'], 2)
            self.assertEqual(list(folder.glob('crossfade-*')), [])
            subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-i', str(output), '-f', 'null', '-'], capture_output=True, check=True)

    def test_beat_accents_change_actual_pixels(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            image = Image.new('RGB', (640, 360), 'navy')
            draw = ImageDraw.Draw(image)
            for x in range(0, 640, 16):
                draw.rectangle((x, 0, x + 7, 359), fill='white')
            source = folder / 'grid.png'
            image.save(source)
            config = {'video': {'width': 320, 'height': 180, 'fps': 24},
                      'effects': {'transitions': {'enabled': False}}}
            frames = []
            for pulse in (0, 0.008):
                generator = VideoGenerator(config)
                scene = Scene(source, 0, 2, folder / f'pulse-{pulse}.mp4', motion='zoom_in',
                              zoom_factor=1.04, beat_accents=[{'time': 1, 'strength': 1}], pulse_strength=pulse)
                generator.generate_scene_video(scene)
                result = subprocess.run(['ffmpeg', '-v', 'error', '-ss', '1', '-i', str(scene.output_file),
                    '-frames:v', '1', '-pix_fmt', 'rgb24', '-f', 'rawvideo', '-'], capture_output=True, check=True)
                frames.append(np.frombuffer(result.stdout, dtype=np.uint8).astype(float))
            self.assertGreater(np.abs(frames[0] - frames[1]).mean(), 1)


if __name__ == '__main__':
    unittest.main()
