import subprocess
import threading
import unittest
import io
from PIL import Image
from types import SimpleNamespace
from unittest.mock import Mock, patch

from daily import Daily
from emulator_launch import ensure_emulator, normalize_emulator, startup_tasks


class StartupTests(unittest.TestCase):
    def test_stalled_black_splash_relaunches_then_accepts_real_page(self):
        from engine import Engine
        clock=[0]
        def wait(_):clock[0]+=35;return False
        def frame(color):
            stream=io.BytesIO();Image.new('RGB',(720,1280),color).save(stream,format='PNG');return stream.getvalue()
        e=Engine(Mock());e.adb='adb';e.serial='selected'
        e.stop_event=Mock();e.stop_event.wait.side_effect=wait
        e.screenshot=Mock(side_effect=[frame('black')]*3+[frame('white')])
        with patch('engine.time.monotonic',side_effect=lambda:clock[0]), \
             patch('engine.adb_run',return_value=b'com.tencent.nikke/.default_Activity') as adb, \
             patch('daily.Daily') as daily:
            d=daily.return_value
            d.maintenance_close.return_value=None;d.announcement_close.return_value=None
            d.login_popup.return_value=None;d.supplies_close.return_value=None
            d.find.side_effect=[None,True];d.lobby.return_value=True
            e.start_game()
        calls=[call.args for call in adb.call_args_list]
        self.assertEqual(sum('force-stop' in call for call in calls),1)
        launches=[call for call in calls if 'start' in call]
        self.assertEqual(len(launches),2)
        self.assertTrue(all('android.intent.category.LAUNCHER' in call for call in launches))
        d.scan.assert_called_once_with()

    def test_loading_announcement_does_not_depend_on_checkbox_ocr(self):
        d = Daily.__new__(Daily)
        d.find = Mock(side_effect=[{'box': [522, 398, 91, 52]}, {'text': '亲爱的指挥官'}])
        d.blue = Mock(return_value=True)
        d.close_cross = Mock(return_value=(960, 424))
        self.assertEqual(d.maintenance_close(), (960, 424))
        self.assertEqual(d.find.call_count, 2)

    def test_loading_announcement_requires_real_close_icon(self):
        d = Daily.__new__(Daily)
        d.find = Mock(side_effect=[{'box': [522, 398, 91, 52]}, {'text': '亲爱的指挥官'}])
        d.blue = Mock(return_value=True)
        d.close_cross = Mock(return_value=None)
        self.assertIsNone(d.maintenance_close())

    def test_run_starts_selected_emulator_and_waits_until_ready(self):
        config = normalize_emulator({}, 'emulator-5558')
        with patch('emulator_launch.discover_adb', return_value='adb.exe'), \
             patch('emulator_launch.ready', side_effect=[False, False, True]), \
             patch('emulator_launch.command', return_value=['ldconsole.exe', 'launch', '--index', '2']), \
             patch('emulator_launch.subprocess.Popen') as launch:
            stop = Mock(); stop.is_set.return_value = False; stop.wait.return_value = False
            self.assertEqual(ensure_emulator('adb.exe', 'emulator-5558', config, Mock(), stop), 'adb.exe')
            self.assertEqual(launch.call_args.args[0][-1], '2')
            self.assertEqual(stop.wait.call_count, 2)

    def test_run_inserts_game_launch_even_when_task_is_unchecked(self):
        config = normalize_emulator({}, 'emulator-5558')
        tasks = [{'id': 'cn_mailbox', 'package': 'com.tencent.nikke'}]
        queued = startup_tasks(tasks, config)
        self.assertEqual(queued[0]['handler'], 'start_game')
        self.assertEqual(startup_tasks(queued, config), queued)


if __name__ == '__main__':
    unittest.main()
