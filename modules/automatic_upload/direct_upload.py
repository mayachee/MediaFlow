#!/usr/bin/env python3
"""
Direct Pinterest web uploader using Brave with cached profile.
Kills Brave, copies profile, launches headless, navigates to create pin,
uploads images directly.
"""

import os
import sys
import json
import time
import shutil
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright

def kill_brave():
    try:
        subprocess.run(["taskkill", "/F", "/IM", "brave.exe", "/T"], 
                      capture_output=True, timeout=10)
        time.sleep(2)
        print("  Killed Brave processes", flush=True)
        return True
    except Exception as e:
        print(f"  [WARN] Could not kill Brave: {e}", flush=True)
        return False

def main():
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
    
    # Prepare images (resize)
    temp_dir = r"C:\Users\Dima D'origine\AppData\Local\Temp\pinterest_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    
    from PIL import Image
    resized_paths = []
    for img_path in image_paths:
        fname = os.path.basename(img_path)
        out_path = os.path.join(temp_dir, fname)
        
        img = Image.open(img_path)
        if max(img.size) > 1024:
            ratio = 1024 / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            resized = img.resize(new_size, Image.Resampling.LANCZOS)
            if img.mode == 'RGBA':
                resized = resized.convert('RGB')
            resized.save(out_path, 'JPEG', quality=85)
            print(f"  Resized: {fname} -> {new_size[0]}x{new_size[1]}", flush=True)
        else:
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            shutil.copy2(img_path, out_path)
        resized_paths.append(out_path)
    
    kill_brave()
    
    # Copy profile
    temp_profile = r"C:\Users\Dima D'origine\AppData\Local\Temp\brave_pinterest_upload"
    if os.path.exists(temp_profile):
        shutil.rmtree(temp_profile, ignore_errors=True)
    
    default_src = os.path.join(brave_user_data, "Default")
    default_dst = os.path.join(temp_profile, "Default")
    if os.path.isdir(default_src):
        print(f"\nCopying Brave profile...", flush=True)
        shutil.copytree(default_src, default_dst, dirs_exist_ok=True)
        print(f"  Done", flush=True)
    
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=temp_profile,
            headless=False,  # Non-headless so user can interact if needed
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
        page.wait_for_timeout(5000)
        
        # Check if logged in
        print(f"  URL: {page.url}", flush=True)
        print(f"  Title: {page.title()}", flush=True)
        
        # Check for login form
        try:
            login_input = page.wait_for_selector('input[name="id"]', state="visible", timeout=5000)
            if login_input:
                print("  Login form detected. Please log in to Pinterest in the browser.", flush=True)
                print("  Waiting 120 seconds for login...", flush=True)
                
                start = time.time()
                while time.time() - start < 120:
                    try:
                        page.wait_for_selector('input[name="id"]', state="hidden", timeout=5000)
                        print("  Login form disappeared, checking if logged in...", flush=True)
                        time.sleep(3)
                        
                        # Check if we're logged in
                        try:
                            page.goto("https://www.pinterest.com/", wait_until="domcontentloaded", timeout=30000)
                            page.wait_for_timeout(3000)
                            # Look for home page elements
                            if page.locator('[data-test-selector="nav-search"]').count() > 0:
                                print("  Logged in successfully!", flush=True)
                                break
                        except:
                            pass
                    except:
                        pass
                    time.sleep(3)
        except:
            print("  No login form detected - may already be logged in", flush=True)
        
        # Now try uploading each image
        results = []
        for i, img_path in enumerate(resized_paths, 1):
            fname = os.path.basename(img_path)
            print(f"\n[{i}/{len(resized_paths)}] Uploading: {fname}", flush=True)
            
            try:
                # Navigate to create pin page
                page.goto("https://www.pinterest.com/create/pin/", wait_until="domcontentloaded", timeout=60000)
                page.wait_for_timeout(8000)
                
                print(f"  Page URL: {page.url}", flush=True)
                
                # Dismiss popups
                try:
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(1000)
                except:
                    pass
                
                # Take a screenshot for debugging
                screenshot_path = os.path.join(temp_dir, f"debug_{i}.png")
                page.screenshot(path=screenshot_path)
                print(f"  Screenshot saved: {screenshot_path}", flush=True)
                
                # Find file input - try many selectors
                file_input = None
                all_selectors = [
                    'input[type="file"]',
                    'input[accept*="image"]',
                    'input[name="imageSource"]',
                    'input[name="image_url"]',
                    '[data-testid="file-input"]',
                    '[data-test-selector="pin-builder-input"]',
                    '[data-test-id="drop-zone-input"]',
                    '[data-test-selector="file-input"]',
                    'div[data-test-selector="file-input"]',
                    'input[accept="image/*"]',
                    'input[accept="image/jpeg"]',
                ]
                
                for sel in all_selectors:
                    try:
                        elem = page.locator(sel)
                        count = elem.count()
                        if count > 0:
                            file_input = elem.first
                            print(f"  Found file input: {sel} (count: {count})", flush=True)
                            break
                    except:
                        continue
                
                if not file_input:
                    # Try clicking upload area first
                    upload_areas = [
                        "[data-testid='pin-builder-upload']",
                        "[data-test-selector='drop-zone']",
                        "div:has-text('Upload')",
                        "button:has-text('Upload')",
                        "div.upload-image",
                        "[aria-label*='upload']",
                        "[aria-label*='Upload']",
                        ".createPinImageUploadContainer",
                        "div[data-test-selector='file-input']",
                        "[data-test-selector='drop-zone-input']",
                        "button[data-test-selector]",
                    ]
                    
                    for area_sel in upload_areas:
                        try:
                            area = page.locator(area_sel)
                            count = area.count()
                            if count > 0:
                                print(f"  Clicking upload area: {area_sel} (count: {count})", flush=True)
                                area.first.click()
                                page.wait_for_timeout(3000)
                                break
                        except:
                            continue
                    
                    # Retry finding file input
                    for sel in all_selectors:
                        try:
                            elem = page.locator(sel)
                            if elem.count() > 0:
                                file_input = elem.first
                                print(f"  Found file input after click: {sel}", flush=True)
                                break
                        except:
                            continue
                
                if not file_input:
                    print(f"  [FAIL] Could not find file upload input for {fname}", flush=True)
                    results.append((fname, None))
                    continue
                
                # Upload the image
                try:
                    file_input.set_input_files(img_path)
                    print(f"  File selected, waiting for upload...", flush=True)
                    page.wait_for_timeout(10000)
                except Exception as e:
                    print(f"  [FAIL] Could not set file: {e}", flush=True)
                    results.append((fname, None))
                    continue
                
                # Wait for image preview to appear
                page.wait_for_timeout(5000)
                
                # Select board
                print(f"  Selecting board: {board_name}", flush=True)
                try:
                    # Try different board selection approaches
                    board_button_selectors = [
                        'button:has-text("Add to board")',
                        'button:has-text("All Boards")',
                        '[data-test-selector="board-select"]',
                        '[data-testid="board-select-button"]',
                        "[aria-label*='board']",
                        "[aria-label*='Board']",
                        "div:has-text('Add to board')",
                    ]
                    
                    for sel in board_button_selectors:
                        try:
                            btn = page.locator(sel)
                            if btn.count() > 0:
                                btn.first.click()
                                print(f"  Clicked board button: {sel}", flush=True)
                                page.wait_for_timeout(2000)
                                break
                        except:
                            continue
                    
                    # Search for board
                    search_selectors = [
                        'input[placeholder*="Search"]',
                        'input[placeholder*="board"]',
                        'input[placeholder*="Board"]',
                        'input[aria-label*="Search"]',
                        'input[type="search"]',
                    ]
                    
                    for sel in search_selectors:
                        try:
                            inp = page.locator(sel)
                            if inp.count() > 0:
                                inp.fill(board_name)
                                print(f"  Entered board name in: {sel}", flush=True)
                                page.wait_for_timeout(3000)
                                
                                # Click the board option
                                board_option_selectors = [
                                    "[role='option']",
                                    "[data-test-selector='board-option']",
                                    "[data-test-selector='board-item']",
                                    "[data-testid='board-option']",
                                    f"li:has-text('{board_name}')",
                                    f"button:has-text('{board_name}')",
                                    f"div:has-text('{board_name}')",
                                ]
                                
                                for opt_sel in board_option_selectors:
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
                    print(f"  [WARN] Could not select board: {e}", flush=True)
                
                page.wait_for_timeout(3000)
                
                # Add title/description
                try:
                    title_input = page.locator('textarea[placeholder*="Add a title"], [data-test-selector="pin-title"]').first
                    if title_input.count() > 0:
                        title_input.fill("Gemini Generated Image")
                        print("  Added title", flush=True)
                        page.wait_for_timeout(1000)
                except:
                    pass
                
                # Click publish
                publish_selectors = [
                    'button:has-text("Create")',
                    'button:has-text("Publish")',
                    'button:has-text("Create Pin")',
                    '[data-test-selector="create-pin-button"]',
                    '[data-testid="create-pin-button"]',
                    "[aria-label*='Create']",
                ]
                
                published = False
                for sel in publish_selectors:
                    try:
                        btn = page.locator(sel)
                        if btn.count() > 0:
                            btn.first.click()
                            print(f"  Clicked publish: {sel}", flush=True)
                            page.wait_for_timeout(8000)
                            published = True
                            break
                    except:
                        continue
                
                if published:
                    print(f"  [OK] Pin created: {fname}", flush=True)
                    results.append((fname, "success"))
                else:
                    print(f"  [FAIL] Could not find publish button", flush=True)
                    results.append((fname, None))
                
            except Exception as e:
                print(f"  [FAIL] Error uploading {fname}: {e}", flush=True)
                results.append((fname, None))
            
            time.sleep(5)
        
        context.close()
        
        # Save results
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
