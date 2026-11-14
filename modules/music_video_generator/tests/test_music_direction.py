import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from src.music_direction import directed_scenes, direct_scene, combined_profile
from src.video_generator import Scene, crossfade_plan
from src.image_processor import ImageProcessor


def profile(energy=0.6):
    return {'beats': [n * 0.5 for n in range(80)], 'onsets': [],
            'energy_times': [0, 40], 'energy': [energy, energy]}


class MusicDirectionTests(unittest.TestCase):
    def test_cuts_follow_detected_beats_and_keep_the_whole_track(self):
        data = profile()
        scenes = directed_scenes(['one.png', 'two.png'], [{'start_time': 0, 'duration': 36}], data)
        self.assertEqual(scenes[0].start_time, 0)
        self.assertAlmostEqual(sum(s.duration for s in scenes), 36)
        self.assertTrue(all(s.start_time in data['beats'] for s in scenes[1:]))
        self.assertTrue(all(6 <= s.duration <= 12 for s in scenes))

    def test_energetic_style_changes_shots_more_often(self):
        info = [{'start_time': 0, 'duration': 36}]
        slow = directed_scenes(['a.png'], info, profile(), 'cinematic')
        fast = directed_scenes(['a.png'], info, profile(), 'energetic')
        self.assertGreater(len(fast), len(slow))

    def test_energy_controls_motion_strength(self):
        calm = Scene(Path('a.png'), 0, 8, Path('a.mp4'))
        strong = Scene(Path('a.png'), 0, 8, Path('b.mp4'))
        direct_scene(calm, profile(0.2))
        direct_scene(strong, profile(0.9))
        self.assertGreater(strong.zoom_factor, calm.zoom_factor)
        self.assertGreater(strong.beat_accents[0]['strength'], calm.beat_accents[0]['strength'])
        self.assertLessEqual(strong.pulse_strength, 0.002)

    def test_no_detected_beats_means_no_invented_accents(self):
        scene = Scene(Path('a.png'), 0, 8, Path('a.mp4'))
        direct_scene(scene, {'beats': [], 'energy_times': [], 'energy': []})
        self.assertEqual(scene.beat_accents, [])

    def test_authored_still_and_fit_are_not_animated(self):
        scene = Scene(Path('a.png'), 0, 8, Path('a.mp4'), motion='still', framing='fit')
        direct_scene(scene, profile(), respect_motion=True)
        self.assertEqual(scene.motion, 'still')
        self.assertEqual(scene.pulse_strength, 0)

    def test_playlist_boundary_is_retained(self):
        infos = [{'start_time': 0, 'duration': 17}, {'start_time': 17, 'duration': 19}]
        scenes = directed_scenes(['a.png', 'b.png'], infos, profile())
        self.assertIn(17, [s.start_time for s in scenes])
        self.assertAlmostEqual(sum(s.duration for s in scenes), 36)

    def test_pulse_expression_is_bounded_and_finite(self):
        text = ImageProcessor(320, 180).generate_zoompan_filter(200, motion='zoom_in',
            beat_accents=[{'time': 190, 'strength': 1}], pulse_strength=0.0015)
        self.assertIn('exp(-60*pow(', text)
        self.assertIn('min(2,', text)

    def test_chunked_boundaries_keep_original_transition_lengths(self):
        plan = crossfade_plan([10, 10, 10], 30, [0.1, 0.2])
        self.assertEqual([b['frames'] for b in plan['boundaries']], [3, 6])
        self.assertEqual(plan['output_frames'], 30)

    def test_montage_varies_shot_size_and_shortens_static_holds(self):
        scenes = directed_scenes(['a.png', 'b.png', 'c.png'],
            [{'start_time': 0, 'duration': 30}], profile(), montage=True)
        self.assertGreaterEqual(len(scenes), 5)
        self.assertLessEqual(max(s.duration for s in scenes), 6.5)
        self.assertEqual([s.crop_factor for s in scenes[:3]], [1.0, 1.22, 1.35])
        self.assertEqual(scenes[1].motion, 'still')

    def test_zero_duration_boundary_means_cut(self):
        plan = crossfade_plan([30, 30, 30], 30, [0, 0.25])
        self.assertEqual(plan['boundaries'][0]['frames'], 0)
        self.assertEqual(plan['output_frames'], 90)


if __name__ == '__main__':
    unittest.main()
