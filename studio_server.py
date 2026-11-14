"""Loopback-only web interface for the existing local script and cleaner backends."""
from collections import deque
import hmac
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import mimetypes
import os
from pathlib import Path
import re
import secrets
import subprocess
import sys
import threading
import time
from urllib.parse import parse_qs, urlsplit
import webbrowser

from tools.script_catalog import ROOT, ScriptJob, build_command, curated_tools, discover_scripts
from tools.workspace_cleaner import WorkspaceCleaner

UI = Path(__file__).resolve().parent / 'ui/studio'
JOB_ID = re.compile(r'^\d{8}-\d{6}-[a-f0-9]{8}$')
ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')


class StudioState:
    def __init__(self, root=ROOT):
        self.root = Path(root).resolve()
        self.guided = curated_tools()
        self.scripts = discover_scripts(self.root)
        self.catalog = {tool['id']: tool for tool in self.guided + self.scripts}
        self.cleaner = WorkspaceCleaner(self.root)
        self.token = secrets.token_urlsafe(32)
        self.lock = threading.RLock()
        self.picker_lock = threading.Lock()
        self.current = None
        self.logs = deque(maxlen=3000)
        self.sequence = 0
        self.job = None
        self.preview = None
        self.allowed_media = set()

    def command(self, data):
        if data.get('tool') not in self.catalog:
            raise ValueError('Choose an available tool.')
        extra = data.get('extra', [])
        if not isinstance(data.get('values', {}), dict):
            raise ValueError('Tool inputs must be an object.')
        if not isinstance(extra, list) or any(not isinstance(arg, str) for arg in extra):
            raise ValueError('Extra arguments must be a list of text values.')
        return build_command(self.catalog[data['tool']], data.get('values', {}), extra,
                             data.get('python') or sys.executable, self.root)

    def _artifacts(self, lines):
        result = {}
        prefixes = ['Video ready: ', 'Vertical video ready: ', 'Video saved to: ', 'Job saved to: ']
        for line in lines:
            line = ANSI.sub('', line).strip()
            for prefix in prefixes:
                if not line.startswith(prefix):
                    continue
                path = Path(line[len(prefix):].strip())
                if prefix == 'Job saved to: ':
                    candidates = [path / 'video/music_video.mp4', path / 'exports/master.wav']
                else:
                    candidates = [path]
                for path in candidates:
                    try:
                        relative = path.resolve().relative_to(self.root).as_posix()
                        if path.is_file() and path.suffix.lower() in {'.mp4', '.wav', '.mp3'}:
                            self.allowed_media.add(relative)
                            result[relative] = dict(path=relative, name=path.name)
                    except (OSError, ValueError):
                        continue
        return list(result.values())

    def start(self, data):
        with self.lock:
            if self.current and self.current['status'] in {'running', 'stopping'}:
                raise ValueError('A job is already running. Wait for it or stop it first.')
            command, cwd = self.command(data)
            tool = self.catalog[data['tool']]
            job = ScriptJob(command, cwd, root=self.root, console=bool(data.get('console')))
            self.job = job
            self.logs.clear()
            self.sequence = 0
            self.current = dict(id=job.folder.name, title=tool['title'], tool=tool['id'],
                                status='running', started=time.time(), folder=str(job.folder), artifacts=[])
            def line_received(line):
                with self.lock:
                    self.sequence += 1
                    self.logs.append((self.sequence, ANSI.sub('', line)))
                    artifacts = self._artifacts([line])
                    existing = {item['path']: item for item in self.current['artifacts']}
                    existing.update({item['path']: item for item in artifacts})
                    self.current['artifacts'] = list(existing.values())
            def worker():
                try:
                    result = job.run(line_received)
                    # Store a readable title in the existing manifest, preserving
                    # compatibility with the cleaner's completed-log category.
                    result.update(title=tool['title'], tool=tool['id'])
                    temporary = job.folder / 'job.tmp'
                    temporary.write_text(json.dumps(result, indent=2), encoding='utf-8')
                    temporary.replace(job.folder / 'job.json')
                except Exception as error:
                    result = dict(status='failed', error=str(error))
                    line_received(f'{error}\n')
                with self.lock:
                    self.current.update(status=result['status'], exit_code=result.get('exit_code'),
                                        error=result.get('error'), finished=time.time())
            threading.Thread(target=worker, daemon=True).start()
            return dict(self.current)

    def snapshot(self, since=0):
        with self.lock:
            return dict(job=dict(self.current) if self.current else None,
                        lines=[dict(sequence=seq, text=line) for seq, line in self.logs if seq > since],
                        sequence=self.sequence)

    def job_detail(self, job_id):
        if not JOB_ID.fullmatch(job_id):
            raise ValueError('Invalid job ID.')
        folder = (self.root / 'runs/script-manager' / job_id).resolve()
        folder.relative_to(self.root / 'runs/script-manager')
        document = json.loads((folder / 'job.json').read_text(encoding='utf-8'))
        log_file = folder / 'output.log'
        text = ''
        if log_file.is_file():
            with log_file.open('rb') as stream:
                stream.seek(max(0, log_file.stat().st_size - 500_000))
                text = stream.read().decode('utf-8', errors='replace')
        with self.lock:
            artifacts = self._artifacts(text.splitlines())
        return dict(id=job_id, title=document.get('title', 'Script job'), status=document['status'],
                    command=document['command'], folder=str(folder), log=ANSI.sub('', text), artifacts=artifacts)

    def history(self):
        result = []
        for path in sorted((self.root / 'runs/script-manager').glob('*/job.json'), reverse=True)[:100]:
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                command = data.get('command', [])
                title = data.get('title')
                if not title:
                    for tool in self.guided:
                        if tool['script'] and str(self.root / tool['script']) in command:
                            title = tool['title']
                            break
                result.append(dict(id=path.parent.name, title=title or 'Script job',
                                   status=data['status'], modified=path.stat().st_mtime))
            except (OSError, ValueError, KeyError):
                continue
        return result

    def cleanup(self, action, data):
        with self.lock:
            if self.current and self.current['status'] in {'running', 'stopping'}:
                raise ValueError('Finish or stop the current job before using the cleaner.')
            if action == 'scan':
                result = self.cleaner.scan(days=int(data.get('days', 7)), caches=data.get('caches', True), logs=data.get('logs', True))
                nonce = secrets.token_hex(12)
                self.preview = dict(id=nonce, items={item['relative']: item for item in result['items']})
                return dict(**result, preview=nonce)
            if action == 'move':
                if not self.preview or data.get('preview') != self.preview['id']:
                    raise ValueError('Scan again before moving files.')
                selected = data.get('selected', [])
                if not isinstance(selected, list) or any(key not in self.preview['items'] for key in selected):
                    raise ValueError('Choose only items from the cleanup preview.')
                result = self.cleaner.quarantine([self.preview['items'][key] for key in selected])
                self.preview = None
                return result
            if action == 'restore':
                return self.cleaner.restore(str(data.get('batch', '')))
            if action == 'purge':
                if data.get('confirm') is not True:
                    raise ValueError('Confirm permanent deletion of the selected trash batch.')
                return self.cleaner.purge(str(data.get('batch', '')))
            raise ValueError('Unknown cleaner operation.')


class StudioServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, state, port=0):
        self.state = state
        super().__init__(('127.0.0.1', port), Handler)
        self.origin = f'http://127.0.0.1:{self.server_port}'
        self.cookie_name = f'studio_{self.server_port}'


class Handler(BaseHTTPRequestHandler):
    def handle(self):
        try:
            super().handle()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            pass

    def log_message(self, *args):
        pass

    def authorized(self):
        token = self.headers.get('X-Studio-Token', '')
        cookie = SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            if not token and self.server.cookie_name in cookie:
                token = cookie[self.server.cookie_name].value
        except Exception:
            pass
        return hmac.compare_digest(token, self.server.state.token)

    def headers_for(self, code, mime, length):
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(length))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; media-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")

    def json(self, data, code=200):
        body = json.dumps(data).encode('utf-8')
        self.headers_for(code, 'application/json; charset=utf-8', len(body))
        if self.authorized():
            self.send_header('Set-Cookie', f'{self.server.cookie_name}={self.server.state.token}; HttpOnly; SameSite=Strict; Path=/')
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}':
            self.json({'error': 'Unexpected local host.'}, 403)
            return
        url = urlsplit(self.path)
        files = {'/': ('index.html', 'text/html'), '/app.css': ('app.css', 'text/css'), '/app.js': ('app.js', 'text/javascript')}
        if url.path in files:
            name, mime = files[url.path]
            body = (UI / name).read_bytes()
            self.headers_for(200, mime + '; charset=utf-8', len(body))
            self.end_headers()
            self.wfile.write(body)
            return
        if not self.authorized():
            self.json({'error': 'Open Studio using its launcher to connect.'}, 403)
            return
        query = parse_qs(url.query)
        state = self.server.state
        try:
            if url.path == '/api/bootstrap':
                self.json(dict(tools=state.guided, scripts=state.scripts, python=sys.executable))
            elif url.path == '/api/state':
                self.json(state.snapshot(int(query.get('since', ['0'])[0])))
            elif url.path == '/api/history':
                self.json(state.history())
            elif url.path == '/api/job':
                self.json(state.job_detail(query.get('id', [''])[0]))
            elif url.path == '/api/trash':
                self.json(state.cleaner.batches())
            elif url.path == '/api/source':
                tool = state.catalog.get(query.get('tool', [''])[0])
                if not tool or not tool['script']:
                    raise ValueError('Choose a source file.')
                path = (state.root / tool['script']).resolve()
                path.relative_to(state.root)
                self.json({'text': path.read_text(encoding='utf-8', errors='replace')})
            elif url.path == '/media':
                relative = query.get('path', [''])[0]
                if relative not in state.allowed_media:
                    raise ValueError('Choose a media result from a Studio job.')
                path = (state.root / relative).resolve()
                path.relative_to(state.root)
                size = path.stat().st_size
                start, end = 0, size - 1
                requested = self.headers.get('Range')
                if requested:
                    match = re.fullmatch(r'bytes=(\d+)-(\d*)', requested)
                    if not match:
                        raise ValueError('Unsupported media range.')
                    start = int(match[1])
                    end = min(int(match[2]) if match[2] else size - 1, size - 1)
                    if start > end:
                        self.send_error(416)
                        return
                self.headers_for(206 if requested else 200, mimetypes.guess_type(path.name)[0] or 'application/octet-stream', end - start + 1)
                self.send_header('Accept-Ranges', 'bytes')
                if requested:
                    self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
                self.end_headers()
                with path.open('rb') as stream:
                    stream.seek(start)
                    remaining = end - start + 1
                    while remaining:
                        chunk = stream.read(min(65536, remaining))
                        if not chunk:
                            break
                        self.wfile.write(chunk)
                        remaining -= len(chunk)
            else:
                self.json({'error': 'Not found'}, 404)
        except (OSError, ValueError, KeyError) as error:
            self.json({'error': str(error)}, 400)

    def do_POST(self):
        if self.headers.get('Host') != f'127.0.0.1:{self.server.server_port}' or self.headers.get('Origin', self.server.origin) != self.server.origin or not self.authorized():
            self.json({'error': 'This request is not from the local Studio session.'}, 403)
            return
        try:
            size = int(self.headers.get('Content-Length', 0))
            if size < 0 or size > 1_000_000:
                raise ValueError('Request is too large.')
            data = json.loads(self.rfile.read(size) or b'{}')
            if not isinstance(data, dict):
                raise ValueError('Expected a request object.')
            action = urlsplit(self.path).path.removeprefix('/api/')
            state = self.server.state
            if action == 'preview':
                command, cwd = state.command(data)
                result = dict(command=subprocess.list2cmdline(command), cwd=str(cwd))
            elif action == 'start':
                result = state.start(data)
            elif action == 'cancel':
                with state.lock:
                    if state.current and state.current['status'] == 'running':
                        state.current['status'] = 'stopping'
                        threading.Thread(target=state.job.cancel, daemon=True).start()
                result = dict(ok=True)
            elif action.startswith('cleaner/'):
                result = state.cleanup(action.split('/')[1], data)
            elif action == 'browse':
                kind = data.get('kind')
                if kind not in {'file', 'directory', 'newdirectory', 'savefile'}:
                    raise ValueError('Unsupported file picker.')
                with state.picker_lock:
                    picked = subprocess.run([sys.executable, str(ROOT / 'tools/studio_picker.py'), kind],
                        check=True, capture_output=True, text=True, encoding='utf-8',
                        env={**os.environ, 'PYTHONIOENCODING': 'utf-8'},
                        creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                result = json.loads(picked.stdout)
            elif action == 'open-folder':
                path = Path(data.get('path', str(state.root / 'runs'))).resolve()
                if not path.is_dir():
                    raise ValueError('Output folder has not been created yet.')
                if os.name == 'nt':
                    os.startfile(str(path))
                else:
                    subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', str(path)])
                result = dict(ok=True)
            elif action == 'quit':
                with state.lock:
                    if state.current and state.current['status'] in {'running', 'stopping'}:
                        raise ValueError('Finish or stop the current job before quitting.')
                result = dict(ok=True)
                threading.Thread(target=self.server.shutdown, daemon=True).start()
            else:
                raise ValueError('Unknown operation.')
            self.json(result)
        except (OSError, ValueError, KeyError, TypeError, subprocess.CalledProcessError) as error:
            self.json({'error': str(error)}, 400)


def serve(port=0, open_browser=True):
    server = StudioServer(StudioState(), port)
    url = server.origin + '/#token=' + server.state.token
    print('Scripts Studio is running on ' + server.origin, flush=True)
    if open_browser:
        webbrowser.open(url)
    else:
        print(url, flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        if server.state.job:
            server.state.job.cancel()
    finally:
        server.server_close()


if __name__ == '__main__':
    serve()
