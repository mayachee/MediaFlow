# YouTube Audio/Video Script Collection

Automated tools for YouTube audio/video workflow:

1. **youtube_automation/** - Searches YouTube and saves links to `youtube_links.txt`
2. **download_mp3.py** - Downloads audio from those links as MP3/WebM
3. **music_video_generator/** - Combines audio files + images into a video (FFmpeg + librosa)
4. **automatic_YouTube_upload/** - Uploads final video to YouTube via Data API v3

## Quick Start

### Full pipeline (one command)

#### Linux/macOS
```bash
make setup                                                                       # Install all dependencies
make all                                                                         # Search -> Download -> Generate -> Upload
```

#### Windows PowerShell
```powershell
.\run.ps1 setup                                                                  # Install all dependencies
.\run.ps1 all                                                                    # Search -> Download -> Generate -> Upload
```

### Individual steps

| Command | Linux/macOS | Windows |
|---------|-------------|---------|
| Setup | `make setup` | `.\run.ps1 setup` |
| Search YouTube | `make search` | `.\run.ps1 search` |
| Download audio | `make download` | `.\run.ps1 download` |
| Generate video | `make generate` | `.\run.ps1 generate` |
| Upload to YouTube | `make upload` | `.\run.ps1 upload` |
| Clean outputs | `make clean` | `.\run.ps1 clean` |

## Setup

Each subdirectory is self-contained with its own `requirements.txt`.

**Prerequisites:**
- Python 3.11+
- FFmpeg (`winget install ffmpeg` or `brew install ffmpeg`)
- Google Cloud credentials for YouTube upload (see `automatic_YouTube_upload/README.md`)
https://console.cloud.google.com/
https://github.com/GyanD/media-autobuild_suite