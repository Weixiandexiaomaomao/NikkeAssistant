"""5x5 Supplies: use existing tickets and verify each observed transition."""
import re
import time


class Supplies:
    def __init__(self, vision):
        self.v = vision

    def is_event(self):
        v=self.v
        return bool((v.find(r'5\s*[xX×]\s*5',(250,90,560,380))
                     and v.find(r'(获取|获得)18次物资',(100,430,920,180)))
                    or (self.box() is not None and v.find('爆发能量|爆发时刻',(300,1450,500,150))
                        and v.find('^任务$',(600,590,280,150))))

    def box(self):
        item=self.v.find(r'^第\s*\d+\s*箱物资$',(380,650,360,150))
        return int(re.search(r'\d+',item['text'])[0]) if item else None

    def tickets(self):
        item=self.v.find(r'^[xX×]\s*\d+$',(760,650,260,160))
        return int(re.search(r'\d+',item['text'])[0]) if item else None

    def notice(self):
        v=self.v
        if (v.find('^通知$',(300,480,500,180))
                and v.find('A型物资.*批量获取已结束',(100,750,900,160))
                and v.find('可开启下个物资箱',(200,820,680,170))):
            if not v.click_text('^确认$',(250,1080,650,250),blue=True):
                raise RuntimeError('5×5 A型物资通知未识别确认按钮')
            v.e.log('已确认A型物资通知，继续开启下一箱')
            return True
        return False

    def close(self):
        v=self.v
        if not self.is_event():
            raise RuntimeError('未确认5×5活动页面，不关闭未知窗口')
        cross=v.close_cross(range(965,1006,2),range(165,215,2))
        if not cross:
            raise RuntimeError('5×5活动关闭按钮未识别')
        v.tap(*cross,delay=2)
        v.home()
        v.e.log('5×5活动已确认返回大厅')

    def open(self):
        v=self.v
        v.scan()
        if self.notice(): v.scan()
        if self.task_dialog():
            self.close_tasks()
            v.scan()
        if self.is_event(): return True
        v.home()
        entry=v.find('^限时活动$',(0,680,380,240))
        if not entry:
            raise RuntimeError('大厅限时活动入口未识别')
        for _ in range(3):
            entry=v.find('^限时活动$',(0,680,380,240))
            if not entry: break
            x,y,w,h=entry['box']
            v.tap(x+w/2,y-65,delay=3,hold_ms=300)
            v.wait(2);v.scan()
        if self.is_event(): return True
        for _ in range(8):
            if not v.find('限时活动页面',(0,0,500,160)):
                raise RuntimeError('未确认限时活动列表，不滑动未知页面')
            entry=v.find(r'5\s*[xX×]\s*5|SUPPLIES|Supplies',(0,390,1080,1380))
            if entry:
                v.click_text(r'5\s*[xX×]\s*5|SUPPLIES|Supplies',(0,390,1080,1380))
                deadline=time.monotonic()+25
                while time.monotonic()<deadline:
                    v.scan()
                    if self.is_event(): return True
                    v.wait(1)
                break
            v.bond_scroll(1500,750)
            v.scan()
        raise RuntimeError('限时活动列表未识别5×5 Supplies入口')

    def claim_tasks(self):
        v=self.v
        # The title loads before the task tab and lower controls finish their
        # slide-in animation. Wait for the actual tab before clicking it.
        v.expect('^任务$',(550,590,380,160),timeout=30)
        if not v.click_text('^任务$',(600,590,280,150)):
            raise RuntimeError('5×5活动任务页签未识别')
        v.wait(2);v.scan()
        if not self.task_dialog():
            raise RuntimeError('未确认5×5任务列表')
        for _ in range(16):
            v.scan()
            claim=v.find(r'^(全部)?领取$',(100,730,950,1000))
            if not claim or not v.colorful_button(claim): break
            v.click_text(r'^(全部)?领取$',(100,730,950,1000))
            v.wait(2)
        else:
            raise RuntimeError('5×5任务领取达到上限，未确认领取结束')
        self.close_tasks()
        v.wait(2);v.scan()
        if self.box() is None or self.tickets() is None:
            raise RuntimeError('5×5任务领取后未确认箱号和物资数量')

    def task_dialog(self):
        v=self.v
        return (v.find('^任务$',(350,250,400,160))
                and v.find('CHALLENGE',(60,440,700,150))
                and v.find('^全部领取$',(650,1580,380,180)))

    def close_tasks(self):
        v=self.v
        if not self.task_dialog():
            raise RuntimeError('未确认5×5任务窗口，不执行关闭')
        cross=v.close_cross(range(950,1006,2),range(178,236,2))
        if not cross:
            raise RuntimeError('5×5任务窗口关闭按钮未识别')
        v.tap(*cross,delay=2)

    def wait_change(self, before, opening=False):
        v=self.v
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            v.scan()
            if self.notice(): continue
            box,count=self.box(),self.tickets()
            if box is not None and count is not None:
                if opening and box==before[0]+1 and count==before[1]: return
                if not opening and box==before[0] and count<before[1]: return
            v.wait(1)
        raise RuntimeError('5×5箱号或物资数量未按操作变化，不重复消耗')

    def advance(self, before):
        v=self.v
        v.click_text('^开启下个物资箱$',(100,1650,450,180),blue=True)
        v.expect(r'确定开启下个物资箱',(200,870,780,230))
        title=v.find(r'^完成第\s*\d+\s*箱奖励$',(250,480,580,200))
        if not title or int(re.search(r'\d+',title['text'])[0])!=before[0]:
            raise RuntimeError('5×5下一箱确认窗口箱号不一致')
        if not v.find('物资将会重置.*完成奖励',(300,850,700,170)):
            raise RuntimeError('5×5下一箱确认内容未识别')
        if not v.click_text('^确认$',(600,1080,380,260),blue=True):
            raise RuntimeError('5×5下一箱蓝色确认按钮未识别')
        self.wait_change(before,opening=True)
        v.e.log(f'5×5第{before[0]}箱完成奖励已领取，已开启第{before[0]+1}箱')

    def run(self):
        v=self.v
        self.open()
        self.claim_tasks()
        for _ in range(80):
            v.scan()
            if self.notice(): continue
            if not self.is_event(): raise RuntimeError('5×5活动页面丢失')
            box,count=self.box(),self.tickets()
            if box is None or count is None:
                raise RuntimeError('5×5箱号或现有物资数量未确认')
            advance=v.find('^开启下个物资箱$',(100,1650,450,180))
            if advance and v.blue(advance['box'][0]+advance['box'][2]/2,
                                  advance['box'][1]+advance['box'][3]/2):
                self.advance((box,count));continue
            if count==0:
                v.e.log('5×5现有物资已用完，结束本轮')
                self.close();return
            item=v.find(r'^获取\s*\d+\s*份物[资瓷]$',(500,1650,550,180))
            if not item or not v.colorful_button(item):
                raise RuntimeError('有现有物资，但5×5获取按钮未确认可用')
            amount=int(re.search(r'\d+',item['text'])[0])
            if not 0<amount<=count:
                raise RuntimeError('5×5获取数量超过已持有物资，不执行')
            v.e.log(f'5×5第{box}箱：使用现有物资批量获取，当前{count}份')
            v.click_text(r'^获取\s*\d+\s*份物[资瓷]$',(500,1650,550,180))
            self.wait_change((box,count))
        raise RuntimeError('5×5循环达到上限，未标记完成')
