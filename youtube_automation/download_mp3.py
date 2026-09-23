"""
YouTube Audio Downloader (Original Quality)
Reads YouTube links from a file and downloads them in original quality.
Optionally trims leading/trailing silence from each file.

Requirements:
    pip install yt-dlp
    ffmpeg must be installed for MP3 conversion (optional)
    librosa + soundfile for silence trimming (optional)
"""

import os
import sys
import shutil
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


def trim_silence_from_file(filepath, output_dir=None, top_db=20):
    """
    Trim leading and trailing silence from an audio file using librosa.

    Args:
        filepath: Path to the audio file.
        output_dir: If provided, write trimmed file there (same filename, .wav).
                    If None, replace the original file in-place.
        top_db: Threshold in dB below the peak to consider as silence.

    Returns:
        Path to the trimmed file.
    """
    import librosa
    import soundfile as sf
    import numpy as np

    filepath = Path(filepath)
    if not filepath.exists():
        return filepath

    print(f"    Trimming silence from: {filepath.name}", flush=True)

    try:
        y, sr = librosa.load(str(filepath), sr=None, mono=False)
    except Exception as e:
        print(f"    [SKIP] Could not load for trimming: {e}")
        return filepath

    if y.ndim > 1:
        trimmed_channels = []
        for ch in range(y.shape[0]):
            yt, _ = librosa.effects.trim(y[ch], top_db=top_db)
            trimmed_channels.append(yt)
        min_len = min(len(t) for t in trimmed_channels)
        y_trimmed = np.column_stack([t[:min_len] for t in trimmed_channels])
    else:
        y_trimmed, _ = librosa.effects.trim(y, top_db=top_db)

    if output_dir:
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        out_path = output_dir / f"{filepath.stem}.wav"
    else:
        out_path = filepath.with_suffix(".wav")

    sf.write(str(out_path), y_trimmed, sr, format="WAV")

    original_size = filepath.stat().st_size
    trimmed_size = out_path.stat().st_size
    print(f"    [OK] {filepath.name} -> {out_path.name} "
          f"({original_size/1e6:.1f}MB -> {trimmed_size/1e6:.1f}MB)", flush=True)

    filepath.unlink(missing_ok=True)

    return out_path


def download_youtube_audio(
    links_file="youtube_links.txt",
    output_dir="downloads",
    convert_to_mp3=False,
    mp3_quality="320",
    trim_silence=False,
    top_db=20,
):
    """
    Download audio from YouTube links in original quality.

    Args:
        links_file: Path to file containing YouTube URLs (one per line)
        output_dir: Directory to save downloaded audio files
        convert_to_mp3: If True, convert to MP3. If False, keep original format.
        mp3_quality: MP3 bitrate in kbps (e.g., 128, 192, 320)
        trim_silence: If True, trim leading/trailing silence from each file.
        top_db: Silence threshold in dB (lower = more aggressive trimming).
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
    mode = "MP3 conversion (" + mp3_quality + "kbps)" if convert_to_mp3 else "Original quality (no conversion)"
    if trim_silence:
        mode += " + silence trim"
    print(f"Mode: {mode}\n")

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
            success_count += 1

            # Trim silence if requested
            if trim_silence:
                # Find the downloaded file for this URL
                # yt-dlp saves with %(title)s.%(ext)s pattern
                try:
                    import glob
                    # Get the most recently modified file in output_dir for this download
                    pattern = os.path.join(output_dir, "*")
                    files = [f for f in glob.glob(pattern) if os.path.isfile(f)]
                    if files:
                        # Find the most recently modified file
                        latest = max(files, key=os.path.getmtime)
                        if latest not in [f for f in glob.glob(os.path.join(output_dir, "*.wav"))]:
                            trimmed = trim_silence_from_file(latest, top_db=top_db)
                except Exception as e:
                    print(f"  [SKIP] Could not trim: {e}")

            print(f"[OK] SUCCESS: {url}")
        except Exception as e:
            print(f"[FAIL] FAILED: {url}")
            print(f"  Error: {e}")

    print(f"\n{'='*60}")
    print(f"Download complete: {success_count}/{len(links)} successful")
    print(f"Files saved to: {os.path.abspath(output_dir)}")
    print(f"{'='*60}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Download audio from YouTube links")
    parser.add_argument("--mp3", action="store_true", help="Convert to MP3 (requires ffmpeg)")
    parser.add_argument("--quality", default="320", help="MP3 bitrate (e.g., 128, 192, 320)")
    parser.add_argument("--trim", action="store_true", help="Trim leading/trailing silence from each file")
    parser.add_argument("--top-db", type=float, default=20, help="Silence threshold in dB (lower = more aggressive)")
    args = parser.parse_args()

    download_youtube_audio(
        convert_to_mp3=args.mp3,
        mp3_quality=args.quality,
        trim_silence=args.trim,
        top_db=args.top_db,
    )