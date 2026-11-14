import sqlite3
import tempfile
import os

tmp_db = os.path.join(tempfile.gettempdir(), 'brave_cookies_copy')
conn = sqlite3.connect(tmp_db)
cursor = conn.cursor()
cursor.execute("SELECT host_key, name, value, encrypted_value, path FROM cookies WHERE host_key LIKE '%pinterest%'")
rows = cursor.fetchall()
for r in rows:
    host, name, value, encrypted, path = r
    val_display = value[:50] if value else '(empty)'
    has_enc = bool(encrypted) if encrypted else False
    print(f"Host: {host}, Name: {name}, Value: {val_display}, HasEncrypted: {has_enc}, Path: {path}")
conn.close()
