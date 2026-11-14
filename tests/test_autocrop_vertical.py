import argparse
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from modules.autocrop_vertical import manage
from tools.script_catalog import build_command, curated_tools


class AutoCropTests(unittest.TestCase):
    def test_studio_fields_build_the_expected_command(self):
        tool = next(item for item in curated_tools() if item['id'] == 'autocrop')
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "Dima's landscape video.mp4"
            source.touch()
            command, _ = build_command(tool, {'input': str(source), 'ratio': '4:5',
                                               'quality': 'high', 'plan_only': True})
            self.assertIn(str(source.resolve()), command)
            self.assertEqual(command[command.index('--ratio') + 1], '4:5')
            self.assertIn('--plan-only', command)
            self.assertIn('convert', command)

    def test_source_changes_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder)
            (source / 'main.py').write_text('print("changed")', encoding='utf-8')
            with patch.object(manage, 'SOURCE', source):
                with self.assertRaisesRegex(ValueError, 'differs'):
                    manage.read_source()

    def test_youtube_defaults_and_output_sizes(self):
        tool = next(item for item in curated_tools() if item['id'] == 'autocrop')
        fields = {item['key']: item for item in tool['fields']}
        self.assertEqual(fields['ratio']['default'], '16:9')
        self.assertEqual(fields['resolution']['default'], '1080p')
        self.assertEqual(manage.output_dimensions('16:9', '1080p'), (1920, 1080))
        self.assertEqual(manage.output_dimensions('16:9', '720p'), (1280, 720))
        self.assertEqual(manage.output_dimensions('9:16', '1080p'), (1080, 1920))
        self.assertIsNone(manage.output_dimensions('16:9', 'native'))

    @unittest.skipUnless((manage.SOURCE / 'main.py').is_file(), 'Downloaded upstream source required')
    def test_portrait_to_landscape_crop_stays_inside_source(self):
        namespace = {'__name__': 'autocrop_test'}
        exec(manage.adapt_source(manage.read_source()), namespace)
        for width, height in [(360, 640), (1280, 720), (854, 480)]:
            for ratio in [16 / 9, 9 / 16, 1]:
                namespace['ASPECT_RATIO'] = ratio
                for target in [[0, 0, 40, 60], [width - 40, height - 60, width, height]]:
                    left, top, right, bottom = namespace['calculate_crop_box'](target, width, height)
                    self.assertTrue(0 <= left < right <= width)
                    self.assertTrue(0 <= top < bottom <= height)
                    self.assertLessEqual(abs((right - left) - (bottom - top) * ratio), 2)

    @unittest.skipUnless((manage.SOURCE / 'main.py').is_file(), 'Downloaded upstream source required')
    def test_pinned_source_is_patched_without_modifying_the_original(self):
        path = manage.SOURCE / 'main.py'
        before = path.read_bytes()
        source = manage.read_source()
        adapted = manage.adapt_source(source, Path("C:/model cache/yolov8n.pt"))
        compile(adapted, 'autocrop_runtime.py', 'exec')
        self.assertIn('get_scene_list(start_in_scene=True)', adapted)
        self.assertIn('_stderr_thread.join()', adapted)
        self.assertIn(f'YOLO({str(Path("C:/model cache/yolov8n.pt"))!r})', adapted)
        self.assertEqual(before, path.read_bytes())
        # Model loading must not receive an absolute Windows account path.
        self.assertIn("YOLO('yolov8n.pt')", manage.adapt_source(source))

    def test_unsupported_patch_revision_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'no longer matches'):
            manage.adapt_source('unknown upstream code')

    def test_validation_catches_wrong_shape_missing_audio_and_truncation(self):
        before = dict(width=1280, height=720, duration=10, audio=True)
        valid = dict(width=406, height=720, duration=10.01, audio=True)
        manage.validate_output(before, valid, '9:16')
        for change in [dict(width=1280), dict(audio=False), dict(duration=5)]:
            with self.assertRaises(RuntimeError):
                manage.validate_output(before, {**valid, **change}, '9:16')

    def test_missing_input_fails_before_creating_output(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            args = argparse.Namespace(input=root / 'absent.mp4', output_root=root / 'results')
            with self.assertRaisesRegex(ValueError, 'existing video'):
                manage.convert(args)
            self.assertFalse(args.output_root.exists())


if __name__ == '__main__':
    unittest.main()
