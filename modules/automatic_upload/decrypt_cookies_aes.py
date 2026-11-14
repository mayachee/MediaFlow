#!/usr/bin/env python3
"""
Decrypt Brave/Chrome cookies using AES-GCM (Chrome 110+ format).
The encryption key is stored in the Local State file.
"""

import os
import sys
import json
import sqlite3
import base64
import tempfile
import shutil

def kill_brave():
    import subprocess
    try:
        subprocess.run(["taskkill", "/F", "/IM", "brave.exe", "/T"], 
                      capture_output=True, timeout=15)
        import time
        time.sleep(2)
        return True
    except:
        return False

def get_chrome_encryption_key(user_data_dir):
    """Extract and decrypt the AES encryption key from Chrome/Brave Local State."""
    import win32crypt
    from Cryptodome.Cipher import AES
    from Cryptodome.Protocol.KDF import PBKDF2
    
    local_state_path = os.path.join(user_data_dir, "Local State")
    if not os.path.isfile(local_state_path):
        print(f"  Local State not found at {local_state_path}")
        return None
    
    with open(local_state_path, "r", encoding="utf-8") as f:
        local_state = json.load(f)
    
    encrypted_key_b64 = local_state.get("os_crypt", {}).get("encrypted_key")
    if not encrypted_key_b64:
        print("  No encrypted_key found in Local State")
        return None
    
    # Decode base64 and strip the "DPAPI" prefix
    encrypted_key = base64.b64decode(encrypted_key_b64)
    if encrypted_key[:5] == b"DPAPI":
        encrypted_key = encrypted_key[5:]
    
    # Decrypt using DPAPI
    try:
        _, key = win32crypt.CryptUnprotectData(encrypted_key)
        return key
    except Exception as e:
        print(f"  DPAPI decryption failed: {e}")
        return None

def decrypt_cookie_value(encrypted_value, key):
    """Decrypt a cookie value using AES-GCM (Chrome 110+ format)."""
    from Cryptodome.Cipher import AES
    
    if not encrypted_value:
        return None
    
    # Check for v10/v11 prefix (AES-GCM format)
    if encrypted_value[:3] == b"v10" or encrypted_value[:3] == b"v11":
        # Remove the 3-byte version prefix
        iv = encrypted_value[3:15]  # 12 bytes (actually 3+12=15, but v10 is 3 bytes, then 12 bytes nonce)
        # Actually the format is: 3-byte version + 12-byte nonce + ciphertext + 16-byte tag
        # But Chrome uses: v10 + 12-byte nonce + ciphertext + 16-byte tag
        nonce = encrypted_value[3:15]
        ciphertext = encrypted_value[15:-16]
        tag = encrypted_value[-16:]
        
        try:
            cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
            decrypted = cipher.decrypt_and_verify(ciphertext, tag)
            return decrypted.decode("utf-8", errors="replace")
        except Exception as e:
            print(f"  AES-GCM decryption failed: {e}")
            return None
    
    # Try DPAPI for older format
    import win32crypt
    try:
        _, decrypted = win32crypt.CryptUnprotectData(encrypted_value)
        return decrypted.decode("utf-8", errors="replace")
    except:
        return None

