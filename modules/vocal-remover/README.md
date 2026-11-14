# vocal-remover

Split songs into **instrumental** and **vocals** stems using [demucs](https://github.com/facebookresearch/demucs).

Takes a YouTube URL, a video, or an audio file and produces two files per track:
`output/instrumental/<track>.mp3` and `output/vocals/<track>.mp3`.

## Quick start

```powershell
cd vocal-remover

.\run.ps1 install                    # one-time setup: .venv with torch (CPU) + demucs
.\run.ps1 local                      # newest file in ..\automatic_upload\downloads
.\run.ps1 local "track.mp4"          # a specific file
.\run.ps1 url "https://youtu.be/..."  # download, then split
.\run.ps1 help
```

Or with GNU make (if `make` is on your PATH):

```bash
make install
make local
make local FILE="track.mp4"
make download      # runs ..\automatic_upload\run.ps1 download
make track         # download, then split
make clean
```

## Requirements

| Tool | Why | Install |
| --- | --- | --- |
| Python 3.9+ | venv + demucs | `winget install Python.Python.3.11` |
| ffmpeg | audio conversion | `winget install Gyan.FFmpeg` |
| yt-dlp | only for `url` / `download` | `pip install -U yt-dlp` |
| GNU make | only if you prefer make targets | `choco install make` |

CPU-only is fine. Expect roughly **2x the track duration** in wall time
(about 14 minutes for a 7:30 song on CPU).

## Layout

```
vocal-remover/
├── run.ps1                  entry point (install / local / url / download / track / clean)
├── Makefile                 same targets for GNU make
├── requirements.txt         pinned dependencies
├── scripts/
│   ├── remove_vocals.ps1      download a URL, then split
│   └── remove_vocals_local.ps1  split a local file
├── work/                    scratch space (temporary wav + demucs output, auto-cleaned)
└── output/
    ├── instrumental/        <track>.mp3 + <track>.wav
    └── vocals/              <track>.mp3 + <track>.wav
```

`work/` and `input/` are disposable. `output/` holds the results.

## Models

Passed with `-Model <name>` (or `make local MODEL=<name>`):

| Model | Notes |
| --- | --- |
| `htdemucs` | default, best general quality |
| `htdemucs_ft` | fine-tuned, slightly better on vocals |
| `htdemucs_6s` | six stems instead of two |
| `mdx_extra` / `mdx_extra_q` | alternate model family |

`--two-stems=vocals` is always used, so you get exactly two outputs.

## Troubleshooting

**`Missing venv`** - run `.\run.ps1 install`.

**`ffmpeg not found on PATH`** - install ffmpeg and open a new terminal.

**`ExecutionPolicy` blocks run.ps1** - once per user:
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`

**Poor separation** - try `-Model htdemucs_ft`, or cut the track into shorter
segments first; long heavy-mix tracks separate worse.
