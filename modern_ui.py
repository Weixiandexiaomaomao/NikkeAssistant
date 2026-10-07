"""三栏任务管理界面，任务勾选与设置焦点互相独立。"""
import json
import os
import threading
import tkinter as tk
import customtkinter as ctk
from portable import ROOT, VERSION

BLUE='#1260FF'
BG='#F1F3F8'
CARD='#FAFAFC'
TEXT='#303746'
MUTED='#848A96'

class TaskSelection:
    def __init__(self, app): self.app=app
    def size(self): return len(self.app.tasks)
    def curselection(self): return tuple(i for i in self.app.visible_indices() if self.app.checked[i].get())
    def selection_set(self, first, last=None):
        for i in range(first, (first if last is None else last)+1): self.app.checked[i].set(True)
    def selection_clear(self, first, last):
        for v in self.app.checked: v.set(False)

class ModernUI:
    def label(self, parent, text, size=14, color=TEXT, **kw):
        return ctk.CTkLabel(parent,text=text,font=('Microsoft YaHei UI',size),text_color=color,**kw)

    def button(self,parent,text,command,primary=False,**kw):
        return ctk.CTkButton(parent,text=text,command=command,height=32,
                             font=('Microsoft YaHei UI',14),corner_radius=8,
                             fg_color=BLUE if primary else '#EEF1F7',
                             text_color='white' if primary else TEXT,
                             hover_color='#3478FF' if primary else '#E2E8F4',**kw)

    def card(self,parent,title):
        outer=ctk.CTkFrame(parent,fg_color=CARD,corner_radius=18,border_width=1,border_color='#E4E7EE')
        header=ctk.CTkFrame(outer,fg_color='transparent',height=40)
        header.pack(fill='x',padx=16,pady=(10,0))
        self.label(header,title,14).pack(side='left')
        ctk.CTkFrame(outer,height=1,fg_color='#D8DBE3').pack(fill='x',padx=16,pady=(0,8))
        body=ctk.CTkFrame(outer,fg_color='transparent')
        body.pack(fill='both',expand=True,padx=16,pady=(0,14))
        return outer,body,header

    def build_ui(self,settings):
        self.configure(fg_color=BG)
        self.geometry('1320x830'); self.minsize(1120,720)
        self.checked=[tk.BooleanVar(value=t.get('id') in settings['selected'] if 'selected' in settings
                                    else t.get('default',False)) for t in self.tasks]
        self.task_list=TaskSelection(self)
        self.focused_task=0
        self.editable=[]; self.row_labels={}; self.row_frames={}; self.row_states={}
        self.task_states={}; self.preview_busy=False
        self.profile=tk.StringVar(value='日常长草')
        self.status_text=tk.StringVar(value='尚未连接')
        self.live=tk.BooleanVar(value=settings.get('live_preview',True))
        # 窄侧栏与顶部页签，对齐用户给出的 M9A 排版。
        rail=ctk.CTkFrame(self,width=48,corner_radius=0,fg_color='#F8F9FC')
        rail.pack(side='left',fill='y'); rail.pack_propagate(False)
        self.label(rail,'›',25).pack(pady=(12,15))
        self.button(rail,'▤',lambda:self._set_profile('日常长草'),width=38).pack(padx=5,pady=6)
        self.button(rail,'⊞',self.open_recorder,width=38).pack(padx=5,pady=6)
        self.button(rail,'▣',self.capture,width=38).pack(padx=5,pady=6)
        self.button(rail,'⚙',self.connection_settings,width=38).pack(side='bottom',padx=5,pady=12)
        self.label(rail,'CN',11,MUTED).pack(side='bottom',pady=6)
        shell=ctk.CTkFrame(self,fg_color='transparent'); shell.pack(side='left',fill='both',expand=True)
        tabs=ctk.CTkFrame(shell,fg_color='#E9ECF3',corner_radius=0,height=45)
        tabs.pack(fill='x')
        self.tabs=ctk.CTkSegmentedButton(tabs,values=['日常长草','日常战斗','活动任务'],
                    command=self._set_profile,font=('Microsoft YaHei UI',14),height=38,
                    fg_color='#E9ECF3',selected_color=CARD,selected_hover_color=CARD,
                    unselected_color='#E9ECF3',unselected_hover_color='#DFE5F0',text_color=BLUE)
        self.tabs.pack(side='left',fill='x',expand=True,padx=14,pady=5); self.tabs.set('日常长草')
        self.button(tabs,'＋',self.open_recorder,width=38).pack(side='left',padx=10)
        self.editable.append(self.tabs)
        bar=ctk.CTkFrame(shell,fg_color=CARD,corner_radius=18,border_width=1,border_color='#E4E7EE')
        bar.pack(fill='x',padx=16,pady=14)
        self.label(bar,'资源类型',12).pack(side='left',padx=(16,8),pady=17)
        self.label(bar,'国服',13).pack(side='left',padx=(0,18))
        self.label(bar,'控制器类型',12).pack(side='left',padx=8)
        self.label(bar,'模拟器',13).pack(side='left',padx=(0,18))
        self.label(bar,'当前控制器',12).pack(side='left',padx=8)
        self.device_box=ctk.CTkComboBox(bar,variable=self.device_display,command=self.select_device,values=[],width=215,
                    font=('Microsoft YaHei UI',12),height=34,corner_radius=9,state='readonly')
        self.device_box.pack(side='left',fill='x',expand=True,padx=8)
        for text,cmd in [('⚙',self.connection_settings),('↻',self.devices),('链接',self.connect)]:
            b=self.button(bar,text,cmd,width=45); b.pack(side='left',padx=4); self.editable.append(b)
        self.editable.append(self.device_box)
        self.start_button=self.button(bar,'▶ 开始任务',self.run,True,width=116)
        self.start_button.pack(side='left',padx=(7,14)); self.editable.append(self.start_button)
        content=ctk.CTkFrame(shell,fg_color='transparent')
        content.pack(fill='both',expand=True,padx=16,pady=(0,14))
        for i in range(3): content.grid_columnconfigure(i,weight=1,uniform='column')
        content.grid_rowconfigure(0,weight=1)
        task_card,task_body,header=self.card(content,'任务列表')
        task_card.grid(row=0,column=0,sticky='nsew',padx=(0,10))
        self.button(header,'全选',lambda:self.select_all(True),width=43).pack(side='right',padx=2)
        self.button(header,'清空',lambda:self.select_all(False),width=43).pack(side='right',padx=2)
        self.task_scroll=ctk.CTkScrollableFrame(task_body,fg_color='transparent',corner_radius=0)
        self.task_scroll.pack(fill='both',expand=True)
        self.label(task_body,'勾选任务执行 · 点任务名修改设置',11,MUTED).pack(anchor='w',pady=(5,0))
        self.selected_count=self.label(task_body,'',12,MUTED); self.selected_count.pack(anchor='w')
        center=ctk.CTkFrame(content,fg_color='transparent')
        center.grid(row=0,column=1,sticky='nsew',padx=8)
        center.grid_columnconfigure(0,weight=1); center.grid_rowconfigure(0,weight=3); center.grid_rowconfigure(1,weight=2)
        setting_card,setting_body,_=self.card(center,'任务设置')
        setting_card.grid(row=0,column=0,sticky='nsew',pady=(0,12))
        self.settings_body=ctk.CTkScrollableFrame(setting_body,fg_color='transparent')
        self.settings_body.pack(fill='both',expand=True)
        description_card,desc_body,_=self.card(center,'任务说明')
        description_card.grid(row=1,column=0,sticky='nsew')
        self.detail_title=self.label(desc_body,'',16); self.detail_title.pack(anchor='w',pady=(0,10))
        self.task_info=self.label(desc_body,'',13,MUTED,justify='left',anchor='nw',wraplength=300)
        self.task_info.pack(fill='both',expand=True,anchor='nw')
        self.detail_status=self.label(desc_body,'',12,'#BC7B20',justify='left',wraplength=300)
        self.detail_status.pack(fill='x',pady=5)
        right=ctk.CTkFrame(content,fg_color='transparent'); right.grid(row=0,column=2,sticky='nsew',padx=(10,0))
        right.grid_columnconfigure(0,weight=1); right.grid_rowconfigure(0,weight=1); right.grid_rowconfigure(1,weight=1)
        preview_card,preview_body,phead=self.card(right,'实时视图')
        preview_card.grid(row=0,column=0,sticky='nsew',pady=(0,12))
        ctk.CTkSwitch(phead,text='',variable=self.live,command=self.save_preferences,width=43,
                     progress_color=BLUE).pack(side='right')
        self.canvas=tk.Canvas(preview_body,background='#EDF0F6',highlightthickness=0)
        self.canvas.pack(fill='both',expand=True)
        self.canvas.bind('<Configure>',lambda event:self.draw_image())
        self.label(preview_body,'竖屏 9:16 · 画面保持原始比例',11,MUTED).pack(pady=(5,0))
        log_card,log_body,lhead=self.card(right,'日志')
        log_card.grid(row=1,column=0,sticky='nsew')
        self.button(lhead,'清屏',self.clear_logs,width=44).pack(side='right',padx=2)
        self.button(lhead,'目录',lambda:os.startfile(ROOT/'logs'),width=44).pack(side='right',padx=2)
        self.logs=tk.Text(log_body,background=CARD,foreground=TEXT,relief='flat',borderwidth=0,
                           state='disabled',wrap='word',font=('Microsoft YaHei UI',-13),height=8,spacing1=3,spacing3=4)
        self.logs.pack(side='left',fill='both',expand=True)
        scroll=ctk.CTkScrollbar(log_body,command=self.logs.yview,width=10); scroll.pack(side='right',fill='y')
        self.logs.configure(yscrollcommand=scroll.set)
        self.logs.tag_configure('error',foreground='#D54646'); self.logs.tag_configure('success',foreground='#219E56')
        footer=ctk.CTkFrame(shell,fg_color='transparent',height=28); footer.pack(fill='x',padx=20,pady=(0,8))
        self.label(footer,'',12,MUTED,textvariable=self.status_text).pack(side='left')
        self.stop_button=self.button(footer,'■ 停止（F8）',self.engine.stop,width=116)
        self.stop_button.pack(side='right')
        self.label(footer,f'妮姬国服助手  v{VERSION}',11,MUTED).pack(side='right',padx=15)
        self.render_tasks(); self.focus_task(0)
        self.after(1500,self.preview_loop)

    def visible_indices(self):
        if self.profile.get()=='日常战斗':
            return [i for i,t in enumerate(self.tasks) if t.get('handler') in ('start_game','simulation','interception','tower','rookie','advise')]
        if self.profile.get()=='活动任务': return [i for i,t in enumerate(self.tasks) if not t.get('id','').startswith('cn_')]
        return [i for i,t in enumerate(self.tasks)
                if not t.get('handler','').startswith('event_') or t.get('handler') in ('event_daily','event_wisdom_daily')]

    def _set_profile(self,value):
        if self.busy: return
        self.profile.set(value); self.tabs.set(value); self.render_tasks()
        indices=self.visible_indices()
        if indices: self.focus_task(indices[0])

    def render_tasks(self):
        for child in self.task_scroll.winfo_children(): child.destroy()
        self.row_frames={}; self.row_states={}
        while len(self.checked)<len(self.tasks): self.checked.append(tk.BooleanVar(value=False))
        for i in self.visible_indices():
            row=ctk.CTkFrame(self.task_scroll,corner_radius=9,fg_color='#E2EAFC' if i==self.focused_task else 'transparent')
            row.pack(fill='x',pady=2); self.row_frames[i]=row
            cb=ctk.CTkCheckBox(row,text='',variable=self.checked[i],width=24,height=32,
                 checkbox_width=18,checkbox_height=18,corner_radius=5,fg_color=BLUE,
                 command=self.selection_changed)
            cb.pack(side='left',padx=(6,5),pady=3); self.editable.append(cb)
            name=self.tasks[i]['name'].split(' / ')[0].replace(' · ',' ')
            label=self.label(row,name,14,anchor='w',width=130); label.pack(side='left',fill='x',expand=True)
            label.bind('<Button-1>',lambda event,index=i:self.focus_task(index))
            state=self.label(row,self.task_states.get(i,'⚙'),12,MUTED,width=28)
            state.pack(side='right',padx=4); state.bind('<Button-1>',lambda event,index=i:self.focus_task(index))
            self.row_states[i]=state
        if not self.visible_indices():
            self.label(self.task_scroll,'暂无活动任务\n点击下方按钮采集',13,MUTED).pack(pady=40)
            self.button(self.task_scroll,'＋ 添加任务',self.open_recorder,True).pack(pady=10)
        self.update_count()

    def update_count(self):
        visible=self.visible_indices()
        self.selected_count.configure(text=f'已勾选 {sum(self.checked[i].get() for i in visible)} / {len(visible)} 项')

    def selection_changed(self):
        self.update_count(); self.save_preferences()

    def select_all(self,enabled):
        if self.busy: return
        for i in self.visible_indices(): self.checked[i].set(enabled)
        self.selection_changed()

    def save_preferences(self):
        if self.busy: return
        settings={**self.load_json(ROOT/'settings.json',{}),'adb':self.adb.get(),'serial':self.serial.get(),
                  'options':self.engine.options,'live_preview':self.live.get(),
                  'selected':[t.get('id') for i,t in enumerate(self.tasks) if self.checked[i].get()]}
        (ROOT/'settings.json').write_text(json.dumps(settings,ensure_ascii=False,indent=2),encoding='utf-8')

    def option(self,parent,label,key,values=None,default=None):
        self.label(parent,label,12).pack(anchor='w',pady=(16,6))
        var=tk.StringVar(value=str(self.engine.options.get(key,default)))
        def save(*args):
            if self.busy: return
            self.engine.options[key]=var.get(); self.save_preferences()
        if values:
            widget=ctk.CTkOptionMenu(parent,variable=var,values=list(map(str,values)),command=save,
                  height=34,fg_color='#EEF1F7',button_color='#E1E6F0',button_hover_color='#CFD8EA',
                  text_color=TEXT,font=('Microsoft YaHei UI',12),dropdown_font=('Microsoft YaHei UI',12))
        else:
            widget=ctk.CTkEntry(parent,textvariable=var,height=35,font=('Microsoft YaHei UI',12))
            var.trace_add('write',save)
        widget.pack(fill='x'); self.editable.append(widget)

    def focus_task(self,index):
        self.focused_task=index
        for i,row in self.row_frames.items(): row.configure(fg_color='#E2EAFC' if i==index else 'transparent')
        for child in self.settings_body.winfo_children(): child.destroy()
        task=self.tasks[index]; kind=task.get('handler')
        self.label(self.settings_body,task['name'].split(' / ')[0],16,anchor='w').pack(fill='x',pady=(4,10))
        switch=ctk.CTkSwitch(self.settings_body,text='启用此任务',variable=self.checked[index],
                            command=self.selection_changed,progress_color=BLUE,font=('Microsoft YaHei UI',12))
        switch.pack(anchor='w',pady=(0,8)); self.editable.append(switch)
        if kind in ('event_daily','event_wisdom_daily'):
            prefix='wisdom_' if kind=='event_wisdom_daily' else 'event_'
            for key,name in [('signin','领取签到'),('story','STORY 关卡'),('challenge','挑战关卡'),('missions','最后领取活动任务')]:
                var=tk.BooleanVar(value=self.engine.options.get(prefix+key,True))
                def save(key=key,var=var):
                    self.engine.options[prefix+key]=var.get(); self.save_preferences()
                cb=ctk.CTkCheckBox(self.settings_body,text=name,variable=var,command=save,font=('Microsoft YaHei UI',12),checkbox_width=18,checkbox_height=18,fg_color=BLUE)
                cb.pack(anchor='w',pady=6); self.editable.append(cb)
            if kind=='event_daily':
                self.option(self.settings_body,'STORY 章节','event_story_part',['I','II'],'I')
            else:
                self.option(self.settings_body,'关卡难度','wisdom_difficulty',['当前','普通','困难'],'当前')
            self.option(self.settings_body,'关卡方式',prefix+'story_mode',['快速战斗','推未通关关卡'],'快速战斗')
            self.option(self.settings_body,'快速战斗关卡',prefix+'farm_stage',['11','12'],'11')
            self.label(self.settings_body,('WISDOM SPRING：ENTER → 关卡 → 挑战 → 任务\n首页没有独立签到入口时跳过\n使用现有门票，不购买次数' if kind=='event_wisdom_daily' else '从大厅或 UNBREAKABLE SPHERE 活动首页开始\n签到 → STORY → 挑战 → 活动任务\n日常与活动页共用勾选和设置\n使用已有门票，沿用当前队伍\n未开放章节跳过；自动战斗需在游戏开启\nSTORY II 开放后优先推进新关卡；无新关卡时按设置刷取'),12,MUTED,justify='left',wraplength=280).pack(anchor='w',pady=14)
        elif kind == 'event_push':
            self.option(self.settings_body,'最多开始关卡数','event_push_count',[1,3,5,12,24],12)
            self.option(self.settings_body,'跳过剧情','event_skip_story',['否','是'],'否')
            self.label(self.settings_body,'先手动进入活动，选择首个未通关关卡\n从准备页或战后下一关页面启动\n沿用当前队伍，需开启自动射击和爆裂\n不买门票；失败、锁定、票不足时停止\n活动地图选关尚未适配',12,MUTED,justify='left',wraplength=280).pack(anchor='w',pady=18)
        elif kind in ('interception','tower','rookie'):
            maxcount=5 if kind=='rookie' else 3
            self.option(self.settings_body,'最多挑战次数',kind+'_count',range(1,maxcount+1),maxcount)
            if kind=='rookie':
                self.option(self.settings_body,'挑战第几个对手','rookie_opponent',[1,2,3],3)
            if kind=='interception':
                quick=self.button(self.settings_body,'▶ 运行拦截战',lambda:self.run_task(index),primary=True)
                quick.pack(fill='x',pady=(20,8)); self.editable.append(quick)
                self.label(self.settings_body,'优先快速战斗；不可用时进入实际战斗\n沿用当前队伍，请开启自动射击和爆裂\n关闭奖励后核对剩余次数\n次数用完结束，不购买次数',12,MUTED,justify='left',wraplength=280).pack(anchor='w',pady=12)
            else:
                self.label(self.settings_body,'队伍：沿用游戏当前队伍\n免费次数不足时结束\n请先开启自动射击 / 自动爆裂',12,MUTED,justify='left',wraplength=280).pack(anchor='w',pady=18)
        elif kind=='simulation':
            self.option(self.settings_body,'难度区域','simulation_region',['当前',1,2,3,4,5],'当前')
            self.option(self.settings_body,'难度分区','simulation_level',['当前','A','B','C'],'当前')
            self.label(self.settings_body,'方式：快速模拟\n今日已完成时自动跳过',12,MUTED,justify='left').pack(anchor='w',pady=18)
        elif kind=='advise':
            self.label(self.settings_body,'沿用游戏批量咨询名单\n批量咨询 → 检查角色花絮红点 → 跳过剧情领奖\n次数用完仍检查花絮，完成后返回大厅\n不送礼、不购买次数，不进入锁定章节',12,MUTED,justify='left',wraplength=280).pack(anchor='w',pady=18)
        elif kind=='missions':
            self.label(self.settings_body,'领取的奖励类别',12).pack(anchor='w',pady=(14,6))
            for key,name in [('daily','每日'),('weekly','每周'),('main','主线'),('achievement','成就'),('pass','MISSION PASS 任务与奖励')]:
                var=tk.BooleanVar(value=self.engine.options.get('mission_'+key,True))
                def save(key=key,var=var):
                    self.engine.options['mission_'+key]=var.get(); self.save_preferences()
                cb=ctk.CTkCheckBox(self.settings_body,text=name,variable=var,command=save,
                                  font=('Microsoft YaHei UI',12),checkbox_width=18,checkbox_height=18,fg_color=BLUE)
                cb.pack(anchor='w',pady=8); self.editable.append(cb)
        else:
            policy={'start_game':'自动定位所选模拟器中的国服游戏\n启动 → 点击开始 → 公告与签到 → 确认大厅\n游戏图标位置改变也可启动\n需要账号登录时停止并提示',
                    'wipe':'仅使用当日免费歼灭\n当前售价大于零时跳过',
                    'shop':'购买零价商品 → 免费刷新 → 再购买\n免费刷新用完时跳过\n不执行付费刷新或购买',
                    'shop_packs':'每日 → 每周 → 每月免费礼包\n领取 STEP UP 当前免费阶段\n核实剩余0/1后返回大厅',
                    'dispatch':'领取已完成派遣，一键派遣\n不重置目录、不付费刷新',
                    'arena_reward':'领取特殊竞技场累积奖励\n不发起特殊竞技场挑战'}.get(kind,'自动识别任务页面\n完成后确认返回大厅')
            self.label(self.settings_body,policy,12,MUTED,justify='left',wraplength=280).pack(anchor='w',pady=20)
        self.label(self.settings_body,'设置自动保存',11,MUTED).pack(anchor='w',pady=(12,3))
        self.detail_title.configure(text=task['name'].split(' / ')[0])
        self.task_info.configure(text=task.get('description','每次操作前识别当前页面，完成后检查最终画面。'))
        self.detail_status.configure(text='验证状态：'+task.get('status','自定义任务')+
             ('\n实际挑战流程仍需验证。' if task.get('status')=='实验功能' else ''))
        if self.busy: self.lock_controls(True)

    def lock_controls(self,locked):
        for widget in self.editable:
            try:
                widget.configure(state='disabled' if locked else ('readonly' if widget==self.device_box else 'normal'))
            except tk.TclError: pass
        self.stop_button.configure(state='normal' if locked else 'disabled')
        self.start_button.configure(text='■ 停止任务' if locked else '▶ 开始任务',
                                    command=self.engine.stop if locked else self.run,state='normal')

    def clear_logs(self):
        self.logs.configure(state='normal'); self.logs.delete('1.0','end'); self.logs.configure(state='disabled')

    def connection_settings(self):
        if self.busy: return
        window=ctk.CTkToplevel(self); window.title('连接设置'); window.geometry('590x240'); window.transient(self)
        self.label(window,'雷电 ADB 路径',14).pack(anchor='w',padx=22,pady=(20,8))
        row=ctk.CTkFrame(window,fg_color='transparent'); row.pack(fill='x',padx=22)
        ctk.CTkEntry(row,textvariable=self.adb,height=36,width=420).pack(side='left',fill='x',expand=True)
        self.button(row,'浏览',self.browse,width=70).pack(side='left',padx=(8,0))
        self.label(window,'启动雷电后点击自动检测，再选择对应的模拟器实例。\n游戏要求：国服、竖屏 9:16、已登录大厅。',12,MUTED,justify='left').pack(anchor='w',padx=22,pady=14)
        self.button(window,'自动检测',self.devices,width=110).pack(side='left',padx=22,pady=12)
        self.button(window,'保存并关闭',lambda:(self.save_preferences(),window.destroy()),True,width=110).pack(side='right',padx=22,pady=12)

    def preview_loop(self):
        if self.engine.controller and self.live.get() and not self.preview_busy:
            self.preview_busy=True
            def capture():
                try: self.events.put(('image',self.engine.screenshot()))
                except Exception: pass
                finally: self.preview_busy=False
            threading.Thread(target=capture,daemon=True).start()
        self.after(3000,self.preview_loop)

    def open_recorder(self):
        if self.busy: return
        if getattr(self,'recorder',None) and self.recorder.winfo_exists(): self.recorder.lift(); return
        self.recorder=ctk.CTkToplevel(self); self.recorder.title('活动 / 自定义任务采集'); self.recorder.geometry('760x650')
        left=ctk.CTkFrame(self.recorder,width=270); left.pack(side='left',fill='y',padx=12,pady=12)
        self.label(left,'任务采集',18).pack(pady=12)
        self.label(left,'截图后框选固定按钮。\n手动进入下一页继续采集。\n末尾添加完成画面检查。',12,MUTED,justify='left').pack(padx=12,pady=8)
        for text,value in [('识别并点击','click'),('仅检查完成画面','check')]:
            ctk.CTkRadioButton(left,text=text,variable=self.action,value=value).pack(anchor='w',padx=14,pady=6)
        self.button(left,'刷新截图',self.capture,width=220).pack(pady=10)
        self.step_list=tk.Listbox(left,height=12,relief='flat'); self.step_list.pack(fill='both',expand=True,padx=12,pady=8)
        for text,cmd in [('撤销步骤',self.undo),('保存任务',self.save_task),('清空',self.clear_draft)]:
            self.button(left,text,cmd,width=220).pack(pady=4)
        self.recorder_canvas=tk.Canvas(self.recorder,background='#EDF0F6',highlightthickness=0)
        self.recorder_canvas.pack(side='right',fill='both',expand=True,padx=12,pady=12)
        self.recorder_canvas.bind('<Configure>',lambda event:self.draw_image())
        self.recorder_canvas.bind('<ButtonPress-1>',self.begin_crop)
        self.recorder_canvas.bind('<B1-Motion>',self.move_crop)
        self.recorder_canvas.bind('<ButtonRelease-1>',self.end_crop)
        self.refresh_steps(); self.draw_image()