def main():
    print("=" * 60, flush=True)
    print("Brave Cookie Decryption (AES-GCM)", flush=True)
    print("=" * 60, flush=True)
    
    # Kill Brave first
    print("\n[1] Stopping Brave processes...", flush=True)
    kill_brave()
    
    brave_user_data = os.path.join(
        os.environ.get("LOCALAPPDATA", r"C:\Users\Dima D'origine\AppData\Local"),
        "BraveSoftware", "Brave-Browser", "User Data"
    )
    
    # Step 1: Get the encryption key
    print("\n[2] Extracting encryption key from Local State...", flush=True)
    key = get_chrome_encryption_key(brave_user_data)
    if not key:
        print("  ERROR: Could not get encryption key", flush=True)
        return
    
    print(f"  Key extracted: {len(key)} bytes", flush=True)
    
    # Step 2: Copy and read cookies database
    print("\n[3] Reading cookies database...", flush=True)
    cookie_db = os.path.join(brave_user_data, "Default", "Network", "Cookies")
    
    # Copy to temp
    tmp_db = os.path.join(tempfile.gettempdir(), "brave_cookies_aes_copy")
    try:
        shutil.copy2(cookie_db, tmp_db)
    except:
        # Try copying with Windows copy command
        import subprocess
        subprocess.run(f'copy "{cookie_db}" "{tmp_db}"', shell=True, capture_output=True)
    
    if not os.path.isfile(tmp_db):
        print(f"  ERROR: Could not copy cookie DB", flush=True)
        return
    
    conn = sqlite3.connect(tmp_db)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Step 3: Decrypt Pinterest cookies
    print("\n[4] Decrypting Pinterest cookies...", flush=True)
    cursor.execute("""
        SELECT host_key, name, value, encrypted_value, path
        FROM cookies
        WHERE host_key LIKE '%pinterest%'
    """)
    rows = cursor.fetchall()
    print(f"  Found {len(rows)} Pinterest cookie entries", flush=True)
    
    cookies_list = []
    for r in rows:
        host = r["host_key"]
        name = r["name"]
        value = r["value"]
        encrypted = r["encrypted_value"]
        path = r["path"]
        
        if value and len(value) > 0:
            cookie_val = value
            print(f"    PLAINTEXT: {name} = {value[:30]}...", flush=True)
        elif encrypted and len(encrypted) > 0:
            cookie_val = decrypt_cookie_value(encrypted, key)
            if cookie_val:
                masked = cookie_val[:30] + "..." if len(cookie_val) > 30 else cookie_val
                print(f"    DECRYPTED: {name} = {masked} (host: {host})", flush=True)
            else:
                print(f"    FAILED: {name} (host: {host})", flush=True)
                continue
        else:
            continue
        
        if cookie_val:
            cookies_list.append((name, cookie_val, host, path))
    
    conn.close()
    
    if not cookies_list:
        print("\n  ERROR: No Pinterest cookies could be decrypted", flush=True)
        return
    
    # Check for session cookie
    sess_cookie = None
    for name, value, host, path in cookies_list:
        if name == '_pinterest_sess':
            sess_cookie = (name, value, host, path)
            break
    
    if sess_cookie:
        print(f"\n  ✓ _pinterest_sess found - user appears logged in!", flush=True)
    else:
        print(f"\n  ⚠ No _pinterest_sess found", flush=True)
    
    # Save cookies
    cookie_header = "; ".join(f"{name}={value}" for name, value, _, _ in cookies_list)
    header_path = os.path.join(tempfile.gettempdir(), "pinterest_cookie_header.txt")
    with open(header_path, 'w') as f:
        f.write(cookie_header)
    print(f"\n  Cookie header saved to: {header_path}", flush=True)
    
    # Test API
    print("\n[5] Testing Pinterest API v5...", flush=True)
    import requests
    
    s = requests.Session()
    s.cookies = requests.cookies.RequestsCookieJar()
    for name, value, host, path in cookies_list:
        domain = host.lstrip(".")
        s.cookies.set(name, value, domain=domain, path=path or "/")
    
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.pinterest.com/",
    })
    
    resp = s.get("https://api.pinterest.com/v5/boards", timeout=15)
    print(f"  GET /v5/boards -> {resp.status_code}", flush=True)
    if resp.status_code == 200:
        data = resp.json()
        items = data.get("items", [])
        print(f"  Found {len(items)} boards:", flush=True)
        for b in items:
            print(f"    ID={b.get('id')}, Name={b.get('name')}", flush=True)
    else:
        print(f"  Error: {resp.text[:300]}", flush=True)

if __name__ == "__main__":
    main()
