"""
YouTube Audio Downloader (Original Quality)
Reads YouTube links from a file and downloads them in original quality.

Requirements:
    pip install yt-dlp
    ffmpeg must be installed for MP3 conversion (optional)
"""

import os
import sys
from pathlib import Path

import yt_dlp


def check_ffmpeg():
    """Check if ffmpeg is available in PATH."""
    import shutil
    if shutil.which("ffmpeg"):
        return True
    # Check common Windows installation paths
    common_paths = [
        r"C:\Program Files\DownloadHelper CoApp",
        r"C:\Program Files\ffmpeg",
        r"C:\Program Files (x86)\ffmpeg",
    ]
    for path in common_paths:
        if Path(path).exists():
            os.environ["PATH"] = os.environ["PATH"] + os.pathsep + path
            return True
    return False


def download_youtube_audio(
    links_file="youtube_links.txt",
    output_dir="downloads",
    convert_to_mp3=False,
    mp3_quality="320",
):
    """
    Download audio from YouTube links in original quality.

    Args:
        links_file: Path to file containing YouTube URLs (one per line)
        output_dir: Directory to save downloaded audio files
        convert_to_mp3: If True, convert to MP3. If False, keep original format.
        mp3_quality: MP3 bitrate in kbps (e.g., 128, 192, 320)
    """
    # Check ffmpeg if MP3 conversion is requested
    if convert_to_mp3 and not check_ffmpeg():
        print("ERROR: ffmpeg is not installed or not in PATH.")
        print("\nInstall ffmpeg:")
        print("  Windows: winget install ffmpeg")
        print("  Or download from: https://ffmpeg.org/download.html")
        print("  Mac: brew install ffmpeg")
        print("  Linux: sudo apt install ffmpeg")
        sys.exit(1)

    # Create output directory
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    # Read links
    links_path = Path(links_file)
    if not links_path.exists():
        print(f"ERROR: {links_file} not found")
        sys.exit(1)

    with open(links_path, "r", encoding="utf-8") as f:
        links = [line.strip() for line in f if line.strip()]

    if not links:
        print(f"No links found in {links_file}")
        return

    print(f"Found {len(links)} link(s) to download")
    print(f"Output directory: {os.path.abspath(output_dir)}")
    print(f"Mode: {'MP3 conversion (' + mp3_quality + 'kbps)' if convert_to_mp3 else 'Original quality (no conversion)'}\n")

    # yt-dlp options
    ydl_opts = {
        "format": "bestaudio/best",  # Best available audio quality
        "outtmpl": os.path.join(output_dir, "%(title)s.%(ext)s"),
        "noplaylist": True,  # Download only the single video, not the playlist
        "quiet": False,
        "no_warnings": False,
        "ignoreerrors": True,
    }

    # Add MP3 postprocessor only if conversion is requested
    if convert_to_mp3:
        ydl_opts["postprocessors"] = [
            {
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": mp3_quality,
            }
        ]

    success_count = 0
    for idx, url in enumerate(links, 1):
        print(f"\n{'='*60}")
        print(f"[{idx}/{len(links)}] Downloading: {url}")
        print(f"{'='*60}")
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])
            print(f"[OK] SUCCESS: {url}")
            success_count += 1
        except Exception as e:
            print(f"[FAIL] FAILED: {url}")
            print(f"  Error: {e}")

    print(f"\n{'='*60}")
    print(f"Download complete: {success_count}/{len(links)} successful")
    print(f"Files saved to: {os.path.abspath(output_dir)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    # Download in original quality (no MP3 conversion)
    download_youtube_audio(convert_to_mp3=False)