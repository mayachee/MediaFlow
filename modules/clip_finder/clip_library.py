"""Content-addressed video library and explicitly reviewed highlight ranges."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import subprocess
import sys
import uuid

DEFAULT_LIBRARY = Path(__file__).resolve().parent / 'library'


def checksum(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def save(path, record):
    temporary = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    temporary.write_text(json.dumps(record, indent=2, ensure_ascii=False, allow_nan=False), encoding='utf-8')
    temporary.replace(path)


def command(args):
    result = subprocess.run([str(value) for value in args], capture_output=True, text=True, encoding='utf-8', errors='replace')
    if result.returncode:
        raise RuntimeError(result.stderr[-3000:])
    return result.stdout


def inspect_video(path, full_decode=True):
    info = json.loads(command(['ffprobe', '-v', 'error', '-show_streams', '-show_format', '-of', 'json', path]))
    video = next((s for s in info.get('streams', []) if s['codec_type'] == 'video'), None)
    if not video:
        raise ValueError('Source contains no video stream')
    duration = float(video.get('duration', info['format'].get('duration', 0)))
    if not math.isfinite(duration) or duration <= 0 or video['width'] < 2 or video['height'] < 2:
        raise ValueError('Invalid video dimensions or duration')
    if full_decode:
        command(['ffmpeg', '-nostdin', '-v', 'error', '-xerror', '-i', path, '-map', '0:v:0', '-map', '0:a?', '-f', 'null', '-'])
    return {'duration': duration, 'width': video['width'], 'height': video['height'],
        'codec': video['codec_name'], 'fps': video.get('avg_frame_rate'),
        'has_audio': any(s['codec_type'] == 'audio' for s in info['streams']),
        'verification': 'full_decode' if full_decode else 'metadata_only'}


class ClipLibrary:
    def __init__(self, folder=DEFAULT_LIBRARY):
        self.folder = Path(folder).resolve()
        self.assets = self.folder / 'assets'
        self.assets.mkdir(parents=True, exist_ok=True)

    def asset(self, identifier):
        if not re.fullmatch('[0-9a-f]{6,64}', identifier):
            raise ValueError('Asset ID must be a hexadecimal checksum or unique prefix')
        matches = list(self.assets.glob(identifier + '*'))
        if len(matches) != 1:
            raise ValueError('Asset ID is missing or ambiguous')
        folder = matches[0]
        record = json.loads((folder / 'asset.json').read_text(encoding='utf-8'))
        path = (folder / record['filename']).resolve()
        if not path.is_relative_to(folder.resolve()):
            raise ValueError('Library original must remain inside its asset folder')
        if not path.is_file() or checksum(path) != record['sha256']:
            raise ValueError('Library original is missing or has changed; restore it before reuse')
        return folder, record, path

    def import_file(self, source, *, source_url=None, title=None, license_info=None, full_decode=True):
        source = Path(source).resolve()
        if not source.is_file():
            raise ValueError(f'Video does not exist: {source}')
        if source.suffix.lower() not in {'.mp4', '.webm', '.mkv', '.mov', '.avi', '.m4v', '.flv', '.wmv'}:
            raise ValueError('Unsupported video extension')
        identifier = checksum(source)
        folder = self.assets / identifier
        if (folder / 'asset.json').is_file():
            _, record, _ = self.asset(identifier)
            reused = True
            if full_decode and record['media']['verification'] != 'full_decode':
                record['media'] = inspect_video(folder / record['filename'])
        else:
            media = inspect_video(source, full_decode)
            folder.mkdir(exist_ok=True)
            filename = 'original' + source.suffix.lower()
            destination = folder / filename
            if destination.exists():
                if checksum(destination) != identifier:
                    raise ValueError('Conflicting incomplete import; original will not be overwritten')
            else:
                temporary = folder / ('import-' + uuid.uuid4().hex + source.suffix)
                shutil.copy2(source, temporary)
                if checksum(temporary) != identifier:
                    raise ValueError('Source changed during import')
                temporary.replace(destination)
            record = {'id': identifier, 'sha256': identifier, 'filename': filename, 'media': media, 'sources': []}
            reused = False
        provenance = {'url': source_url, 'title': title or source.stem,
                      'license': license_info or 'unknown', 'imported_from': str(source)}
        if provenance not in record['sources']:
            record['sources'].append(provenance)
        save(folder / 'asset.json', record)
        return {**record, 'file': str(folder / record['filename']), 'reused': reused}

    def cached_source(self, url):
        for metadata in self.assets.glob('*/asset.json'):
            record = json.loads(metadata.read_text(encoding='utf-8'))
            if any(source.get('url') == url for source in record['sources']):
                _, record, path = self.asset(record['id'])
                return {**record, 'file': str(path), 'reused': True}
        return None

    def add_highlight(self, identifier, start, end, tags=None, note=''):
        folder, asset, _ = self.asset(identifier)
        if not math.isfinite(start) or not math.isfinite(end) or not 0 <= start < end <= asset['media']['duration']:
            raise ValueError('Highlight must have 0 <= start < end <= source duration')
        if end - start < 0.1:
            raise ValueError('Select at least 0.1 seconds')
        record = {'asset_id': asset['id'], 'start': start, 'end': end,
                  'tags': sorted(set(tags or [])), 'note': note, 'selection': 'explicit_user_range'}
        highlight_id = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()[:12]
        record['id'] = highlight_id
        highlights = folder / 'highlights'
        highlights.mkdir(exist_ok=True)
        save(highlights / (highlight_id + '.json'), record)
        return {**record, 'reference': asset['id'] + ':' + highlight_id}

    def render_highlight(self, reference):
        identifier, separator, highlight_id = reference.partition(':')
        if not separator or not re.fullmatch('[0-9a-f]{12}', highlight_id):
            raise ValueError('Use an ASSET_ID:HIGHLIGHT_ID reference')
        folder, asset, original = self.asset(identifier)
        record = json.loads((folder / 'highlights' / (highlight_id + '.json')).read_text(encoding='utf-8'))
        selection = {key: value for key, value in record.items() if key != 'id'}
        expected_id = hashlib.sha256(json.dumps(selection, sort_keys=True).encode()).hexdigest()[:12]
        if expected_id != highlight_id:
            raise ValueError('Highlight record changed; create a new range rather than modifying a cached selection')
        output = folder / 'highlights' / (highlight_id + '.mp4')
        receipt = output.with_suffix('.render.json')
        if output.is_file() and receipt.is_file():
            rendered = json.loads(receipt.read_text(encoding='utf-8'))
            if rendered['sha256'] == checksum(output):
                return {**rendered, 'file': str(output), 'reused': True}
        temporary = output.with_name(highlight_id + '-' + uuid.uuid4().hex + '.mp4')
        command(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-ss', record['start'], '-i', original,
            '-t', record['end'] - record['start'], '-map', '0:v:0', '-an',
            '-vf', 'scale=trunc(iw*sar/2)*2:trunc(ih/2)*2,setsar=1',
            '-c:v', 'libx264', '-preset', 'fast', '-crf', '18', '-pix_fmt', 'yuv420p', '-movflags', '+faststart', temporary])
        media = inspect_video(temporary)
        if abs(media['duration'] - (record['end'] - record['start'])) > 0.15:
            raise ValueError('Trimmed highlight has an unexpected duration')
        temporary.replace(output)
        rendered = {'reference': reference, 'asset_id': asset['id'], 'range': record,
                    'sha256': checksum(output), 'media': media, 'sources': asset['sources']}
        save(receipt, rendered)
        return {**rendered, 'file': str(output), 'reused': False}

    def export_timeline(self, references, destination, seconds=None):
        destination = Path(destination).resolve()
        if destination.exists() or destination.with_suffix('.sources.json').exists():
            raise ValueError('Choose a new timeline filename to preserve previous edits')
        if seconds is not None and (not math.isfinite(seconds) or seconds <= 0):
            raise ValueError('Timeline seconds must be positive and finite')
        clips = [self.render_highlight(reference) for reference in references]
        if not clips:
            raise ValueError('Select at least one highlight')
        coverage = sum(clip['media']['duration'] for clip in clips)
        target = coverage if seconds is None else seconds
        if coverage + 0.01 < target:
            raise ValueError(f'Only {coverage:.2f}s of reviewed footage covers a {target:.2f}s timeline; select more highlights')
        scenes, provenance, remaining = [], [], target
        for clip in clips:
            if remaining < 0.001:
                break
            length = min(remaining, clip['media']['duration'])
            if length < 0.1:
                raise ValueError('Timeline ends with a sub-0.1s shot; adjust the requested length')
            scenes.append({'source': clip['file'], 'duration': length, 'framing': 'fill', 'motion': 'still'})
            provenance.append({'reference': clip['reference'], 'sha256': clip['sha256'],
                               'source_range': clip['range'], 'sources': clip['sources']})
            remaining -= length
        scenes[-1]['duration'] = 'auto'
        document = {'scenes': scenes, 'provenance': provenance, 'planned_seconds': target}
        destination.parent.mkdir(parents=True, exist_ok=True)
        save(destination, document)
        save(destination.with_suffix('.sources.json'), {'provenance': provenance, 'planned_seconds': target})
        return document


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--library', type=Path, default=DEFAULT_LIBRARY)
    sub = parser.add_subparsers(dest='action', required=True)
    add = sub.add_parser('import')
    add.add_argument('--file', type=Path, required=True)
    add.add_argument('--source-url')
    add.add_argument('--title')
    add.add_argument('--license')
    add.add_argument('--quick', action='store_true', help='Metadata-only inspection; full decoding is the default')
    highlight = sub.add_parser('highlight')
    highlight.add_argument('--asset', required=True)
    highlight.add_argument('--start', type=float, required=True)
    highlight.add_argument('--end', type=float, required=True)
    highlight.add_argument('--tag', action='append', default=[])
    highlight.add_argument('--note', default='')
    render = sub.add_parser('render')
    render.add_argument('--highlight', required=True)
    export = sub.add_parser('export')
    export.add_argument('--highlight', action='append', required=True)
    export.add_argument('--output', type=Path, required=True)
    length = export.add_mutually_exclusive_group()
    length.add_argument('--seconds', type=float)
    length.add_argument('--audio', type=Path, help='Use this audio file duration as the required footage coverage')
    sub.add_parser('list')
    download = sub.add_parser('download')
    download.add_argument('--report', type=Path, required=True, help='Previously reviewed candidates.json')
    download.add_argument('--rank', type=int, action='append', required=True, help='One-based rank to download; repeat to select several')
    args = parser.parse_args()
    try:
        library = ClipLibrary(args.library)
        if args.action == 'download':
            candidates = json.loads(args.report.read_text(encoding='utf-8'))['candidates']
            ranks = list(dict.fromkeys(args.rank))
            if any(rank < 1 or rank > len(candidates) for rank in ranks):
                raise ValueError('Selected rank is outside this report')
            from find_matching_clips import download_selected
            job = library.folder / 'downloads' / uuid.uuid4().hex[:12]
            job.mkdir(parents=True)
            result = download_selected([candidates[rank - 1] for rank in ranks], len(ranks), job, library.folder)
            save(job / 'download-report.json', {'report': str(args.report.resolve()), 'ranks': ranks, 'results': result})
            if any('error' in record for record in result):
                raise RuntimeError(f'Selected downloads failed; see {job / "download-report.json"}')
        elif args.action == 'import':
            result = library.import_file(args.file, source_url=args.source_url, title=args.title,
                                         license_info=args.license, full_decode=not args.quick)
        elif args.action == 'highlight':
            result = library.add_highlight(args.asset, args.start, args.end, args.tag, args.note)
        elif args.action == 'render':
            result = library.render_highlight(args.highlight)
        elif args.action == 'export':
            seconds = args.seconds
            if args.audio:
                info = json.loads(command(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', args.audio]))
                seconds = float(info['format']['duration'])
            result = library.export_timeline(args.highlight, args.output, seconds)
        else:
            result = [json.loads(p.read_text(encoding='utf-8')) for p in library.assets.glob('*/asset.json')]
        print(json.dumps(result, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, KeyError) as error:
        print(f'Library operation failed: {error}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
