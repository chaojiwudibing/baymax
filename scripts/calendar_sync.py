"""Portable ICS export and conditional CalDAV updates. No provider account is required for export."""
import argparse
import base64
import hashlib
import json
import os
import re
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit, quote
from urllib.request import Request, build_opener, HTTPRedirectHandler
from urllib.error import HTTPError
from reminder_bridge import private_json, instant

class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs): return None

def escape(s):
    return str(s).replace('\\','\\\\').replace('\r\n','\n').replace('\r','\n').replace('\n','\\n').replace(';','\\;').replace(',','\\,')

def fold(line):
    parts, current = [], ''
    for c in line:
        if len((current+c).encode('utf-8')) > 75:
            parts.append(current); current=' '+c
        else: current+=c
    return '\r\n'.join(parts+[current])

def stamp(t): return t.astimezone(timezone.utc).strftime('%Y%m%dT%H%M%SZ')

def validate(plan):
    if plan.get('status') != 'ready' or plan.get('conflicts'):
        raise ValueError('请先解决计划冲突再导出或同步日历')
    if type(plan.get('revision')) is not int or plan['revision'] < 1: raise ValueError('Invalid revision')
    seen=set()
    for e in plan['events']:
        if not re.fullmatch('[a-f0-9]{32}', e.get('id','')) or e['id'] in seen: raise ValueError('Invalid event ID')
        seen.add(e['id']); instant(e['at'])
        if type(e['minutes']) is not int or not 1<=e['minutes']<=240: raise ValueError('Invalid duration')
        if type(e.get('reminder_minutes',10)) is not int or not 0<=e.get('reminder_minutes',10)<=1440: raise ValueError('Invalid alarm')
        if not isinstance(e['title'],str) or not isinstance(e['body'],str): raise ValueError('Invalid content')
    return plan

def calendar(plan, events=None, details=True):
    validate(plan)
    lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//Baymax//Life Plan//ZH-CN','CALSCALE:GREGORIAN','X-WR-CALNAME:'+escape(plan['title'] if details else 'Baymax')]
    for e in plan['events'] if events is None else events:
        t=instant(e['at'])
        lines+=['BEGIN:VEVENT','UID:'+e['id']+'@baymax.local','SEQUENCE:'+str(plan['revision']),
                'DTSTAMP:'+stamp(instant(plan['updated_at'])), 'DTSTART:'+stamp(t),'DTEND:'+stamp(t+timedelta(minutes=e['minutes'])),
                'SUMMARY:'+escape(e['title'] if details else '健康生活计划'),
                'DESCRIPTION:'+escape(e['body'] if details else '请查看本地个人计划；未上传健康详情。'),
                'STATUS:CONFIRMED','TRANSP:TRANSPARENT','BEGIN:VALARM','ACTION:DISPLAY',
                'DESCRIPTION:'+escape(e['title'] if details else '健康生活计划'),
                'TRIGGER:-PT'+str(e.get('reminder_minutes',10))+'M','END:VALARM','END:VEVENT']
    lines+=['END:VCALENDAR']
    return ('\r\n'.join(fold(x) for x in lines)+'\r\n').encode('utf-8')

class CalDAV:
    def __init__(self, config):
        self.base=config['calendar_url'].rstrip('/')+'/'
        url=urlsplit(self.base)
        if url.scheme!='https' or not url.hostname or url.username or url.password or url.query or url.fragment:
            raise ValueError('Use an HTTPS CalDAV collection URL without credentials or query')
        user=config['username']; password=os.environ.get(config.get('password_env','BAYMAX_CALDAV_PASSWORD'))
        if not password: raise ValueError('Set the configured password environment variable; never save it in the plan')
        self.auth='Basic '+base64.b64encode((user+':'+password).encode()).decode()
        self.target=hashlib.sha256((self.base+'|'+user).encode()).hexdigest()
    def call(self, method, key='', data=None, headers=None):
        if key and not re.fullmatch(r'[a-f0-9]{32}\.ics',key): raise ValueError('Invalid calendar resource')
        req=Request(self.base+key, data=data, method=method, headers={'Authorization':self.auth,**(headers or {})})
        try:
            with build_opener(NoRedirect()).open(req,timeout=25) as r:
                return r.status, dict(r.headers), r.read(4*1024*1024)
        except HTTPError as e:
            if e.code in (404,409,412): return e.code,dict(e.headers),b''
            raise RuntimeError(f'CalDAV HTTP {e.code}; check account, permission and collection URL') from None
    def inspect(self):
        body=b'<?xml version="1.0"?><d:propfind xmlns:d="DAV:" xmlns:c="urn:ietf:params:xml:ns:caldav"><d:prop><d:displayname/><d:resourcetype/><d:current-user-principal/><c:calendar-home-set/></d:prop></d:propfind>'
        status,_,data=self.call('PROPFIND',data=body,headers={'Depth':'1','Content-Type':'application/xml'})
        if status!=207: raise ValueError('Server did not return a CalDAV resource listing')
        root=ET.fromstring(data)
        return [{'href':r.findtext('{DAV:}href'),'name':r.findtext('.//{DAV:}displayname'),
                 'is_calendar':r.find('.//{urn:ietf:params:xml:ns:caldav}calendar') is not None,
                 'principal':r.findtext('.//{DAV:}current-user-principal/{DAV:}href'),
                 'home':r.findtext('.//{urn:ietf:params:xml:ns:caldav}calendar-home-set/{DAV:}href')} for r in root.findall('{DAV:}response')]

