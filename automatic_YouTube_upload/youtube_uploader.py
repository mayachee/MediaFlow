#!/usr/bin/env python3
"""
YouTube Video Uploader with Auto-Generated Metadata

Uploads videos to YouTube with automatic professional title/description
generation and optional thumbnail support.

Usage:
    # Full upload with auto-generated metadata
    python youtube_uploader.py
        --video path/to/video.mp4
        [--thumbnail path/to/thumb.jpg]
        [--title "Custom Title"]
        [--description "Custom Description"]
        [--tags "tag1,tag2,tag3"]
        [--privacy public|private|unlisted]

    # Thumbnail-only upload to existing video
    python youtube_uploader.py
        --video-id YOUTUBE_VIDEO_ID
        [--thumbnail path/to/thumb.jpg]

If --title or --description are omitted, they are auto-generated from
the video file name. Use --metadata path/to/metadata.json to load
AI-generated title, description, and tags.
"""

import os
import sys
import re
import json
import pickle
import argparse
from pathlib import Path
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload

SCOPES = [
    "https://www.googleapis.com/auth/youtube.upload",
    "https://www.googleapis.com/auth/youtube",
]


def get_authenticated_service():
    """Load or refresh OAuth2 credentials and build the YouTube API client."""
    creds = None
    base_dir = Path(__file__).parent
    token_file = base_dir / "token.pickle"
    client_secret_file = base_dir / "client_secret.json"
    if not client_secret_file.exists():
        client_secret_file = base_dir.parent / "client_secret.json"

    if token_file.exists():
        with open(token_file, "rb") as f:
            creds = pickle.load(f)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("Refreshing token...", flush=True)
            creds.refresh(Request())
        else:
            print("Starting browser auth...", flush=True)
            flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_file), SCOPES)
            creds = flow.run_local_server(port=0)

        with open(token_file, "wb") as f:
            pickle.dump(creds, f)

    return build("youtube", "v3", credentials=creds)


def parse_song_title(filename):
    """
    Extract a clean display title from a YouTube-style filename.
    e.g. 'Shakira & Burna Boy - Dai Dai (Lyrics) World Cup Song 2026.webm'
         → 'Shakira & Burna Boy - Dai Dai'
    """
    name = Path(filename).stem
    # Remove common suffixes
    for suffix in [" (Lyrics)", " (Official Music Video)", " (Official Video)",
                   " Lyric Video", " Official Audio", " (Lyrics)"]:
        name = name.replace(suffix, "")
    # Remove "(Lyrics)" if still present in the middle
    name = re.sub(r"\(Lyrics\)", "", name).strip()
    # Collapse multiple spaces
    name = re.sub(r"\s+", " ", name).strip()
    return name


def load_ai_metadata(metadata_path):
    """
    Load AI-generated metadata from metadata.json.

    Returns a dict keyed by the raw song string:
        { "Song Title – Artist": {"title": ..., "youtube_title": ..., "description": ..., "tags": [...]} }
    Returns {} if the file is missing or invalid.
    """
    path = Path(metadata_path)
    if not path.exists():
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            entries = json.load(f)
        result = {}
        for entry in entries:
            song = entry.get("song", "")
            if song and entry.get("status") == "success":
                result[song] = entry
        return result
    except (json.JSONDecodeError, Exception):
        return {}


def auto_generate_title(video_path, song_titles):
    """Create a professional playlist title."""
    if song_titles:
        if len(song_titles) == 1:
            return song_titles[0]
        first = song_titles[0]
        return f"Top Hits Playlist | {first} & {len(song_titles) - 1} More"
    return Path(video_path).stem.replace("_", " ").title()


def auto_generate_description(song_titles, video_path):
    """Create a professional description with song list and links."""
    lines = [
        "Enjoy this collection of hit songs!",
        "",
        "Tracklist:",
    ]
    for i, title in enumerate(song_titles, 1):
        lines.append(f"  {i}. {title}")
    lines.extend([
        "",
        "Like, comment, and subscribe for more music!",
        "Turn on notifications to never miss a new upload.",
        "",
        "#Music #Playlist #Hits",
    ])
    return "\n".join(lines)


def auto_generate_tags(song_titles):
    """Generate relevant tags from song titles."""
    tags = ["music", "playlist", "hit songs", "top hits", "lyrics"]
    for title in song_titles:
        artist = title.split(" - ")[0].strip()
        if artist and artist not in tags and len(tags) < 30:
            tags.append(artist)
    return tags


def find_thumbnail(video_path, song_titles):
    """
    Look for an existing thumbnail image near the video file.
    Falls back to the first song's image if available.
    """
    video_dir = Path(video_path).parent
    # Check for common thumbnail names
    for name in ["thumbnail.jpg", "thumbnail.png", "thumb.jpg", "thumb.png",
                 "cover.jpg", "cover.png"]:
        candidate = video_dir / name
        if candidate.exists():
            return str(candidate)
    # Check in input/images directory
    images_dir = video_dir.parent / "input" / "images"
    if images_dir.exists():
        images = sorted(images_dir.glob("*.jpg")) + sorted(images_dir.glob("*.png"))
        if images:
            return str(images[0])
    return None


