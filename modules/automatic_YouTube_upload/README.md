# YouTube Upload Automation

Upload videos to YouTube with auto-generated professional metadata.

## Quick Start

### Windows (PowerShell)
```powershell
.\run.ps1 install            # First time: install dependencies
.\run.ps1 upload              # Upload video with auto-title/description
.\run.ps1 upload-thumb <ID> <IMAGE>  # Upload thumbnail to existing video
.\run.ps1 clean              # Remove token.pickle and logs
```

### Linux/macOS (Makefile)
```bash
make install                  # Install dependencies
make upload                   # Upload video to YouTube
make upload-thumbnail VIDEO_ID=abc123 THUMBNAIL=thumb.jpg  # Upload thumbnail only
make clean                    # Remove token and logs
```

## Prerequisites

- **Python 3.11+**
- **Google Cloud credentials** (required)
- **FFmpeg** (for thumbnail processing, if using non-standard formats)

### Google Cloud Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a project or select an existing one
3. Enable **YouTube Data API v3**:
   - **APIs & Services** → **Library** → Search "YouTube Data API v3" → **Enable**
4. Create OAuth credentials:
   - **APIs & Services** → **Credentials** → **Create Credentials** → **OAuth client ID**
   - Application type: **Desktop app**
   - Download JSON → save as `client_secret.json`
5. Configure OAuth consent screen:
   - **APIs & Services** → **OAuth consent screen**
   - Add your Gmail address under **Test users**
   - Click **Publish App**

## Files

| File | Description |
|------|-------------|
| `client_secret.json` | Google OAuth credentials (keep secret) |
| `token.pickle` | Auth token (auto-generated, keeps secret) |
| `youtube_uploader.py` | Main upload script |

## Usage

### Full Upload (auto-generated metadata)
```powershell
python youtube_uploader.py --video "path/to/video.mp4"
```
Auto-generates title/description from the video filename.

### Custom Upload
```powershell
python youtube_uploader.py \
    --video "path/to/video.mp4" \
    --title "My Title" \
    --description "My description" \
    --tags "music,lyrics" \
    --privacy public
```

### Thumbnail-Only Upload
```powershell
python youtube_uploader.py --video-id abc123 --thumbnail "thumb.jpg"
```

## Options

| Flag | Required | Description |
|------|----------|-------------|
| `--video` | Yes (unless `--video-id`) | Path to video file |
| `--video-id` | Yes (if no `--video`) | YouTube video ID for thumbnail-only |
| `--thumbnail` | No | Custom thumbnail path |
| `--title` | No | Custom title (auto-generated if omitted) |
| `--description` | No | Custom description (auto-generated if omitted) |
| `--tags` | No | Comma-separated tags |
| `--privacy` | No | `public`, `private`, or `unlisted` (default: public) |

## Notes

- First run opens a browser for OAuth2 authorization
- `token.pickle` is saved after first auth for future use
- `client_secret.json` must never be committed to git (in `.gitignore`)
- Auto-generated title/description based on song filenames
- Thumbnail auto-selected from `input/images/` if not specified