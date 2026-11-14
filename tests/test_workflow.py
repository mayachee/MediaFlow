import argparse
import json
import subprocess
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

import workflow


class WorkflowTests(unittest.TestCase):
    def test_handoffs_and_failed_render_blocks_upload(self):
        for failure in (None, 'render', 'quality'):
            with self.subTest(failure=failure), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary)
                images = root / 'visuals'
                images.mkdir()
                (images / 'cover.jpg').write_bytes(b'image')
                audio = root / 'song.wav'
                audio.write_bytes(b'original audio')
                generator = root / 'modules/music_video_generator'
                generator.mkdir(parents=True)
                (generator / 'config.yaml').write_text('test configuration')
                args = argparse.Namespace(images=images, audio=audio, url=None,
                    max_songs=1, metadata=None, effect='reverse', instrumental=False,
                    privacy='private', upload=True)
                commands = []
                configs = []

                def fake_run(command, **kwargs):
                    commands.append(command)
                    if command[0] == 'ffmpeg':
                        Path(command[-1]).write_bytes(b'processed audio')
                    elif str(command[1]).endswith('main.py'):
                        if failure == 'render':
                            raise subprocess.CalledProcessError(1, command)
                        output = Path(command[command.index('--output') + 1])
                        output.parent.mkdir()
                        output.write_bytes(b'video')

                yaml = types.SimpleNamespace(
                    safe_load=lambda _: {'paths': {}},
                    safe_dump=lambda config: configs.append(config) or json.dumps(config))
                with patch.object(workflow, 'ROOT', root), patch.object(workflow.shutil, 'which', return_value='ffmpeg'), patch.object(workflow, 'run', side_effect=fake_run), patch.object(workflow, 'validate_video', return_value={'status': 'passed'}, side_effect=ValueError('bad quality') if failure == 'quality' else None), patch.dict('sys.modules', yaml=yaml):
                    if failure:
                        with self.assertRaises((subprocess.CalledProcessError, ValueError)):
                            workflow.execute(args)
                    else:
                        workflow.execute(args)
                manifest = json.loads(next((root / 'runs').glob('*/manifest.json')).read_text())
                uploads = [c for c in commands if any('youtube_uploader.py' in str(p) for p in c)]
                self.assertEqual(len(uploads), 0 if failure else 1)
                self.assertEqual(manifest['status'], 'failed' if failure else 'completed')
                self.assertEqual(audio.read_bytes(), b'original audio')
                processed = Path(configs[0]['paths']['input_audio'])
                self.assertEqual(len(list(processed.glob('*.wav'))), 1)
                self.assertIn('areverse', commands[0])
                if uploads:
                    self.assertEqual(str(uploads[0][uploads[0].index('--video') + 1]), manifest['video'])


if __name__ == '__main__':
    unittest.main()
