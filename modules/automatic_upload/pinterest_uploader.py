#!/usr/bin/env python3
"""
YouTube-to-Pinterest Image Automation

Runs after a YouTube video upload to:
1. Wait for YouTube video processing to complete (monitor upload status)
2. Extract keyframes from the video (or match against known source images)
3. Upload the identified images to a Pinterest board

Recommended Libraries:
    - google-api-python-client, google-auth-oauthlib : YouTube Data API (OAuth2 auth)
    - yt-dlp                                        : Download YouTube video
    - opencv-python (cv2)                           : Frame extraction & scene detection
    - Pillow                                        : Image manipulation (PIL)
    - imagehash                                     : Perceptual hashing for dedup/matching
    - numpy                                         : Numerical ops (required by imagehash/cv2)
    - requests                                      : Pinterest REST API v5 calls

Environment (.env):
    YOUTUBE_TOKEN_FILE      - OAuth token pickle path (default: token.pickle)
    YOUTUBE_CLIENT_SECRETS  - OAuth client_secret.json path (default: client_secret.json)
    PINTEREST_ACCESS_TOKEN  - Pinterest OAuth2 bearer token (scopes: pins:create, boards:read, media:upload)
    PINTEREST_BOARD_ID      - Target Pinterest board ID (numeric string)
    PINTEREST_USERNAME      - Pinterest username (for default board lookup)

Usage:
    # Full automation: wait for processing -> extract frames -> upload to Pinterest
    python pinterest_uploader.py --video-id VIDEO_ID

    # Use a local video file instead of downloading from YouTube
    python pinterest_uploader.py --video-id VIDEO_ID --local-video path/to/video.mp4

    # Match extracted frames against known source images
    python pinterest_uploader.py --video-id VIDEO_ID --source-images input/images/

    # Upload to a specific board (overrides .env)
    python pinterest_uploader.py --video-id VIDEO_ID --board-id BOARD_ID

    # Dry-run: extract frames but don't upload to Pinterest
    python pinterest_uploader.py --video-id VIDEO_ID --dry-run

    # Skip waiting for YouTube processing (video already processed)
    python pinterest_uploader.py --video-id VIDEO_ID --no-wait

Setup:
    1. Install dependencies: pip install -r requirements.txt
    2. Configure YouTube OAuth: copy client_secret.json into automatic_upload/
    3. Get Pinterest access token:
       - Register an app at https://developers.pinterest.com/
       - Add scopes: pins:create, boards:read, media:upload
       - Generate a long-lived access token
       - Add PINTEREST_ACCESS_TOKEN=<token> to .env
    4. Find your Pinterest board ID (in the URL when editing a board)
    5. Add PINTEREST_BOARD_ID=<board_id> to .env
"""

import os
import sys
import json
import time
import shutil
import argparse
import tempfile
from pathlib import Path
from typing import List, Optional, Dict, Any, Tuple, Set

import requests
import numpy as np
from PIL import Image
import imagehash

# Optional: YouTube Data API error class (falls back to Exception if google packages missing)
try:
    from googleapiclient.errors import HttpError
except ImportError:
    HttpError = Exception  # type: ignore[misc,assignment]


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

def load_env(env_path: str = ".env") -> None:
    """Load environment variables from a .env file (no external dependency)."""
    path = Path(env_path)
    if not path.exists():
        return
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            key = key.strip()
            value = value.strip()
            if (value.startswith('"') and value.endswith('"')) or (
                value.startswith("'") and value.endswith("'")
            ):
                value = value[1:-1]
            if value:
                os.environ.setdefault(key, value)


# ---------------------------------------------------------------------------
# YouTube Monitoring
# ---------------------------------------------------------------------------

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.readonly"]


class YouTubeMonitor:
    """Monitor YouTube video upload / processing status via the Data API v3."""

    def __init__(
        self,
        token_file: str = "token.pickle",
        client_secrets_file: str = "client_secret.json",
    ):
        self.token_file = Path(token_file)
        self.client_secrets_file = client_secrets_file
        self._youtube = None

    def _get_service(self):
        """Load or refresh OAuth2 credentials and build the YouTube API client."""
        if self._youtube is not None:
            return self._youtube

        try:
            from google_auth_oauthlib.flow import InstalledAppFlow
            from google.auth.transport.requests import Request
            from googleapiclient.discovery import build
            import pickle
        except ImportError:
            print(
                "ERROR: google-api-python-client and google-auth-oauthlib are required.\n"
                "  Install: pip install google-api-python-client google-auth-oauthlib",
                flush=True,
            )
            sys.exit(1)

        creds = None
        if self.token_file.exists():
            with open(self.token_file, "rb") as f:
                creds = pickle.load(f)

        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                print("  Refreshing YouTube token...", flush=True)
                creds.refresh(Request())
            else:
                print("  Starting YouTube OAuth browser flow...", flush=True)
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.client_secrets_file, YOUTUBE_SCOPES
                )
                creds = flow.run_local_server(port=0)

            with open(self.token_file, "wb") as f:
                pickle.dump(creds, f)

        self._youtube = build("youtube", "v3", credentials=creds)
        return self._youtube

    def get_video_info(self, video_id: str) -> dict:
        """Fetch video details including processing status."""
        youtube = self._get_service()
        request = youtube.videos().list(
            part="id,snippet,status,contentDetails,processingDetails",
            id=video_id,
        )
        response = request.execute()
        items = response.get("items", [])
        if not items:
            raise ValueError(f"Video not found (or not accessible): {video_id}")
        return items[0]

    def check_processing_status(self, video_id: str) -> Tuple[str, Optional[str]]:
        """
        Check YouTube video processing status.

        Returns (status, issue) where status is one of:
        'processing', 'succeeded', 'failed', 'unknown'
        """
        info = self.get_video_info(video_id)

        # processingDetails may be absent if the API can't see it
        processing = info.get("processingDetails", {})
        status = processing.get("processingStatus", "unknown")

        # Collect any issue details
        issue_parts = []
        for field in ("processingIssue", "processingReason", "processingFailureReason"):
            val = processing.get(field)
            if val:
                issue_parts.append(val)
        issue = "; ".join(issue_parts) if issue_parts else None

        return status, issue

    def wait_for_processing(
        self,
        video_id: str,
        timeout: int = 300,
        poll_interval: int = 15,
    ) -> Tuple[bool, Optional[str]]:
        """
        Poll the YouTube API until video processing finishes or timeout.

        Returns (success, error_message).
        """
        print(f"  Monitoring YouTube processing for video: {video_id}", flush=True)
        elapsed = 0
        attempt = 0

        while elapsed < timeout:
            attempt += 1
            try:
                status, issue = self.check_processing_status(video_id)
            except HttpError as e:
                print(f"  [WARN] API error (attempt {attempt}): {e}", flush=True)
            except ValueError as e:
                print(f"  [ERROR] {e}", flush=True)
                return False, str(e)
            else:
                msg = f"  Processing status: {status}"
                if issue:
                    msg += f" ({issue})"
                print(msg, flush=True)

                if status == "succeeded":
                    return True, None
                elif status == "failed":
                    return False, issue or "Processing failed (unknown reason)"

            sleep_time = min(poll_interval, timeout - elapsed)
            time.sleep(sleep_time)
            elapsed += poll_interval

        return False, f"Timeout after {timeout}s waiting for processing"


