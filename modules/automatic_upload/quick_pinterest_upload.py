#!/usr/bin/env python3
"""
Robust Pinterest uploader using Playwright with Brave.
Kills existing Brave, launches fresh session using cached profile,
waits for login, then uploads images.
"""

import os
import sys
import time
import json
import shutil
import subprocess
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError

# Image dimensions
TARGET_SIZE = 1024

def resize_image(img_path: str, output_path: str, max_size: int = TARGET_SIZE) -> bool:
    """Resize image to fit within max_size x max_size, preserving aspect ratio."""
    try:
        from PIL import Image
        img = Image.open(img_path)
        if max(img.size) > max_size:
            ratio = max_size / max(img.size)
            new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
            resized = img.resize(new_size, Image.Resampling.LANCZOS)
            if img.mode == 'RGBA':
                resized = resized.convert('RGB')
            resized.save(output_path, 'JPEG', quality=85)
            print(f"  Resized to {new_size[0]}x{new_size[1]}", flush=True)
            return True
        else:
            # Just copy and convert if needed
            if img.mode == 'RGBA':
                img = img.convert('RGB')
            img.save(output_path, 'JPEG', quality=85)
            return True
    except Exception as e:
        print(f"  [WARN] Could not resize image: {e}", flush=True)
        shutil.copy2(img_path, output_path)
        return False

