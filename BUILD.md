# 从开源仓库构建

直接克隆本仓库即可获得源码、`resource`、`pipelines`、`tasks.json` 和许可文件。
Windows 64 位 Python 3.10 环境中安装 `requirements.txt` 和 `pyinstaller==6.22.3`。

```powershell
python -m PyInstaller --noconfirm --onedir --windowed --name NikkeAssistant --collect-all maa --collect-all customtkinter --exclude-module cv2 --exclude-module pytest app.py
python package_release.py
```

打包脚本使用明确的文件白名单，不收集个人设置、日志、截图和虚拟环境。
MaaFramework DLL 外置于 `_internal/maa/bin`；运行时使用雷电自带的 ADB。
便携包自检可运行 `NikkeAssistant.exe --self-test C:\Temp\nikke-selftest.json`。