# ---------------------------------------------------------------------------
# Video Image Extraction
# ---------------------------------------------------------------------------

class VideoImageExtractor:
    """Download, extract keyframes, and identify images from a video."""

    def __init__(self, output_dir: str = "extracted_images"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # -- Download ----------------------------------------------------------

    def download_video(self, video_url_or_id: str, output_path: Optional[str] = None) -> str:
        """
        Download a YouTube video using yt-dlp.

        Returns the local path to the downloaded video file.
        """
        import yt_dlp

        if output_path is None:
            output_path = str(self.output_dir / "downloaded_video.mp4")

        ydl_opts = {
            "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]",
            "outtmpl": output_path,
            "quiet": True,
            "no_warnings": True,
            "noplaylist": True,
        }

        print(f"  Downloading video from YouTube...", flush=True)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([video_url_or_id])

        print(f"  Downloaded: {output_path}", flush=True)
        return output_path

    # -- Keyframe extraction ----------------------------------------------

    def extract_keyframes(
        self,
        video_path: str,
        max_frames: int = 50,
        scene_threshold: float = 0.5,
        min_interval_sec: float = 1.0,
    ) -> List[str]:
        """
        Extract keyframes from a video using OpenCV scene-change detection.

        A frame is saved when its perceptual hash differs from the previous
        saved frame by more than ``scene_threshold`` (Hamming distance on
        an 8×8 phash).  This reduces redundant frames while keeping visually
        distinct shots.
        """
        try:
            import cv2
        except ImportError:
            print(
                "ERROR: opencv-python is required for video frame extraction.\n"
                "  Install: pip install opencv-python",
                flush=True,
            )
            sys.exit(1)

        video_path = str(video_path)
        vidcap = cv2.VideoCapture(video_path)
        if not vidcap.isOpened():
            raise RuntimeError(f"Cannot open video: {video_path}")

        fps = vidcap.get(cv2.CAP_PROP_FPS) or 30
        frame_count = int(vidcap.get(cv2.CAP_PROP_FRAME_COUNT))
        duration = frame_count / fps if fps > 0 else 0

        print(
            f"  Video info: {frame_count} frames, {fps:.1f} FPS, {duration:.1f}s",
            flush=True,
        )

        min_interval_frames = max(1, int(min_interval_sec * fps))
        extracted: List[str] = []
        prev_hash = None
        frame_idx = 0

        while True:
            ret, frame = vidcap.read()
            if not ret:
                break

            if frame_idx % min_interval_frames == 0:
                # Compute perceptual hash for scene-change detection
                pil_img = Image.fromarray(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
                curr_hash = imagehash.phash(pil_img, hash_size=8)

                if prev_hash is not None:
                    diff = float(curr_hash - prev_hash)
                    if diff > scene_threshold:
                        filepath = self._save_frame(frame, frame_idx)
                        extracted.append(filepath)
                        prev_hash = curr_hash
                else:
                    filepath = self._save_frame(frame, frame_idx)
                    extracted.append(filepath)
                    prev_hash = curr_hash

                if len(extracted) >= max_frames:
                    break

            frame_idx += 1

        vidcap.release()
        print(f"  Extracted {len(extracted)} keyframes", flush=True)
        return extracted

    def _save_frame(self, frame, frame_idx: int, prefix: str = "frame") -> str:
        """Save a single frame as a JPEG and return its path."""
        filename = f"{prefix}_{frame_idx:06d}.jpg"
        filepath = self.output_dir / filename
        cv2.imwrite(str(filepath), frame)
        return str(filepath)

    # -- Deduplication -----------------------------------------------------

    @staticmethod
    def deduplicate_images(
        image_paths: List[str],
        hash_size: int = 16,
        threshold: int = 5,
    ) -> List[str]:
        """
        Remove visually similar / duplicate images using perceptual hashing.

        Images whose Hamming distance is <= ``threshold`` are considered
        duplicates and the later one is dropped.
        """
        if len(image_paths) <= 1:
            return image_paths

        print(f"  Deduplicating {len(image_paths)} images...", flush=True)
        unique_hashes: List[imagehash.ImageHash] = []
        unique_paths: List[str] = []

        for path in image_paths:
            try:
                img = Image.open(path)
                curr_hash = imagehash.phash(img, hash_size=hash_size)
            except Exception as e:
                print(f"    [SKIP] Could not hash {os.path.basename(path)}: {e}", flush=True)
                unique_paths.append(path)
                continue

            is_dup = any(curr_hash - uh <= threshold for uh in unique_hashes)

            if not is_dup:
                unique_hashes.append(curr_hash)
                unique_paths.append(path)

        print(f"  After dedup: {len(unique_paths)} unique images", flush=True)
        return unique_paths

    # -- Source image matching ---------------------------------------------

    @staticmethod
    def match_source_images(
        frame_paths: List[str],
        source_images_dir: str,
        hash_size: int = 16,
        threshold: int = 8,
    ) -> List[str]:
        """
        Match extracted frame hashes against images in ``source_images_dir``.

        Returns the list of source image paths that visually appear in the video.
        """
        source_dir = Path(source_images_dir)
        if not source_dir.exists():
            raise FileNotFoundError(f"Source images directory not found: {source_images_dir}")

        source_paths: List[str] = []
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.webp"):
            source_paths.extend(str(p) for p in sorted(source_dir.glob(ext)))

        if not source_paths:
            print(f"  No images found in {source_images_dir}", flush=True)
            return []

        print(
            f"  Matching {len(frame_paths)} frames against "
            f"{len(source_paths)} source images...",
            flush=True,
        )

        source_hashes: List[Tuple[str, imagehash.ImageHash]] = []
        for sp in source_paths:
            try:
                img = Image.open(sp)
                source_hashes.append((sp, imagehash.phash(img, hash_size=hash_size)))
            except Exception as e:
                print(f"    [SKIP] Could not hash source {sp}: {e}", flush=True)

        matched: Set[str] = set()
        for fp in frame_paths:
            try:
                img = Image.open(fp)
                frame_hash = imagehash.phash(img, hash_size=hash_size)
            except Exception:
                continue

            for sp, sh in source_hashes:
                if frame_hash - sh <= threshold:
                    matched.add(sp)

        matched_list = sorted(matched)
        print(f"  Matched {len(matched_list)} source images", flush=True)
        return matched_list

    # -- Cleanup ------------------------------------------------------------

    def cleanup_downloaded_video(self) -> None:
        """Remove the downloaded video file to save disk space."""
        video_file = self.output_dir / "downloaded_video.mp4"
        if video_file.exists():
            video_file.unlink()
            print(f"  Cleaned up: {video_file.name}", flush=True)


# ---------------------------------------------------------------------------
# Pinterest Upload
# ---------------------------------------------------------------------------

class PinterestUploader:
    """Upload images to Pinterest via the v5 REST API."""

    BASE_URL = "https://api.pinterest.com/v5"

    def __init__(self, access_token: str, board_id: str):
        self.access_token = access_token
        self.board_id = board_id
        self.headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def check_auth(self) -> bool:
        """Verify the access token and that the target board exists."""
        try:
            resp = requests.get(
                f"{self.BASE_URL}/boards/{self.board_id}",
                headers=self.headers,
                timeout=30,
            )
            if resp.status_code == 200:
                board = resp.json()
                print(
                    f"  Pinterest board verified: {board.get('name', self.board_id)}",
                    flush=True,
                )
                return True
            elif resp.status_code == 401:
                print("  ERROR: Invalid Pinterest access token", flush=True)
                return False
            else:
                print(
                    f"  ERROR: Cannot access board ({resp.status_code}): {resp.text}",
                    flush=True,
                )
                return False
        except requests.RequestException as e:
            print(f"  ERROR: Pinterest API unreachable: {e}", flush=True)
            return False

    def upload_image_media(self, image_path: str) -> Optional[str]:
        """
        Register an image upload and send the binary data to Pinterest.

        Returns the ``media_id`` on success, or ``None`` on failure.
        """
        register_data = {"media_type": "image"}

        try:
            resp = requests.post(
                f"{self.BASE_URL}/media/upload",
                headers=self.headers,
                json=register_data,
                timeout=30,
            )
            resp.raise_for_status()
            media_data = resp.json()
        except (requests.RequestException, ValueError) as e:
            print(f"  [FAIL] Could not register media upload: {e}", flush=True)
            return None

        media_id = media_data.get("media_id")
        upload_url = media_data.get("upload_url")

        if not media_id or not upload_url:
            print(f"  [FAIL] Unexpected media upload response: {media_data}", flush=True)
            return None

        image_size = os.path.getsize(image_path)

        try:
            with open(image_path, "rb") as f:
                upload_resp = requests.put(
                    upload_url,
                    data=f,
                    headers={
                        "Content-Type": "image/jpeg",
                        "Content-Length": str(image_size),
                    },
                    timeout=120,
                )
            upload_resp.raise_for_status()
        except requests.RequestException as e:
            print(f"  [FAIL] Could not upload image data: {e}", flush=True)
            return None

        return media_id

    def create_pin(
        self,
        media_id: str,
        title: str = "",
        description: str = "",
        link: str = "",
    ) -> Optional[str]:
        """
        Create a Pin on the target board using an uploaded ``media_id``.

        Returns the pin ID, or ``None`` on failure.
        """
        pin_data: Dict[str, Any] = {
            "board_id": self.board_id,
            "media": {"media_id": media_id},
        }
        if title:
            pin_data["title"] = title
        if description:
            pin_data["description"] = description
        if link:
            pin_data["link"] = link

        try:
            resp = requests.post(
                f"{self.BASE_URL}/pins",
                headers=self.headers,
                json=pin_data,
                timeout=60,
            )
            resp.raise_for_status()
            result = resp.json()
            pin_id = result.get("id")
            print(f"  [OK] Pin created: {pin_id}", flush=True)
            return pin_id
        except requests.HTTPError as e:
            detail = resp.text if resp is not None else str(e)
            print(f"  [FAIL] Could not create pin: {e} — {detail}", flush=True)
            return None
        except (requests.RequestException, ValueError) as e:
            print(f"  [FAIL] Could not create pin: {e}", flush=True)
            return None

    def upload_image(
        self,
        image_path: str,
        title: str = "",
        description: str = "",
        link: str = "",
    ) -> Optional[str]:
        """Full workflow: upload image → create pin. Returns pin ID or None."""
        print(f"  Uploading: {os.path.basename(image_path)}", flush=True)
        media_id = self.upload_image_media(image_path)
        if not media_id:
            return None
        return self.create_pin(media_id, title=title, description=description, link=link)


# ---------------------------------------------------------------------------
# Pinterest Web Uploader (Playwright-based fallback)
# ---------------------------------------------------------------------------

class PinterestWebUploader:
    """
    Upload images to Pinterest via the web UI using Playwright.

    Used when a Pinterest OAuth2 access token is not available.  The user
    logs in manually in the browser window, then the script automates the
    pin-creation flow.
    """

    PIN_CREATE_URL = "https://www.pinterest.com/pin/create/"

    def __init__(self, board_name: str = "", board_id: str = "", output_dir: str = "extracted_images"):
        self.board_name = board_name
        self.board_id = board_id
        self.output_dir = output_dir

    def _wait_for_login(self, page) -> bool:
        """Wait until the user is logged in to Pinterest."""
        print("  Waiting for Pinterest login (complete login in the browser window)...", flush=True)

        try:
            page.goto("https://www.pinterest.com/", wait_until="domcontentloaded", timeout=15000)
            page.wait_for_timeout(2000)
        except Exception:
            pass

        login_selector = 'input[name="id"], input[name="password"], input[name="email"]'
        try:
            page.wait_for_selector(login_selector, state="visible", timeout=5000)
            # Login form is visible — wait for user to complete login
            print("  Login page detected.", flush=True)
            print("  Please log in to Pinterest in the browser window...", flush=True)
            print("  (The browser is using Brave. Your session will be saved for future runs.)", flush=True)

            # Count down so the user knows how much time they have
            total_wait = 300
            elapsed = 0
            while elapsed < total_wait:
                try:
                    page.wait_for_selector(login_selector, state="hidden", timeout=5000)
                    # Login form disappeared
                    print("  Login complete!", flush=True)
                    time.sleep(3)
                    return True
                except Exception:
                    elapsed += 5
                    remaining = total_wait - elapsed
                    if remaining > 0:
                        print(f"  Still waiting for login... ({remaining}s remaining)", flush=True)
                    page.wait_for_timeout(5000)

            print("  Login timed out.", flush=True)
            return False
        except Exception:
            # No login form = already logged in (from persistent session)
            print("  Already logged in.", flush=True)
            return True

    def upload_image(
        self,
        page,
        image_path: str,
        title: str = "",
        description: str = "",
    ) -> Optional[str]:
        """
        Upload a single image to Pinterest using the web UI.

        Returns the pin URL on success, or None on failure.
        """
        print(f"  Uploading: {os.path.basename(image_path)}", flush=True)

        # Resize large images to prevent browser page crashes
        upload_path = image_path
        try:
            img = Image.open(image_path)
            if max(img.size) > 1024:
                ratio = 1024 / max(img.size)
                new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
                resized = img.resize(new_size, Image.Resampling.LANCZOS)
                upload_path = str(Path(self.output_dir) / f"resized_{os.path.basename(image_path)}")
                resized.convert("RGB").save(upload_path, "JPEG", quality=85)
                print(f"  Resized to {new_size[0]}x{new_size[1]} to prevent crashes", flush=True)
        except Exception as e:
            print(f"  [WARN] Could not resize image: {e}", flush=True)

        try:
            # Navigate to Pinterest homepage (in case we're not already there)
            try:
                page.goto("https://www.pinterest.com/", wait_until="domcontentloaded", timeout=30000)
                page.wait_for_timeout(2000)
            except Exception:
                pass  # Already on Pinterest

            # Click the "Create" button in the header to open the dropdown
            try:
                create_btn = page.locator("button").filter(has_text="Create")
                if create_btn.count() > 0:
                    create_btn.first.click()
                    page.wait_for_timeout(1000)
            except Exception:
                pass

            # Click "Create Pin" in the dropdown
            clicked_create_pin = False
            for sel in [
                "a:has-text('Create Pin')",
                "button:has-text('Create Pin')",
                "[data-test-id='create-pin']",
                "div[role='menuitem']:has-text('Pin')",
            ]:
                try:
                    elem = page.locator(sel)
                    if elem.count() > 0:
                        elem.first.click()
                        clicked_create_pin = True
                        break
                except Exception:
                    continue

            if not clicked_create_pin:
                # Try navigating directly to the pin builder
                for url in ["https://www.pinterest.com/pin/create/", "https://www.pinterest.com/create-pin/"]:
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=15000)
                        page.wait_for_timeout(3000)
                        break
                    except Exception:
                        continue

            # Wait for the pin builder to load
            page.wait_for_timeout(3000)

            # Find and click the upload area / file input
            file_input = None
            upload_selectors = [
                'input[type="file"]',
                'input[accept*="image"]',
                '[data-testid="file-input"]',
                '[data-test-id="drop-zone-input"]',
            ]

            for sel in upload_selectors:
                try:
                    file_input = page.wait_for_selector(sel, state="attached", timeout=8000)
                    if file_input:
                        break
                except Exception:
                    continue

            # If no direct input found, try clicking the upload area first
            if not file_input:
                upload_areas = [
                    "[data-testid='pin-builder-upload']",
                    "[data-test-id='drop-zone']",
                    "div:has-text('Upload')",
                    "div:has-text('Add')",
                    "[aria-label*='upload']",
                    "[aria-label*='Upload']",
                ]
                for area_sel in upload_areas:
                    try:
                        area = page.locator(area_sel)
                        if area.count() > 0:
                            area.first.click()
                            page.wait_for_timeout(2000)
                            break
                    except Exception:
                        continue

                # Retry finding file input after clicking
                for sel in upload_selectors:
                    try:
                        file_input = page.wait_for_selector(sel, state="attached", timeout=5000)
                        if file_input:
                            break
                    except Exception:
                        continue

            if not file_input:
                print("  [FAIL] Could not find image upload input on Pinterest.", flush=True)
                page.screenshot(path=str(Path(self.output_dir) / f"debug_{os.path.basename(image_path)[:20]}.png"))
                return None

            # Upload the image file
            try:
                file_input.set_input_files(str(upload_path))
                page.wait_for_timeout(5000)
            except Exception as e:
                print(f"  [FAIL] Could not set file input: {e}", flush=True)
                return None

            # Wait for the pin editor to appear
            page.wait_for_timeout(2000)

            # Select board
            if self.board_name or self.board_id:
                try:
                    board_trigger = page.locator('[data-testid="board-select-button"], [data-test-id="board-dropper"]')
                    if board_trigger.count() == 0:
                        board_trigger = page.locator("button").filter(has_text="Add to")
                    if board_trigger.count() == 0:
                        board_trigger = page.locator("button").filter(has_text=
                            self.board_name or self.board_id)
                    if board_trigger.count() > 0:
                        board_trigger.first.click()
                        page.wait_for_timeout(1500)

                        # Type or select the board
                        search_input = page.locator('input[placeholder*="Search"], input[placeholder*="board"], input[placeholder*="Board"]')
                        if search_input.count() > 0:
                            search_input.fill(self.board_name or self.board_id)
                            page.wait_for_timeout(2000)
                            board_option = page.locator("[data-testid='board-option'], [role='option'], [data-test-id='board-item']").first
                            if board_option.count() > 0:
                                board_option.click()
                        else:
                            board_option = page.locator("[data-testid='board-option'], [role='option'], [data-test-id='board-item']").first
                            if board_option.count() > 0:
                                board_option.click()
                        page.wait_for_timeout(1000)
                except Exception as e:
                    print(f"  [WARN] Could not select board: {e}", flush=True)

            # Fill title
            if title:
                try:
                    title_input = page.locator('input[placeholder*="Title"], [data-testid="pin-title"], [data-test-id="pin-title"]')
                    if title_input.count() > 0:
                        title_input.fill(title)
                except Exception:
                    pass

            # Fill description
            if description:
                try:
                    desc_input = page.locator('textarea[placeholder*="description"], [data-testid="pin-description"], [data-test-id="pin-description"]')
                    if desc_input.count() > 0:
                        desc_input.fill(description)
                except Exception:
                    pass

            # Click "Create" or "Publish" button
            try:
                publish_btn = page.locator("button").filter(has_text="Create Pin")
                if publish_btn.count() == 0:
                    publish_btn = page.locator("button").filter(has_text="Publish")
                if publish_btn.count() == 0:
                    publish_btn = page.locator("button").filter(has_text="Create")
                if publish_btn.count() > 0:
                    publish_btn.first.click()
                    page.wait_for_timeout(4000)
                    print(f"  [OK] Pin created: {os.path.basename(image_path)}", flush=True)
                    return page.url
                else:
                    print("  [FAIL] Could not find publish button.", flush=True)
                    page.screenshot(path=str(Path(self.output_dir) / f"debug_no_publish_{os.path.basename(image_path)[:20]}.png"))
                    return None
            except Exception as e:
                print(f"  [FAIL] Could not publish pin: {e}", flush=True)
                return None

        except Exception as e:
            print(f"  [FAIL] Unexpected error: {e}", flush=True)
            return None

    def upload_directory(
        self,
        image_paths: List[str],
        title: str = "",
        description: str = "",
        browser_executable: str = None,
    ) -> List[Tuple[str, Optional[str]]]:
        """Upload all images in the list via the Pinterest web UI."""
        from playwright.sync_api import sync_playwright

        results: List[Tuple[str, Optional[str]]] = []

        # Auto-detect Brave/Chrome/Edge executable
        if browser_executable is None:
            for candidate in [
                r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
                r"C:\Program Files\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
                r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            ]:
                if os.path.isfile(candidate):
                    browser_executable = candidate
                    break

        launch_kwargs: dict = {"headless": False}
        if browser_executable:
            launch_kwargs["executable_path"] = browser_executable
            print(f"  Using browser: {os.path.basename(browser_executable)}", flush=True)

        # Use a temporary profile so we don't conflict with any running browser
        user_data_dir = str(Path(self.output_dir) / "pinterest_session")
        Path(user_data_dir).mkdir(parents=True, exist_ok=True)
        print(f"  Browser profile: {user_data_dir} (fresh session — log in to Pinterest in the browser window)", flush=True)

        # If using Brave and not explicitly told otherwise, try to reuse the
        # existing Brave user data dir so we get the cached Pinterest session.
        brave_user_data = None
        if browser_executable and "brave" in browser_executable.lower():
            # Search common Brave profile locations
            for candidate in [
                os.path.join(os.environ.get("LOCALAPPDATA", r"C:\Users\Dima D'origine\AppData\Local"),
                             "BraveSoftware", "Brave-Browser", "User Data"),
                os.path.join(os.path.expanduser("~"), "AppData", "Local", "BraveSoftware",
                             "Brave-Browser", "User Data"),
            ]:
                if os.path.isdir(candidate):
                    brave_user_data = candidate
                    break

        if brave_user_data:
            # We found the Brave user data dir — reuse it for a persistent context
            # so cached Pinterest cookies are available.  Brave must be fully closed
            # for this to work (Chromium locks the profile dir while running).
            print(f"  Found Brave profile: {brave_user_data}", flush=True)
            print(f"  (If Brave is running, it will be killed to release the profile)", flush=True)

        with sync_playwright() as p:
            # If browser_executable is provided (Brave/Chrome/Edge)
            if browser_executable:
                # If we found a Brave profile, kill Brave processes to release the profile lock
                if brave_user_data:
                    try:
                        import subprocess
                        subprocess.run(
                            ["taskkill", "/F", "/IM", "brave.exe", "/T"],
                            capture_output=True,
                            timeout=10,
                        )
                        time.sleep(2)
                        print(f"  Reusing cached Brave profile for Pinterest session", flush=True)
                    except Exception as e:
                        print(f"  [WARN] Could not kill Brave processes: {e}", flush=True)
                        print(f"  Falling back to fresh session - you will need to log in", flush=True)
                        brave_user_data = None

                context_kwargs: dict = {
                    "headless": False,
                    "executable_path": browser_executable,
                    "args": ["--no-first-run", "--no-default-browser-check", "--no-sandbox"],
                }
                if brave_user_data:
                    context_kwargs["user_data_dir"] = brave_user_data
                else:
                    context_kwargs["user_data_dir"] = user_data_dir

                try:
                    context = p.chromium.launch_persistent_context(**context_kwargs)
                except Exception as e:
                    print(f"  [WARN] Failed to launch with existing profile: {e}", flush=True)
                    print(f"  Falling back to fresh session - log in to Pinterest in the browser window", flush=True)
                    context_kwargs["user_data_dir"] = user_data_dir
                    context = p.chromium.launch_persistent_context(**context_kwargs)
            else:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=user_data_dir,
                    headless=False,
                    args=["--no-first-run", "--no-default-browser-check"],
                )

            page = context.new_page()
            page.set_default_timeout(30000)
            page.set_default_navigation_timeout(60000)

            try:
                if not self._wait_for_login(page):
                    print("  ERROR: Login failed or timed out.", flush=True)
                    return results

                # After login, Pinterest may redirect and close the old page.
                # Create a fresh page from the (now authenticated) context.
                try:
                    page.close()
                except Exception:
                    pass
                page = context.new_page()
                page.set_default_timeout(30000)
                page.set_default_navigation_timeout(60000)

                for i, img_path in enumerate(image_paths, 1):
                    pin_url = None
                    for attempt in range(3):
                        try:
                            pin_url = self.upload_image(page, img_path, title=title, description=description)
                        except Exception as e:
                            err_msg = str(e).lower()
                            print(f"  [RETRY] Attempt {attempt + 2}/3 after error: {e}", flush=True)
                            if "crashed" in err_msg or "closed" in err_msg:
                                try:
                                    page.close()
                                except Exception:
                                    pass
                                try:
                                    page = context.new_page()
                                    page.set_default_timeout(30000)
                                    page.set_default_navigation_timeout(60000)
                                    page.goto("https://www.pinterest.com/", wait_until="domcontentloaded", timeout=15000)
                                    page.wait_for_timeout(2000)
                                except Exception:
                                    pass
                            if pin_url:
                                break
                            if attempt < 2:
                                time.sleep(3)
                    results.append((img_path, pin_url))
                    if i < len(image_paths):
                        time.sleep(2)
            finally:
                context.close()

        return results


