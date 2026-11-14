#!/usr/bin/env python3
"""
Extract Pinterest cookies by launching a headless Brave with the user's profile,
then reading cookies from the browser context directly.
"""

import os
import sys
import json
import time
import subprocess
from playwright.sync_api import sync_playwright

def kill_brave():
    """Kill any running Brave processes."""
    try:
        subprocess.run(["taskkill", "/F", "/IM", "brave.exe", "/T"], 
                      capture_output=True, timeout=10)
        time.sleep(2)
        print("  Killed Brave processes", flush=True)
        return True
    except Exception as e:
        print(f"  Could not kill Brave: {e}", flush=True)
        return False

def extract_pinterest_cookies():
    """Launch Brave with cached profile and extract Pinterest cookies."""
    
    brave_exe = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
    if not os.path.isfile(brave_exe):
        print(f"ERROR: Brave not found at {brave_exe}", flush=True)
        return None
    
    brave_user_data = os.path.join(
        os.environ.get("LOCALAPPDATA", r"C:\Users\Dima D'origine\AppData\Local"),
        "BraveSoftware", "Brave-Browser", "User Data"
    )
    if not os.path.isdir(brave_user_data):
        brave_user_data = os.path.join(
            os.path.expanduser("~"), "AppData", "Local", "BraveSoftware",
            "Brave-Browser", "User Data"
        )
    
    print(f"Brave profile: {brave_user_data}", flush=True)
    
    kill_brave()
    
    with sync_playwright() as p:
        # Launch Brave with the user's profile
        context = p.chromium.launch_persistent_context(
            user_data_dir=brave_user_data,
            headless=True,  # Headless to avoid display issues
            executable_path=brave_exe,
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--no-sandbox",
            ],
        )
        
        # Navigate to Pinterest to trigger cookie loading
        page = context.new_page()
        try:
            page.goto("https://www.pinterest.com/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
        except Exception as e:
            print(f"  [WARN] Navigation error: {e}", flush=True)
        
        # Extract all cookies
        cookies = context.cookies()
        
        # Filter for Pinterest cookies
        pinterest_cookies = [c for c in cookies if 'pinterest' in c.get('domain', '').lower()]
        
        print(f"\nFound {len(pinterest_cookies)} Pinterest cookies:", flush=True)
        
        session_cookie = None
        for c in pinterest_cookies:
            name = c['name']
            value = c['value'][:40] + '...' if len(c.get('value', '')) > 40 else c.get('value', '')
            print(f"  {name} = {value} (domain: {c.get('domain')}, path: {c.get('path')})", flush=True)
            if c['name'] == '_pinterest_sess':
                session_cookie = c
        
        # Save all cookies to a file
        cookies_path = os.path.join(os.path.expanduser("~"), "pinterest_cookies.json")
        with open(cookies_path, 'w') as f:
            json.dump(pinterest_cookies, f, indent=2)
        print(f"\nCookies saved to: {cookies_path}", flush=True)
        
        # Build a cookie header
        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in pinterest_cookies)
        print(f"\nCookie header (for API testing):")
        print(f"  {cookie_header[:200]}...", flush=True)
        
        context.close()
        
        return pinterest_cookies

def test_pinterest_api(cookies):
    """Test the Pinterest API v5 with extracted cookies."""
    if not cookies:
        print("\nNo cookies to test with.", flush=True)
        return
    
    import requests
    
    cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies)
    
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.pinterest.com/",
        "Cookie": cookie_header,
    })
    
    print("\n--- Testing Pinterest API v5 with cookies ---", flush=True)
    
    # Try to get boards
    try:
        resp = s.get("https://api.pinterest.com/v5/boards", timeout=15)
        print(f"GET /v5/boards -> {resp.status_code}", flush=True)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('items', [])
            print(f"  Found {len(items)} boards", flush=True)
            for b in items[:10]:
                print(f"    ID={b.get('id')}, Name={b.get('name')}", flush=True)
            return items
        else:
            print(f"  Response: {resp.text[:500]}", flush=True)
    except Exception as e:
        print(f"  Error: {e}", flush=True)
    
    return None

if __name__ == "__main__":
    cookies = extract_pinterest_cookies()
    if cookies:
        boards = test_pinterest_api(cookies)
        if boards:
            print("\n✓ Pinterest cookies are valid!", flush=True)
            print("\nNext steps: Use these cookies to upload via the API, or use them in Playwright.", flush=True)
    else:
        print("Failed to extract Pinterest cookies.", flush=True)
