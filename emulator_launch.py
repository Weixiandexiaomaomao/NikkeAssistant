"""Start the selected emulator and wait for Android, without changing instances."""
import ctypes
import json
from pathlib import Path
import subprocess
import time
from portable import discover_adb, decode_console

FLAGS=getattr(subprocess,'CREATE_NO_WINDOW',0)

def normalize_emulator(value,serial='',adb=''):
    value=value if isinstance(value,dict) else {}
    index=value.get('index','')
    if index=='':
        if serial.startswith('emulator-') and serial[9:].isdigit():
            port=int(serial[9:])
            if port>=5554 and (port-5554)%2==0:index=str((port-5554)//2)
    return {'path':str(value.get('path','')), 'arguments':str(value.get('arguments','')),
            'index':str(index), 'auto_start':bool(value.get('auto_start',True)),
            'auto_game':bool(value.get('auto_game',True))}

def discover_emulator(adb='',preferred=''):
    if preferred:
        return preferred if Path(preferred).is_file() else ''
    found=discover_adb(adb)
    if found:
        exe=Path(found).parent/'dnplayer.exe'
        if exe.is_file():return str(exe)
    return ''

def arguments(text):
    if not text.strip():return []
    from ctypes import wintypes
    shell=ctypes.WinDLL('shell32',use_last_error=True)
    shell.CommandLineToArgvW.argtypes=[wintypes.LPCWSTR,ctypes.POINTER(ctypes.c_int)]
    shell.CommandLineToArgvW.restype=ctypes.POINTER(wintypes.LPWSTR)
    count=ctypes.c_int();pointer=shell.CommandLineToArgvW('launcher '+text,ctypes.byref(count))
    if not pointer:raise ValueError('模拟器启动参数无效')
    try:return [pointer[i] for i in range(1,count.value)]
    finally:
        kernel=ctypes.WinDLL('kernel32');kernel.LocalFree.argtypes=[ctypes.c_void_p]
        kernel.LocalFree(ctypes.cast(pointer,ctypes.c_void_p))

def command(adb,serial,config):
    exe=discover_emulator(adb,config['path'])
    if not exe:raise RuntimeError('未找到模拟器程序，请在「设置 → 连接设置」选择模拟器 exe 路径。')
    console=Path(exe).parent/'ldconsole.exe'
    if Path(exe).name.lower() in ('dnplayer.exe','ldconsole.exe') and not config['arguments']:
        index=config['index']
        if not index.isdigit():raise ValueError('请在连接设置中填写雷电实例编号，避免启动错误实例。')
        if serial!=f'emulator-{5554+2*int(index)}':
            raise ValueError('雷电实例编号与设备地址不一致，请修改连接设置中的实例编号或设备地址。')
        if not console.is_file():raise RuntimeError('模拟器目录中缺少 ldconsole.exe')
        result=subprocess.run([str(console),'list2'],capture_output=True,timeout=10,creationflags=FLAGS,check=True)
        if not any(line.partition(',')[0]==index for line in decode_console(result.stdout).splitlines()):
            raise ValueError('未找到所配置的雷电实例编号：'+index)
        return [str(console),'launch','--index',index]
    return [exe,*arguments(config['arguments'])]

def ready(adb,serial):
    try:
        result=subprocess.run([adb,'-s',serial,'shell','getprop','sys.boot_completed'],capture_output=True,timeout=5,creationflags=FLAGS)
        return result.returncode==0 and result.stdout.strip()==b'1'
    except (OSError,subprocess.TimeoutExpired):return False

def ensure_emulator(adb,serial,config,log,stop,timeout=180):
    found=discover_adb(adb)
    if not found:
        exe=discover_emulator(adb,config['path'])
        candidate=Path(exe).parent/'adb.exe' if exe else None
        if candidate and candidate.is_file():found=str(candidate)
    if not found:raise RuntimeError('未找到 ADB，请在连接设置配置模拟器程序路径或 adb.exe。')
    if not serial:raise ValueError('请在连接设置填写设备地址，例如 emulator-5558。')
    if ready(found,serial):
        log('模拟器已就绪：'+serial);return found
    if not config['auto_start']:raise RuntimeError('模拟器未就绪，请启用连接设置中的自动启动模拟器。')
    launch=command(found,serial,config)
    if stop.is_set():raise InterruptedError('用户停止')
    log('正在启动模拟器：'+serial)
    subprocess.Popen(launch,cwd=str(Path(launch[0]).parent),creationflags=FLAGS,
                     stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        if stop.wait(2):raise InterruptedError('用户停止')
        if ready(found,serial):
            log('模拟器启动完成，Android 已就绪');return found
    raise RuntimeError('等待模拟器启动超时，请检查模拟器路径、实例编号和设备地址。')

def startup_tasks(tasks,config):
    if config['auto_game'] and any(t.get('package')=='com.tencent.nikke' for t in tasks) and not any(t.get('handler')=='start_game' for t in tasks):
        return [{'id':'auto_start_game','name':'自动启动游戏','handler':'start_game','package':'com.tencent.nikke'},*tasks]
    return tasks