# ---------------------------------------------------------------------------
# Metadata helpers
# ---------------------------------------------------------------------------

def load_metadata(metadata_path: str = "metadata.json") -> List[dict]:
    """Load AI-generated metadata from metadata.json (if it exists)."""
    path = Path(metadata_path)
    if not path.exists():
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            data = data.get("songs", data.get("items", [data]))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError) as e:
        print(f"  [WARN] Could not load metadata.json: {e}", flush=True)
        return []


def match_image_to_metadata(image_path: str, metadata: List[dict]) -> Tuple[str, str]:
    """
    Try to find a metadata entry whose song title or artist appears in the
    image filename.  Returns (title, description) for the pin.
    """
    fname = Path(image_path).stem.lower()

    for entry in metadata:
        if entry.get("status") != "success":
            continue

        title = (entry.get("title") or "").lower()
        artist = (entry.get("artist") or "").lower()
        # Also try the full song string and the AI-generated youtube_title
        song_raw = (entry.get("song") or "").lower()
        yt_title = (entry.get("youtube_title") or "").lower()

        if title and title in fname:
            return entry["youtube_title"], entry.get("description", "")
        if artist and artist in fname:
            return entry["youtube_title"], entry.get("description", "")
        if song_raw and song_raw.split(" - ")[0] in fname:
            return entry["youtube_title"], entry.get("description", "")
        if yt_title and yt_title.split(" - ")[0] in fname:
            return entry["youtube_title"], entry.get("description", "")

    return "", ""


