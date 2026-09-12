# YouTube Automation

Search YouTube, extract video links, and download audio files automatically.

## Quick Start

### Windows (PowerShell)
```powershell
.\run.ps1 install      # First time: setup venv + install dependencies
.\run.ps1 search       # Search YouTube using input.txt -> youtube_links.txt
.\run.ps1 download     # Download MP3 from youtube_links.txt -> downloads/
.\run.ps1 all          # Run search + download in one command
.\run.ps1 clean        # Remove generated files
```

### Linux/macOS (Makefile)
```bash
make install           # First time: setup venv + install dependencies
make search            # Search YouTube using input.txt -> youtube_links.txt
make download          # Download MP3 from youtube_links.txt -> downloads/
make all               # Run search + download in one command
make clean             # Remove generated files
```

## Prerequisites

- **Python 3.11+**
- **FFmpeg** (for audio conversion)
  - Windows: `winget install ffmpeg`
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg`
- **Playwright browsers** (installed automatically by `install`)

## Files

| File | Description |
|------|-------------|
| `input.txt` | Song names to search for (one per line) |
| `main.py` | Searches YouTube and saves links to `youtube_links.txt` |
| `download_mp3.py` | Downloads audio from links in `youtube_links.txt` |
| `requirements.txt` | Python dependencies |
| `youtube_links.txt` | Output: YouTube URLs (auto-generated) |
| `downloads/` | Output: Downloaded MP3 files |

## How It Works

1. `main.py` reads song names from `input.txt`
2. Searches YouTube via Playwright (headless Chromium)
3. Extracts the first video URL for each song
4. Saves URLs to `youtube_links.txt`
5. `download_mp3.py` uses yt-dlp to download each video as MP3
6. Files are saved to `downloads/`