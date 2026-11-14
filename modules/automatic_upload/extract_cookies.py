import ctypes
import os
import sqlite3
import tempfile

kernel32 = ctypes.windll.kernel32

src = r"C:\Users\Dima D'origine\AppData\Local\BraveSoftware\Brave-Browser\User Data\Default\Network\Cookies"
dst = os.path.join(tempfile.gettempdir(), "brave_cookies_copy")

GENERIC_READ = 0x80000000
FILE_SHARE_READ = 1
FILE_SHARE_WRITE = 2
OPEN_EXISTING = 3
FILE_FLAG_BACKUP_SEMANTICS = 0x02000000

print(f"Source: {src}")
print(f"Exists: {os.path.isfile(src)}")

handle = kernel32.CreateFileW(
    src,
    GENERIC_READ,
    FILE_SHARE_READ | FILE_SHARE_WRITE,
    None,
    OPEN_EXISTING,
    FILE_FLAG_BACKUP_SEMANTICS,
    None
)

if handle == -1 or handle == 0xFFFFFFFF:
    error = kernel32.GetLastError()
    print(f"CreateFile failed: error {error}")
else:
    print("File opened successfully!")
    with open(dst, 'wb') as f:
        buffer = ctypes.create_string_buffer(65536)
        total = 0
        while True:
            bytes_read = ctypes.c_ulong(0)
            result = kernel32.ReadFile(
                handle, buffer, 65536, ctypes.byref(bytes_read), None
            )
            if not result or bytes_read.value == 0:
                break
            f.write(buffer.raw[:bytes_read.value])
            total += bytes_read.value
    kernel32.CloseHandle(handle)
    print(f"Copied {total} bytes to {dst}")
    print(f"Copy exists: {os.path.exists(dst)}, size: {os.path.getsize(dst)}")

    # Query for Pinterest cookies
    conn = sqlite3.connect(dst)
    cursor = conn.cursor()
    cursor.execute("SELECT host_key, name, value, encrypted_value FROM cookies WHERE host_key LIKE '%pinterest%'")
    rows = cursor.fetchall()
    print(f"\nPinterest cookies found: {len(rows)}")
    for r in rows:
        print(f"  Host: {r[0]}, Name: {r[1]}, HasValue: {len(r[2])>0}, HasEncrypted: {len(r[3])>0}")
    conn.close()
