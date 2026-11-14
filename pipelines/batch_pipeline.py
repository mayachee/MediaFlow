#!/usr/bin/env python3
"""
Batch Music Video Generator & YouTube Uploader

Features:
- Reads 93 songs from input.txt and divides them into batches of 3 songs (31 videos).
- Downloads audio for each song using yt-dlp.
- Randomly assigns 3 distinct images per video (1 per song).
- Renders video with FFmpeg.
- Uploads to YouTube with title, description (with timestamps), tags, and custom thumbnail.
- DIRECTLY DELETES the generated video file upon successful upload to save disk space.
- Progress tracking in batch_progress.json allows resuming if interrupted or if API quota is reached.
"""

import os
import sys
import json
import hashlib
import time
import random
import logging
import argparse
import subprocess
from pathlib import Path
from typing import List, Dict, Any, Optional

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("BatchPipeline")

ROOT_DIR = Path(__file__).resolve().parents[1]

# Add directories to sys.path
sys.path.insert(0, str(ROOT_DIR / "modules/music_video_generator"))
sys.path.insert(0, str(ROOT_DIR / "modules/music_video_generator" / "src"))
sys.path.insert(0, str(ROOT_DIR / "modules/automatic_YouTube_upload"))

from src.utils import load_config, ensure_output_dir
from src.audio_analyzer import AudioAnalyzer
from src.video_generator import VideoGenerator, Scene
import youtube_uploader


def load_song_titles(input_file: Path) -> List[str]:
    """Read non-empty song titles from input file."""
    if not input_file.exists():
        raise FileNotFoundError(f"Input file not found: {input_file}")
    with open(input_file, "r", encoding="utf-8") as f:
        songs = [line.strip() for line in f if line.strip()]
    return songs


def get_available_images(images_dir: Path) -> List[Path]:
    """Find all image files in the directory."""
    extensions = [".jpg", ".jpeg", ".png", ".webp", ".bmp"]
    images = []
    for ext in extensions:
        images.extend(images_dir.glob(f"*{ext}"))
        images.extend(images_dir.glob(f"*{ext.upper()}"))
    return sorted(list(set(images)))


