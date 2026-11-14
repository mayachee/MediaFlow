import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml
from PIL import Image
from modules.music_video_generator.src.timeline import load_timeline, build_scenes, crop_timeline
from modules.music_video_generator.src.video_generator import VideoGenerator, Scene, crossfade_plan
from modules.music_video_generator.src.image_processor import ImageProcessor


class TimelineTests(unittest.TestCase):
    def test_reviewed_footage_cannot_silently_fill_a_longer_song(self):
        with self.assertRaisesRegex(ValueError, 'does not match this audio'):
            build_scenes({'planned_seconds': 2, 'scenes': [{'source': 'a.mp4', 'duration': 'auto'}]},
                         10, [{'duration': 10}], 24)

    def test_preview_preserves_provenance_and_updates_coverage(self):
        document = {'planned_seconds': 8, 'provenance': [{'source_url': 'example'}],
                    'scenes': [{'source': 'a.mp4', 'duration': 'auto'}]}
        cropped = crop_timeline(document, [{'duration': 8}], 2, 3, 24)
        self.assertEqual(cropped['planned_seconds'], 3)
        self.assertEqual(cropped['provenance'], document['provenance'])

    def test_relative_sources_and_final_auto(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            Image.new('RGB', (20, 20), 'red').save(root / 'cover.png')
            document = {'scenes': [{'source': 'cover.png', 'duration': 2, 'motion': 'pan_left'},
                                   {'source': 'cover.png', 'duration': 'auto', 'framing': 'fit'}]}
            path = root / 'timeline.yaml'
            path.write_text(yaml.safe_dump(document))
            scenes = build_scenes(load_timeline(path), 6, [{'duration': 6}], 24)
            self.assertEqual(scenes[0].source_path, (root / 'cover.png').resolve())
            self.assertEqual([s.duration for s in scenes], [2, 4])

    def test_timeline_cannot_silently_drop_audio(self):
        with self.assertRaisesRegex(ValueError, 'Timeline totals'):
            build_scenes({'scenes': [{'source': 'a.png', 'duration': 2}]}, 6, [], 24)

    def test_tracks_follow_selected_audio_order(self):
        document = {'scenes': [{'source': 'a.png', 'track': 1}, {'source': 'b.png', 'track': 2}]}
        scenes = build_scenes(document, 7, [{'duration': 3}, {'duration': 4}], 24)
        self.assertEqual([s.start_time for s in scenes], [0, 3])
        document['scenes'].reverse()
        with self.assertRaisesRegex(ValueError, 'in order'):
            build_scenes(document, 7, [{'duration': 3}, {'duration': 4}], 24)

    def test_preview_crops_visuals_to_the_same_audio_range(self):
        document = {'scenes': [{'source': 'a.png', 'duration': 2}, {'source': 'b.png', 'duration': 2},
                               {'source': 'c.png', 'duration': 'auto'}]}
        cropped = crop_timeline(document, [{'duration': 8}], 1, 4, 24)
        self.assertEqual([s['duration'] for s in cropped['scenes']], [1, 2, 1])

    def test_bad_mapping_does_not_fall_back_to_random_artwork(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / 'timeline.yaml'
            path.write_text('scenes:\n  - source: missing.png\n    duration: 2\n')
            with self.assertRaisesRegex(ValueError, 'not found'):
                load_timeline(path)


class CrossfadeTests(unittest.TestCase):
    def test_handles_preserve_the_full_timeline(self):
        plan = crossfade_plan([48, 72, 48], 24, 0.5)
        handles = sum(b['incoming_frames'] + b['outgoing_frames'] for b in plan['boundaries'])
        overlap = sum(b['frames'] for b in plan['boundaries'])
        self.assertEqual(sum(plan['scene_frames']) + handles - overlap, 168)
        self.assertEqual(plan['output_frames'], 168)
        self.assertEqual(plan['boundaries'][0]['offset_frames'], 42)

    def test_odd_frame_overlaps_are_still_exact(self):
        plan = crossfade_plan([60, 60], 30, 0.5)
        boundary = plan['boundaries'][0]
        self.assertEqual(boundary['frames'], 15)
        self.assertEqual(boundary['incoming_frames'] + boundary['outgoing_frames'], 15)
        self.assertEqual(plan['output_frames'], 120)

    def test_transition_is_clamped_to_short_scenes(self):
        plan = crossfade_plan([3, 4, 3], 24, 5)
        self.assertEqual([b['frames'] for b in plan['boundaries']], [3, 3])
        self.assertEqual(plan['output_frames'], 10)


class MotionAndFramingTests(unittest.TestCase):
    def test_fit_retains_the_whole_portrait(self):
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / 'portrait.png'
            image = Image.new('RGB', (100, 200), 'green')
            image.paste('red', (0, 0, 100, 20))
            image.paste('blue', (0, 180, 100, 200))
            image.save(source)
            prepared = ImageProcessor(320, 180).load_and_prepare(source, fit_to_screen=False, enhance=False)
            self.assertEqual(prepared.getpixel((0, 90)), (0, 0, 0))
            self.assertGreater(prepared.getpixel((160, 5))[0], 200)
            self.assertGreater(prepared.getpixel((160, 175))[2], 200)

    def test_alternating_motion_is_deterministic_and_fit_is_still(self):
        config = {'video': {'width': 320, 'height': 180, 'fps': 24}, 'image': {'motion': 'alternate'}}
        with patch.object(VideoGenerator, '_find_ffmpeg', return_value='ffmpeg'):
            generator = VideoGenerator(config)
        scenes = [Scene(Path('a.png'), index * 2, 2, Path(f'{index}.mp4')) for index in range(3)]
        scenes[-1].framing = 'fit'
        for scene in scenes:
            generator.resolve_scene(scene)
        self.assertEqual([s.motion for s in scenes], ['zoom_in', 'pan_right', 'still'])

    def test_pan_filter_moves_the_camera(self):
        result = ImageProcessor(320, 180).generate_zoompan_filter(2, fps=24, motion='pan_right')
        self.assertIn("x='(iw-iw/zoom)*min(on/47,1)'", result)


if __name__ == '__main__':
    unittest.main()
