#!/usr/bin/env python3
"""
Full Pipeline Runner
Runs the complete YouTube music video automation pipeline in one command:

  1. Search YouTube for song links (with yt-dlp fallback)
  2. Download audio files
  3. Generate AI-powered metadata (OpenRouter free model)
  4. Copy audio + download thumbnails to music_video_generator
  5. Generate music video (FFmpeg)
  6. Upload to YouTube (with OAuth)

Usage:
    python run_all.py [--skip-upload] [--skip-video] [--max-songs N]

Environment:
    Uses .env in youtube_automation/ for OPENAI_API_KEY (OpenRouter free key)
    Uses ffmpeg from PATH or common install locations.
"""

import os
import sys
import json
import shutil
import subprocess
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent
YOUTUBE_DIR = ROOT / "youtube_automation"
MVG_DIR = ROOT / "music_video_generator"
UPLOADER_DIR = ROOT / "automatic_YouTube_upload"

# Add ffmpeg to PATH if found in common locations
for ffmpeg_path in [
    r"C:\Program Files\DownloadHelper Coapp",
    r"C:\Program Files\ffmpeg\bin",
    r"C:\Program Files\ffmpeg",
]:
    if Path(ffmpeg_path).exists():
        os.environ["PATH"] = ffmpeg_path + os.pathsep + os.environ.get("PATH", "")
        break


def log(step, msg, status="INFO"):
    print(f"[{step}] {status}: {msg}", flush=True)


def run(cmd, cwd=None, env=None):
    """Run a command and stream output."""
    result = subprocess.run(cmd, cwd=cwd, env=env, shell=True)
    return result.returncode == 0


def search_songs():
    """Step 1: Search YouTube for song links."""
    log("SEARCH", "Searching YouTube for songs...")

    # Try the Playwright-based search first
    result = subprocess.run(
        [sys.executable, str(YOUTUBE_DIR / "main.py")],
        cwd=str(YOUTUBE_DIR),
        capture_output=True,
        text=True,
        timeout=90,
    )
    if result.returncode == 0:
        log("SEARCH", "Found links via Playwright")

    # Verify we have links for all songs
    links_path = YOUTUBE_DIR / "youtube_links.txt"
    if not links_path.exists():
        log("SEARCH", "youtube_links.txt not found, using yt-dlp fallback", "WARN")
        return False

    input_path = YOUTUBE_DIR / "input.txt"
    with open(input_path, encoding="utf-8") as f:
        songs = [line.strip() for line in f if line.strip()]

    with open(links_path, encoding="utf-8") as f:
        links = [line.strip() for line in f if line.strip()]

    missing = len(songs) - len(links)
    if missing > 0:
        log("SEARCH", f"{missing} song(s) missing, using yt-dlp fallback", "WARN")
        import yt_dlp

        found_links = list(links)
        for song in songs:
            query = song.replace(" – ", " ").replace(" — ", " ").replace(" - ", " ")
            try:
                ydl = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True})
                info = ydl.extract_info(f"ytsearch1:{query}", download=False)
                if "entries" in info and info["entries"]:
                    url = f"https://www.youtube.com/watch?v={info['entries'][0]['id']}"
                    found_links.append(url)
                    log("SEARCH", f"Found via yt-dlp: {query}")
            except Exception as e:
                log("SEARCH", f"Could not find: {query} ({e})", "ERROR")

        with open(links_path, "w", encoding="utf-8") as f:
            f.write("\n".join(found_links) + "\n")

    log("SEARCH", f"Done. {len(links)} links in youtube_links.txt")
    return True


def download_audio():
    """Step 2: Download audio files."""
    log("DOWNLOAD", "Downloading audio files...")
    success = run([sys.executable, "download_mp3.py"], cwd=str(YOUTUBE_DIR))
    downloads_dir = YOUTUBE_DIR / "downloads"
    if downloads_dir.exists():
        files = list(downloads_dir.glob("*.webm")) + list(downloads_dir.glob("*.mp3"))
        log("DOWNLOAD", f"{len(files)} files downloaded to downloads/")
    return success


def generate_metadata():
    """Step 3: Generate AI-powered metadata."""
    log("METADATA", "Generating AI metadata...")

    # Load .env
    env_path = YOUTUBE_DIR / ".env"
    if env_path.exists():
        for line in env_path:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                value = value.strip().strip('"').strip("'")
                if value and not value.startswith("your-"):
                    os.environ.setdefault(key.strip(), value)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key or api_key.startswith("your-"):
        log("METADATA", "OPENAI_API_KEY not set. Skipping AI metadata.", "WARN")
        log("METADATA", "Get a free key at https://openrouter.ai/keys")
        return False

    success = run([sys.executable, "generate_metadata.py"], cwd=str(YOUTUBE_DIR))
    if success:
        log("METADATA", "metadata.json and metadata.txt generated")
    return success


