import subprocess
import sys
import os

# Use PowerShell to copy the locked Cookies file using backup mode
src = r"C:\Users\Dima D'origine\AppData\Local\BraveSoftware\Brave-Browser\User Data\Default\Network\Cookies"
dst = os.path.join(os.environ['TEMP'], "brave_cookies_copy")

ps_script = f'''
$src = "{src}"
$dst = "{dst}"
try {{
    # Try CreateFile with backup mode
    $bytes = [System.IO.File]::Open($src, 'Open', 'Read', 'Read')
    $fs = [System.IO.File]::OpenWrite($dst)
    $buffer = New-Object byte[] 8192
    while ($true) {{
        $read = $bytes.Read($buffer, 0, $buffer.Length)
        if ($read -eq 0) {{ break }}
        $fs.Write($buffer, 0, $read)
    }}
    $fs.Close()
    $bytes.Close()
    Write-Output "Copy succeeded"
}} catch {{
    Write-Output "Error: $_"
}}
'''

result = subprocess.run(['powershell', '-Command', ps_script], capture_output=True, text=True)
print(result.stdout)
print(result.stderr)
print(f"Copy succeeded: {os.path.exists(dst)}")
