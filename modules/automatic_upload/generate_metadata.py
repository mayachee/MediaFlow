#!/usr/bin/env python3
"""
AI Metadata Generator for YouTube Music Videos

Reads song titles from input.txt and uses an AI model (OpenAI-compatible API)
to generate professional, SEO-optimized YouTube titles, descriptions, and tags
for each song.

Works with any OpenAI-compatible API endpoint:
  - OpenAI (https://api.openai.com/v1)
  - OpenRouter (https://openrouter.ai/api/v1)
  - Kilo Gateway (https://gateway.kilo.ai/v1)
  - Local/Ollama (http://localhost:11434/v1)

Usage:
    python generate_metadata.py                        # Use defaults
    python generate_metadata.py --model gpt-4o         # Specify model
    python generate_metadata.py --input songs.txt      # Custom input
    python generate_metadata.py --output results.json  # Custom output

Environment:
    OPENAI_API_KEY  - Required: API key for the AI provider
    OPENAI_API_BASE - Optional: Custom base URL (e.g., OpenRouter, Kilo Gateway)

Output Files:
    metadata.json            - Structured JSON with all metadata
    metadata.txt             - Human-readable formatted text
"""

import json
import os
import re
import sys
import time
import argparse
from pathlib import Path
from typing import List, Dict, Optional, Tuple

import requests


def load_env(env_path=".env"):
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


DEFAULT_MODEL = "gpt-4o-mini"
DEFAULT_INPUT = "input.txt"
DEFAULT_OUTPUT = "metadata.json"
DEFAULT_BASE_URL = "https://api.openai.com/v1"

# Song line separators (en-dash, em-dash, hyphen)
SEPARATORS = ["\u2013", "\u2014", " - "]

SYSTEM_PROMPT = """You are a professional YouTube content creator specializing in music content.
Your task is to generate a compelling, SEO-optimized YouTube video title, description,
and tags for the given song.

Requirements:
- Title: 50-70 characters max. Include the song title and artist.
  Add a relevant keyword like "Official Audio", "Lyrics", "Visualiser", or "Audio".
- Description: 200-350 words. Start with a hook, include song details,
  a short engaging paragraph, a call-to-action (like/comment/subscribe),
  and end with 8-12 relevant hashtags.
- Tags: 10-15 relevant tags (artist, song title, genre, related artists, etc.).
- Social Media: Find and include official social media links/handles for the artist
  (Instagram, Twitter/X, Facebook, TikTok, YouTube channel, Spotify, website, etc.).
  If no official accounts are known, omit the field or set to empty object.

Output ONLY valid JSON with these exact fields:
{"title": "...", "description": "...", "tags": ["tag1", "tag2", ...], "social_media": {"instagram": "...", "twitter": "...", "facebook": "...", "tiktok": "...", "youtube": "...", "spotify": "...", "website": "..."}}

Do not include any surrounding text or markdown."""


def parse_song_line(line: str) -> Tuple[str, str]:
    """Parse a song line into (title, artist).

    Handles formats like:
      'Song Title – Artist Name'
      'Song Title — Artist Name'
      'Song Title - Artist Name'
    """
    stripped = line.strip()
    for sep in SEPARATORS:
        idx = stripped.find(sep)
        if idx != -1:
            title = stripped[:idx].strip()
            artist = stripped[idx + len(sep):].strip()
            if title and artist:
                return title, artist
    return stripped, ""


def load_songs(input_file: Path) -> List[Dict[str, str]]:
    """Read and parse songs from the input file."""
    if not input_file.exists():
        print(f"ERROR: Input file not found: {input_file}")
        sys.exit(1)

    with open(input_file, "r", encoding="utf-8") as f:
        lines = [line.strip() for line in f if line.strip()]

    songs = []
    for line in lines:
        title, artist = parse_song_line(line)
        songs.append({"raw": line, "title": title, "artist": artist})

    return songs


def generate_metadata(
    song: Dict[str, str],
    model: str,
    api_key: str,
    api_base: str,
    max_retries: int = 3,
    base_delay: float = 10.0,
) -> Optional[Dict[str, str]]:
    """Call the AI API to generate title, description, and tags for a song."""
    title = song["title"] if song["title"] else song["raw"]
    artist = song["artist"]

    prompt = f"Generate YouTube title, description, and tags for: '{title}' by {artist}."

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ]

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.7,
        "max_tokens": 1000,
    }

    for attempt in range(max_retries):
        try:
            response = requests.post(
                f"{api_base.rstrip('/')}/chat/completions",
                headers=headers,
                json=payload,
                timeout=60,
            )
            response.raise_for_status()
            data = response.json()
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if not content:
                print(f"  [ERROR] API returned empty response (possibly rate-limited)")
                raise requests.exceptions.HTTPError("Empty response")
            content = content.strip()

            # Try parsing JSON directly, then extract from markdown code blocks
            result = None
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                # Try extracting from ```json ... ``` block
                match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
                if match:
                    try:
                        result = json.loads(match.group(1))
                    except json.JSONDecodeError:
                        pass
                if not result:
                    # Try finding first { and last }
                    start = content.find('{')
                    end = content.rfind('}')
                    if start != -1 and end != -1 and end > start:
                        try:
                            result = json.loads(content[start:end+1])
                        except json.JSONDecodeError:
                            pass

            if not result:
                print(f"  [WARNING] AI returned non-JSON response, retrying...")
                print(f"    Response preview: {content[:200]}...")
                raise ValueError("Non-JSON response")

            return {
                "title": result["title"],
                "description": result["description"],
                "tags": result["tags"],
                "social_media": result.get("social_media", {}),
            }
        except requests.exceptions.HTTPError as e:
            print(f"  [ERROR] API request failed: {e}")
            if response.status_code == 401:
                print("  Check your API key.")
                return None
            elif response.status_code == 429:
                print(f"  Rate limited (429). Waiting {base_delay * (2**attempt):.0f}s before retry...")
                time.sleep(base_delay * (2**attempt))
                continue
            return None
        except Exception as e:
            print(f"  [ERROR] {e}")
            if attempt < max_retries - 1:
                time.sleep(base_delay * (2**attempt))
                continue
            return None
    return None


