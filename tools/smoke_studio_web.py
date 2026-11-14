"""Check the dashboard in headless Chrome; cleanup actions use disposable fixtures."""
import json
from pathlib import Path
import sys
import subprocess
import tempfile
import threading
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from studio_server import StudioServer, StudioState
from tools.workspace_cleaner import WorkspaceCleaner


def main():
    from playwright.sync_api import sync_playwright
    output = ROOT / 'runs/studio-ui-review' / uuid.uuid4().hex[:8]
    output.mkdir(parents=True)
    errors = []
    with tempfile.TemporaryDirectory() as temporary:
        fixture = Path(temporary)
        cache = fixture / 'tools/__pycache__/fixture.pyc'
        cache.parent.mkdir(parents=True)
        cache.write_bytes(b'cache fixture' * 100)
        state = StudioState()
        fixture_video = output / 'source.mp4'
        subprocess.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=green:s=160x90:r=10:d=1',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', str(fixture_video)], check=True)
        original = state.catalog['clips-auto']
        state.catalog['clips-auto'] = dict(original, script='tests/fixtures/clip_search_runner.py',
            args=original['args'] + ['--fixture-video', str(fixture_video), '--fixture-output', str(output / 'clip-search')])
        state.cleaner = WorkspaceCleaner(fixture)
        server = StudioServer(state)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(executable_path='C:/Program Files/Google/Chrome/Application/chrome.exe', headless=True)
                page = browser.new_page(viewport={'width': 1440, 'height': 1050}, device_scale_factor=1, reduced_motion='reduce')
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(server.origin + '/#token=' + state.token)
                page.get_by_role('heading', name='Your next video starts here.').wait_for()
                assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                page.screenshot(path=str(output / 'overview.png'), full_page=True)
                page.get_by_role('button', name='Create a video', exact=True).click()
                page.locator('[data-field="audio"]').wait_for()
                assert not page.locator('#extra').is_visible()
                page.locator('[data-field="preview_seconds"]').fill('12')
                page.locator('[data-field="preset"]').select_option('master')
                assert not page.locator('[data-field="images"]').is_visible()
                assert page.locator('[data-field="preview_seconds"]').input_value() == ''
                page.get_by_role('button', name='Export WAV master', exact=True).wait_for()
                page.locator('[data-field="preset"]').select_option('preview')
                page.screenshot(path=str(output / 'create-video.png'), full_page=True)
                page.get_by_role('button', name='YouTube & Shorts', exact=True).click()
                assert page.locator('[data-field="ratio"]').input_value() == '16:9'
                assert page.locator('[data-field="resolution"]').input_value() == '1080p'
                assert not page.locator('[data-field="frame_skip"]').is_visible()
                page.screenshot(path=str(output / 'youtube.png'), full_page=True)
                page.get_by_role('button', name='Find & download clips', exact=True).click()
                page.locator('[data-field="title"]').fill('forest mountains sunrise')
                page.locator('[data-field="download_top"]').fill('2')
                assert not page.locator('[data-field="audio"]').is_visible()
                page.screenshot(path=str(output / 'find-download-form.png'), full_page=True)
                page.get_by_role('button', name='Find & download', exact=True).click()
                page.get_by_role('heading', name='2 clips downloaded', exact=True).wait_for(timeout=60000)
                report = json.loads((output / 'clip-search/candidates.json').read_text())
                assert report['title'] == 'forest mountains sunrise'
                assert report['audio'] is None
                page.screenshot(path=str(output / 'downloaded-clips.png'), full_page=True)
                page.get_by_role('button', name='Use clips in a music video', exact=True).click()
                visuals = page.locator('[data-field="images"]').input_value()
                assert len(list(Path(visuals).glob('*.mp4'))) == 2
                assert state.current['tool'] == 'clips-auto'
                page.get_by_role('button', name='Workspace cleaner', exact=True).click()
                page.locator('#clean-days').fill('0')
                page.locator('#scan-cleaner').click()
                page.locator('[data-clean-index="0"]').wait_for()
                page.screenshot(path=str(output / 'cleaner.png'), full_page=True)
                page.locator('#move-cleaner').click()
                page.locator('#toast').filter(has_text='Studio Trash').wait_for()
                assert not cache.exists()
                page.locator('#trash-tab').click()
                page.get_by_role('button', name='Restore', exact=True).click()
                page.locator('#toast').filter(has_text='restored').wait_for()
                assert cache.read_bytes() == b'cache fixture' * 100
                page.get_by_role('button', name='Script explorer', exact=True).click()
                page.locator('#script-search').fill('audio_analyzer.py')
                assert page.get_by_text('Shared code · view only', exact=True).count() == 1
                page.get_by_role('button', name='View source', exact=True).click()
                page.locator('#source-code').wait_for()
                page.locator('#close-modal').click()
                page.locator('#global-search').fill('Run offline clip tests')
                page.locator('.tool-card').click()
                page.locator('.run-tool').click()
                page.get_by_text('Your result is ready.', exact=True).wait_for(timeout=60000)
                assert state.current['status'] == 'completed'
                media_checked = False
                for job in state.history()[:20]:
                    detail = state.job_detail(job['id'])
                    if not any(a['path'].endswith('.mp4') for a in detail['artifacts']):
                        continue
                    page.evaluate('(id) => jobModal(id)', job['id'])
                    video = page.locator('#modal video')
                    video.wait_for()
                    width = video.evaluate('(v) => v.readyState >= 1 ? Promise.resolve(v.videoWidth) : new Promise((resolve,reject) => {v.onloadedmetadata=()=>resolve(v.videoWidth);v.onerror=()=>reject(new Error("Media preview failed"));})')
                    assert width > 0
                    page.screenshot(path=str(output / 'video-result.png'), full_page=True)
                    page.locator('#close-modal').click()
                    media_checked = True
                    break
                for width in [1024, 390]:
                    page.set_viewport_size({'width': width, 'height': 900})
                    if width == 390:
                        page.locator('#menu').click()
                    page.get_by_role('button', name='Overview', exact=True).click()
                    assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
                    page.screenshot(path=str(output / f'overview-{width}.png'), full_page=True)
                assert not errors, errors
                browser.close()
            result = dict(status='passed', checks=['dashboard', 'progressive forms', 'YouTube defaults',
                'cleaner preview/move/restore in temporary fixture', 'source explorer',
                'title-only search/download with offline provider fixture', 'downloaded clip previews and creator handoff',
                'real offline clip test job', 'responsive layouts', 'no browser exceptions'], media_preview=media_checked, screenshots=str(output))
            (output / 'result.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
            print(json.dumps(result, indent=2))
        finally:
            if state.job and state.current['status'] in {'running', 'stopping'}:
                state.job.cancel()
            server.shutdown()
            server.server_close()
            thread.join(5)


if __name__ == '__main__':
    main()
