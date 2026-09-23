# YouTube Audio/Video Script Collection

Automated tools for YouTube audio/video workflow:

1. **youtube_automation/** - Searches YouTube and saves links to `youtube_links.txt`
2. **download_mp3.py** - Downloads audio from those links as MP3/WebM
3. **generate_metadata.py** - AI-powered YouTube titles & descriptions (optional)
4. **music_video_generator/** - Combines audio files + images into a video (FFmpeg + librosa)
5. **automatic_YouTube_upload/** - Uploads final video to YouTube via Data API v3

## Quick Start

### Full pipeline (one command)

#### Linux/macOS
```bash
make setup                                                                       # Install all dependencies
make all                                                                         # Search -> Download -> Metadata -> Copy -> Generate -> Upload
```

#### Windows PowerShell
```powershell
.\run.ps1 setup                                                                  # Install all dependencies
.\run.ps1 all                                                                    # Search -> Download -> Metadata -> Copy -> Generate -> Upload
```

### Individual steps

| Command | Linux/macOS | Windows |
|---------|-------------|---------|
| Setup | `make setup` | `.\run.ps1 setup` |
| Search YouTube | `make search` | `.\run.ps1 search` |
| Download audio | `make download` | `.\run.ps1 download` |
| Download + trim | `make download-trim` | `.\run.ps1 download-trim` |
| **Generate AI metadata** | `make metadata` | `.\run.ps1 metadata` |
| Copy downloads | `make copy` | `.\run.ps1 copy` |
| Generate video | `make generate` | `.\run.ps1 generate` |
| Upload to YouTube | `make upload` | `.\run.ps1 upload` |
| Clean outputs | `make clean` | `.\run.ps1 clean` |

### One-command pipeline

```bash
make full    # Linux/macOS — runs everything with smart fallbacks
```
```powershell
.\run.ps1 full   # Windows — runs everything with smart fallbacks
```

**`run_all.py`** handles the complete pipeline automatically:
1. Searches YouTube (falls back to yt-dlp if Playwright fails)
2. Downloads audio from all links
3. Generates AI-powered titles/descriptions (`metadata.json`)
4. Copies audio + downloads thumbnails to video generator
5. Generates the music video (FFmpeg)
6. Uploads to YouTube (prompts for OAuth in browser)

## Setup

Each subdirectory is self-contained with its own `requirements.txt`.

**Prerequisites:**
- Python 3.11+
- FFmpeg (`winget install ffmpeg` or `brew install ffmpeg`)
- Google Cloud credentials for YouTube upload (see `automatic_YouTube_upload/README.md`)
https://console.cloud.google.com/
https://github.com/GyanD/media-autobuild_suite