def download_song_audio(song_title: str, cache_dir: Path) -> Path:
    """Download audio for a song using yt-dlp, cached by song title."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    # Sanitize title for filename
    safe_title = "".join(c if c.isalnum() or c in (" ", "-", "_") else "_" for c in song_title).strip()
    safe_title = safe_title[:80]
    expected_output = cache_dir / f"{safe_title}.mp3"

    if expected_output.exists() and expected_output.stat().st_size > 50000:
        logger.info(f"Using cached audio for: {song_title}")
        return expected_output

    logger.info(f"Downloading audio for: {song_title}")
    out_template = str(cache_dir / f"{safe_title}.%(ext)s")

    cmd = [
        "yt-dlp",
        "--js-runtimes", "node",
        "--no-playlist",
        "-x",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "-o", out_template,
        f"ytsearch1:{song_title}",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        logger.warning(f"Download warning for '{song_title}': {result.stderr}")
        # Try without --js-runtimes if failed
        cmd_fallback = [
            "yt-dlp",
            "--no-playlist",
            "-x",
            "--audio-format", "mp3",
            "--audio-quality", "0",
            "-o", out_template,
            f"ytsearch1:{song_title}",
        ]
        res_fb = subprocess.run(cmd_fallback, capture_output=True, text=True)
        if res_fb.returncode != 0:
            raise RuntimeError(f"Failed to download audio for '{song_title}': {res_fb.stderr}")

    if not expected_output.exists():
        # Check if file has another audio extension
        matches = list(cache_dir.glob(f"{safe_title}.*"))
        if matches:
            return matches[0]
        raise FileNotFoundError(f"Audio file not found after download for: {song_title}")

    return expected_output


def format_timestamp(seconds: float) -> str:
    """Format seconds into MM:SS format."""
    mins = int(seconds // 60)
    secs = int(seconds % 60)
    return f"{mins:02d}:{secs:02d}"


def generate_batch_video(
    batch_num: int,
    songs: List[str],
    audio_paths: List[Path],
    images: List[Path],
    output_dir: Path,
    config: Dict[str, Any],
) -> Path:
    """Generate a video combining 3 songs and 3 images."""
    logger.info(f"\n--- Generating Video for Batch {batch_num} (3 songs) ---")
    analyzer = AudioAnalyzer(detect_beats=False)
    
    # Analyze individual audio files
    file_infos = []
    total_duration = 0.0
    for path in audio_paths:
        duration, _, _ = analyzer.analyze(str(path))
        file_infos.append({
            "path": path,
            "duration": duration,
            "start_time": total_duration,
        })
        total_duration += duration

    logger.info(f"Total video duration: {total_duration:.1f}s ({format_timestamp(total_duration)})")

    # Combine audio files into one
    temp_dir = output_dir / f"temp_batch_{batch_num:02d}"
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    combined_audio = temp_dir / "combined_audio.wav"
    generator = VideoGenerator(config)
    generator.concatenate_audio_files(audio_paths, combined_audio)

    # Create scenes (1 scene per song)
    scenes = []
    for i, (info, img) in enumerate(zip(file_infos, images)):
        scene_output = temp_dir / f"scene_{i:02d}.mp4"
        scenes.append(Scene(
            source_path=img,
            start_time=info["start_time"],
            duration=info["duration"],
            output_file=scene_output,
        ))

    # Render scene videos
    scene_files = []
    for i, scene in enumerate(scenes):
        logger.info(f"Rendering scene {i+1}/{len(scenes)} ({scene.duration:.1f}s) with image: {scene.source_path.name}")
        generator.generate_scene_video(scene)
        scene_files.append(scene.output_file)

    # Concatenate scenes with combined audio
    final_output = output_dir / f"batch_video_{batch_num:02d}.mp4"
    logger.info(f"Combining scenes into final video: {final_output.name}")
    generator.concatenate_videos(
        scene_files=scene_files,
        output_file=final_output,
        audio_file=combined_audio,
    )

    # Cleanup temporary scene and combined audio files
    for sf in scene_files:
        if sf.exists():
            sf.unlink()
        png_temp = sf.with_suffix(".png")
        if png_temp.exists():
            png_temp.unlink()
    if combined_audio.exists():
        combined_audio.unlink()
    if temp_dir.exists():
        try:
            temp_dir.rmdir()
        except Exception:
            pass

    return final_output


def build_metadata(
    batch_num: int,
    songs: List[str],
    file_infos: List[Dict[str, Any]],
    ai_metadata: Optional[Dict[str, Dict]] = None,
) -> Dict[str, Any]:
    """Generate title, description with timestamps, and tags."""
    clean_titles = [youtube_uploader.parse_song_title(s) for s in songs]
    ai_metadata = ai_metadata or {}

    # Title: Use AI title of the first song if available, otherwise combine
    first_song = songs[0] if songs else ""
    first_ai = ai_metadata.get(first_song)
    if first_ai and first_ai.get("status") == "success":
        title = first_ai.get("youtube_title", "")
        if not title or len(title) > 95:
            title_short = " • ".join(clean_titles)
            title = f"Top Hits Playlist #{batch_num} | {clean_titles[0]} & More" if len(title_short) > 95 else title_short
    else:
        title_short = " • ".join(clean_titles)
        if len(title_short) > 95:
            title = f"Top Hits Playlist #{batch_num} | {clean_titles[0]} & More"
        else:
            title = title_short

    # Description with timestamps and AI-generated content
    desc_lines = [
        f"Enjoy this 3-song music playlist (Part #{batch_num})!",
        "",
        "Tracklist & Timestamps:",
    ]
    for i, (song, info) in enumerate(zip(clean_titles, file_infos), 1):
        ts = format_timestamp(info["start_time"])
        desc_lines.append(f"  {ts} - {song}")
        # Include AI-generated description snippet for each song
        ai_entry = ai_metadata.get(song)
        if ai_entry and ai_entry.get("status") == "success":
            ai_desc = ai_entry.get("description", "")
            if ai_desc:
                snippet = " ".join(ai_desc.split()[:30])
                if len(ai_desc.split()) > 30:
                    snippet += "..."
                desc_lines.append(f"    {snippet}")
        desc_lines.append("")

    desc_lines.extend([
        "Like, comment, and subscribe for more music!",
        "Turn on notifications to never miss a new upload.",
        "",
        "#Music #Playlist #Hits #TopSongs",
    ])
    description = "\n".join(desc_lines)

    # Tags: Combine AI-generated tags from all songs
    all_tags = set()
    for song in songs:
        ai_entry = ai_metadata.get(song)
        if ai_entry and ai_entry.get("status") == "success":
            for tag in ai_entry.get("tags", []):
                all_tags.add(tag)
    # Merge with auto-generated tags (deduplicated, max 30)
    auto_tags = youtube_uploader.auto_generate_tags(clean_titles)
    tags = list(all_tags)
    for tag in auto_tags:
        if tag not in all_tags and len(tags) < 30:
            tags.append(tag)
    if len(tags) > 30:
        tags = tags[:30]

    return {
        "title": title,
        "description": description,
        "tags": tags,
    }


def load_ai_metadata(metadata_path: Path) -> Dict[str, Dict]:
    """Load AI-generated metadata from metadata.json, keyed by song string."""
    if not metadata_path.exists():
        logger.warning(f"AI metadata file not found: {metadata_path}")
        return {}

    try:
        with open(metadata_path, "r", encoding="utf-8") as f:
            entries = json.load(f)
        ai_metadata = {}
        for entry in entries:
            song = entry.get("song", "")
            if song:
                ai_metadata[song] = entry
        logger.info(f"Loaded AI metadata for {len(ai_metadata)} song(s) from {metadata_path.name}")
        return ai_metadata
    except Exception as e:
        logger.warning(f"Could not load AI metadata: {e}")
        return {}


def main():
    parser = argparse.ArgumentParser(description="Batch Music Video Generator & YouTube Uploader")
    parser.add_argument("--input", default=str(ROOT_DIR / "modules/automatic_upload" / "input.txt"), help="Path to input.txt")
    parser.add_argument("--images-dir", default=str(ROOT_DIR / "modules/music_video_generator" / "input" / "images"), help="Images folder")
    parser.add_argument("--privacy", default="public", choices=["public", "private", "unlisted"], help="Upload privacy status")
    parser.add_argument("--skip-upload", action="store_true", help="Generate videos without uploading")
    parser.add_argument("--start-batch", type=int, default=1, help="Start at batch number (1-based)")
    parser.add_argument("--max-batches", type=int, default=31, help="Maximum number of batches to process")
    parser.add_argument("--shuffle", action="store_true", help="Randomize the 93 songs before batching")
    parser.add_argument("--keep-videos", action="store_true", help="Do NOT delete videos after uploading")
    args = parser.parse_args()

    input_file = Path(args.input)
    images_dir = Path(args.images_dir)
    output_dir = ROOT_DIR / "modules/music_video_generator" / "output"
    cache_dir = ROOT_DIR / "modules/automatic_upload" / "downloads" / "cache"
    progress_file = ROOT_DIR / "batch_progress.json"
    metadata_path = ROOT_DIR / "modules/automatic_upload" / "metadata.json"

    # Load songs
    songs = load_song_titles(input_file)
    logger.info(f"Loaded {len(songs)} songs from {input_file.name}")

    if args.shuffle:
        logger.info("Randomizing song order as requested...")
        random.seed(42)
        random.shuffle(songs)

    # Group into batches of 3
    batches = [songs[i : i + 3] for i in range(0, len(songs), 3)]
    logger.info(f"Divided {len(songs)} songs into {len(batches)} batches (3 songs per video)")

    # Load images
    all_images = get_available_images(images_dir)
    if not all_images:
        logger.error(f"No images found in {images_dir}")
        sys.exit(1)
    logger.info(f"Found {len(all_images)} images in {images_dir.name}")

    # Load config
    config_path = ROOT_DIR / "modules/music_video_generator" / "config.yaml"
    config = load_config(str(config_path))
    ensure_output_dir(output_dir)

     # Load existing progress
    progress = {}
    if progress_file.exists():
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                progress = json.load(f)
            logger.info(f"Loaded progress: {len(progress)} batches already completed.")
        except Exception as e:
            logger.warning(f"Could not load progress file: {e}")

    # Load AI-generated metadata (title, description, tags) from metadata.json
    ai_metadata = load_ai_metadata(metadata_path)

    # Authenticate YouTube service upfront if uploading is enabled
    youtube = None
    if not args.skip_upload:
        logger.info("Checking YouTube authentication...")
        try:
            youtube = youtube_uploader.get_authenticated_service()
            logger.info("YouTube authenticated successfully!")
        except Exception as e:
            logger.error(f"YouTube authentication failed: {e}")
            logger.error("Please complete Google OAuth sign-in first.")
            sys.exit(1)

    # Process batches
    completed_count = 0
    for idx, batch_songs in enumerate(batches, start=1):
        if idx < args.start_batch:
            continue
        if completed_count >= args.max_batches:
            break

        # Resume identity must follow the songs, not their mutable list position.
        identity = hashlib.sha256(json.dumps(batch_songs, ensure_ascii=False).encode('utf-8')).hexdigest()[:16]
        batch_key = f"batch_{identity}"
        if batch_key in progress and progress[batch_key].get("status") == "uploaded":
            logger.info(f"Skipping {batch_key} (already uploaded: {progress[batch_key].get('video_id')})")
            continue

        logger.info(f"\n{'='*70}")
        logger.info(f"Processing Batch {idx}/{len(batches)}")
        for s_idx, song in enumerate(batch_songs, 1):
            logger.info(f"  Song {s_idx}: {song}")
        logger.info(f"{'='*70}")

        # 1. Download audio for the 3 songs
        audio_paths = []
        try:
            for song in batch_songs:
                audio_path = download_song_audio(song, cache_dir)
                audio_paths.append(audio_path)
        except Exception as e:
            logger.error(f"Failed to download songs for batch {idx}: {e}")
            continue

        # 2. Pick 3 random images
        if len(all_images) >= len(batch_songs):
            selected_images = random.sample(all_images, len(batch_songs))
        else:
            selected_images = random.choices(all_images, k=len(batch_songs))

        logger.info(f"Selected 3 random images for batch {idx}:")
        for img in selected_images:
            logger.info(f"  - {img.name}")

        # 3. Calculate timing and metadata
        analyzer = AudioAnalyzer(detect_beats=False)
        file_infos = []
        curr_offset = 0.0
        for a_path in audio_paths:
            dur, _, _ = analyzer.analyze(str(a_path))
            file_infos.append({"path": a_path, "duration": dur, "start_time": curr_offset})
            curr_offset += dur

        metadata = build_metadata(idx, batch_songs, file_infos, ai_metadata)

        # 4. Generate video
        try:
            video_file = generate_batch_video(
                batch_num=idx,
                songs=batch_songs,
                audio_paths=audio_paths,
                images=selected_images,
                output_dir=output_dir,
                config=config,
            )
        except Exception as e:
            logger.error(f"Failed to generate video for batch {idx}: {e}")
            continue

        # 5. Upload to YouTube
        if not args.skip_upload and youtube:
            thumbnail_path = str(selected_images[0])
            logger.info(f"Uploading Batch {idx} to YouTube (Privacy: {args.privacy})...")
            logger.info(f"Title: {metadata['title']}")
            
            try:
                video_id = youtube_uploader.upload_video(
                    youtube=youtube,
                    video_path=str(video_file),
                    title=metadata["title"],
                    description=metadata["description"],
                    tags=metadata["tags"],
                    privacy=args.privacy,
                    thumbnail_path=thumbnail_path,
                )
                logger.info(f"[SUCCESS] Batch {idx} uploaded! URL: https://youtu.be/{video_id}")

                # Save progress
                progress[batch_key] = {
                    "status": "uploaded",
                    "video_id": video_id,
                    "url": f"https://youtu.be/{video_id}",
                    "songs": batch_songs,
                    "uploaded_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                }
                temporary_progress = progress_file.with_suffix('.tmp')
                with open(temporary_progress, "w", encoding="utf-8") as pf:
                    json.dump(progress, pf, indent=2)
                temporary_progress.replace(progress_file)

                # Cleanup only after the upload record is durable.
                if not args.keep_videos and video_file.exists():
                    video_file.unlink()

                completed_count += 1

            except Exception as e:
                err_str = str(e)
                logger.error(f"[ERROR] Failed to upload Batch {idx}: {err_str}")
                if "quotaExceeded" in err_str:
                    logger.warning("\nYouTube API Daily Quota Exceeded (10,000 units limit per day).")
                    logger.warning("The video file has been saved. You can resume tomorrow!")
                    break
                else:
                    logger.warning(f"Video file preserved at {video_file} for retry.")
        else:
            logger.info(f"Batch {idx} generated successfully at {video_file} (upload skipped).")
            completed_count += 1

    logger.info("\n" + "="*70)
    logger.info(f"Batch processing run finished. Completed batches: {completed_count}")
    logger.info("="*70)


if __name__ == "__main__":
    main()