def etag(headers): return next((v for k,v in headers.items() if k.lower()=='etag'),None)

def sync(plan, state_path, client, details=True, now=None):
    validate(plan); now=now or datetime.now(timezone.utc)
    path=Path(state_path)
    # An exclusive lock prevents concurrent workers from losing accepted writes.
    path.parent.mkdir(parents=True,exist_ok=True)
    lock=path.with_suffix(path.suffix+'.lock')
    try: fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    except FileExistsError: raise ValueError('另一个同步正在运行；若进程已退出，先核对云端再清理锁文件') from None
    os.close(fd)
    result={'created':0,'updated':0,'deleted':0,'unchanged':0,'conflicts':[],'past_preserved':0}
    try:
        state=json.loads(path.read_text()) if path.exists() else {'target':client.target,'plan':plan['id'],'events':{}}
        if state['target']!=client.target or state['plan']!=plan['id']: raise ValueError('同步状态属于其他账号、日历或计划')
        if state.get('revision',0)>plan['revision']: raise ValueError('拒绝用旧版本覆盖新的云端计划')
        def save(): private_json(path,state)
        active={e['id']:e for e in plan['events']}
        for key,e in active.items():
            if instant(e['at'])<now: result['past_preserved']+=1; continue
            payload=calendar(plan,[e],details); digest=hashlib.sha256(payload).hexdigest()
            previous=state['events'].get(key)
            status,headers,remote=client.call('GET',key+'.ics')
            remote_etag=etag(headers)
            if status not in (200,404): raise RuntimeError('Cannot read destination event')
            if status==200 and (remote==payload or (previous and previous['hash']==digest and remote_etag and previous['etag']==remote_etag)):
                state['events'][key]={'etag':remote_etag,'hash':digest,'at':e['at']}; save(); result['unchanged']+=1; continue
            if status==200 and (not previous or not remote_etag or remote_etag!=previous['etag']):
                result['conflicts'].append(key+': 云端存在或已被手工修改，未覆盖');continue
            if status==404 and previous:
                result['conflicts'].append(key+': 云端已删除，未自动重建');continue
            condition={'If-Match':remote_etag} if status==200 else {'If-None-Match':'*'}
            code,head,_=client.call('PUT',key+'.ics',payload,{'Content-Type':'text/calendar; charset=utf-8',**condition})
            if code in (409,412): result['conflicts'].append(key+': 同步期间发生修改');continue
            if code not in (200,201,204): raise RuntimeError('Calendar write was not accepted')
            newtag=etag(head)
            if not newtag:
                # Do not adopt a concurrently edited remote body as our own.
                _,head,body=client.call('GET',key+'.ics');newtag=etag(head)
                if body!=payload: result['conflicts'].append(key+': 写入结果待核对');continue
            state['events'][key]={'etag':newtag,'hash':digest,'at':e['at']}; save()
            result['updated' if previous else 'created']+=1
        for key,old in list(state['events'].items()):
            if key in active or instant(old['at'])<now: continue
            if not old['etag']: result['conflicts'].append(key+': 缺少删除前置条件');continue
            code,_,_=client.call('DELETE',key+'.ics',headers={'If-Match':old['etag']})
            if code in (404,200,204): del state['events'][key]; save(); result['deleted']+=1
            elif code in (409,412): result['conflicts'].append(key+': 已修改的云端事件未删除')
            else: raise RuntimeError('Calendar deletion was not accepted')
        if not result['conflicts']: state['revision']=plan['revision'];save()
        return result
    finally: lock.unlink()

def main():
    p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
    c=sub.add_parser('export');c.add_argument('--plan',required=True);c.add_argument('--out',required=True);c.add_argument('--private-titles',action='store_true')
    c=sub.add_parser('inspect');c.add_argument('--config',required=True)
    c=sub.add_parser('sync');c.add_argument('--plan',required=True);c.add_argument('--config',required=True);c.add_argument('--state',required=True);c.add_argument('--allow-upload',action='store_true');c.add_argument('--private-titles',action='store_true')
    a=p.parse_args()
    if a.command=='inspect': print(json.dumps(CalDAV(json.loads(Path(a.config).read_text())).inspect(),ensure_ascii=False));return 0
    plan=json.loads(Path(a.plan).read_text())
    if a.command=='export':
        payload=calendar(plan,details=not a.private_titles)
        with os.fdopen(os.open(a.out,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600),'wb') as f:f.write(payload)
        print('ICS 已生成；尚未导入手机，不会自动更新。');return 0
    if not a.allow_upload: p.error('先获得上传计划到用户指定日历的授权，再传 --allow-upload')
    result=sync(plan,a.state,CalDAV(json.loads(Path(a.config).read_text())),not a.private_titles)
    print(json.dumps(result,ensure_ascii=False));return 1 if result['conflicts'] else 0

if __name__=='__main__':
    try: raise SystemExit(main())
    except (ValueError,KeyError,OSError,RuntimeError) as e: print('日历操作未完成：'+str(e),file=sys.stderr);raise SystemExit(2)
