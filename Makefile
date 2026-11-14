.DEFAULT_GOAL := help
.PHONY: studio
studio:
	$(PYTHON) script_manager.py

.PHONY: create-video
create-video:
	$(PYTHON) create_video.py

.PHONY: setup search download metadata copy download-trim generate upload all full clean help

# Independent clip library workflow; paths stay relative to this directory.
CLIP_TARGETS := help setup search download import list highlight render-highlight export-timeline preview video demo test
.PHONY: $(addprefix clips-,$(CLIP_TARGETS))
$(addprefix clips-,$(CLIP_TARGETS)):
	$(MAKE) -f modules/clip_finder/Makefile $(patsubst clips-%,%,$@)

.PHONY: doctor test smoke
doctor:
	$(PYTHON) tools/doctor.py --output docs/health-check.json

test:
	$(PYTHON) -m unittest discover -s tests -v

smoke:
	$(PYTHON) tools/smoke_media.py

PYTHON := python

# Colors for terminal output
BOLD   := \033[1m
GREEN  := \033[32m
YELLOW := \033[33m
BLUE   := \033[34m
RESET  := \033[0m

# Helper functions for consistent output
step = @echo "$(BOLD)$(GREEN)>>> $(1)$(RESET)"
ok = @echo "$(GREEN)OK: $(1)$(RESET)"

# Legacy workflow targets require GNU Make and Unix-like tools.
# On Windows use '.\run.ps1 <target>' for those, or mingw32-make clips-help
# for the independent clip library targets (no Unix utilities required).

## Setup: Install all dependencies and check FFmpeg
setup:
	@echo "$(BOLD)$(BLUE)=== YouTube Audio/Video Workflow - Setup ===$(RESET)"
	@echo "$(BOLD)$(GREEN)>>> Installing dependencies...$(RESET)"
	cd modules/automatic_upload && $(PYTHON) -m pip install -r requirements.txt && $(PYTHON) -m playwright install chromium
	cd modules/music_video_generator && $(PYTHON) -m pip install -r requirements.txt
	cd modules/automatic_YouTube_upload && $(PYTHON) -m pip install -r requirements.txt
	@echo "$(BOLD)$(GREEN)>>> Checking FFmpeg...$(RESET)"
	@command -v ffmpeg >/dev/null 2>&1 || (echo "$(YELLOW)WARNING: FFmpeg not found.$(RESET)"; echo "  Linux: sudo apt install ffmpeg"; echo "  macOS: brew install ffmpeg"; echo "  Windows: winget install ffmpeg")
	@echo "$(BOLD)$(GREEN)Setup complete!$(RESET)"

## Search: Find YouTube links from input.txt
search:
	@echo "$(BOLD)$(GREEN)>>> Searching YouTube...$(RESET)"
	cd modules/automatic_upload && $(PYTHON) main.py
	@echo "$(GREEN)OK: youtube_links.txt created$(RESET)"

## Download: Download MP3 from found links
download:
	$(call step,Downloading audio files...)
	cd modules/automatic_upload && $(PYTHON) download_mp3.py
	$(call ok,Audio downloads complete)

## Download-trim: Download audio and trim leading/trailing silence
download-trim:
	@echo "$(BOLD)$(GREEN)>>> Downloading + trimming silence...$(RESET)"
	cd modules/automatic_upload && $(PYTHON) download_mp3.py --trim
	@echo "$(GREEN)OK: audio files trimmed$(RESET)"

## Metadata: Generate AI-powered titles and descriptions from input.txt
metadata:
	@echo "$(BOLD)$(GREEN)>>> Generating AI metadata...$(RESET)"
	cd modules/automatic_upload && $(PYTHON) generate_metadata.py
	@echo "$(GREEN)OK: metadata.json and metadata.txt created$(RESET)"

## Copy: Move downloaded audio to modules/music_video_generator input
copy:
	$(call step,Copying audio files...)
	mkdir -p modules/music_video_generator/input/audio
	cp -f modules/automatic_upload/downloads/*.mp3 modules/music_video_generator/input/audio/ 2>/dev/null || true
	cp -f modules/automatic_upload/downloads/*.webm modules/music_video_generator/input/audio/ 2>/dev/null || true
	cp -f modules/automatic_upload/downloads/*.mp4 modules/music_video_generator/input/audio/ 2>/dev/null || true
	$(call ok,Audio files copied)

## Generate: Create music video from audio + images
generate:
	@echo "$(BOLD)$(GREEN)>>> Generating music video...$(RESET)"
	cd modules/music_video_generator && $(PYTHON) -u main.py
	@echo "$(GREEN)OK: output/music_video.mp4 created$(RESET)"

## Upload: Upload video to YouTube
upload:
	@echo "$(BOLD)$(GREEN)>>> Uploading to YouTube...$(RESET)"
	cd modules/automatic_YouTube_upload && $(PYTHON) -u youtube_uploader.py \
		--video ../music_video_generator/output/music_video.mp4 \
		--metadata ../automatic_upload/metadata.json \
		--privacy public
	@echo "$(GREEN)OK: Upload complete$(RESET)"

## All: Full workflow (search -> download -> metadata -> copy -> generate -> upload)
all: search download metadata copy generate upload
	@echo ""
	@echo "$(BOLD)$(GREEN)=========================================$(RESET)"
	@echo "$(BOLD)$(GREEN) Full workflow complete! Video uploaded.   $(RESET)"
	@echo "$(BOLD)$(GREEN)=========================================$(RESET)"

## Full: Smart pipeline with fallbacks (search + download + AI metadata + video + upload)
full:
	@echo "$(BOLD)$(GREEN)>>> Running full pipeline with smart fallbacks...$(RESET)"
	$(PYTHON) pipelines/run_all.py --max-songs 3
	@echo "$(GREEN)OK: Pipeline complete!$(RESET)"

## Clean: Remove all generated files
clean:
	@echo "$(BOLD)$(YELLOW)=== Cleaning all generated files ===$(RESET)"
	@echo "$(YELLOW)  Cleaning automatic_upload...$(RESET)"
	rm -f modules/automatic_upload/youtube_links.txt
	rm -rf modules/automatic_upload/__pycache__ modules/automatic_upload/downloads
	rm -f modules/automatic_upload/metadata.json modules/automatic_upload/metadata.txt
	@echo "$(YELLOW)  Cleaning music_video_generator...$(RESET)"
	rm -rf modules/music_video_generator/output modules/music_video_generator/__pycache__ modules/music_video_generator/src/__pycache__
	rm -f modules/music_video_generator/input/audio/*.mp3 modules/music_video_generator/input/audio/*.webm modules/music_video_generator/input/audio/*.wav
	rm -f modules/music_video_generator/input/images/* 2>/dev/null || true
	@echo "$(YELLOW)  Cleaning automatic_YouTube_upload...$(RESET)"
	rm -f modules/automatic_YouTube_upload/token.pickle modules/automatic_YouTube_upload/*.log
	rm -rf modules/automatic_YouTube_upload/__pycache__
	@echo "$(BOLD)$(GREEN)=== All cleaned! ===$(RESET)"

## Help: Show available targets
help:
	@echo "  make studio - Open Scripts Studio for all workspace tools"
	@echo "  make create-video - Open the desktop music video creator"
	@echo "  make clips-help - Clip search, library, highlights and video commands"
	@echo "$(BOLD)$(BLUE)"
	@echo "+----------------------------------------------------+"
	@echo "|  YouTube Audio/Video Workflow - Makefile            |"
	@echo "+----------------------------------------------------+"
	@echo "$(RESET)"
	@echo ""
	@echo "$(BOLD)$(GREEN)Targets:$(RESET)"
	@echo "  make setup    - Install all dependencies and check FFmpeg"
	@echo "  make search   - Search YouTube for song links"
	@echo "  make download - Download MP3 files from links"
	@echo "  make download-trim - Download and trim silence from audio"
	@echo "  make metadata - Generate AI-powered titles & descriptions"
	@echo "  make copy     - Copy downloads to video generator input"
	@echo "  make generate - Create music video from audio + images"
	@echo "  make upload   - Upload video to YouTube"
	@echo "  make all      - Run full pipeline (search -> download -> metadata -> copy -> generate -> upload)"
	@echo "  make full     - Smart pipeline with yt-dlp fallbacks (run_all.py)"
	@echo "  make clean    - Remove all generated files"
	@echo "  make help     - Show this help message"
