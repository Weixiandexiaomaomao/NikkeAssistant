"""Daily wall-clock scheduling with durable minute-level deduplication."""
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path
from uuid import uuid4

DEFAULT_TIMES=('04:01','12:01','20:01','02:27','08:01','18:01','00:01','02:27')

def normalize_schedule(value):
    value=value if isinstance(value,dict) else {}
    slots=value.get('slots',[])
    result={'enabled':bool(value.get('enabled',False)),
            'show_window':bool(value.get('show_window',True)),
            'wait_when_busy':bool(value.get('wait_when_busy',True)), 'slots':[]}
    for index,default in enumerate(DEFAULT_TIMES):
        slot=slots[index] if index<len(slots) and isinstance(slots[index],dict) else {}
        clock=slot.get('time',default)
        if not isinstance(clock,str) or not re.fullmatch(r'(?:[01]\d|2[0-3]):[0-5]\d',clock):
            raise ValueError(f'定时 {index+1} 的时间无效，请填写 00:00～23:59')
        result['slots'].append({'enabled':bool(slot.get('enabled',False)),'time':clock})
    return result

class DailySchedule:
    def __init__(self,path): self.path=Path(path)
    def read(self):
        if not self.path.exists(): return {'fired':{},'pending':None}
        state=json.loads(self.path.read_text(encoding='utf-8'))
        if not isinstance(state,dict) or not isinstance(state.get('fired'),dict):
            raise ValueError('定时记录损坏，请检查 runtime/schedule-state.json')
        return state
    def save(self,state):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        temporary=self.path.with_name(self.path.name+'.'+uuid4().hex+'.tmp')
        temporary.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
        os.replace(temporary,self.path)
    def poll(self,config,now,busy):
        state=self.read();pending=state.get('pending')
        if not config['enabled']:
            if pending: state['pending']=None;self.save(state)
            return None
        day=now.strftime('%Y-%m-%d');clock=now.strftime('%H:%M');key=day+' '+clock
        if pending and not pending.startswith(day+' '):
            state['pending']=None;pending=None;self.save(state)
        times={slot['time'] for slot in config['slots'] if slot['enabled']}
        fired=state['fired'].get(day,[])
        due=clock in times and clock not in fired
        if due:
            state['fired'][day]=[*fired,clock]
            state['fired']={date:state['fired'][date] for date in sorted(state['fired'])[-7:]}
            state['pending']=key if busy and config['wait_when_busy'] else None
            self.save(state)
            return ('queued' if busy and config['wait_when_busy'] else 'skipped' if busy else 'run',key)
        if pending and not busy:
            state['pending']=None;self.save(state)
            return ('run',pending)
        return None
    def next_time(self,config,now):
        if not config['enabled']: return None
        candidates=[]
        fired=self.read()['fired'].get(now.strftime('%Y-%m-%d'),[])
        for slot in config['slots']:
            if not slot['enabled']:continue
            hour,minute=map(int,slot['time'].split(':'))
            when=now.replace(hour=hour,minute=minute,second=0,microsecond=0)
            if when<now.replace(second=0,microsecond=0) or slot['time'] in fired:
                when+=timedelta(days=1)
            candidates.append(when)
        return min(candidates) if candidates else None
