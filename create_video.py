"""Choose audio and visuals in a desktop window, or render from the command line."""
import argparse
import json
import math
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading

ROOT = Path(__file__).resolve().parent
DEFAULT_VISUALS = ROOT / 'modules/music_video_generator/input/images'


def render_environment():
    # Keep analysis caches in the project, including on restricted installations.
    cache = ROOT / 'runs/.cache/numba'
    cache.mkdir(parents=True, exist_ok=True)
    return {**os.environ, 'PYTHONIOENCODING': 'utf-8', 'PYTHONUNBUFFERED': '1',
            'NUMBA_CACHE_DIR': str(cache)}


def build_command(audio, visuals=DEFAULT_VISUALS, timeline=None, preset='preview', start=0, seconds=15):
    audio = Path(audio).expanduser().resolve()
    if not audio.is_file() or audio.suffix.lower() not in {'.mp3', '.wav', '.flac', '.m4a', '.ogg', '.aac', '.mp4', '.webm'}:
        raise ValueError('Choose an existing audio file (MP3, WAV, FLAC, M4A, OGG, AAC, MP4 or WebM).')
    if preset not in {'preview', 'video'}:
        raise ValueError('Choose preview or video.')
    command = [sys.executable, '-u', str(ROOT / 'workflow.py'), '--audio', str(audio),
               '--preset', preset, '--normalize', 'off']
    if timeline:
        path = Path(timeline).expanduser().resolve()
        if not path.is_file():
            raise ValueError('Choose an existing exported timeline.')
        command += ['--timeline', str(path)]
    else:
        folder = Path(visuals).expanduser().resolve()
        extensions = {'.jpg', '.jpeg', '.png', '.webp', '.bmp', '.mp4', '.mov', '.mkv', '.webm'}
        if not folder.is_dir() or not any(p.is_file() and p.suffix.lower() in extensions for p in folder.iterdir()):
            raise ValueError('Choose a folder containing photos or video clips, or select an exported timeline.')
        command += ['--images', str(folder)]
    if preset == 'preview':
        start, seconds = float(start), float(seconds)
        if not math.isfinite(start) or start < 0 or not math.isfinite(seconds) or seconds <= 0:
            raise ValueError('Preview start must be zero or greater; duration must be positive.')
        command += ['--preview-start', str(start), '--preview-seconds', str(seconds)]
    return command


