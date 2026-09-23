# YouTube Automation

Search YouTube, extract video links, and download audio files automatically.

## Quick Start

### Windows (PowerShell)
```powershell
.\run.ps1 install      # First time: setup venv + install dependencies
.\run.ps1 search       # Search YouTube using input.txt -> youtube_links.txt
.\run.ps1 download     # Download audio from youtube_links.txt -> downloads/
.\run.ps1 download-trim  # Download + trim leading/trailing silence
.\run.ps1 metadata     # Generate AI-powered titles & descriptions -> metadata.json
.\run.ps1 all          # Run search + download in one command
.\run.ps1 clean        # Remove generated files
```

### Linux/macOS (Makefile)
```bash
make install           # First time: setup venv + install dependencies
make search            # Search YouTube using input.txt -> youtube_links.txt
make download          # Download MP3 from youtube_links.txt -> downloads/
make metadata          # Generate AI-powered titles & descriptions -> metadata.json
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
| `download_mp3.py` | Downloads audio from links in `youtube_links.txt` with optional silence trimming |
| `generate_metadata.py` | Generates AI-powered titles & descriptions from songs |
| `requirements.txt` | Python dependencies |
| `youtube_links.txt` | Output: YouTube URLs (auto-generated) |
| `metadata.json` | Output: AI-generated metadata (JSON) |
| `metadata.txt` | Output: AI-generated metadata (readable) |
| `downloads/` | Output: Downloaded MP3 files |

## How It Works

1. `main.py` reads song names from `input.txt`
2. Searches YouTube via Playwright (headless Chromium)
3. Extracts the first video URL for each song
4. Saves URLs to `youtube_links.txt`
5. `generate_metadata.py` uses an AI model (OpenAI API) to generate
   SEO-optimized YouTube titles, descriptions, and tags for each song
6. `download_mp3.py` uses yt-dlp to download each video's audio
7. Files are saved to `downloads/`

## Silence Trimming

Remove leading/trailing silence from downloaded audio files (e.g., intro/outro
silence from YouTube videos):

```powershell
.\run.ps1 download-trim    # Download + trim in one step
# Or:
python download_mp3.py --trim
# Adjust sensitivity:
python download_mp3.py --trim --top-db 15   # More aggressive (default: 20)
```

Uses `librosa` to detect silence and trim it. Output is saved as `.wav`.

## AI Metadata Generator

Generate SEO-optimized YouTube titles and descriptions for every song using an AI model.
Works with any OpenAI-compatible API endpoint.

### Prerequisites

- An OpenAI-compatible API key (`OPENAI_API_KEY`)
- Optionally set `OPENAI_API_BASE` for custom endpoints

### Free Options (no credit card required)

**Option 1 — OpenRouter (free tier, 200+ requests/day):**
1. Sign up at [openrouter.ai/keys](https://openrouter.ai/keys) (no credit card)
2. Copy your API key
3. Edit `.env` and set `OPENAI_API_KEY`, `OPENAI_API_BASE=https://openrouter.ai/api/v1`, `OPENAI_MODEL=openrouter/free`

**Option 2 — Ollama (100% local, no internet):**
1. Install [Ollama](https://ollama.com/download)
2. Run `ollama run llama3` (or any model)
3. Edit `.env` and set:
   ```
   OPENAI_API_KEY=ollama
   OPENAI_API_BASE=http://localhost:11434/v1
   OPENAI_MODEL=llama3
   ```

### Usage

```powershell
# Generate metadata for songs in input.txt (uses .env automatically)
.\run.ps1 metadata

# Or run directly
python generate_metadata.py
python generate_metadata.py --model gpt-4o          # Specify a different model
python generate_metadata.py --input songs.txt       # Custom input file
python generate_metadata.py --output results.json   # Custom output file
```

Output:
- `metadata.json` — structured JSON with title, description, and tags per song
- `metadata.txt` — human-readable formatted text