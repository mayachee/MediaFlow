# Find online clips for a song

## Find and download from a title or keywords

In **Scripts Studio**, click **Find & download clips** in the left sidebar or
the home screen's clip card. Enter a video idea, title, or keywords, choose the
number of clips, and click **Find & download**. For example:
`ocean waves at sunset` or `cinematic forest mountains sunrise`.
No audio file is required. Audio filename context and extra search settings are
optional under **Advanced settings**.

Studio searches and ranks candidates, automatically downloads the requested
number where possible, and tries other ranked candidates if a source fails.
Downloaded results appear with video previews. Click **Use clips in a music
video** to select the downloaded visuals in the creator, then add your audio.
The same button is available when reopening the job from Activity & results.

Each job has a `visuals/` folder ready for the renderer, including when original
videos were reused from the library cache. Originals remain in the shared
library. Full candidate videos are downloaded, rather than automatically chosen
highlight ranges. Matches use metadata and your words; review the actual scenes
before rendering. A partial download retains the clips that succeeded and
records the shortfall and source errors in `candidates.json`.

CLI equivalent:

```powershell
python modules/clip_finder/find_matching_clips.py --title "cinematic forest mountains sunrise" --download-top 3 --download-mode best-available --count 12
```

For a shortlist without downloading:

```powershell
python modules/clip_finder/find_matching_clips.py --keywords "sports cars drifting footage"
```

`find_matching_clips.py` searches YouTube and saves a ranked shortlist. It uses
the song filename as context or, preferably, your visual story keywords. It
does not upload the song or require a YouTube account/API key.

This module handles discovery and optional downloads independently of the renderer.
Its only handoff is a local clips folder.

**New:** [Reusable library, reviewed highlight ranges, and renderer timelines](LIBRARY.md).
Downloads now import into the shared library, and repeated source URLs reuse
verified cached originals. Use exported highlight timelines as the stable
handoff to the renderer.

## Make commands

From the **repository root**, use `mingw32-make` on this Windows installation
(or `make` on systems with GNU Make under that name):

```powershell
mingw32-make clips-help
mingw32-make clips-test
mingw32-make clips-search "AUDIO=modules/music_video_generator/input/audio/my song.mp3" "KEYWORDS=forest mountains sunrise footage"
mingw32-make clips-download "REPORT=modules/clip_finder/output/search/RESULT/candidates.json" "RANKS=1 3"
mingw32-make clips-list
mingw32-make clips-highlight ASSET=ASSET_ID START=128 END=133 "TAGS=opening landscape"
mingw32-make clips-export-timeline "HIGHLIGHTS=ASSET_ID:HIGHLIGHT_ID ASSET_ID:SECOND_ID" TIMELINE=runs/my-timeline.json SECONDS=10
mingw32-make clips-preview "AUDIO=modules/music_video_generator/input/audio/my song.mp3" TIMELINE=runs/my-timeline.json PREVIEW_START=60 PREVIEW_SECONDS=10
```

Replace `RESULT`, asset IDs, and highlight IDs with the values printed by the
preceding commands. Review the shortlist before downloading and inspect each
source before choosing its highlight timestamps. `clips-search` only searches;
downloads require `clips-download`. Export needs a new filename and sufficient
reviewed footage to cover the requested duration. Match `SECONDS` to
`PREVIEW_SECONDS` for an excerpt. For a full song, export with `AUDIO=path`
instead of `SECONDS`, then use `clips-video` with that audio and timeline.
Normalization remains off by default.

Other targets include `clips-setup` (install this module's dependencies),
`clips-import FILE=path` (copy local footage into the library),
`clips-render-highlight HIGHLIGHT=asset:highlight`, and `clips-demo` (generate
synthetic footage and render an offline example). Rendering and the demo also
require the music video generator dependencies, FFmpeg, and ffprobe.

Every supplied path is relative to the directory where you run Make. All library
commands accept `LIBRARY=path`; use the same value throughout a custom-library
workflow. Override the interpreter with `"PYTHON=py -3.11"` or a quoted Python
executable path if needed. From this module directory, the same targets are
available without the `clips-` prefix, for example `mingw32-make test`.

From this module folder:

```powershell
py -3.11 -m pip install -r requirements.txt
.\run.ps1 search -Audio "../music_video_generator/input/audio/my-song.mp3" -Keywords "nature forests mountains"
```

Results go into a new `output/search/<timestamp>/` directory:

- `README.md`: clickable candidate links, durations, and matching words.
- `candidates.json`: queries, ranking reasons, channel/source information, and errors.
- `clips/`: created only when downloads are explicitly requested.

For more precise scene searches, repeat `--query` with the direct Python command:

```powershell
py -3.11 find_matching_clips.py --audio "../music_video_generator/input/audio/my-song.mp3" --keywords "nature forests" --query "forest waterfall drone footage" --query "mountain sunrise landscape footage" --count 10
```

Candidates are deduplicated by video ID, filtered by duration (12–600 seconds by
default), and ranked by topic words. Reaction/tutorial/lyrics/music-video results
receive penalties. Live/upcoming videos are excluded when the search metadata
identifies them. Unknown durations and licenses are displayed as unknown.

## Matching limitations

This is metadata-based discovery, not a model that watches scenes, understands
lyrics, recognizes a song, or finds exact highlight timestamps. `--mood` adds
search wording; it does not infer an emotion from the audio. Search relevance
and upload descriptions can be inaccurate. Review candidates before choosing
them. The renderer's separate local analysis handles musical pacing after you
have selected suitable visual sources.

## Optional downloads and rendering

```powershell
# Opt in to downloading the top two candidates, at up to 720p
.\run.ps1 search -Audio "../music_video_generator/input/audio/my-song.mp3" -Keywords "nature forests" -DownloadTop 2

# Use that result's actual clips folder in the renderer
.\..\music_video_generator\run.ps1 preview -Audio "input/audio/my-song.mp3" -Visuals "../clip_finder/output/search/RESULT/clips" -PreviewStart 0 -PreviewSeconds 30
```

Replace `RESULT` with the directory printed by the search. Downloads are full
candidate videos, limited to 300 MB each; download errors are retained in the
report. The generator uses your song as audio and ignores the clips' own sound.
It currently plays/loops clips from their beginning; exact highlight selection
is a separate editing step. Online search needs internet access and yt-dlp's
extractors can stop working when a provider changes its site.

A matching title, public URL, or successful download does not grant permission
to reuse a video. The report records available license metadata without treating
it as verified clearance. No accounts, browser cookies, or private sources are
used by this tool.

The search uses the [yt-dlp Python API](https://github.com/yt-dlp/yt-dlp#embedding-yt-dlp).
Run `run.ps1 test` for offline ranking/filtering tests. Live search and download
outcomes are recorded separately and are not established by those offline tests.
