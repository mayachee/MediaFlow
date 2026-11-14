# Makefile - vocal-remover
# Splits songs into instrumental + vocal stems with demucs.
#
# Prerequisites (run once):
#   make install            # creates .venv, installs torch (CPU) + demucs
#   ffmpeg on PATH; yt-dlp on PATH for 'download'/'track'/'url'
#
# Usage:
#   make install            Set up .venv
#   make check              Verify python, ffmpeg, yt-dlp, powershell are on PATH
#   make local [FILE=<f>]   Split newest file in DOWNLOADS (or FILE=<name|path>)
#   make latest             Alias for 'local'
#   make url URL=<link>     Download from URL, then split
#   make download           Run ../automatic_upload/run.ps1 download
#   make track              Download, then split the result
#   make clean              Remove output/ and work/
#   make distclean          Also remove input/

PYTHON    ?= python
VENV_DIR  := .venv
MODEL     ?= htdemucs
URL       ?=
FILE      ?=
QUALITY   ?= 320
SCRIPT_DIR := scripts

# Sibling project that sources come from
ifeq ($(OS),Windows_NT)
	UPLOAD_DIR ?= ../automatic_upload
	DOWNLOADS  ?= ..\automatic_upload\downloads
	PSHELL     ?= powershell
	NULL       := >NUL 2>&1
	HAVE       = where $(1) $(NULL)
	VENV_PY    := $(VENV_DIR)\Scripts\python.exe
	PS1_EXT    := .ps1
else
	UPLOAD_DIR ?= ../automatic_upload
	DOWNLOADS  ?= ../automatic_upload/downloads
	PSHELL     ?= pwsh
	NULL       := >/dev/null 2>&1
	HAVE       = command -v $(1) $(NULL)
	VENV_PY    := $(VENV_DIR)/bin/python
	PS1_EXT    := .sh
endif

.PHONY: help install check local latest url download track clean distclean

help: ## Show available targets
	@echo "vocal-remover"
	@echo ""
	@echo "  make install            Set up .venv (torch CPU + demucs)"
	@echo "  make check              Verify python, ffmpeg, yt-dlp, powershell on PATH"
	@echo "  make local [FILE=<f>]   Split newest file in DOWNLOADS (or a specific one)"
	@echo "  make latest             Alias for 'local'"
	@echo "  make url URL=<link>     Download from URL, then split"
	@echo "  make download           Run ../automatic_upload/run.ps1 download"
	@echo "  make track              Download, then split the result"
	@echo "  make clean              Remove output/ and work/"
	@echo "  make distclean          Also remove input/"
	@echo ""
	@echo "  MODEL=htdemucs_ft       demucs model (default: htdemucs)"
	@echo "  DOWNLOADS=<dir>         Source folder (default: ../automatic_upload/downloads)"
	@echo "  PSHELL=pwsh             PowerShell executable to use for the scripts"

install: ## Create .venv and install torch (CPU) + demucs
	$(PYTHON) -m venv $(VENV_DIR)
	$(VENV_PY) -m pip install --upgrade pip
	$(VENV_PY) -m pip install -r requirements.txt
	@echo "Install complete. Run: make local"

check: ## Verify required external tools are available
	@echo "Required: $(PYTHON), ffmpeg, yt-dlp, $(PSHELL)"
	@$(call HAVE,$(PYTHON)) || exit 1
	@$(call HAVE,ffmpeg) || exit 1
	@$(call HAVE,yt-dlp) || exit 1
	@$(call HAVE,$(PSHELL)) || exit 1
	@echo "All required tools are available."

local: check ## Split newest file in DOWNLOADS, or FILE=<name|path>
	$(PSHELL) -NoProfile -ExecutionPolicy Bypass -File $(SCRIPT_DIR)\remove_vocals_local$(PS1_EXT) -Model $(MODEL) -Downloads "$(DOWNLOADS)" $(if $(strip $(FILE)),-File "$(FILE)",)

latest: ## Alias for 'local'
	@$(MAKE) local

url: check ## Download URL= then split
ifeq ($(strip $(URL)),)
	@echo ERROR: URL is required. Usage: make url URL=https://youtu.be/link
	@exit 1
else
	$(PSHELL) -NoProfile -ExecutionPolicy Bypass -File $(SCRIPT_DIR)\remove_vocals$(PS1_EXT) -Url "$(URL)" -Model $(MODEL)
endif

download: check ## Run ../automatic_upload/run.ps1 download
	cd $(UPLOAD_DIR) && $(PSHELL) -NoProfile -ExecutionPolicy Bypass -File run.ps1 download

track: download ## Download, then split the result
	@$(MAKE) local

clean: ## Remove output/ and work/
	-$(PSHELL) -NoProfile -ExecutionPolicy Bypass -Command "Remove-Item -LiteralPath 'output','work' -Recurse -Force -ErrorAction SilentlyContinue"
	@echo "Cleaned output/ and work/"

distclean: clean ## Also remove input/
	-$(PSHELL) -NoProfile -ExecutionPolicy Bypass -Command "Remove-Item -LiteralPath 'input' -Recurse -Force -ErrorAction SilentlyContinue"
	@echo "Removed input/"
