#!/usr/bin/env python3
"""
Pinterest web uploader using Brave with cached profile.
Non-headless mode - user logs in manually if needed.
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
                      capture_output=True, timeout=10)
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
    from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
    
    brave_exe = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
    brave_user_data = os.path.join(
        os.environ.get("LOCALAPPDATA", r"C:\Users\Dima D'origine\AppData\Local"),
        "BraveSoftware", "Brave-Browser", "User Data"
    )
    
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
    
    # Copy profile
    temp_profile = r"C:\Users\Dima D'origine\AppData\Local\Temp\brave_pinterest_session"
    if os.path.exists(temp_profile):
        shutil.rmtree(temp_profile, ignore_errors=True)
    
    default_src = os.path.join(brave_user_data, "Default")
    default_dst = os.path.join(temp_profile, "Default")
    if os.path.isdir(default_src):
        print(f"\nCopying Brave profile...", flush=True)
        shutil.copytree(default_src, default_dst, dirs_exist_ok=True)
        print(f"  Done", flush=True)
    
    print(f"\nStarting browser...")
    print(f"  Go to https://www.pinterest.com/ and log in if needed.", flush=True)
    print(f"  The browser window will stay open for 180 seconds.", flush=True)
    print(f"  Press Ctrl+C to abort at any time.", flush=True)
    
    with sync_playwright() as p:
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
        print("\nNavigating to Pinterest...", flush=True)
        page.goto("https://www.pinterest.com/", wait_until="domcontentloaded", timeout=60000)
        page.wait_for_timeout(3000)
        
        # Check if login form is visible
        login_needed = False
        try:
            login_input = page.wait_for_selector('input[name="id"]', state="visible", timeout=5000)
            if login_input:
                login_needed = True
        except:
            try:
                page.wait_for_selector('input[name="password"]', state="visible", timeout=5000)
                login_needed = True
            except:
                pass
        
        if login_needed:
            print("\n*** ATTENTION: Please log in to Pinterest in the browser window ***", flush=True)
            print("*** Waiting 180 seconds for you to complete login... ***", flush=True)
            print("*** The browser window is on top. ***", flush=True)
            print(f"*** Login URL: https://www.pinterest.com/ ***", flush=True)
            
            # Bring browser window to front
            time.sleep(1)
            
            start = time.time()
            while time.time() - start < 180:
                try:
                    page.wait_for_selector('input[name="id"]', state="hidden", timeout=5000)
                    print("  Login form disappeared, checking...", flush=True)
                    time.sleep(3)
                    
                    # Verify login
                    page.goto("https://www.pinterest.com/", wait_until="domcontentloaded", timeout=30000)
                    page.wait_for_timeout(3000)
                    
                    nav_selectors = [
                        '[data-test-selector="nav-search"]',
                        '[data-test-selector="pin-count"]',
                        'a[data-test-selector="logo"]',
                    ]
                    for sel in nav_selectors:
                        try:
                            if page.locator(sel).first.is_visible(timeout=2000):
                                print("  Login verified! Proceeding with upload.", flush=True)
                                login_needed = False
                                break
                        except:
                            continue
                except:
                    pass
                time.sleep(3)
        else:
            print("  Already logged in to Pinterest!", flush=True)
        
        if login_needed:
            print("ERROR: Login not completed within timeout.", flush=True)
            context.close()
            return
        
        # Upload each image
        results = []
        for i, img_path in enumerate(resized_paths, 1):
            fname = os.path.basename(img_path)
            print(f"\n[{i}/{len(resized_paths)}] Uploading: {fname}", flush=True)
            
            try:
                # Navigate to create pin
                page.goto("https://www.pinterest.com/create/pin/", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(8000)
                
                print(f"  URL: {page.url}", flush=True)
                
                # Dismiss popups
                try:
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(1000)
                except:
                    pass
                
                # Find file input
                file_input = None
                all_selectors = [
                    'input[type="file"]',
                    'input[accept*="image"]',
                    'input[name="imageSource"]',
                    '[data-testid="file-input"]',
                    '[data-test-selector="pin-builder-input"]',
                    '[data-test-id="drop-zone-input"]',
                    'input[accept="image/*"]',
                    'input[accept="image/jpeg"]',
                ]
                
                for sel in all_selectors:
                    try:
                        elem = page.locator(sel)
                        if elem.count() > 0:
                            file_input = elem.first
                            print(f"  Found file input: {sel}", flush=True)
                            break
                    except:
                        continue
                
                if not file_input:
                    # Try clicking upload area
                    upload_areas = [
                        "[data-testid='pin-builder-upload']",
                        "[data-test-selector='drop-zone']",
                        "div:has-text('Upload')",
                        "button:has-text('Upload')",
                    ]
                    
                    for area_sel in upload_areas:
                        try:
                            area = page.locator(area_sel)
                            if area.count() > 0:
                                area.first.click()
                                page.wait_for_timeout(2000)
                                break
                        except:
                            continue
                    
                    for sel in all_selectors:
                        try:
                            elem = page.locator(sel)
                            if elem.count() > 0:
                                file_input = elem.first
                                break
                        except:
                            continue
                
                if not file_input:
                    print(f"  [FAIL] Could not find file input for {fname}", flush=True)
                    page.screenshot(path=os.path.join(temp_dir, f"debug_{i}.png"))
                    results.append((fname, None))
                    continue
                
                # Upload
                file_input.set_input_files(img_path)
                print(f"  File selected, waiting...", flush=True)
                page.wait_for_timeout(10000)
                
                # Select board
                try:
                    board_btns = [
                        'button:has-text("Add to board")',
                        'button:has-text("All Boards")',
                        '[data-test-selector="board-select"]',
                        '[data-testid="board-select-button"]',
                    ]
                    
                    for sel in board_btns:
                        try:
                            btn = page.locator(sel)
                            if btn.count() > 0:
                                btn.first.click()
                                page.wait_for_timeout(2000)
                                break
                        except:
                            continue
                    
                    # Search board
                    search_inps = [
                        'input[placeholder*="Search"]',
                        'input[placeholder*="board"]',
                        'input[aria-label*="Search"]',
                    ]
                    
                    for sel in search_inps:
                        try:
                            inp = page.locator(sel)
                            if inp.count() > 0:
                                inp.fill(board_name)
                                page.wait_for_timeout(2000)
                                
                                # Select board option
                                board_opts = [
                                    "[role='option']",
                                    "[data-test-selector='board-option']",
                                    f"li:has-text('{board_name}')",
                                ]
                                
                                for opt_sel in board_opts:
                                    try:
                                        opt = page.locator(opt_sel)
                                        if opt.count() > 0:
                                            opt.first.click()
                                            print(f"  Selected board: {board_name}", flush=True)
                                            break
                                    except:
                                        continue
                                break
                        except:
                            continue
                except Exception as e:
                    print(f"  [WARN] Board selection error: {e}", flush=True)
                
                page.wait_for_timeout(3000)
                
                # Click publish
                publish_selectors = [
                    'button:has-text("Create Pin")',
                    'button:has-text("Create")',
                    'button:has-text("Publish")',
                ]
                
                published = False
                for sel in publish_selectors:
                    try:
                        btn = page.locator(sel)
                        if btn.count() > 0:
                            btn.first.click()
                            print(f"  Clicked: {sel}", flush=True)
                            page.wait_for_timeout(8000)
                            published = True
                            break
                    except:
                        continue
                
                if published:
                    print(f"  [OK] Pin created: {fname}", flush=True)
                    results.append((fname, "success"))
                else:
                    print(f"  [FAIL] Could not click publish", flush=True)
                    results.append((fname, None))
                
            except Exception as e:
                print(f"  [FAIL] Error: {e}", flush=True)
                results.append((fname, None))
            
            time.sleep(3)
        
        context.close()
        
        # Save log
        log_path = os.path.join(temp_dir, "upload_results.json")
        with open(log_path, 'w') as f:
            json.dump(results, f, indent=2)
        
        success = sum(1 for _, s in results if s == "success")
        failed = len(results) - success
        
        print(f"\n{'='*50}", flush=True)
        print(f"Done! {success}/{len(results)} pins created", flush=True)
        if failed:
            print(f"  Failed: {failed}", flush=True)
        print(f"  Log: {log_path}", flush=True)
        print(f"{'='*50}", flush=True)

if __name__ == "__main__":
    main()
