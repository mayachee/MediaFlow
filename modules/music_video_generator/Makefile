.PHONY: install generate clean help

PYTHON = python

## Install: Install Python dependencies
install:
	$(PYTHON) -m pip install -r requirements.txt
	@echo "FFmpeg is required. Install it if not already present."
	@echo "  Windows: winget install ffmpeg"
	@echo "  macOS: brew install ffmpeg"
	@echo "  Linux: sudo apt install ffmpeg"

## Generate: Create music video from input/audio and input/images
generate:
	$(PYTHON) -u main.py

## Clean: Remove generated files
clean:
	@if exist output rmdir /S /Q output
	@if exist src\__pycache__ rmdir /S /Q src\__pycache__
	@if exist __pycache__ rmdir /S /Q __pycache__
	@echo "Cleaned!"

## Help: Show available targets
help:
	@echo "Music Video Generator - Usage:"
	@echo ""
	@echo "  make install    - Install Python dependencies"
	@echo "  make generate   - Create music video from audio + images"
	@echo "  make clean      - Remove generated output files"
	@echo "  make help       - Show this help message"
	@echo ""
	@echo "Outputs: output/music_video.mp4"