def format_output(songs: List[Dict[str, str]], results: List[Dict]) -> str:
    """Generate human-readable formatted text of all metadata."""
    lines = []
    lines.append("=" * 70)
    lines.append("AI-Generated YouTube Metadata")
    lines.append("=" * 70)
    lines.append("")

    for i, (song, result) in enumerate(zip(songs, results), 1):
        if result is None:
            lines.append(f"[{i}/{len(songs)}] {song['raw']}  -- FAILED")
            lines.append("-" * 70)
            continue

        lines.append(f"[{i}/{len(songs)}] {song['raw']}")
        lines.append("-" * 70)
        lines.append(f"Title: {result['title']}")
        lines.append("")
        lines.append("Description:")
        lines.append(result["description"])
        lines.append("")
        lines.append(f"Tags: {', '.join(result['tags'])}")
        if result.get("social_media"):
            lines.append("")
            lines.append("Social Media:")
            for platform, handle in result["social_media"].items():
                lines.append(f"  {platform}: {handle}")
        lines.append("=" * 70)
        lines.append("")

    return "\n".join(lines)


def save_results(
    songs: List[Dict[str, str]],
    results: List[Dict],
    output_file: Path,
    formatted_file: Path,
) -> None:
    """Save metadata to JSON and formatted text files."""
    # Structured JSON output
    json_data = []
    for song, result in zip(songs, results):
        if result is None:
            json_data.append({"song": song["raw"], "status": "failed"})
        else:
            json_data.append({
                "song": song["raw"],
                "artist": song["artist"],
                "title": song["title"],
                "youtube_title": result["title"],
                "description": result["description"],
                "tags": result["tags"],
                "social_media": result.get("social_media", {}),
                "status": "success",
            })

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    # Human-readable formatted output
    text_output = format_output(songs, results)
    with open(formatted_file, "w", encoding="utf-8") as f:
        f.write(text_output)


def main():
    load_env()
    parser = argparse.ArgumentParser(
        description="Generate AI-powered YouTube titles and descriptions for songs"
    )
    parser.add_argument(
        "--input", default=DEFAULT_INPUT,
        help=f"Input file with song list (default: {DEFAULT_INPUT})",
    )
    parser.add_argument(
        "--output", default=DEFAULT_OUTPUT,
        help=f"Output JSON file (default: {DEFAULT_OUTPUT})",
    )
    parser.add_argument(
        "--model", default=os.environ.get("OPENAI_MODEL", DEFAULT_MODEL),
        help=f"AI model to use (default: {DEFAULT_MODEL}, or OPENAI_MODEL env)",
    )
    args = parser.parse_args()

    input_file = Path(args.input)
    output_file = Path(args.output)
    formatted_file = output_file.with_suffix(".txt").name if output_file.suffix == ".json" else output_file.with_name(output_file.stem + ".txt")
    formatted_file = Path(formatted_file)

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("ERROR: OPENAI_API_KEY environment variable is not set.")
        print()
        print("Quick start with a FREE option:")
        print("  1. Sign up at https://openrouter.ai/keys (no credit card)")
        print("  2. Set these env vars:")
        print("     $env:OPENAI_API_KEY='your-openrouter-key'")
        print("     $env:OPENAI_API_BASE='https://openrouter.ai/api/v1'")
        print("     $env:OPENAI_MODEL='openrouter/free'")
        print()
        print("Or run completely offline with Ollama:")
        print("  pip install ollama && ollama run llama3")
        print("  $env:OPENAI_API_KEY='ollama'")
        print("  $env:OPENAI_API_BASE='http://localhost:11434/v1'")
        sys.exit(1)

    api_base = os.environ.get("OPENAI_API_BASE") or os.environ.get("OPENAI_BASE_URL") or DEFAULT_BASE_URL

    # Load songs
    songs = load_songs(input_file)
    if not songs:
        print(f"No songs found in {input_file}")
        sys.exit(1)

    print(f"Loaded {len(songs)} song(s) from {input_file.name}")
    print(f"Model: {args.model}")
    print(f"API Base: {api_base}")
    print()

    results = []
    for i, song in enumerate(songs, 1):
        title = song["title"] if song["title"] else song["raw"]
        artist = song["artist"] or "Unknown Artist"
        print(f"[{i}/{len(songs)}] Generating metadata for: {title} - {artist}")

        result = generate_metadata(song, args.model, api_key, api_base)
        if result:
            print(f"  [OK] Title: {result['title']}")
        else:
            print(f"  [FAIL] Could not generate metadata after retries.")
        results.append(result)
        print()

        # Delay between songs to respect rate limits on free tiers
        time.sleep(15)

    # Save results
    save_results(songs, results, output_file, formatted_file)

    success_count = sum(1 for r in results if r is not None)
    print("=" * 70)
    print(f"Done! Generated metadata for {success_count}/{len(songs)} songs.")
    print(f"JSON output:   {output_file}")
    print(f"Text output:   {formatted_file}")
    print("=" * 70)


if __name__ == "__main__":
    main()
