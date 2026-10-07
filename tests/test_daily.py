import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch, Mock
from PIL import Image, ImageDraw
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from daily import Daily

class DailyChecks(unittest.TestCase):
    def test_promotion_closes_footer_once_then_resumes_recognition(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock());d.tap=Mock()
        offer=[{'text':'从同时出现的礼包中选择一个购买。','box':[220,940,650,40]},
               {'text':'点击关闭画面。','box':[400,1770,280,40]}]
        frames=iter([offer,[{'text':'方舟','box':[50,50,80,40]}]])
        d.scan_raw=lambda:setattr(d,'items',next(frames))
        self.assertEqual(d.scan()[0]['text'],'方舟')
        d.tap.assert_called_once_with(540,1790,delay=2)

    def test_promotion_does_not_close_without_both_offer_and_close_prompt(self):
        d=Daily.__new__(Daily)
        for items in ([{'text':'点击关闭画面。','box':[400,1770,280,40]}],
                      [{'text':'从礼包中选择一个购买。','box':[220,940,650,40]}],
                      [{'text':'每日免费礼包','box':[100,690,250,40]}]):
            d.items=items;self.assertIsNone(d.promotion_close())

    def test_persistent_promotion_has_a_bounded_close_limit(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock());d.tap=Mock();d.scan_raw=Mock()
        d.items=[{'text':'从礼包中选择一个购买。','box':[220,940,650,40]},
                 {'text':'点击关闭画面。','box':[400,1770,280,40]}]
        with self.assertRaisesRegex(RuntimeError,'礼包推销弹窗关闭重试'):d.scan()
        self.assertEqual(d.tap.call_count,6)

    def test_native_daily_pipelines_prioritize_promotion_close_at_each_transition(self):
        import json
        for name in ('mailbox','friends','defense'):
            nodes=json.loads((ROOT/'pipelines'/f'{name}.json').read_text(encoding='utf-8'))
            for key,node in nodes.items():
                if key!='PromotionClose' and node.get('next'):
                    self.assertEqual(node['next'][0],'PromotionClose')
            self.assertGreater(nodes['PromotionClose']['target'][1],1100)
            self.assertEqual(len(nodes['PromotionClose']['all_of']),2)

    def test_launch_task_runs_first_and_missions_still_run_last(self):
        from engine import Engine
        e=Engine(Mock());e.controller=object();events=[]
        e.start_game=lambda:events.append('start_game')
        tasks=[{'name':'奖励','handler':'missions'},{'name':'咨询','handler':'advise'},
               {'name':'启动游戏','handler':'start_game','package':'com.tencent.nikke'}]
        with patch('engine.adb_run',return_value=b'') as adb,patch('daily.Daily') as daily:
            daily.return_value.run.side_effect=lambda kind:events.append(kind)
            e.run(tasks)
        self.assertEqual(events,['start_game','advise','missions'])
        daily.return_value.dismiss_startup_popups.assert_not_called()

    def test_launch_rejects_missing_or_other_games_component(self):
        from engine import Engine
        e=Engine(Mock());e.adb='adb';e.serial='chosen'
        for response in (b'No activity found',b'com.other.game/.MainActivity'):
            with patch('engine.adb_run',return_value=response) as adb:
                with self.assertRaisesRegex(RuntimeError,'未找到国服游戏'):e.start_game()
                self.assertEqual(adb.call_count,1)

    def test_launch_failure_stops_remaining_queue(self):
        from engine import Engine
        from tempfile import TemporaryDirectory
        e=Engine(Mock());e.controller=object();e.screenshot=Mock(return_value=b'capture')
        e.start_game=Mock(side_effect=RuntimeError('启动失败'))
        with TemporaryDirectory() as temp,patch('engine.ROOT',Path(temp)),patch('daily.Daily') as daily:
            with self.assertRaisesRegex(RuntimeError,'启动失败'):
                e.run([{'name':'邮件','handler':'missions'},
                       {'name':'启动游戏','handler':'start_game'}])
            daily.assert_not_called()

    def test_launch_waits_through_landscape_before_using_portrait_recognition(self):
        import io
        from engine import Engine
        frames=[]
        for size in ((1280,720),(720,1280)):
            b=io.BytesIO();Image.new('RGB',size).save(b,format='PNG');frames.append(b.getvalue())
        e=Engine(Mock());e.adb='adb';e.serial='chosen';e.stop_event=Mock()
        e.stop_event.wait.return_value=False;e.screenshot=Mock(side_effect=frames)
        with patch('engine.adb_run',side_effect=[b'com.tencent.nikke/.default_Activity',b'Starting: Intent']),patch('daily.Daily') as daily:
            d=daily.return_value;d.maintenance_close.return_value=None
            d.announcement_close.return_value=None;d.login_popup.return_value=None;d.supplies_close.return_value=None
            d.find.side_effect=[None,True];d.lobby.return_value=True
            e.start_game()
        daily.assert_called_once_with(e);d.scan.assert_called_once_with();d.home.assert_called_once_with()

    def test_bond_notifications_are_round_dots_in_the_requested_strip(self):
        d=Daily.__new__(Daily);d.image=Image.new('RGB',(1080,1920),'white')
        draw=ImageDraw.Draw(d.image)
        draw.ellipse((1010,700,1030,720),fill=(255,70,20))
        draw.rectangle((1010,900,1030,920),fill=(255,70,20))
        draw.ellipse((300,700,320,720),fill=(255,70,20))
        self.assertEqual(d.notification_dots((995,550,55,1160)),[(1020,710)])

    def test_bond_list_can_replace_a_claimed_row_with_another_pending_character(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock());d.expect=Mock();d.scan=Mock()
        d.image=Image.new('RGB',(1080,1920),'white');d.tap=Mock();d.bond_scroll=Mock();d.click_text=Mock()
        d.notification_dots=Mock(side_effect=[[(1020,700)],[(1020,700)],[],[]])
        d.find=Mock(side_effect=[{'text':'诺亚尔'},{'text':'克雷伊'}]);d.bond_chapters=Mock(return_value=1)
        self.assertEqual(d.bond_rewards(),2)
        self.assertEqual(d.bond_chapters.call_count,2)

    def test_bond_rewards_checked_even_with_no_advise_attempts(self):
        d=Daily.__new__(Daily);d.advise_batch=Mock(return_value='skipped')
        d.bond_rewards=Mock(return_value=2)
        self.assertIsNone(d.advise());d.bond_rewards.assert_called_once_with()

    def test_bond_chapter_waits_for_reward_fade_in_before_accepting_return(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock());d.expect=Mock()
        d.image=Image.new('RGB',(1080,1920),'white');d.tap=Mock();d.wait=Mock();d.bond_scroll=Mock()
        d.notification_dots=Mock(side_effect=[[(980,1000)],[],[]])
        d.skip_bond_story=Mock(return_value=True)
        state={'scan':0}
        def scan():
            state['scan']+=1;d.reward_dismissed=state['scan']==4
        d.scan=scan;d.find=lambda *args:state['scan']!=2
        self.assertEqual(d.bond_chapters(),1)
        d.skip_bond_story.assert_called_once_with()
        self.assertEqual(d.tap.call_count,2)
        d.wait.assert_called_once_with(1)

    def test_advise_keeps_skipped_status_when_neither_consultation_nor_rewards_available(self):
        d=Daily.__new__(Daily);d.advise_batch=Mock(return_value='skipped');d.bond_rewards=Mock(return_value=0)
        self.assertEqual(d.advise(),'skipped')

    def wipe_panel(self, center=698, price=None, notification=True):
        d=Daily.__new__(Daily);d.blue=Mock(return_value=True)
        d.items=[{'text':'进行歼灭','box':[center-74,1452,148,44]},
                 {'text':'每日首次免费，战斗经验值除外','box':[319,1016,443,34]}]
        if price is not None:d.items.append({'text':str(price),'box':[585,1454,36,34]})
        d.image=Image.new('RGB',(1080,1920))
        if notification:d.image.paste((74,36,8),(515,1585,530,1605))
        return d

    def test_free_wipe_without_price_requires_centered_button_and_notification(self):
        self.assertTrue(self.wipe_panel().wipe_free_available())
        self.assertFalse(self.wipe_panel(notification=False).wipe_free_available())

    def test_paid_wipe_is_rejected_despite_daily_free_description(self):
        self.assertFalse(self.wipe_panel(center=822,price=50).wipe_free_available())
        self.assertFalse(self.wipe_panel(price=50).wipe_free_available())

    def test_offscreen_step_up_tab_scrolls_in_category_strip(self):
        d=Daily.__new__(Daily);d.scan=Mock();d.wait=Mock()
        d.click_text=Mock(side_effect=[False,True]);d.find=Mock(return_value=True)
        controller=Mock()
        controller.post_screencap.return_value.wait.return_value.get.return_value=SimpleNamespace(shape=(1280,720,3))
        controller.post_swipe.return_value.wait.return_value.succeeded=True
        d.e=SimpleNamespace(controller=controller)
        d.select_pack_tab('STEP UP礼包',page='限时礼包',pattern=r'STEP\s*UP.*礼包')
        controller.post_swipe.assert_called_once_with(640,363,440,363,600)
        d.find.assert_called_once_with('限时礼包',(300,100,500,200))

    def test_free_pack_requires_title_stock_and_free_price(self):
        d=Daily.__new__(Daily);d.expect=Mock();d.pack_stock=Mock(return_value=1)
        d.find=Mock(return_value=None);d.tap=Mock()
        with self.assertRaisesRegex(RuntimeError,'免费价格'):
            d.claim_free_pack('^每日免费礼包$',(30,660,330,130),(30,950,330,160),(30,1140,330,140))
        d.tap.assert_not_called()

    def test_free_pack_waits_for_stock_zero_without_repeated_purchase(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock());d.expect=Mock()
        d.pack_stock=Mock(side_effect=[1,1,0]);d.find=Mock(return_value={'box':[164,1190,86,48]})
        d.tap=Mock();d.scan=Mock();d.wait=Mock()
        d.claim_free_pack('^每日免费礼包$',(30,660,330,130),(30,950,330,160),(30,1140,330,140))
        d.tap.assert_called_once_with(207,1214,3)
        d.wait.assert_called_once_with(1)

    def test_already_claimed_pack_does_not_click(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock());d.expect=Mock()
        d.pack_stock=Mock(return_value=0);d.tap=Mock()
        d.claim_free_pack('^每周免费礼包$',(30,660,330,130),(30,950,330,160),(30,1140,330,140))
        d.tap.assert_not_called()

    def test_step_up_does_not_skip_paid_stage_to_later_free_labels(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock());d.expect=Mock();d.scan=Mock()
        d.items=[{'text':'阶段1','box':[140,906,96,30]},
                 {'text':'阶段2','box':[150,1112,90,36]},
                 {'text':'阶段3','box':[135,1324,105,34]},
                 {'text':'免费','box':[950,1440,86,46]}]
        d.pack_stock=Mock(side_effect=[0,1]);d.claim_free_pack=Mock()
        d.step_up_free_pack()
        d.claim_free_pack.assert_not_called()

    def test_rookie_defeat_is_settled_before_continuing_daily_challenges(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock());d.wait=Mock();d.reward_dismissed=False
        frames=iter([
            [{'text':'DEFEAT','box':[200,220,650,210]}, {'text':'ROOKIE ARENA','box':[400,550,280,50]}],
            [{'text':'点击进行下一步','box':[360,1700,350,45]}],
            [{'text':'新人竞技场','box':[20,45,250,60]}]])
        d.scan=lambda:setattr(d,'items',next(frames))
        d.click_text=Mock(side_effect=[False,False,True,False])
        self.assertTrue(d.battle('新人竞技场',allow_defeat=True))
        d.e.log.assert_called_once_with('竞技场本场落败，等待结算后继续剩余免费挑战')
    def test_rookie_waits_for_all_three_opponents_after_result_transition(self):
        d=Daily.__new__(Daily);d.wait=Mock();d.find=Mock(return_value=True)
        buttons=[{'text':'进入战斗','box':[780,y,190,60]} for y in (1040,1320,1590)]
        frames=iter([[],buttons,buttons])
        d.scan=lambda:setattr(d,'items',next(frames))
        d.wait_rookie_list()
        self.assertEqual(d.wait.call_count,2)
    def test_interception_waits_through_stale_count_before_allowing_next_battle(self):
        d=Daily.__new__(Daily);d.wait=Mock()
        counts=iter(['3/3','3/3','2/3'])
        state={}
        d.scan=lambda:state.update(text=next(counts))
        d.find=lambda *args:{'text':state['text']}
        d.wait_interception_settled(3)
        self.assertEqual(d.wait.call_count,2)

    def test_simulation_completed_until_reset_does_not_click_start_again(self):
        import tempfile,json,time
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock(),serial='emulator-5556')
        d.ark=Mock();d.scan=Mock();d.items=[];d.click_text=Mock()
        with tempfile.TemporaryDirectory() as folder,patch('daily.ROOT',Path(folder)):
            state=Path(folder)/'runtime/simulation.json';state.parent.mkdir()
            state.write_text(json.dumps({'serial':'emulator-5556','completed_until':time.time()+100}))
            self.assertEqual(d.simulation(),'skipped')
        d.click_text.assert_not_called()

    def test_free_refresh_retries_only_verified_shop_then_stops_at_dialog(self):
        d=Daily.__new__(Daily);d.scan=Mock();d.tap=Mock();d.expect=Mock();d.e=SimpleNamespace(log=Mock())
        state={'taps':0}
        def tap(*args,**kwargs):state['taps']+=1
        d.tap.side_effect=tap
        def find(expression,*args):
            if expression=='是否更新商品':return True if state['taps']==2 else None
            if expression=='^免费$':return {'box':[610,826,88,28]}
            return True
        d.find=find;d.open_free_shop_refresh()
        self.assertEqual(d.tap.call_count,2)
        d.tap.assert_called_with(400,872,3,hold_ms=200)

    def test_shop_refresh_waits_for_dialog_to_close_and_stock_to_update(self):
        d=Daily.__new__(Daily);d.wait=Mock()
        frames=iter(['dialog','old_stock','refreshed'])
        state={}
        d.scan=lambda:state.update(page=next(frames))
        def find(expression,*args):
            if expression=='普通商店':return True
            if expression=='是否更新商品':return state['page']=='dialog'
            if expression in ('^免费$','售罄|售馨'):return state['page']!='refreshed'
        d.find=find
        d.wait_shop_refreshed()
        self.assertEqual(d.wait.call_count,2)

    def test_character_reward_result_confirms_without_recruit_again(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock());d.tap=Mock()
        result=[{'text':'RECRUITMENT RESULT','box':[63,264,290,28]},
                {'text':'确认','box':[494,1706,87,54]},
                {'text':'再招募','box':[760,1706,120,54]}]
        page=[{'text':'大厅','box':[500,1850,80,30]}]
        frames=iter([result,page]);d.scan_raw=lambda:setattr(d,'items',next(frames))
        self.assertEqual(d.scan(),page)
        d.tap.assert_called_once_with(537.5,1733,delay=2)
        self.assertTrue(d.acquire_dismissed)

    def test_free_recruitment_accepts_shared_result_confirmation(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock());d.click_text=Mock(return_value=True)
        d.expect=Mock();d.wait=Mock();d.colorful_button=Mock(return_value=True)
        d.recruit_paid_only=Mock(return_value=True);d.finish_recruit_result=Mock()
        state={'settled':False}
        def scan():
            state['settled']=d.acquire_dismissed=bool(d.click_text.call_count>=2)
        d.scan=scan
        def find(expression,*args):
            if '每日免费' in expression:return None if state['settled'] else {'text':'每日免费1次'}
            return True
        d.find=find
        d.recruit_free()
        d.finish_recruit_result.assert_not_called()
        self.assertEqual(d.click_text.call_count,2)

    def test_character_reveal_is_skipped_and_next_page_rescanned(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock());d.tap=Mock()
        reveal=[{'text':'TETRA','box':[23,68,368,160]},
                {'text':'跳过','box':[893,26,141,56]},
                {'text':'SSR','box':[927,1478,131,66]},
                {'text':'首次得','box':[762,1714,89,30]}]
        page=[{'text':'RECRUITMENT RESULT','box':[80,100,500,60]}]
        frames=iter([reveal,page]);d.scan_raw=lambda:setattr(d,'items',next(frames))
        self.assertEqual(d.scan(),page)
        d.tap.assert_called_once_with(963.5,54,delay=2)
        self.assertFalse(d.reward_dismissed)

    def test_story_skip_is_not_character_reveal(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock());d.tap=Mock()
        d.items=[{'text':'跳过','box':[893,26,141,56]}]
        d.scan_raw=Mock()
        self.assertEqual(d.scan(),d.items)
        d.tap.assert_not_called()

    def test_character_reveal_stuck_has_bounded_retry(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock());d.tap=Mock();d.scan_raw=Mock()
        d.items=[{'text':'TETRA','box':[23,68,368,160]},
                 {'text':'跳过','box':[893,26,141,56]},
                 {'text':'SSR','box':[927,1478,131,66]},
                 {'text':'首次得','box':[762,1714,89,30]}]
        with self.assertRaisesRegex(RuntimeError,'获得角色展示页跳过重试'):d.scan()
        self.assertEqual(d.tap.call_count,6)

    def test_recruit_result_confirms_without_clicking_paid_repeat(self):
        d=Daily.__new__(Daily);d.find=Mock(return_value=True);d.click_text=Mock();d.expect=Mock()
        d.e=SimpleNamespace(log=Mock())
        self.assertTrue(d.finish_recruit_result())
        d.click_text.assert_called_once_with('^确认$',(100,1550,440,320))

    def test_used_recruitment_never_clicks_paid_single(self):
        d=Daily.__new__(Daily);d.click_text=Mock(return_value=True);d.expect=Mock()
        d.wait=Mock();d.scan=Mock();d.find=Mock(return_value=None);d.recruit_paid_only=Mock(return_value=True)
        d.e=SimpleNamespace(log=Mock())
        self.assertEqual(d.recruit_free(),'skipped')
        d.click_text.assert_called_once_with('^队员招募$',(750,1720,330,200))

    def test_interception_uses_real_battle_when_quick_is_unavailable(self):
        import re
        d=Daily.__new__(Daily); d.options={'interception_count':1}; d.e=SimpleNamespace(log=Mock())
        d.ark=Mock(); d.scan=Mock(); d.expect=Mock(); d.reward=Mock(); d.click_text=Mock(return_value=True)
        state={'count':3}
        def find(expression,roi=(0,0,1080,1920)):
            words=['挑战','每日快速战斗','进入战斗',str(state['count'])+'/3']
            word=next((w for w in words if re.search(expression,w)),None)
            return {'text':word,'box':[700,1700,200,60]} if word else None
        d.find=find
        d.colorful_button=lambda item:item['text']!='每日快速战斗'
        def battle(_): state['count']-=1; return True
        d.battle=Mock(side_effect=battle)
        d.interception()
        d.battle.assert_called_once()
        d.reward.assert_not_called()
        d.e.log.assert_any_call('已核实拦截次数减少')

    def test_native_queue_recovers_hall_before_loading_pipeline(self):
        from engine import Engine
        engine=Engine(Mock());engine.controller=object()
        with patch('engine.adb_run',return_value=b''),patch('daily.Daily') as daily:
            daily.return_value.home.side_effect=InterruptedError('stopped')
            engine.run([{'name':'邮箱','pipeline':'mailbox.json','package':'com.tencent.nikke'}])
        daily.return_value.dismiss_startup_popups.assert_called_once()
        daily.return_value.home.assert_called_once()
        engine.log.assert_called_with('任务已停止')

    def test_recovered_failure_continues_queue_without_reporting_all_complete(self):
        import tempfile
        from engine import Engine
        engine=Engine(Mock());engine.controller=object();engine.screenshot=Mock(return_value=b'capture')
        with tempfile.TemporaryDirectory() as folder, patch('engine.ROOT',Path(folder)), \
                patch('engine.adb_run',return_value=b''), patch('daily.Daily') as daily:
            daily.return_value.run.side_effect=[RuntimeError('menu missing'),None]
            engine.run([{'name':'活动','handler':'event_wisdom_daily'},
                        {'name':'奖励','handler':'missions'}])
        self.assertEqual(daily.return_value.run.call_count,2)
        daily.return_value.home.assert_called_once()
        engine.log.assert_any_call('队列已结束，仍有失败任务未完成：活动')
        self.assertNotIn('所有选中任务完成',[c.args[0] for c in engine.log.call_args_list])

    def test_simulation_result_never_clicks_background_end_button_under_confirmation(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock())
        d.find=Mock(return_value=True);d.click_text=Mock(return_value=True);d.expect=Mock()
        self.assertTrue(d.finish_simulation_result())
        d.click_text.assert_called_once_with('^确认$',(300,1130,500,150),blue=True)
        d.expect.assert_called_once_with('^开始模拟$',(240,1000,620,300),timeout=25)

    def test_simulation_result_does_not_end_unknown_or_failed_screen(self):
        d=Daily.__new__(Daily);d.find=Mock(return_value=None);d.click_text=Mock()
        self.assertFalse(d.finish_simulation_result())
        d.click_text.assert_not_called()

    def test_shop_refresh_rejects_nonzero_or_unreadable_cost(self):
        d=Daily.__new__(Daily);d.scan=Mock();d.find=Mock(return_value=True)
        d.zero_price=Mock(return_value=False);d.click_text=Mock()
        with self.assertRaisesRegex(RuntimeError,'未核实零价'):
            d.confirm_free_shop_refresh()
        d.click_text.assert_called_once_with('^取消$',(150,1130,350,150))

    def test_shop_free_refresh_confirms_only_after_zero_cost(self):
        d=Daily.__new__(Daily);d.scan=Mock();d.find=Mock(return_value=True)
        d.zero_price=Mock(return_value=True);d.click_text=Mock(return_value=True)
        d.confirm_free_shop_refresh()
        d.zero_price.assert_called_once_with((620,1000,30,50))
        d.click_text.assert_called_once_with('^确认$',(550,1130,450,150),blue=True)

    def test_pass_claims_tasks_before_rewards_and_skips_gray_buttons(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock())
        d.scan=Mock();d.tap=Mock();d.expect=Mock();d.lobby=Mock(return_value=True)
        d.pass_page=Mock(return_value=True)
        d.find=Mock(return_value={'box':[700,260,300,70]})
        d.click_text=Mock(side_effect=[True,False,False,False,False,False,False]);d.reward=Mock()
        d.pass_rewards()
        self.assertEqual([c.args[:2] for c in d.tap.call_args_list][1:3],[(780,620),(280,620)])
        self.assertTrue(all(c.args[0]=='^全部领取$' and c.kwargs['blue'] for c in d.click_text.call_args_list))
        d.reward.assert_called_once()
        self.assertEqual(d.tap.call_args_list[-1].args,(975,132,3))

    def test_global_mission_rewards_run_after_daily_and_event_tasks(self):
        from engine import Engine
        engine=Engine(Mock());engine.controller=object()
        tasks=[{'name':'奖励','handler':'missions'},
               {'name':'咨询','handler':'advise'},
               {'name':'活动','handler':'event_wisdom_daily'}]
        with patch('engine.adb_run',return_value=b''),patch('daily.Daily') as daily:
            engine.run(tasks)
        self.assertEqual([c.args[0] for c in daily.return_value.run.call_args_list],
                         ['advise','event_wisdom_daily','missions'])
        self.assertEqual(tasks[0]['handler'],'missions')

    def test_consult_count_ignores_selected_batch_consumption(self):
        d=Daily.__new__(Daily)
        d.items=[{'text':'消耗次数10/10','box':[21,1532,237,40]},
                 {'text':'0/10','box':[343,444,91,36]}]
        self.assertEqual(d.advise_remaining(),0)
        d.items=d.items[:1]
        self.assertIsNone(d.advise_remaining())

    def test_home_retries_when_navigation_appears_after_result_animation(self):
        d=Daily.__new__(Daily);d.items=[]
        d.dismiss_startup_popups=Mock();d.tap=Mock();d.wait=Mock();d.blue=Mock(return_value=True)
        checks=iter([False,False,True])
        def lobby():
            result=next(checks)
            if not result and checks:
                d.items=[{'text':'返回','box':[110,1796,70,36]}] if lobby.calls else []
            lobby.calls+=1
            return result
        lobby.calls=0;d.lobby=lobby
        d.home()
        d.tap.assert_called_once_with(295,1810,5)

    def test_rookie_target_uses_free_badge_and_selected_row(self):
        d=Daily.__new__(Daily);d.blue=Mock(return_value=True)
        d.items=[{'text':'0','box':[144,885,49,55]}]
        for y in (1016,1284,1552):
            d.items.extend([{'text':'免费','box':[869,y,62,32]},
                            {'text':'进入战斗','box':[831,y+54,129,42]}])
        self.assertEqual(d.rookie_target(3)['box'][1],1606)
        self.assertEqual(d.rookie_target(1)['box'][1],1070)
        d.blue.return_value=False
        self.assertIsNone(d.rookie_target(3))

    def test_simulation_button_does_not_match_explanatory_sentence(self):
        d=Daily.__new__(Daily)
        d.items=[{'text':'可获得奖励时，快速模拟将跳过战斗立即完成','box':[434,1502,556,28]},
                 {'text':'快速模拟','box':[742,1620,177,50]}]
        self.assertEqual(d.find('^快速模拟$',(550,1510,430,210))['box'],[742,1620,177,50])

    def test_recovery_closes_stage_sheet_before_using_home(self):
        d=Daily.__new__(Daily); d.items=[{'text':'关卡信息','box':[720,1090,180,50]},
            {'text':'进入战斗','box':[740,1730,180,60]}]
        d.dismiss_startup_popups=Mock();d.lobby=Mock(side_effect=[False,True])
        d.tap=Mock();d.wait=Mock()
        d.scan=lambda:setattr(d,'items',[{'text':'返回','box':[70,1790,150,70]}])
        d.home()
        self.assertEqual(d.tap.call_args_list,[unittest.mock.call(1055,1000,2),
                                              unittest.mock.call(295,1810,5)])

    def test_shared_interception_result_closes_before_next_page(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock());d.tap=Mock()
        popup=[{'text':'总伤害','box':[55,740,103,42]},
               {'text':'阶段','box':[43,922,82,46]},
               {'text':'点击任意处进行下一步','box':[391,1676,297,34]}]
        page=[{'text':'进入战斗','box':[700,1760,200,60]}]
        frames=iter([popup,page]);d.scan_raw=lambda:setattr(d,'items',next(frames))
        self.assertEqual(d.scan(),page)
        d.tap.assert_called_once_with(539.5,1693,delay=2)
        self.assertTrue(d.reward_dismissed)
    def test_shared_reward_handler_clears_layers_and_rescans(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock());d.tap=Mock()
        popup=[{'text':'奖励','box':[448,692,179,98]},
               {'text':'点击领取奖励','box':[442,1210,197,42]}]
        page=[{'text':'普通商店','box':[200,700,200,60]}]
        frames=iter([popup,popup,page])
        d.scan_raw=lambda:setattr(d,'items',next(frames))
        self.assertEqual(d.scan(),page)
        self.assertTrue(d.reward_dismissed)
        self.assertEqual(d.tap.call_count,2)

    def test_interception_colored_button_accepts_orange_rejects_gray(self):
        d=Daily.__new__(Daily);d.image=Image.new('RGB',(1080,1920),'black')
        button={'box':[485,1500,110,45]}
        d.image.paste((255,175,15),(400,1470,680,1580))
        self.assertTrue(d.colorful_button(button))
        d.image.paste((100,100,100),(400,1470,680,1580))
        self.assertFalse(d.colorful_button(button))

    def test_battle_preparation_starts_before_return_and_checks_result(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock());d.tap=Mock();d.wait=Mock()
        d.colorful_button=Mock(return_value=True);d.reward_dismissed=False
        prep=[{'text':'进入战斗','box':[740,1700,180,65]},
              {'text':'返回','box':[70,1800,100,45]}]
        result=[{'text':'返回','box':[470,1660,140,65]}]
        menu=[{'text':'异个体拦截战','box':[20,45,240,60]}]
        frames=iter([prep,result,menu])
        d.scan=lambda:setattr(d,'items',next(frames))
        self.assertTrue(d.battle('拦截战'))
        self.assertEqual(d.tap.call_args_list[0].args,(830,1732.5))
        self.assertEqual(d.tap.call_args_list[1].args,(540,1692.5))

    def dispatch_modal(self):
        d=Daily.__new__(Daily)
        d.items=[{'text':'全部派遣','box':[510,260,150,40]},
                 {'text':'执行全部派遣。','box':[70,365,180,30]},
                 {'text':'派遣','box':[602,520,56,30]},
                 {'text':'派遣','box':[602,780,56,30]},
                 {'text':'派遣','box':[680,1615,80,44]}]
        d.e=SimpleNamespace(log=Mock());d.tap=Mock();d.expect=Mock();d.blue=Mock(return_value=True)
        return d

    def test_dispatch_confirms_footer_not_repeated_column_labels(self):
        d=self.dispatch_modal()
        self.assertTrue(d.confirm_dispatch())
        d.tap.assert_called_once_with(720,1637)
        d.expect.assert_called_once_with('派遣公告栏',(90,180,700,230))

    def test_disabled_dispatch_closes_without_starting(self):
        d=self.dispatch_modal();d.blue.return_value=False
        self.assertTrue(d.confirm_dispatch())
        d.tap.assert_called_once_with(975,265)

    def test_other_dispatch_text_does_not_confirm_unrelated_page(self):
        d=self.dispatch_modal();d.items=d.items[2:]
        self.assertFalse(d.confirm_dispatch());d.tap.assert_not_called()

    def test_dispatch_can_resume_existing_confirmation_page(self):
        d=self.dispatch_modal();d.scan=Mock();d.home=Mock();d.dispatch=Mock()
        d.run('dispatch')
        self.assertEqual(d.tap.call_count,2)
        d.dispatch.assert_not_called();d.home.assert_called_once()

    def test_level_up_layers_clear_then_original_reward_remains(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock());d.tap=Mock()
        popup=[{'text':'LEVEL UP','box':[400,780,260,70]},
               {'text':'指挥官升级','box':[450,890,180,40]},
               {'text':'点击领取奖励','box':[420,1340,230,45]}]
        reward=[{'text':'奖励','box':[460,720,160,70]}]
        frames=iter([popup,popup,reward])
        d.scan_raw=lambda:setattr(d,'items',next(frames))
        self.assertEqual(d.scan(),reward)
        self.assertEqual(d.tap.call_count,2)

    def test_upgrade_without_dismiss_prompt_stops_without_click(self):
        d=Daily.__new__(Daily);d.e=SimpleNamespace(log=Mock());d.tap=Mock()
        d.items=[{'text':'LEVEL UP','box':[400,780,260,70]},
                 {'text':'指挥官升级','box':[450,890,180,40]}]
        d.scan_raw=Mock()
        with self.assertRaisesRegex(RuntimeError,'领取提示'):d.scan()
        d.tap.assert_not_called()

    def test_unrelated_popup_is_not_automatically_clicked(self):
        d=Daily.__new__(Daily);d.tap=Mock();d.scan_raw=Mock()
        d.items=[{'text':'确认购买','box':[400,780,260,70]}]
        self.assertEqual(d.scan(),d.items);d.tap.assert_not_called()

    def announcement(self):
        d=Daily.__new__(Daily)
        d.image=Image.new('RGB',(1080,1920),'black')
        d.image.paste(Image.open(ROOT/'tests/fixtures/announcement_header.png'),(42,137))
        d.items=[{'text':'公告','box':[540,185,75,40]},
                 {'text':'活动公告','box':[240,307,145,40]},
                 {'text':'系统公告','box':[700,307,145,40]}]
        d.e=SimpleNamespace(log=Mock());d.scan=Mock();d.tap=Mock();d.lobby=Mock(return_value=True);d.wait=Mock()
        return d

    def test_actual_announcement_header_closes_before_confirming_lobby(self):
        d=self.announcement()
        close=d.announcement_close()
        self.assertIsNotNone(close)
        self.assertLess(abs(close[0]-981),7)
        self.assertLess(abs(close[1]-196),7)
        d.announcement_close=Mock(side_effect=[close,None,None])
        self.assertTrue(d.dismiss_startup_popups())
        d.tap.assert_called_once_with(*close,delay=2.5)
        self.assertEqual(d.lobby.call_count,2)

    def test_missing_cross_or_other_notice_text_never_clicked(self):
        d=self.announcement();d.image.paste((0,120,240),(950,165,1010,225))
        self.assertIsNone(d.announcement_close())
        self.assertFalse(d.dismiss_startup_popups());d.tap.assert_not_called()
        d=self.announcement();d.items[0]['text']='活动通知'
        self.assertIsNone(d.announcement_close())

    def test_persistent_announcement_retries_are_bounded(self):
        d=self.announcement()
        with self.assertRaisesRegex(RuntimeError,'重试已达上限'):d.dismiss_startup_popups()
        self.assertEqual(d.tap.call_count,3)

    def test_remaining_unknown_popup_prevents_later_actions(self):
        d=self.announcement();d.announcement_close=Mock(side_effect=[(980,196),None,None,None])
        d.lobby.return_value=False
        with self.assertRaisesRegex(RuntimeError,'剩余弹窗'):d.dismiss_startup_popups()

    def test_daily_login_image_finds_close_and_enabled_claim(self):
        d=self.announcement();d.image=Image.new('RGB',(1080,1920),'black')
        d.image.paste(Image.open(ROOT/'tests/fixtures/login_close.png'),(900,150))
        d.image.paste(Image.open(ROOT/'tests/fixtures/login_claim.png'),(640,1760))
        d.items=[{'text':'根据累计登入天数，','box':[545,624,272,36]},
                 {'text':'可获得相应奖励','box':[802,626,202,34]},
                 {'text':'全部领取','box':[780,1780,135,50]}]
        claim,close=d.login_popup()
        self.assertLess(abs(close[0]-974),8)
        self.assertLess(abs(close[1]-203),8)
        self.assertTrue(d.colorful_button(claim))
        d.image.paste((100,100,100),(640,1760,1040,1880))
        self.assertFalse(d.colorful_button(claim))

    def test_unrelated_claim_all_and_white_rectangle_are_not_login(self):
        d=self.announcement();d.image=Image.new('RGB',(1080,1920),'white')
        d.items=[{'text':'全部领取','box':[780,1780,135,50]}]
        self.assertIsNone(d.login_popup())
        self.assertIsNone(d.close_cross(range(950,990,4),range(170,220,4)))

    def test_popup_chain_claims_confirms_closes_and_waits_for_next(self):
        d=self.announcement()
        frames=iter(['daily','reward','daily_done','transition','autumn','reward','autumn_done','lobby','lobby'])
        state={'page':None}
        d.scan=lambda:state.update(page=next(frames))
        d.announcement_close=lambda:None
        claim={'box':[780,1780,135,50]}
        d.login_popup=lambda:(claim,(974,203)) if state['page'] in ('daily','daily_done','autumn','autumn_done') else None
        d.colorful_button=lambda item:state['page'] in ('daily','autumn')
        d.supplies_close=lambda:None
        d.find=lambda expression,*args:True if state['page']=='reward' and expression in ('^奖励$','点击领取奖励') else None
        d.lobby=lambda:state['page'] in ('transition','lobby')
        d.click_text=Mock()
        self.assertTrue(d.dismiss_startup_popups())
        self.assertEqual(d.click_text.call_count,4)
        self.assertEqual(d.tap.call_count,2)
        d.wait.assert_any_call(2.5)

    def test_stop_during_popup_processing_does_not_continue(self):
        d=self.announcement();d.wait=Mock(side_effect=InterruptedError('停止'))
        with self.assertRaises(InterruptedError):d.dismiss_startup_popups()
        self.assertEqual(d.tap.call_count,1)

    def test_disabled_gray_buttons_are_not_enabled(self):
        if not all((ROOT/'captures'/name).is_file() for name in ('dispatch_validation.png','defense_new.png')):
            self.skipTest('Private account screenshots are not distributed')
        d=Daily.__new__(Daily)
        d.image=Image.open(ROOT/'captures/dispatch_validation.png').convert('RGB')
        self.assertFalse(d.blue(580,1615))
        self.assertFalse(d.blue(850,1615))
        d.image=Image.open(ROOT/'captures/defense_new.png').convert('RGB')
        self.assertTrue(d.blue(780,1640))

    def test_coordinates_scale_to_actual_device(self):
        import numpy as np
        d=Daily.__new__(Daily); d.size=(1080,1920)
        controller=Mock()
        controller.post_screencap.return_value.wait.return_value.get.return_value=np.zeros((1280,720,3))
        controller.post_click.return_value.wait.return_value.succeeded=True
        d.e=SimpleNamespace(controller=controller,stop_event=threading.Event())
        d.wait=lambda seconds=1: None
        d.tap(540,960)
        controller.post_click.assert_called_once_with(360,640)

    def test_stop_interrupts_delay(self):
        d=Daily.__new__(Daily)
        d.e=SimpleNamespace(stop_event=threading.Event())
        d.e.stop_event.set()
        with self.assertRaises(InterruptedError): d.wait(5)

    def test_free_cost_requires_price_region(self):
        d=Daily.__new__(Daily)
        d.items=[{'text':'每日首次免费','box':[300,1010,400,40]},
                 {'text':'50','box':[580,1450,70,40]}]
        self.assertIsNone(d.find('^0$|^免费$',(435,1420,255,90)))
        self.assertIsNotNone(d.find('^50$',(435,1420,255,90)))

if __name__=='__main__': unittest.main()
