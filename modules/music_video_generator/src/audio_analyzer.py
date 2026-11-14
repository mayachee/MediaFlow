import logging
import subprocess
import shutil
import json
from pathlib import Path
from typing import List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)


class AudioAnalyzer:
    """Analyze audio files for beat detection and timing."""
    
    def __init__(self, hop_length: int = 512, backtrack: bool = True, trim: bool = True, detect_beats: bool = True):
        self.hop_length = hop_length
        self.backtrack = backtrack
        self.trim = trim
        self._librosa_available = False
        self._profiles = {}
        if not detect_beats:
            return
        try:
            import librosa
            self._librosa = librosa
            self._librosa_available = True
        except Exception as e:
            logger.warning(f"librosa not available: {e}. Beat detection disabled.")
    
    def analyze(self, audio_path: str) -> Tuple[float, List[float], float]:
        """
        Analyze audio file and extract beat information.
        
        Returns:
            Tuple of (duration, beat_times, tempo)
        """
        logger.info(f"Analyzing audio: {audio_path}")
        
        if not self._librosa_available:
            logger.info("Beat analysis disabled or unavailable; using measured duration")
            return self._simple_duration(audio_path)
        
        try:
            # Load audio file
            y, sr = self._librosa.load(audio_path, sr=22050)
            duration = self._librosa.get_duration(y=y, sr=sr)
            
            # Detect tempo and beats
            onset = self._librosa.onset.onset_strength(y=y, sr=sr, hop_length=self.hop_length)
            tempo, beats = self._librosa.beat.beat_track(
                onset_envelope=onset,
                sr=sr,
                hop_length=self.hop_length,
                trim=self.trim,
            )
            
            # Convert beat frames to time
            beat_times = self._librosa.frames_to_time(beats, sr=sr, hop_length=self.hop_length)
            
            tempo = float(np.asarray(tempo).reshape(-1)[0])
            rms = self._librosa.feature.rms(y=y, frame_length=2048, hop_length=self.hop_length)[0]
            frames = self._librosa.frames_to_time(np.arange(len(rms)), sr=sr, hop_length=self.hop_length)
            grid = np.arange(0, duration, 0.25)
            sampled = np.interp(grid, frames, rms)
            db = 20 * np.log10(sampled + 1e-8)
            low, high = np.percentile(db, [10, 90])
            energy = np.clip((db - low) / (high - low), 0, 1) if high - low > 1 else np.full(len(grid), 0.5)
            energy[sampled < 1e-5] = 0
            if len(energy) >= 5:
                energy = np.convolve(np.pad(energy, (2, 2), mode='edge'), np.ones(5) / 5, mode='valid')
            onsets = self._librosa.onset.onset_detect(onset_envelope=onset, sr=sr,
                hop_length=self.hop_length, units='time').tolist()
            self._profiles[str(Path(audio_path).resolve())] = {
                'duration': duration, 'tempo_bpm': tempo, 'beats': beat_times.tolist(),
                'onsets': onsets, 'energy_times': grid.tolist(), 'energy': energy.tolist(),
                'method': 'Detected beats/onsets and smoothed relative RMS; not semantic chorus/downbeat detection.'}
            logger.info(f"Audio duration: {duration:.2f}s")
            logger.info(f"Detected tempo: {tempo:.1f} BPM")
            logger.info(f"Found {len(beat_times)} beats")
            
            return duration, beat_times.tolist(), float(tempo)
        except Exception as e:
            logger.warning(f"librosa analysis failed: {e}. Using simple duration.")
            return self._simple_duration(audio_path)
    
    def analyze_multiple(
        self,
        audio_paths: List[str],
    ) -> Tuple[float, List[float], float, List[dict]]:
        """
        Analyze multiple audio files and combine them into a playlist.
        
        Returns:
            Tuple of (total_duration, all_beat_times, avg_tempo, file_infos)
            file_infos contains dicts with path, duration, start_time, end_time
        """
        all_beat_times = []
        total_duration = 0.0
        tempos = []
        file_infos = []
        current_offset = 0.0
        
        for path in audio_paths:
            duration, beat_times, tempo = self.analyze(path)
            tempos.append(tempo)
            
            # Offset beat times to global timeline
            offset_beats = [bt + current_offset for bt in beat_times]
            all_beat_times.extend(offset_beats)
            
            file_infos.append({
                "path": path,
                "duration": duration,
                "start_time": current_offset,
                "end_time": current_offset + duration,
            })
            
            current_offset += duration
            total_duration += duration
        
        avg_tempo = sum(tempos) / len(tempos) if tempos else 120.0
        
        logger.info(f"Playlist total duration: {total_duration:.2f}s")
        logger.info(f"Average tempo: {avg_tempo:.1f} BPM")
        
        return total_duration, all_beat_times, avg_tempo, file_infos

    def profile(self, audio_path):
        """Return analysis already computed by analyze(); never fabricate beats."""
        return self._profiles.get(str(Path(audio_path).resolve()))
    
    def _simple_duration(self, audio_path: str) -> Tuple[float, List[float], float]:
        """Fallback: estimate duration without beat detection."""
        duration = self._probe_duration(audio_path)
        if duration is None or not np.isfinite(duration) or duration <= 0:
            raise RuntimeError(f"Cannot determine audio duration: {audio_path}. Check the file and ffprobe.")
        
        logger.info(f"Audio duration: {duration:.2f}s (no beat detection)")
        return duration, [], 120.0
    
    def _probe_duration(self, audio_path: str) -> Optional[float]:
        """Get exact duration using ffprobe if available."""
        try:
            ffprobe = shutil.which("ffprobe")
            if not ffprobe:
                common_paths = [
                    r"C:\Program Files\DownloadHelper CoApp\ffprobe.exe",
                    r"C:\Program Files\ffmpeg\bin\ffprobe.exe",
                ]
                for path in common_paths:
                    if Path(path).exists():
                        ffprobe = path
                        break
            
            if not ffprobe:
                return None
            
            cmd = [
                ffprobe,
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "json",
                audio_path,
            ]
            result = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', check=True)
            import json
            info = json.loads(result.stdout)
            return float(info["format"]["duration"])
        except Exception:
            return None
    
    def get_beat_intervals(self, beat_times: List[float]) -> List[float]:
        """Calculate intervals between consecutive beats."""
        if len(beat_times) < 2:
            return []
        
        intervals = []
        for i in range(1, len(beat_times)):
            intervals.append(beat_times[i] - beat_times[i - 1])
        
        return intervals
    
    def get_scene_timings(
        self,
        beat_times: List[float],
        num_images: int,
        default_duration: float = 4.0,
    ) -> List[Tuple[float, float]]:
        """
        Calculate scene start/end times based on beats.
        
        Returns:
            List of (start_time, end_time) tuples for each scene
        """
        if not beat_times or num_images == 0:
            return []
        
        # If we have enough beats, use them for scene transitions
        if len(beat_times) >= num_images:
            # Distribute images across beats
            step = len(beat_times) // num_images
            scene_beats = beat_times[::step][:num_images]
        else:
            # Not enough beats, use default duration
            scene_beats = []
            current_time = 0.0
            for _ in range(num_images):
                scene_beats.append(current_time)
                current_time += default_duration
        
        # Create scene timings
        scenes = []
        for i, start_time in enumerate(scene_beats):
            if i < len(scene_beats) - 1:
                end_time = scene_beats[i + 1]
            else:
                # Last scene goes to the end
                end_time = beat_times[-1] + default_duration if beat_times else start_time + default_duration
            
            scenes.append((start_time, end_time))
        
        return scenes
