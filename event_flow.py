"""Activity continuation from a manually selected stage; event maps require separate adapters."""
import time
import re
import numpy as np


class EventActivities:
    """Observed CN Unbreakable Sphere menu, sign-in, story and challenge flow."""
    def __init__(self, vision, layout="sphere"):
        self.v = vision
        self.layout = layout

    def bounded_step(self, method, seconds):
        """Every scan, click and delay calls wait, providing a cancellable deadline."""
        original_wait = self.v.wait
        deadline = time.monotonic() + seconds
        def checked_wait(delay=1):
            if time.monotonic() >= deadline:
                raise RuntimeError('当前步骤超时')
            original_wait(min(delay,max(0,deadline-time.monotonic())))
            if time.monotonic() >= deadline:
                raise RuntimeError('当前步骤超时')
        self.v.wait = checked_wait
        try:
            return method()
        finally:
            self.v.wait = original_wait

    def is_home(self):
        v = self.v
        if self.layout=='wisdom':
            return bool(v.find('剧情活动',(0,0,300,180)) and v.find('^ENTER$')
                        and v.find('^挑战$') and v.find('^任务$'))
        return bool(v.find('活动地区', (0,0,300,180)) and
                    v.find('签到印章', (550,1400,530,250)) and
                    v.find('STORY', (0,1300,500,400)))

    def home(self):
        v = self.v
        rotations = 0
        for _ in range(5):
            v.scan()
            if self.is_home():
                return
            if self.layout=='wisdom' and v.find('活动地区',(0,0,300,180)) and v.find('签到印章'):
                v.home()
                continue
            if v.find('^大厅$', (450,1820,180,100)) and v.lobby():
                banner = (550,1450,530,280)
                wanted='WISDOM|SPRING' if self.layout=='wisdom' else 'UNBREAKABLE'
                other='UNBREAKABLE' if self.layout=='wisdom' else 'WISDOM|SPRING'
                if v.find(wanted,banner):
                    v.e.log('从大厅进入 '+('WISDOM SPRING' if self.layout=='wisdom' else 'UNBREAKABLE SPHERE')+' 活动')
                    v.click_text(wanted,banner)
                    v.expect('剧情活动' if self.layout=='wisdom' else '活动地区',(0,0,300,180),timeout=35)
                    # The header appears before the animated menu. Do not use
                    # Back while its remaining controls are still loading, and
                    # check the final entry even on the last navigation attempt.
                    deadline = time.monotonic() + 15
                    while time.monotonic() < deadline:
                        v.scan()
                        if self.is_home():
                            return
                        v.wait(1)
                    raise RuntimeError('活动首页菜单加载后仍未识别，请保留截图')
                elif rotations < 2 and v.find(other,banner):
                    # The observed lobby carousel has a refresh button at its lower right.
                    v.tap(1030,1700)
                    rotations += 1
                else:
                    raise RuntimeError('大厅未识别到所选活动入口，请确认活动仍开放')
            elif v.find('关卡信息') and v.find('进入战斗'):
                # Close the selected-stage sheet before using the bottom back button.
                v.tap(1050,1000)
            elif v.find('每日任务',(100,250,400,220)) and v.find('成就',(450,250,450,220)):
                v.tap(990,120)
            elif self.layout=='wisdom' and v.find('CHALLENGE',(70,500,750,180)) and v.find('全部领取',(550,1600,500,250)):
                v.tap(990,230)
            elif v.find('剩余次数',(300,1100,500,220)) and v.find('进行战斗',(650,1370,380,200)):
                v.click_text('^取消$',(100,1370,350,200))
            elif v.find('点击任意处进行下一步|点击领取奖励'):
                v.click_text('点击任意处进行下一步|点击领取奖励')
            elif v.find('返回', (0,1750,300,170)):
                v.click_text('返回', (0,1750,300,170))
            else:
                raise RuntimeError('请先进入 UNBREAKABLE SPHERE 活动首页；未识别可返回活动的页面')
            v.wait(3)
        raise RuntimeError('未确认返回活动首页')

    def enabled(self, item):
        x,y,w,h = item['box']
        pixels = np.asarray(self.v.image.crop((max(0,int(x+w/2)-110),max(0,int(y+h/2)-20),
                                             min(1080,int(x+w/2)+110),min(1920,int(y+h/2)+20))),dtype=np.int16)
        return pixels.size > 0 and np.mean((pixels.max(2)-pixels.min(2)>55)&(pixels.max(2)>130))>.2

    def open_menu(self, expression, page):
        self.home()
        v = self.v
        if not v.click_text(expression,(0,1350,1080,390)):
            raise RuntimeError('未识别活动入口：'+expression)
        v.expect(page,timeout=35)

    def option(self,key,default=None):
        prefix='wisdom_' if self.layout=='wisdom' else 'event_'
        return self.v.options.get(prefix+key,default)

    def signin(self):
        v = self.v
        if self.layout=='wisdom':
            self.home()
            v.e.log('WISDOM SPRING 首页没有独立签到入口，跳过签到')
            return
        self.open_menu('签到印章','累计登入天数|累[计积].*登[入录]|全部领取')
        v.expect('全部领取',(450,1730,600,180),timeout=20)
        item = v.find('全部领取',(450,1730,600,180))
        if not item:
            raise RuntimeError('未识别签到领取按钮')
        if self.enabled(item):
            v.click_text('全部领取',(450,1730,600,180))
            v.reward()
            v.expect('全部领取',(450,1730,600,180))
            v.wait(2); v.scan()
            item = v.find('全部领取',(450,1730,600,180))
            if not item or self.enabled(item):
                raise RuntimeError('签到后未确认领取按钮变灰')
            v.e.log('活动签到奖励已领取')
        else:
            v.e.log('活动签到已领取，跳过')
        self.home()

    @staticmethod
    def stage_number(text):
        match = re.fullmatch(r'\s*(?:Event\s*)?(\d+)\s*[-－]\s*(\d+)\s*',text,re.I)
        return tuple(map(int,match.groups())) if match else None

    def select_stage(self, number=None):
        v = self.v
        for _ in range(10):
            v.scan()
            candidates = []
            if self.layout=='wisdom' and number is not None:
                # Whole-screen detection truncates the leading digits on this
                # narrow list. Re-read each observed REPEAT row's number crop.
                from maa.pipeline import JOCR
                for row in list(v.items):
                    if not re.fullmatch('REPEAT',row['text'],re.I):
                        continue
                    _,ry,_,rh=row['box']
                    if not 550<ry<1500:
                        continue
                    cy=ry+rh/2
                    crop=v.image.crop((470,int(cy-32),610,int(cy+23))).resize((560,220))
                    result=v.t.post_recognition('OCR',JOCR(expected=['.*'],only_rec=True,threshold=.7),
                                               np.asarray(crop)[:,:,::-1].copy()).wait().get()
                    for node in result.nodes if result else []:
                        if not node.recognition:
                            continue
                        for reread in node.recognition.raw_detail.get('filtered',[]):
                            parsed=self.stage_number(reread['text'])
                            if parsed and parsed==(1,number):
                                candidates.append((parsed,{'text':reread['text'],'box':[470,cy-32,140,55]}))
            if self.layout=='sphere' and number is None:
                # This chapter uses an ornate Event row; whole-screen OCR can
                # omit its thin digits. The unlocked Event label itself is an
                # observed row anchor, while Access Denied rows are excluded.
                for row in v.items:
                    if re.fullmatch(r'Event',row['text'],re.I):
                        x,y,w,h=row['box'];key=(0,round(y))
                        if 250<y<1700 and key not in getattr(self,'checked_stages',set()):
                            candidates.append((key,row))
            for item in v.items:
                parsed = self.stage_number(item['text'])
                if not parsed:
                    continue
                x,y,w,h = item['box']
                if not 250<y<1700:
                    continue
                if number is None and parsed in getattr(self,'checked_stages',set()):
                    continue
                if number is not None and parsed[1] != number:
                    continue
                if number is None and v.find('clear|CLEAR|REPEAT|已通关|锁定|Access\s*Denied',
                                             (max(0,x-180),max(0,y-100),min(1080,600),180)):
                    continue
                candidates.append((parsed,item))
            if candidates:
                selected,item = sorted(candidates,key=lambda pair:pair[0])[0]
                x,y,w,h = item['box']
                v.tap(x+w/2,y+h/2 if self.layout=="wisdom" or re.match(r"Event",item["text"],re.I) else max(260,y-95))
                v.expect('关卡信息|进入战斗|故事')
                if number is None:
                    self.checked_stages=getattr(self,'checked_stages',set())|{selected}
                    v.scan()
                    quick=v.find('快速战斗',(500,1550,580,220))
                    if quick and self.enabled(quick):
                        v.tap(1050,1000)
                        v.expect('活动关卡',(0,0,300,170))
                        continue
                return True
            # Only swipe an identified story stage list; never scan unrelated screens.
            if not v.find('活动关卡',(0,0,300,170)):
                raise RuntimeError('未识别活动关卡列表')
            from engine import adb_run
            s = v.size
            adb_run(v.e.adb,v.e.serial,'shell','input','swipe',
                    str(round(540*s[0]/1080)),str(round(1450*s[1]/1920)),
                    str(round(540*s[0]/1080)),str(round(650*s[1]/1920)),'650')
            v.wait(1.5)
        return False

    def story(self):
        v = self.v
        self.home(); v.scan()
        if self.layout=='wisdom':
            if not v.click_text('^ENTER$',(100,1250,800,300)):
                raise RuntimeError('未识别 WISDOM SPRING 的 ENTER 入口')
            v.expect('活动关卡',(0,0,300,170),timeout=35)
            difficulty=self.option('difficulty','当前')
            if difficulty in ('普通','困难'):
                v.click_text('^NORMAL$' if difficulty=='普通' else '^HARD$',(500,1640,580,280))
                v.wait(2);v.scan()
        else:
            # Prefer newly opened STORY II before consuming tickets on old farming.
            second=v.find(r'^STORY\s*II$',(0,1300,500,400))
            if second and self.enabled(second):
                self.open_story_part('II')
                v.scan()
                if v.find(r'0\s*[/／]\s*5',(500,90,500,220)):
                    v.e.log('STORY II 门票已用完，保留新关卡优先策略至下次重置')
                    self.home();return
                self.checked_stages=set()
                if self.select_stage():
                    v.e.log('STORY II 已开放，优先推进未通关的新关卡')
                    EventPush(v).run()
                    self.home()
                    return
                v.e.log('STORY II 未找到可推进的新关卡，使用日常关卡设置')
                self.home();v.scan()
            if not self.open_story_part(self.option('story_part','I')):
                return
        v.scan()
        if v.find(r'0\s*[/／]\s*5',(700,420,380,180) if self.layout=='wisdom' else (500,90,350,140)):
            v.e.log('活动 STORY 门票已用完，跳过'); self.home(); return
        farm = self.option('story_mode','快速战斗')=='快速战斗'
        number = int(self.option('farm_stage',11)) if farm else None
        if not self.select_stage(number):
            if farm:
                raise RuntimeError('未找到指定活动关卡')
            v.e.log('当前可见活动关卡均已完成或锁定'); self.home(); return
        v.scan()
        if farm:
            quick = v.find('快速战斗',(500,1550,580,220))
            if not quick or not self.enabled(quick):
                raise RuntimeError('指定关卡未开放快速战斗，请先通关或改为推图')
            v.click_text('快速战斗',(500,1550,580,220))
            v.expect('按照.*快速战斗|自订.*次数|剩余次数')
            v.scan()
            # The observed dialog presents existing-ticket count. Never open ticket shop.
            v.expect('进行战斗',(650,1370,380,200),timeout=20)
            if not v.find('剩余次数'):
                raise RuntimeError('未识别快速战斗次数弹窗')
            self.set_quick_count()
            if not v.click_text('进行战斗',(650,1370,380,200),blue=True):
                raise RuntimeError('未识别快速战斗确认按钮')
            v.expect('点击任意处进行下一步',timeout=40)
            v.click_text('点击任意处进行下一步')
            v.expect('活动关卡',(0,0,300,170))
            v.e.log('活动 STORY 快速战斗已完成')
        else:
            EventPush(v).run()
        self.home()

    def open_story_part(self, part):
        v=self.v
        expression=r'^STORY\s*'+part+r'$'
        v.expect(expression,(0,1300,500,400),timeout=15)
        item=v.find(expression,(0,1300,500,400))
        if not item:raise RuntimeError('未识别 STORY '+part)
        if not self.enabled(item):
            v.e.log('STORY '+part+' 尚未开放，跳过')
            return False
        v.click_text(expression,(0,1300,500,400))
        v.expect('^(?:ENTER|Enter|nter)$|活动关卡',timeout=35)
        if v.find('^(?:ENTER|Enter|nter)$',(100,1250,800,400)):
            if not v.find('剧情活动',(0,0,300,170)):
                raise RuntimeError('未确认 STORY 剧情活动入口页')
            v.click_text('^(?:ENTER|Enter|nter)$',(100,1250,800,400))
            v.expect('活动关卡',(0,0,300,170))
        return True

    def challenge(self):
        v = self.v
        self.open_menu('^挑战$','挑战关卡')
        v.expect('CHALLENGE\\s*STAGE|WARNING|CLEAR\\s*STAGE|[/／]',
                 (0,400,1080,1250),timeout=20)
        v.scan()
        if v.find(r'[0OoＯ]\s*[/／]\s*[1Il丨]',(870,480,210,150)):
            v.e.log('活动挑战次数已用完，跳过'); self.home(); return
        rows = [item for item in v.items if re.search('CHALLENGE\s*STAGE|WARNING',item['text'],re.I)]
        if self.layout=='wisdom':
            # WARNING is a fixed heading in this layout, not a stage row.
            rows = [item for item in v.items if re.search('(?:CHALLENGE|CLEAR)\s*STAGE',item['text'],re.I)]
        if not rows:
            raise RuntimeError('未识别可挑战关卡')
        item = max(rows,key=lambda it:it['box'][1])
        x,y,w,h = item['box']; v.tap(x+w/2,y+h/2)
        v.expect('进入战斗',(500,1690,580,180))
        v.scan()
        quick=v.find('快速战斗',(500,1550,580,220))
        if quick and self.enabled(quick):
            self.quick_battle()
            v.e.log('活动挑战快速战斗已完成')
            self.home()
            return
        start = v.find('进入战斗',(500,1690,580,180))
        if start and not self.enabled(start):
            v.e.log('活动挑战开战按钮为灰色，跳过并继续领取任务')
            self.home()
            return
        if not v.battle('挑战关卡',limit=240):
            self.home(); return
        v.e.log('活动挑战战斗已结束'); self.home()

    def missions(self):
        v = self.v
        self.home()
        if not v.click_text('^任务$',(550,1500,530,240) if self.layout=='wisdom' else (880,250,200,330)):
            raise RuntimeError('未识别活动任务入口')
        if self.layout=='wisdom':
            v.expect('CHALLENGE',(70,500,750,180),timeout=25)
            self.claim_missions('任务')
            self.home()
            return
        v.expect('每日任务')
        for tab in ('每日任务','成就'):
            v.scan()
            if not v.click_text('^'+tab+'$',(50,250,930,220)):
                raise RuntimeError('未识别活动任务分类：'+tab)
            self.claim_missions(tab)
        self.home()

    def claim_missions(self,tab):
        v=self.v
        v.expect('全部领取',(550,1600,500,250),timeout=20)
        for _ in range(20):
            v.scan()
            item=v.find('全部领取',(550,1600,500,250))
            if not item:
                raise RuntimeError('未识别活动任务领取状态')
            if not self.enabled(item):
                v.e.log('活动'+tab+'奖励已领完')
                return
            x,y,w,h=item['box'];v.tap(x+w/2,y+h/2)
            v.reward()
            v.wait(1.5)
        raise RuntimeError('活动任务领取达到检查上限')

    def quick_battle(self):
        v=self.v
        v.click_text('快速战斗',(500,1550,580,220))
        v.expect('剩余次数',timeout=20)
        v.scan()
        v.expect('进行战斗',(650,1370,380,200),timeout=20)
        self.set_quick_count()
        if not v.click_text('进行战斗',(650,1370,380,200),blue=True):
            raise RuntimeError('未识别快速战斗确认按钮')
        v.expect('点击任意处进行下一步',timeout=40)
        v.click_text('点击任意处进行下一步')
        v.expect('挑战关卡',(0,0,300,170),timeout=25)

    def set_quick_count(self):
        v=self.v
        # A single ticket disables MIN/MAX and OCR may omit their gray text.
        if v.find(r'^1\s*[/／]\s*1$',(400,1280,240,150)):
            return
        if not v.find('^MAX$',(650,1280,250,150)):
            raise RuntimeError('未识别快速战斗次数控制')
        v.click_text('^MAX$',(650,1280,250,150));v.scan()

    def run(self):
        self.home()
        skipped = []
        for key,method,timeout in [('signin',self.signin,90),('story',self.story,900),
                                   ('challenge',self.challenge,300),('missions',self.missions,150)]:
            if self.option(key,True):
                self.v.e.log('活动流程：'+key)
                try:
                    self.bounded_step(method,timeout)
                except InterruptedError:
                    raise
                except RuntimeError as error:
                    skipped.append(key)
                    self.v.e.log(f'活动步骤跳过：{key}，原因：{error}')
                    if hasattr(self.v.e,'screenshot'):
                        from portable import ROOT
                        folder=ROOT/'captures'
                        folder.mkdir(exist_ok=True)
                        target=folder/f'event-{key}-{int(time.time())}.png'
                        target.write_bytes(self.v.e.screenshot())
                        self.v.e.log('活动失败截图：'+str(target))
                    try:
                        self.bounded_step(self.home,60)
                    except InterruptedError:
                        raise
                    except RuntimeError as recovery:
                        raise RuntimeError(f'{key} 异常后未能确认返回活动首页，为避免误操作停止：{recovery}') from error
                    self.v.e.log('已恢复活动首页，继续下一项')
        self.v.e.log('活动日常流程结束，已返回活动首页'+
                     ('；未完成步骤：'+', '.join(skipped) if skipped else ''))
        return 'skipped' if skipped else None


