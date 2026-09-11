#!/usr/bin/env python3
"""
Music Video Generator
Main entry point for generating music videos from images and audio.
"""

import sys
import logging
from pathlib import Path
from typing import List, Optional

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent / "src"))

from src.utils import (
    load_config,
    ensure_output_dir,
    get_input_files,
    setup_logging,
)
from src.audio_analyzer import AudioAnalyzer
from src.video_generator import VideoGenerator, Scene

logger = logging.getLogger(__name__)


def select_audio_files(audio_dir: Path, max_songs: int = 4) -> List[Path]:
    """Select audio files from directory for playlist."""
    audio_files = get_input_files(audio_dir, [".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm"])
    
    if not audio_files:
        logger.warning(f"No audio files found in {audio_dir}")
        return []
    
    if len(audio_files) == 1:
        return audio_files[:1]
    
    logger.info(f"Found {len(audio_files)} audio files, selecting up to {max_songs}")
    return audio_files[:max_songs]


def select_images(images_dir: Path, count: int) -> List[Path]:
    """Select and distribute images across video duration."""
    image_files = get_input_files(images_dir, [".jpg", ".jpeg", ".png", ".bmp", ".webp"])
    
    if not image_files:
        logger.error(f"No images found in {images_dir}")
        sys.exit(1)
    
    logger.info(f"Found {len(image_files)} images")
    
    # If we have more images than needed, select evenly spaced ones
    if len(image_files) > count:
        step = len(image_files) / count
        selected = []
        for i in range(count):
            idx = int(i * step)
            selected.append(image_files[idx % len(image_files)])
        return selected
    
    # If we have fewer images, repeat them
    if len(image_files) < count:
        repeated = []
        while len(repeated) < count:
            repeated.extend(image_files)
        return repeated[:count]
    
    return image_files


def create_scenes(
    images: List[Path],
    duration: float,
    default_duration: float = 4.0,
    beat_times: Optional[List[float]] = None,
) -> List[Scene]:
    """Create scene list from images and timing information."""
    scenes = []
    
    if beat_times and len(beat_times) >= len(images):
        # Use beat-synced timing
        step = len(beat_times) // len(images)
        for i, img in enumerate(images):
            start_idx = min(i * step, len(beat_times) - 1)
            start_time = beat_times[start_idx]
            
            if i < len(images) - 1:
                end_idx = min((i + 1) * step, len(beat_times) - 1)
                end_time = beat_times[end_idx]
            else:
                end_time = duration
            
            scene_duration = max(end_time - start_time, 1.0)
            
            scenes.append(Scene(
                image_path=img,
                start_time=start_time,
                duration=scene_duration,
                output_file=Path(f"temp_scene_{i:03d}.mp4"),
            ))
    else:
        # Use equal duration for each image
        duration_per_image = duration / len(images)
        for i, img in enumerate(images):
            scenes.append(Scene(
                image_path=img,
                start_time=i * duration_per_image,
                duration=duration_per_image,
                output_file=Path(f"temp_scene_{i:03d}.mp4"),
            ))
    
    return scenes


