import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from daily import Daily

def item(text,x,y,w=100,h=35):return {'text':text,'box':[x,y,w,h]}

class ArenaChecks(unittest.TestCase):
    def daily(self,items):
        d=Daily.__new__(Daily);d.items=items;d.e=SimpleNamespace(log=Mock())
        d.wait=Mock();d.tap=Mock();d.expect=Mock();d.scan=Mock()
        return d

    def test_support_selects_larger_share_on_either_side(self):
        for left,right,side in ((16.51,83.49,1),(72.30,27.70,0)):
            d=self.daily([item(f'{left:.2f}%',150,872),item(f'{right:.2f}%',825,874)])
            self.assertEqual(d.cheer_choice()[0],side)

    def test_support_rejects_missing_or_inconsistent_percentages(self):
        for entries in ([item('83.49%',825,874)],
                        [item('16.51%',150,872),item('3.49%',825,874)],
                        [item('116.51%',150,872),item('83.49%',825,874)]):
            self.assertIsNone(self.daily(entries).cheer_choice())

    def test_selecting_is_not_submitting_and_submission_needs_cheer_on_bracket(self):
        d=self.daily([item('应援现状',450,860),item('选择后仍可变更应援对象。',370,1120),
                      item('16.51%',150,872),item('83.49%',825,874),item('选择中',730,954)])
        d.click_text=Mock(return_value=True)
        d.scan.side_effect=lambda:setattr(d,'items',[item('CHEER',357,1168)])
        d.submit_cheer()
        d.click_text.assert_called_once_with('^应援$',(560,1550,460,190),blue=True)
        self.assertIn('提交成功',d.e.log.call_args[0][0])

    def test_paid_special_challenge_is_not_started_without_free_badge(self):
        d=self.daily([item('进入战斗',843,1176),item('进入战斗',843,1404),item('进入战斗',843,1628)])
        d.options={};d.ark=Mock();d.special_free_count=Mock(return_value=2)
        d.click_text=Mock(return_value=True);d.wait_rookie_list=Mock()
        with self.assertRaisesRegex(RuntimeError,'没有免费标记'):d.special_arena()
        d.tap.assert_not_called()

    def test_special_zero_daily_count_finishes_without_entering(self):
        d=self.daily([item('每日免费次数0/2',802,918,190)])
        d.options={};d.ark=Mock();d.click_text=Mock()
        d.special_arena()
        d.click_text.assert_not_called();d.tap.assert_not_called()

    def test_special_challenge_requires_exactly_one_count_decrement(self):
        d=self.daily([item('进入战斗',843,1176),item('进入战斗',843,1404),item('进入战斗',843,1628),
                      item('免费',877,1572)])
        d.options={};d.ark=Mock();d.special_free_count=Mock(side_effect=[2,2])
        d.click_text=Mock(return_value=True);d.wait_rookie_list=Mock();d.blue=Mock(return_value=True)
        d.battle=Mock(return_value=True)
        with self.assertRaisesRegex(RuntimeError,'免费次数未减少'):d.special_arena()
        d.battle.assert_called_once()

    def test_general_popup_guard_preserves_special_preparation(self):
        d=self.daily([item('快速战斗',200,1510),item('进入战斗',650,1580)])
        d.active_handler='special_arena'
        self.assertIsNone(d.generic_popup_close())

    def test_special_win_with_one_defeat_round_still_settles(self):
        d=self.daily([]);d.reward_dismissed=False
        frames=iter([[item('SPECIAL ARENA',430,120,250),item('WIN',300,220),
                      item('DEFEAT',750,600),item('点击进行下一步',440,1770,220)],
                     [item('特殊竞技场',25,56,150)]])
        d.scan.side_effect=lambda:setattr(d,'items',next(frames))
        self.assertTrue(d.battle('^特殊竞技场$',allow_defeat=True))
        d.tap.assert_called_once_with(550,1787.5)

    def test_general_popup_guard_preserves_champion_selection(self):
        d=self.daily([item('应援现状',450,860)])
        d.active_handler='champion'
        self.assertIsNone(d.generic_popup_close())

    def test_champion_existing_support_does_not_submit_again(self):
        d=self.daily([item('应援',510,1418),item('CHEER',357,1168)])
        d.ark=Mock();d.click_text=Mock(return_value=True);d.submit_cheer=Mock()
        d.champion()
        d.submit_cheer.assert_not_called()

    def test_old_support_marks_on_other_rounds_do_not_skip_current_match(self):
        d=self.daily([item('应援',510,1418),item('CHEER',357,1458)])
        d.ark=Mock();d.click_text=Mock(return_value=True);d.submit_cheer=Mock()
        d.champion()
        d.submit_cheer.assert_called_once()

    def test_special_free_count_is_checked_after_each_settlement(self):
        d=self.daily([item('进入战斗',843,1176),item('进入战斗',843,1404),item('进入战斗',843,1628),
                      item('免费',877,1572)])
        d.options={};d.ark=Mock();d.special_free_count=Mock(side_effect=[2,1,0])
        d.click_text=Mock(return_value=True);d.wait_rookie_list=Mock();d.blue=Mock(return_value=True)
        d.battle=Mock(return_value=True)
        d.special_arena()
        self.assertEqual(d.battle.call_count,2)
        self.assertEqual(d.special_free_count.call_count,3)

if __name__=='__main__':unittest.main()
