# Visual mapping, motion, framing, and crossfades

The generator now supports explicit scene timelines as well as automatic visual
selection. The default configuration alternates image motion and crossfades
between scenes. Image colors are preserved unless enhancement is enabled.

## Try the working examples

```powershell
py -3.11 tools/smoke_video_editing.py
```

This generates local music/artwork and four viewable examples: a color blend, a
mapped video with zoom/pan/portrait/looped clip, a cropped preview, and a short
1080p crossfade. It prints a results-page path under `runs/video-editing-demo/`.
The test checks actual decoded frame pixels, audio/video duration, and complete
decoding; it does not download or upload anything.

## Map your visuals explicitly

Create a YAML file next to your artwork:

```yaml
scenes:
  - source: artwork/intro.jpg
    duration: 8
    motion: zoom_in
    framing: fill

  - source: clips/performance.mp4
    duration: 12
    framing: fit

  - source: artwork/portrait.jpg
    duration: auto
    motion: still
    framing: fit
```

`source` paths resolve relative to the YAML file, not your terminal directory.
The first two scenes use 20 seconds; final `duration: auto` fills the rest of
the selected audio. Every scene must last at least one output frame. A timeline
that does not cover the selected audio fails explicitly rather than silently
changing the edit. Only the last scene can use `auto`.

```powershell
# Main workflow: copies the mapped visuals into the isolated job
.\run.ps1 workflow -Audio "song.wav" -Timeline "my-project/timeline.yaml"

# Preview a section using the same visual mapping
.\run.ps1 workflow -Audio "song.wav" -Timeline "my-project/timeline.yaml" -Preset preview -PreviewStart 10 -PreviewSeconds 20

# Standalone generator: uses audio/configured paths directly
py -3.11 modules/music_video_generator/main.py --timeline "my-project/timeline.yaml"
```

`--images` is unnecessary when a timeline supplies every visual. A workflow
audio-only master does not accept a visual timeline. A copied `timeline.yaml`
is retained in the job, alongside a `video/scene-plan.json` describing the actual
source, start time, duration, motion, and framing of each scene.

For a playlist with exactly one visual per song, use track numbers instead of
durations:

```yaml
scenes:
  - track: 1
    source: artwork/song-one.jpg
    motion: zoom_out
  - track: 2
    source: artwork/song-two.jpg
    motion: pan_left
```

Track numbers follow the selected audio files in filename order. Every selected
track must appear once, in order starting at 1; `track` and `duration` cannot be
mixed in a timeline. The saved scene plan lists the actual audio filenames.
Neither this mapping nor the reference tools identify songs semantically.

Preview timelines are cropped to intersect the selected audio range. Motion
restarts within each cropped scene, and video sources restart at their beginning;
the preview is a review of the section's mapping, not a frame-identical extract
of a completed full render. Adjust the range if it creates a sub-frame scene.

## Motion and framing

| Setting | Behavior |
|---|---|
| `still` | No camera movement |
| `zoom_in`, `zoom_out` | Gentle, bounded center zoom |
| `pan_left`, `pan_right` | Camera traverses a zoomed image horizontally |
| `pan_up`, `pan_down` | Camera traverses a zoomed image vertically |
| `alternate` | Repeatable zoom-in → pan-right → zoom-out → pan-left cycle |
| `framing: fill` | Fill the screen, cropping excess from the center |
| `framing: fit` | Preserve the full image/clip with black letterboxing |

Fit mode resolves image motion to `still` to keep all edges visible. Image-motion
settings do not animate video clips; clips retain their native motion and loop
to the required scene duration. A clip's own audio is not mixed into the song.
The scene plan records the effective settings, including these resolutions.

Global defaults are in `modules/music_video_generator/config.yaml`:

```yaml
image:
  motion: alternate
  framing: fill
  zoom_factor: 1.15
  supersample: 2
  enhance: false
```

Per-scene motion/framing override global defaults. `supersample: 2` prepares a
larger still image for smoother motion; use `1` to reduce memory and preparation
cost. The permitted zoom range is 1–2. EXIF orientation is honored, transparent
images are composited over black, and `enhance: false` avoids automatic
contrast/saturation/sharpening changes. For all-still videos, set `motion: still`.
The explicit motion setting supersedes the older Ken Burns enable/zoom flag.

## Transitions without shortening the song

```yaml
effects:
  transitions:
    enabled: true
    type: crossfade
    duration: 0.5
```

| Type | Result |
|---|---|
| `crossfade` | Blend neighboring scenes without a black dip |
| `fade` | Fade each scene through black, as in the older renderer |
| `cut` | Join scenes directly; also used when transitions are disabled |

A plain overlap would shorten the visuals relative to the music. Instead, the
renderer adds cloned edge-frame handles around each boundary and blends those
handles. The crossfade is centered approximately on the original cut and the
full audio timeline is retained. Motion may briefly hold at the edges of a
blend. Transition duration is rounded to output frames and clamped for short
scenes. `transitions.json` records frame counts, handle lengths, and offsets.

Crossfading changes pixels, so it requires a final video encode. The cut/fade
join retains the existing stream-copy path. Scenes use a higher-quality
intermediate (`video.scene_crf`, default at most 18); final crossfades honor
`video.crf` and `video.preset`. Crossfades take more CPU/RAM than cuts, especially
on long timelines with many sources. The current graph opens the scene inputs
together; use fewer scenes or cuts for large jobs on constrained machines.

These transitions only affect visuals. Song audio and playlist order remain
unchanged; no audio crossfade, time stretch, or normalization is introduced.
Audio normalization still requires the separate production options.

Implementation uses FFmpeg's [xfade and tpad filters](https://ffmpeg.org/ffmpeg-filters.html).
Frame rounding can leave a small visual-duration difference; the workflow's
existing technical gate checks it against the audio rather than silently
accepting an incomplete render.
