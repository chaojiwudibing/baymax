import test_community as base
import unittest
import threading
import time
import json
from pathlib import Path
from unittest.mock import patch
import http.cookiejar
import urllib.request

class PlannerTests(unittest.TestCase):
    setUp=base.CommunityTests.setUp
    tearDown=base.CommunityTests.tearDown
    call=base.CommunityTests.call
    def request_plan(self):return dict(id='synthetic-period',title='合成计划',start='2030-01-01',timezone='Asia/Shanghai',suitability_confirmed=True,selections=[dict(module='daily-reflection')],base_revision=0)
    def test_life_owner_revision_and_records(self):
        req=self.request_plan();code,result=self.call('/api/life-plans',req);self.assertEqual(code,201);p=result['plan'];self.assertEqual(len(p['days']),30)
        self.assertEqual(self.call('/api/life-plans',req)[0],409)
        e=p['events'][0];self.assertEqual(self.call('/api/life-records',dict(plan=p['id'],event=e['id'],status='done',note='实际记录不是计划摄入'))[0],200)
        req['base_revision']=1;req['selections'][0]['overrides']={'record':{'time':'20:00'}}
        self.assertEqual(self.call('/api/life-plans',req)[1]['plan']['revision'],2)
        result=self.call('/api/life-plans')[1];self.assertEqual(len(result['records']),1);self.assertEqual(result['records'][0]['note'],'实际记录不是计划摄入')
        other=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));self.call('/api/catalog',client=other)
        self.assertEqual(self.call('/api/life-plans',client=other)[1]['plans'],[])
        self.assertEqual(self.call('/api/life-export?id=synthetic-period&format=json',client=other)[0],404)
        with self.server.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM life_revisions').fetchone()[0],2)
    def test_life_inputs_and_library(self):
        lib=self.call('/api/life-library')[1];self.assertEqual(len(lib['inventory']),1369)
        req=self.request_plan();req['selections']=[dict(module='creator-7618962209967965617')];self.assertEqual(self.call('/api/life-plans',req)[0],400)
        req=self.request_plan();req['suitability_confirmed']=False;self.assertEqual(self.call('/api/life-plans',req)[0],400)

    def test_saving_connected_plan_queues_sync_and_preserves_revision(self):
        config=Path(self.temp.name)/'calendar.json';config.write_text('{}')
        self.server.calendar_config=str(config);self.server.calendar_state=Path(self.temp.name)/'sync'
        sent=[]
        def simulated_sync(plan,*args,**kwargs):
            sent.append(plan['revision']);return {'conflicts':[],'created':len(plan['events'])}
        with patch('server.CalDAV',return_value=object()),patch('server.sync',side_effect=simulated_sync):
            worker=threading.Thread(target=self.server.calendar_worker,daemon=True);worker.start()
            req=self.request_plan();self.assertEqual(self.call('/api/life-plans',req)[0],201)
            deadline=time.monotonic()+5
            while time.monotonic()<deadline:
                status=self.call('/api/life-plans')[1]['calendar']
                if status and status[0]['status']=='synced':break
                time.sleep(.1)
            self.assertEqual(status[0]['status'],'synced');self.assertEqual(sent,[1])
            self.server.calendar_stop.set();worker.join(2)
