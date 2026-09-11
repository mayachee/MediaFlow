# YouTube Audio/Video Script Collection

Automated tools for YouTube audio/video workflow:

1. **youtube_automation/** - Searches YouTube and saves links to `youtube_links.txt`
2. **download_mp3.py** - Downloads audio from those links as MP3/WebM
3. **music_video_generator/** - Combines audio files + images into a video (FFmpeg + librosa)
4. **automatic_YouTube_upload/** - Uploads final video to YouTube via Data API v3

## Quick Start

```bash
cd youtube_automation
python main.py                    # Search songs -> youtube_links.txt
python download_mp3.py            # Download audio files

cd ../music_video_generator
python main.py                    # Create music video (audio + images -> mp4)

cd ../automatic_YouTube_upload
python youtube_uploader.py --video ../music_video_generator/output/music_video.mp4 --title "My Video"
```

## Setup

Each subdirectory is self-contained with its own `requirements.txt`.

**Prerequisites:**
- Python 3.11+
- FFmpeg (`winget install ffmpeg` or `brew install ffmpeg`)
- Google Cloud credentials for YouTube upload (see `automatic_YouTube_upload/README.md`)