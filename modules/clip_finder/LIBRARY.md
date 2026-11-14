# Reusable footage and reviewed highlights

The clip finder owns the media library. The music-video generator receives a
timeline of reviewed clips; it does not manage searches, downloads, or originals.
Library operations require `ffmpeg` and `ffprobe` on PATH. Local import/selection
uses Python's standard library; online downloads additionally require yt-dlp.

```text
Search shortlist -> select ranks -> download/import -> library original
                                                        |
                                   review start/end ranges and tags
                                                        |
                                      cached silent highlight MP4s
                                                        |
                                      timeline.json + source records
                                                        |
                                           music_video_generator
```

## Download selected results, without searching again

Run commands from `modules/clip_finder`. Replace the example report directory
with the one printed by your search:

```powershell
py -3.11 clip_library.py download --report "output/search/RESULT/candidates.json" --rank 2 --rank 4
```

The download report prints asset IDs and canonical library paths. Existing
source URLs are reused after checking the cached original's checksum. Newly
downloaded videos are inspected and fully decoded before import. Search-time
`--download-top` also imports into the same library automatically.

Use your own local footage as well:

```powershell
$asset = py -3.11 clip_library.py import --file "C:/footage/my-video.mp4" --source-url "https://example.com/source" --title "City at night" --license "My recorded permission notes" | ConvertFrom-Json
$asset.id
```

Source URL/title/license fields record what you supplied or what the provider
reported. They do not independently verify permission. `--quick` performs
metadata-only inspection instead of the default full decode and is recorded as
such. Import keeps the original local file and stores a separate verified copy.

## Select the exact usable moments

Watch the original first, then record the ranges you actually want:

```powershell
$first = py -3.11 clip_library.py highlight --asset $asset.id --start 12 --end 17 --tag city --tag quiet --note "Wide skyline" | ConvertFrom-Json
$second = py -3.11 clip_library.py highlight --asset $asset.id --start 40 --end 46 --tag action --note "Character enters frame" | ConvertFrom-Json
```

Every selection prints a full `ASSET_ID:HIGHLIGHT_ID` reference. An asset's
unique checksum prefix (at least six hexadecimal characters) can also be used.
Ranges are checked against measured duration. Different ranges/tags produce
different selection IDs. Tags are descriptive metadata, not an automatic claim
that a scene matches a lyric or a musical event.

Render a selection if you want to inspect it separately:

```powershell
py -3.11 clip_library.py render --highlight $first.reference
```

This precisely seeks to the selected source time and re-encodes that range into
a silent MP4. It avoids keyframe-only copy cuts and removes the footage's audio
so it cannot accidentally be mixed into the song. Original video/audio remain
untouched. Repeated rendering reuses the cached highlight when its checksum
matches. Create a new highlight to revise a range rather than editing cached JSON.

## Export a renderer timeline

```powershell
py -3.11 clip_library.py export --highlight $first.reference --highlight $second.reference --seconds 11 --output "output/my-edit/timeline.json"
```

The order of `--highlight` options is your edit order. You can alternatively
use `--audio "music.wav"` to require coverage for that audio's measured duration.
Without either option, the timeline covers the combined selected ranges.

The tool fails if there is insufficient reviewed footage. It does not silently
loop five seconds of footage to cover a three-minute song. Add more highlights
or export a shorter review version. The final selected clip can be shortened to
the requested duration. A new timeline filename is required for another edit.

JSON is valid input for the generator's YAML timeline loader. The export contains
the clip paths, planned duration, and provenance; a companion `.sources.json`
records source URLs/licenses, original ranges, asset IDs, and clip checksums.
The generator checks the planned duration against the chosen music and saves
the provenance in `scene-plan.json`. Root workflow job copies also retain it.

From the renderer folder:

```powershell
.\.venv\Scripts\python.exe main.py --audio "path/to/music.wav" --timeline "../clip_finder/output/my-edit/timeline.json"
```

For an explicitly short timeline, select an audio excerpt of the same duration,
or use the root workflow with `--preset preview --preview-seconds 11` and your
exported timeline. A longer timeline may also be cropped by the root preview
workflow. Check the chosen excerpt's narrative fit yourself.

## Storage layout

```text
library/
  assets/<full-sha256>/
    original.mp4               canonical original (extension can differ)
    asset.json                 source records + measured media properties
    highlights/<range-id>.json start/end, tags, notes
    highlights/<range-id>.mp4  derived silent clip
    highlights/<range-id>.render.json
  downloads/<job>/             staging files and download report
```

`--library <folder>` before the subcommand selects another library. Content
hashes deduplicate identical files even when names differ. A cached source URL
reuses the recorded version; detecting a later replacement on the remote site
is not implemented. Metadata operations are intended for one writer at a time.
Library originals and cached renders are checked for modification before reuse.
The library is ignored by Git, and no automatic deletion/retention job is run.
Download staging files can consume additional space; the library's canonical
paths and highlight timelines are the stable handoff, not a staging `clips/` folder.

## Try it without downloading anything

```powershell
py -3.11 demo_library.py
.\run.ps1 test
```

The demo generates red/blue source footage and audio, imports it twice to check
reuse, selects later moments, exports a timeline, and renders a small video with
provenance attached. Its artifacts and results are under `output/library-demo/`.
Tests verify the trimmed clip actually starts in the later blue section, range
validation, deduplication, checksum corruption handling, and coverage validation.