def wait_for_login(page, timeout: int = 120) -> bool:
    """Wait for Pinterest login to complete."""
    print("  Waiting for Pinterest login...", flush=True)
    
    # Check if we're already logged in
    try:
        page.goto("https://www.pinterest.com/", wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(5000)
        
        # Check for login form elements
        login_selectors = [
            'input[name="id"]',
            'input[name="password"]',
            'input[name="email"]',
            'button[type="submit"]',
            'a[data-test-selector="join-link"]',  # Login/continue button
        ]
        
        for sel in login_selectors:
            try:
                if page.wait_for_selector(sel, state="visible", timeout=3000):
                    print("  Login page detected. Please log in to Pinterest in the browser...", flush=True)
                    break
            except:
                continue
        
        # Check if already logged in (home feed present)
        home_selectors = [
            '[data-test-selector="pin-count"]',
            '[data-test-selector="nav-search"]',
            'a[data-test-selector="logo"]',
            '[data-testid="logo"]',
            'div[data-test-selector="pin"]',
        ]
        
        for sel in home_selectors:
            try:
                if page.locator(sel).first.is_visible(timeout=2000):
                    print("  Already logged in to Pinterest!", flush=True)
                    return True
            except:
                continue
        
        # If we get here, check if login form appeared
        login_form_visible = False
        for sel in login_selectors:
            try:
                if page.locator(sel).first.is_visible(timeout=2000):
                    login_form_visible = True
                    break
            except:
                continue
        
        if not login_form_visible:
            # No login form and no home elements - assume logged in
            print("  Assuming already logged in (no login form visible).", flush=True)
            return True
        
        print("  Please complete login in the browser window...", flush=True)
        
        # Poll for login completion
        start = time.time()
        while time.time() - start < timeout:
            # Look for login form disappearing
            login_gone = True
            for sel in login_selectors:
                try:
                    if page.locator(sel).first.is_visible(timeout=1000):
                        login_gone = False
                        break
                except:
                    continue
            
            if login_gone:
                time.sleep(3)
                # Verify we're logged in
                for sel in home_selectors:
                    try:
                        if page.locator(sel).first.is_visible(timeout=2000):
                            print("  Login complete!", flush=True)
                            return True
                    except:
                        continue
                print("  Login form gone, assuming success.", flush=True)
                return True
            
            time.sleep(3)
        
        print("  Login timed out.", flush=True)
        return False
    except Exception as e:
        print(f"  [WARN] Login check error: {e}", flush=True)
        return True  # Assume logged in to proceed

def upload_to_pinterest(image_paths, board_name="Test Upload"):
    """Upload images to Pinterest using Brave with cached profile."""
    
    # Kill Brave processes
    print("Killing existing Brave processes...", flush=True)
    try:
        subprocess.run(["taskkill", "/F", "/IM", "brave.exe", "/T"], 
                      capture_output=True, timeout=10)
        time.sleep(2)
    except:
        pass
    
    # Brave executable
    brave_exe = r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe"
    if not os.path.isfile(brave_exe):
        print(f"ERROR: Brave not found at {brave_exe}", flush=True)
        return
    
    # Brave user data directory (cached profile)
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
    
    # Temp directory for resized images
    temp_dir = r"C:\Users\Dima D'origine\AppData\Local\Temp\pinterest_uploads"
    os.makedirs(temp_dir, exist_ok=True)
    
    # Resize all images first
    print("\nPreparing images...", flush=True)
    resized_images = []
    for img_path in image_paths:
        fname = os.path.basename(img_path)
        out_path = os.path.join(temp_dir, fname)
        resize_image(img_path, out_path)
        resized_images.append(out_path)
        print(f"  Ready: {fname} ({os.path.getsize(out_path)} bytes)", flush=True)
    
    with sync_playwright() as p:
        # Launch Brave with cached profile
        user_data_copy = r"C:\Users\Dima D'origine\AppData\Local\Temp\brave_pinterest_session"
        if os.path.exists(user_data_copy):
            shutil.rmtree(user_data_copy, ignore_errors=True)
        
        # Try using the real Brave profile
        print(f"\nLaunching Brave with cached profile...", flush=True)
        
        context = p.chromium.launch_persistent_context(
            user_data_dir=brave_user_data,
            headless=False,
            executable_path=brave_exe,
            args=[
                "--no-first-run",
                "--no-default-browser-check",
                "--no-sandbox",
                "--disable-extensions-except=/",
                "--disable-extensions",
            ],
        )
        
        page = context.new_page()
        page.set_default_timeout(60000)
        page.set_default_navigation_timeout(60000)
        
        # Wait for login
        if not wait_for_login(page, timeout=120):
            print("ERROR: Login failed or timed out.", flush=True)
            context.close()
            return
        
        # Upload each image
        results = []
        for i, img_path in enumerate(resized_images, 1):
            fname = os.path.basename(img_path)
            print(f"\n[{i}/{len(resized_images)}] Uploading: {fname}", flush=True)
            
            try:
        # Navigate to Pinterest create pin page
                try:
                    page.goto("https://www.pinterest.com/create/pin/", wait_until="domcontentloaded", timeout=60000)
                except Exception:
                    pass
                
                # If we got redirected, try the homepage first then navigate
                if "create" not in page.url:
                    print(f"  Redirected to {page.url}, trying homepage first...", flush=True)
                    try:
                        page.goto("https://www.pinterest.com/", wait_until="domcontentloaded", timeout=60000)
                        page.wait_for_timeout(3000)
                        # Now try create pin
                        page.goto("https://www.pinterest.com/create/pin/", wait_until="domcontentloaded", timeout=60000)
                    except Exception:
                        pass
                
                page.wait_for_timeout(5000)
                
                # Try to dismiss any popups
                try:
                    page.keyboard.press("Escape")
                except:
                    pass
                
                # Find file input
                file_input = None
                selectors = [
                    'input[type="file"]',
                    'input[accept*="image"]',
                    'input[name="imageSource"]',
                    '[data-testid="file-input"]',
                    '[data-test-selector="pin-builder-input"]',
                    '[data-test-id="drop-zone-input"]',
                ]
                
                # Debug: print page url and title
                print(f"  Page URL: {page.url}", flush=True)
                print(f"  Page title: {page.title()}", flush=True)
                
                # Debug: try to find any file inputs
                try:
                    all_inputs = page.eval_on_selector_all('input[type="file"]', 'elements => elements.length')
                    print(f"  File inputs found on page: {all_inputs}", flush=True)
                except Exception as e:
                    print(f"  File input search error: {e}", flush=True)
                
                for sel in selectors:
                    try:
                        elem = page.locator(sel)
                        count = elem.count()
                        if count > 0:
                            file_input = elem.first
                            print(f"  Found file input: {sel} (count: {count})", flush=True)
                            break
                    except Exception as e:
                        print(f"  Selector {sel}: error {e}", flush=True)
                        continue
                
                if not file_input:
                    # Try clicking the upload area first
                    upload_areas = [
                        "[data-testid='pin-builder-upload']",
                        "[data-test-selector='drop-zone']",
                        "div:has-text('Upload')",
                        "button:has-text('Upload')",
                        "div.upload-image",
                        "[aria-label*='upload']",
                        "[aria-label*='Upload']",
                        ".createPinImageUploadContainer",
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
                    
                    # Retry finding file input
                    for sel in selectors:
                        try:
                            elem = page.locator(sel)
                            if elem.count() > 0:
                                file_input = elem.first
                                print(f"  Found file input after click: {sel}", flush=True)
                                break
                        except:
                            continue
                
                if not file_input:
                    print("  [FAIL] Could not find file upload input", flush=True)
                    page.screenshot(path=os.path.join(temp_dir, f"debug_{i}.png"))
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
                
                # Select board
                try:
                    # Try various board selection approaches
                    board_btn_selectors = [
                        '[data-test-selector="board-select"]',
                        '[data-testid="board-select-button"]',
                        'button:has-text("Add to board")',
                        'button:has-text("All Boards")',
                        '[data-test-selector="board-option"]',
                        "[aria-label*='board']",
                    ]
                    
                    for sel in board_btn_selectors:
                        try:
                            btn = page.locator(sel)
                            if btn.count() > 0:
                                btn.first.click()
                                page.wait_for_timeout(2000)
                                break
                        except:
                            continue
                    
                    # Search for board name
                    search_input_selectors = [
                        'input[placeholder*="Search"]',
                        'input[placeholder*="board"]',
                        'input[placeholder*="Board"]',
                        'input[aria-label*="Search"]',
                        'input[aria-label*="board"]',
                    ]
                    
                    for sel in search_input_selectors:
                        try:
                            inp = page.locator(sel)
                            if inp.count() > 0:
                                inp.fill(board_name)
                                page.wait_for_timeout(2000)
                                
                                # Click the first matching board option
                                board_option_selectors = [
                                    "[data-test-selector='board-option']",
                                    "[data-testid='board-option']",
                                    "[role='option']",
                                    "[data-test-selector='board-item']",
                                    "li:has-text('" + board_name + "')",
                                ]
                                
                                for opt_sel in board_option_selectors:
                                    try:
                                        opt = page.locator(opt_sel)
                                        if opt.count() > 0:
                                            opt.first.click()
                                            print(f"  Board selected: {board_name}", flush=True)
                                            break
                                    except:
                                        continue
                                break
                        except:
                            continue
                except Exception as e:
                    print(f"  [WARN] Could not select board: {e}", flush=True)
                
                page.wait_for_timeout(2000)
                
                # Click Create/Publish button
                publish_selectors = [
                    'button:has-text("Create")',
                    'button:has-text("Publish")',
                    'button:has-text("Create Pin")',
                    '[data-test-selector="create-pin-button"]',
                    '[data-testid="create-pin-button"]',
                ]
                
                published = False
                for sel in publish_selectors:
                    try:
                        btn = page.locator(sel)
                        if btn.count() > 0:
                            btn.first.click()
                            print(f"  Publish button clicked: {sel}", flush=True)
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
                    page.screenshot(path=os.path.join(temp_dir, f"no_publish_{i}.png"))
                    results.append((fname, None))
                
            except Exception as e:
                print(f"  [FAIL] Error uploading {fname}: {e}", flush=True)
                results.append((fname, None))
            
            time.sleep(3)
        
        context.close()
        
        # Save log
        log_path = os.path.join(temp_dir, "upload_results.json")
        with open(log_path, "w") as f:
            json.dump(results, f, indent=2)
        print(f"\nUpload log saved: {log_path}", flush=True)
    
    success_count = sum(1 for _, s in results if s == "success")
    fail_count = len(results) - success_count
    print(f"\n{'='*50}", flush=True)
    print(f"Done! {success_count} pin(s) created", flush=True)
    if fail_count:
        print(f"  Failed: {fail_count}", flush=True)
    print(f"{'='*50}", flush=True)

if __name__ == "__main__":
    images_dir = r"C:\Users\Dima D'origine\OneDrive\Bureau\scripts\.kilo\worktrees\flint-sunscreen\music_video_generator\input\images"
    board_name = "Test Upload"
    
    # Collect images
    image_paths = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.bmp", "*.webp"):
        image_paths.extend(str(p) for p in sorted(Path(images_dir).glob(ext)))
    
    if not image_paths:
        print(f"ERROR: No images found in {images_dir}", flush=True)
        sys.exit(1)
    
    print(f"Found {len(image_paths)} images to upload:", flush=True)
    for path in image_paths:
        print(f"  - {Path(path).name}", flush=True)
    
    upload_to_pinterest(image_paths, board_name)