def upload_video(youtube, video_path, title, description, tags, privacy="public", thumbnail_path=None, max_retries=5):
    """Upload a video to YouTube with optional thumbnail.

    Retries on transient network/SSL errors during the resumable upload.
    """
    import time as _time
    import httplib2
    import ssl

    body = {
        "snippet": {
            "title": title,
            "description": description,
            "tags": tags,
            "categoryId": "10",  # Music
        },
        "status": {
            "privacyStatus": privacy,
            "selfDeclaredMadeForKids": False,
        },
    }

    print(f"Preparing upload: {os.path.basename(video_path)}", flush=True)
    media = MediaFileUpload(
        video_path,
        chunksize=10 * 1024 * 1024,
        resumable=True,
        mimetype="video/mp4",
    )

    request = youtube.videos().insert(
        part=",".join(body.keys()),
        body=body,
        media_body=media,
    )

    print("Uploading...", flush=True)
    response = None
    attempt = 0
    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                if pct % 20 == 0:
                    print(f"Upload progress: {pct}%", flush=True)
        except (ssl.SSLEOFError, httplib2.ServerNotFoundError,
                httplib2.socket.error, ConnectionError) as e:
            attempt += 1
            if attempt <= max_retries:
                print(f"  Network error during upload: {e}", flush=True)
                print(f"  Retrying ({attempt}/{max_retries}) in 10s...", flush=True)
                _time.sleep(10)
            else:
                print(f"  Failed after {max_retries} retries.", flush=True)
                raise
        except Exception as e:
            print(f"  Upload error: {e}", flush=True)
            raise

    print(f"Video uploaded successfully! Video ID: {response['id']}", flush=True)

    # Upload thumbnail if provided
    video_id = response["id"]
    if thumbnail_path and os.path.exists(thumbnail_path):
        upload_thumbnail(youtube, video_id, thumbnail_path)

    return video_id


def upload_thumbnail(youtube, video_id, thumbnail_path):
    """Upload a custom thumbnail for the video."""
    print(f"Uploading thumbnail: {os.path.basename(thumbnail_path)}", flush=True)
    media = MediaFileUpload(thumbnail_path, resumable=True)
    request = youtube.thumbnails().set(
        videoId=video_id,
        media_body=media,
    )
    request.execute()
    print("Thumbnail uploaded successfully.", flush=True)


def main():
    parser = argparse.ArgumentParser(
        description="Upload videos to YouTube with auto-generated metadata"
    )
    parser.add_argument("--video", required=False, help="Path to video file")
    parser.add_argument("--video-id", required=False, help="YouTube video ID (for thumbnail-only upload)")
    parser.add_argument("--thumbnail", default=None, help="Path to thumbnail image")
    parser.add_argument("--title", default=None, help="Video title (auto-generated if omitted)")
    parser.add_argument("--description", default=None, help="Video description (auto-generated if omitted)")
    parser.add_argument("--tags", default="", help="Comma-separated tags")
    parser.add_argument("--privacy", default="public", choices=["public", "private", "unlisted"])
    parser.add_argument("--metadata", default=None, help="Path to metadata.json for AI-generated title/description/tags")
    args = parser.parse_args()

    # Thumbnail-only mode
    if args.video_id:
        print("Authenticating...", flush=True)
        youtube = get_authenticated_service()
        thumbnail_path = args.thumbnail or find_thumbnail(".", [])
        if thumbnail_path:
            upload_thumbnail(youtube, args.video_id, thumbnail_path)
        else:
            print("ERROR: No thumbnail found. Provide one with --thumbnail", flush=True)
            sys.exit(1)
        return

    video_path = os.path.abspath(args.video)
    if not os.path.exists(video_path):
        print(f"ERROR: Video file not found: {video_path}", flush=True)
        sys.exit(1)

    # Parse song titles from the video directory or file name
    song_titles = [parse_song_title(Path(video_path).name)]

    # Load AI metadata if provided
    ai_metadata = load_ai_metadata(args.metadata) if args.metadata else {}

    # Auto-generate title and description if not provided
    final_title = args.title or auto_generate_title(video_path, song_titles)
    final_description = args.description or auto_generate_description(song_titles, video_path)

    # Use AI metadata to enhance title/description/tags when not explicitly set
    if ai_metadata:
        first_song = song_titles[0] if song_titles else ""
        ai_entry = ai_metadata.get(first_song)
        if not ai_entry:
            # Try matching by filename stem or first word
            for song_key, entry in ai_metadata.items():
                if parse_song_title(song_key) == first_song:
                    ai_entry = entry
                    break
        if not ai_entry and ai_metadata:
            # Fall back to the first entry in the metadata file
            ai_entry = next(iter(ai_metadata.values()))

        if ai_entry:
            if not args.title:
                final_title = ai_entry.get("youtube_title", final_title)
            if not args.description:
                final_description = ai_entry.get("description", final_description)

    # Use provided tags or auto-generate
    if args.tags:
        tags = [tag.strip() for tag in args.tags.split(",") if tag.strip()]
    elif ai_metadata and ai_entry:
        tags = ai_entry.get("tags", auto_generate_tags(song_titles))
    else:
        tags = auto_generate_tags(song_titles)

    print(f"Title: {final_title}", flush=True)
    print(f"Description: {final_description[:100]}...", flush=True)
    print(f"Tags: {tags}", flush=True)
    print(f"Privacy: {args.privacy}", flush=True)

    # Find thumbnail if not explicitly provided
    thumbnail_path = args.thumbnail or find_thumbnail(video_path, song_titles)
    if thumbnail_path:
        print(f"Thumbnail: {thumbnail_path}", flush=True)

    print("Authenticating...", flush=True)
    youtube = get_authenticated_service()

    video_id = upload_video(
        youtube,
        video_path,
        final_title,
        final_description,
        tags,
        args.privacy,
        thumbnail_path,
    )

    print(f"\nDone! Video URL: https://youtu.be/{video_id}", flush=True)


if __name__ == "__main__":
    main()