def save_upload_log(
    results: List[Tuple[str, Optional[str]]],
    output_dir: Path,
) -> str:
    """Write a JSON log of uploaded pins to ``pinterest_uploads.json``."""
    log_path = output_dir / "pinterest_uploads.json"
    entries = [
        {"image": os.path.basename(img), "pin_id": pid, "status": "success" if pid else "failed"}
        for img, pid in results
    ]
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)
    print(f"  Upload log saved: {log_path}", flush=True)
    return str(log_path)


def save_image_list(image_paths: List[str], output_dir: Path) -> str:
    """Write the list of identified images to ``images_found.txt``."""
    list_path = output_dir / "images_found.txt"
    with open(list_path, "w", encoding="utf-8") as f:
        for p in image_paths:
            f.write(p + "\n")
    return str(list_path)


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="After a YouTube upload completes, extract images from the "
                    "video and upload them to Pinterest.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    # --- YouTube ---
    yt = parser.add_argument_group("YouTube Monitoring")
    yt.add_argument("--video-id", help="YouTube video ID to monitor and process")
    yt.add_argument("--video-url", help="Full YouTube URL (alternative to --video-id)")
    yt.add_argument(
        "--no-wait",
        action="store_true",
        help="Skip waiting for YouTube processing to complete",
    )
    yt.add_argument(
        "--poll-timeout",
        type=int,
        default=300,
        help="Max seconds to wait for processing (default: 300)",
    )
    yt.add_argument(
        "--poll-interval",
        type=int,
        default=15,
        help="Seconds between status polls (default: 15)",
    )

    # --- Video ---
    vid = parser.add_argument_group("Video Processing")
    vid.add_argument(
        "--local-video",
        default=None,
        help="Use a local video file instead of downloading from YouTube",
    )
    vid.add_argument(
        "--source-images",
        default=None,
        help="Directory of source images to match against (e.g. input/images/)",
    )
    vid.add_argument(
        "--max-frames",
        type=int,
        default=50,
        help="Maximum keyframes to extract (default: 50)",
    )
    vid.add_argument(
        "--scene-threshold",
        type=float,
        default=0.5,
        help="Scene-change sensitivity; higher = fewer frames (default: 0.5)",
    )
    vid.add_argument(
        "--dedupe-threshold",
        type=int,
        default=5,
        help="Hamming distance threshold for dedup (lower = stricter, default: 5)",
    )
    vid.add_argument(
        "--output-dir",
        default="extracted_images",
        help="Directory for extracted / matched images (default: extracted_images)",
    )
    vid.add_argument(
        "--cleanup-video",
        action="store_true",
        help="Delete downloaded video after frame extraction to save disk space",
    )

    # --- Pinterest ---
    pin = parser.add_argument_group("Pinterest Upload")
    pin.add_argument("--board-id", default=None, help="Pinterest board ID (API mode, overrides .env)")
    pin.add_argument("--board-name", default=None, help="Pinterest board name (web mode)")
    pin.add_argument(
        "--skip-pinterest",
        action="store_true",
        help="Extract images only; skip Pinterest upload",
    )
    pin.add_argument(
        "--use-web",
        action="store_true",
        help="Use Playwright web UI upload instead of Pinterest API (no OAuth token needed)",
    )
    pin.add_argument(
        "--browser",
        default=None,
        help="Path to browser executable for web mode (auto-detects Brave/Chrome/Edge)",
    )
    pin.add_argument("--pin-description", default=None, help="Override description for all pins")
    pin.add_argument("--metadata", default=None, help="Path to metadata.json for auto-generating pin descriptions (default: metadata.json)")
    pin.add_argument(
        "--skip-existing",
        action="store_true",
        help="Skip images that already have an upload log entry",
    )
    pin.add_argument("--dry-run", action="store_true", help="Show what would be uploaded without uploading")
    pin.add_argument(
        "--images-dir",
        default=None,
        help="Directory of images to upload directly (skip extraction from video)",
    )

    # --- Auth ---
    auth = parser.add_argument_group("Authentication")
    auth.add_argument(
        "--youtube-token-file",
        default=None,
        help="Path to YouTube OAuth token pickle (default: env or token.pickle)",
    )
    auth.add_argument(
        "--youtube-client-secrets",
        default=None,
        help="Path to YouTube client_secret.json (default: env or client_secret.json)",
    )

    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_env()

    # Resolve auth paths
    token_file = args.youtube_token_file or os.environ.get("YOUTUBE_TOKEN_FILE", "token.pickle")
    client_secrets = (
        args.youtube_client_secrets
        or os.environ.get("YOUTUBE_CLIENT_SECRETS", str(Path(__file__).resolve().parents[2] / "config/credentials/client_secret.json"))
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    images_to_upload: List[str] = []
    list_path: Optional[str] = None
    step_num = 0
    total_steps = 4 if not args.images_dir else 2

    # ------------------------------------------------------------------
    # Step 1 — Wait for YouTube processing (skip if --images-dir)
    # ------------------------------------------------------------------
    if args.images_dir:
        step_num += 1
        image_dir = Path(args.images_dir)
        if not image_dir.exists():
            print(f"ERROR: Images directory not found: {image_dir}", flush=True)
            sys.exit(1)
        for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.webp"):
            images_to_upload.extend(str(p) for p in sorted(image_dir.glob(ext)))
        if not images_to_upload:
            print(f"ERROR: No images found in {image_dir}", flush=True)
            sys.exit(1)
        print(f"[{step_num}/{total_steps}] Found {len(images_to_upload)} image(s) in {image_dir}\n", flush=True)
    else:
        # Resolve video source
        if args.local_video:
            video_path = args.local_video
            video_id = None
            video_url = None
        elif args.video_id:
            video_id = args.video_id
            video_url = f"https://www.youtube.com/watch?v={video_id}"
        elif args.video_url:
            video_url = args.video_url
            video_id = None
        else:
            print("ERROR: Must provide --video-id, --video-url, --local-video, or --images-dir", flush=True)
            sys.exit(1)

        step_num += 1
        if video_id and not args.no_wait:
            print(f"\n[{step_num}/{total_steps}] Waiting for YouTube processing to complete...", flush=True)
            monitor = YouTubeMonitor(token_file=token_file, client_secrets_file=client_secrets)
            success, error = monitor.wait_for_processing(
                video_id,
                timeout=args.poll_timeout,
                poll_interval=args.poll_interval,
            )
            if not success:
                print(f"\nERROR: {error}", flush=True)
                sys.exit(1)
            print("  Video processing complete!\n", flush=True)
        elif video_id and args.no_wait:
            print(f"\n[{step_num}/{total_steps}] Skipping YouTube processing wait (--no-wait)\n", flush=True)

        # ------------------------------------------------------------------
        # Step 2 — Get video (download or use local)
        # ------------------------------------------------------------------
        step_num += 1
        print(f"[{step_num}/{total_steps}] Preparing video source...", flush=True)
        extractor = VideoImageExtractor(output_dir=str(output_dir))

        if args.local_video:
            print(f"  Using local video: {video_path}", flush=True)
        else:
            video_path = extractor.download_video(video_url)

        # ------------------------------------------------------------------
        # Step 3 — Extract / identify images
        # ------------------------------------------------------------------
        step_num += 1
        print(f"\n[{step_num}/{total_steps}] Extracting images from video...", flush=True)

        frames = extractor.extract_keyframes(
            video_path,
            max_frames=args.max_frames,
            scene_threshold=args.scene_threshold,
        )

        if args.source_images:
            matched = VideoImageExtractor.match_source_images(frames, args.source_images)
            if matched:
                images_to_upload = matched
            else:
                print("  No source images matched; falling back to extracted keyframes.", flush=True)
                images_to_upload = frames
        else:
            images_to_upload = frames

        if not images_to_upload:
            print("\nERROR: No images were extracted from the video.", flush=True)
            sys.exit(1)

        images_to_upload = VideoImageExtractor.deduplicate_images(
            images_to_upload,
            threshold=args.dedupe_threshold,
        )

        list_path = save_image_list(images_to_upload, output_dir)

        if args.cleanup_video and not args.local_video:
            extractor.cleanup_downloaded_video()

    # ------------------------------------------------------------------
    # Step 4 (or 2) — Upload to Pinterest
    # ------------------------------------------------------------------
    step_num += 1
    print(f"\n[{step_num}/{total_steps}] Identified {len(images_to_upload)} image(s) to upload.\n", flush=True)

    if args.dry_run:
        print("=== DRY RUN ===", flush=True)
        for p in images_to_upload:
            print(f"  Would upload: {p}", flush=True)
        print("=== End DRY RUN ===", flush=True)
        return

    if args.skip_pinterest:
        print("Skipping Pinterest upload (--skip-pinterest).", flush=True)
        return

    # Load metadata for descriptions
    metadata_path = args.metadata or "metadata.json"
    metadata = load_metadata(metadata_path)
    if metadata:
        print(f"  Loaded {len(metadata)} metadata entries from {metadata_path}", flush=True)

    # Resolve Pinterest credentials / mode
    board_id = args.board_id or os.environ.get("PINTEREST_BOARD_ID")
    access_token = os.environ.get("PINTEREST_ACCESS_TOKEN")
    board_name = args.board_name or os.environ.get("PINTEREST_BOARD_NAME", "")
    use_web = args.use_web or not access_token or not board_id

    results: List[Tuple[str, Optional[str]]] = []

    if use_web:
        # --- Playwright web-based upload ---
        board_name = board_name or os.environ.get("PINTEREST_BOARD_NAME", "My Videos")
        print(f"\nUploading via Pinterest web UI (board: {board_name})...", flush=True)
        print("  A browser window will open. Please log in to Pinterest if needed.\n", flush=True)

        web_uploader = PinterestWebUploader(
            board_name=board_name,
            board_id=board_id,
            output_dir=str(output_dir),
        )

        # Generate a combined description if metadata is available
        combined_desc = args.pin_description or ""
        if not combined_desc and metadata:
            all_tags = set()
            for entry in metadata:
                if entry.get("status") == "success":
                    all_tags.update(entry.get("tags", []))
            if all_tags:
                combined_desc = " ".join(sorted(all_tags))

        web_results = web_uploader.upload_directory(
            images_to_upload,
            title="",
            description=combined_desc,
            browser_executable=args.browser,
        )
        results = web_results

    else:
        # --- API-based upload ---
        print(f"\nUploading via Pinterest API (board: {board_id})...", flush=True)
        uploader = PinterestUploader(access_token=access_token, board_id=board_id)

        if not uploader.check_auth():
            print("ERROR: Pinterest authentication failed.", flush=True)
            sys.exit(1)

        # Load existing upload log for skip-existing
        existing_uploads = set()
        if args.skip_existing:
            log_path = output_dir / "pinterest_uploads.json"
            if log_path.exists():
                try:
                    with open(log_path, "r", encoding="utf-8") as f:
                        for entry in json.load(f):
                            if entry.get("status") == "success":
                                existing_uploads.add(entry.get("image", ""))
                except (json.JSONDecodeError, OSError):
                    pass

        for i, img_path in enumerate(images_to_upload, 1):
            basename = os.path.basename(img_path)

            if args.skip_existing and basename in existing_uploads:
                print(f"  [{i}/{len(images_to_upload)}] Skipping (already uploaded): {basename}", flush=True)
                results.append((img_path, "skipped"))
                continue

            print(f"  [{i}/{len(images_to_upload)}] Processing: {basename}", flush=True)

            title = ""
            description = args.pin_description or ""

            if not description and metadata:
                meta_title, meta_desc = match_image_to_metadata(img_path, metadata)
                title = meta_title
                description = meta_desc

            pin_id = uploader.upload_image(
                img_path,
                title=title,
                description=description,
            )
            results.append((img_path, pin_id))

    # Save results
    if list_path:
        pass  # Already saved above
    else:
        list_path = save_image_list(images_to_upload, output_dir)

    log_path = save_upload_log(results, output_dir)

    if use_web:
        success_count = sum(1 for _, pid in results if pid)
        fail_count = len(results) - success_count
        print(f"\n{'=' * 60}", flush=True)
        print(f"Done! {success_count} pin(s) created on Pinterest")
        if fail_count:
            print(f"  Failed: {fail_count}")
        print(f"  Images: {list_path}")
        print(f"  Log:    {log_path}")
        print(f"{'=' * 60}", flush=True)
        if fail_count > 0:
            sys.exit(1)
    else:
        success_count = sum(1 for _, pid in results if pid and pid != "skipped")
        skip_count = sum(1 for _, pid in results if pid == "skipped")
        fail_count = len(results) - success_count - skip_count

        print(f"\n{'=' * 60}", flush=True)
        print(f"Done! Uploaded {success_count} pin(s) to Pinterest")
        if skip_count:
            print(f"  Skipped: {skip_count} (already uploaded)")
        if fail_count:
            print(f"  Failed:  {fail_count}")
        print(f"  Images found: {list_path}")
        print(f"  Upload log:   {log_path}")
        print(f"{'=' * 60}", flush=True)

        if fail_count > 0:
            sys.exit(1)


if __name__ == "__main__":
    main()
