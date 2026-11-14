import http.client
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest

from studio_server import StudioServer, StudioState


class DashboardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.state = StudioState(self.root)
        self.server = StudioServer(self.state)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)

    def close_server(self):
        if self.state.job:
            self.state.job.cancel()
            deadline = time.time() + 5
            while self.state.current['status'] in {'running', 'stopping'} and time.time() < deadline:
                time.sleep(.02)
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(5)

    def request(self, path, data=None, auth=True, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1', self.server.server_port, timeout=10)
        combined = {'X-Studio-Token': self.state.token} if auth else {}
        combined.update(headers or {})
        if data is not None:
            combined['Content-Type'] = 'application/json'
        connection.request('GET' if data is None else 'POST', path, None if data is None else json.dumps(data), combined)
        response = connection.getresponse()
        body = response.read()
        status = response.status
        connection.close()
        return status, body

    def test_loopback_and_session_protect_private_api(self):
        self.assertEqual(self.server.server_address[0], '127.0.0.1')
        self.assertEqual(self.request('/api/bootstrap', auth=False)[0], 403)
        self.assertEqual(self.request('/api/bootstrap')[0], 200)
        self.assertEqual(self.request('/api/start', {}, headers={'Origin': 'https://example.invalid'})[0], 403)
        self.assertEqual(self.request('/api/bootstrap', headers={'Host': 'example.invalid'})[0], 403)

    def test_static_page_does_not_expose_arbitrary_files(self):
        self.assertEqual(self.request('/', auth=False)[0], 200)
        self.assertEqual(self.request('/app.css', auth=False)[0], 200)
        self.assertNotEqual(self.request('/../script_manager.py', auth=False)[0], 200)
        self.assertNotEqual(self.request('/api/source?tool=../config/credentials')[0], 200)

    def test_one_click_starts_only_one_job_and_history_is_readable(self):
        script = self.root / 'worker.py'
        script.write_text('import time; print("fixture ready",flush=True); time.sleep(.35)')
        self.state.catalog['fixture'] = dict(id='fixture', title='Test job', script='worker.py', cwd='.', fields=[], args=[], runnable=True)
        payload = {'tool': 'fixture', 'values': {}, 'python': sys.executable}
        first, body = self.request('/api/start', payload)
        self.assertEqual(first, 200)
        self.assertEqual(self.request('/api/start', payload)[0], 400)
        deadline = time.time() + 10
        while self.state.snapshot()['job']['status'] == 'running' and time.time() < deadline:
            time.sleep(.03)
        self.assertEqual(self.state.snapshot()['job']['status'], 'completed')
        jobs = self.state.history()
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0]['title'], 'Test job')
        detail = self.state.job_detail(json.loads(body)['id'])
        self.assertIn('fixture ready', detail['log'])

    def test_cleaner_requires_preview_and_explicit_purge_confirmation(self):
        cache = self.root / 'tools/__pycache__/sample.pyc'
        cache.parent.mkdir(parents=True)
        cache.write_bytes(b'fixture')
        self.assertEqual(self.request('/api/cleaner/move', {'selected': ['source.py']})[0], 400)
        _, body = self.request('/api/cleaner/scan', {'days': 0})
        preview = json.loads(body)
        _, body = self.request('/api/cleaner/move', {'preview': preview['preview'], 'selected': [preview['items'][0]['relative']]})
        batch = json.loads(body)['batch']
        self.assertFalse(cache.exists())
        self.assertEqual(self.request('/api/cleaner/purge', {'batch': batch})[0], 400)
        self.assertEqual(self.request('/api/cleaner/restore', {'batch': batch})[0], 200)
        self.assertEqual(cache.read_bytes(), b'fixture')
        self.assertEqual(self.request('/api/cleaner/purge', {'batch': batch, 'confirm': True})[0], 200)

    def test_media_preview_requires_a_known_result_and_supports_seeking(self):
        video = self.root / 'runs/demo.mp4'
        video.parent.mkdir()
        video.write_bytes(b'0123456789')
        self.assertNotEqual(self.request('/media?path=runs/demo.mp4')[0], 200)
        self.state.allowed_media.add('runs/demo.mp4')
        status, body = self.request('/media?path=runs/demo.mp4', headers={'Range': 'bytes=2-5'})
        self.assertEqual(status, 206)
        self.assertEqual(body, b'2345')

    def test_cleanup_cannot_race_an_active_job(self):
        self.state.current = {'status': 'running'}
        self.assertEqual(self.request('/api/cleaner/scan', {'days': 0})[0], 400)
        self.state.current = None


if __name__ == '__main__':
    unittest.main()
