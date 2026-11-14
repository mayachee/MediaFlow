.PHONY: install search download metadata pinterest all clean help

PYTHON = .venv/Scripts/python.exe
PIP = .venv/Scripts/pip.exe

## Install: Set up virtual environment and dependencies
install:
	python -m venv .venv
	$(PIP) install -r requirements.txt
	$(PYTHON) -m playwright install chromium

## Search: Find YouTube links from input.txt
search:
	$(PYTHON) main.py

## Download: Download MP3 from links in youtube_links.txt
download:
	$(PYTHON) download_mp3.py

## Download-trim: Download audio and trim leading/trailing silence
download-trim:
	$(PYTHON) download_mp3.py --trim

## Metadata: Generate AI-powered YouTube titles & descriptions from input.txt
metadata:
	$(PYTHON) generate_metadata.py

## Pinterest: After YouTube upload, extract images and upload to Pinterest
pinterest:
	$(PYTHON) pinterest_uploader.py --video-id $(VIDEO_ID)

## All: Generate metadata, search, and download
all: metadata search download

## Clean: Remove generated files
clean:
	del /Q youtube_links.txt 2>nul || true
	rmdir /S /Q downloads 2>nul || true
	del /Q *.mp3 2>nul || true
	del /Q metadata.json metadata.txt 2>nul || true
	rmdir /S /Q extracted_images 2>nul || true

## Help: Show available targets
help:
	@echo "Available targets:"
	@echo "  make install    - Create venv and install dependencies"
	@echo "  make search     - Find YouTube links from input.txt"
	@echo "  make download   - Download MP3 files from youtube_links.txt"
	@echo "  make download-trim - Download and trim silence from audio"
	@echo "  make metadata   - Generate AI-powered titles & descriptions"
	@echo "  make pinterest  - Extract images from YouTube video and upload to Pinterest"
	@echo "                   (requires VIDEO_ID=xxx, e.g. make pinterest VIDEO_ID=dQw4w9WgXcQ)"
	@echo "  make all        - Run search + download in one command"
	@echo "  make clean      - Remove generated files"
	@echo "  make help       - Show this help message"