"""国服任务资源与 MaaFramework 执行器。"""
import json
import subprocess
import threading
import time
from portable import ROOT

from maa.controller import AdbController
from maa.context import ContextEventSink
from maa.event_sink import NotificationType
from maa.resource import Resource
from maa.tasker import Tasker
from maa.toolkit import Toolkit
from maa.define import MaaAdbInputMethodEnum, MaaAdbScreencapMethodEnum

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)


def adb_run(adb, serial, *args):
    result = subprocess.run([str(adb), '-s', serial, *args], capture_output=True,
                            timeout=20, creationflags=NO_WINDOW)
    if result.returncode:
        raise RuntimeError(result.stderr.decode('utf-8', errors='replace').strip())
    return result.stdout


def compile_steps(steps, dry_run=False):
    """每次点击前识别；末尾必须存在独立的完成画面检查。"""
    if not steps or steps[-1]['action'] != 'check':
        raise ValueError('任务末尾必须添加完成画面的「检查」步骤')
    # Maa 的任务入口直接执行动作；入口必须先转入识别节点。
    pipeline = {'Entry': {'next': ['Step0'], 'timeout': 20000}}
    for i, step in enumerate(steps):
        if step['action'] not in ('click', 'check'):
            raise ValueError('不支持的动作')
        if not 0.5 <= float(step['threshold']) <= 1:
            raise ValueError('识别阈值超出范围')
        if len(step['roi']) != 4 or any(v < 0 for v in step['roi']):
            raise ValueError('无效识别区域')
        node = {
            'recognition': 'TemplateMatch',
            'template': step['template'],
            'roi': step['roi'],
            'threshold': step['threshold'],
            'action': 'DoNothing' if dry_run or step['action'] == 'check' else 'Click',
            'target': True,
            'timeout': 20000,
            'rate_limit': 1000,
            'post_delay': 1200 if step['action'] == 'click' else 300,
            'next': [f'Step{i + 1}'] if i + 1 < len(steps) else [],
        }
        pipeline[f'Step{i}'] = node
    return pipeline


class ProgressSink(ContextEventSink):
    def __init__(self, log, labels):
        self.log, self.labels = log, labels

    def on_node_pipeline_node(self, context, noti_type, detail):
        if noti_type == NotificationType.Succeeded:
            self.log(self.labels.get(detail.name, detail.name))


