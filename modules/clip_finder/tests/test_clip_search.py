import importlib.util
from pathlib import Path
import unittest

spec = importlib.util.spec_from_file_location('clip_finder', Path(__file__).resolve().parents[1] / 'find_matching_clips.py')
finder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(finder)


class ClipSearchTests(unittest.TestCase):
    def test_relevance_duration_and_duplicates(self):
        entries = [
            {'id': 'aaaaaaaaaaa', 'title': 'Batman Gotham rooftop scene', 'duration': 90},
            {'id': 'aaaaaaaaaaa', 'title': 'duplicate', 'duration': 90},
            {'id': 'bbbbbbbbbbb', 'title': 'Batman reaction tutorial', 'duration': 90},
            {'id': 'ccccccccccc', 'title': 'Batman short', 'duration': 5},
            {'id': 'ddddddddddd', 'title': 'Cooking pasta', 'duration': 90},
            {'id': 'eeeeeeeeeee', 'title': 'Batman live', 'live_status': 'is_live'}]
        ranked = finder.rank_candidates(entries, 'Batman Gotham')
        self.assertEqual([item['id'] for item in ranked], ['aaaaaaaaaaa', 'bbbbbbbbbbb'])
        self.assertEqual(ranked[0]['matched_terms'], ['batman', 'gotham'])
        self.assertIn('verify', ranked[0]['license'])

    def test_invalid_ids_and_unknown_durations(self):
        ranked = finder.rank_candidates([{'id': '../bad', 'title': 'Batman'},
            {'id': 'abcdefghijk', 'title': 'Batman scene'}], 'Batman')
        self.assertEqual(len(ranked), 1)
        self.assertIsNone(ranked[0]['duration_seconds'])

    def test_unicode_title_normalization(self):
        self.assertIn('batman', finder.words('𝐁𝐚𝐭𝐦𝐚𝐧 official audio'))

    def test_scene_candidates_outrank_lesson_videos(self):
        ranked = finder.rank_candidates([
            {'id': 'aaaaaaaaaaa', 'title': 'Life lessons from Batman Gotham resilience', 'duration': 120},
            {'id': 'bbbbbbbbbbb', 'title': 'Batman rooftop scene', 'duration': 120}], 'Batman Gotham resilience')
        self.assertEqual(ranked[0]['id'], 'bbbbbbbbbbb')


if __name__ == '__main__':
    unittest.main()
