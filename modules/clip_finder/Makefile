# Run here, or from the repository root with -f modules/clip_finder/Makefile.
# All user-supplied paths are relative to the directory where make is run.
.DEFAULT_GOAL := help
.DELETE_ON_ERROR:

CLIP_DIR := $(dir $(lastword $(MAKEFILE_LIST)))
ifeq ($(OS),Windows_NT)
PYTHON ?= py -3.11
else
PYTHON ?= python3
endif

COUNT ?= 10
MOOD ?= cinematic
PREVIEW_START ?= 0
PREVIEW_SECONDS ?= 15
LIBRARY_OPTION = $(if $(strip $(LIBRARY)),--library "$(LIBRARY)")
CLI = $(PYTHON) "$(CLIP_DIR)clip_library.py" $(LIBRARY_OPTION)
require = $(if $(strip $($(1))),,$(error Missing $(1). Run the help target for usage))

.PHONY: help setup search download import list highlight render-highlight export-timeline preview video demo test

help:
	@echo "Clip finder and reviewed footage library"
	@echo "setup             Install clip finder dependencies"
	@echo "search            AUDIO=path KEYWORDS=words [COUNT=10 MOOD=cinematic]"
	@echo "download          REPORT=candidates.json RANKS='1 3'"
	@echo "import            FILE=path [SOURCE_URL=url TITLE=text LICENSE=text]"
	@echo "list              List saved library assets"
	@echo "highlight         ASSET=id START=0 END=5 [TAGS='opening action' NOTE=text]"
	@echo "render-highlight  HIGHLIGHT=asset:highlight"
	@echo "export-timeline   HIGHLIGHTS='ref1 ref2' TIMELINE=new.json [SECONDS=n or AUDIO=path]"
	@echo "preview           AUDIO=path TIMELINE=path [PREVIEW_START=0 PREVIEW_SECONDS=15]"
	@echo "video             AUDIO=path TIMELINE=path (full song)"
	@echo "demo              Generate synthetic footage and render an offline example"
	@echo "test              Run offline clip finder and library tests"
	@echo "Optional: LIBRARY=path PYTHON=interpreter; quote values containing spaces."
	@echo "Rendering needs the music_video_generator dependencies and FFmpeg."

setup:
	$(PYTHON) -m pip install -r "$(CLIP_DIR)requirements.txt"

search:
	$(call require,AUDIO)
	$(PYTHON) "$(CLIP_DIR)find_matching_clips.py" --audio "$(AUDIO)" $(if $(strip $(KEYWORDS)),--keywords "$(KEYWORDS)") --mood "$(MOOD)" --count "$(COUNT)"

download:
	$(call require,REPORT)
	$(call require,RANKS)
	$(CLI) download --report "$(REPORT)" $(foreach rank,$(RANKS),--rank "$(rank)")

import:
	$(call require,FILE)
	$(CLI) import --file "$(FILE)" $(if $(strip $(SOURCE_URL)),--source-url "$(SOURCE_URL)") $(if $(strip $(TITLE)),--title "$(TITLE)") $(if $(strip $(LICENSE)),--license "$(LICENSE)")

list:
	$(CLI) list

highlight:
	$(call require,ASSET)
	$(call require,START)
	$(call require,END)
	$(CLI) highlight --asset "$(ASSET)" --start "$(START)" --end "$(END)" $(foreach tag,$(TAGS),--tag "$(tag)") $(if $(strip $(NOTE)),--note "$(NOTE)")

render-highlight:
	$(call require,HIGHLIGHT)
	$(CLI) render --highlight "$(HIGHLIGHT)"

export-timeline:
	$(call require,HIGHLIGHTS)
	$(call require,TIMELINE)
	$(if $(and $(strip $(SECONDS)),$(strip $(AUDIO))),$(error Choose SECONDS or AUDIO for export-timeline, not both))
	$(CLI) export $(foreach ref,$(HIGHLIGHTS),--highlight "$(ref)") --output "$(TIMELINE)" $(if $(strip $(SECONDS)),--seconds "$(SECONDS)") $(if $(strip $(AUDIO)),--audio "$(AUDIO)")

preview:
	$(call require,AUDIO)
	$(call require,TIMELINE)
	$(PYTHON) "$(CLIP_DIR)../../workflow.py" --audio "$(AUDIO)" --timeline "$(TIMELINE)" --preset preview --preview-start "$(PREVIEW_START)" --preview-seconds "$(PREVIEW_SECONDS)"

video:
	$(call require,AUDIO)
	$(call require,TIMELINE)
	$(PYTHON) "$(CLIP_DIR)../../workflow.py" --audio "$(AUDIO)" --timeline "$(TIMELINE)" --preset video

demo:
	$(PYTHON) "$(CLIP_DIR)demo_library.py"

test:
	$(PYTHON) -m unittest discover -s "$(CLIP_DIR)tests" -v
