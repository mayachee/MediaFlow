import logging
import subprocess
import shutil
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from .image_processor import ImageProcessor

logger = logging.getLogger(__name__)


@dataclass
class Scene:
    """Represents a video scene with image and timing."""
    image_path: Path
    start_time: float
    duration: float
    output_file: Path


class VideoGenerator:
    """Generate videos from images and audio using FFmpeg."""
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.video_config = config.get("video", {})
        self.effects_config = config.get("effects", {})
        
        # Extract video settings
        self.width = self.video_config.get("width", 1920)
        self.height = self.video_config.get("height", 1080)
        self.fps = self.video_config.get("fps", 30)
        self.bitrate = self.video_config.get("bitrate", "25M")
        
        # Image processor
        self.image_processor = ImageProcessor(
            target_width=self.width,
            target_height=self.height,
            zoom_factor=config.get("image", {}).get("zoom_factor", 1.15),
        )
        
        # Check FFmpeg availability
        self.ffmpeg_path = self._find_ffmpeg()
    
    def _find_ffmpeg(self) -> str:
        """Find FFmpeg executable."""
        ffmpeg = shutil.which("ffmpeg")
        if ffmpeg:
            return ffmpeg
        
        # Check common Windows paths
        common_paths = [
            r"C:\Program Files\DownloadHelper CoApp\ffmpeg.exe",
            r"C:\Program Files\ffmpeg\bin\ffmpeg.exe",
        ]
        
        for path in common_paths:
            if Path(path).exists():
                return path
        
        raise RuntimeError(
            "FFmpeg not found. Please install FFmpeg:\n"
            "  Windows: winget install ffmpeg\n"
            "  Or download from: https://ffmpeg.org/download.html"
        )
    
    def generate_scene_video(
        self,
        scene: Scene,
        output_file: Optional[Path] = None,
    ) -> Path:
        """
        Generate video segment for a single scene with Ken Burns effect.
        
        Args:
            scene: Scene object with image and timing
            output_file: Output file path (optional)
        
        Returns:
            Path to generated video segment
        """
        if output_file is None:
            output_file = scene.output_file
        
        # Load and prepare image
        img = self.image_processor.load_and_prepare(scene.image_path)
        if img is None:
            raise RuntimeError(f"Failed to load image: {scene.image_path}")
        
        # Save prepared image
        temp_img = output_file.with_suffix(".png")
        img.save(temp_img, "PNG", optimize=True)
        
        # Build FFmpeg command - optimized for memory efficiency
        duration = scene.duration

        # Use lightweight filters: fps + fade (zoompan removed for memory efficiency
        # on long scenes — -loop 1 already repeats the input image)
        fade_filter = (
            f"fade=t=in:st=0:d=0.5,"
            f"fade=t=out:st={max(duration - 0.5, 0)}:d=0.5"
        )

        filters = [f"fps={self.fps}", fade_filter]

        combined_filter = ",".join(filters)

        # Use -threads 1 to reduce memory pressure
        cmd = [
            self.ffmpeg_path,
            "-loop", "1",
            "-i", str(temp_img),
            "-vf", combined_filter,
            "-c:v", "libx264",
            "-preset", "ultrafast",
            "-crf", "28",
            "-pix_fmt", "yuv420p",
            "-threads", "1",
            "-t", str(duration),
            "-y",
            str(output_file),
        ]
        
        # Execute FFmpeg
        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr}")
            raise RuntimeError(f"Failed to generate scene video: {e}")
        
        # Cleanup temp image
        if temp_img.exists():
            temp_img.unlink()
        
        return output_file
    
    def concatenate_videos(
        self,
        scene_files: List[Path],
        output_file: Path,
        audio_file: Optional[Path] = None,
    ) -> Path:
        """
        Concatenate scene videos and add audio.
        
        Args:
            scene_files: List of scene video files
            output_file: Final output file path
            audio_file: Optional audio file to add
        
        Returns:
            Path to final video
        """
        logger.info(f"Concatenating {len(scene_files)} scenes...")
        
        # Create concat list file
        concat_list = output_file.parent / "concat_list.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for scene_file in scene_files:
                escaped_path = str(scene_file.absolute()).replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")
        
        # Build FFmpeg command
        cmd = [
            self.ffmpeg_path,
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
        ]
        
        # Add audio if provided
        if audio_file and audio_file.exists():
            cmd.extend(["-i", str(audio_file)])
        
        # Video settings
        cmd.extend([
            "-c:v", "libx264",
            "-preset", self.video_config.get("preset", "slow"),
            "-crf", "25",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
        ])
        
        # Audio settings
        if audio_file and audio_file.exists():
            cmd.extend([
                "-c:a", "aac",
                "-b:a", self.video_config.get("audio_bitrate", "320k"),
                "-ar", "44100",
            ])
        
        cmd.extend(["-y", str(output_file)])
        
        # Execute FFmpeg
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            logger.debug(f"FFmpeg output: {result.stdout}")
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr}")
            raise RuntimeError(f"Failed to concatenate videos: {e}")
        
        # Cleanup
        if concat_list.exists():
            concat_list.unlink()
        
        logger.info(f"Final video saved to: {output_file}")
        return output_file
    
    def concatenate_audio_files(
        self,
        audio_files: List[Path],
        output_file: Path,
    ) -> Path:
        """
        Concatenate multiple audio files into one.
        
        Args:
            audio_files: List of audio file paths
            output_file: Output concatenated audio file
        
        Returns:
            Path to concatenated audio file
        """
        if len(audio_files) == 1:
            return audio_files[0]
        
        logger.info(f"Concatenating {len(audio_files)} audio files...")
        
        # Create concat list for audio
        concat_list = output_file.parent / "audio_concat_list.txt"
        with open(concat_list, "w", encoding="utf-8") as f:
            for audio_file in audio_files:
                escaped_path = str(audio_file.absolute()).replace("'", "'\\''")
                f.write(f"file '{escaped_path}'\n")
        
        # Use FFmpeg concat demuxer - no re-encoding needed for same format
        # If formats differ, we re-encode to avoid errors
        cmd = [
            self.ffmpeg_path,
            "-f", "concat",
            "-safe", "0",
            "-i", str(concat_list),
            "-c", "copy",
            "-y",
            str(output_file),
        ]
        
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            logger.debug(f"FFmpeg audio concat output: {result.stdout}")
        except subprocess.CalledProcessError:
            # If copy fails due to format mismatch, re-encode
            logger.warning("Direct copy failed, re-encoding audio...")
            cmd = [
                self.ffmpeg_path,
                "-f", "concat",
                "-safe", "0",
                "-i", str(concat_list),
                "-c:a", "libmp3lame",
                "-b:a", "320k",
                "-y",
                str(output_file),
            ]
            try:
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    check=True,
                )
                logger.debug(f"FFmpeg audio re-encode output: {result.stdout}")
            except subprocess.CalledProcessError as e:
                logger.error(f"FFmpeg audio concat error: {e.stderr}")
                raise RuntimeError(f"Failed to concatenate audio files: {e}")
        
        # Cleanup
        if concat_list.exists():
            concat_list.unlink()
        
        logger.info(f"Concatenated audio saved to: {output_file}")
        return output_file
    
    def cleanup_scenes(self, scene_files: List[Path]) -> None:
        """Remove temporary scene files."""
        for scene_file in scene_files:
            if scene_file.exists():
                scene_file.unlink()
                logger.debug(f"Removed: {scene_file}")