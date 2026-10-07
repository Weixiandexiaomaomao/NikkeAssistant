"""使用白名单打包便携软件，不携带用户的截图、日志和设置。"""
import hashlib
import json
from importlib.metadata import distribution
from pathlib import Path
import shutil
import sys
import zipfile

ROOT = Path(__file__).resolve().parent
from portable import VERSION


def main():
    name = f'NikkeAssistant-{VERSION}-win-x64'
    target = ROOT / 'release' / name
    if target.exists():
        raise RuntimeError('发行目录已存在，请指定新的版本目录，避免混入旧配置')
    shutil.copytree(ROOT / 'dist' / 'NikkeAssistant', target)
    (target / 'resource' / 'pipeline').mkdir(parents=True)
    (target / 'resource' / 'pipeline' / 'empty.json').write_text('{}', encoding='utf-8')
    shutil.copytree(ROOT / 'resource' / 'image' / 'cn', target / 'resource' / 'image' / 'cn')
    shutil.copytree(ROOT / 'resource' / 'model', target / 'resource' / 'model')
    (target / 'pipelines').mkdir()
    for filename in ('mailbox.json', 'friends.json', 'defense.json'):
        shutil.copy2(ROOT / 'pipelines' / filename, target / 'pipelines' / filename)
    tasks = [task for task in json.loads((ROOT / 'tasks.json').read_text(encoding='utf-8'))
             if task.get('id', '').startswith(('cn_', 'event_'))]
    (target / 'tasks.json').write_text(json.dumps(tasks, ensure_ascii=False, indent=2), encoding='utf-8')
    shutil.copy2(ROOT / 'PORTABLE_README.txt', target / '使用说明.txt')
    shutil.copy2(ROOT / 'VALIDATION.md', target / '验证说明.md')
    source = target / 'source'
    source.mkdir()
    for filename in ('app.py', 'modern_ui.py', 'engine.py', 'daily.py', 'event_flow.py', 'portable.py', 'requirements.txt',
                     'package_release.py', 'PORTABLE_README.txt', 'BUILD.md', 'VALIDATION.md', 'Apache-2.0.txt'):
        shutil.copy2(ROOT / filename, source / filename)
    licenses = target / 'licenses'
    licenses.mkdir()
    shutil.copy2(ROOT / 'Apache-2.0.txt', licenses / 'Apache-2.0.txt')
    for package in ('maafw', 'numpy', 'Pillow', 'customtkinter', 'darkdetect'):
        dist = distribution(package)
        for file in dist.files or []:
            if 'license' in str(file).lower() or 'copying' in str(file).lower():
                location = dist.locate_file(file)
                if location.is_file():
                    destination = licenses / package / str(file).replace('..', '_')
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(location, destination)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.exists():
        shutil.copy2(python_license, licenses / 'Python-LICENSE.txt')
    gpl = ROOT.parent / 'references' / 'NKAS-mirror' / 'LICENSE'
    if gpl.exists():
        shutil.copy2(gpl, licenses / 'GNU-GPL-3.0.txt')
    notices = '''Third-party components used by NikkeAssistant

MaaFramework 5.14.2 (LGPL-3.0): https://github.com/MaaXYZ/MaaFramework
Source for this version: https://github.com/MaaXYZ/MaaFramework/releases/tag/v5.14.2
MaaFramework runtime DLLs are external in _internal/maa/bin.
Python 3.10: https://www.python.org/
NumPy 2.2.6: https://github.com/numpy/numpy/tree/v2.2.6
Pillow 12.3.0: https://github.com/python-pillow/Pillow
CustomTkinter 5.2.2 (MIT): https://github.com/TomSchimansky/CustomTkinter
Darkdetect 0.8.0 (BSD): https://github.com/albertosottile/darkdetect
Tcl/Tk runtime: https://www.tcl.tk/
PyInstaller bootloader: https://github.com/pyinstaller/pyinstaller (GPL with bootloader exception).
Native dependencies bundled by MaaFramework include OpenCV, ONNX Runtime,
FastDeploy/PPOCR, DirectML, and ViGEmClient. See MaaFramework upstream
source and dependency build scripts for notices and source references.

The application source and build instructions are in source/.
MaaAgentBinary, game accounts, login information, logs and screenshots
are not included in this archive.
'''
    (licenses / 'THIRD_PARTY_NOTICES.txt').write_text(notices, encoding='utf-8')
    (licenses / 'OCR_MODELS.txt').write_text('PP-OCRv4 detection and Chinese recognition models (Apache-2.0).\nSource: https://github.com/PaddlePaddle/PaddleOCR\nModel distribution: rapidocr_onnxruntime 1.4.4, https://github.com/RapidAI/RapidOCR\nModels and character dictionary are stored in resource/model/ocr.\n', encoding='utf-8')
    # Tcl/Tk 的版权文件若已随 PyInstaller 收集，一并保留在发行目录。
    archive = target.parent / (name + '.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as output:
        for file in sorted(target.rglob('*')):
            if file.is_file():
                output.write(file, name + '/' + file.relative_to(target).as_posix())
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256').write_text(digest + '  ' + archive.name + '\n', encoding='ascii')
    print(json.dumps({'zip': str(archive), 'size_mb': round(archive.stat().st_size / 1048576, 1),
                      'sha256': digest}, ensure_ascii=False))


if __name__ == '__main__':
    main()
