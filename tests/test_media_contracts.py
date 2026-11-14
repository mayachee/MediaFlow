"""Offline regression checks for timing, upload recovery, and failed stages."""
import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'modules/music_video_generator'))
sys.path.insert(0, str(ROOT / 'modules/automatic_YouTube_upload'))
from pipelines import media_quality
from pipelines import run_all
import youtube_uploader
from modules.music_video_generator.main import create_scenes
from src.audio_analyzer import AudioAnalyzer
from src.utils import get_input_files


class TimingTests(unittest.TestCase):
    def test_late_first_beat_does_not_remove_opening_or_extend_short_scenes(self):
        scenes = create_scenes([Path('a.png'), Path('b.png')], 1.0, beat_times=[0.2, 0.8])
        self.assertEqual(scenes[0].start_time, 0)
        self.assertAlmostEqual(sum(s.duration for s in scenes), 1.0)
        self.assertAlmostEqual(scenes[0].duration, scenes[1].start_time)

    def test_unknown_duration_fails_instead_of_inventing_three_minutes(self):
        analyzer = AudioAnalyzer(detect_beats=False)
        with patch.object(analyzer, '_probe_duration', return_value=None):
            with self.assertRaises(RuntimeError):
                analyzer.analyze('broken.wav')

    def test_uppercase_extensions_are_selected(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / 'song.WAV').touch()
            (folder / 'ignore.txt').touch()
            self.assertEqual([p.name for p in get_input_files(folder, ['.wav'])], ['song.WAV'])


class QualityTests(unittest.TestCase):
    def setUp(self):
        self.config = {'video': {'width': 320, 'height': 180, 'fps': 24}}
        self.info = {'format': {'duration': '2.4'}, 'streams': [
            {'codec_type': 'video', 'codec_name': 'h264', 'duration': '2.4',
             'width': 320, 'height': 180, 'avg_frame_rate': '24/1'},
            {'codec_type': 'audio', 'codec_name': 'aac', 'duration': '2.4'}]}

    def test_audio_stream_required(self):
        self.info['streams'].pop()
        with patch.object(media_quality, 'probe', return_value=self.info):
            with self.assertRaisesRegex(ValueError, 'both video and audio'):
                media_quality.validate_video(Path('video.mp4'), [], self.config)

    def test_truncated_video_rejected(self):
        self.info['streams'][0]['duration'] = '1.0'
        with patch.object(media_quality, 'probe', return_value=self.info), patch.object(media_quality, 'duration', return_value=2.4):
            with self.assertRaisesRegex(ValueError, 'duration mismatch'):
                media_quality.validate_video(Path('video.mp4'), [Path('audio.wav')], self.config)

    def test_wrong_dimensions_rejected(self):
        self.info['streams'][0]['width'] = 640
        with patch.object(media_quality, 'probe', return_value=self.info), patch.object(media_quality, 'duration', return_value=2.4):
            with self.assertRaisesRegex(ValueError, 'dimensions'):
                media_quality.validate_video(Path('video.mp4'), [Path('audio.wav')], self.config)


class RunnerTests(unittest.TestCase):
    def test_failed_search_stops_download_and_upload(self):
        with patch.object(sys, 'argv', ['run_all.py']), patch.object(run_all, 'search_songs', return_value=False), patch.object(run_all, 'download_audio') as download, patch.object(run_all, 'upload_video') as upload:
            self.assertEqual(run_all.main(), 1)
            download.assert_not_called()
            upload.assert_not_called()

    def test_metadata_reads_env_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            (folder / '.env').write_text('OPENAI_API_KEY=test-key\n')
            with patch.object(run_all, 'YOUTUBE_DIR', folder), patch.dict(run_all.os.environ, {}, clear=True), patch.object(run_all, 'run', return_value=True) as command:
                self.assertTrue(run_all.generate_metadata())
                self.assertEqual(run_all.os.environ['OPENAI_API_KEY'], 'test-key')
                command.assert_called_once()

    def test_thumbnail_error_preserves_successful_upload_and_receipt(self):
        youtube = Mock()
        youtube.videos.return_value.insert.return_value.next_chunk.return_value = (None, {'id': 'test-video-id'})
        with tempfile.TemporaryDirectory() as temporary:
            video = Path(temporary) / 'video.mp4'
            thumbnail = Path(temporary) / 'thumb.jpg'
            video.touch()
            thumbnail.touch()
            with patch.object(youtube_uploader, 'MediaFileUpload'), patch.object(youtube_uploader, 'upload_thumbnail', side_effect=RuntimeError('thumbnail failed')):
                video_id = youtube_uploader.upload_video(youtube, str(video), 'title', 'description', [], thumbnail_path=str(thumbnail))
            self.assertEqual(video_id, 'test-video-id')
            self.assertEqual(json.loads(video.with_suffix('.upload.json').read_text())['video_id'], video_id)

    def test_downloader_error_status_is_not_success(self):
        spec = importlib.util.spec_from_file_location('audited_downloader', ROOT / 'modules/automatic_upload/download_mp3.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory() as temporary, patch.object(module.yt_dlp, 'YoutubeDL') as downloader:
            downloader.return_value.__enter__.return_value.download.return_value = 1
            self.assertFalse(module.download_youtube_audio(urls=['https://example.invalid/video'], output_dir=temporary))


if __name__ == '__main__':
    unittest.main()
