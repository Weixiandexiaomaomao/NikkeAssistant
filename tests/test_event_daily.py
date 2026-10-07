import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock
from PIL import Image
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from event_flow import EventActivities


class EventDailyTests(unittest.TestCase):
    def test_story_waits_for_fresh_exact_label_after_animation(self):
        import re
        label={'text':'STORYI','box':[184,1410,147,34]}
        frames={'ready':False}
        def find(expression,*args):
            if expression==r'0\s*[/／]\s*5':return True
            return label if frames['ready'] and re.search(expression,label['text']) else None
        def expect(expression,*args,**kwargs):
            if expression.startswith('^STORY'):
                self.assertIsNone(re.search(expression,'STORYII'))
                frames['ready']=True
        v=SimpleNamespace(options={},scan=Mock(),find=find,expect=Mock(side_effect=expect),
                          click_text=Mock(),e=SimpleNamespace(log=Mock()))
        flow=EventActivities(v);flow.home=Mock();flow.enabled=Mock(return_value=True)
        flow.story()
        v.expect.assert_any_call(r'^STORY\s*I$',(0,1300,500,400),timeout=15)
        v.click_text.assert_called_once_with(r'^STORY\s*I$',(0,1300,500,400))

    def test_open_story_two_pushes_before_configured_farming(self):
        from unittest.mock import patch
        label={'text':'STORY II','box':[100,1500,200,40]}
        v=SimpleNamespace(options={'event_story_mode':'快速战斗','event_farm_stage':11},
            scan=Mock(),find=Mock(side_effect=lambda expression,*args:label if expression==r'^STORY\s*II$' else None),
            e=SimpleNamespace(log=Mock()))
        flow=EventActivities(v);flow.home=Mock();flow.enabled=Mock(return_value=True)
        flow.open_story_part=Mock(return_value=True);flow.select_stage=Mock(return_value=True)
        with patch('event_flow.EventPush') as push:
            flow.story()
            push.return_value.run.assert_called_once()
        flow.open_story_part.assert_called_once_with('II')
        flow.select_stage.assert_called_once_with()

    def test_story_two_without_tickets_never_starts_or_farms(self):
        label={'text':'STORY II','box':[100,1500,200,40]}
        v=SimpleNamespace(options={},scan=Mock(),find=Mock(side_effect=lambda expression,*args:
            label if expression==r'^STORY\s*II$' else True),e=SimpleNamespace(log=Mock()))
        flow=EventActivities(v);flow.home=Mock();flow.enabled=Mock(return_value=True)
        flow.open_story_part=Mock(return_value=True);flow.select_stage=Mock()
        flow.story()
        flow.select_stage.assert_not_called()

    def test_cleared_story_two_falls_back_to_selected_part(self):
        from unittest.mock import patch
        label={'text':'STORY II','box':[100,1500,200,40]}
        v=SimpleNamespace(options={'event_story_part':'I'},scan=Mock(),find=Mock(side_effect=lambda expression,*args:
            label if expression==r'^STORY\s*II$' else None),e=SimpleNamespace(log=Mock()))
        flow=EventActivities(v);flow.home=Mock();flow.enabled=Mock(return_value=True)
        flow.open_story_part=Mock(side_effect=[True,False]);flow.select_stage=Mock(return_value=False)
        with patch('event_flow.EventPush') as push:
            flow.story();push.assert_not_called()
        self.assertEqual([c.args for c in flow.open_story_part.call_args_list],[('II',),('I',)])

    def test_event_prefix_and_locked_rows(self):
        self.assertEqual(EventActivities.stage_number('Event 1-1'),(1,1))
        self.assertIsNone(EventActivities.stage_number('Access Denied'))

    def test_event_entry_waits_for_animated_menu_without_back(self):
        v=SimpleNamespace(scan=Mock(),find=Mock(side_effect=lambda expression,*args:
            True if expression in ('^大厅$','WISDOM|SPRING') else None),
            lobby=Mock(return_value=True),click_text=Mock(),expect=Mock(),wait=Mock(),
            tap=Mock(),e=SimpleNamespace(log=Mock()))
        flow=EventActivities(v,'wisdom')
        flow.is_home=Mock(side_effect=[False,False,False,True])
        flow.home()
        v.click_text.assert_called_once_with('WISDOM|SPRING',(550,1450,530,280))
        v.tap.assert_not_called()
        self.assertEqual(v.wait.call_count,2)

    def test_signin_does_not_wait_for_popup_already_closed_by_shared_handler(self):
        claim={'box':[780,1780,135,50]}
        v=SimpleNamespace(find=Mock(return_value=claim),click_text=Mock(),reward=Mock(),
                          expect=Mock(),wait=Mock(),scan=Mock(),e=SimpleNamespace(log=Mock()))
        flow=EventActivities(v);flow.open_menu=Mock();flow.home=Mock()
        flow.enabled=Mock(side_effect=[True,False])
        flow.signin()
        v.reward.assert_called_once()
        v.expect.assert_any_call('全部领取',(450,1730,600,180),timeout=20)
        self.assertTrue(all(call.args[0]=='全部领取' for call in v.expect.call_args_list))

    def test_lobby_enters_identified_event_before_daily_sections(self):
        v=SimpleNamespace(scan=Mock(),find=Mock(side_effect=lambda expression,*args:
            {'box':[600,1550,200,70]} if expression in ('^大厅$','UNBREAKABLE') else None),
            lobby=Mock(return_value=True),click_text=Mock(),expect=Mock(),wait=Mock(),
            tap=Mock(),e=SimpleNamespace(log=Mock()))
        flow=EventActivities(v)
        flow.is_home=Mock(side_effect=[False,True])
        flow.home()
        v.click_text.assert_called_once_with('UNBREAKABLE',(550,1450,530,280))
        v.tap.assert_not_called()

    def test_missing_event_banner_has_bounded_rotation(self):
        v=SimpleNamespace(scan=Mock(),find=Mock(side_effect=lambda expression,*args:
            True if expression in ('^大厅$','WISDOM|SPRING') else None),
            lobby=Mock(return_value=True),click_text=Mock(),expect=Mock(),wait=Mock(),
            tap=Mock(),e=SimpleNamespace(log=Mock()))
        flow=EventActivities(v)
        flow.is_home=Mock(return_value=False)
        with self.assertRaisesRegex(RuntimeError,'活动入口'):flow.home()
        self.assertEqual(v.tap.call_count,2)
        v.click_text.assert_not_called()

    def test_dimmed_lobby_does_not_click_event_under_modal(self):
        v=SimpleNamespace(scan=Mock(),find=Mock(side_effect=lambda expression,*args:
            True if expression in ('^大厅$','UNBREAKABLE') else None),
            lobby=Mock(return_value=False),click_text=Mock(),tap=Mock())
        flow=EventActivities(v)
        flow.is_home=Mock(return_value=False)
        with self.assertRaisesRegex(RuntimeError,'活动首页'):flow.home()
        v.click_text.assert_not_called();v.tap.assert_not_called()

    def test_gray_claim_and_colored_claim_are_distinct(self):
        v=SimpleNamespace(image=Image.new('RGB',(1080,1920),(80,80,80)))
        flow=EventActivities(v)
        item={'box':[600,1700,300,50]}
        self.assertFalse(flow.enabled(item))
        for color in ((22,170,255),(100,70,190),(255,130,10)):
            v.image=Image.new('RGB',(1080,1920),color)
            self.assertTrue(flow.enabled(item))

    def test_daily_order_and_disabled_component(self):
        flow=EventActivities(SimpleNamespace(options={'event_story':False},e=SimpleNamespace(log=Mock())))
        order=[]
        flow.home=lambda: order.append('home')
        flow.bounded_step=lambda method,seconds:method()
        for name in ('signin','story','challenge','missions'):
            setattr(flow,name,lambda name=name:order.append(name))
        flow.run()
        self.assertEqual(order,['home','signin','challenge','missions'])

    def test_stage_parser_never_accepts_currency_or_ticket_counts(self):
        self.assertEqual(EventActivities.stage_number('1-11'),(1,11))
        for text in ('5/5','2980','STORY I','1-11 故事'):
            self.assertIsNone(EventActivities.stage_number(text))

    def test_unidentified_page_never_clicked(self):
        v=SimpleNamespace(scan=Mock(),find=Mock(return_value=None),tap=Mock(),click_text=Mock())
        with self.assertRaisesRegex(RuntimeError,'活动首页'):
            EventActivities(v).home()
        v.tap.assert_not_called()
        v.click_text.assert_not_called()

    def test_step_failure_recovers_and_continues_to_rewards(self):
        flow=EventActivities(SimpleNamespace(options={},e=SimpleNamespace(log=Mock())))
        flow.home=Mock()
        flow.bounded_step=lambda method,seconds:method()
        flow.signin=Mock()
        flow.story=Mock(side_effect=RuntimeError('步骤超时'))
        flow.challenge=Mock()
        flow.missions=Mock()
        flow.run()
        flow.challenge.assert_called_once()
        flow.missions.assert_called_once()
        self.assertEqual(flow.home.call_count,2)

    def test_user_stop_never_starts_later_sections(self):
        flow=EventActivities(SimpleNamespace(options={},e=SimpleNamespace(log=Mock())))
        flow.home=Mock()
        flow.bounded_step=lambda method,seconds:method()
        flow.signin=Mock(side_effect=InterruptedError('用户停止'))
        flow.story=Mock(); flow.challenge=Mock(); flow.missions=Mock()
        with self.assertRaises(InterruptedError):flow.run()
        flow.story.assert_not_called(); flow.missions.assert_not_called()

    def test_failed_recovery_stops_instead_of_clicking_unidentified_page(self):
        flow=EventActivities(SimpleNamespace(options={},e=SimpleNamespace(log=Mock())))
        flow.home=Mock(side_effect=[None,RuntimeError('页面未知')])
        flow.bounded_step=lambda method,seconds:method()
        flow.signin=Mock(side_effect=RuntimeError('识别失败'))
        flow.story=Mock(); flow.challenge=Mock(); flow.missions=Mock()
        with self.assertRaisesRegex(RuntimeError,'为避免误操作停止'):flow.run()
        flow.story.assert_not_called()

    def test_deadline_restores_wait(self):
        from unittest.mock import patch
        v=SimpleNamespace(wait=Mock())
        original=v.wait
        flow=EventActivities(v)
        with patch('event_flow.time.monotonic',side_effect=[0,100]):
            with self.assertRaisesRegex(RuntimeError,'超时'):
                flow.bounded_step(lambda:v.wait(1),10)
        self.assertIs(v.wait,original)

    def test_wisdom_keeps_options_separate(self):
        v=SimpleNamespace(options={'event_farm_stage':12,'wisdom_farm_stage':11})
        self.assertEqual(EventActivities(v,'wisdom').option('farm_stage'),11)
        self.assertEqual(EventActivities(v).option('farm_stage'),12)

    def test_wisdom_home_requires_its_own_menu(self):
        import re
        page=['活动地区','STORY I','签到印章','挑战','任务']
        v=SimpleNamespace(find=lambda expression,*args:next((x for x in page if re.search(expression,x)),None))
        self.assertFalse(EventActivities(v,'wisdom').is_home())
        page[:]=['剧情活动','ENTER','挑战','任务']
        self.assertTrue(EventActivities(v,'wisdom').is_home())

    def test_wisdom_missions_use_single_panel(self):
        v=SimpleNamespace(click_text=Mock(return_value=True),expect=Mock())
        flow=EventActivities(v,'wisdom');flow.home=Mock();flow.claim_missions=Mock()
        flow.missions()
        flow.claim_missions.assert_called_once_with('任务')
        v.click_text.assert_called_once_with('^任务$',(550,1500,530,240))

    def test_gray_challenge_skips_battle_and_returns_home(self):
        start={'text':'进入战斗','box':[650,1750,280,50]}
        v=SimpleNamespace(scan=Mock(),items=[{'text':'WARNING','box':[300,650,300,70]}],
            find=lambda expression,*args:start if expression=='进入战斗' else None,
            tap=Mock(),expect=Mock(),battle=Mock(),e=SimpleNamespace(log=Mock()))
        flow=EventActivities(v)
        flow.open_menu=Mock();flow.home=Mock();flow.enabled=Mock(return_value=False)
        flow.challenge()
        v.battle.assert_not_called()
        flow.home.assert_called_once()


if __name__=='__main__':unittest.main()
