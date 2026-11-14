"""Preview and quarantine regenerable workspace files; never clean media or inputs."""
import argparse
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
PROTECTED = {'.git', '.codex', '.agents', '.aws', '.venv', 'venv', 'vendor', 'assets',
             'config', 'input', 'library', 'downloads', 'output', 'work', 'stems', 'node_modules'}
TERMINAL = {'completed', 'failed', 'cancelled'}


def size_label(value):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if value < 1024 or unit == 'TB':
            return f'{value:.1f} {unit}'
        value /= 1024


class WorkspaceCleaner:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.trash = self.root / 'runs/.trash/cleaner'

    def _path(self, relative):
        value = Path(relative)
        if value.is_absolute() or '..' in value.parts or value.drive or not value.parts:
            raise ValueError('Expected a relative path inside the workspace.')
        path = self.root / value
        path.resolve().relative_to(self.root)
        current = self.root
        for part in value.parts:
            current = current / part
            if current.is_symlink() or (current.exists() and
                    getattr(current.lstat(), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT):
                raise ValueError('Linked paths and Windows junctions are excluded.')
        return path

    def _info(self, path):
        """Validate the complete tree before any recursive move or delete."""
        path = self._path(path.relative_to(self.root))
        records, total, newest = [], 0, path.stat().st_mtime
        for folder, directories, files in os.walk(path, followlinks=False):
            for name in sorted(directories + files):
                child = self._path((Path(folder) / name).relative_to(self.root))
                info = child.lstat()
                if not stat.S_ISDIR(info.st_mode) and not stat.S_ISREG(info.st_mode):
                    raise ValueError('Only ordinary files and directories can be cleaned.')
                records.append((child.relative_to(path).as_posix(), info.st_size, info.st_mtime_ns))
                if stat.S_ISREG(info.st_mode):
                    total += info.st_size
                newest = max(newest, info.st_mtime)
        signature = hashlib.sha256(json.dumps(sorted(records)).encode()).hexdigest()
        return dict(bytes=total, files=sum(1 for row in records if (path / row[0]).is_file()),
                    newest=newest, signature=signature)

    def _kind(self, path):
        relative = path.relative_to(self.root)
        if not path.is_dir():
            raise ValueError('Only generated folders are eligible for cleanup.')
        if path.name in {'__pycache__', '.pytest_cache'} and not any(part.casefold() in PROTECTED or part.casefold() == 'runs' for part in relative.parts):
            return 'Python cache'
        if path.parent == self.root / 'runs/script-manager':
            document = json.loads((path / 'job.json').read_text(encoding='utf-8'))
            if document.get('status') not in TERMINAL:
                raise ValueError('Running or unknown jobs are excluded.')
            if any(child.name not in {'job.json', 'output.log', 'job.tmp'} or not child.is_file() for child in path.iterdir()):
                raise ValueError('Job folders with additional files are excluded.')
            return 'Completed job log'
        raise ValueError('This location is not eligible for cleanup.')

    def scan(self, days=7, caches=True, logs=True):
        if not isinstance(days, int) or days < 0:
            raise ValueError('Age must be a nonnegative whole number of days.')
        candidates = []
        if caches:
            for folder, directories, _ in os.walk(self.root, followlinks=False):
                kept = []
                for name in sorted(directories):
                    child = Path(folder) / name
                    if name.casefold() in PROTECTED or name.casefold() == 'runs' or (name.startswith('.') and name != '.pytest_cache'):
                        continue
                    try:
                        self._path(child.relative_to(self.root))
                    except (OSError, ValueError):
                        continue
                    if name in {'__pycache__', '.pytest_cache'}:
                        candidates.append(child)
                    else:
                        kept.append(name)
                directories[:] = kept
        if logs:
            parent = self._path('runs/script-manager')
            if parent.is_dir():
                candidates += sorted(parent.iterdir())
        items = []
        cutoff = time.time() - days * 86400
        for path in candidates:
            try:
                path = self._path(path.relative_to(self.root))
                kind = self._kind(path)
                info = self._info(path)
                if info['newest'] <= cutoff and info['files']:
                    items.append(dict(relative=path.relative_to(self.root).as_posix(), kind=kind, **info))
            except (OSError, ValueError, KeyError):
                continue
        return dict(items=items, bytes=sum(item['bytes'] for item in items), days=days)

    def _save(self, batch, document):
        self._path(batch.relative_to(self.root))
        temporary = batch / 'manifest.tmp'
        self._path(temporary.relative_to(self.root))
        temporary.write_text(json.dumps(document, indent=2), encoding='utf-8')
        temporary.replace(batch / 'manifest.json')

    def quarantine(self, items):
        if not items:
            raise ValueError('Select at least one preview item.')
        batch_id = datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:8]
        batch = self._path(f'runs/.trash/cleaner/{batch_id}')
        batch.mkdir(parents=True)
        document = dict(version=1, batch=batch_id, created=datetime.now().isoformat(), items=[], errors=[])
        self._save(batch, document)
        for item in items:
            try:
                source = self._path(item['relative'])
                self._kind(source)
                info = self._info(source)
                if info['signature'] != item['signature']:
                    raise ValueError('Files changed after the preview; scan again.')
                target = self._path((batch / 'files' / item['relative']).relative_to(self.root))
                target.parent.mkdir(parents=True, exist_ok=True)
                if target.exists():
                    raise ValueError('Trash destination already exists.')
                record = dict(relative=item['relative'], bytes=info['bytes'], signature=info['signature'], status='pending')
                document['items'].append(record)
                self._save(batch, document)
                # Both resolved paths and every descendant have been validated.
                source.rename(target)
                record['status'] = 'quarantined'
                self._save(batch, document)
            except (OSError, ValueError, KeyError) as error:
                document['errors'].append(f"{item.get('relative', '?')}: {error}")
        self._save(batch, document)
        return document

    def _batch(self, batch_id):
        if Path(batch_id).name != batch_id or batch_id in {'', '.', '..'}:
            raise ValueError('Choose a valid Studio Trash batch.')
        batch = self._path(f'runs/.trash/cleaner/{batch_id}')
        manifest = self._path((batch / 'manifest.json').relative_to(self.root))
        document = json.loads(manifest.read_text(encoding='utf-8'))
        if document.get('version') != 1 or document.get('batch') != batch_id:
            raise ValueError('Unrecognized trash manifest.')
        return batch, document

    def batches(self):
        self._path('runs/.trash/cleaner')
        if not self.trash.is_dir():
            return []
        result = []
        for path in sorted(self.trash.iterdir(), reverse=True):
            try:
                batch, document = self._batch(path.name)
                info = self._info(batch)
                result.append(dict(id=path.name, bytes=info['bytes'], document=document))
            except (OSError, ValueError, KeyError):
                continue
        return result

    def restore(self, batch_id):
        batch, document = self._batch(batch_id)
        errors = []
        for record in document['items']:
            if record['status'] not in {'quarantined', 'pending'}:
                continue
            try:
                target = self._path(record['relative'])
                self._kind_location(target)
                source = self._path((batch / 'files' / record['relative']).relative_to(self.root))
                if not source.exists():
                    raise ValueError('Trash payload is missing.')
                info = self._info(source)
                if info['signature'] != record['signature']:
                    raise ValueError('Trash contents changed; restore them manually.')
                if target.exists():
                    raise ValueError('Original location already exists; nothing was overwritten.')
                target.parent.mkdir(parents=True, exist_ok=True)
                source.rename(target)
                record['status'] = 'restored'
                self._save(batch, document)
            except (OSError, ValueError, KeyError) as error:
                errors.append(f"{record['relative']}: {error}")
        return dict(batch=batch_id, errors=errors)

    def _kind_location(self, path):
        """Check a restore location without requiring the original to exist."""
        relative = path.relative_to(self.root)
        cache = path.name in {'__pycache__', '.pytest_cache'} and not any(part.casefold() in PROTECTED or part.casefold() == 'runs' for part in relative.parts)
        job = path.parent == self.root / 'runs/script-manager'
        if not cache and not job:
            raise ValueError('Restore location is outside supported cleanup locations.')

    def purge(self, batch_id):
        batch, _ = self._batch(batch_id)
        # Validate the absolute target and full tree before recursive deletion.
        batch.resolve().relative_to(self.trash.resolve())
        info = self._info(batch)
        shutil.rmtree(batch)
        return dict(batch=batch_id, bytes=info['bytes'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--days', type=int, default=7)
    args = parser.parse_args()
    print(json.dumps(WorkspaceCleaner().scan(args.days), indent=2))


if __name__ == '__main__':
    main()
