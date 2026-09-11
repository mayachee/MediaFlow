# Music Video Generator

Automated music video generator from audio files and images.
Creates high-quality videos with beat-synced transitions and zoompan effects.

## Project Structure

```
music_video_generator/
├── input/
│   ├── images/          # Put your images here
│   └── audio/           # Put your audio files here
├── output/              # Generated videos will be saved here
├── src/
│   ├── __init__.py
│   ├── audio_analyzer.py # Beat detection and audio analysis
│   ├── image_processor.py # Image preparation and effects
│   ├── video_generator.py # FFmpeg-based video creation
│   └── utils.py         # Helper utilities
├── config.yaml          # Configuration settings
├── requirements.txt     # Python dependencies
└── main.py              # Main entry point
```

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

2. Install FFmpeg:
   ```bash
   # Windows
   winget install ffmpeg
   
   # Or download from https://ffmpeg.org/download.html
   ```

3. Add your files:
   - Put images in `input/images/`
   - Put audio in `input/audio/`

4. Run:
   ```bash
   python main.py
   ```

## Output

- High-quality MP4 (H.264, 1080p, 30fps)
- Beat-synced scene transitions
- Smooth zoompan effects on images
- Optional MP3 conversion for compatibility
