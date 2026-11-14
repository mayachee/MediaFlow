#!/usr/bin/env python3
"""
Complete Pinterest upload workflow:
1. Kill all Brave processes
2. Launch Brave with cached profile (non-headless)
3. Wait for user to manually log in to Pinterest
4. Extract cookies from the browser context
5. Use cookies to authenticate with Pinterest API
6. Upload images via API
"""

import os
import sys
import json
import time
import shutil
import subprocess
from pathlib import Path

def kill_brave():
    try:
        result = subprocess.run(["taskkill", "/F", "/IM", "brave.exe", "/T"], 
                      capture_output=True, timeout=15)
        time.sleep(2)
        print("  Killed Brave processes", flush=True)
        return True
    except Exception as e:
        print(f"  [WARN] Could not kill Brave: {e}", flush=True)
        return False

def resize_image(img_path, output_path, max_size=1024):
    from PIL import Image
    img = Image.open(img_path)
    if max(img.size) > max_size:
        ratio = max_size / max(img.size)
        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
        resized = img.resize(new_size, Image.Resampling.LANCZOS)
        if img.mode == 'RGBA':
            resized = resized.convert('RGB')
        resized.save(output_path, 'JPEG', quality=85)
        print(f"  Resized: {Path(img_path).name} -> {new_size[0]}x{new_size[1]}", flush=True)
    else:
        if img.mode == 'RGBA':
            img = img.convert('RGB')
        shutil.copy2(img_path, output_path)

