import json
import io
import queue
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, Mock
from types import SimpleNamespace
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from app import App

class InterfaceTests(unittest.TestCase):
    def test_start_connects_selected_instance_before_tasks_and_stops_on_failure(self):
        image = io.BytesIO()
        Image.new('RGB', (1080,1920)).save(image,format='PNG')
        engine = Mock()
        engine.serial = 'emulator-5554'
        engine.screenshot.return_value = image.getvalue()
        target = SimpleNamespace(tasks=[{'name':'邮箱'}],
            task_list=Mock(), adb=Mock(), serial=Mock(), save_preferences=Mock(),
            events=queue.Queue(), engine=engine, work=lambda fn: fn(), log=Mock())
        target.task_list.curselection.return_value = (0,)
        target.adb.get.return_value = 'adb.exe'
        target.serial.get.return_value = 'emulator-5556'
        target.run_tasks=lambda selected: App.run_tasks(target,selected)
        with patch('app.discover_adb',return_value='adb.exe'):
            App.run(target)
            self.assertEqual(engine.method_calls[0],
                unittest.mock.call.connect('adb.exe','emulator-5556'))
            self.assertEqual(engine.method_calls[2], unittest.mock.call.run(target.tasks))
            engine.reset_mock()
            engine.connect.side_effect = RuntimeError('连接失败')
            with self.assertRaisesRegex(RuntimeError,'连接失败'):
                App.run(target)
            engine.run.assert_not_called()

    def test_single_task_button_ignores_other_checked_tasks(self):
        target=SimpleNamespace(tasks=[{'id':'cn_shop'},{'id':'cn_interception'}],run_tasks=Mock())
        App.run_task(target,1)
        target.run_tasks.assert_called_once_with([target.tasks[1]])

    def test_focus_selection_persistence_and_three_columns(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            (root/'tasks.json').write_bytes((ROOT/'tasks.json').read_bytes())
            with patch('app.ROOT',root),patch('modern_ui.ROOT',root):
                app=App(auto_scan=False)
                try:
                    app.update()
                    app.apply_devices('adb.exe',['emulator-5554','emulator-5556'],
                                      'emulator-5556',{'emulator-5556':'雷电模拟器-1'})
                    self.assertEqual(app.device_display.get(),'雷电模拟器-1（emulator-5556）')
                    self.assertEqual(app.serial.get(),'emulator-5556')
                    app.select_device('Android 设备（emulator-5554）')
                    self.assertEqual(app.serial.get(),'emulator-5554')
                    app.apply_devices('adb.exe',['emulator-5554','emulator-5556'],
                                      'emulator-5556',{'emulator-5554':'已改名'})
                    self.assertEqual(app.device_display.get(),'已改名（emulator-5554）')
                    event = next(i for i,t in enumerate(app.tasks) if t.get('handler')=='event_daily')
                    push = next(i for i,t in enumerate(app.tasks) if t.get('handler')=='event_push')
                    self.assertIn(event,app.visible_indices())
                    self.assertNotIn(push,app.visible_indices())
                    app.checked[event].set(True)
                    self.assertEqual(app.task_list.curselection().count(event),1)
                    self.assertEqual(app.tasks[-1]['handler'],'missions')
                    self.assertEqual(app.tasks[app.task_list.curselection()[-1]]['handler'],'missions')
                    app._set_profile('活动任务')
                    self.assertIn(event,app.task_list.curselection())
                    app.focus_task(event)
                    app.engine.options['event_challenge']=False
                    app._set_profile('日常长草')
                    self.assertTrue(app.checked[event].get())
                    self.assertFalse(app.engine.options['event_challenge'])
                    selected=app.task_list.curselection()
                    app.focus_task(6)
                    self.assertEqual(selected,app.task_list.curselection())
                    self.assertLess(app.task_scroll.winfo_rootx(),app.settings_body.winfo_rootx())
                    self.assertLess(app.settings_body.winfo_rootx(),app.canvas.winfo_rootx())
                    self.assertGreater(app.logs.winfo_rooty(),app.canvas.winfo_rooty()+app.canvas.winfo_height())
                    app.engine.options['simulation_region']='5'
                    app.selection_changed()
                    saved=json.loads((root/'settings.json').read_text(encoding='utf-8'))
                    self.assertEqual(saved['options']['simulation_region'],'5')
                    self.assertEqual(saved['serial'],'emulator-5554')
                    self.assertEqual(len(saved['selected']),len(selected))
                    app.lock_controls(True)
                    self.assertEqual(app.device_box.cget('state'),'disabled')
                    self.assertEqual(app.start_button.cget('text'),'■ 停止任务')
                    app.lock_controls(False)
                    self.assertEqual(app.device_box.cget('state'),'readonly')
                finally: app.close()

if __name__=='__main__': unittest.main()
