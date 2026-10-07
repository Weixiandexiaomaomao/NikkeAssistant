"""国服日常：离线中文 OCR、页面检查、免费操作和有界循环。"""
import io
import json
import re
import time
import numpy as np
from PIL import Image
from maa.resource import Resource
from maa.tasker import Tasker
from maa.pipeline import JOCR
from portable import ROOT


class Daily:
    def __init__(self, engine):
        self.e = engine
        self.r = Resource()
        if not self.r.post_bundle(ROOT / 'resource').wait().succeeded:
            raise RuntimeError('中文识别资源加载失败')
        self.t = Tasker()
        self.t.bind(self.r, engine.controller)
        engine.tasker = self.t
        self.options = engine.options
        self.items = []

    def wait(self, seconds=1):
        if self.e.stop_event.wait(seconds):
            raise InterruptedError('用户停止')

    def scan(self):
        self.reward_dismissed = False
        self.acquire_dismissed = False
        for attempt in range(7):
            self.scan_raw()
            promotion=self.promotion_close()
            if promotion:
                if attempt==6:raise RuntimeError('礼包推销弹窗关闭重试已达上限')
                self.e.log('统一关闭礼包推销弹窗，继续当前任务')
                x,y,w,h=promotion['box'];self.tap(x+w/2,y+h/2,delay=2)
                continue
            reveal_skip=self.find(r'^(?:[>》»\s]*)(?:跳过|SKIP)$',(800,0,280,160))
            reveal=(reveal_skip and self.find(r'^(?:TETRA|ELYSION|MISSILIS|PILGRIM|ABNORMAL)$',(0,0,650,400))
                    and self.find(r'^(?:SSR|SR|R)$',(750,1350,330,300))
                    and self.find('首次得',(600,1650,480,200)))
            if reveal:
                if attempt==6:
                    raise RuntimeError('获得角色展示页跳过重试已达上限')
                self.e.log('统一跳过获得角色展示，重新识别当前页面')
                x,y,w,h=reveal_skip['box']
                self.tap(x+w/2,y+h/2,delay=2)
                continue
            acquire_confirm=self.find('^确认$',(100,1550,880,320))
            if (self.find('RECRUITMENT.*RESULT',(0,0,650,420)) and acquire_confirm):
                if attempt==6:
                    raise RuntimeError('角色获取结果确认重试已达上限')
                self.e.log('统一确认角色获取结果，重新识别当前页面')
                x,y,w,h=acquire_confirm['box']
                self.tap(x+w/2,y+h/2,delay=2)
                self.acquire_dismissed=True
                continue
            reward=self.find('^奖励$',(350,650,400,250))
            claim=self.find('点击领取奖励',(150,1050,850,600))
            result_prompt=self.find('点击任意处进行下一步',(200,1500,800,270))
            result_page=(result_prompt and self.find('总伤害',(0,700,1080,250))
                         and self.find('阶段',(0,900,250,220)))
            if (reward and claim) or result_page:
                if attempt==6:
                    raise RuntimeError('奖励弹窗关闭重试已达上限')
                self.e.log('统一关闭奖励弹窗，重新识别当前页面')
                x,y,w,h=(claim if reward and claim else result_prompt)['box']
                self.tap(x+w/2,y+h/2,delay=2)
                self.reward_dismissed=True
                continue
            if not (self.find('LEVEL.*UP',(300,700,500,220))
                    and self.find('指挥官升级',(350,800,400,200))):
                return self.items
            prompt=self.find('点击领取奖励',(150,1200,850,450))
            if not prompt:
                raise RuntimeError('升级弹窗未识别到领取提示')
            if attempt>=3:
                raise RuntimeError('升级弹窗关闭重试已达上限')
            self.e.log('关闭指挥官升级奖励，继续当前任务')
            x,y,w,h=prompt['box']
            self.tap(x+w/2,y+h/2,delay=1.5)

    def promotion_close(self):
        close=self.find(r'^点击(?:.*)关闭(?:画面|页面)?[。.]?$',(150,1650,850,250))
        offer=self.find('礼包.*购买|礼包中.*选择',(0,750,1080,420))
        return close if close and offer else None

    def scan_raw(self):
        self.wait(.05)
        raw = Image.open(io.BytesIO(self.e.screenshot())).convert('RGB')
        if abs(raw.width / raw.height - 9 / 16) > .01:
            raise RuntimeError('日常任务要求竖屏 9:16')
        self.size = raw.size
        self.image = raw.resize((1080, 1920))
        job = self.t.post_recognition('OCR', JOCR(expected=['.*'], roi=[0, 0, 1080, 1920],
                                     threshold=.55), np.asarray(self.image)[:, :, ::-1].copy()).wait()
        result = job.get()
        self.items = [item for node in result.nodes if node.recognition
                      for item in node.recognition.raw_detail.get('filtered', [])] if result else []
        return self.items

    def find(self, expression, roi=(0, 0, 1080, 1920)):
        x, y, w, h = roi
        return next((item for item in self.items if re.search(expression, item['text'])
                     and x <= item['box'][0] + item['box'][2] / 2 <= x + w
                     and y <= item['box'][1] + item['box'][3] / 2 <= y + h), None)

    def number(self, roi):
        x,y,w,h=roi
        if roi == (144, 885, 49, 55):
            reference=Image.open(ROOT/'resource/image/cn/arena_zero.png').convert('L')
            patch=self.image.crop((x,y,x+w,y+h)).convert('L')
            if np.mean(np.abs(np.asarray(patch,dtype=float)-np.asarray(reference,dtype=float))) < 8:
                return 0
        crop=self.image.crop((x,y,x+w,y+h)).resize((w*3,h*3))
        job=self.t.post_recognition('OCR', JOCR(expected=['.*'],only_rec=True,threshold=.7),
                                   np.asarray(crop)[:,:,::-1].copy()).wait()
        result=job.get()
        found=[item.text.strip() for node in result.nodes if node.recognition
               for item in node.recognition.filtered_results] if result else []
        return int(found[0]) if found and re.fullmatch('[0-9]+', found[0]) else None

    def tap(self, x, y, delay=1.2, hold_ms=0):
        self.wait(.05)
        # Controller clicks use its scaled screenshot size, rather than OCR's
        # 1080 x 1920 reference size. Maa converts these back to device pixels.
        frame=self.e.controller.post_screencap().wait().get()
        if frame is None:
            raise RuntimeError('触控校准截图失败')
        px=round(x*frame.shape[1]/1080);py=round(y*frame.shape[0]/1920)
        job=(self.e.controller.post_swipe(px,py,px,py,hold_ms) if hold_ms
             else self.e.controller.post_click(px,py))
        if not job.wait().succeeded:
            raise RuntimeError('触控失败')
        self.wait(delay)

    def zero_price(self, roi):
        """Recognize only the current-price glyph, excluding crossed-out prices."""
        x,y,w,h=roi
        crop=self.image.crop((x,y,x+w,y+h)).resize((w*4,h*4))
        result=self.t.post_recognition('OCR',JOCR(expected=['^0$'],only_rec=True,threshold=.3),
                         np.asarray(crop)[:,:,::-1].copy()).wait().get()
        return bool(result and any(item.text.strip()=='0'
                    for node in result.nodes if node.recognition
                    for item in node.recognition.filtered_results))

    def click_text(self, expression, roi=(0, 0, 1080, 1920), blue=False):
        item = self.find(expression, roi)
        if not item:
            return False
        x, y, w, h = item['box']
        if blue and not self.blue(x + w / 2, y + h / 2):
            return False
        self.e.log('识别操作：' + item['text'])
        self.tap(x + w / 2, y + h / 2)
        return True

    def blue(self, x, y):
        pixels = np.asarray(self.image.crop((max(0, int(x)-90), max(0, int(y)-28),
                                             min(1080, int(x)+90), min(1920, int(y)+28))))
        return bool(np.mean((pixels[:, :, 2] > 150) & (pixels[:, :, 1] > 90)
                            & (pixels[:, :, 0] < 100)) > .18)

    def expect(self, expression, roi=(0, 0, 1080, 1920), timeout=25):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.scan()
            if self.find(expression, roi):
                return
            self.wait(1)
        raise RuntimeError('未识别到页面：' + expression)

    def lobby(self):
        self.scan()
        # 模态弹窗会将底部大厅标记变暗，需同时检查文字与亮度。
        crop = np.asarray(self.image.crop((480, 1838, 596, 1890)))
        return bool(self.find('^大厅$', (450, 1820, 180, 100))
                    and np.mean(np.min(crop, axis=2) > 190) > .025)

    def announcement_close(self):
        """Only the observed blue announcement dialog, never an arbitrary X."""
        title = self.find('^公告$', (380,140,320,130))
        if not (title and self.find('活动公告',(100,270,430,120))
                and self.find('系统公告',(580,270,430,120))):
            return None
        y = round(title['box'][1]+title['box'][3]/2)
        if not self.blue(800,y):
            return None
        return self.close_cross(range(976,987,2),range(y-10,y+11,2))

    def maintenance_close(self):
        title=self.find('^公告$',(380,300,400,300))
        if not (title and self.find('亲爱的指挥官',(80,450,700,220))
                and self.find('一周内不再显示',(80,1380,850,200))):
            return None
        y=round(title['box'][1]+title['box'][3]/2)
        if not self.blue(800,y):return None
        return self.close_cross(range(944,975,2),range(y-14,y+15,2))

    def close_cross(self, xs, ys):
        """A white cross with two strokes, rejecting plain white areas."""
        # OCR text and the icon can differ slightly in vertical alignment.
        for cy in ys:
            for x in xs:
                patch = np.asarray(self.image.crop((x-23,cy-23,x+24,cy+24)))
                white = np.min(patch,axis=2)>215
                if white.mean() > .42:
                    continue
                strokes = []
                for direction in (1,-1):
                    hits = [white[23+offset-2:23+offset+3,
                                  23+direction*offset-2:23+direction*offset+3].any()
                            for offset in range(-16,17)]
                    strokes.append(np.mean(hits))
                if min(strokes) >= .85:
                    return x,cy
        return None

    def login_popup(self):
        # Shared text observed on DAILY LOGIN and Swing into Autumn.
        if not (self.find('累[计积].*登[入录].*天数',(100,500,950,250))
                and self.find('获[得取].*奖励',(100,500,950,250))):
            return None
        claim = self.find('^全部领取$',(500,1450,580,430))
        close = self.close_cross(range(930,1011,4),range(160,281,4))
        return (claim,close) if claim and close else None

    def colorful_button(self,item):
        x,y,w,h=item['box']
        pixels=np.asarray(self.image.crop((int(x+w/2)-70,int(y+h/2)-15,
                                           int(x+w/2)+70,int(y+h/2)+15)),dtype=np.int16)
        return bool(np.mean((pixels.max(2)-pixels.min(2)>60)&(pixels.max(2)>140))>.18)

    def supplies_close(self):
        if (self.find('获得18次物资|获取18次物资',(100,450,950,150))
                and self.find('获取3份物资',(500,1680,550,160))
                and self.find('爆发能量',(300,1470,500,130))):
            return self.close_cross(range(960,1011,2),range(165,221,2))
        return None

    def dismiss_startup_popups(self):
        handled = False
        idle = 0
        unconfirmed = 0
        last_key = None
        repeats = 0
        deadline = time.monotonic()+120
        for _ in range(24):
            if time.monotonic()>=deadline:
                raise RuntimeError('登录弹窗处理超时，请手动检查')
            self.scan()
            close = self.announcement_close()
            key = '公告'
            action = None
            popup = None if close else self.login_popup()
            if close:
                action=lambda:self.tap(*close,delay=2.5)
            elif self.find('^奖励$',(350,650,400,250)) and self.find('点击领取奖励',(100,1050,900,500)):
                key='奖励确认'
                action=lambda:self.click_text('点击领取奖励',(100,1050,900,500))
            elif popup:
                claim,close=popup
                key=f'签到{round(claim["box"][1]/50)}'
                if self.colorful_button(claim):
                    key+='领取'
                    action=lambda:self.click_text('^全部领取$',(500,1450,580,430))
                else:
                    key+='关闭'
                    action=lambda:self.tap(*close,delay=2.5)
            elif (close := self.supplies_close()):
                key='物资展示关闭'
                action=lambda:self.tap(*close,delay=2.5)
            if action:
                repeats = repeats+1 if key==last_key else 1
                last_key = key
                if repeats>3:
                    raise RuntimeError(key+'重试已达上限，请手动检查弹窗')
                self.e.log('登录弹窗：'+key)
                action()
                self.wait(1)
                handled=True;idle=0;unconfirmed=0
                continue
            if not handled:
                return False
            # Subsequent login popups appear after a brief lobby transition.
            if self.lobby():
                idle+=1;unconfirmed=0
                if idle>=2:return True
            else:
                idle=0;unconfirmed+=1
                if unconfirmed>=3:
                    raise RuntimeError('未确认大厅，请关闭剩余弹窗')
            self.wait(2.5)
        raise RuntimeError('登录弹窗数量超过保护上限，请手动检查')

    def home(self):
        self.dismiss_startup_popups()
        if self.lobby():
            return
        if self.find('请选择增益效果',(250,300,600,160)):
            self.e.log('恢复未完成的模拟室结算流程')
            self.complete_simulation()
            self.scan()
        self.finish_simulation_result()
        if self.finish_recruit_result():
            self.scan()
        if self.find('^花絮$',(350,130,400,150)) and self.find('可以查看妮姬的花絮',(50,280,700,140)):
            self.tap(980,215,2);self.scan()
        if self.find('查看花絮',(750,900,330,500)) and self.find('咨询次数',(500,1500,500,200)):
            self.click_text('^返回$',(0,1720,280,180));self.scan()
        if self.find('防御前哨基地',(80,180,660,180)):
            if self.find('^进行歼灭$',(400,1400,600,140)):
                if not self.click_text('^取消$',(100,1400,300,140)):
                    raise RuntimeError('未确认歼灭窗口取消按钮')
                self.scan()
            self.tap(970,235)
            self.scan()
        if (self.find('是否更新商品',(250,650,600,240))
                and self.find('重置购买次数',(250,740,650,160))):
            self.click_text('^取消$',(150,1130,350,150))
            self.expect('普通商店',(150,660,400,180))
        if (self.find('购买道具',(320,250,440,180))
                and self.find('消耗资金',(150,1280,360,180))):
            self.click_text('^取消$',(150,1540,400,180))
            self.expect('普通商店',(150,660,400,180))
        if self.pass_page():
            self.tap(975,132,3)
            self.scan()
        if self.find('消耗次数',(0,1480,500,160)) and self.find('批量咨询',(720,1580,350,220)):
            self.click_text('^关闭$',(720,1740,350,160))
            self.expect('^返回$',(0,1750,250,130),timeout=20)
        # Tower/stage detail sheets cover the navigation bar. Close only a
        # positively identified stage sheet before looking for Home.
        if self.find('关卡信息') and self.find('进入战斗',(400,1600,680,320)):
            self.tap(1055,1000,2)
            self.scan()
        if self.find('选择地区',(300,350,500,200)) and self.find('^模拟室$',(350,100,500,230)):
            self.tap(978,149,2)
            self.scan()
        navigations=0
        if self.find('返回', (0, 1750, 250, 130)):
            self.tap(295, 1810, 5)
            navigations=1
        elif self.find('^妮姬$', (0, 0, 240, 150)):
            self.tap(540, 1800, 5)
            navigations=1
        elif self.find('^招募队员$',(0,0,320,180)) and self.find('^大厅$',(450,1820,180,100)):
            self.tap(540,1800,5)
            navigations=1
        # A result may still be fading when Home is first inspected. Retry only
        # after the visible navigation bar returns, rather than waiting idle.
        deadline=time.monotonic()+35
        while time.monotonic()<deadline:
            if self.lobby():
                return
            if (navigations<3 and self.find('^返回$',(0,1750,250,130))
                    and self.blue(295,1810)):
                self.tap(295,1810,5)
                navigations+=1
            else:
                self.wait(1)
        raise RuntimeError('未确认大厅，请手动关闭弹窗再运行')

    def reward(self):
        # Rewards fade in after the server response; do not inspect only once mid-animation.
        self.wait(2)
        self.scan()
        if self.reward_dismissed:
            return True
        if self.click_text('点击领取奖励|点击.*继续', (160, 650, 800, 980)):
            self.scan()
            return True
        return False

    def ark(self, card, page):
        self.home()
        if not self.click_text('^方舟$',(650,1150,420,280)):
            raise RuntimeError('大厅方舟入口未识别')
        self.wait(3)
        # A lobby navigation tap can be dropped during its return animation.
        self.scan()
        if self.find('^大厅$',(450,1820,180,100)) and self.find('^方舟$',(650,1150,420,280)):
            self.click_text('^方舟$',(650,1150,420,280))
        self.expect('^方舟$', (0, 0, 220, 130))
        self.expect('模拟室|拦截战', (0, 500, 600, 1250))
        self.tap(*card, delay=4)
        self.expect(page, (0, 0, 300, 150))

    def run(self, kind):
        if kind == 'dispatch':
            self.scan()
            if self.confirm_dispatch():
                self.tap(985,260)
                self.home()
                return
        if kind in ('event_daily','event_wisdom_daily'):
            from event_flow import EventActivities
            return EventActivities(self,layout='wisdom' if kind=='event_wisdom_daily' else 'sphere').run()
        if kind == 'event_push':
            from event_flow import EventPush
            outcome=EventPush(self).run()
            if outcome=='skipped':
                self.home()
                self.e.log('已确认返回大厅')
            return outcome
        self.home()
        outcome=getattr(self, kind)()
        self.home()
        self.e.log('已确认返回大厅')
        return outcome

    def missions(self):
        self.tap(984, 470)
        self.expect('^任务$', (400, 130, 280, 150))
        for x, tab, key in ((204, '每日','daily'), (445, '每周','weekly'), (680, '主线','main'), (900, '成就','achievement')):
            if not self.options.get('mission_'+key,True):
                continue
            self.tap(x, 350)
            self.expect(tab, (80, 290, 930, 130))
            for _ in range(12):
                self.scan()
                if not self.click_text('全部领取', (650, 1640, 380, 150), blue=True):
                    break
                self.reward()
            else:
                raise RuntimeError('任务奖励领取超过上限')
        self.tap(990, 132)
        if not self.lobby():
            raise RuntimeError('关闭任务窗口后未确认大厅')
        if self.options.get('mission_pass',True):
            self.pass_rewards()

    def pass_page(self):
        return (self.find('^任务$',(550,540,460,140))
                and self.find('购买PASS',(700,450,330,130))
                and self.find('^全部领取$',(250,1730,580,140)))

    def pass_rewards(self):
        self.scan()
        banner=self.find('MISSION.*PASS',(620,230,460,220))
        if not banner:
            self.e.log('大厅未显示 MISSION PASS 入口，跳过 PASS')
            return
        x,y,w,h=banner['box']
        self.tap(x+w/2,y+h/2,3)
        self.expect('购买PASS',(700,450,330,130),timeout=20)
        if not self.pass_page():
            raise RuntimeError('MISSION PASS 页签未确认')
        # The CN pass panel has three carousel pages; bound traversal to one cycle.
        for page in range(3):
            self.e.log(f'检查 PASS 第{page+1}页')
            for x,tab in ((780,'任务'),(280,'奖励')):
                self.tap(x,620,2)
                self.expect('^'+tab+'$',(80,540,930,140))
                for _ in range(12):
                    self.scan()
                    if not self.pass_page():
                        self.expect('购买PASS',(700,450,330,130),timeout=15)
                        if not self.pass_page():
                            raise RuntimeError('PASS 领取后未确认页面')
                    if not self.click_text('^全部领取$',(250,1730,580,140),blue=True):
                        self.e.log('PASS '+tab+'暂无可领取内容')
                        break
                    self.e.log('领取 PASS '+tab)
                    self.reward()
                else:
                    raise RuntimeError('PASS 领取重试达到上限')
            if page<2:
                self.tap(1030,955,3)
                self.expect('购买PASS',(700,450,330,130),timeout=20)
        self.tap(975,132,3)
        if not self.lobby():
            raise RuntimeError('关闭 PASS 后未确认大厅')

    def confirm_dispatch(self):
        if not (self.find('^全部派遣$',(380,180,400,180))
                and self.find('执行全部派遣',(40,310,650,150))):
            return False
        button=self.find('^派\s*遣$',(550,1500,480,260))
        if not button:
            raise RuntimeError('全部派遣确认按钮未识别')
        x,y,w,h=button['box']
        if not self.blue(x+w/2,y+h/2):
            self.e.log('全部派遣按钮不可用，关闭后继续')
            self.tap(975,265)
        else:
            self.click_text('^派\s*遣$',(550,1500,480,260),blue=True)
            self.e.log('已确认全部派遣')
        self.expect('派遣公告栏',(90,180,700,230))
        return True

    def dispatch(self):
        self.tap(415, 1570)
        self.expect('派遣公告栏', (90, 180, 700, 230))
        for _ in range(3):
            self.scan()
            if not self.click_text('全部领取', (690, 1530, 340, 180), blue=True):
                break
            self.reward()
        self.scan()
        if self.click_text('全部派遣', (370, 1530, 330, 180), blue=True):
            self.scan()
            # 如出现角色选择，仅使用游戏提供的一键自动选择。
            if self.click_text('自动选择|自动编队'):
                self.scan()
            if not self.confirm_dispatch() and self.find('派遣公告栏', (90, 180, 700, 230)) is None:
                if not self.click_text('^派\s*遣$|^确认$',(550,1500,480,260), blue=True):
                    raise RuntimeError('派遣选择界面未识别，请手动完成')
                self.expect('派遣公告栏')
        self.scan()
        self.e.log('派遣检查完成；不重置目录、不花费刷新资源')
        self.tap(985, 260)

    def wipe_free_available(self):
        if self.find('^0$|^免费$', (435,1420,255,90)):
            return True
        button=self.find('^进行歼灭$',(400,1400,600,140))
        if not button or not self.find('每日首次免费',(250,980,600,100)):
            return False
        x,y,w,h=button['box']
        # The free variant has centered text and no currency/price on its left.
        # Require the underlying free-action notification as independent evidence.
        pixels=np.asarray(self.image.crop((510,1580,540,1615)))
        red=(pixels[:,:,0]>60)&(pixels[:,:,0]>pixels[:,:,1]*1.5)&(pixels[:,:,0]>pixels[:,:,2]*2)
        return (650<=x+w/2<=750 and self.blue(x+w/2,y+h/2)
                and np.count_nonzero(red)>20
                and not self.find(r'^\d+$|钻石|消耗',(435,1420,175,90)))

    def wipe(self):
        outcome=None
        self.tap(120, 1600)
        self.expect('防御前哨基地', (80, 180, 660, 180))
        self.tap(325, 1640)
        self.expect('进行歼灭', (400, 1400, 600, 140))
        # “每日首次免费”说明一直显示，不能用它判断免费；检查当前按钮价格。
        if self.wipe_free_available():
            if not self.click_text('^进行歼灭$', (400,1400,600,140), blue=True):
                raise RuntimeError('免费歼灭按钮状态变化')
            self.reward()
            self.scan()
            if self.wipe_free_available() or not self.find(r'^[1-9]\d*$',(435,1420,255,90)):
                raise RuntimeError('免费歼灭后未确认切换为付费价格，不重复点击')
            self.e.log('已领取免费歼灭奖励，核实下一次为付费价格')
            if self.find('进行歼灭', (400, 1400, 600, 140)):
                self.tap(250, 1470)
        else:
            self.e.log('免费歼灭已使用或价格未确认，跳过付费操作')
            self.tap(250, 1470)
            outcome='skipped'
        self.expect('防御前哨基地', (80, 180, 660, 180))
        self.tap(970, 235)
        return outcome

    def shop(self):
        self.scan()
        entry=self.find('^商店$',(0,1180,600,230))
        if not entry:
            raise RuntimeError('未识别大厅商店入口')
        x,y,w,h=entry['box']
        self.tap(x+w/2,y+h/2,4,hold_ms=100)
        self.expect('百货商店', (0, 0, 260, 150))
        self.expect('普通商店', (150, 660, 400, 180))
        self.buy_free_shop_item()
        self.scan()
        if not self.find('^免费$',(580,800,150,100)):
            self.e.log('普通商店免费刷新已用完')
            return
        self.open_free_shop_refresh()
        self.confirm_free_shop_refresh()
        self.wait_shop_refreshed()
        self.e.log('已核实免费刷新成功，再次购买零价商品')
        self.buy_free_shop_item()

    def open_free_shop_refresh(self):
        for attempt in range(3):
            self.scan()
            if self.find('是否更新商品',(250,650,600,240)):
                return
            badge=self.find('^免费$',(580,800,150,100))
            if not badge or not self.find('普通商店',(150,660,400,180)):
                raise RuntimeError('刷新入口状态变化，停止点击')
            if not self.find('距离商品更新还有',(180,820,460,100)):
                raise RuntimeError('未识别商品刷新栏，停止点击')
            # The refresh icon/free badge extends outside the responding button.
            # Its verified hit area is the middle of the refresh bar.
            self.e.log('点击免费刷新栏有效区域')
            self.tap(400,872,3,hold_ms=200)
        self.expect('是否更新商品',(250,650,600,240),timeout=10)

    def wait_shop_refreshed(self):
        deadline=time.monotonic()+20
        while time.monotonic()<deadline:
            self.scan()
            if (self.find('普通商店',(150,660,400,180))
                    and not self.find('是否更新商品',(250,650,600,240))
                    and not self.find('^免费$',(580,800,150,100))
                    and not self.find('售罄|售馨',(185,1040,290,240))):
                return
            self.wait(1)
        raise RuntimeError('刷新后未确认免费标记消失及商品补货')

    def confirm_free_shop_refresh(self):
        self.scan()
        if not (self.find('是否更新商品',(250,650,600,240))
                and self.find('重置购买次数',(250,740,650,160))
                and self.find('消耗资金',(350,950,250,150))
                and self.zero_price((620,1000,30,50))):
            self.click_text('^取消$',(150,1130,350,150))
            raise RuntimeError('刷新确认页未核实零价，已取消刷新')
        if not self.click_text('^确认$',(550,1130,450,150),blue=True):
            raise RuntimeError('免费刷新确认按钮未识别')

    def buy_free_shop_item(self):
        # First discounted item varies; the sale banner alone never authorizes purchase.
        if not self.find('售罄|售馨', (185, 1040, 290, 210)):
            if not self.find(r'100\s*[%％].*SALE', (185,1200,290,110)):
                raise RuntimeError('免费商品价格未识别，停止商店任务')
            self.tap(330, 1110)
            self.expect('购买道具',(320,250,440,180))
            if not (self.find('消耗资金',(150,1280,360,180))
                    and self.find(r'100\s*[%％]',(710,1280,200,190))
                    and self.zero_price((668,1348,40,65))
                    and self.zero_price((670,1350,30,60))):
                self.e.log('未确认零价格，取消本次购买')
                self.click_text('^取消$',(150,1540,400,180))
                raise RuntimeError('商品确认页未识别零价格，已取消购买')
            if not self.click_text('^购买$', (550,1540,400,180), blue=True):
                raise RuntimeError('商品确认按钮未识别')
            self.reward()
            self.expect('普通商店',(150,660,400,180))
            if not self.find('售罄|售馨', (185,1040,290,240)):
                raise RuntimeError('购买后未确认商品售罄，停止重复购买')
            self.e.log('已核实免费商品购买成功：第一格售罄')
        else:
            self.e.log('普通商店免费商品已领取')

    def pack_stock(self, roi):
        item=self.find(r'^剩余\s*[01]\s*[/／]\s*1$',roi)
        return int(re.search(r'([01])\s*[/／]',item['text'])[1]) if item else None

    def claim_free_pack(self, title, title_roi, stock_roi, price_roi):
        self.expect(title,title_roi,timeout=20)
        stock=self.pack_stock(stock_roi)
        if stock==0:
            self.e.log('免费礼包已领取：'+title.replace('^','').replace('$',''))
            return
        free=self.find('^免费$',price_roi)
        if stock!=1 or not free:
            raise RuntimeError('未确认礼包剩余1/1及免费价格，停止领取')
        x,y,w,h=free['box']
        self.tap(x+w/2,y+h/2,3)
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            self.scan()
            if self.find(title,title_roi) and self.pack_stock(stock_roi)==0:
                self.e.log('已核实免费礼包领取成功：'+title.replace('^','').replace('$',''))
                return
            self.wait(1)
        raise RuntimeError('礼包领取后未确认剩余0/1，不重复点击')

    def select_pack_tab(self, label, page='普通礼包', pattern=None):
        for attempt in range(6):
            self.scan()
            if self.click_text(pattern or '^'+label+'$',(0,490,1080,140)):
                self.wait(2)
                return
            if not self.find(page,(300,100,500,200)):
                raise RuntimeError('未确认'+page+'页面，停止切换')
            if attempt==5:
                raise RuntimeError('未找到礼包页签：'+label)
            frame=self.e.controller.post_screencap().wait().get()
            if frame is None:raise RuntimeError('礼包页签截图失败')
            sx=frame.shape[1]/1080;sy=frame.shape[0]/1920
            if not self.e.controller.post_swipe(round(960*sx),round(545*sy),
                    round(660*sx),round(545*sy),600).wait().succeeded:
                raise RuntimeError('礼包页签滑动失败')
            self.wait(2)

    def step_up_free_pack(self):
        self.expect('限时礼包',(300,100,500,200))
        self.expect('加强礼包',(300,610,550,160))
        for _ in range(4):
            self.scan()
            stages=sorted((item for item in self.items if
                re.fullmatch(r'阶段\s*\d+',item['text']) and 100<=item['box'][0]<=300
                and 860<=item['box'][1]<=1700),
                key=lambda item:int(re.search(r'\d+',item['text'])[0]))
            if not stages:raise RuntimeError('未识别 STEP UP 阶段')
            for stage in stages:
                y=stage['box'][1]
                stock_roi=(850,y-60,200,90)
                stock=self.pack_stock(stock_roi)
                if stock==0:continue
                if stock!=1:raise RuntimeError('未确认 STEP UP 阶段剩余次数')
                price_roi=(850,y+70,200,130)
                if not self.find('^免费$',price_roi):
                    self.e.log('STEP UP 下一阶段为付费阶段，免费领取检查结束')
                    return
                # Only the next unclaimed stage can be unlocked. Do not jump
                # ahead to free labels that require buying preceding stages.
                self.claim_free_pack('^'+stage['text']+'$',(100,y-25,300,90),stock_roi,price_roi)
                break
            else:
                self.e.log('STEP UP 当前免费阶段已领取')
                return
        raise RuntimeError('STEP UP 免费阶段领取达到保护上限')

    def shop_packs(self):
        if not self.click_text('^付费商店$',(0,1100,600,180)):
            raise RuntimeError('未识别大厅付费商店入口')
        self.expect('^付费商店$',(0,0,300,140))
        self.tap(225,425,3)
        self.expect('普通礼包',(300,100,500,200))
        for period in ('每日','每周','每月'):
            self.select_pack_tab(period)
            self.claim_free_pack('^'+period+'免费礼包$',(30,660,330,130),
                                 (30,950,330,160),(30,1140,330,140))
        self.tap(70,425,3)
        self.expect('限时礼包',(300,100,500,200))
        self.select_pack_tab('STEP UP礼包',page='限时礼包',pattern=r'STEP\s*UP.*礼包')
        self.step_up_free_pack()

    def simulation(self):
        self.ark((210, 1020), '^模拟室$')
        self.scan()
        self.simulation_reset_at=None
        for item in self.items:
            reset=re.search(r'距离重置.*?(\d+)\s*小时\s*(\d+)\s*分钟',item['text'])
            if reset:
                self.simulation_reset_at=time.time()+int(reset[1])*3600+int(reset[2])*60
                break
        state=ROOT/'runtime'/'simulation.json'
        try:
            recorded=json.loads(state.read_text(encoding='utf-8'))
        except (OSError,ValueError):
            recorded={}
        if recorded.get('serial')==self.e.serial and recorded.get('completed_until',0)>time.time():
            self.e.log('模拟室本轮已确认通关，不再点击开始模拟')
            return 'skipped'
        self.expect('开始模拟', (240, 1000, 620, 300),timeout=50)
        self.click_text('开始模拟', (240, 1000, 620, 300), blue=True)
        self.expect('^快速模拟$', (550, 1510, 430, 210))
        region=str(self.options.get('simulation_region','当前'))
        level=self.options.get('simulation_level','当前')
        if region in ('1','2','3','4','5'):
            self.tap([174,350,540,720,900][int(region)-1],600)
        if level in ('A','B','C'):
            self.tap({'A':230,'B':540,'C':850}[level],1000)
        self.scan()
        if self.find('已通关|重置模拟室后', (150, 1200, 790, 300)):
            self.e.log('模拟室今日已通关')
            self.record_simulation_completed()
            self.tap(978, 149)
            return
        # 游戏保留上次难度，快速模拟只在解锁的难度可用。
        quick = self.find('^快速模拟$', (550, 1510, 430, 210))
        if not quick or not self.colorful_button(quick):
            raise RuntimeError('当前难度未开放快速模拟')
        self.click_text('^快速模拟$', (550, 1510, 430, 210))
        self.scan()
        if self.find('确认|确定'):
            self.click_text('^确认$|^确定$', blue=True)
        self.complete_simulation()

    def complete_simulation(self):
        # The explanatory sentence also contains "快速模拟". Only click the
        # exact button, and require a real reward before reporting completion.
        finished=False
        deadline=time.monotonic()+60
        buffs=0
        while time.monotonic()<deadline:
            self.scan()
            if self.find('请选择增益效果'):
                if buffs>=3:
                    raise RuntimeError('增益选择超过3次，停止避免重复点击')
                if not self.click_text(r'^[+?？>》»\s]*跳过增益效果选择$',(200,1680,700,200)):
                    raise RuntimeError('未识别增益选择跳过按钮')
                buffs+=1
                continue
            start=self.find('^进入战斗$',(550,1600,520,300))
            if start and self.colorful_button(start):
                self.e.log('快速模拟后的最终节点仍需战斗，完成最后一战')
                self.click_text('^进入战斗$',(550,1600,520,300))
                if not self.battle('模拟室',limit=180):
                    raise RuntimeError('模拟室最终战斗失败')
                finished=True
                break
            if self.reward():
                finished=True
                break
            self.wait(1)
        if not finished:
            raise RuntimeError('快速模拟后未确认奖励结算，不标记完成')
        self.scan()
        if self.finish_simulation_result():
            return
        if self.find('^快速模拟$', (550, 1510, 430, 210)):
            self.tap(978, 149)
        self.expect('开始模拟', (240, 1000, 620, 300))

    def finish_simulation_result(self):
        confirmation=(self.find('模拟即将结束',(250,650,600,220))
                      and self.find('难度通关成功',(250,850,600,200)))
        if not confirmation and not (self.find('DIFFICULTY.*CLEAR',(80,400,950,230))
                and self.find('FINAL.*REWARD|已获得该区域的最终奖励',(250,570,600,270))):
            return False
        if not confirmation:
            if not self.click_text('^模拟结束$',(300,1280,500,170)):
                raise RuntimeError('模拟通关结算页未找到结束按钮')
            self.expect('模拟即将结束',(250,650,600,220),timeout=15)
        if not self.find('难度通关成功',(250,850,600,200)):
            raise RuntimeError('未确认模拟通关成功，停止结束操作')
        if not self.click_text('^确认$',(300,1130,500,150),blue=True):
            raise RuntimeError('模拟结束确认按钮未识别')
        self.e.log('已关闭模拟室最终通关结算')
        self.expect('^开始模拟$',(240,1000,620,300),timeout=25)
        self.record_simulation_completed()
        return True

    def record_simulation_completed(self):
        reset_at=getattr(self,'simulation_reset_at',None)
        if reset_at and reset_at>time.time():
            state=ROOT/'runtime'/'simulation.json'
            state.parent.mkdir(exist_ok=True)
            state.write_text(json.dumps({'serial':self.e.serial,'completed_until':reset_at}),encoding='utf-8')

    def arena_reward(self):
        self.ark((790, 1190), '^竞技场$')
        self.expect('特殊竞技场')
        self.tap(790, 1070, 4)
        self.expect('特殊竞技场', (0, 0, 320, 150))
        self.tap(540, 424)
        self.expect('竞技场信息', (300, 220, 500, 180))
        if self.click_text('^领取$', (560, 1640, 400, 160), blue=True):
            self.reward()
        else:
            self.tap(980, 320)

    def battle(self, return_page, limit=300, allow_defeat=False):
        deadline = time.monotonic() + limit
        entered = False
        settled = False
        arena_defeat = False
        while time.monotonic() < deadline:
            self.scan()
            if self.reward_dismissed:
                entered = settled = True
            if self.find('失败|战斗失败|DEFEAT'):
                if allow_defeat and self.find('ROOKIE.*ARENA',(200,450,700,300)):
                    if not arena_defeat:
                        self.e.log('竞技场本场落败，等待结算后继续剩余免费挑战')
                    arena_defeat = entered = True
                else:
                    self.click_text('返回|确认', (0, 1000, 1080, 850))
                    self.e.log('本次战斗失败，结束该任务')
                    return False
            if self.click_text('点击领取奖励|点击.*继续|点击.*下一步', (0, 650, 1080, 1120)):
                entered = True
                settled = True
                continue
            if entered and settled and self.find(return_page):
                return True
            start=self.find('战斗开始|进入战斗|开始战斗',(0,1000,1080,800))
            if start and self.colorful_button(start):
                self.click_text('战斗开始|进入战斗|开始战斗',(0,1000,1080,800))
                entered = True
                continue
            if entered and self.click_text('^返回$|^完成$', (0, 1500, 1080, 400)):
                entered = True
                settled = True
                continue
            self.wait(2)
        raise RuntimeError('战斗超时，请检查游戏是否开启自动射击和自动爆裂')

    def interception(self):
        self.ark((420, 1510), '拦截战')
        self.scan()
        if self.find(r'0\s*[/／]\s*3',(0,120,560,180)):
            self.e.log('拦截战次数已用完')
            return 'skipped'
        button=self.find('^挑战$',(260,1430,580,240))
        if not button or not self.colorful_button(button):
            raise RuntimeError('未识别可用挑战按钮')
        self.click_text('^挑战$',(260,1430,580,240))
        self.expect('每日快速战斗|快速战斗',(550,1500,520,240))
        for _ in range(max(1,min(3,int(self.options.get('interception_count',3))))):
            self.scan()
            if self.find(r'0\s*[/／]\s*3',(0,120,560,180)):
                self.e.log('拦截战次数已用完')
                return
            if self.find('^挑战$',(260,1430,580,240)):
                self.click_text('^挑战$',(260,1430,580,240))
                self.expect('快速战斗',(550,1500,520,240))
            count=self.find(r'[0-3]\s*[/／]\s*3',(550,1660,520,240))
            if not count:
                raise RuntimeError('未确认拦截剩余次数')
            before=int(re.search(r'([0-3])\s*[/／]\s*3',count['text'])[1])
            if before==0:
                self.e.log('拦截战次数已用完')
                return
            quick_pattern=r'^[》>»\s]*(?:每日|每周)?快速战斗$'
            button=self.find(quick_pattern, (550,1500,520,240))
            if not button or not self.colorful_button(button):
                start=self.find('^进入战斗$',(550,1660,520,240))
                if not start or not self.colorful_button(start):
                    raise RuntimeError('有剩余拦截次数，但快速战斗及进入战斗均未确认可用')
                self.e.log('快速战斗不可用，沿用当前队伍进入实际战斗')
                if not self.battle('^挑战$|快速战斗|剩余拦截次数'):
                    raise RuntimeError('拦截实际战斗未结算，剩余次数未完成')
            else:
                self.click_text(quick_pattern,(550,1500,520,240))
                self.scan()
                if self.find('快速战斗') and self.find('^确认$|^确定$',(250,1000,800,750)):
                    if self.find('购买|钻石|支付',(100,300,880,1250)):
                        raise RuntimeError('快速战斗出现付费提示，停止操作')
                    self.click_text('^确认$|^确定$',(250,1000,800,750),blue=True)
                self.reward()
            self.wait_interception_settled(before)
            self.e.log('已核实拦截次数减少')

    def wait_interception_settled(self, before):
        # The old count remains visible under the quick-battle reward animation.
        # Rescan/dismiss its result until the server updates the remaining count.
        deadline=time.monotonic()+35
        while time.monotonic()<deadline:
            self.scan()
            after=(self.find(r'[0-3]\s*[/／]\s*3',(550,1660,520,240))
                   or self.find(r'[0-3]\s*[/／]\s*3',(0,120,560,180)))
            if after and int(re.search(r'([0-3])\s*[/／]\s*3',after['text'])[1])<before:
                return
            self.wait(1)
        raise RuntimeError('拦截次数未减少，不标记成功或重复挑战')

    def notification_dots(self, roi):
        x,y,w,h=roi
        a=np.asarray(self.image.crop((x,y,x+w,y+h)))
        mask=(a[:,:,0]>200)&(a[:,:,1]<155)&(a[:,:,2]<115)
        seen=set();dots=[]
        for py,px in zip(*np.where(mask)):
            if (py,px) in seen:continue
            stack=[(py,px)];seen.add((py,px));points=[]
            while stack:
                yy,xx=stack.pop();points.append((yy,xx))
                for dy,dx in ((1,0),(-1,0),(0,1),(0,-1)):
                    ny,nx=yy+dy,xx+dx
                    if 0<=ny<h and 0<=nx<w and mask[ny,nx] and (ny,nx) not in seen:
                        seen.add((ny,nx));stack.append((ny,nx))
            ys,xs=zip(*points);bw=max(xs)-min(xs)+1;bh=max(ys)-min(ys)+1
            if (10<=bw<=34 and 10<=bh<=34 and .65<bw/bh<1.5
                    and 50<=len(points)<=700 and .45<len(points)/(bw*bh)<.92):
                dots.append((x+(min(xs)+max(xs))/2,y+(min(ys)+max(ys))/2))
        return sorted(dots,key=lambda p:p[1])

    def bond_scroll(self, start_y, end_y):
        frame=self.e.controller.post_screencap().wait().get()
        if frame is None:raise RuntimeError('花絮列表截图失败')
        sx=frame.shape[1]/1080;sy=frame.shape[0]/1920
        if not self.e.controller.post_swipe(round(540*sx),round(start_y*sy),
                round(540*sx),round(end_y*sy),600).wait().succeeded:
            raise RuntimeError('花絮列表滑动失败')
        self.wait(2)

    def bond_chapters(self):
        self.expect('^花絮$',(350,130,400,150))
        claimed=0;previous=None
        for _ in range(20):
            self.scan()
            dots=self.notification_dots((950,860,70,855))
            if dots:
                _,y=dots[0]
                if y>1540:
                    self.bond_scroll(1550,1120);continue
                self.tap(600,y+75,2)
                deadline=time.monotonic()+60;reward_seen=False
                while time.monotonic()<deadline:
                    self.scan()
                    reward_seen=reward_seen or self.reward_dismissed
                    if self.find('^花絮$',(350,130,400,150)):
                        if not reward_seen:
                            self.wait(1);continue
                        claimed+=1;self.e.log('已跳过花絮并领取章节奖励');previous=None;break
                    if self.skip_bond_story():
                        continue
                    if self.find('跳过.*剧情|跳过.*故事'):
                        self.click_text('^确认$|^确定$',(0,700,1080,750));continue
                    self.wait(1)
                else:raise RuntimeError('花絮剧情跳过或奖励结算超时')
                continue
            fingerprint=np.asarray(self.image.crop((80,860,995,1715)).resize((64,64)),dtype=float)
            if previous is not None and np.mean(np.abs(fingerprint-previous))<1.5:break
            previous=fingerprint;self.bond_scroll(1550,1020)
        else:raise RuntimeError('花絮章节检查达到上限')
        self.tap(980,215,2)
        self.expect('查看花絮',(750,900,330,500))
        return claimed

    def skip_bond_story(self, label="角色花絮"):
        result=self.t.post_recognition('OCR',JOCR(expected=['跳过|SKIP'],
                    roi=[875,0,190,120],threshold=.55),
                    np.asarray(self.image)[:,:,::-1].copy()).wait().get()
        if result and any(re.search('跳过|SKIP',i.text)
                          for node in result.nodes if node.recognition
                          for i in node.recognition.filtered_results):
            self.e.log('跳过'+label+'剧情');self.tap(970,50,2);return True
        return False

    def bond_rewards(self):
        self.expect('咨询次数',(70,400,460,110))
        top_previous=None
        for _ in range(80):
            self.scan()
            current=np.asarray(self.image.crop((50,550,1040,1660)).resize((64,64)),dtype=float)
            if top_previous is not None and np.mean(np.abs(current-top_previous))<1.5:break
            top_previous=current;self.bond_scroll(650,1560)
        else:raise RuntimeError('未确认角色列表顶部')
        previous=None;claimed=0;handled=set()
        for _ in range(80):
            self.scan()
            dots=self.notification_dots((995,550,55,1160))
            if dots:
                _,y=dots[0]
                if y>1540:
                    self.bond_scroll(1550,1050);continue
                self.tap(600,y+70,2)
                self.expect('查看花絮',(750,900,330,500))
                role=self.find(r'^[^\d/]+$',(50,1150,500,100))
                if not role:raise RuntimeError('未确认花絮角色名称')
                if role['text'] in handled:
                    raise RuntimeError('已处理角色仍有花絮红点，不重复进入')
                self.click_text('查看花絮',(750,900,330,500))
                claimed+=self.bond_chapters()
                handled.add(role['text'])
                self.click_text('^返回$',(0,1720,280,180))
                self.expect('咨询次数',(70,400,460,110))
                previous=None;continue
            fingerprint=np.asarray(self.image.crop((50,550,1040,1660)).resize((64,64)),dtype=float)
            if previous is not None and np.mean(np.abs(fingerprint-previous))<1.5:
                self.e.log(f'花絮红点检查完成，领取{claimed}个章节奖励');return claimed
            previous=fingerprint;self.bond_scroll(1560,650)
        raise RuntimeError('角色花絮检查达到上限')

    def advise(self):
        outcome=self.advise_batch()
        claimed=self.bond_rewards()
        return None if claimed else outcome

    def advise_batch(self):
        self.tap(150, 1800, 4)
        self.expect('^妮姬$', (0, 0, 250, 130))
        self.expect('^咨询$', (740, 160, 330, 130),timeout=25)
        self.click_text('^咨询$', (740, 160, 330, 130))
        self.expect('咨询次数', (70, 400, 460, 110))
        before=self.advise_remaining()
        if before==0:
            self.e.log('今日咨询次数已用完')
            return 'skipped'
        if before is None:
            raise RuntimeError('未识别咨询剩余次数')
        if not self.click_text('批量咨询', (790, 1720, 280, 150), blue=True):
            raise RuntimeError('未解锁批量咨询，请先手动完成对应角色咨询')
        self.expect('消耗次数',(0,1480,500,160),timeout=25)
        selected=self.find(r'消耗次数\s*(\d+)\s*[/／]\s*(\d+)',(0,1480,500,160))
        if not selected:
            raise RuntimeError('未确认游戏批量咨询名单与消耗次数')
        match=re.search(r'消耗次数\s*(\d+)\s*[/／]\s*(\d+)',selected['text'])
        count=int(match.group(1))
        if count==0:
            self.click_text('^关闭$',(720,1740,350,160))
            self.e.log('游戏批量名单没有可咨询角色，跳过')
            return 'skipped'
        if count>before:
            raise RuntimeError('批量咨询消耗超过剩余免费次数')
        if self.find('钻石|购买'):
            raise RuntimeError('咨询出现付费提示，已停止')
        if not self.click_text('^批量咨询$', (720,1580,350,220), blue=True):
            raise RuntimeError('未识别批量咨询确认按钮')
        deadline=time.monotonic()+45
        while time.monotonic()<deadline:
            self.scan()
            remaining=self.advise_remaining()
            if remaining==before-count:
                if self.find('消耗次数',(0,1480,500,160)):
                    self.click_text('^关闭$',(720,1740,350,160))
                self.e.log(f'批量咨询已完成 {count} 次，剩余 {remaining}/10')
                return
            if self.find('是否.*批量咨询',(100,700,850,300)):
                self.click_text('^确认$|^确定$',(300,900,760,800),blue=True)
            self.wait(1)
        raise RuntimeError('批量咨询后次数未减少，不标记完成')

    def recruit_free(self):
        if not self.click_text('^队员招募$',(750,1720,330,200)):
            raise RuntimeError('大厅队员招募入口未识别')
        self.expect('^招募队员$',(0,0,320,180))
        self.wait(2); self.scan()
        free_roi=(0,1450,420,330)
        free=self.find(r'每日免费\s*[1一]\s*次',free_roi)
        if not free:
            if self.recruit_paid_only():
                self.e.log('每日免费招募入口已消失，已使用，跳过')
                return 'skipped'
            raise RuntimeError('当前招募页未识别每日免费一次入口，不执行招募')
        if not self.colorful_button(free):
            self.e.log('每日免费招募已使用，跳过')
            return 'skipped'
        if not self.find('招募1名|招募１名',free_roi):
            raise RuntimeError('未确认免费单次招募按钮')
        self.e.log('领取每日免费单次招募')
        self.click_text(r'每日免费\s*[1一]\s*次',free_roi)
        # Result states are deliberately explicit; unknown pages are captured
        # by Engine rather than clicking paid recruitment controls underneath.
        deadline=time.monotonic()+90
        settled=False
        while time.monotonic()<deadline:
            self.scan()
            if self.acquire_dismissed:
                settled=True
            if self.find('^招募队员$',(0,0,320,180)):
                free=self.find(r'每日免费\s*[1一]\s*次',free_roi)
                if free and not self.colorful_button(free):
                    self.e.log('免费招募已结算，免费入口已不可用')
                    return
                if settled and not free and self.recruit_paid_only():
                    self.e.log('免费招募已结算，免费入口已消失')
                    return
            if self.click_text('^SKIP$|^跳过$',(650,0,430,330)):
                continue
            if self.finish_recruit_result():
                settled=True
                continue
            self.wait(1)
        raise RuntimeError('免费招募结果未确认，停止本项，不重复抽取')

    def recruit_paid_only(self):
        return bool(self.find('^招募队员$',(0,0,320,180))
                    and self.find('特殊招募',(250,1000,700,400))
                    and self.find('^招募1名$',(150,1450,380,200))
                    and self.find('^招募10名$',(550,1450,500,200))
                    and self.find(r'[xX×]\s*1$',(150,1500,400,240)))

    def finish_recruit_result(self):
        if not (self.find('RECRUITMENT.*RESULT',(0,0,650,420))
                and self.find('^再招募$',(550,1550,520,320))
                and self.find('^确认$',(100,1550,440,320))):
            return False
        self.click_text('^确认$',(100,1550,440,320))
        self.expect('^招募队员$',(0,0,320,180))
        self.e.log('已关闭招募结果，重新核对免费状态')
        return True

    def advise_remaining(self):
        item=self.find(r'^\s*\d+\s*[/／]\s*10\s*$',(280,400,200,110))
        return int(re.match(r'\s*(\d+)',item['text']).group(1)) if item else None

    def tower(self):
        self.ark((855, 670), '无限之塔')
        # 只进入当天开放的企业塔，不自动爬无上限的普通塔。
        opens = [item for item in self.items if re.fullmatch('开启', item['text'])
                 and 1000 < item['box'][1] < 1100]
        if not opens:
            self.e.log('今日没有可进入的企业塔')
            return
        x, _, w, _ = opens[0]['box']
        self.tap(x+w/2, 1330, 4)
        self.expect('剩余次数', (200,1450,880,460))
        for _ in range(max(1,min(3,int(self.options.get('tower_count',3))))):
            self.scan()
            if self.find(r'0\s*[/／]\s*3', (200,1450,880,460)):
                self.e.log('企业塔次数已用完')
                return
            before=self.find(r'[0-3]\s*[/／]\s*3',(200,1450,880,460))
            if not before:
                raise RuntimeError('企业塔剩余次数未确认')
            before=int(re.search(r'([0-3])\s*[/／]\s*3',before['text'])[1])
            if not self.find('进入战斗',(400,1600,680,320)):
                self.tap(540, 800)
                self.expect('进入战斗',(400,1600,680,320))
            if not self.battle('剩余次数'):
                return 'skipped'
            self.scan()
            after=self.find(r'[0-3]\s*[/／]\s*3',(200,1450,880,460))
            if not after or int(re.search(r'([0-3])\s*[/／]\s*3',after['text'])[1])>=before:
                self.e.log('企业塔次数未减少，结束本项，不重复挑战')
                return 'skipped'
            self.e.log('已核实企业塔剩余次数减少')

    def rookie_target(self, position):
        # The zero beside the currency icon is not the daily free count.
        # Each opponent exposes a separate blue 免费 badge above its button.
        y=(970,1238,1506)[position-1]
        free=self.find('^免费$',(800,y,220,100))
        button=self.find('^进入战斗$',(760,y+80,290,130))
        if free and button:
            x,fy,w,h=free['box']
            if self.blue(x+w/2,fy+h/2):
                return button
        return None

    def rookie(self):
        self.ark((790, 1190), '^竞技场$')
        self.tap(270, 1050, 4)
        self.expect('新人竞技场', (0, 0, 300, 150))
        position=int(self.options.get('rookie_opponent',3))
        if position not in (1,2,3):
            raise RuntimeError('竞技场对手必须为第1、2或3个')
        completed=0
        for _ in range(max(1,min(5,int(self.options.get('rookie_count',5))))):
            self.wait_rookie_list()
            button=self.rookie_target(position)
            if not button:
                self.e.log('所选对手没有免费挑战标记，结束；不购买次数')
                return 'skipped' if not completed else None
            self.e.log(f'免费挑战第{position}个对手')
            x,y,w,h=button['box']
            self.tap(x+w/2,y+h/2,2)
            if not self.battle('新人竞技场',allow_defeat=True):
                raise RuntimeError('未确认竞技场战斗结算')
            completed+=1
            self.e.log(f'竞技场已结算{completed}次')

    def wait_rookie_list(self):
        deadline=time.monotonic()+25
        while time.monotonic()<deadline:
            self.scan()
            buttons=[item for item in self.items
                     if re.fullmatch('进入战斗',item['text'])
                     and 760<=item['box'][0]+item['box'][2]/2<=1050
                     and 900<=item['box'][1]+item['box'][3]/2<=1850]
            if len(buttons)==3 and self.find('更新目录',(700,800,380,170)):
                # The title returns before the opponent list during result fade-out.
                self.wait(1)
                self.scan()
                return
            self.wait(1)
        raise RuntimeError('竞技场对手列表未恢复，不把缺失的免费标记视为次数用完')