class EventPush:
    def __init__(self, vision):
        self.v = vision

    def run(self):
        v = self.v
        maximum = max(1, min(24, int(v.options.get('event_push_count', 12))))
        skip = v.options.get('event_skip_story', '否') == '是'
        v.scan()
        stage = v.find(r'^\s*(?:Event\s*)?\d+\s*[-－]\s*\d+\s*(?:.*)?$')
        start = '^(?:战斗开始|进入战斗|开始战斗)$'
        next_stage = '^下一关(?:卡)?$'
        if not (v.find(next_stage) or (stage and v.find(start))):
            raise RuntimeError('请先进入活动并选择关卡，停在战斗准备页或战后“下一关卡”页。活动地图自动选关尚未适配。')
        started = 0
        in_battle = False
        result_seen = False
        deadline = time.monotonic() + 1200
        progress = time.monotonic()
        battle_started = None
        while time.monotonic() < deadline:
            v.scan()
            if v.find('战斗失败|DEFEAT|^失败$'):
                raise RuntimeError('活动战斗失败，推图已停止')
            if v.find('门票不足|入场券不足|次数不足|尚未解锁|未开放|购买.*(?:门票|入场券)|(?:门票|入场券).*购买'):
                raise RuntimeError('活动关卡锁定或门票不足，推图已停止')
            if getattr(v,'reward_dismissed',False):
                result_seen=True
                in_battle=False
            if v.find('战斗胜利|VICTORY|点击领取奖励'):
                result_seen = True
                in_battle = False
            if v.find(next_stage):
                if started >= maximum:
                    v.e.log(f'活动推图达到上限：已开始 {started} 关，停留在战后页面')
                    return
                if not v.click_text(next_stage, (0, 1000, 1080, 920), blue=True):
                    raise RuntimeError('下一关按钮不可用，活动推图停止')
                in_battle = False
                result_seen = False
                progress = time.monotonic()
                continue
            if not in_battle and v.find(start):
                if started >= maximum:
                    v.e.log(f'活动推图达到上限：已开始 {started} 关')
                    return
                button=v.find(start,(0,900,1080,1020))
                if button and not v.colorful_button(button):
                    v.e.log('活动开战按钮为灰色，跳过当前推图，不购买门票')
                    return 'skipped'
                if not v.click_text(start, (0, 900, 1080, 1020)):
                    raise RuntimeError('未确认可用的活动开战按钮')
                started += 1
                in_battle = True
                result_seen = False
                battle_started = progress = time.monotonic()
                v.e.log(f'活动推图：开始第 {started}/{maximum} 关')
                continue
            if result_seen and v.click_text('^点击领取奖励$|^点击.*继续$', (0, 650, 1080, 1200)):
                progress = time.monotonic()
                continue
            dedicated_skip=skip and hasattr(v,'skip_bond_story') and v.skip_bond_story('活动')
            if dedicated_skip or (skip and v.find('^SKIP$|^跳过$', (600, 0, 480, 300))):
                if not dedicated_skip:
                    v.click_text('^SKIP$|^跳过$', (600, 0, 480, 300))
                v.scan()
                if v.find('跳过.*剧情|跳过.*故事'):
                    v.click_text('^确认$|^确定$', (0, 700, 1080, 650))
                progress = time.monotonic()
                continue
            if result_seen and started and v.find('活动关卡',(0,0,300,170)):
                v.e.log('新关卡已结束并返回活动关卡列表')
                return
            if result_seen and v.find('返回活动|返回地图'):
                v.e.log('当前关卡已结束，需手动选择后续关卡；地图自动选关尚未适配')
                return
            now = time.monotonic()
            if in_battle and battle_started is not None and now - battle_started > 240:
                raise RuntimeError('活动战斗超过四分钟，请检查自动射击和自动爆裂')
            if not in_battle and now - progress > 45:
                raise RuntimeError('未识别到后续活动页面，推图停止，请保留当前画面用于适配')
            v.wait(2)
        raise RuntimeError('活动推图超过二十分钟，已停止')
