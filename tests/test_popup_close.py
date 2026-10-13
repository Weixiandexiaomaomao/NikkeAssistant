import unittest
from types import SimpleNamespace
from unittest.mock import Mock
from PIL import Image, ImageDraw
from daily import Daily
from common_popups import with_common_popups


class PopupCloseTests(unittest.TestCase):
    def make_daily(self):
        d=Daily.__new__(Daily);d.items=[];d.reward_generation=0
        d.e=SimpleNamespace(log=Mock());d.tap=Mock()
        return d

    def test_close_instruction_without_offer_resumes_original_page(self):
        d=self.make_daily()
        frames=iter([[{'text':'点击关闭画面。','box':[400,1770,280,40]}],
                     [{'text':'方舟','box':[50,50,80,40]}]])
        d.scan_raw=lambda:setattr(d,'items',next(frames))
        self.assertEqual(d.scan()[0]['text'],'方舟')
        d.tap.assert_called_once_with(540,1790,delay=2)

    def test_close_text_is_detected_without_purchase_keywords(self):
        d=self.make_daily();d.items=[{'text':'关闭','box':[880,300,60,30]}]
        self.assertEqual(d.generic_popup_close(),(910,315))

    def test_tower_closed_status_is_not_a_popup_button(self):
        d=self.make_daily()
        d.items=[{'text':'无限之塔','box':[20,50,180,40]},
                 {'text':'关闭','box':[370,1040,100,40]},
                 {'text':'目前无法进入','box':[340,1630,180,40]}]
        self.assertIsNone(d.generic_popup_close())
        self.assertIsNone(d.generic_popup_close(dismiss_navigation=True))

    def test_white_x_on_blue_header_and_plain_background_rejection(self):
        d=self.make_daily();d.image=Image.new('RGB',(1080,1920),'black')
        draw=ImageDraw.Draw(d.image);draw.rectangle((100,300,1020,400),fill=(0,150,245))
        draw.line((940,330,972,362),fill='white',width=3)
        draw.line((940,362,972,330),fill='white',width=3)
        hit=d.generic_popup_close();self.assertIsNotNone(hit)
        self.assertLess(abs(hit[0]-956),4);self.assertLess(abs(hit[1]-346),4)
        d.image=Image.new('RGB',(1080,1920),'white')
        self.assertIsNone(d.generic_popup_close())

    def test_task_confirmation_keeps_its_own_handler(self):
        d=self.make_daily();d.items=[{'text':'取消','box':[150,1000,80,30]},
                                   {'text':'关闭','box':[900,300,60,30]}]
        self.assertIsNone(d.generic_popup_close())

    def test_task_destination_window_is_not_dismissed_as_a_popup(self):
        d=self.make_daily();d.items=[{'text':'邮箱','box':[430,230,150,50]}]
        d.image=Image.new('RGB',(1080,1920),'black');d.close_cross=Mock()
        self.assertIsNone(d.generic_popup_close());d.close_cross.assert_not_called()

    def test_stage_sheet_stays_open_for_battle_handler(self):
        d=self.make_daily();d.items=[{'text':'关卡信息','box':[430,640,150,50]}]
        d.image=Image.new('RGB',(1080,1920),'black');d.close_cross=Mock()
        self.assertIsNone(d.generic_popup_close());d.close_cross.assert_not_called()

    def test_startup_closes_pass_panel_with_non_blue_x(self):
        d=self.make_daily();d.items=[{'text':'任务','box':[700,600,100,50]}]
        d.image=Image.new('RGB',(1080,1920),'black')
        draw=ImageDraw.Draw(d.image);draw.rectangle((900,90,1030,200),fill=(150,180,190))
        draw.line((960,116,992,148),fill='white',width=3)
        draw.line((960,148,992,116),fill='white',width=3)
        self.assertIsNone(d.generic_popup_close())
        self.assertIsNotNone(d.generic_popup_close(dismiss_navigation=True))
        d.items.append({'text':'购买PASS','box':[740,480,210,60]})
        d.active_handler='rookie'
        self.assertIsNotNone(d.generic_popup_close())
        d.active_handler='missions'
        self.assertIsNone(d.generic_popup_close())

    def test_native_flow_returns_to_interrupted_node(self):
        graph=with_common_popups({'Entry':{'next':['Claim']},'Claim':{'next':['Done']},'Done':{}})
        self.assertEqual(graph['Claim']['next'][:2],['[JumpBack]CommonCloseConfirmDismiss','[JumpBack]CommonTextCloseDismiss'])

    def test_confirm_closure_before_dimmed_footer_then_resume(self):
        d=self.make_daily()
        frames=iter([[{'text':'关闭窗口后，商品会移至限定礼包商店，过期后将无法购买。','box':[130,850,800,40]},
                      {'text':'确认','box':[730,1170,100,45]},
                      {'text':'取消','box':[310,1170,100,45]},
                      {'text':'点击关闭画面。','box':[400,1770,280,40]}],
                     [{'text':'方舟','box':[50,50,80,40]}]])
        d.scan_raw=lambda:setattr(d,'items',next(frames))
        self.assertEqual(d.scan()[0]['text'],'方舟')
        d.tap.assert_called_once_with(780,1192.5,delay=2)
