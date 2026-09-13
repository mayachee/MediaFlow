.PHONY: setup search download generate upload all clean help

PYTHON := python

# Colors for terminal output
BOLD   := \033[1m
GREEN  := \033[32m
YELLOW := \033[33m
BLUE   := \033[34m
RESET  := \033[0m

# NOTE: On Windows use '.\run.ps1 <target>' instead of make.
# This Makefile requires GNU Make and Unix-like tools (Linux/macOS/Git Bash).

## Setup: Install all dependencies and check FFmpeg
setup:
	@echo "$(BOLD)$(BLUE)=== YouTube Audio/Video Workflow - Setup ===$(RESET)"
	@echo "$(BOLD)$(GREEN)>>> Installing dependencies...$(RESET)"
	cd youtube_automation && $(PYTHON) -m pip install -r requirements.txt && $(PYTHON) -m playwright install chromium
	cd music_video_generator && $(PYTHON) -m pip install -r requirements.txt
	cd automatic_YouTube_upload && $(PYTHON) -m pip install -r requirements.txt
	@echo "$(BOLD)$(GREEN)>>> Checking FFmpeg...$(RESET)"
	@command -v ffmpeg >/dev/null 2>&1 || (echo "$(YELLOW)WARNING: FFmpeg not found.$(RESET)"; echo "  Linux: sudo apt install ffmpeg"; echo "  macOS: brew install ffmpeg"; echo "  Windows: winget install ffmpeg")
	@echo "$(BOLD)$(GREEN)Setup complete!$(RESET)"

## Search: Find YouTube links from input.txt
search:
	@echo "$(BOLD)$(GREEN)>>> Searching YouTube...$(RESET)"
	cd youtube_automation && $(PYTHON) main.py
	@echo "$(GREEN)OK: youtube_links.txt created$(RESET)"

## Download: Download MP3 from found links
download:
	$(call step,Downloading audio files...)
	cd youtube_automation && $(PYTHON) download_mp3.py
	$(call ok,Audio downloads complete)

## Copy: Move downloaded audio to music_video_generator input
copy:
	$(call step,Copying audio files...)
	mkdir -p music_video_generator/input/audio
	cp -f youtube_automation/downloads/*.mp3 music_video_generator/input/audio/ 2>/dev/null || true
	cp -f youtube_automation/downloads/*.webm music_video_generator/input/audio/ 2>/dev/null || true
	cp -f youtube_automation/downloads/*.mp4 music_video_generator/input/audio/ 2>/dev/null || true
	$(call ok,Audio files copied)

## Generate: Create music video from audio + images
generate:
	@echo "$(BOLD)$(GREEN)>>> Generating music video...$(RESET)"
	cd music_video_generator && $(PYTHON) -u main.py
	@echo "$(GREEN)OK: output/music_video.mp4 created$(RESET)"

## Upload: Upload video to YouTube
upload:
	@echo "$(BOLD)$(GREEN)>>> Uploading to YouTube...$(RESET)"
	cd automatic_YouTube_upload && $(PYTHON) -u youtube_uploader.py \
		--video ../music_video_generator/output/music_video.mp4 \
		--title "My Music Video" \
		--description "Auto-generated music video" \
		--tags "music,video,lyrics" \
		--privacy public
	@echo "$(GREEN)OK: Upload complete$(RESET)"

## All: Full workflow (search -> download -> copy -> generate -> upload)
all: search download copy generate upload
	@echo ""
	@echo "$(BOLD)$(GREEN)=========================================$(RESET)"
	@echo "$(BOLD)$(GREEN) Full workflow complete! Video uploaded.   $(RESET)"
	@echo "$(BOLD)$(GREEN)=========================================$(RESET)"

## Clean: Remove all generated files
clean:
	@echo "$(BOLD)$(YELLOW)=== Cleaning all generated files ===$(RESET)"
	@echo "$(YELLOW)  Cleaning youtube_automation...$(RESET)"
	rm -f youtube_automation/youtube_links.txt
	rm -rf youtube_automation/__pycache__ youtube_automation/downloads
	@echo "$(YELLOW)  Cleaning music_video_generator...$(RESET)"
	rm -rf music_video_generator/output music_video_generator/__pycache__ music_video_generator/src/__pycache__
	@echo "$(YELLOW)  Cleaning automatic_YouTube_upload...$(RESET)"
	rm -f automatic_YouTube_upload/token.pickle automatic_YouTube_upload/*.log
	rm -rf automatic_YouTube_upload/__pycache__
	@echo "$(BOLD)$(GREEN)=== All cleaned! ===$(RESET)"

## Help: Show available targets
help:
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
	@echo "  make copy     - Copy downloads to music_video_generator input"
	@echo "  make generate - Create music video from audio + images"
	@echo "  make upload   - Upload video to YouTube"
	@echo "  make all      - Run full pipeline (search -> download -> copy -> generate -> upload)"
	@echo "  make clean    - Remove all generated files"
	@echo "  make help     - Show this help message"