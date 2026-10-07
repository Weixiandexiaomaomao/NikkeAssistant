import io
import json
import ctypes
from ctypes import wintypes
import os
from datetime import datetime
import queue
import subprocess
import threading
import tkinter as tk
import customtkinter as ctk
from modern_ui import ModernUI, BLUE
from tkinter import filedialog, messagebox, simpledialog, ttk
from pathlib import Path
from uuid import uuid4

from PIL import Image, ImageTk
from engine import Engine, ROOT, NO_WINDOW
from portable import VERSION, discover_adb, discover_device_names


class App(ModernUI, ctk.CTk):
    def __init__(self, auto_scan=True):
        ctk.set_appearance_mode('light')
        ctk.set_widget_scaling(1.0)
        ctk.set_window_scaling(1.0)
        super().__init__()
        self.title(f'妮姬国服助手 v{VERSION} · MaaFramework')
        self.geometry('1180x850')
        self.minsize(950, 720)
        style = ttk.Style(self)
        if 'vista' in style.theme_names():
            style.theme_use('vista')
        self.option_add('*Font', ('Microsoft YaHei UI', 10))
        style.configure('TButton', padding=5)
        self.events = queue.Queue()
        (ROOT / 'logs').mkdir(exist_ok=True)
        self.log_path = ROOT / 'logs' / ('gui-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '.txt')
        self.engine = Engine(lambda text: self.events.put(('log', text)))
        self.busy = False
        self.frame_image = None
        self.draft = []
        self.tasks = self.load_json(ROOT / 'tasks.json', [])
        self.tasks.sort(key=lambda task: task.get('handler') == 'missions')
        settings = self.load_json(ROOT / 'settings.json', {})
        self.adb = tk.StringVar(value=settings.get('adb', ''))
        self.serial = tk.StringVar(value=settings.get('serial', ''))
        self.device_display = tk.StringVar(value=self.serial.get())
        self.device_serials = {}
        self.action = tk.StringVar(value='click')
        self.engine.options = settings.get('options', {})
        self.build_ui(settings)
        self.bind('<F8>', lambda event: self.engine.stop())
        self.global_hotkey = bool(os.name == 'nt' and ctypes.windll.user32.RegisterHotKey(
            None, 0x4e4b, 0x4000, 0x77))
        self.protocol('WM_DELETE_WINDOW', self.close)
        self.after(100, self.pump)
        self.log('先登录国服大厅，再连接并运行选中任务。内置任务适配竖屏 9:16。')
        self.log('全局 F8 停止已启用。' if self.global_hotkey else 'F8 仅在助手窗口聚焦时有效。')
        if auto_scan:
            self.devices()

    @staticmethod
    def load_json(path, default):
        return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

    def log(self, text):
        line = datetime.now().strftime('%H:%M:%S ') + text
        with self.log_path.open('a', encoding='utf-8') as file:
            file.write(line + '\n')
        self.logs.config(state='normal')
        tag='error' if any(word in text for word in ('Error','失败','停止')) else 'success' if text.startswith('完成：') else ''
        self.logs.insert('end', line + '\n',tag)
        if text.startswith(('开始：','完成：','失败：','跳过：')):
            for index,task in enumerate(self.tasks):
                if text[3:].split('；',1)[0]==task['name']:
                    self.task_states[index]='↻' if text.startswith('开始') else '×' if text.startswith('失败') else '—' if text.startswith('跳过') else '✓'
                    if index in self.row_states: self.row_states[index].configure(text=self.task_states[index],text_color=BLUE if text.startswith('开始') else '#E15454' if text.startswith('失败') else '#20A348')
        self.logs.see('end')
        self.logs.config(state='disabled')

    def pump(self):
        if self.global_hotkey:
            msg = wintypes.MSG()
            while ctypes.windll.user32.PeekMessageW(ctypes.byref(msg), None, 0x312, 0x312, 1):
                if msg.wParam == 0x4e4b:
                    self.engine.stop()
                    self.log('F8：请求停止')
        while not self.events.empty():
            kind, data = self.events.get()
            if kind in ('log', 'error'):
                self.log(data)
            elif kind == 'done':
                self.busy = False
                self.lock_controls(False)
                self.status_text.set('已连接 · 待机' if self.engine.controller else '尚未连接')
            elif kind == 'image':
                self.frame_image = Image.open(io.BytesIO(data)).convert('RGB')
                self.draw_image()
            elif kind == 'devices':
                self.apply_devices(*data)
        self.after(100, self.pump)

    def work(self, fn):
        if self.busy:
            self.log('正在执行操作，请先停止或等待完成。')
            return
        self.busy = True
        self.lock_controls(True)
        self.status_text.set('正在执行操作…')
        def target():
            try:
                fn()
            except Exception as exc:
                self.events.put(('error', f'{type(exc).__name__}: {exc}'))
            finally:
                self.events.put(('done', None))
        threading.Thread(target=target, daemon=True).start()

    def browse(self):
        name = filedialog.askopenfilename(filetypes=[('ADB', 'adb.exe')])
        if name:
            self.adb.set(name)

    def select_device(self, label):
        self.serial.set(self.device_serials.get(label, ''))

    def apply_devices(self, adb, devices, suggested, names):
        self.adb.set(adb)
        labels = {serial: f'{names.get(serial, "Android 设备")}（{serial}）'
                  for serial in devices}
        self.device_serials = {label: serial for serial, label in labels.items()}
        self.device_box.configure(values=list(self.device_serials))
        if self.serial.get() not in devices:
            self.serial.set(suggested)
        self.device_display.set(labels.get(self.serial.get(), ''))

    def devices(self):
        adb = self.adb.get()
        def scan():
            found = discover_adb(adb)
            if not found:
                raise RuntimeError('未找到雷电 ADB。请先启动雷电，或点「浏览」选择雷电安装目录中的 adb.exe。')
            result = subprocess.run([found, 'devices'], capture_output=True, timeout=15,
                                    creationflags=NO_WINDOW, check=True)
            devices = [line.split()[0] for line in result.stdout.decode().splitlines()
                       if '\tdevice' in line]
            installed = []
            for serial in devices:
                check = subprocess.run([found, '-s', serial, 'shell', 'pm', 'path', 'com.tencent.nikke'],
                                       capture_output=True, timeout=5, creationflags=NO_WINDOW)
                if check.returncode == 0 and b'package:' in check.stdout:
                    installed.append(serial)
            suggested = installed[0] if len(installed) == 1 else devices[0] if len(devices) == 1 else ''
            names = discover_device_names(found, devices)
            self.events.put(('devices', (found, devices, suggested, names)))
            labels = [f'{names.get(serial, "Android 设备")}（{serial}）' for serial in devices]
            self.events.put(('log', f'发现设备：{", ".join(labels) or "无"}'))
        self.work(scan)

    def connect(self):
        adb, serial = self.adb.get(), self.serial.get()
        if not adb or not serial:
            self.log('请先查找设备并选择一个模拟器实例。')
            return
        def fn():
            self.engine.connect(adb, serial)
            (ROOT / 'settings.json').write_text(json.dumps({**self.load_json(ROOT / 'settings.json', {}), 'adb': adb, 'serial': serial}), encoding='utf-8')
            self.events.put(('image', self.engine.screenshot()))
        self.work(fn)

    def capture(self):
        self.work(lambda: self.events.put(('image', self.engine.screenshot())))

    def draw_image(self):
        if self.frame_image is None:
            if self.canvas.winfo_width() > 10:
                self.canvas.delete('all')
                self.canvas.create_text(self.canvas.winfo_width()/2,self.canvas.winfo_height()/2,
                    text='连接模拟器后显示画面',fill='#9299A8',font=('Microsoft YaHei UI',11))
            return
        targets=[('main',self.canvas)]
        if getattr(self,'recorder',None) and self.recorder.winfo_exists():
            targets.append(('recorder',self.recorder_canvas))
        for name,canvas in targets:
            w,h=self.frame_image.size
            self.scale=min(max(1,canvas.winfo_width())/w,max(1,canvas.winfo_height())/h)
            dw,dh=max(1,round(w*self.scale)),max(1,round(h*self.scale))
            self.offset=((canvas.winfo_width()-dw)//2,(canvas.winfo_height()-dh)//2)
            photo=ImageTk.PhotoImage(self.frame_image.resize((dw,dh),Image.Resampling.LANCZOS))
            setattr(self,'photo_'+name,photo)
            canvas.delete('all'); canvas.create_image(*self.offset,anchor='nw',image=photo)

    def begin_crop(self, event):
        if self.frame_image is None or self.busy:
            return
        self.start = (event.x, event.y)
        self.crop_canvas = event.widget
        self.rect = self.crop_canvas.create_rectangle(event.x, event.y, event.x, event.y, outline='#42dfad', width=2)

    def move_crop(self, event):
        if hasattr(self, 'rect') and hasattr(self, 'start'):
            self.crop_canvas.coords(self.rect, *self.start, event.x, event.y)

    def end_crop(self, event):
        if not hasattr(self, 'start'):
            return
        start = self.start
        del self.start
        w, h = self.frame_image.size
        ox, oy = self.offset
        x1, x2 = sorted([max(0, min(w, round((v - ox) / self.scale))) for v in (start[0], event.x)])
        y1, y2 = sorted([max(0, min(h, round((v - oy) / self.scale))) for v in (start[1], event.y)])
        if x2 - x1 < 12 or y2 - y1 < 12:
            return
        if self.draft and self.draft[0]['size'] != [w, h]:
            messagebox.showerror('方向变化', '同一任务的截图方向和尺寸必须一致。')
            return
        name = simpledialog.askstring('步骤名称', '这个按钮或完成画面叫什么？', parent=self)
        if not name:
            return
        # MaaFramework 将截图短边标准化到 720；模板和 ROI 必须使用同一尺度。
        factor = 720 / min(w, h)
        normalized = self.frame_image.resize((round(w * factor), round(h * factor)), Image.Resampling.LANCZOS)
        a, b, c, d = [round(v * factor) for v in (x1, y1, x2, y2)]
        filename = uuid4().hex + '.png'
        folder = ROOT / 'resource' / 'image'
        folder.mkdir(parents=True, exist_ok=True)
        normalized.crop((a, b, c, d)).save(folder / filename)
        rw, rh = normalized.size
        rx, ry = max(0, a - 20), max(0, b - 20)
        step = {'name': name, 'template': filename, 'action': self.action.get(),
                'roi': [rx, ry, min(rw, c + 20) - rx, min(rh, d + 20) - ry],
                'threshold': 0.9, 'size': [w, h]}
        self.draft.append(step)
        self.refresh_steps()
        self.log(f'记录：{name}。请手动进入下一画面，再刷新截图。')

    def refresh_steps(self):
        self.step_list.delete(0, 'end')
        for step in self.draft:
            self.step_list.insert('end', f"{'点击' if step['action'] == 'click' else '检查'} · {step['name']}")

    def undo(self):
        if self.draft:
            self.draft.pop()
            self.refresh_steps()

    def clear_draft(self):
        self.draft.clear()
        self.refresh_steps()

    def save_task(self):
        if not self.draft or self.draft[-1]['action'] != 'check':
            messagebox.showinfo('缺少完成检查', '请在任务末尾记录一个「仅检查画面」步骤。')
            return
        name = simpledialog.askstring('任务名称', '例如：邮箱领取、前哨基地收菜', parent=self)
        if not name:
            return
        self.tasks.append({'id': 'custom_' + uuid4().hex, 'name': name, 'steps': list(self.draft)})
        (ROOT / 'tasks.json').write_text(json.dumps(self.tasks, ensure_ascii=False, indent=2), encoding='utf-8')
        self.clear_draft()
        self.refresh_tasks()
        self.log(f'已保存：{name}')

    def refresh_tasks(self):
        self.render_tasks()

    def show_task_info(self,event=None):
        self.focus_task(self.focused_task)

    def task_settings(self):
        self.connection_settings()

    def run(self):
        selected = [self.tasks[i] for i in self.task_list.curselection()]
        self.run_tasks(selected)

    def run_task(self, index):
        self.run_tasks([self.tasks[index]])

    def run_tasks(self, selected):
        if not selected:
            self.log('请勾选需要执行的任务。')
            return
        adb, serial = self.adb.get(), self.serial.get()
        if not serial:
            self.log('请选择需要运行任务的模拟器实例。')
            return
        self.save_preferences()
        def fn():
            found = discover_adb(adb)
            if not found:
                raise RuntimeError('未找到 ADB，请启动雷电或在连接设置中选择 adb.exe。')
            # Always establish the selected connection before starting, including after
            # emulator restarts or switching instances. Failure must not run any task.
            self.events.put(('log', '正在自动连接模拟器…'))
            self.engine.connect(found, serial)
            screenshot = self.engine.screenshot()
            with Image.open(io.BytesIO(screenshot)) as frame:
                if any(step['size'] != list(frame.size)
                       for task in selected for step in task.get('steps', [])):
                    raise RuntimeError('任务采集尺寸与当前截图不一致，请恢复原尺寸和方向。')
            self.events.put(('image', screenshot))
            self.engine.run(selected)
            self.events.put(('image', self.engine.screenshot()))
        self.work(fn)

    def close(self):
        self.engine.stop()
        if self.global_hotkey:
            ctypes.windll.user32.UnregisterHotKey(None, 0x4e4b)
        self.destroy()


def main():
    import sys
    os.chdir(ROOT)
    if '--run-selected' in sys.argv:
        report_path=Path(sys.argv[sys.argv.index('--run-selected')+1])
        settings=json.loads((ROOT/'settings.json').read_text(encoding='utf-8'))
        selected_ids=set(settings.get('selected',[]))
        selected=[t for t in json.loads((ROOT/'tasks.json').read_text(encoding='utf-8'))
                  if t['id'] in selected_ids]
        log_dir=ROOT/'logs';log_dir.mkdir(exist_ok=True)
        log_path=log_dir/('cli-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.txt')
        messages=[]
        def log(message):
            messages.append(message)
            with log_path.open('a',encoding='utf-8') as file:
                file.write(datetime.now().strftime('%H:%M:%S ')+message+'\n')
        engine=Engine(log); engine.options=settings.get('options',{})
        try:
            if not selected:
                raise RuntimeError('没有选中任务')
            engine.connect(settings['adb'],settings['serial'])
            engine.run(selected)
        except Exception as exc:
            log('RuntimeError: '+str(exc))
        failures=[m for m in messages if m.startswith(('失败：','RuntimeError:')) or '未完成步骤' in m]
        report={'version':VERSION,'selected':[t['id'] for t in selected],
                'passed':bool(messages and messages[-1]=='所有选中任务完成' and not failures),
                'failures':failures,'log':str(log_path)}
        if engine.controller:
            captures=ROOT/'captures';captures.mkdir(exist_ok=True)
            screenshot=captures/('queue-'+datetime.now().strftime('%Y%m%d-%H%M%S')+'.png')
            screenshot.write_bytes(engine.screenshot());report['screenshot']=str(screenshot)
        report_path.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
        return
    if '--self-test' in sys.argv:
        # 打包后的只读检查，可在没有 Python 的 PATH 中运行。
        from maa.library import Library
        report_path = Path(sys.argv[sys.argv.index('--self-test') + 1])
        result = {'version': VERSION, 'root': str(ROOT), 'frozen': bool(getattr(sys, 'frozen', False))}
        try:
            app = App(auto_scan=False)
            app.update()
            result['tasks'] = app.task_list.size()
            result['gui'] = 'passed'
            Library.framework()
            result['maa_dll'] = 'loaded'
            if '--probe-adb' in sys.argv:
                adb = discover_adb()
                serial = sys.argv[sys.argv.index('--probe-adb') + 1]
                names = discover_device_names(adb, [serial])
                app.apply_devices(adb, [serial], serial, names)
                result['device_display'] = app.device_display.get()
                if app.serial.get() != serial:
                    raise RuntimeError('设备显示名称影响了连接地址')
                app.engine.connect(adb, serial)
                app.engine.screenshot()
                from maa.resource import Resource
                resource = Resource()
                result['resources'] = resource.post_bundle(ROOT / 'resource').wait().succeeded
                result['adb_screenshot'] = 'passed'
                from daily import Daily
                vision = Daily(app.engine)
                result['ocr_text_count'] = len(vision.scan())
                if result['ocr_text_count'] == 0:
                    raise RuntimeError('OCR 未能读取当前设备画面')
            app.close()
            result['passed'] = True
        except Exception as exc:
            result.update({'passed': False, 'error': repr(exc)})
        report_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
        return
    try:
        App().mainloop()
    except Exception as exc:
        messagebox.showerror('启动失败', f'{type(exc).__name__}: {exc}\n请完整解压压缩包，并放在可写入的目录。')


if __name__ == '__main__':
    main()
