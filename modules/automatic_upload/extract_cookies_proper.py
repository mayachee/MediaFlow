#!/usr/bin/env python3
"""
Alternative cookie extraction using Windows DPAPI in the user's own session.
Tries to decrypt Brave cookies by using the CryptUnprotectData API properly.
"""

import os
import sys
import json
import sqlite3
import tempfile
import win32security
import win32api
import win32con
import win32file
import win32crypt
import requests

def enable_backup_privilege():
    """Enable SeBackupPrivilege to read locked files."""
    try:
        token = win32security.OpenProcessToken(
            win32api.GetCurrentProcess(),
            win32con.TOKEN_ADJUST_PRIVILEGES | win32con.TOKEN_QUERY
        )
        priv_id = win32security.LookupPrivilegeValue(None, "SeBackupPrivilege")
        win32security.AdjustTokenPrivileges(
            token, False, [(priv_id, win32con.SE_PRIVILEGE_ENABLED)]
        )
        err = win32api.GetLastError()
        return err == 0
    except Exception as e:
        print(f"  Could not enable SeBackupPrivilege: {e}")
        return False

def copy_locked_file(src, dst):
    """Copy a file even if it's locked by another process."""
    GENERIC_READ = 0x80000000
    OPEN_EXISTING = 3
    FILE_FLAG_BACKUP_SEMANTICS = 0x02000000
    FILE_SHARE_READ = 1
    FILE_SHARE_WRITE = 2
    
    handle = win32file.CreateFile(
        src,
        GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_WRITE,
        None,
        OPEN_EXISTING,
        FILE_FLAG_BACKUP_SEMANTICS,
        None,
    )
    try:
        with open(dst, "wb") as f:
            while True:
                _, data = win32file.ReadFile(handle, 65536)
                if not data:
                    break
                f.write(data)
        return True
    except Exception as e:
        print(f"    Error: {e}")
        return False
    finally:
        win32file.CloseHandle(handle)

def find_brave_cookie_db():
    """Find the Brave cookies database."""
    candidates = [
        os.path.join(os.environ.get("LOCALAPPDATA", ""),
                     "BraveSoftware", "Brave-Browser", "User Data", "Default", "Network", "Cookies"),
        os.path.join(os.path.expanduser("~"), "AppData", "Local", "BraveSoftware",
                     "Brave-Browser", "User Data", "Default", "Network", "Cookies"),
    ]
    for path in candidates:
        if os.path.isfile(path):
            return path
    return None

def decrypt_cookie(encrypted_value):
    """Decrypt a Chromium cookie value using Windows DPAPI."""
    if not encrypted_value:
        return None
    
    # Chromium uses two formats:
    # 1. OSCrypt::kDPAPI (Windows): Uses CryptProtectData (DPAPI)
    # 2. OSCrypt::kKey: (older): Starts with "v10" or "v11" prefix, then uses AES-GCM
    
    try:
        # Try DPAPI decryption first
        decrypted = win32crypt.CryptUnprotectData(encrypted_value)
        if decrypted and len(decrypted) > 1:
            return decrypted[1].decode("utf-8", errors="replace")
    except Exception as e:
        # This might be the AES-GCM format
        pass
    
    # Try AES-GCM decryption (Chrome 110+ format with "v10" or "v11" prefix)
    try:
        if encrypted_value[:4] in (b'v10', b'v11'):
            # This is the newer format - requires the encryption key
            # The key is stored in Local State file under os_crypt.encrypted_key
            # This is more complex to decrypt
            pass
    except:
        pass
    
    return None

