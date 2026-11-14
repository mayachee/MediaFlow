# AutoCrop Vertical in Scripts Studio

Integration of [kamilstanuch/Autocrop-vertical](https://github.com/kamilstanuch/Autocrop-vertical),
pinned to commit `e02663944597b89b63c7fbfda3ed7166954f5724`.
Upstream source is downloaded into `vendor/autocrop-vertical/`; the adapter does
not modify that source. It creates an adapted runtime copy for each job.

## In the desktop program

1. Restart **Scripts Studio** (`Start Scripts Studio.cmd`).
2. Under **Setup & maintenance**, run **Setup AutoCrop Vertical** once. This
   installs CPU PyTorch, OpenCV, PySceneDetect, Ultralytics, and their dependencies
   into this module's `.venv`. Initial setup needs internet and a large download.
   The YOLOv8 nano weights are saved under `work/` for reuse.
3. Run **Check AutoCrop installation** to inspect readiness.
4. Under **Video & audio**, choose **AutoCrop Vertical: reframe video**.
5. Choose the source video and output folder. Select **16:9** for standard YouTube,
   **9:16** for Shorts/Reels, **4:5**, or **1:1**. Choose resolution and encoding quality.
   Studio initially selects **16:9 + 1080p**, producing a **1920x1080** video.
   **720p** produces **1280x720** in 16:9. **Native** uses the source frame height.
6. Optionally select **Analyze only** to inspect the scene decisions without
   encoding. Otherwise, click **Run tool** to produce the video.

Each conversion creates a new timestamped subfolder containing `youtube.mp4`
(16:9) or `vertical.mp4` (other formats),
`result.json`, and the adapted runtime. The source file and earlier conversions
are preserved. Studio keeps console output in its normal job log. With
**Analyze only**, there is a plan in the log and a result record, but no MP4.

## Connect it to the music-video workflow

```mermaid
flowchart LR
    A[Audio + clips or artwork] --> B[Create music video]
    B --> C[Review landscape MP4]
    C --> D[AutoCrop Vertical]
    D --> E[Review vertical MP4]
    E --> F[Optional publish]
```

Choose a completed music-video MP4 as AutoCrop's input. It keeps the existing
audio and changes the visual framing; this is a separate conversion step.
Fixed resolutions are available for each shape: 1080p gives 1920x1080 in 16:9,
1080x1920 in 9:16, 1080x1350 in 4:5, or 1080x1080 in 1:1. Setting a larger
output size cannot restore detail missing from a small source. Native size
uses the original frame height with even encoding dimensions. Review framing
before publishing, especially with text, fast motion, or people far apart.

Upstream samples a scene's middle frame for person/face detection, then uses
that composition for the scene. This is not continuous frame-by-frame subject
tracking. Empty or widely spread groups use letterboxing. Square and other
formats are selected through the same upstream ratio option.

## Command line

From the workspace root:

```powershell
python modules/autocrop_vertical/manage.py setup
python modules/autocrop_vertical/manage.py status
python modules/autocrop_vertical/manage.py convert --input "my video.mp4" --ratio 9:16 --quality balanced
python modules/autocrop_vertical/manage.py convert --input "my video.mp4" --ratio 16:9 --resolution 1080p --quality high
python modules/autocrop_vertical/manage.py convert --input "my video.mp4" --plan-only
```

Default output: `runs/autocrop-vertical/<timestamp-id>/`. Override with
`--output-root`. FFmpeg and ffprobe must be on PATH.
The CLI retains 9:16/native defaults; Studio selects 16:9/1080p explicitly.

YouTube lists 16:9 as the standard desktop aspect ratio and 1920x1080 as its
1080p size: [YouTube resolution guide](https://support.google.com/youtube/answer/6375112?hl=en).

The integration supports clips with no scene cuts and drains FFmpeg's error
pipe while frames are written to avoid a full pipe blocking long encodes. The
runtime uses a local hard link to the cached model (a copy when linking is not
available), avoiding a model-loader issue with apostrophes in Windows paths.
A completed conversion must
pass a full FFmpeg decode, aspect-ratio and duration checks, and audio-presence
validation. Hardware encoders are intentionally not selected by this adapter;
CPU H.264 encoding is used for consistent behavior across machines.

The setup stores source locally for use; consult the upstream repository for
its own terms and third-party dependency licensing when redistributing.
