# YouTube Upload Automation

Upload videos to YouTube via the YouTube Data API v3.

## Setup

### 1. Install dependencies
```bash
pip install -r requirements.txt
```

### 2. Get Google API credentials
1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project or select an existing one
3. Enable **YouTube Data API v3**
4. Go to **APIs & Services** → **Credentials**
5. Create **OAuth 2.0 Client IDs** → Application type: **Desktop app**
6. Download the JSON file as `client_secret.json` (place in this folder)
7. Go to **OAuth consent screen** and add your email as a test user

### 3. Upload a video
```bash
python youtube_uploader.py \
  --video "path/to/video.mp4" \
  --title "Video Title" \
  --description "Video description" \
  --tags "tag1,tag2,tag3" \
  --privacy public
```

## Arguments

| Flag | Required | Description |
|------|----------|-------------|
| `--video` | Yes | Path to video file |
| `--title` | Yes | Video title |
| `--description` | No | Video description |
| `--tags` | No | Comma-separated tags |
| `--privacy` | No | `public`, `private`, or `unlisted` (default: public) |

## Notes
- First run will open a browser for OAuth2 authorization
- `token.pickle` is saved after first auth for future use
- `client_secret.json` must never be committed to git