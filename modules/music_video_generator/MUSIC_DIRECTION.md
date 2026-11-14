# Make the edit follow the music

The generator can now use the audio's detected beats, onsets, and changing
energy to direct the visuals. This happens locally inside this module; no model
download, external service, or upload is involved.

## Quick start from this folder

```powershell
# Thirty-second preview from the first selected track, starting at one minute
.\run.ps1 preview -Style cinematic -PreviewStart 60 -PreviewSeconds 30

# Pick an exact file; artwork still comes from input/images
.\run.ps1 preview -Audio "input/audio/my-song.mp3" -PreviewStart 0 -PreviewSeconds 30

# Full selected track once the preview looks right
.\run.ps1 generate -Audio "input/audio/my-song.mp3" -Style cinematic

# Generate using the configured audio folder (up to MaxSongs files)
.\run.ps1 generate -Style balanced -MaxSongs 2
```

Previews have unique folders under `output/preview-<timestamp>/` and do not
overwrite a full video. The original audio/artwork remain in `input/`. Preview
extraction only decodes the requested range before analyzing it. The preview
wrapper selects the first audio file; `-Audio` fixes the selection explicitly.
Relative paths in these commands are relative to this module's directory.

Equivalent direct command:

```powershell
.\.venv\Scripts\python.exe main.py --audio "input/audio/my-song.mp3" --style cinematic --preview-start 60 --preview-seconds 30
```

For previews of an explicit mapped timeline, continue using the root
`workflow.py --timeline ... --preset preview` command. Standalone range previews
are for automatic music direction, not trimming a pre-authored timeline.

## What follows the audio

1. The analyzer measures the actual audio at 22.05 kHz, extracting beats/onsets
   and a smoothed relative RMS envelope. Analysis is shared between timing and
   motion decisions instead of loading a track twice.
2. Automatic scene boundaries favor detected beats near the style's target shot
   length. Onset cues or measured-time spacing are used when beat candidates are
   unavailable. Song boundaries remain intact in playlists.
3. Relative energy controls camera travel: quiet passages get less movement;
   stronger passages allow slightly more. Very quiet sections can remain still.
4. Small, smoothly shaped zoom accents peak on detected beats. These are not
   flashes, brightness strobes, shake, or modifications to the soundtrack.
5. Crossfades stay centered around the chosen visual boundaries while retaining
   the complete audio timeline. Their default duration follows the selected style.

## Styles

| Style | Normal shot range | Camera zoom range | Crossfade | Intended starting point |
|---|---|---|---|---|
| `cinematic` | 6–12 seconds | 1.025–1.075× | 0.9 s | Soundtracks, contemplative music, slower montage |
| `balanced` | 4–9 seconds | 1.035–1.10× | 0.6 s | General music presentations |
| `energetic` | 2–6 seconds | 1.045–1.12× | 0.3 s | More frequent cuts and stronger accents |

Very short tracks or final sections can be shorter than the normal range.
Scene lengths and crossfades are quantized to video frames. These are starting
presets, not an automatic guarantee of artistic quality or perfect beat tracking.
The detector does not understand lyrics, emotions, choruses, downbeats, or the
semantic content of an image. Voiceovers, ambient music, and changing tempos can
produce imperfect beat estimates; review the result or use an explicit timeline.

## Configuration

```yaml
direction:
  enabled: true
  edit_mode: montage
  style: cinematic
  beat_accents: false
  follow_style_transitions: true

effects:
  transitions:
    enabled: true
    type: crossfade
    duration: 0.5
    maximum_inputs: 6
```

- `enabled: false` restores the earlier automatic scene-selection behavior.
- `edit_mode: montage` varies wide/medium/closer framings, limits automatic
  static holds to roughly 3–6.5 seconds, and chooses clean cuts around stronger
  passages with short blends elsewhere. `classic` retains the longer style ranges
  in the table above. Explicit timelines retain their authored framing/timing.
- `direction.focal_points` maps exact artwork filenames to normalized `[x, y]`
  coordinates. These guide the optional closer framing; they are editorial
  anchors, not automatic subject detection. Crop factors alternate 1, 1.22, 1.35.
- `beat_accents: false` keeps music-based pacing and energy-directed motion,
  while removing the small zoom accents.

Montage mode is an edited treatment of still artwork, not generated character
animation. Real action or natural subject movement requires appropriate video
clips. Colors remain as supplied: grade or replace mismatched artwork deliberately
rather than expecting a global effect to resolve every palette difference.
- `follow_style_transitions: false` uses the transition duration you specify
  under `effects.transitions` instead of the style default.
- `--no-beat-sync`, or `beat_detection.enabled: false`, disables audio-driven
  direction and keeps the previous timing behavior.
- Global `image.motion: still` remains still. Explicit timeline scene motions and
  times are respected; direction can adjust their strength when applicable.
- `framing: fit` and source video clips do not receive image-camera accents.
  Source video retains its own movement; no synthetic shake is added.

## Long-track rendering

A long soundtrack can produce many shots. Crossfade renders now open at most
`maximum_inputs` scenes at once (2–16; default 6). Longer edits are combined in
bounded batches with lossless H.264 intermediates, keeping the original boundary
durations. Temporary batch files are removed after successful assembly. This
reduces open-input pressure, but long 1080p edits still need substantial CPU time
and temporary disk space. Failed renders preserve source inputs and report errors.

Still images are decoded at one frame per second, while zoompan/fps filters
produce the configured video frame rate. This avoids repeatedly decoding a large
PNG for every output frame. Supersampling can still be set to 1 to reduce cost.
Audio remains unchanged apart from explicitly selecting a preview interval and
the existing final AAC encoding. There is no automatic normalization, pitch,
speed, or EQ change in musical direction.

## Inspect and test

- `scene-plan.json`: effective shot boundaries, artwork, motion, zoom range,
  relative energy, and beat accents.
- `music-analysis.json`: detected cues, energy curve, source tracks, preview
  selection, and whether music direction was active or fell back.
- `transitions.json`: frame counts, crossfade handles, and batch information.
- `selected-audio/`: the exact WAV excerpt used for a standalone preview.

Run the module's focused tests with:

```powershell
.\run.ps1 test
```

They check cue-aligned pacing, energy response, preserved authored settings,
actual audio analysis, preview extraction, visible rendered beat accents, and
bounded crossfades with intact audio/frame counts. The workspace regression
tests remain available via the root `run.ps1 test` command.
