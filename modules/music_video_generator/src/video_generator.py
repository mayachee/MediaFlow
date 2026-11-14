import logging
import subprocess
import shutil
import json
import math
import tempfile
from pathlib import Path
from typing import List, Optional, Dict, Any
from dataclasses import dataclass

from .image_processor import ImageProcessor

logger = logging.getLogger(__name__)

VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v", ".flv", ".wmv"}


def is_video(path: Path) -> bool:
    """Return True if the given path refers to a video file."""
    return path.suffix.lower() in VIDEO_EXTENSIONS


@dataclass
class Scene:
    """Represents a video scene with an image or video source and timing."""
    source_path: Path
    start_time: float
    duration: float
    output_file: Path
    motion: Optional[str] = None
    framing: Optional[str] = None
    energy: Optional[float] = None
    zoom_factor: Optional[float] = None
    beat_accents: Optional[List[dict]] = None
    pulse_strength: float = 0.0
    crop_factor: float = 1.0
    focal_point: tuple = (0.5, 0.5)


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
        self._scene_index = 0
        if (not isinstance(self.width, int) or not isinstance(self.height, int) or
                self.width <= 0 or self.height <= 0 or self.width % 2 or self.height % 2 or
                not math.isfinite(self.fps) or self.fps <= 0):
            raise ValueError('Video dimensions must be positive even integers and fps must be positive')
        zoom = config.get('image', {}).get('zoom_factor', 1.15)
        if not math.isfinite(zoom) or not 1 <= zoom <= 2:
            raise ValueError('image.zoom_factor must be between 1 and 2')
        
        # Image processor
        self.image_processor = ImageProcessor(
            target_width=self.width,
            target_height=self.height,
            zoom_factor=config.get("image", {}).get("zoom_factor", 1.15),
        )
        
        # Check FFmpeg availability
        self.ffmpeg_path = self._find_ffmpeg()

    def resolve_scene(self, scene):
        image = self.config.get('image', {})
        scene.framing = scene.framing or image.get('framing', 'fill')
        if scene.framing not in {'fit', 'fill'}:
            raise ValueError('Scene framing must be fit or fill')
        motion = scene.motion or image.get('motion')
        if motion is None:
            ken = self.effects_config.get('ken_burns', {})
            motion = ('zoom_in' if ken.get('zoom_in', True) else 'zoom_out') if ken.get('enabled', False) else 'still'
        choices = {'still', 'zoom_in', 'zoom_out', 'pan_left', 'pan_right', 'pan_up', 'pan_down', 'alternate'}
        if motion not in choices:
            raise ValueError(f'Unsupported motion: {motion}')
        if motion == 'alternate':
            motion = ('zoom_in', 'pan_right', 'zoom_out', 'pan_left')[self._scene_index % 4]
        if scene.framing == 'fit' or is_video(scene.source_path):
            motion = 'still'
            scene.beat_accents, scene.pulse_strength = [], 0
        scene.motion = motion
        self._scene_index += 1
        if not math.isfinite(scene.duration) or scene.duration < 1 / self.fps:
            raise ValueError('Scene must have a finite duration of at least one frame')

    def _fade_filters(self, duration):
        transitions = self.effects_config.get('transitions', {})
        if not transitions.get('enabled', True) or transitions.get('type', 'fade') != 'fade':
            return []
        fade = min(float(transitions.get('duration', 0.5)), duration / 4)
        return [f'fade=t=in:st=0:d={fade}', f'fade=t=out:st={duration - fade}:d={fade}'] if fade > 0 else []
    
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
        Generate a video segment for a single scene.

        For image sources a Ken Burns-style still is looped to the scene duration.
        For video sources the clip is simply looped to fill the duration
        (no image processing or zoompan is applied).

        Args:
            scene: Scene object with an image or video source and timing
            output_file: Output file path (optional)

        Returns:
            Path to generated video segment
        """
        if output_file is None:
            output_file = scene.output_file
        output_file.parent.mkdir(parents=True, exist_ok=True)
        self.resolve_scene(scene)

        duration = scene.duration
        temp_img = None

        if is_video(scene.source_path):
            cmd = self._build_loop_video_command(scene, duration, output_file)
        else:
            # Image path: load, prepare and loop the single frame
            scale = self.config.get('image', {}).get('supersample', 2) if scene.motion != 'still' else 1
            if scale not in (1, 2):
                raise ValueError('image.supersample must be 1 or 2')
            zoom = scene.zoom_factor or self.image_processor.zoom_factor
            processor = ImageProcessor(self.width * scale, self.height * scale, zoom)
            img = processor.load_and_prepare(scene.source_path, fit_to_screen=scene.framing == 'fill',
                                             enhance=self.config.get('image', {}).get('enhance', False),
                                             crop_factor=scene.crop_factor if scene.framing == 'fill' else 1,
                                             focal_point=scene.focal_point)
            if img is None:
                raise RuntimeError(f"Failed to load image: {scene.source_path}")

            # Save prepared image
            temp_img = output_file.with_suffix(".png")
            img.save(temp_img, "PNG", optimize=True)

            filters = [] if scene.motion != 'still' else [f"fps={self.fps}"]
            if scene.motion != 'still':
                filters.append(self.image_processor.generate_zoompan_filter(
                    duration, fps=self.fps, motion=scene.motion, zoom_factor=zoom,
                    beat_accents=scene.beat_accents, pulse_strength=scene.pulse_strength,
                    frames_per_image=self.fps))
            filters.extend(self._fade_filters(duration))
            filters.append('setsar=1')
            combined_filter = ",".join(filters)

            cmd = [
                self.ffmpeg_path,
                '-nostdin', '-hide_banner',
                '-framerate', '1',
                "-loop", "1",
                "-i", str(temp_img),
                "-vf", combined_filter,
                "-c:v", "libx264",
                "-preset", self.video_config.get("preset", "fast"),
                "-crf", str(self.video_config.get("scene_crf", min(self.video_config.get("crf", 20), 18))),
                "-pix_fmt", "yuv420p",
                "-threads", "1",
                "-t", str(duration),
                "-an",
                "-y",
                str(output_file),
            ]

        # Execute FFmpeg
        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True, encoding='utf-8', errors='replace',
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.error(f"FFmpeg error: {e.stderr}")
            raise RuntimeError(f"Failed to generate scene video: {e}")

        # Cleanup temp image
        if temp_img is not None and temp_img.exists():
            temp_img.unlink()

        return output_file

    def _build_loop_video_command(
        self,
        scene: Scene,
        duration: float,
        output_file: Path,
    ) -> List[str]:
        """
        Build an FFmpeg command that loops an input video to a target duration.

        The video is scaled/padded to the target resolution so that all scene
        segments are uniform for concatenation. No image-processing effects
        (zoompan, fade, etc.) are applied — the clip is just looped.
        """
        scale_filter = (
            f"scale={self.width}:{self.height}:"
            f"force_original_aspect_ratio=decrease,"
            f"pad={self.width}:{self.height}:"
            f"(ow-iw)/2:(oh-ih)/2,"
            f"fps={self.fps}"
        )
        if scene.framing == 'fill':
            scale_filter = (f'scale={self.width}:{self.height}:force_original_aspect_ratio=increase,'
                            f'crop={self.width}:{self.height},fps={self.fps}')
        scale_filter += ',setsar=1'
        fades = self._fade_filters(duration)
        if fades:
            scale_filter += ',' + ','.join(fades)

        return [
            self.ffmpeg_path,
            '-nostdin', '-hide_banner',
            "-stream_loop", "-1",
            "-i", str(scene.source_path),
            "-vf", scale_filter,
            "-c:v", "libx264",
            "-preset", self.video_config.get("preset", "fast"),
            "-crf", str(self.video_config.get("scene_crf", min(self.video_config.get("crf", 20), 18))),
            "-pix_fmt", "yuv420p",
            "-threads", "1",
            "-t", str(duration),
            "-an",
            "-y",
            str(output_file),
        ]
    
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
        if not scene_files:
            raise ValueError('No rendered scenes to concatenate')
        output_file.parent.mkdir(parents=True, exist_ok=True)
        transitions = self.effects_config.get('transitions', {})
        kind = transitions.get('type', 'fade') if transitions.get('enabled', True) else 'cut'
        if kind not in {'cut', 'fade', 'crossfade'}:
            raise ValueError('Transition type must be crossfade, fade, or cut')
        fade_duration = float(transitions.get('duration', 0.5))
        if not math.isfinite(fade_duration) or fade_duration < 0:
            raise ValueError('Transition duration must be finite and nonnegative')
        if kind == 'crossfade' and len(scene_files) > 1 and fade_duration >= 1 / self.fps:
            durations = transitions.get('per_boundary', fade_duration)
            return self._crossfade_videos(scene_files, output_file, audio_file, durations)
        
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
        if audio_file and not audio_file.is_file():
            raise FileNotFoundError(f"Audio file not found: {audio_file}")
        if audio_file:
            cmd.extend(["-i", str(audio_file)])
        
        # Video settings
        cmd.extend([
            "-map", "0:v:0",
            "-c:v", "copy",
            "-movflags", "+faststart",
        ])
        
        # Audio settings
        if audio_file and audio_file.exists():
            cmd.extend([
                "-map", "1:a:0",
                "-c:a", "aac",
                "-b:a", self.video_config.get("audio_bitrate", "320k"),
                "-ar", str(self.video_config.get("audio_sample_rate", 44100)),
            ])
        
        cmd.extend(["-y", str(output_file)])
        
        # Execute FFmpeg
        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True, encoding='utf-8', errors='replace',
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

    def _crossfade_videos(self, files, output, audio, requested, lossless=False):
        if audio is not None and not audio.is_file():
            raise FileNotFoundError(audio)
        ffprobe = shutil.which('ffprobe') or str(Path(self.ffmpeg_path).with_name('ffprobe' + Path(self.ffmpeg_path).suffix))
        counts = []
        for path in files:
            result = subprocess.run([ffprobe, '-v', 'error', '-select_streams', 'v:0',
                '-show_entries', 'stream=nb_frames,duration', '-of', 'json', str(path)],
                capture_output=True, text=True, encoding='utf-8', errors='replace', check=True)
            stream = json.loads(result.stdout)['streams'][0]
            counts.append(int(stream['nb_frames']) if stream.get('nb_frames', 'N/A') != 'N/A'
                          else round(float(stream['duration']) * self.fps))
        plan = crossfade_plan(counts, self.fps, requested)
        limit = self.effects_config.get('transitions', {}).get('maximum_inputs', 6)
        if not isinstance(limit, int) or not 2 <= limit <= 16:
            raise ValueError('transitions.maximum_inputs must be an integer between 2 and 16')
        if len(files) > limit:
            with tempfile.TemporaryDirectory(prefix='crossfade-', dir=output.parent) as temporary:
                cache = Path(temporary).resolve()
                if not cache.is_relative_to(output.parent.resolve()):
                    raise ValueError('Crossfade cache must remain inside the output directory')
                groups, between = [], []
                for offset in range(0, len(files), limit):
                    stop = min(offset + limit, len(files))
                    bundle = cache / f'{offset:05d}.mp4'
                    if stop - offset == 1:
                        shutil.copy2(files[offset], bundle)
                    else:
                        durations = [item['frames'] / self.fps for item in plan['boundaries'][offset:stop - 1]]
                        self._crossfade_videos(files[offset:stop], bundle, None, durations, lossless=True)
                    groups.append(bundle)
                    if stop < len(files):
                        between.append(plan['boundaries'][stop - 1]['frames'] / self.fps)
                self._crossfade_videos(groups, output, audio, between, lossless=lossless)
            plan.update(batched=True, maximum_inputs=limit, intermediate_codec='lossless H.264', cache_cleaned=True)
            (output.parent / 'transitions.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
            return output
        command = [self.ffmpeg_path, '-nostdin', '-hide_banner', '-filter_complex_threads', '1']
        filters = []
        for index, path in enumerate(files):
            command += ['-i', str(path)]
            before = plan['boundaries'][index - 1]['incoming_frames'] if index else 0
            after = plan['boundaries'][index]['outgoing_frames'] if index < len(files) - 1 else 0
            filters.append(f'[{index}:v]fps={self.fps},format=yuv444p,setsar=1,'
                f'tpad=start={before}:stop={after}:start_mode=clone:stop_mode=clone,'
                f'settb=AVTB,setpts=PTS-STARTPTS[v{index}]')
        previous = 'v0'
        for index, boundary in enumerate(plan['boundaries'], 1):
            label = f'blend{index}'
            if boundary['frames'] == 0:
                filters.append(f'[{previous}][v{index}]concat=n=2:v=1:a=0,fps={self.fps},settb=AVTB,setpts=PTS-STARTPTS[{label}]')
            else:
                filters.append(f'[{previous}][v{index}]xfade=transition=fade:'
                               f'duration={boundary["frames"] / self.fps:.9f}:'
                               f'offset={boundary["offset_frames"] / self.fps:.9f}[{label}]')
            previous = label
        filters.append(f'[{previous}]trim=end_frame={sum(counts)},setpts=PTS-STARTPTS,format=yuv420p[out]')
        if audio is not None:
            command += ['-i', str(audio)]
        command += ['-filter_complex', ';'.join(filters), '-map', '[out]', '-c:v', 'libx264',
                    '-preset', 'ultrafast' if lossless else self.video_config.get('preset', 'fast'),
                    '-crf', '0' if lossless else str(self.video_config.get('crf', 20)), '-threads', '1',
                    '-pix_fmt', 'yuv420p', '-movflags', '+faststart']
        if audio is not None:
            command += ['-map', f'{len(files)}:a:0', '-c:a', 'aac',
                        '-b:a', self.video_config.get('audio_bitrate', '256k'),
                        '-ar', str(self.video_config.get('audio_sample_rate', 44100))]
        command += ['-y', str(output)]
        result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8', errors='replace')
        if result.returncode:
            raise RuntimeError(f'Crossfade failed: {result.stderr[-4000:]}')
        (output.parent / 'transitions.json').write_text(json.dumps(plan, indent=2), encoding='utf-8')
        return output
    
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
        
        # Normalize each decoded input before concatenation. A concat demuxer
        # cannot safely combine arbitrary codecs, sample rates, and layouts.
        if not audio_files:
            raise ValueError("No audio files to concatenate")
        cmd = [self.ffmpeg_path, "-nostdin"]
        filters = []
        for index, audio_file in enumerate(audio_files):
            if not audio_file.is_file():
                raise FileNotFoundError(audio_file)
            cmd.extend(["-i", str(audio_file)])
            filters.append(
                f"[{index}:a:0]aformat=sample_fmts=fltp:sample_rates=48000:"
                f"channel_layouts=stereo,asetpts=PTS-STARTPTS[a{index}]"
            )
        inputs = "".join(f"[a{index}]" for index in range(len(audio_files)))
        filters.append(f"{inputs}concat=n={len(audio_files)}:v=0:a=1[out]")
        cmd.extend(["-filter_complex", ";".join(filters), "-map", "[out]"])
        if output_file.suffix.lower() == ".wav":
            cmd.extend(["-c:a", "pcm_s24le"])
        else:
            cmd.extend(["-c:a", "libmp3lame", "-b:a", "320k"])
        cmd.extend(["-y", str(output_file)])
        try:
            subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', check=True)
        except subprocess.CalledProcessError as error:
            raise RuntimeError(f"Audio concatenation failed: {error.stderr}") from error
        return output_file

    def cleanup_scenes(self, scene_files: List[Path]) -> None:
        """Remove temporary scene files."""
        for scene_file in scene_files:
            if scene_file.exists():
                scene_file.unlink()
                logger.debug(f"Removed: {scene_file}")


def crossfade_plan(frame_counts, fps, requested):
    """Clone edge-frame handles; overlaps do not shorten the original timeline."""
    boundaries, elapsed = [], 0
    for index, (left, right) in enumerate(zip(frame_counts, frame_counts[1:])):
        elapsed += left
        value = requested[index] if isinstance(requested, list) else requested
        if not math.isfinite(value) or value < 0:
            raise ValueError('Boundary durations must be nonnegative and finite')
        frames = min(max(0, round(value * fps)), left, right)
        incoming, outgoing = frames // 2, frames - frames // 2
        boundaries.append({'frames': frames, 'incoming_frames': incoming,
                           'outgoing_frames': outgoing, 'offset_frames': elapsed - incoming})
    return {'fps': fps, 'scene_frames': frame_counts, 'boundaries': boundaries,
            'output_frames': sum(frame_counts), 'duration': sum(frame_counts) / fps,
            'method': 'Cloned boundary handles; visual overlaps preserve the full audio timeline.'}
