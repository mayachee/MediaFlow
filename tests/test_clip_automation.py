import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from modules.clip_finder import find_matching_clips as finder
from modules.clip_finder import clip_library
from studio_server import StudioState
from tools.script_catalog import build_command, curated_tools


class ClipAutomationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.video = self.root / 'existing.mp4'
        self.video.write_bytes(b'original fixture bytes')
        self.entries = [dict(id=key * 11, title=f'Batman Gotham scene {key}', duration=60)
                        for key in ['a', 'b', 'c']]

    def invoke(self, arguments, downloads=None):
        with patch.object(finder, 'search', return_value=(self.entries, [])) as search, \
             patch.object(finder, 'download_selected', return_value=downloads or []) as download, \
             contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            result = finder.main(arguments)
        return result, search, download

    def test_title_only_search_download_and_visuals_handoff(self):
        folder = self.root / 'title-search'
        records = [dict(id='a' * 11, error='first source unavailable'),
                   dict(id='b' * 11, file=str(self.video), asset_id='asset-b', cached=True),
                   dict(id='c' * 11, file=str(self.video), asset_id='asset-c', cached=False)]
        result, search, download = self.invoke(['--title', 'Batman Gotham rooftops', '--download-top', '2',
            '--download-mode', 'best-available', '--output', str(folder)], records)
        self.assertEqual(result, 0)
        self.assertIn('Batman Gotham rooftops', search.call_args.args[0][0])
        self.assertTrue(download.call_args.kwargs['try_alternates'])
        report = json.loads((folder / 'candidates.json').read_text())
        self.assertIsNone(report['audio'])
        self.assertEqual(report['requested_downloads'], 2)
        self.assertEqual(len(list(Path(report['visuals_folder']).glob('*.mp4'))), 2)
        self.assertEqual(self.video.read_bytes(), b'original fixture bytes')
        state = StudioState(self.root)
        parsed = state._clip_report([f'Clip report: {folder / "candidates.json"}'])
        self.assertEqual(len(parsed['clips']), 2)
        self.assertEqual(parsed['visuals_folder'], str(folder / 'visuals'))
        self.assertEqual(len(parsed['failures']), 1)

    def test_keywords_only_shortlist_does_not_download(self):
        folder = self.root / 'keywords'
        result, _, download = self.invoke(['--keywords', 'Batman Gotham', '--output', str(folder)])
        self.assertEqual(result, 0)
        download.assert_not_called()

    def test_partial_download_keeps_usable_clips_and_reports_failure(self):
        folder = self.root / 'partial'
        result, _, _ = self.invoke(['--title', 'Batman Gotham', '--download-top', '3',
            '--download-mode', 'best-available', '--output', str(folder)],
            [dict(id='a' * 11, file=str(self.video), asset_id='asset-a')])
        self.assertEqual(result, 1)
        self.assertEqual(len(list((folder / 'visuals').glob('*.mp4'))), 1)

    def test_invalid_input_never_searches_or_creates_output(self):
        folder = self.root / 'invalid'
        for arguments in [[], ['--title', '   '], ['--title', 'Batman', '--download-top', '11'],
                          ['--title', 'Batman', '--download-mode', 'best-available', '--download-top', '0']]:
            with self.assertRaises(SystemExit):
                self.invoke(arguments + ['--output', str(folder)])
            self.assertFalse(folder.exists())

    def test_automatic_mode_tries_next_source_after_download_failure(self):
        folder = self.root / 'download'
        folder.mkdir()
        choices = finder.rank_candidates(self.entries, 'Batman Gotham')
        class FakeDownloader:
            def __init__(self, options):
                self.options = options
            def __enter__(self):
                return self
            def __exit__(self, *args):
                pass
            def extract_info(self, url, download):
                if 'a' * 11 in url:
                    raise RuntimeError('Unavailable source')
                Path(self.options['outtmpl'].replace('%(ext)s', 'mp4')).write_bytes(b'download fixture')
                return {'license': 'fixture'}
        library = Mock()
        library.cached_source.return_value = None
        library.import_file.return_value = {'id': 'asset', 'file': str(self.video)}
        with patch.dict(sys.modules, {'yt_dlp': SimpleNamespace(YoutubeDL=FakeDownloader)}), \
             patch.object(clip_library, 'ClipLibrary', return_value=library), \
             contextlib.redirect_stdout(io.StringIO()):
            results = finder.download_selected(choices, 2, folder, try_alternates=True)
        self.assertEqual(sum('file' in item for item in results), 2)
        self.assertEqual(len(results), 3)

    def test_studio_has_title_and_auto_download_without_required_audio(self):
        tool = next(tool for tool in curated_tools() if tool['id'] == 'clips-auto')
        command, _ = build_command(tool, {'title': 'forest mountains sunrise'})
        self.assertIn('--title', command)
        self.assertIn('forest mountains sunrise', command)
        self.assertIn('best-available', command)
        self.assertEqual(command[command.index('--download-top') + 1], '3')
        self.assertNotIn('--audio', command)

    def test_arbitrary_topics_use_the_entered_words_and_filter_unrelated_clips(self):
        for index, topic in enumerate(['ocean waves sunset', 'sports cars drifting',
                                       'space planets stars', 'plage vagues coucher soleil']):
            with self.subTest(topic=topic):
                folder = self.root / f'topic-{index}'
                entries = [dict(id='a' * 11, title=topic + ' footage', duration=60),
                           dict(id='b' * 11, title='Gotham rooftop scene', duration=60)]
                with patch.object(finder, 'search', return_value=(entries, [])) as search, \
                     contextlib.redirect_stdout(io.StringIO()):
                    self.assertEqual(finder.main(['--keywords', topic, '--output', str(folder)]), 0)
                self.assertTrue(all(topic in query for query in search.call_args.args[0]))
                report = json.loads((folder / 'candidates.json').read_text())
                self.assertEqual(report['keywords'], topic)
                self.assertEqual([row['id'] for row in report['candidates']], ['a' * 11])


if __name__ == '__main__':
    unittest.main()
