# Music Video Generator

Create music videos from audio files and images using Python + FFmpeg.

Online clip discovery lives in the separate [clip finder module](../clip_finder/README.md).
Supply selected local footage with `-Visuals <clips-folder>`; the renderer does
not search or download videos.

**Music-responsive editing:** [cinematic/balanced/energetic direction](MUSIC_DIRECTION.md)
uses detected beats and relative energy for shot timing, gentle camera movement,
and subtle beat accents. Try a local preview before rendering a long soundtrack:

```powershell
.\run.ps1 preview -Style cinematic -PreviewStart 60 -PreviewSeconds 30
```

**New editing controls:** [visual mapping, varied motion, fit/fill framing,
and true crossfades](../../docs/VIDEO_EDITING.md). Use `--timeline path/to/timeline.yaml`
for explicit scenes. See `examples/timeline.example.yaml` for a template.
The default configuration now alternates image motion and blends scenes with
crossfades while retaining the full audio timeline.

## Quick Start

### Windows (PowerShell)
```powershell
.\run.ps1 install      # First time: install dependencies
.\run.ps1 generate     # Create music video -> output/music_video.mp4
.\run.ps1 clean        # Remove generated files
```

### Linux/macOS (Makefile)
```bash
make install           # Install dependencies
make generate          # Create music video -> output/music_video.mp4
make clean             # Remove generated files
```

## Prerequisites

- **Python 3.11+**
- **FFmpeg** (critical dependency)
  - Windows: `winget install ffmpeg`
  - macOS: `brew install ffmpeg`
  - Linux: `sudo apt install ffmpeg`

## Directories

```
music_video_generator/
├── input/
│   ├── audio/          # Put your audio files here (.mp3, .webm, .wav, etc.)
│   └── images/         # Put your images or videos here (.jpg, .png, .webp, .mp4, etc.)
├── output/             # Generated videos are saved here
├── src/                # Core modules
│   ├── audio_analyzer.py  # Audio analysis (librosa)
│   ├── image_processor.py # Image preparation (PIL)
│   ├── video_generator.py # FFmpeg video creation
│   └── utils.py           # Helper utilities
├── config.yaml         # Configuration
├── main.py             # Main entry point
└── requirements.txt
```

## Configuration

Edit `config.yaml` to adjust:

| Setting | Description | Default |
|---------|-------------|---------|
| `video.width` | Output width | 1280 |
| `video.height` | Output height | 720 |
| `video.fps` | Frames per second | 30 |
| `video.preset` | FFmpeg encoding preset | ultrafast |
| `image.default_duration` | Seconds per image | 12.0 |
| `image.zoom_factor` | Ken Burns zoom amount | 1.15 |
| `beat_detection.enabled` | Beat-synced scenes | true |
| `effects.ken_burns.enabled` | Enable zoom effect | true |
| `effects.transitions.enabled` | Enable fade transitions | true |

## How It Works

1. Reads audio files from `input/audio/` (supports playlists)
2. Analyzes audio duration and beats (if librosa is available)
3. Matches images/videos from `input/images/` (one source per song)
4. Generates scenes: still images get a Ken Burns + fade effect, videos are looped to fill their scene duration
5. Concatenates all scenes with audio into final video
6. Output saved to `output/music_video.mp4`

## Notes

- If you have 3 songs, 3 sources will be used (one per song)
- Video sources are simply looped to match each scene's duration (no zoom/pan effects applied)
- Without librosa, falls back to equal-duration scenes
- Audio must be installed in the same virtual environment if using a venv
- Output quality can be adjusted in config.yaml (resolution, CRF, bitrate)
