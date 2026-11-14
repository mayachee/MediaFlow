import urllib.request
import os
import json

scripts_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "assets", "soundfonts"))
output = os.path.join(scripts_dir, "SoundFont.sf2")

# GitHub API to find release assets
try:
    api_url = "https://api.github.com/repos/zeittresor/opensoundfont/releases/latest"
    req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github.v3+json"})
    resp = urllib.request.urlopen(req, timeout=30)
    release_info = json.loads(resp.read())
    for asset in release_info.get("assets", []):
        print(f"Asset: {asset['name']}, size: {asset['size']/(1024*1024):.1f} MB, url: {asset['browser_download_url']}")
except Exception as e:
    print(f"GitHub API error: {e}")

# Try direct download of FluidR3 GM from Jacklz GitHub
download_urls = [
    "https://github.com/Jacalz/fluid-soundfont/raw/master/original-files/FluidR3_GM.sf2",
    "https://github.com/zeittresor/opensoundfont/raw/main/FM_GM_SoundFont_v0_2_1_mini.sf2",
]

for url in download_urls:
    try:
        print(f"\nTrying download: {url}")
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=30)
        total = resp.headers.get("Content-Length", "unknown")
        print(f"  Content-Length: {total}")
        if total != "unknown" and int(total) > 1000:
            size_mb = int(total) / (1024 * 1024)
            print(f"  Downloading ({size_mb:.1f} MB)...")
            urllib.request.urlretrieve(url, output)
            print(f"  Saved: {os.path.getsize(output)/(1024*1024):.1f} MB")
            break
    except Exception as e:
        print(f"  Failed: {e}")
