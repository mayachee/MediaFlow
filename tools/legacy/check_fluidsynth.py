import urllib.request
import json

api_url = "https://api.github.com/repos/FluidSynth/fluidsynth/releases"
req = urllib.request.Request(api_url, headers={"User-Agent": "Mozilla/5.0", "Accept": "application/vnd.github.v3+json"})
try:
    resp = urllib.request.urlopen(req, timeout=30)
    releases = json.loads(resp.read())
    for release in releases[:3]:
        tag = release["tag_name"]
        print(f"Release: {tag}")
        for asset in release.get("assets", []):
            name = asset["name"]
            size = asset["size"] / (1024 * 1024)
            url = asset["browser_download_url"]
            if "win" in name.lower() or "exe" in name.lower() or "zip" in name.lower() or "dll" in name.lower():
                print(f"  Asset: {name} ({size:.1f} MB) - {url}")
except Exception as e:
    print(f"API error: {e}")
