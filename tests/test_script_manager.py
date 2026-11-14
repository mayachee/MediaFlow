import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest

from tools.script_catalog import ROOT, ScriptJob, build_command, curated_tools, discover_scripts


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tools = {tool['id']: tool for tool in curated_tools()}

    def test_catalog_entries_exist_and_upload_is_private(self):
        for tool in self.tools.values():
            self.assertTrue((ROOT / tool['cwd']).is_dir(), tool['id'])
            if tool['script']:
                self.assertTrue((ROOT / tool['script']).is_file(), tool['script'])
        privacy = next(field for field in self.tools['youtube']['fields'] if field['key'] == 'privacy')
        self.assertEqual(privacy['default'], 'private')

    def test_discovery_never_imports_and_skips_generated_and_vendor_code(self):
        (self.root / 'danger.py').write_text('raise RuntimeError("Never import me")')
        for folder in ['vendor', 'runs', '.venv', 'src']:
            (self.root / folder).mkdir()
            (self.root / folder / 'helper.py').write_text('raise RuntimeError()')
        catalog = discover_scripts(self.root)
        self.assertEqual({tool['script'] for tool in catalog}, {'danger.py', 'src/helper.py'})
        self.assertFalse(next(tool for tool in catalog if tool['script'] == 'src/helper.py')['runnable'])

    def test_rank_repetition_and_paths_are_passed_as_arguments(self):
        report = self.root / "Dima's report & clips.json"
        report.write_text('{}')
        command, cwd = build_command(self.tools['clips-download'], {'report': str(report), 'ranks': '1 3'})
        self.assertEqual(command[-4:], ['--rank', '1', '--rank', '3'])
        self.assertIn(str(report.resolve()), command)
        self.assertEqual(cwd, ROOT)
        with self.assertRaises(ValueError):
            build_command(self.tools['clips-download'], {'report': str(report), 'ranks': '0'})

    def test_zero_timestamp_and_invalid_inputs(self):
        command, _ = build_command(self.tools['clips-highlight'], {'asset': 'abc123', 'start': '0', 'end': '5'})
        self.assertEqual(command[command.index('--start') + 1], '0')
        for values in [{'asset': '', 'end': '5'}, {'asset': 'abc123', 'start': 'nan', 'end': '5'}]:
            with self.assertRaises(ValueError):
                build_command(self.tools['clips-highlight'], values)
        with self.assertRaises(ValueError):
            build_command(self.tools['video'], {'preset': 'video', 'preview_seconds': '15'})

    def test_shared_files_and_escaping_paths_cannot_be_run(self):
        tool = dict(self.tools['doctor'], script='../outside.py')
        with self.assertRaises(ValueError):
            build_command(tool, {})
        tool['runnable'] = False
        with self.assertRaises(ValueError):
            build_command(tool, {})

    def test_jobs_capture_output_and_nonzero_exit(self):
        lines = []
        job = ScriptJob([sys.executable, '-c', 'print("hello"); raise SystemExit(3)'], self.root, self.root)
        result = job.run(lines.append)
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['exit_code'], 3)
        self.assertIn('hello', ''.join(lines))
        self.assertIn('hello', (job.folder / 'output.log').read_text())
        self.assertEqual(json.loads((job.folder / 'job.json').read_text())['status'], 'failed')

    def test_cancel_running_process(self):
        job = ScriptJob([sys.executable, '-u', '-c', 'import time; print("ready", flush=True); time.sleep(60)'], self.root, self.root)
        ready = threading.Event()
        results = []
        worker = threading.Thread(target=lambda: results.append(job.run(lambda line: ready.set())), daemon=True)
        worker.start()
        def finish():
            if worker.is_alive() and job.process:
                job.process.kill()
                worker.join(10)
        self.addCleanup(finish)
        self.assertTrue(ready.wait(10), 'Child process did not start')
        job.cancel()
        worker.join(10)
        self.assertFalse(worker.is_alive(), 'Cancellation did not stop the process')
        self.assertEqual(results[0]['status'], 'cancelled')

    def test_cancel_before_start_is_persisted(self):
        job = ScriptJob([sys.executable, '-c', 'raise RuntimeError()'], self.root, self.root)
        job.cancel()
        result = job.run()
        self.assertEqual(result['status'], 'cancelled')
        self.assertEqual(json.loads((job.folder / 'job.json').read_text())['status'], 'cancelled')

    @unittest.skipUnless(sys.platform == 'win32', 'Windows job object check')
    def test_windows_cancellation_stops_child_processes(self):
        import ctypes
        from ctypes import wintypes
        child_code = 'import time; time.sleep(60)'
        parent_code = ('import subprocess,sys,time; '
                       f'p=subprocess.Popen([sys.executable,"-c",{child_code!r}]); '
                       'print(p.pid,flush=True); time.sleep(60)')
        job = ScriptJob([sys.executable, '-u', '-c', parent_code], self.root, self.root)
        ready = threading.Event()
        pids, results = [], []
        def received(line):
            pids.append(int(line.strip()))
            ready.set()
        worker = threading.Thread(target=lambda: results.append(job.run(received)), daemon=True)
        worker.start()
        self.addCleanup(lambda: (job.cancel(), worker.join(10)))
        self.assertTrue(ready.wait(10))
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        kernel.WaitForSingleObject.restype = wintypes.DWORD
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x00100000, False, pids[0])
        self.assertTrue(handle)
        self.addCleanup(lambda: kernel.CloseHandle(handle))
        self.assertIsNotNone(job.windows_job, 'Process was not assigned to a Windows job object')
        job.cancel()
        worker.join(10)
        self.assertFalse(worker.is_alive())
        self.assertEqual(kernel.WaitForSingleObject(handle, 5000), 0, 'Child process survived cancellation')


if __name__ == '__main__':
    unittest.main()
