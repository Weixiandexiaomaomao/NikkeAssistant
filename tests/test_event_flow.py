import re
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from event_flow import EventPush


class Replay:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.page = []
        self.options = {'event_push_count': 1}
        self.e = SimpleNamespace(log=Mock())
        self.actions = []

    def scan(self):
        self.page = next(self.pages)

    def find(self, expression, *args):
        return next((text for text in self.page if re.search(expression,text)),None)

    def click_text(self, expression, *args, **kwargs):
        text = self.find(expression)
        if text:
            self.actions.append(text)
        return bool(text)

    def wait(self, seconds):
        pass

    def colorful_button(self, item):
        return True


class EventTests(unittest.TestCase):
    def test_disabled_stage_button_skips_without_input(self):
        v=Replay([['1-11 故事','进入战斗'],['1-11 故事','进入战斗']])
        v.colorful_button=lambda item:False
        self.assertEqual(EventPush(v).run(),'skipped')
        self.assertEqual(v.actions,[])

    def test_lobby_never_clicked(self):
        v = Replay([['大厅','作战出击']])
        with self.assertRaisesRegex(RuntimeError,'请选择|请先进入'):
            EventPush(v).run()
        self.assertEqual(v.actions,[])

    def test_stops_after_one_stage_without_starting_next(self):
        v = Replay([['1-1','战斗开始'],['1-1','战斗开始'],
                    ['战斗胜利','下一关卡']])
        EventPush(v).run()
        self.assertEqual(v.actions,['战斗开始'])

    def test_tickets_and_failure_stop_without_confirmation(self):
        for text in ('门票不足','战斗失败','尚未解锁'):
            v = Replay([['1-1','战斗开始'],[text,'确定']])
            with self.assertRaises(RuntimeError):
                EventPush(v).run()
            self.assertEqual(v.actions,[])


if __name__=='__main__': unittest.main()
