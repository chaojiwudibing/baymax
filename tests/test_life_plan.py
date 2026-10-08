import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from life_plan import compile_plan, library, local_time
from calendar_sync import calendar, sync
from zoneinfo import ZoneInfo

class FakeDAV:
    target='test-account-calendar'
    def __init__(self): self.items={};self.n=0;self.writes=[];self.uncertain=False
    def call(self,method,key='',data=None,headers=None):
        old=self.items.get(key);headers=headers or {}
        if method=='GET':return (200,{'ETag':old[0]},old[1]) if old else (404,{},b'')
        if headers.get('If-None-Match')=='*' and old:return 412,{},b''
        if 'If-Match' in headers and (not old or old[0]!=headers['If-Match']):return 412,{},b''
        if method=='PUT':
            self.n+=1;tag='"%d"'%self.n;self.items[key]=(tag,data);self.writes.append((method,key))
            if self.uncertain:self.uncertain=False;raise TimeoutError('response lost')
            return 201,{'ETag':tag},b''
        if method=='DELETE':
            if key not in self.items:return 404,{},b''
            del self.items[key];self.writes.append((method,key));return 204,{},b''
        raise AssertionError(method)

class LifePlans(unittest.TestCase):
    def setUp(self):
        self.modules=library()['modules'];self.req=dict(id='test-period',title='合成测试',start='2030-01-01',timezone='Asia/Shanghai',suitability_confirmed=True,selections=[dict(module='daily-reflection')])
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.state=Path(self.temp.name)/'state.json';self.dav=FakeDAV();self.now=datetime(2029,1,1,tzinfo=timezone.utc)
    def plan(self):return compile_plan(self.req,self.modules)
    def test_month_and_revision_stable_identity(self):
        p=self.plan();self.assertEqual(len(p['days']),30);self.assertEqual(len(p['events']),30);self.assertEqual(p['days'][-1]['date'],'2030-01-30')
        self.req['selections'][0]['overrides']={'record':{'time':'20:00'}}
        q=compile_plan(self.req,self.modules,p);self.assertEqual(q['revision'],2);self.assertEqual([e['id'] for e in p['events']],[e['id'] for e in q['events']]);self.assertNotEqual(p['events'][0]['at'],q['events'][0]['at'])
        self.req['start']='2030-02-01'
        with self.assertRaises(ValueError):compile_plan(self.req,self.modules,p)
    def test_selection_conflict_and_source_gate(self):
        self.req['selections'].append(dict(module='weekly-review',overrides={'review':{'time':'21:00'}}));p=self.plan();self.assertEqual(len(p['conflicts']),4)
        with self.assertRaises(ValueError):calendar(p)
        self.req['selections']=[dict(module='creator-7618962209967965617')]
        with self.assertRaises(ValueError):self.plan()
        self.req['selections']=[dict(module='daily-reflection',actions=['made-up'])]
        with self.assertRaises(ValueError):self.plan()
    def test_dst_and_unknown_timezone(self):
        self.req.update(start='2030-03-01',timezone='America/New_York');p=self.plan();self.assertTrue(p['events'][0]['at'].endswith('-05:00'));self.assertTrue(p['events'][-1]['at'].endswith('-04:00'))
        with self.assertRaises(ValueError):local_time('2030-03-10','02:30',ZoneInfo('America/New_York'))
        with self.assertRaises(ValueError):local_time('2030-11-03','01:30',ZoneInfo('America/New_York'))
    def test_ics_unicode_escaping_alarms_and_no_profile(self):
        p=self.plan();p['events'][0]['title']='测试,分号;换行\nBEGIN:VEVENT'+'中'*80
        out=calendar(p);self.assertEqual(out.count(b'\r\nBEGIN:VEVENT\r\n'),30);self.assertEqual(out.count(b'BEGIN:VALARM'),30)
        self.assertTrue(all(len(l)<=75 for l in out.split(b'\r\n')));self.assertIn(b'\\nBEGIN:VEVENT',out)
        private=calendar(p,details=False);self.assertNotIn('实际饮食'.encode(),private)
    def test_caldav_update_remove_and_preserve_manual_changes(self):
        p=self.plan();result=sync(p,self.state,self.dav,now=self.now);self.assertEqual(result['created'],30)
        result=sync(p,self.state,self.dav,now=self.now);self.assertEqual(result['unchanged'],30);self.assertEqual(len(self.dav.writes),30)
        self.req['selections'][0]['overrides']={'record':{'time':'20:00','weekdays':[0,1,2,3,4]}}
        q=compile_plan(self.req,self.modules,p);key=q['events'][0]['id']+'.ics';self.dav.items[key]=('"user-edit"',b'User notes')
        result=sync(q,self.state,self.dav,now=self.now);self.assertEqual(len(result['conflicts']),1);self.assertGreater(result['updated'],0);self.assertGreater(result['deleted'],0);self.assertEqual(self.dav.items[key][1],b'User notes')
    def test_uncertain_write_retry_and_missing_remote(self):
        p=self.plan();self.dav.uncertain=True
        with self.assertRaises(TimeoutError):sync(p,self.state,self.dav,now=self.now)
        r=sync(p,self.state,self.dav,now=self.now);self.assertEqual(r['created'],29);self.assertEqual(len(self.dav.items),30)
        key=p['events'][0]['id']+'.ics';del self.dav.items[key]
        r=sync(p,self.state,self.dav,now=self.now);self.assertEqual(len(r['conflicts']),1);self.assertNotIn(key,self.dav.items)
    def test_server_normalization_does_not_rewrite_unchanged_events(self):
        p=self.plan();sync(p,self.state,self.dav,now=self.now)
        for key,(tag,body) in self.dav.items.items():self.dav.items[key]=(tag,body+b'SERVER-NORMALIZED')
        result=sync(p,self.state,self.dav,now=self.now)
        self.assertEqual(result['unchanged'],30);self.assertEqual(len(self.dav.writes),30)
    def test_module_import_requires_source_review(self):
        from import_plan_module import import_module
        m=copy.deepcopy(next(m for m in self.modules if m['kind']=='creator'))
        dest=Path(self.temp.name)/'modules.json'
        import_module(m,dest)
        with self.assertRaises(ValueError):import_module(m,dest)
        m['status']='ready'
        with self.assertRaises(ValueError):import_module(m,Path(self.temp.name)/'reviewed.json')
        m['profile']={'weight':'private'}
        with self.assertRaises(ValueError):import_module(m,Path(self.temp.name)/'leak.json')
    def test_past_events_and_target_identity(self):
        p=self.plan();r=sync(p,self.state,self.dav,now=datetime(2031,1,1,tzinfo=timezone.utc));self.assertEqual(r['past_preserved'],30);self.assertFalse(self.dav.items)
        self.dav.target='other'
        with self.assertRaises(ValueError):sync(p,self.state,self.dav,now=self.now)
    def test_diet_requires_audited_matching_month(self):
        self.req['nutrition_audit']={'days':[{}]*30}
        with self.assertRaises((ValueError,KeyError)):self.plan()
        from export_reminders import export
        meals=[dict(type=t,time=h,name='合成餐',ingredients=[dict(food='合成食材',grams=10,weight_basis='干重')],steps=['合成步骤'],storage='当天现做') for t,h in [('早餐','08:00'),('午餐','12:00'),('晚餐','18:00')]]
        days=[dict(date=d['date'],meals=meals) for d in self.plan_without_audit()['days']]
        audit=dict(status='数据协议通过',gaps=[],days=days,profile={'secret':'DO_NOT_EXPORT'})
        self.req['nutrition_audit']=audit;p=self.plan();self.assertEqual(len(p['events']),154);self.assertNotIn('DO_NOT_EXPORT',json.dumps(p));self.assertIn('逐餐',p['nutrition_status'])
        audit['gaps']=['未核实食物']
        with self.assertRaises(ValueError):self.plan()
    def plan_without_audit(self):
        r=copy.deepcopy(self.req);r.pop('nutrition_audit',None);return compile_plan(r,self.modules)

if __name__=='__main__':unittest.main()