def main():
    """Main function to generate music video."""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate music videos from images and audio"
    )
    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to configuration file",
    )
    parser.add_argument(
        "--output",
        help="Output file path (overrides config)",
    )
    parser.add_argument(
        "--no-beat-sync",
        action="store_true",
        help="Disable beat synchronization",
    )
    parser.add_argument(
        "--mp3",
        action="store_true",
        help="Convert audio to MP3",
    )
    parser.add_argument(
        "--max-songs",
        type=int,
        default=4,
        help="Maximum number of songs to include (default: 4)",
    )
    
    args = parser.parse_args()
    
    # Setup logging
    setup_logging("INFO")
    logger.info("Starting Music Video Generator")
    
    # Load configuration
    config = load_config(args.config)
    
    # Override beat sync if requested
    if args.no_beat_sync:
        config["beat_detection"]["enabled"] = False
    
    # Setup paths
    base_dir = Path(__file__).parent
    input_images_dir = base_dir / config["paths"]["input_images"]
    input_audio_dir = base_dir / config["paths"]["input_audio"]
    output_dir = ensure_output_dir(base_dir / config["paths"]["output"])
    
    # Select audio files
    audio_files = select_audio_files(input_audio_dir, max_songs=args.max_songs)
    if not audio_files:
        logger.error("No audio files found. Please add audio files to input/audio/")
        sys.exit(1)
    
    logger.info(f"Selected {len(audio_files)} audio file(s)")
    
    # Analyze audio
    analyzer = AudioAnalyzer(
        hop_length=config["beat_detection"]["hop_length"],
        backtrack=config["beat_detection"]["backtrack"],
        trim=config["beat_detection"]["trim"],
    )
    
    # Analyze multiple files or single file
    if len(audio_files) > 1:
        duration, beat_times, tempo, file_infos = analyzer.analyze_multiple(
            [str(p) for p in audio_files]
        )
        
        # Concatenate audio files
        concatenated_audio = output_dir / "concatenated_audio.mp3"
        generator_for_audio = VideoGenerator(config)
        combined_audio = generator_for_audio.concatenate_audio_files(
            audio_files,
            concatenated_audio,
        )
    else:
        duration, beat_times, tempo = analyzer.analyze(str(audio_files[0]))
        combined_audio = audio_files[0]
    
    # Select images based on total duration
    all_images = select_images(input_images_dir, 9999)
    
    # For multiple songs, use exactly one image per song
    if len(audio_files) > 1:
        num_images = len(audio_files)
    else:
        num_images = max(5, int(duration / config["image"]["default_duration"]))
        num_images = min(num_images, len(all_images))
    
    images = select_images(input_images_dir, num_images)
    
    # If we have more images than songs, pick the first N images
    if len(images) > len(audio_files):
        images = images[:len(audio_files)]
    
    # If we have fewer images than songs, repeat the images
    while len(images) < len(audio_files):
        images = images + images
    images = images[:len(audio_files)]
    
    logger.info(f"Using {len(images)} image(s) for {len(audio_files)} song(s)")
    for i, (audio, image) in enumerate(zip(audio_files, images)):
        logger.info(f"  Song {i+1}: {audio.name}")
        logger.info(f"    -> Image: {image.name}")
    
    # Create scenes
    use_beat_sync = config["beat_detection"]["enabled"] and beat_times
    
    if len(audio_files) > 1 and not use_beat_sync:
        scenes = []
        for i, (img, audio_file) in enumerate(zip(images, audio_files)):
            if i < len(file_infos):
                song_duration = file_infos[i]["duration"]
                start_time = file_infos[i]["start_time"]
            else:
                song_duration = config["image"]["default_duration"]
                start_time = sum(f["duration"] for f in file_infos)
            
            scenes.append(Scene(
                image_path=img,
                start_time=start_time,
                duration=song_duration,
                output_file=Path(f"temp_scene_{i:03d}.mp4"),
            ))
    else:
        scenes = create_scenes(
            images=images,
            duration=duration,
            default_duration=config["image"]["default_duration"],
            beat_times=beat_times if use_beat_sync else None,
        )
    
    logger.info(f"Created {len(scenes)} scenes")
    logger.info(f"Total video duration: {duration:.2f}s")
    logger.info(f"Sync mode: {'Beat-synced' if use_beat_sync else 'Equal duration'}")
    logger.info("Starting video rendering...")
    
    # Generate video
    generator = VideoGenerator(config)
    temp_dir = output_dir / "temp"
    temp_dir.mkdir(exist_ok=True)
    
    # Generate scene videos
    scene_files = []
    for i, scene in enumerate(scenes):
        scene.output_file = temp_dir / scene.output_file.name
        try:
            generator.generate_scene_video(scene)
            scene_files.append(scene.output_file)
            if (i + 1) % 10 == 0 or i == 0:
                logger.info(f"Rendered {i + 1}/{len(scenes)} scenes...")
        except Exception as e:
            logger.error(f"Failed to generate scene {i}: {e}")
            continue
    
    if not scene_files:
        logger.error("No scenes were generated successfully")
        sys.exit(1)
    
    # Concatenate scenes into ONE final video
    output_file = Path(args.output) if args.output else output_dir / "music_video.mp4"
    try:
        generator.concatenate_videos(
            scene_files=scene_files,
            output_file=output_file,
            audio_file=combined_audio if not args.mp3 else None,
        )
    except Exception as e:
        logger.error(f"Failed to create final video: {e}")
        sys.exit(1)
    
    # Cleanup temp files
    generator.cleanup_scenes(scene_files)
    if temp_dir.exists():
        temp_dir.rmdir()
    
    logger.info(f"Music video created successfully: {output_file}")


if __name__ == "__main__":
    main()