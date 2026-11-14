import json
import os
from pathlib import Path
import tempfile
import subprocess
import time
import unittest

from tools.workspace_cleaner import WorkspaceCleaner


class CleanerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.cleaner = WorkspaceCleaner(self.root)

    def file(self, relative, data=b'fixture'):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def job(self, name, status):
        self.file(f'runs/script-manager/{name}/job.json', json.dumps({'status': status}).encode())
        self.file(f'runs/script-manager/{name}/output.log')

    def test_preview_is_read_only_and_protects_originals_models_and_active_jobs(self):
        self.file('tools/__pycache__/sample.pyc')
        self.file('source.py')
        for protected in ['input', 'library', 'work', 'config', '.venv', 'VENDOR', 'runs/render/video']:
            self.file(f'modules/{protected}/__pycache__/keep.pyc') if protected != 'runs/render/video' else self.file('runs/render/video/__pycache__/keep.pyc')
        self.job('finished', 'completed')
        self.job('active', 'running')
        self.job('has-media', 'completed')
        self.file('runs/script-manager/has-media/keep.mp4')
        before = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        result = self.cleaner.scan(days=0)
        self.assertEqual({item['relative'] for item in result['items']},
                         {'tools/__pycache__', 'runs/script-manager/finished'})
        after = {path.relative_to(self.root): path.read_bytes() for path in self.root.rglob('*') if path.is_file()}
        self.assertEqual(before, after)

    def test_quarantine_and_restore_preserve_content(self):
        path = self.file('tools/__pycache__/sample.pyc', b'original bytes')
        items = self.cleaner.scan(days=0)['items']
        batch = self.cleaner.quarantine(items)
        self.assertEqual(batch['errors'], [])
        self.assertFalse(path.exists())
        self.assertTrue(self.cleaner.batches())
        result = self.cleaner.restore(batch['batch'])
        self.assertEqual(result['errors'], [])
        self.assertEqual(path.read_bytes(), b'original bytes')

    def test_changed_preview_is_not_moved(self):
        path = self.file('tools/__pycache__/sample.pyc')
        items = self.cleaner.scan(days=0)['items']
        path.write_bytes(b'changed after scanning')
        result = self.cleaner.quarantine(items)
        self.assertTrue(result['errors'])
        self.assertTrue(path.exists())

    def test_restore_never_overwrites_recreated_files(self):
        path = self.file('tools/__pycache__/sample.pyc')
        result = self.cleaner.quarantine(self.cleaner.scan(days=0)['items'])
        self.file('tools/__pycache__/sample.pyc', b'new cache')
        restored = self.cleaner.restore(result['batch'])
        self.assertTrue(restored['errors'])
        self.assertEqual(path.read_bytes(), b'new cache')

    def test_purge_only_removes_a_validated_trash_batch(self):
        original = self.file('source.py')
        self.file('tools/__pycache__/sample.pyc')
        batch = self.cleaner.quarantine(self.cleaner.scan(days=0)['items'])
        result = self.cleaner.purge(batch['batch'])
        self.assertGreater(result['bytes'], 0)
        self.assertTrue(original.exists())
        self.assertFalse((self.cleaner.trash / batch['batch']).exists())
        for illegal in ['../../..', '.', '..', str(self.root)]:
            with self.assertRaises((ValueError, OSError)):
                self.cleaner.purge(illegal)

    def test_forged_preview_cannot_move_source_or_protected_folders(self):
        source = self.file('source.py')
        protected = self.file('.venv/__pycache__/model.pyc')
        for relative in ['source.py', '.venv/__pycache__', '../outside']:
            result = self.cleaner.quarantine([dict(relative=relative, signature='invalid')])
            self.assertTrue(result['errors'])
        self.assertTrue(source.exists())
        self.assertTrue(protected.exists())

    def test_age_filter_uses_latest_content_and_category_switches(self):
        path = self.file('tools/__pycache__/sample.pyc')
        self.assertFalse(self.cleaner.scan(days=7)['items'])
        old = time.time() - 10 * 86400
        os.utime(path, (old, old))
        os.utime(path.parent, (old, old))
        self.assertEqual(len(self.cleaner.scan(days=7)['items']), 1)
        self.assertFalse(self.cleaner.scan(days=0, caches=False, logs=False)['items'])

    def test_tampered_trash_manifest_cannot_restore_outside_workspace(self):
        self.file('tools/__pycache__/sample.pyc')
        batch = self.cleaner.quarantine(self.cleaner.scan(days=0)['items'])
        manifest = self.cleaner.trash / batch['batch'] / 'manifest.json'
        data = json.loads(manifest.read_text())
        data['items'][0]['relative'] = '../outside'
        manifest.write_text(json.dumps(data))
        self.assertTrue(self.cleaner.restore(batch['batch'])['errors'])

    def test_reparse_points_are_not_followed_during_scan_or_purge(self):
        keep = self.file('library/keep.pyc', b'original asset')
        link = self.root / 'tools/__pycache__'
        link.parent.mkdir()
        def link_to(path):
            try:
                path.symlink_to(keep.parent, target_is_directory=True)
            except OSError:
                if os.name != 'nt':
                    self.skipTest('Symbolic links are unavailable')
                result = subprocess.run(['cmd.exe', '/c', 'mklink', '/J', str(path), str(keep.parent)], capture_output=True)
                if result.returncode:
                    self.skipTest('Junction creation is unavailable')
        link_to(link)
        self.assertFalse(self.cleaner.scan(days=0)['items'])
        self.file('tests/__pycache__/fixture.pyc')
        batch = self.cleaner.quarantine(self.cleaner.scan(days=0)['items'])
        injected = self.cleaner.trash / batch['batch'] / 'files/tests/__pycache__/unexpected-link'
        link_to(injected)
        with self.assertRaises(ValueError):
            self.cleaner.purge(batch['batch'])
        self.assertEqual(keep.read_bytes(), b'original asset')

    def test_job_that_started_again_is_excluded_from_stale_preview(self):
        self.job('finished', 'completed')
        items = self.cleaner.scan(days=0)['items']
        self.job('finished', 'running')
        result = self.cleaner.quarantine(items)
        self.assertTrue(result['errors'])
        self.assertTrue((self.root / 'runs/script-manager/finished/output.log').is_file())


if __name__ == '__main__':
    unittest.main()
