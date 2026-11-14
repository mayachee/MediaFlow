#!/usr/bin/env python3
"""Debug cookie encryption format."""

import os
import json
import sqlite3
import base64
import tempfile
import shutil
import win32crypt
import win32security
import win32api
import win32con
from Cryptodome.Cipher import AES

def get_key(user_data_dir):
    local_state_path = os.path.join(user_data_dir, "Local State")
    with open(local_state_path, "r", encoding="utf-8") as f:
        local_state = json.load(f)
    
    encrypted_key_b64 = local_state.get("os_crypt", {}).get("encrypted_key")
    encrypted_key = base64.b64decode(encrypted_key_b64)
    
    if encrypted_key[:5] == b"DPAPI":
        encrypted_key = encrypted_key[5:]
    
    _, key = win32crypt.CryptUnprotectData(encrypted_key)
    return key

def main():
    brave_user_data = os.path.join(
        os.environ.get("LOCALAPPDATA", r"C:\Users\Dima D'origine\AppData\Local"),
        "BraveSoftware", "Brave-Browser", "User Data"
    )
    
    # Get the key
    key = get_key(brave_user_data)
    print(f"Key length: {len(key)} bytes", flush=True)
    print(f"Key (hex): {key.hex()}", flush=True)
    
    # Copy cookies DB
    cookie_db = os.path.join(brave_user_data, "Default", "Network", "Cookies")
    tmp_db = os.path.join(tempfile.gettempdir(), "brave_cookies_debug.db")
    
    # Kill Brave first
    import subprocess
    subprocess.run(["taskkill", "/F", "/IM", "brave.exe", "/T"], capture_output=True, timeout=15)
    import time
    time.sleep(2)
    
    shutil.copy2(cookie_db, tmp_db)
    
    conn = sqlite3.connect(tmp_db)
    cursor = conn.cursor()
    
    # Get all cookie values (both plaintext and encrypted)
    cursor.execute("""
        SELECT host_key, name, value, encrypted_value, path
        FROM cookies
        WHERE host_key LIKE '%pinterest%'
        LIMIT 5
    """)
    rows = cursor.fetchall()
    
    for row in rows:
        host, name, value, encrypted_value, path = row
        print(f"\nCookie: {name} (host: {host})", flush=True)
        print(f"  Plaintext value: {value[:50] if value else '(empty)'}...", flush=True)
        print(f"  Encrypted value length: {len(encrypted_value) if encrypted_value else 0}", flush=True)
        if encrypted_value:
            print(f"  Encrypted value (hex): {encrypted_value[:50].hex()}...", flush=True)
            print(f"  Encrypted value (first bytes): {encrypted_value[:20]}", flush=True)
            
            # Check the format
            if encrypted_value[:3] == b"v10":
                print(f"  Format: v10 (AES-GCM)", flush=True)
            elif encrypted_value[:3] == b"v11":
                print(f"  Format: v11 (AES-GCM)", flush=True)
            else:
                print(f"  Format: DPAPI (first byte: {encrypted_value[0]:02x})", flush=True)
            
            # Try AES-GCM decryption (v10/v11 format)
            try:
                version = encrypted_value[:3]
                print(f"  Version prefix: {version}", flush=True)
                
                if version in (b"v10", b"v11"):
                    # v10/v11 format: 3-byte prefix + 12-byte nonce + ciphertext + 16-byte tag
                    nonce = encrypted_value[3:15]
                    ciphertext = encrypted_value[15:-16]
                    tag = encrypted_value[-16:]
                    
                    print(f"  Nonce (hex): {nonce.hex()}", flush=True)
                    print(f"  Ciphertext length: {len(ciphertext)}", flush=True)
                    print(f"  Tag (hex): {tag.hex()}", flush=True)
                    
                    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                    decrypted = cipher.decrypt_and_verify(ciphertext, tag)
                    print(f"  AES-GCM decrypted: {decrypted.decode('utf-8', errors='replace')[:50]}...", flush=True)
                else:
                    # Maybe it's still v20 format but with different structure
                    # The first 3 bytes are "v20", then 12-byte nonce, then ciphertext, then 16-byte tag
                    nonce = encrypted_value[3:15]
                    ciphertext = encrypted_value[15:-16]
                    tag = encrypted_value[-16:]
                    
                    print(f"  Trying v20 format...", flush=True)
                    print(f"  Nonce (hex): {nonce.hex()}", flush=True)
                    print(f"  Ciphertext length: {len(ciphertext)}", flush=True)
                    print(f"  Tag (hex): {tag.hex()}", flush=True)
                    
                    cipher = AES.new(key, AES.MODE_GCM, nonce=nonce)
                    decrypted = cipher.decrypt_and_verify(ciphertext, tag)
                    print(f"  AES-GCM decrypted: {decrypted.decode('utf-8', errors='replace')[:50]}...", flush=True)
            except Exception as e:
                print(f"  AES-GCM failed: {e}", flush=True)
            
            # Try DPAPI
            try:
                _, decrypted = win32crypt.CryptUnprotectData(encrypted_value)
                print(f"  DPAPI decrypted: {decrypted.decode('utf-8', errors='replace')[:50]}...", flush=True)
            except Exception as e:
                print(f"  DPAPI failed: {e}", flush=True)
    
    conn.close()

if __name__ == "__main__":
    main()
