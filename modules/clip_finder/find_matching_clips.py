"""Search YouTube for visual candidates for a song; downloads are opt-in."""
import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import re
import subprocess
import sys
import unicodedata
import uuid

BASE = Path(__file__).resolve().parent
STOP = {'the', 'a', 'an', 'of', 'and', 'or', 'to', 'you', 'your', 'why', 'should', 'up', 'never', 'gave',
        'mp3', 'wav', 'official', 'audio', 'lyrics', 'music', 'song', 'video', 'complete'}


def words(text):
    return [word for word in re.findall(r'\w+', unicodedata.normalize('NFKC', text).lower()) if word not in STOP and len(word) > 2]


def rank_candidates(entries, keywords, min_seconds=12, max_seconds=600):
    terms = set(words(keywords))
    ranked, seen = [], set()
    for entry in entries:
        if not entry or not re.fullmatch(r'[A-Za-z0-9_-]{11}', str(entry.get('id', ''))):
            continue
        identifier = entry['id']
        if identifier in seen or entry.get('live_status') in {'is_live', 'is_upcoming'}:
            continue
        seen.add(identifier)
        duration = entry.get('duration')
        if duration is not None and (not math.isfinite(duration) or not min_seconds <= duration <= max_seconds):
            continue
        title = entry.get('title') or identifier
        matches = sorted(terms & set(words(title + ' ' + (entry.get('description') or ''))))
        if terms and not matches:
            continue
        penalties = [term for term in ('reaction', 'tutorial', 'lyrics', 'music video', 'soundtrack', '#shorts',
                     'life lessons', 'learn these', 'motivation', 'explained', 'analysis', 'review') if term in title.lower()]
        visual_signals = [term for term in ('scene', 'footage', 'clip', 'rooftop', 'fight') if term in title.lower()]
        title_matches = terms & set(words(title))
        score = (10 * len(title_matches) + 3 * len(set(matches) - title_matches) +
                 (18 if visual_signals else 0) + (2 if duration is not None else 0) - 7 * len(penalties))
        ranked.append({'id': identifier, 'title': title, 'url': f'https://www.youtube.com/watch?v={identifier}',
            'duration_seconds': duration, 'channel': entry.get('channel') or entry.get('uploader'),
            'score': score, 'matched_terms': matches, 'penalties': penalties, 'visual_signals': visual_signals,
            'query': entry.get('_query'), 'license': entry.get('license') or 'unknown; verify on the source page'})
    return sorted(ranked, key=lambda item: (-item['score'], item['title'].lower()))


def search(queries, per_query):
    import yt_dlp
    entries, failures = [], []
    options = {'quiet': True, 'no_warnings': True, 'extract_flat': True,
               'socket_timeout': 15, 'retries': 1, 'extractor_retries': 1, 'noplaylist': True}
    with yt_dlp.YoutubeDL(options) as downloader:
        for query in queries:
            print(f'Searching: {query}', flush=True)
            try:
                result = downloader.extract_info(f'ytsearch{per_query}:{query}', download=False)
                entries.extend({**entry, '_query': query} for entry in (result or {}).get('entries', []) if entry)
            except Exception as error:
                failures.append({'query': query, 'error': str(error)})
    return entries, failures