def desktop():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk
    from tkinter.scrolledtext import ScrolledText

    window = tk.Tk()
    window.title('Music Video Creator')
    window.geometry('820x640')
    window.minsize(650, 500)
    panel = ttk.Frame(window, padding=18)
    panel.pack(fill='both', expand=True)
    panel.columnconfigure(1, weight=1)
    ttk.Label(panel, text='Create a video from your music', font=('Segoe UI', 18)).grid(
        row=0, column=0, columnspan=3, sticky='w', pady=(0, 12))
    ttk.Label(panel, text='Choose your song and footage. Start with a short preview.').grid(
        row=1, column=0, columnspan=3, sticky='w', pady=(0, 12))
    audio, visuals, timeline = tk.StringVar(), tk.StringVar(value=str(DEFAULT_VISUALS)), tk.StringVar()

    def browse(variable, folder=False, audio_file=False):
        if folder:
            chosen = filedialog.askdirectory(parent=window, title='Choose photos and clips folder')
        else:
            filters = [('Audio', '*.mp3 *.wav *.flac *.m4a *.ogg *.aac *.mp4 *.webm')] if audio_file else [
                ('Timeline', '*.json *.yaml *.yml')]
            chosen = filedialog.askopenfilename(parent=window, filetypes=filters + [('All files', '*.*')])
        if chosen:
            variable.set(chosen)

    for row, label, variable, folder, audio_file in [
        (2, 'Audio file', audio, False, True),
        (3, 'Photos / clips folder', visuals, True, False),
        (4, 'Timeline (optional)', timeline, False, False),
    ]:
        ttk.Label(panel, text=label).grid(row=row, column=0, sticky='w', padx=(0, 10), pady=5)
        ttk.Entry(panel, textvariable=variable).grid(row=row, column=1, sticky='ew', pady=5)
        ttk.Button(panel, text='Browse', command=lambda v=variable, f=folder, a=audio_file: browse(v, f, a)).grid(
            row=row, column=2, padx=(8, 0), pady=5)
    ttk.Label(panel, text='A timeline uses your reviewed highlights instead of the folder above.').grid(
        row=5, column=0, columnspan=3, sticky='w', pady=5)
    options = ttk.Frame(panel)
    options.grid(row=6, column=0, columnspan=3, sticky='w', pady=12)
    preset = tk.StringVar(value='preview')
    ttk.Radiobutton(options, text='480p preview', variable=preset, value='preview').pack(side='left')
    ttk.Radiobutton(options, text='1080p full song', variable=preset, value='video').pack(side='left', padx=12)
    start, seconds = tk.StringVar(value='0'), tk.StringVar(value='15')
    for label, variable in [('Preview start (s)', start), ('Length (s)', seconds)]:
        ttk.Label(options, text=label).pack(side='left', padx=(8, 4))
        ttk.Entry(options, textvariable=variable, width=6).pack(side='left')
    status = tk.StringVar(value='Ready. Audio normalization is off.')
    ttk.Label(panel, textvariable=status, wraplength=740).grid(row=8, column=0, columnspan=3, sticky='w', pady=8)
    logs = ScrolledText(panel, height=14, wrap='word', state='disabled')
    logs.grid(row=9, column=0, columnspan=3, sticky='nsew')
    panel.rowconfigure(9, weight=1)
    messages = queue.Queue()
    state = {'running': False, 'job': None}

    def worker(command):
        try:
            # Argument lists preserve paths with spaces and apostrophes.
            with subprocess.Popen(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                  text=True, encoding='utf-8', errors='replace',
                                  env=render_environment()) as process:
                job = None
                for line in process.stdout:
                    messages.put(('log', line))
                    if line.startswith('Job saved to: '):
                        job = Path(line.removeprefix('Job saved to: ').strip())
                code = process.wait()
                if code:
                    raise RuntimeError('Rendering failed. See the log for details.')
                if job is None or not (job / 'video/music_video.mp4').is_file():
                    raise RuntimeError('The renderer returned without a video. See the log for details.')
                messages.put(('done', job))
        except Exception as error:
            messages.put(('error', str(error)))

    def generate():
        try:
            if not audio.get().strip():
                raise ValueError('Choose your audio file first.')
            command = build_command(audio.get(), visuals.get(), timeline.get().strip() or None,
                                    preset.get(), start.get(), seconds.get())
        except (ValueError, OSError) as error:
            messagebox.showerror('Check your selection', str(error), parent=window)
            return
        state.update(running=True, job=None)
        generate_button.config(state='disabled')
        open_button.config(state='disabled')
        logs.config(state='normal')
        logs.delete('1.0', 'end')
        logs.config(state='disabled')
        status.set('Creating video. Progress appears below; long songs can take several minutes.')
        threading.Thread(target=worker, args=(command,), daemon=True).start()

    def poll():
        # Limit each batch so verbose renders cannot block the window.
        for _ in range(150):
            try:
                kind, value = messages.get_nowait()
            except queue.Empty:
                break
            if kind == 'log':
                logs.config(state='normal')
                logs.insert('end', value)
                logs.see('end')
                logs.config(state='disabled')
            else:
                state['running'] = False
                generate_button.config(state='normal')
                if kind == 'done':
                    state['job'] = value
                    status.set(f'Video ready: {value / "video/music_video.mp4"}')
                    open_button.config(state='normal')
                else:
                    status.set(value)
                    messagebox.showerror('Video could not be created', value, parent=window)
        window.after(100, poll)

    def open_output():
        path = str(state['job'] / 'video')
        if sys.platform == 'win32':
            os.startfile(path)
        else:
            subprocess.Popen(['open' if sys.platform == 'darwin' else 'xdg-open', path])

    def close():
        if state['running']:
            messagebox.showinfo('Video is rendering', 'Wait for the render to finish before closing this window.', parent=window)
        else:
            window.destroy()

    buttons = ttk.Frame(panel)
    buttons.grid(row=7, column=0, columnspan=3, sticky='w')
    generate_button = ttk.Button(buttons, text='Create video', command=generate)
    generate_button.pack(side='left')
    open_button = ttk.Button(buttons, text='Open output folder', command=open_output, state='disabled')
    open_button.pack(side='left', padx=10)
    window.protocol('WM_DELETE_WINDOW', close)
    window.after(100, poll)
    window.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audio', type=Path, help='Omit to open the desktop window')
    parser.add_argument('--visuals', type=Path, default=DEFAULT_VISUALS)
    parser.add_argument('--timeline', type=Path)
    parser.add_argument('--preset', choices=['preview', 'video'], default='preview')
    parser.add_argument('--start', type=float, default=0)
    parser.add_argument('--seconds', type=float, default=15)
    parser.add_argument('--dry-run', action='store_true', help='Validate selections and print arguments without rendering')
    args = parser.parse_args()
    if not args.audio:
        if len(sys.argv) > 1:
            parser.error('Supply --audio for command-line use; use no arguments to open the window.')
        desktop()
        return 0
    try:
        command = build_command(args.audio, args.visuals, args.timeline, args.preset, args.start, args.seconds)
        if args.dry_run:
            # Escapes also work in older Windows consoles with a non-UTF-8 encoding.
            print(json.dumps(command, ensure_ascii=True, indent=2))
            return 0
        return subprocess.run(command, cwd=ROOT, env=render_environment()).returncode
    except (ValueError, OSError) as error:
        parser.error(str(error))


if __name__ == '__main__':
    sys.exit(main())
