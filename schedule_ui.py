"""Connection and daily schedule settings, in the assistant itself."""
from datetime import datetime
import tkinter as tk
import customtkinter as ctk
from daily_schedule import DailySchedule, normalize_schedule
from engine import exclusive_device
from portable import ROOT
from emulator_launch import normalize_emulator, discover_emulator
from tkinter import filedialog

class ScheduleUI:
    def init_schedule(self,settings,active=True):
        try:self.schedule_config=normalize_schedule(settings.get('schedule'))
        except ValueError as error:
            self.schedule_config=normalize_schedule({});self.log(str(error))
        self.scheduler=DailySchedule(ROOT/'runtime/schedule-state.json')
        self.schedule_error=None
        if active:self.after(1000,self.schedule_tick)

    def schedule_tick(self):
        try:
            with exclusive_device('schedule:'+str(ROOT)):
                action=self.scheduler.poll(self.schedule_config,datetime.now(),self.busy)
            if action:
                kind,key=action
                if kind=='queued':self.log(f'定时 {key}：当前忙碌，等待结束；多个定时合并为一次待执行任务')
                elif kind=='skipped':self.log(f'定时 {key}：当前忙碌，已跳过本次')
                else:
                    self.log(f'定时 {key}：开始运行当前勾选任务')
                    if self.schedule_config['show_window']:
                        self.deiconify();self.lift()
                    selected=[task for index,task in enumerate(self.tasks) if self.checked[index].get()]
                    self.run_tasks(selected)
            if hasattr(self,'schedule_status'):
                when=self.scheduler.next_time(self.schedule_config,datetime.now())
                self.schedule_status.configure(text=('下次定时 '+when.strftime('%m-%d %H:%M')) if when else '定时未启用')
            self.schedule_error=None
        except Exception as error:
            if str(error)!=self.schedule_error:
                self.log('定时检查失败：'+str(error));self.schedule_error=str(error)
        self.after(1000,self.schedule_tick)

    def open_settings(self,page='定时执行'):
        if self.busy:return
        if getattr(self,'settings_window',None) and self.settings_window.winfo_exists():
            self.settings_window.lift();self.settings_tabs.set(page);return
        window=ctk.CTkToplevel(self);self.settings_window=window
        window.title('助手设置');window.geometry('720x650');window.transient(self)
        tabs=ctk.CTkTabview(window,fg_color='#FAFAFC');tabs.pack(fill='both',expand=True,padx=16,pady=12)
        self.settings_tabs=tabs
        connection=tabs.add('连接设置');schedule=tabs.add('定时执行');tabs.set(page)
        connection_scroll=ctk.CTkScrollableFrame(connection,fg_color='transparent')
        connection_scroll.pack(fill='both',expand=True);connection=connection_scroll
        self.label(connection,'雷电 ADB 路径').pack(anchor='w',padx=20,pady=(20,8))
        row=ctk.CTkFrame(connection,fg_color='transparent');row.pack(fill='x',padx=20)
        ctk.CTkEntry(row,textvariable=self.adb,height=36).pack(side='left',fill='x',expand=True)
        self.button(row,'浏览',self.browse,width=70).pack(side='left',padx=(8,0))
        config=self.emulator_config
        exe=tk.StringVar(value=config['path'] or discover_emulator(self.adb.get()))
        params=tk.StringVar(value=config['arguments']);index=tk.StringVar(value=config['index'])
        auto=tk.BooleanVar(value=config['auto_start']);game=tk.BooleanVar(value=config['auto_game'])
        self.label(connection,'模拟器程序路径（找不到时手动选择）').pack(anchor='w',padx=20,pady=(14,8))
        row=ctk.CTkFrame(connection,fg_color='transparent');row.pack(fill='x',padx=20)
        ctk.CTkEntry(row,textvariable=exe,height=36).pack(side='left',fill='x',expand=True)
        def browse_emulator():
            path=filedialog.askopenfilename(parent=window,title='选择模拟器程序',filetypes=[('程序','*.exe')])
            if path:exe.set(path)
        self.button(row,'浏览',browse_emulator,width=70).pack(side='left',padx=(8,0))
        for text,var in [('雷电实例编号（在多开器中查看）',index),('设备地址（例如 emulator-5558）',self.serial),('额外启动参数（雷电默认留空，按实例编号启动）',params)]:
            self.label(connection,text,12).pack(anchor='w',padx=20,pady=(10,4))
            ctk.CTkEntry(connection,textvariable=var,height=32).pack(fill='x',padx=20)
        ctk.CTkCheckBox(connection,text='设备未就绪时自动启动模拟器',variable=auto).pack(anchor='w',padx=20,pady=(12,8))
        ctk.CTkCheckBox(connection,text='运行任务前自动启动游戏',variable=game).pack(anchor='w',padx=20,pady=8)
        self.label(connection,'手动和定时任务都会等待 Android 启动完成，再连接并启动游戏。\n模拟器已运行时直接连接；可停止等待。修改后请保存连接设置。',12,justify='left').pack(anchor='w',padx=20,pady=10)
        self.button(connection,'自动检测',self.devices,width=110).pack(anchor='w',padx=20)
        connection_notice=self.label(connection,'',12);connection_notice.pack(anchor='w',padx=20,pady=6)
        def save_connection():
            try:
                path=exe.get().strip()
                from pathlib import Path
                if path and not Path(path).is_file():raise ValueError('模拟器程序路径不存在，请重新选择。')
                value=normalize_emulator({'path':path,'arguments':params.get(),'index':index.get().strip(),'auto_start':auto.get(),'auto_game':game.get()},self.serial.get())
                if value['index'] and not value['index'].isdigit():raise ValueError('雷电实例编号须为非负整数。')
                self.emulator_config=value;self.save_preferences()
                self.device_display.set(self.serial.get());connection_notice.configure(text='连接与启动设置已保存',text_color='#219E56')
            except Exception as error:connection_notice.configure(text=str(error),text_color='#D54646')
        self.button(connection,'保存连接设置',save_connection,True,width=140).pack(anchor='w',padx=20,pady=8)
        config=self.schedule_config
        enabled=tk.BooleanVar(value=config['enabled']);show=tk.BooleanVar(value=config['show_window'])
        wait=tk.BooleanVar(value=config['wait_when_busy'])
        for title,var in [('启用每日定时执行',enabled),('定时启动前显示助手窗口',show),('忙碌时等待当前队列结束，再运行一次',wait)]:
            ctk.CTkCheckBox(schedule,text=title,variable=var,font=('Microsoft YaHei UI',14)).pack(anchor='w',padx=20,pady=9)
        grid=ctk.CTkFrame(schedule,fg_color='transparent');grid.pack(fill='x',padx=14,pady=10)
        for col in range(2):grid.grid_columnconfigure(col,weight=1)
        variables=[]
        for index,slot in enumerate(config['slots']):
            block=ctk.CTkFrame(grid,fg_color='transparent');block.grid(row=index%4,column=index//4,sticky='w',padx=6,pady=9)
            on=tk.BooleanVar(value=slot['enabled']);hour,minute=slot['time'].split(':')
            h=tk.StringVar(value=hour);m=tk.StringVar(value=minute);variables.append((on,h,m))
            ctk.CTkCheckBox(block,text=f'定时 {index+1}',variable=on,width=96,font=('Microsoft YaHei UI',13)).pack(side='left')
            ctk.CTkEntry(block,textvariable=h,width=48,justify='center').pack(side='left')
            self.label(block,'：').pack(side='left')
            ctk.CTkEntry(block,textvariable=m,width=48,justify='center').pack(side='left')
        self.label(schedule,'按电脑本地时间，每天重复。助手须保持运行。\n到点按连接设置启动模拟器与游戏，再运行勾选任务。\n同一时间不重复启动，错过的时间不补跑。设置保存后生效。',12,justify='left',wraplength=650).pack(anchor='w',padx=20,pady=12)
        notice=self.label(schedule,'',12);notice.pack(anchor='w',padx=20)
        def save():
            if self.busy:notice.configure(text='任务执行中，请结束后保存。');return
            try:
                slots=[]
                for on,h,m in variables:
                    if not h.get().isdigit() or not m.get().isdigit():raise ValueError('小时和分钟须为数字')
                    slots.append({'enabled':on.get(),'time':f'{int(h.get()):02d}:{int(m.get()):02d}'})
                value=normalize_schedule({'enabled':enabled.get(),'show_window':show.get(),'wait_when_busy':wait.get(),'slots':slots})
                if value['enabled'] and not any(s['enabled'] for s in value['slots']):raise ValueError('请至少勾选一个定时')
                old=self.schedule_config;self.schedule_config=value
                try:self.save_preferences()
                except Exception:self.schedule_config=old;raise
                notice.configure(text='定时设置已保存',text_color='#219E56')
            except Exception as error:notice.configure(text=str(error),text_color='#D54646')
        self.button(schedule,'保存定时设置',save,True,width=140).pack(anchor='e',padx=20,pady=10)
