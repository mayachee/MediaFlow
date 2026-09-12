.PHONY: setup search download generate upload all clean help

PYTHON = python

## Setup: Install all dependencies (requires FFmpeg system-wide)
setup:
	@echo "=== Setting up YouTube Audio/Video Workflow ==="
	@echo "Installing youtube_automation dependencies..."
	cd youtube_automation && $(PYTHON) -m pip install -r requirements.txt && $(PYTHON) -m playwright install chromium
	@echo "Installing music_video_generator dependencies..."
	cd music_video_generator && $(PYTHON) -m pip install -r requirements.txt
	@echo "Installing automatic_YouTube_upload dependencies..."
	cd automatic_YouTube_upload && $(PYTHON) -m pip install -r requirements.txt
	@echo "Checking FFmpeg..."
	@(where ffmpeg >nul 2>nul || (echo "WARNING: FFmpeg not found. Install it:" && echo "  Windows: winget install ffmpeg" && echo "  macOS: brew install ffmpeg" && echo "  Linux: sudo apt install ffmpeg"))
	@echo "Setup complete!"

## Search: Find YouTube links from input.txt
search:
	@echo "=== Searching YouTube ==="
	cd youtube_automation && $(PYTHON) main.py

## Download: Download MP3 from found links
download:
	@echo "=== Downloading audio files ==="
	cd youtube_automation && $(PYTHON) download_mp3.py

## Generate: Create music video from audio + images
generate:
	@echo "=== Generating music video ==="
	cd music_video_generator && $(PYTHON) -u main.py

## Upload: Upload video to YouTube
upload:
	@echo "=== Uploading to YouTube ==="
	cd automatic_YouTube_upload && $(PYTHON) -u youtube_uploader.py \
		--video ../music_video_generator/output/music_video.mp4 \
		--title "My Music Video" \
		--description "Auto-generated music video" \
		--tags "music,video,lyrics" \
		--privacy public

## All: Full workflow (search -> download -> generate -> upload)
all: search download generate upload
	@echo "=== Full workflow complete! ==="

## Clean: Remove all generated files
clean:
	@echo "Cleaning generated files..."
	@if exist youtube_automation\youtube_links.txt del /Q youtube_automation\youtube_links.txt
	@if exist music_video_generator\output rmdir /S /Q music_video_generator\output
	@if exist automatic_YouTube_upload\token.pickle del /Q automatic_YouTube_upload\token.pickle
	@if exist automatic_YouTube_upload\*.log del /Q automatic_YouTube_upload\*.log
	@if exist youtube_automation\__pycache__ rmdir /S /Q youtube_automation\__pycache__
	@if exist music_video_generator\__pycache__ rmdir /S /Q music_video_generator\__pycache__
	@if exist music_video_generator\src\__pycache__ rmdir /S /Q music_video_generator\src\__pycache__
	@if exist automatic_YouTube_upload\__pycache__ rmdir /S /Q automatic_YouTube_upload\__pycache__
	@echo "Cleaned!"

## Help: Show available targets
help:
	@echo "YouTube Audio/Video Workflow - Global Makefile"
	@echo ""
	@echo "  make setup    - Install all dependencies and check FFmpeg"
	@echo "  make search   - Search YouTube for song links"
	@echo "  make download - Download MP3 files from links"
	@echo "  make generate - Create music video from audio + images"
	@echo "  make upload   - Upload video to YouTube"
	@echo "  make all      - Run full pipeline (search, download, generate, upload)"
	@echo "  make clean    - Remove all generated files"
	@echo "  make help     - Show this help"