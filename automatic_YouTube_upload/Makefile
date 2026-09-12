.PHONY: install upload clean help

PYTHON = python

## Install: Install Python dependencies
install:
	$(PYTHON) -m pip install -r requirements.txt

## Upload: Upload a video to YouTube
upload:
	$(PYTHON) -u youtube_uploader.py \
		--video ../music_video_generator/output/music_video.mp4 \
		--title "My Music Video" \
		--description "Auto-generated music video" \
		--tags "music,video,lyrics" \
		--privacy public

## Upload-thumbnail: Upload only a thumbnail to an existing video
upload-thumbnail:
	$(PYTHON) -u youtube_uploader.py \
		--video-id $(VIDEO_ID) \
		--thumbnail ../music_video_generator/input/images/$(THUMBNAIL)

## Clean: Remove token and logs
clean:
	del /Q token.pickle 2>nul || true
	del /Q *.log 2>nul || true
	@echo "Cleaned!"

## Help: Show available targets
help:
	@echo "YouTube Uploader - Usage:"
	@echo ""
	@echo "  make install               - Install Python dependencies"
	@echo "  make upload                - Upload music video to YouTube"
	@echo "  make upload-thumbnail VIDEO_ID=id THUMBNAIL=file.jpg - Upload just thumbnail"
	@echo "  make clean                 - Remove token.pickle and logs"
	@echo "  make help                  - Show this help"