def main():
    from playwright.sync_api import sync_playwright
    
    brave_exe = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
    brave_user_data = os.path.join(
        os.environ.get("LOCALAPPDATA", r"C:\Users\Dima D'origine\AppData\Local"),
        "BraveSoftware", "Brave-Browser", "User Data"
    )
    
    # Images to upload
    images_dir = r"C:\Users\Dima D'origine\OneDrive\Bureau\scripts\.kilo\worktrees\flint-sunscreen\music_video_generator\input\images"
    board_name = "Test Upload"
    
    # Collect images
    image_paths = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.webp"):
        image_paths.extend(str(p) for p in sorted(Path(images_dir).glob(ext)))
    
    if not image_paths:
        print(f"ERROR: No images found in {images_dir}", flush=True)
        return
    
    print(f"Found {len(image_paths)} images to upload:", flush=True)
    for path in image_paths:
        print(f"  - {Path(path).name}", flush=True)
    
    # Prepare images
    temp_dir = r"C:\Users\Dima D'origine\AppData\Local\Temp\pinterest_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    resized_paths = []
    for img_path in image_paths:
        fname = os.path.basename(img_path)
        out_path = os.path.join(temp_dir, fname)
        resize_image(img_path, out_path)
        resized_paths.append(out_path)
    
    kill_brave()
    
    # Copy profile to temp location
    temp_profile = r"C:\Users\Dima D'origine\AppData\Local\Temp\brave_pinterest_upload"
    if os.path.exists(temp_profile):
        shutil.rmtree(temp_profile, ignore_errors=True)
    
    default_src = os.path.join(brave_user_data, "Default")
    default_dst = os.path.join(temp_profile, "Default")
    if os.path.isdir(default_src):
        print(f"\nCopying Brave profile to temp location...", flush=True)
        shutil.copytree(default_src, default_dst, dirs_exist_ok=True)
        print(f"  Done", flush=True)
    else:
        os.makedirs(default_dst, exist_ok=True)
    
    with sync_playwright() as p:
        # Launch Brave (non-headless for manual login)
        context = p.chromium.launch_persistent_context(
            user_data_dir=temp_profile,
            headless=False,
            executable_path=brave_exe,
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--no-sandbox",
            ],
        )
        
        page = context.new_page()
        page.set_default_timeout(60000)
        
        # Navigate to Pinterest
        print("\n[1] Navigating to Pinterest...", flush=True)
        page.goto("https://www.pinterest.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        
        current_url = page.url
        print(f"  Current URL: {current_url}", flush=True)
        print(f"  Page title: {page.title()}", flush=True)
        
        # Check if we need to log in
        login_needed = False
        login_selectors = [
            'input[name="id"]',
            'input[name="password"]',
            'input[name="email"]',
            'input[name="username"]',
        ]
        
        for sel in login_selectors:
            try:
                if page.locator(sel).first.is_visible(timeout=2000):
                    login_needed = True
                    print(f"  Login form detected (selector: {sel})", flush=True)
                    break
            except:
                continue
        
        if login_needed:
            print("\n*** ATTENTION: Please log in to Pinterest in the browser window ***", flush=True)
            print("*** You have 300 seconds (5 minutes) to complete login ***", flush=True)
            print(f"*** URL: https://www.pinterest.com/ ***", flush=True)
            
            # Wait for login to complete
            start = time.time()
            while time.time() - start < 300:
                time.sleep(5)
                
                # Check if login form is gone
                form_still_visible = False
                for sel in login_selectors:
                    try:
                        if page.locator(sel).first.is_visible(timeout=1000):
                            form_still_visible = True
                            break
                    except:
                        continue
                
                if not form_still_visible:
                    # Verify we're logged in
                    try:
                        page.goto("https://www.pinterest.com/", wait_until="domcontentloaded", timeout=30000)
                        page.wait_for_timeout(3000)
                        
                        # Check for home page elements
                        nav_selectors = [
                            '[data-test-selector="nav-search"]',
                            '[data-test-selector="pin-count"]',
                            'a[data-test-selector="logo"]',
                            '[data-testid="nav-search"]',
                            '[data-testid="logo"]',
                        ]
                        
                        for nsel in nav_selectors:
                            try:
                                if page.locator(nsel).first.is_visible(timeout=2000):
                                    print("\n  Login verified! Proceeding with upload.", flush=True)
                                    login_needed = False
                                    break
                            except:
                                continue
                        
                        if not login_needed:
                            break
                    except Exception as e:
                        print(f"  [WARN] Navigation error during login check: {e}", flush=True)
                
                elapsed = int(time.time() - start)
                if elapsed % 60 == 0:
                    print(f"  Still waiting for login... ({elapsed}s elapsed)", flush=True)
            else:
                print("\nERROR: Login timeout (300 seconds).", flush=True)
                print("  Please try again and complete login faster.", flush=True)
                context.close()
                return
        else:
            print("  Already logged in to Pinterest!", flush=True)
        
        # [2] Extract cookies from the authenticated session
        print("\n[2] Extracting Pinterest cookies...", flush=True)
        all_cookies = context.cookies()
        pinterest_cookies = [c for c in all_cookies if 'pinterest' in c.get('domain', '').lower()]
        
        print(f"  Found {len(pinterest_cookies)} Pinterest cookies", flush=True)
        session_cookie = None
        for c in pinterest_cookies:
            name = c['name']
            value = c['value']
            if len(value) > 40:
                val_display = value[:40] + '...'
            else:
                val_display = value
            print(f"    {name} = {val_display} (domain: {c.get('domain')})", flush=True)
            if c['name'] == '_pinterest_sess':
                session_cookie = c
        
        if not session_cookie:
            print("\n  ERROR: No _pinterest_sess cookie found!", flush=True)
            print("  You may not be properly logged in.", flush=True)
            page.screenshot(path=os.path.join(temp_dir, "debug_login.png"))
            context.close()
            return
        
        print("\n  _pinterest_sess cookie found - session is valid!", flush=True)
        
        # [3] Test Pinterest API with cookies
        print("\n[3] Testing Pinterest API v5 with cookies...", flush=True)
        
        import requests
        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in pinterest_cookies)
        
        s = requests.Session()
        s.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.pinterest.com/",
            "Cookie": cookie_header,
        })
        
        # Test boards endpoint
        resp = s.get("https://api.pinterest.com/v5/boards", timeout=15)
        print(f"  GET /v5/boards -> {resp.status_code}", flush=True)
        
        board_id = None
        if resp.status_code == 200:
            data = resp.json()
            items = data.get('items', [])
            print(f"  Found {len(items)} boards:", flush=True)
            
            # Find the target board
            for b in items:
                print(f"    ID={b.get('id')}, Name={b.get('name')}", flush=True)
                if b.get('name', '').lower() == board_name.lower():
                    board_id = b.get('id')
                    print(f"  *** Target board found: {board_name} (ID: {board_id}) ***", flush=True)
            
            if not board_id:
                print(f"\n  Target board '{board_name}' not found. Available boards:", flush=True)
                print(f"  Using first board ({items[0].get('name') if items else 'None'}) as target.", flush=True)
                if items:
                    board_id = items[0].get('id')
        else:
            print(f"  Error: {resp.text[:300]}", flush=True)
            print("  Falling back to web-based upload...", flush=True)
        
        # [4] Upload images
        results = []
        
        if board_id:
            # API-based upload
            print(f"\n[4] Uploading images via API (board ID: {board_id})...", flush=True)
            
            for i, img_path in enumerate(resized_paths, 1):
                fname = os.path.basename(img_path)
                print(f"\n  [{i}/{len(resized_paths)}] Uploading: {fname}", flush=True)
                
                try:
                    # Step 1: Register media upload
                    media_resp = s.post(
                        "https://api.pinterest.com/v5/media/upload",
                        headers={"Content-Type": "application/json"},
                        json={"media_type": "image"},
                        timeout=30,
                    )
                    
                    if media_resp.status_code != 200:
                        print(f"    [FAIL] Could not register media: {media_resp.status_code}", flush=True)
                        results.append((fname, None))
                        continue
                    
                    media_data = media_resp.json()
                    media_id = media_data.get("media_id")
                    upload_url = media_data.get("upload_url")
                    
                    if not media_id or not upload_url:
                        print(f"    [FAIL] No media_id or upload_url", flush=True)
                        results.append((fname, None))
                        continue
                    
                    print(f"    Media registered: {str(media_id)[:30]}...", flush=True)
                    
                    # Step 2: Upload image data
                    with open(img_path, "rb") as f:
                        upload_resp = s.put(
                            upload_url,
                            data=f,
                            headers={
                                "Content-Type": "image/jpeg",
                                "Content-Length": str(os.path.getsize(img_path)),
                            },
                            timeout=120,
                        )
                    
                    if upload_resp.status_code != 200:
                        print(f"    [FAIL] Upload failed: {upload_resp.status_code}", flush=True)
                        print(f"    Response: {upload_resp.text[:200]}", flush=True)
                        results.append((fname, None))
                        continue
                    
                    print(f"    Image uploaded successfully", flush=True)
                    
                    # Step 3: Create pin
                    pin_data = {
                        "board_id": board_id,
                        "media": {"media_id": media_id},
                        "title": "Gemini Generated Image",
                        "description": "AI generated artwork",
                    }
                    
                    pin_resp = s.post(
                        "https://api.pinterest.com/v5/pins",
                        headers={"Content-Type": "application/json"},
                        json=pin_data,
                        timeout=30,
                    )
                    
                    if pin_resp.status_code == 200:
                        result = pin_resp.json()
                        pin_id = result.get("id")
                        print(f"    [OK] Pin created: {pin_id}", flush=True)
                        results.append((fname, pin_id))
                    else:
                        print(f"    [FAIL] Pin creation failed: {pin_resp.status_code}", flush=True)
                        print(f"    Response: {pin_resp.text[:200]}", flush=True)
                        results.append((fname, None))
                
                except Exception as e:
                    print(f"    [FAIL] Error: {e}", flush=True)
                    results.append((fname, None))
                
                time.sleep(2)
        else:
            # Web-based fallback
            print(f"\n[4] Uploading via web UI...", flush=True)
            
            for i, img_path in enumerate(resized_paths, 1):
                fname = os.path.basename(img_path)
                print(f"\n  [{i}/{len(resized_paths)}] Uploading: {fname}", flush=True)
                
                try:
                    # Navigate to pin creation page
                    page.goto("https://www.pinterest.com/create/pin/", wait_until="domcontentloaded", timeout=60000)
                    page.wait_for_timeout(8000)
                    
                    # Find and click upload area
                    page.keyboard.press("Escape")  # Dismiss popups
                    page.wait_for_timeout(2000)
                    
                    # Try to find file input directly
                    file_input = None
                    for sel in ['input[type="file"]', 'input[accept*="image"]', '[data-testid="file-input"]']:
                        try:
                            elem = page.locator(sel)
                            if elem.count() > 0:
                                file_input = elem.first
                                break
                        except:
                            continue
                    
                    if not file_input:
                        # Click upload area first
                        for sel in ["[data-testid='pin-builder-upload']", "[data-test-selector='drop-zone']", "div:has-text('Upload')"]:
                            try:
                                area = page.locator(sel)
                                if area.count() > 0:
                                    area.first.click()
                                    page.wait_for_timeout(3000)
                                    break
                            except:
                                continue
                        
                        for sel in ['input[type="file"]', 'input[accept*="image"]']:
                            try:
                                elem = page.locator(sel)
                                if elem.count() > 0:
                                    file_input = elem.first
                                    break
                            except:
                                continue
                    
                    if file_input:
                        file_input.set_input_files(img_path)
                        print("  File selected, waiting for upload...", flush=True)
                        page.wait_for_timeout(15000)
                        
                        # Select board
                        for btn_sel in ['button:has-text("Add to board")', 'button:has-text("All Boards")']:
                            try:
                                btn = page.locator(btn_sel)
                                if btn.count() > 0:
                                    btn.first.click()
                                    page.wait_for_timeout(2000)
                                    break
                            except:
                                continue
                        
                        # Search for board
                        for inp_sel in ['input[placeholder*="Search"]', 'input[placeholder*="board"]']:
                            try:
                                inp = page.locator(inp_sel)
                                if inp.count() > 0:
                                    inp.fill(board_name)
                                    page.wait_for_timeout(2000)
                                    
                                    for opt_sel in ["[role='option']", f"li:has-text('{board_name}')"]:
                                        try:
                                            opt = page.locator(opt_sel)
                                            if opt.count() > 0:
                                                opt.first.click()
                                                break
                                        except:
                                            continue
                                    break
                            except:
                                continue
                        
                        page.wait_for_timeout(3000)
                        
                        # Publish
                        for pub_sel in ['button:has-text("Create Pin")', 'button:has-text("Create")', 'button:has-text("Publish")']:
                            try:
                                btn = page.locator(pub_sel)
                                if btn.count() > 0:
                                    btn.first.click()
                                    print("  Published!", flush=True)
                                    page.wait_for_timeout(8000)
                                    results.append((fname, "success"))
                                    break
                            except:
                                continue
                        else:
                            print("  [FAIL] Could not find publish button", flush=True)
                            results.append((fname, None))
                    else:
                        print("  [FAIL] Could not find file input", flush=True)
                        results.append((fname, None))
                
                except Exception as e:
                    print(f"  [FAIL] Error: {e}", flush=True)
                    results.append((fname, None))
                
                time.sleep(3)
        
        context.close()
        
        # Save results
        log_path = os.path.join(temp_dir, "upload_results.json")
        with open(log_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        success = sum(1 for _, s in results if s == "success" or s is not None)
        failed = len(results) - success
        
        print(f"\n{'='*50}", flush=True)
        print(f"Done! {success}/{len(results)} pins created", flush=True)
        if failed:
            print(f"  Failed: {failed}", flush=True)
        print(f"  Log: {log_path}", flush=True)
        print(f"{'='*50}", flush=True)

if __name__ == "__main__":
    main()
