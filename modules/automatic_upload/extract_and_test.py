#!/usr/bin/env python3
"""Extract Pinterest cookies from Brave using SeBackupPrivilege."""

import os
import sys
import sqlite3
import tempfile
import win32security
import win32api
import win32con
import win32file
import win32crypt
import requests

# --- 1. Enable SeBackupPrivilege ---
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
    if err == 0:
        print("SeBackupPrivilege enabled successfully!")
    else:
        print(f"SeBackupPrivilege enable returned error: {err}")
    token.Close()
except Exception as e:
    print(f"Could not enable SeBackupPrivilege: {e}")

# --- 2. Find and copy Brave cookies database ---
BRAVE_COOKIE_DB = os.path.join(
    os.environ.get("LOCALAPPDATA", ""),
    "BraveSoftware", "Brave-Browser", "User Data", "Default", "Network", "Cookies",
)
if not os.path.isfile(BRAVE_COOKIE_DB):
    BRAVE_COOKIE_DB = os.path.join(
        os.path.expanduser("~"), "AppData", "Local", "BraveSoftware",
        "Brave-Browser", "User Data", "Default", "Network", "Cookies",
    )

print(f"\nBrave cookie DB: {BRAVE_COOKIE_DB}")
print(f"Exists: {os.path.isfile(BRAVE_COOKIE_DB)}")

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000

tmp_db = os.path.join(tempfile.gettempdir(), "brave_cookies_copy")
tmp_wal = os.path.join(tempfile.gettempdir(), "brave_cookies_copy-wal")
tmp_shm = os.path.join(tempfile.gettempdir(), "brave_cookies_copy-shm")

def copy_locked_file(src, dst):
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

for suffix, dst in [("", tmp_db), ("-wal", tmp_wal), ("-shm", tmp_shm)]:
    src = BRAVE_COOKIE_DB + suffix
    if os.path.isfile(src):
        print(f"  Copying {os.path.basename(src)}...", flush=True)
        if copy_locked_file(src, dst):
            print(f"  OK: {os.path.basename(dst)} ({os.path.getsize(dst)} bytes)")
        else:
            print(f"  FAILED: {os.path.basename(src)}")

if not os.path.isfile(tmp_db):
    print("\nERROR: Could not copy cookies database.")
    sys.exit(1)

# --- 3. Query for Pinterest cookies ---
conn = sqlite3.connect(tmp_db)
conn.row_factory = sqlite3.Row
cursor = conn.cursor()

cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
print(f"\nSQLite tables: {tables}")

cursor.execute("""
    SELECT host_key, name, value, encrypted_value, path
    FROM cookies
    WHERE host_key LIKE '%pinterest%'
""")
rows = cursor.fetchall()
print(f"\nPinterest cookies found: {len(rows)}")

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
        try:
            decrypted = win32crypt.CryptUnprotectData(encrypted)
            cookie_val = decrypted[1].decode("utf-8", errors="replace")
        except Exception as e:
            print(f"  [FAIL] Decrypt {name}: {e}")
            cookie_val = None
    else:
        cookie_val = None

    if cookie_val:
        cookies_list.append((name, cookie_val, host, path))
        val_display = cookie_val[:40] + "..." if len(cookie_val) > 40 else cookie_val
        print(f"  OK: {name} = {val_display}")

conn.close()

# --- 4. Build session and test API ---
if not cookies_list:
    print("\nNo Pinterest cookies found.")
    sys.exit(1)

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

# Try v5 API - list boards
print("\n--- Testing Pinterest API v5 ---")
try:
    resp = s.get("https://api.pinterest.com/v5/boards", timeout=15)
    print(f"GET /v5/boards -> {resp.status_code}")
    if resp.status_code == 200:
        boards = resp.json()
        items = boards.get("items", [])
        print(f"  Boards: {len(items)}")
        for b in items[:10]:
            print(f"    ID={b.get('id')}, Name={b.get('name')}")
    else:
        print(f"  Response: {resp.text[:300]}")
except Exception as e:
    print(f"  Error: {e}")

# Try media upload (first step of pin creation)
print("\n--- Testing media upload registration ---")
try:
    resp = s.post(
        "https://api.pinterest.com/v5/media/upload",
        headers={"Content-Type": "application/json"},
        json={"media_type": "image"},
        timeout=15,
    )
    print(f"POST /v5/media/upload -> {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"  media_id: {str(data.get('media_id', 'N/A'))[:30]}")
        print(f"  upload_url present: {bool(data.get('upload_url'))}")
    else:
        print(f"  Response: {resp.text[:300]}")
except Exception as e:
    print(f"  Error: {e}")
