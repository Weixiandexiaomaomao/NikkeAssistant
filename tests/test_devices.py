import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from portable import discover_device_names


class DeviceNamesTests(unittest.TestCase):
    def test_chinese_title_comma_and_confirmed_serial(self):
        listing = '7,自定义,模拟器,10,20,1,30,40,1080,1920,280\n'.encode('gb18030')
        responses = [subprocess.CompletedProcess([], 0, listing),
                     subprocess.CompletedProcess([], 0, b'emulator-5556\r\n')]
        with patch('portable.Path.is_file', return_value=True), \
             patch('portable.subprocess.run', side_effect=responses) as run:
            self.assertEqual(discover_device_names('adb.exe', ['emulator-5556']),
                             {'emulator-5556': '自定义,模拟器'})
            self.assertIn('7', run.call_args.args[0])

    def test_unavailable_console_falls_back_without_guessing(self):
        with patch('portable.Path.is_file', return_value=True), \
             patch('portable.subprocess.run', side_effect=OSError('unavailable')):
            self.assertEqual(discover_device_names('adb.exe', ['emulator-5556']), {})


if __name__ == '__main__':
    unittest.main()