def main():
    print("=" * 60, flush=True)
    print("Pinterest Cookie Extraction (Brave, Windows DPAPI)", flush=True)
    print("=" * 60, flush=True)
    
    # Step 1: Enable SeBackupPrivilege
    print("\n[1] Enabling SeBackupPrivilege...", flush=True)
    if enable_backup_privacy():
        print("  SeBackupPrivilege enabled!", flush=True)
    else:
        print("  SeBackupPrivilege not available (will try anyway)", flush=True)
    
    # Step 2: Find cookie DB
    print("\n[2] Locating Brave cookie database...", flush=True)
    cookie_db = find_brave_cookie_db()
    if not cookie_db:
        print("  ERROR: Could not find Brave cookie database!", flush=True)
        sys.exit(1)
    
    print(f"  Found: {cookie_db}", flush=True)
    
    # Step 3: Copy the cookie DB
    print("\n[3] Copying cookie database...", flush=True)
    tmp_db = os.path.join(tempfile.gettempdir(), "brave_cookies_copy_temp")
    if copy_locked_file(cookie_db, tmp_db):
        print(f"  Copy successful: {os.path.getsize(tmp_db)} bytes", flush=True)
    else:
        print("  ERROR: Could not copy cookie database", flush=True)
        sys.exit(1)
    
    # Step 4: Extract Pinterest cookies
    print("\n[4] Extracting Pinterest cookies...", flush=True)
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    print(f"  SQLite tables: {tables}", flush=True)
    
    cursor.execute("""
        SELECT host_key, name, value, encrypted_value, path
        FROM cookies
        WHERE host_key LIKE '%pinterest%'
    """)
    rows = cursor.fetchall()
    print(f"  Pinterest cookies found: {len(rows)}", flush=True)
    
    cookies_list = []
    for r in rows:
        host = r["host_key"]
        name = r["name"]
        value = r["value"]
        encrypted = r["encrypted_value"]
        path = r["path"]
        
        if value and len(value) > 0:
            cookie_val = value
        elif encrypted and len(encrypted) > 0:
            cookie_val = decrypt_cookie(encrypted)
            if cookie_val is None:
                continue
        
        if cookie_val:
            cookies_list.append((name, cookie_val, host, path))
            # Show a masked version
            masked = cookie_val[:20] + "..." if len(cookie_val) > 20 else cookie_val
            print(f"    {name} = {masked}", flush=True)
    
    conn.close()
    
    if not cookies_list:
        print("\n  ERROR: No Pinterest cookies could be decrypted.", flush=True)
        print("  This may be because:", flush=True)
        print("  1. Brave is still running (close it first)", flush=True)
        print("  2. You are not logged in to Pinterest in Brave", flush=True)
        print("  3. Cookie encryption uses AES-GCM (Chrome 110+ format)", flush=True)
        sys.exit(1)
    
    # Step 5: Test API with cookies
    print("\n[5] Testing Pinterest API with cookies...", flush=True)
    
    cj = requests.cookies.RequestsCookieJar()
    for name, value, host, path in cookies_list:
        domain = host.lstrip(".")
        cj.set(name, value, domain=domain, path=path)
    
    s = requests.Session()
    s.cookies = cj
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.pinterest.com/",
    })
    
    # Test boards endpoint
    try:
        resp = s.get("https://api.pinterest.com/v5/boards", timeout=15)
        print(f"  GET /v5/boards -> {resp.status_code}", flush=True)
        if resp.status_code == 200:
            data = resp.json()
            items = data.get("items", [])
            print(f"  Found {len(items)} boards:", flush=True)
            for b in items:
                print(f"    ID={b.get('id')}, Name={b.get('name')}", flush=True)
            
            # Save cookies for later use
            cookie_header = "; ".join(f"{name}={value}" for name, value, _, _ in cookies_list)
            with open(os.path.join(tempfile.gettempdir(), "pinterest_cookie_header.txt"), 'w') as f:
                f.write(cookie_header)
            print(f"\n  Cookie header saved!", flush=True)
            
            return cookies_list
        else:
            print(f"  Response: {resp.text[:300]}", flush=True)
    except Exception as e:
        print(f"  Error: {e}", flush=True)

if __name__ == "__main__":
    main()
