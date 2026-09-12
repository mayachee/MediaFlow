.PHONY: install search download all clean help

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

## All: Search and download in one go
all: search download

## Clean: Remove generated files
clean:
	del /Q youtube_links.txt 2>nul || true
	rmdir /S /Q downloads 2>nul || true
	del /Q *.mp3 2>nul || true

## Help: Show available targets
help:
	@echo "Available targets:"
	@echo "  make install    - Create venv and install dependencies"
	@echo "  make search     - Find YouTube links from input.txt"
	@echo "  make download   - Download MP3 files from youtube_links.txt"
	@echo "  make all        - Run search then download"
	@echo "  make clean      - Remove generated files"
	@echo "  make help       - Show this help message"