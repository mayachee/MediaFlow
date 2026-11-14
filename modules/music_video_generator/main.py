#!/usr/bin/env python3
"""
Music Video Generator
Main entry point for generating music videos from images and audio.
"""

import sys
import logging
import json
import math
from datetime import datetime
import uuid
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
from src.timeline import load_timeline, build_scenes as build_timeline
from src.music_direction import combined_profile, directed_scenes, direct_scene, style_settings
from src.preview import prepare_preview

logger = logging.getLogger(__name__)


def select_audio_files(audio_dir: Path, max_songs: int = 4) -> List[Path]:
    """Select audio files from directory for playlist."""
    audio_files = get_input_files(audio_dir, [".mp3", ".wav", ".m4a", ".ogg", ".flac", ".webm", ".mp4"])
    
    if not audio_files:
        logger.warning(f"No audio files found in {audio_dir}")
        return []
    
    if len(audio_files) == 1:
        return audio_files[:1]
    
    logger.info(f"Found {len(audio_files)} audio files, selecting up to {max_songs}")
    return audio_files[:max_songs]


IMAGE_EXTENSIONS = [".jpg", ".jpeg", ".png", ".bmp", ".webp"]
VIDEO_EXTENSIONS = [".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".flv", ".wmv"]


def select_sources(sources_dir: Path, count: int) -> List[Path]:
    """Select and distribute image/video sources across video duration."""
    source_files = get_input_files(sources_dir, IMAGE_EXTENSIONS + VIDEO_EXTENSIONS)

    if not source_files:
        logger.error(f"No images or videos found in {sources_dir}")
        sys.exit(1)

    logger.info(f"Found {len(source_files)} source file(s)")

    # If we have more sources than needed, select evenly spaced ones
    if len(source_files) > count:
        step = len(source_files) / count
        selected = []
        for i in range(count):
            idx = int(i * step)
            selected.append(source_files[idx % len(source_files)])
        return selected

    # If we have fewer sources, repeat them
    if len(source_files) < count:
        repeated = []
        while len(repeated) < count:
            repeated.extend(source_files)
        return repeated[:count]

    return source_files


def create_scenes(
    sources: List[Path],
    duration: float,
    default_duration: float = 4.0,
    beat_times: Optional[List[float]] = None,
) -> List[Scene]:
    """Create scene list from image/video sources and timing information."""
    scenes = []

    if not sources or duration <= 0:
        raise ValueError("Scenes require sources and a positive duration")
    if beat_times and len(beat_times) >= len(sources):
        # Use beat-synced timing
        step = len(beat_times) // len(sources)
        for i, src in enumerate(sources):
            start_idx = min(i * step, len(beat_times) - 1)
            start_time = 0.0 if i == 0 else beat_times[start_idx]

            if i < len(sources) - 1:
                end_idx = min((i + 1) * step, len(beat_times) - 1)
                end_time = beat_times[end_idx]
            else:
                end_time = duration

            scene_duration = end_time - start_time
            if scene_duration <= 0:
                raise ValueError("Beat times must produce positive scene durations")

            scenes.append(Scene(
                source_path=src,
                start_time=start_time,
                duration=scene_duration,
                output_file=Path(f"temp_scene_{i:03d}.mp4"),
            ))
    else:
        # Use equal duration for each source
        duration_per_source = duration / len(sources)
        for i, src in enumerate(sources):
            scenes.append(Scene(
                source_path=src,
                start_time=i * duration_per_source,
                duration=duration_per_source,
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
        default=str(Path(__file__).resolve().parent / "config.yaml"),
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
        help="Deprecated; use the downloader for MP3 conversion (video audio is always included)",
    )
    parser.add_argument(
        "--max-songs",
        type=int,
        default=4,
        help="Maximum number of songs to include (default: 4)",
    )
    
    parser.add_argument("--timeline", type=Path, help="YAML mapping of visuals, durations, motion, and framing")
    parser.add_argument('--style', choices=['cinematic', 'balanced', 'energetic'], help='Music-responsive visual pacing')
    parser.add_argument('--audio', type=Path, help='Select one exact audio file or an audio directory')
    parser.add_argument('--visuals', type=Path, help='Folder of selected local images/video clips')
    parser.add_argument('--preview-start', type=float, default=0, help='Start time in the selected playlist')
    parser.add_argument('--preview-seconds', type=float, help='Render only this many seconds, into a separate preview folder')
    args = parser.parse_args()
    if args.max_songs < 1:
        parser.error("--max-songs must be positive")
    if not math.isfinite(args.preview_start) or args.preview_start < 0:
        parser.error('--preview-start must be finite and nonnegative')
    if args.preview_start and args.preview_seconds is None:
        parser.error('--preview-start requires --preview-seconds')
    if args.preview_seconds is not None and (not math.isfinite(args.preview_seconds) or args.preview_seconds <= 0):
        parser.error('--preview-seconds must be positive and finite')
    if args.preview_seconds is not None and args.timeline:
        parser.error('For mapped timeline previews, use the root workflow preview command')
    
    # Setup logging
    setup_logging("INFO")
    logger.info("Starting Music Video Generator")
    
    # Load configuration
    config = load_config(args.config)
    direction = config.get('direction', {})
    style = args.style or direction.get('style', 'cinematic')
    style_settings(style)
    
    # Override beat sync if requested
    if args.no_beat_sync:
        config["beat_detection"]["enabled"] = False
    
    # Setup paths
    base_dir = Path(__file__).parent
    input_images_dir = base_dir / config["paths"]["input_images"]
    if args.visuals:
        input_images_dir = args.visuals.resolve()
    input_audio_dir = base_dir / config["paths"]["input_audio"]
    output_dir = ensure_output_dir(base_dir / config["paths"]["output"])
    if args.preview_seconds is not None:
        output_dir = ensure_output_dir(Path(args.output).resolve().parent if args.output else
            output_dir / ('preview-' + datetime.now().strftime('%Y%m%d-%H%M%S-') + uuid.uuid4().hex[:6]))
    
    # Select audio files
    if args.audio and args.audio.is_file():
        if args.audio.suffix.lower() not in {'.mp3', '.wav', '.m4a', '.ogg', '.flac', '.webm', '.mp4'}:
            parser.error('Unsupported audio file')
        audio_files = [args.audio.resolve()]
    else:
        audio_files = select_audio_files(args.audio.resolve() if args.audio else input_audio_dir, max_songs=args.max_songs)
    if not audio_files:
        logger.error("No audio files found. Please add audio files to input/audio/")
        sys.exit(1)
    
    logger.info(f"Selected {len(audio_files)} audio file(s)")
    preview_selection = None
    if args.preview_seconds is not None:
        audio_files, preview_selection = prepare_preview(audio_files, args.preview_start,
            args.preview_seconds, output_dir / 'selected-audio')
    
    # Analyze audio
    analyzer = AudioAnalyzer(
        hop_length=config["beat_detection"]["hop_length"],
        backtrack=config["beat_detection"]["backtrack"],
        trim=config["beat_detection"]["trim"],
        detect_beats=config["beat_detection"]["enabled"],
    )
    
    file_infos = []
    # Analyze multiple files or single file
    if len(audio_files) > 1:
        duration, beat_times, tempo, file_infos = analyzer.analyze_multiple(
            [str(p) for p in audio_files]
        )
        
        # Concatenate audio files
        concatenated_audio = output_dir / "concatenated_audio.wav"
        generator_for_audio = VideoGenerator(config)
        combined_audio = generator_for_audio.concatenate_audio_files(
            audio_files,
            concatenated_audio,
        )
    else:
        duration, beat_times, tempo = analyzer.analyze(str(audio_files[0]))
        combined_audio = audio_files[0]
        file_infos = [{"path": audio_files[0], "duration": duration, "start_time": 0.0}]

    profiles = [analyzer.profile(path) for path in audio_files]
    music_profile = combined_profile(file_infos, profiles)
    music_directed = bool(direction.get('enabled', False) and config['beat_detection']['enabled'] and music_profile['tracks'])
    beat_accents = direction.get('beat_accents', True)
    
    if args.timeline:
        timeline_document = load_timeline(args.timeline)
        scenes = build_timeline(timeline_document, duration, file_infos, config["video"]["fps"])
        if music_directed:
            for index, scene in enumerate(scenes):
                direct_scene(scene, music_profile, style, index, beat_accents, respect_motion=True)
        use_beat_sync = False
    elif music_directed:
        all_sources = get_input_files(input_images_dir, IMAGE_EXTENSIONS + VIDEO_EXTENSIONS)
        scenes = directed_scenes(all_sources, file_infos, music_profile, style, config['video']['fps'], beat_accents,
                                 montage=direction.get('edit_mode') == 'montage', focal_points=direction.get('focal_points'))
        if config.get('image', {}).get('motion', 'alternate') != 'alternate':
            for scene in scenes:
                scene.motion = config['image']['motion']
                if scene.motion == 'still':
                    scene.beat_accents, scene.pulse_strength = [], 0
        use_beat_sync = bool(music_profile['beats'])
    else:
        # Select sources (images or videos) based on total duration
        all_sources = get_input_files(input_images_dir, IMAGE_EXTENSIONS + VIDEO_EXTENSIONS)
        if not all_sources:
            logger.error("No visual sources found in %s", input_images_dir)
            sys.exit(1)

        # For multiple songs, use exactly one source per song
        if len(audio_files) > 1:
            num_sources = len(audio_files)
        else:
            num_sources = max(5, int(duration / config["image"]["default_duration"]))
            num_sources = min(num_sources, len(all_sources))

        sources = select_sources(input_images_dir, num_sources)

        logger.info(f"Using {len(sources)} source(s) for {len(audio_files)} song(s)")
        for i, (audio, source) in enumerate(zip(audio_files, sources)):
            logger.info(f"  Song {i+1}: {audio.name}")
            logger.info(f"    -> Source: {source.name}")

        # Create scenes
        use_beat_sync = config["beat_detection"]["enabled"] and beat_times

        if len(audio_files) > 1:
            scenes = []
            for i, (src, audio_file) in enumerate(zip(sources, audio_files)):
                if i < len(file_infos):
                    song_duration = file_infos[i]["duration"]
                    start_time = file_infos[i]["start_time"]
                else:
                    song_duration = config["image"]["default_duration"]
                    start_time = sum(f["duration"] for f in file_infos)

                scenes.append(Scene(
                    source_path=src,
                    start_time=start_time,
                    duration=song_duration,
                    output_file=Path(f"temp_scene_{i:03d}.mp4"),
                ))
        else:
            scenes = create_scenes(
                sources=sources,
                duration=duration,
                default_duration=config["image"]["default_duration"],
                beat_times=beat_times if use_beat_sync else None,
            )
    
    logger.info(f"Created {len(scenes)} scenes")
    logger.info(f"Total video duration: {duration:.2f}s")
    if music_directed and direction.get('follow_style_transitions', True):
        config.setdefault('effects', {}).setdefault('transitions', {})['duration'] = style_settings(style)['transition']
    if music_directed and not args.timeline and direction.get('edit_mode') == 'montage':
        config.setdefault('effects', {}).setdefault('transitions', {})['per_boundary'] = [
            0.0 if max(left.energy or 0, right.energy or 0) >= 0.55 else 0.25
            for left, right in zip(scenes, scenes[1:])]
    logger.info("Sync mode: %s", "Explicit timeline" if args.timeline else f'Music-directed {style}' if music_directed else
                ("Song boundaries" if len(audio_files) > 1 else ("Beat-synced" if use_beat_sync else "Equal duration")))
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
            raise RuntimeError(f"Scene {i} failed; refusing to produce an incomplete video") from e
    
    if not scene_files:
        logger.error("No scenes were generated successfully")
        sys.exit(1)
    
    plan = {"audio_files": [str(p.resolve()) for p in audio_files],
            "duration": duration, "timeline": str(args.timeline.resolve()) if args.timeline else None,
            'direction_style': style if music_directed else None, 'preview_selection': preview_selection,
            'provenance': timeline_document.get('provenance', []) if args.timeline else [],
            "scenes": [{"source": str(scene.source_path.resolve()), "start": scene.start_time,
                        "duration": scene.duration, "motion": scene.motion, "framing": scene.framing,
                        'energy': scene.energy, 'zoom_factor': scene.zoom_factor,
                        'crop_factor': scene.crop_factor, 'focal_point': scene.focal_point,
                        'pulse_strength': scene.pulse_strength, 'beat_accents': scene.beat_accents}
                       for scene in scenes]}
    (output_dir / "scene-plan.json").write_text(json.dumps(plan, indent=2), encoding="utf-8")
    (output_dir / 'music-analysis.json').write_text(json.dumps({'active': music_directed, 'style': style,
        'profile': music_profile, 'preview_selection': preview_selection,
        'fallback': None if music_directed else 'Music direction disabled or analysis unavailable; existing timing retained.'}, indent=2), encoding='utf-8')

    # Concatenate scenes into ONE final video
    output_file = Path(args.output) if args.output else output_dir / "music_video.mp4"
    try:
        generator.concatenate_videos(
            scene_files=scene_files,
            output_file=output_file,
            audio_file=combined_audio,
        )
    except Exception as e:
        logger.error(f"Failed to create final video: {e}")
        sys.exit(1)
    
    # Cleanup temp files
    generator.cleanup_scenes(scene_files)
    if temp_dir.exists():
        temp_dir.rmdir()
    
    logger.info(f"Music video created successfully: {output_file}")
    print(f'Video saved to: {output_file.resolve()}', flush=True)


if __name__ == "__main__":
    main()
