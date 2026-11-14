#!/usr/bin/env python3
"""
Extract Pinterest OAuth token from Brave browser's local/session storage
by launching headless Brave and reading the storage.
"""

import os
import json
import time
import shutil
import subprocess
from pathlib import Path

def kill_brave():
    try:
        subprocess.run(["taskkill", "/F", "/IM", "brave.exe", "/T"], 
                      capture_output=True, timeout=10)
        time.sleep(2)
        print("  Killed Brave processes", flush=True)
    except Exception as e:
        print(f"  Could not kill Brave: {e}", flush=True)

def main():
    from playwright.sync_api import sync_playwright
    
    brave_exe = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
    brave_user_data = os.path.join(
        os.environ.get("LOCALAPPDATA", r"C:\Users\Dima D'origine\AppData\Local"),
        "BraveSoftware", "Brave-Browser", "User Data"
    )
    
    kill_brave()
    
    # Copy profile to temp location
    temp_profile = r"C:\Users\Dima D'origine\AppData\Local\Temp\brave_pinterest_copy2"
    if os.path.exists(temp_profile):
        shutil.rmtree(temp_profile, ignore_errors=True)
    
    default_src = os.path.join(brave_user_data, "Default")
    default_dst = os.path.join(temp_profile, "Default")
    if os.path.isdir(default_src):
        print(f"  Copying Brave profile...", flush=True)
        shutil.copytree(default_src, default_dst, dirs_exist_ok=True)
    
    with sync_playwright() as p:
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
        
        # Intercept network requests to capture OAuth token
        oauth_token = None
        captured_requests = []
        
        def handle_response(response):
            nonlocal oauth_token
            url = response.url
            # Look for API responses that contain token info
            if 'api.pinterest.com' in url or 'pinterest.com/api' in url:
                try:
                    body = response.json()
                    if isinstance(body, dict):
                        if 'access_token' in body:
                            oauth_token = body['access_token']
                        if 'token' in body and 'access_token' in str(body):
                            oauth_token = body.get('token', {}).get('access_token', oauth_token)
                except:
                    pass
            
            # Also check for authorization headers in network requests
            if 'pinterest.com' in url:
                captured_requests.append({
                    'url': url,
                    'method': response.request.method,
                    'headers': dict(response.request.headers),
                })
        
        page.on("response", handle_response)
        
        # Navigate to Pinterest
        print("Navigating to Pinterest...", flush=True)
        page.goto("https://www.pinterest.com/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        
        # Try to read local storage / session storage for OAuth token
        print("\nChecking localStorage and sessionStorage...", flush=True)
        
        try:
            local_storage = page.evaluate("""() => {
                const result = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    result[key] = localStorage.getItem(key);
                }
                return result;
            }""")
            print(f"localStorage keys: {list(local_storage.keys())}", flush=True)
            for key in local_storage:
                if 'token' in key.lower() or 'auth' in key.lower() or 'oauth' in key.lower():
                    val = local_storage[key]
                    if len(str(val)) > 60:
                        val = str(val)[:60] + '...'
                    print(f"  localStorage[{key}] = {val}", flush=True)
                    if 'token' in key.lower():
                        oauth_token = val if not val.endswith('...') else None
        except Exception as e:
            print(f"  localStorage error: {e}", flush=True)
        
        try:
            session_storage = page.evaluate("""() => {
                const result = {};
                for (let i = 0; i < sessionStorage.length; i++) {
                    const key = sessionStorage.key(i);
                    result[key] = sessionStorage.getItem(key);
                }
                return result;
            }""")
            print(f"sessionStorage keys: {list(session_storage.keys())}", flush=True)
            for key in session_storage:
                if 'token' in key.lower() or 'auth' in key.lower() or 'oauth' in key.lower():
                    val = session_storage[key]
                    if len(str(val)) > 60:
                        val = str(val)[:60] + '...'
                    print(f"  sessionStorage[{key}] = {val}", flush=True)
                    if 'token' in key.lower() and not str(val).endswith('...'):
                        oauth_token = str(val)
        except Exception as e:
            print(f"  sessionStorage error: {e}", flush=True)
        
        # Check cookies for bearer tokens
        cookies = context.cookies()
        for c in cookies:
            if 'pinterest' in c.get('domain', '').lower():
                name = c['name']
                val = c['value']
                if 'token' in name.lower() or 'auth' in name.lower() or 'sess' in name.lower():
                    if len(val) > 60:
                        val = val[:60] + '...'
                    print(f"  Cookie: {name} = {val}", flush=True)
        
        # Try to access Pinterest's developer page or API docs to get a token
        # Also try navigating to a page that might expose the token
        try:
            # Navigate to Pinterest settings or create pin page which might trigger API calls
            page.goto("https://www.pinterest.com/create/pin/", wait_until="domcontentloaded", timeout=30000)
            page.wait_for_timeout(10000)
        except:
            pass
        
        # Check for authorization header in captured requests
        auth_token = None
        for req in captured_requests:
            auth = req.get('headers', {}).get('authorization', '')
            if auth and 'Bearer' in auth:
                auth_token = auth.replace('Bearer ', '')
                print(f"\nFound OAuth token in Authorization header!", flush=True)
                break
        
        if oauth_token:
            print(f"\nFound OAuth token in storage: {oauth_token[:40]}...", flush=True)
            auth_token = oauth_token
        
        if auth_token:
            token_path = r"C:\Users\Dima D'origine\AppData\Local\Temp\pinterest_oauth_token.txt"
            with open(token_path, 'w') as f:
                f.write(auth_token)
            print(f"OAuth token saved to: {token_path}", flush=True)
            
            # Test the API
            cookies = context.cookies()
            cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in cookies if 'pinterest' in c.get('domain', '').lower())
            
            import requests
            s = requests.Session()
            s.headers.update({
                "Authorization": f"Bearer {auth_token}",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Accept": "application/json, text/plain, */*",
            })
            
            print("\nTesting API with OAuth token...", flush=True)
            resp = s.get("https://api.pinterest.com/v5/boards", timeout=15)
            print(f"  GET /v5/boards -> {resp.status_code}", flush=True)
            if resp.status_code == 200:
                data = resp.json()
                items = data.get('items', [])
                print(f"  Found {len(items)} boards:", flush=True)
                for b in items[:10]:
                    print(f"    ID={b.get('id')}, Name={b.get('name')}", flush=True)
            else:
                print(f"  Error: {resp.text[:500]}", flush=True)
        else:
            print("\nNo OAuth token found in storage or network requests.", flush=True)
            print("  Will try to use cookies directly for web upload.", flush=True)
            
            # Save cookies for direct web upload
            cookies_path = r"C:\Users\Dima D'origine\AppData\Local\Temp\pinterest_cookies.json"
            with open(cookies_path, 'w') as f:
                json.dump([c for c in cookies if 'pinterest' in c.get('domain', '').lower()], f, indent=2)
            print(f"  Cookies saved to: {cookies_path}", flush=True)
        
        context.close()

if __name__ == "__main__":
    main()