def copy_to_video_generator():
    """Step 4: Copy audio + download thumbnails to music_video_generator."""
    log("COPY", "Preparing music_video_generator inputs...")

    audio_input = MVG_DIR / "input" / "audio"
    images_input = MVG_DIR / "input" / "images"
    downloads_dir = YOUTUBE_DIR / "downloads"

    audio_input.mkdir(parents=True, exist_ok=True)
    images_input.mkdir(parents=True, exist_ok=True)

    # Copy audio files
    audio_files = list(downloads_dir.glob("*.webm")) + list(downloads_dir.glob("*.mp3"))
    for f in audio_files:
        dest = audio_input / f.name
        shutil.copy2(f, dest)
        log("COPY", f"Audio: {f.name}")

    # Download thumbnails as images
    import yt_dlp

    metadata_path = YOUTUBE_DIR / "metadata.json"
    metadata = []
    if metadata_path.exists():
        with open(metadata_path, encoding="utf-8") as f:
            metadata = json.load(f)

    links_path = YOUTUBE_DIR / "youtube_links.txt"
    if links_path.exists():
        with open(links_path, encoding="utf-8") as f:
            links = [line.strip() for line in f if line.strip()]
        for i, url in enumerate(links):
            try:
                ydl = yt_dlp.YoutubeDL({"quiet": True, "no_warnings": True})
                info = ydl.extract_info(url, download=False)
                thumb_url = info.get("thumbnail")
                if thumb_url:
                    import urllib.request
                    ext = "jpg"
                    if "webp" in thumb_url:
                        ext = "webp"
                    thumb_path = images_input / f"thumb_{i:03d}.{ext}"
                    urllib.request.urlretrieve(thumb_url, thumb_path)
                    log("COPY", f"Thumbnail: thumb_{i:03d}.{ext}")
            except Exception as e:
                log("COPY", f"Could not download thumbnail: {e}", "WARN")

    log("COPY", "Done preparing inputs")
    return True


def generate_video(max_songs=4):
    """Step 5: Generate music video."""
    log("GENERATE", "Generating music video...")

    # Check for images
    images_dir = MVG_DIR / "input" / "images"
    image_files = list(images_dir.glob("*.jpg")) + list(images_dir.glob("*.png")) + list(images_dir.glob("*.webp"))
    if not image_files:
        log("GENERATE", "No images found. Skipping video generation.", "WARN")
        return False

    # Check for audio
    audio_dir = MVG_DIR / "input" / "audio"
    audio_files = list(audio_dir.glob("*.webm")) + list(audio_dir.glob("*.mp3"))
    if not audio_files:
        log("GENERATE", "No audio files found. Skipping video generation.", "WARN")
        return False

    cmd = [sys.executable, "main.py", "--max-songs", str(max_songs)]
    success = run(cmd, cwd=str(MVG_DIR))
    if success:
        video_path = MVG_DIR / "output" / "music_video.mp4"
        if video_path.exists():
            size_mb = video_path.stat().st_size / 1e6
            log("GENERATE", f"Video created: {video_path.name} ({size_mb:.1f} MB)")
    return success


def upload_video():
    """Step 6: Upload to YouTube."""
    log("UPLOAD", "Uploading to YouTube...")

    video_path = MVG_DIR / "output" / "music_video.mp4"
    if not video_path.exists():
        log("UPLOAD", "Video file not found. Run with --skip-upload to generate first.", "ERROR")
        return False

    metadata_path = YOUTUBE_DIR / "metadata.json"
    metadata_arg = f"--metadata {metadata_path}" if metadata_path.exists() else ""

    cmd = f'{sys.executable} -u youtube_uploader.py --video "{video_path}" --privacy public'
    if metadata_path.exists():
        cmd += f' --metadata "{metadata_path}"'

    log("UPLOAD", "Starting OAuth (check browser for authorization)...")
    success = run(cmd, cwd=str(UPLOADER_DIR))
    if success:
        log("UPLOAD", "Upload complete!")
    else:
        log("UPLOAD", "Upload may have failed. Check OAuth and retry.", "WARN")
    return success


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Run the full YouTube music video pipeline")
    parser.add_argument("--skip-search", action="store_true", help="Skip YouTube search")
    parser.add_argument("--skip-download", action="store_true", help="Skip audio download")
    parser.add_argument("--skip-metadata", action="store_true", help="Skip AI metadata generation")
    parser.add_argument("--skip-video", action="store_true", help="Skip video generation")
    parser.add_argument("--skip-upload", action="store_true", help="Skip YouTube upload")
    parser.add_argument("--max-songs", type=int, default=4, help="Max songs per video")
    args = parser.parse_args()

    log("PIPELINE", "=" * 50)
    log("PIPELINE", "Full YouTube Music Video Pipeline")
    log("PIPELINE", "=" * 50)

    if not args.skip_search:
        search_songs()
    else:
        log("PIPELINE", "Skipping search")

    if not args.skip_download:
        download_audio()
    else:
        log("PIPELINE", "Skipping download")

    if not args.skip_metadata:
        generate_metadata()
    else:
        log("PIPELINE", "Skipping metadata")

    if not args.skip_video:
        copy_to_video_generator()
        generate_video(args.max_songs)
    else:
        log("PIPELINE", "Skipping copy + video generation")

    if not args.skip_upload:
        upload_video()
    else:
        log("PIPELINE", "Skipping upload")

    log("PIPELINE", "Pipeline finished!")


if __name__ == "__main__":
    main()
