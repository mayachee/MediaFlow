#!/usr/bin/env python3
"""
Extract Pinterest cookies by launching Brave with the user's profile,
navigating to Pinterest, then extracting cookies from the Playwright context.
Uses headless mode with longer timeout.
"""

import os
import sys
import json
import time
import shutil
import subprocess
from pathlib import Path

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

def main():
    from playwright.sync_api import sync_playwright
    
    brave_exe = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
    if not os.path.isfile(brave_exe):
        print(f"ERROR: Brave not found at {brave_exe}", flush=True)
        return
    
    brave_user_data = os.path.join(
        os.environ.get("LOCALAPPDATA", r"C:\Users\Dima D'origine\AppData\Local"),
        "BraveSoftware", "Brave-Browser", "User Data"
    )
    
    print(f"Brave profile: {brave_user_data}", flush=True)
    
    kill_brave()
    
    # Use a COPY of the profile to avoid conflicts
    temp_profile = r"C:\Users\Dima D'origine\AppData\Local\Temp\brave_pinterest_copy"
    if os.path.exists(temp_profile):
        shutil.rmtree(temp_profile, ignore_errors=True)
    
    # Copy just the Default profile
    default_src = os.path.join(brave_user_data, "Default")
    default_dst = os.path.join(temp_profile, "Default")
    if os.path.isdir(default_src):
        print(f"  Copying Brave profile to {temp_profile}...", flush=True)
        shutil.copytree(default_src, default_dst, dirs_exist_ok=True)
        print(f"  Profile copied successfully", flush=True)
    
    with sync_playwright() as p:
        # Launch with the copied profile
        context = p.chromium.launch_persistent_context(
            user_data_dir=temp_profile,
            headless=True,
            executable_path=brave_exe,
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--no-sandbox",
                "--disable-gpu",
                "--disable-dev-shm-usage",
            ],
        )
        
        page = context.new_page()
        
        # Navigate to Pinterest
        print("\nNavigating to Pinterest...", flush=True)
        try:
            page.goto("https://www.pinterest.com/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(5000)
            print(f"  Current URL: {page.url}", flush=True)
        except Exception as e:
            print(f"  [WARN] Navigation error: {e}", flush=True)
        
        # Get all cookies
        cookies = context.cookies()
        print(f"\nTotal cookies: {len(cookies)}", flush=True)
        
        # Filter for Pinterest cookies
        pinterest_cookies = []
        for c in cookies:
            domain = c.get('domain', '')
            if 'pinterest' in domain.lower():
                pinterest_cookies.append(c)
        
        print(f"Pinterest cookies: {len(pinterest_cookies)}", flush=True)
        
        session_cookie = None
        for c in pinterest_cookies:
            name = c['name']
            value = c['value']
            if len(value) > 40:
                val_display = value[:40] + '...'
            else:
                val_display = value
            print(f"  {name} = {val_display} (domain: {domain})", flush=True)
            if c['name'] == '_pinterest_sess':
                session_cookie = c
        
        # Save cookies
        cookies_path = r"C:\Users\Dima D'origine\AppData\Local\Temp\pinterest_cookies.json"
        with open(cookies_path, 'w') as f:
            json.dump(pinterest_cookies, f, indent=2)
        print(f"\nCookies saved to: {cookies_path}", flush=True)
        
        # Build cookie string for API testing
        cookie_str = "; ".join(f"{c['name']}={c['value']}" for c in pinterest_cookies)
        
        # Test the API
        if session_cookie:
            print("\nTesting Pinterest API v5 with extracted cookies...", flush=True)
            import requests
            
            s = requests.Session()
            s.headers.update({
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "application/json, text/plain, */*",
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://www.pinterest.com/",
                "Cookie": cookie_str,
            })
            
            # Test boards endpoint
            resp = s.get("https://api.pinterest.com/v5/boards", timeout=15)
            print(f"  GET /v5/boards -> {resp.status_code}", flush=True)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get('items', [])
                print(f"  Found {len(items)} boards:", flush=True)
                for b in items[:10]:
                    print(f"    ID={b.get('id')}, Name={b.get('name')}", flush=True)
            else:
                print(f"  Error: {resp.text[:300]}", flush=True)
            
            # Save the cookie header for later use
            header_path = r"C:\Users\Dima D'origine\AppData\Local\Temp\pinterest_cookie_header.txt"
            with open(header_path, 'w') as f:
                f.write(cookie_str)
            print(f"\n  Cookie header saved to: {header_path}", flush=True)
        else:
            print("\n  No _pinterest_sess found - may not be logged in", flush=True)
        
        context.close()

if __name__ == "__main__":
    main()