def save_report(folder, report):
    (folder / 'candidates.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
    lines = ['# Online clip shortlist', '', f'Audio: `{report["audio"]}`',
             f'Keywords: {report["keywords"]}', f'Mood: {report["mood"]}', '',
             'Matches use metadata keywords and duration. No frames or lyrics were analyzed, and music synchronization is not certified.', '',
             '| Rank | Candidate | Length | Why selected |', '|---|---|---:|---|']
    for index, candidate in enumerate(report['candidates'], 1):
        title = candidate['title'].replace('|', '/').replace('[', '(').replace(']', ')').replace('\n', ' ')
        seconds = candidate['duration_seconds']
        length = f'{seconds:.0f}s' if seconds is not None else 'unknown'
        lines.append(f'| {index} | [{title}]({candidate["url"]}) | {length} | {", ".join(candidate["matched_terms"])} |')
    lines += ['', 'Review the actual scenes and source license before selecting clips. A keyword score is not a rights clearance.', '',
              'Search queries:', *[f'- {query}' for query in report['queries']]]
    if report['search_errors']:
        lines += ['', 'Some queries failed; see `candidates.json` for details.']
    if report.get('downloads'):
        lines += ['', 'Downloaded selections:']
        for item in report['downloads']:
            lines.append(f'- Asset `{item.get("asset_id", "unavailable")}`: {item.get("file", item.get("error", "Download failed"))}')
    (folder / 'README.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')


def download_selected(candidates, count, folder, library_folder=None):
    import yt_dlp
    from clip_library import ClipLibrary, DEFAULT_LIBRARY
    library = ClipLibrary(library_folder or DEFAULT_LIBRARY)
    clips = folder / 'clips'
    clips.mkdir()
    results = []
    for candidate in candidates[:count]:
        try:
            cached = library.cached_source(candidate['url'])
            if cached:
                results.append({'id': candidate['id'], 'asset_id': cached['id'], 'file': cached['file'],
                                'cached': True, 'license': cached['sources'][0]['license']})
                continue
            options = {'format': 'bestvideo[height<=720][ext=mp4]/best[height<=720][ext=mp4]/best[height<=720]',
                'outtmpl': str(clips / (candidate['id'] + '.%(ext)s')), 'noplaylist': True,
                'max_filesize': 300 * 1024 * 1024, 'socket_timeout': 20, 'retries': 2,
                'quiet': True, 'no_warnings': True}
            print(f'Downloading selected candidate: {candidate["title"]}', flush=True)
            with yt_dlp.YoutubeDL(options) as downloader:
                info = downloader.extract_info(candidate['url'], download=True)
            matches = [p for p in clips.glob(candidate['id'] + '.*') if p.suffix.lower() in {'.mp4', '.webm', '.mkv'}]
            if not info or not matches:
                raise RuntimeError('No supported video file was produced (possibly over the size limit)')
            imported = library.import_file(matches[0], source_url=candidate['url'], title=candidate['title'],
                                           license_info=info.get('license') or candidate['license'])
            results.append({'id': candidate['id'], 'asset_id': imported['id'], 'file': imported['file'],
                            'cached': False, 'license': info.get('license') or candidate['license']})
        except Exception as error:
            results.append({'id': candidate['id'], 'error': str(error)})
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', type=Path, required=True, help='Song used as the search context; not uploaded')
    parser.add_argument('--keywords', help='Visual topic/story, e.g. Batman Gotham resilience; inferred from filename if omitted')
    parser.add_argument('--mood', default='cinematic', help='Search wording, not an inferred emotion')
    parser.add_argument('--query', action='append', help='Exact search query; repeat to search several scenes')
    parser.add_argument('--count', type=int, default=10, help='Maximum ranked candidates saved')
    parser.add_argument('--per-query', type=int, default=10)
    parser.add_argument('--min-seconds', type=float, default=12)
    parser.add_argument('--max-seconds', type=float, default=600)
    parser.add_argument('--output', type=Path, help='New result directory; default unique output/search folder')
    parser.add_argument('--download-top', type=int, default=0, help='Explicitly download this many top candidates for local review')
    parser.add_argument('--library', type=Path, help='Shared local video library; default this module/library')
    args = parser.parse_args()
    if not args.audio.is_file():
        parser.error('--audio must be an existing file')
    if not 1 <= args.count <= 50 or not 1 <= args.per_query <= 30 or not 0 <= args.download_top <= args.count:
        parser.error('Use count 1–50, per-query 1–30, and download-top between zero and count')
    if not math.isfinite(args.min_seconds) or not math.isfinite(args.max_seconds) or not 0 < args.min_seconds <= args.max_seconds:
        parser.error('Duration limits must be positive, finite, and ordered')
    keywords = args.keywords or ' '.join(dict.fromkeys(words(args.audio.stem)))
    if not words(keywords):
        parser.error('Supply useful --keywords for this audio file')
    queries = args.query or [f'{keywords} {args.mood} scene', f'{keywords} cinematic footage']
    folder = (args.output or BASE / 'output/search' /
              (datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:6])).resolve()
    if folder.exists():
        parser.error('Output directory exists; choose a new one to preserve previous results')
    folder.mkdir(parents=True)
    try:
        entries, errors = search(queries, args.per_query)
        ranked = rank_candidates(entries, keywords, args.min_seconds, args.max_seconds)[:args.count]
        report = {'audio': str(args.audio.resolve()), 'keywords': keywords, 'mood': args.mood,
            'queries': queries, 'candidates': ranked, 'search_errors': errors,
            'method': 'Metadata keyword overlap, duration filtering, and edit/reaction penalties. Not audiovisual semantic analysis.'}
        save_report(folder, report)
        if not ranked:
            print(f'No matching candidates found. Search diagnostics: {folder / "candidates.json"}', file=sys.stderr)
            return 1
        if args.download_top:
            report['downloads'] = download_selected(ranked, args.download_top, folder, args.library)
            save_report(folder, report)
            if any('error' in item for item in report['downloads']):
                print(f'Some downloads failed. See {folder / "README.md"}', file=sys.stderr)
                return 1
        print(f'{len(ranked)} candidates saved. Open: {folder / "README.md"}', flush=True)
        return 0
    except Exception as error:
        (folder / 'error.txt').write_text(str(error), encoding='utf-8')
        print(f'Clip search failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