class Engine:
    def __init__(self, log):
        self.log = log
        self.controller = self.resource = self.tasker = None
        self.stop_event = threading.Event()
        self.adb = self.serial = None
        self.options = {}

    def connect(self, adb, serial):
        devices = Toolkit.find_adb_devices(adb)
        device = next((d for d in devices if d.address == serial), None)
        if device is None:
            raise RuntimeError(f'未找到设备 {serial}，请确认雷电已启动并开启 ADB')
        ctrl = AdbController(adb_path=device.adb_path, address=device.address,
                             screencap_methods=MaaAdbScreencapMethodEnum.Encode,
                             input_methods=MaaAdbInputMethodEnum.AdbShell, config=device.config)
        if not ctrl.post_connection().wait().succeeded:
            raise RuntimeError('MaaFramework 连接失败')
        self.controller = ctrl
        self.adb, self.serial = str(adb), serial
        self.log(f'已连接 {serial}')

    def screenshot(self):
        if not self.controller:
            raise RuntimeError('请先连接模拟器')
        # PNG 原始字节避免 PowerShell 重定向破坏图片。
        return adb_run(self.adb, self.serial, 'exec-out', 'screencap', '-p')

    def stop(self):
        self.stop_event.set()
        if self.tasker:
            self.tasker.post_stop()

    def start_game(self):
        import io
        import re
        from PIL import Image
        from daily import Daily
        package='com.tencent.nikke'
        resolved=adb_run(self.adb,self.serial,'shell','cmd','package','resolve-activity',
                         '--brief','-c','android.intent.category.LAUNCHER',package).decode('utf-8',errors='replace')
        component=next((line.strip() for line in resolved.splitlines()
                        if re.fullmatch(r'com\.tencent\.nikke/[A-Za-z0-9_.$]+',line.strip())),None)
        if not component:raise RuntimeError('所选模拟器未找到国服游戏启动入口，请检查是否已安装')
        self.log('已定位游戏启动入口：'+component)
        result=adb_run(self.adb,self.serial,'shell','am','start','-n',component).decode('utf-8',errors='replace')
        if re.search(r'Error:|Exception|Permission Denial',result):
            raise RuntimeError('游戏启动失败：'+result.strip())
        vision=None;deadline=time.monotonic()+240;title_clicks=0;last_title=0
        while time.monotonic()<deadline:
            if self.stop_event.wait(1):raise InterruptedError('用户停止')
            image=Image.open(io.BytesIO(self.screenshot()))
            if abs(image.width/image.height-9/16)>.01:continue
            if vision is None:vision=Daily(self)
            vision.scan()
            maintenance=vision.maintenance_close()
            if maintenance:
                self.log('关闭启动维护公告');vision.tap(*maintenance,delay=2);continue
            if vision.find('点击开始',(250,1400,600,330)) and vision.find('服务器',(250,1000,600,240)):
                if time.monotonic()-last_title<15:continue
                if title_clicks>=3:raise RuntimeError('启动页点击开始后仍未进入游戏')
                vision.click_text('^点击开始$',(250,1400,600,330))
                title_clicks+=1;last_title=time.monotonic();self.log('已点击开始，等待游戏加载')
                continue
            if vision.announcement_close() or vision.login_popup() or vision.supplies_close():
                vision.dismiss_startup_popups()
            if (vision.find('^大厅$',(450,1820,180,100))
                    or vision.find('^返回$',(0,1750,250,130))
                    or vision.find('^妮姬$|^招募队员$',(0,0,320,180))):
                vision.home()
                if vision.lobby():
                    self.log('启动游戏已确认进入大厅');return
            if vision.find('QQ登录|微信登录|输入.*验证码|手机.*登录'):
                raise RuntimeError('游戏需要登录，请完成账号登录后重新运行启动任务')
        raise RuntimeError('启动游戏等待大厅超过四分钟，请检查加载或登录画面')

    def run(self, tasks):
        if not self.controller:
            raise RuntimeError('请先连接模拟器')
        # Claim global missions after all selected daily and event activities,
        # regardless of the caller's or a saved task file's original order.
        tasks = sorted(tasks, key=lambda task: -1 if task.get('handler')=='start_game'
                       else 1 if task.get('handler')=='missions' else 0)
        self.stop_event.clear()
        startup_checked = False
        failed_tasks = []
        for task in tasks:
            if self.stop_event.is_set():
                self.log('已停止')
                return
            if task.get('handler')=='start_game':
                self.log(f"开始：{task['name']}")
                try:
                    self.start_game()
                except InterruptedError:
                    self.log('任务已停止');return
                except Exception as exc:
                    (ROOT/'captures').mkdir(exist_ok=True)
                    failure=ROOT/'captures'/f'failure-startup-{int(time.time())}.png'
                    failure.write_bytes(self.screenshot())
                    self.log(f"启动游戏失败，停止后续任务：{exc}；截图：{failure}")
                    raise
                startup_checked=True
                self.log(f"完成：{task['name']}")
                continue
            if not startup_checked and task.get('package') == 'com.tencent.nikke':
                focus = adb_run(self.adb,self.serial,'shell','dumpsys','window','windows').decode('utf-8',errors='replace')
                lines = [line for line in focus.splitlines() if 'mCurrentFocus=' in line]
                if lines and 'com.tencent.nikke' not in lines[0]:
                    raise RuntimeError('当前前台不是国服游戏')
                from daily import Daily
                try:
                    Daily(self).dismiss_startup_popups()
                    if task.get('pipeline'):
                        Daily(self).home()
                except InterruptedError:
                    self.log('任务已停止')
                    return
                startup_checked = True
            if task.get('handler'):
                focus = adb_run(self.adb, self.serial, 'shell', 'dumpsys', 'window', 'windows').decode('utf-8', errors='replace')
                lines = [line for line in focus.splitlines() if 'mCurrentFocus=' in line]
                if lines and 'com.tencent.nikke' not in lines[0]:
                    raise RuntimeError('当前前台不是国服游戏')
                from daily import Daily
                self.log(f"开始：{task['name']}")
                try:
                    outcome=Daily(self).run(task['handler'])
                except InterruptedError:
                    self.log('任务已停止')
                    return
                except Exception as exc:
                    failed_tasks.append(task['name'])
                    (ROOT / 'captures').mkdir(exist_ok=True)
                    failure=ROOT / 'captures' / f'failure-{int(time.time())}.png'
                    failure.write_bytes(self.screenshot())
                    self.log(f"失败：{task['name']}；{exc}；截图：{failure}")
                    if self.stop_event.is_set():
                        return
                    try:
                        Daily(self).home()
                    except InterruptedError:
                        self.log('任务已停止')
                        return
                    except Exception as recovery:
                        raise RuntimeError(f'恢复大厅失败，停止队列：{recovery}') from exc
                    self.log('已确认恢复大厅，跳过失败任务并继续下一项')
                    continue
                self.log(f"{'跳过' if outcome=='skipped' else '完成'}：{task['name']}")
                continue
            steps = task.get('steps', [])
            for step in steps:
                if not (ROOT / 'resource' / 'image' / step['template']).is_file():
                    raise RuntimeError(f"缺少模板：{step['template']}")
            if 'pipeline' in task:
                pipeline = json.loads((ROOT / task['pipeline']).read_text(encoding='utf-8'))
                entry = task['entry']
            else:
                pipeline = compile_steps(steps)
                entry = 'Entry'
            # 内置任务限竖屏 9:16，避免在其他设备方向错误点击。
            if task.get('aspect'):
                from PIL import Image
                import io
                image = Image.open(io.BytesIO(self.screenshot()))
                if abs(image.width / image.height - task['aspect']) > 0.01:
                    raise RuntimeError('内置任务需要竖屏 9:16，请在雷电中恢复该显示方向')
            package = task.get('package')
            if package:
                focus = adb_run(self.adb, self.serial, 'shell', 'dumpsys', 'window', 'windows').decode(
                    'utf-8', errors='replace')
                lines = [line for line in focus.splitlines() if 'mCurrentFocus=' in line]
                if lines and package not in lines[0]:
                    raise RuntimeError('当前前台不是国服游戏，请先进入游戏大厅')
            bundle = ROOT / 'runtime' / 'bundle'
            (bundle / 'pipeline').mkdir(parents=True, exist_ok=True)
            (bundle / 'pipeline' / 'task.json').write_text(json.dumps(pipeline), encoding='utf-8')
            # 同时加载原始图像目录和当前任务流水线，避免旧节点混入。
            resource = Resource()
            if not resource.post_bundle(ROOT / 'resource').wait().succeeded:
                raise RuntimeError('图像资源加载失败')
            if not resource.post_bundle(bundle).wait().succeeded:
                raise RuntimeError('任务资源加载失败')
            tasker = Tasker()
            if not tasker.bind(resource, self.controller):
                raise RuntimeError('任务执行器初始化失败')
            self.resource, self.tasker = resource, tasker
            sink = ProgressSink(self.log, task.get('labels', {}))
            tasker.add_context_sink(sink)
            if self.stop_event.is_set():
                return
            self.log(f"开始：{task['name']}")
            job = tasker.post_task(entry)
            deadline = time.monotonic() + task.get('total_timeout', len(steps) * 30 + 30)
            while not job.done:
                if self.stop_event.wait(0.1):
                    tasker.post_stop().wait()
                    self.log('任务已停止')
                    return
                if time.monotonic() > deadline:
                    tasker.post_stop().wait()
                    raise RuntimeError('任务超过总时限，队列停止')
            if not job.succeeded:
                (ROOT / 'captures').mkdir(exist_ok=True)
                target = ROOT / 'captures' / f'failure-{int(time.time())}.png'
                target.write_bytes(self.screenshot())
                raise RuntimeError(f'未识别到预期画面，队列停止。截图：{target.name}')
            terminal = 'Done' if 'pipeline' in task else f'Step{len(steps) - 1}'
            last = tasker.get_latest_node(terminal)
            if last is None or not last.completed:
                raise RuntimeError('任务缺少已通过的最终画面检查，队列停止')
            self.log('已通过最终画面检查')
            tasker.clear_context_sinks()
            self.log(f"完成：{task['name']}")
        if failed_tasks:
            self.log('队列已结束，仍有失败任务未完成：' + '、'.join(failed_tasks))
        else:
            self.log('所有选中任务完成')
