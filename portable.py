"""便携版路径与雷电自动检测。"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else Path(__file__).resolve().parent
VERSION = '0.3.37'


def decode_console(data):
    for encoding in ('utf-8-sig', 'gb18030'):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode('utf-8', errors='replace')


def discover_device_names(adb, serials):
    """Read LDPlayer instance titles and confirm each instance's ADB serial."""
    console = Path(adb).parent / 'ldconsole.exe'
    names = {}
    if not console.is_file():
        return names
    flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
    try:
        result = subprocess.run([str(console), 'list2'], capture_output=True,
                                timeout=8, creationflags=flags, check=True)
        for line in decode_console(result.stdout).splitlines():
            # The title may itself contain commas; list2 has eight numeric tail fields.
            head, *tail = line.rsplit(',', 8)
            index, separator, title = head.partition(',')
            if len(tail) != 8 or not separator or not index.isdigit() or tail[2] != '1':
                continue
            try:
                probe = subprocess.run([str(console), 'adb', '--index', index,
                                        '--command', 'get-serialno'], capture_output=True,
                                       timeout=5, creationflags=flags, check=True)
                serial = decode_console(probe.stdout).strip()
                if serial in serials and title.strip():
                    names[serial] = title.strip()
            except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
                continue
    except (OSError, subprocess.TimeoutExpired, subprocess.CalledProcessError):
        pass
    return names


def discover_adb(preferred=''):
    if preferred and Path(preferred).is_file():
        return preferred
    # 已运行实例的安装位置优先，支持安装到任意盘符。
    command = "Get-CimInstance Win32_Process -Filter \"Name='dnplayer.exe'\" | Select-Object -ExpandProperty ExecutablePath | ConvertTo-Json -Compress"
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', command],
                                capture_output=True, timeout=12,
                                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        value = json.loads(result.stdout.decode('utf-8', errors='replace').lstrip('\ufeff') or '[]')
        paths = [value] if isinstance(value, str) else value or []
        for path in paths:
            if path:
                adb = Path(path).parent / 'adb.exe'
                if adb.is_file():
                    return str(adb)
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    try:
        import winreg
        for hive in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
            for base in (r'SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall',
                         r'SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall'):
                try:
                    with winreg.OpenKey(hive, base) as key:
                        for index in range(winreg.QueryInfoKey(key)[0]):
                            with winreg.OpenKey(key, winreg.EnumKey(key, index)) as item:
                                try:
                                    name = winreg.QueryValueEx(item, 'DisplayName')[0]
                                    if not any(word in name.lower() for word in ('雷电', 'ldplayer')):
                                        continue
                                    location = winreg.QueryValueEx(item, 'InstallLocation')[0]
                                    adb = Path(location) / 'adb.exe'
                                    if adb.is_file():
                                        return str(adb)
                                except OSError:
                                    continue
                except OSError:
                    continue
    except ImportError:
        pass
    return shutil.which('adb') or ''
