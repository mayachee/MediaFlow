"""Offline provider fixture for the dashboard's real search/download workflow."""
import argparse
from pathlib import Path
from unittest.mock import patch

from modules.clip_finder import find_matching_clips as finder


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--fixture-video', type=Path, required=True)
    parser.add_argument('--fixture-output', type=Path, required=True)
    args, remaining = parser.parse_known_args()
    def search(queries, count):
        return [dict(id=key * 11, title=f'Offline fixture {index}: {queries[0]}', duration=60)
                for index, key in enumerate(['a', 'b', 'c'], 1)], []
    def download(candidates, count, folder, library_folder=None, try_alternates=False):
        return [dict(id=row['id'], asset_id='offline-fixture-' + row['id'],
                     file=str(args.fixture_video.resolve()), cached=False) for row in candidates[:count]]
    with patch.object(finder, 'search', side_effect=search), patch.object(finder, 'download_selected', side_effect=download):
        return finder.main(remaining + ['--output', str(args.fixture_output)])


if __name__ == '__main__':
    raise SystemExit(main())
