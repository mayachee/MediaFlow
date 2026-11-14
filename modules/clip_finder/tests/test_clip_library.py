import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from clip_library import ClipLibrary, checksum


@unittest.skipUnless(shutil.which('ffmpeg') and shutil.which('ffprobe'), 'FFmpeg required')
class LibraryTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.source = self.folder / 'source.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=red:s=160x90:r=24:d=2',
            '-f', 'lavfi', '-i', 'color=blue:s=160x90:r=24:d=2', '-filter_complex', '[0:v][1:v]concat=n=2:v=1:a=0[v]',
            '-map', '[v]', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(self.source)], capture_output=True, check=True)
        self.library = ClipLibrary(self.folder / 'library')
        self.asset = self.library.import_file(self.source, source_url='https://example.test/video', license_info='synthetic fixture')

    def test_identical_content_and_url_are_reused(self):
        again = self.library.import_file(self.source)
        self.assertTrue(again['reused'])
        self.assertEqual(self.asset['id'], again['id'])
        self.assertEqual(len(list(self.library.assets.iterdir())), 1)
        self.assertEqual(self.library.cached_source('https://example.test/video')['id'], self.asset['id'])

    def test_corrupted_original_is_not_silently_reused(self):
        Path(self.asset['file']).write_bytes(b'corrupt')
        with self.assertRaisesRegex(ValueError, 'changed'):
            self.library.asset(self.asset['id'])

    def test_range_validation_and_real_trim_seek(self):
        with self.assertRaises(ValueError):
            self.library.add_highlight(self.asset['id'], -1, 2)
        with self.assertRaises(ValueError):
            self.library.add_highlight(self.asset['id'], 3, 5)
        highlight = self.library.add_highlight(self.asset['id'], 2.5, 3.5, ['quiet'])
        rendered = self.library.render_highlight(highlight['reference'])
        frame = subprocess.run(['ffmpeg', '-v', 'error', '-i', rendered['file'], '-frames:v', '1',
            '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-'], capture_output=True, check=True).stdout
        count = len(frame) // 3
        self.assertGreater(sum(frame[2::3]) / count, 200, 'Trim must start in the blue part, not the red opening')
        self.assertLess(sum(frame[0::3]) / count, 30)
        self.assertFalse(rendered['media']['has_audio'])
        self.assertTrue(self.library.render_highlight(highlight['reference'])['reused'])
        self.assertEqual(checksum(self.source), self.asset['sha256'])

    def test_timeline_provenance_and_insufficient_coverage(self):
        highlight = self.library.add_highlight(self.asset['id'], 2.5, 3.5)
        with self.assertRaisesRegex(ValueError, 'select more highlights'):
            self.library.export_timeline([highlight['reference']], self.folder / 'too-long.json', 2)
        path = self.folder / 'timeline.json'
        document = self.library.export_timeline([highlight['reference']], path, 1)
        self.assertEqual(document['scenes'][-1]['duration'], 'auto')
        self.assertEqual(document['provenance'][0]['source_range']['start'], 2.5)
        self.assertEqual(document['provenance'][0]['sources'][0]['url'], 'https://example.test/video')
        with self.assertRaises(ValueError):
            self.library.export_timeline([highlight['reference']], path, 1)


if __name__ == '__main__':
    unittest.main()
