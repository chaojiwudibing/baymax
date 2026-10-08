import http.cookiejar
import json
from pathlib import Path
import sys
import tempfile
import threading
import unittest
import urllib.request
import urllib.error
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from server import CommunityServer

class CommunityTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.server=CommunityServer(('127.0.0.1',0),Path(self.temp.name)/'test.sqlite3')
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base=f'http://127.0.0.1:{self.server.server_port}'
        self.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.call('/api/catalog')
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.thread.join();self.temp.cleanup()
    def call(self,path,data=None,client=None,headers=None):
        h={'Content-Type':'application/json','X-Requested-With':'BodyCommons','Origin':self.base}
        h.update(headers or {})
        req=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers=h)
        try:
            with (client or self.client).open(req) as res:return res.status,json.loads(res.read()) if path.startswith('/api/') else res.read()
        except urllib.error.HTTPError as e:
            payload=e.read()
            try:payload=json.loads(payload)
            except ValueError:pass
            return e.code,payload
    def test_catalog_is_attributed_and_bounded(self):
        code,data=self.call('/api/catalog');self.assertEqual(code,200)
        self.assertEqual(len(data['queries']),20)
        self.assertEqual(len({r['id'] for r in data['resources']}),len(data['resources']))
        curated=[r for r in data['resources'] if r['curated']]
        self.assertEqual(len(curated),data['curatedCount'])
        self.assertTrue(all(r['readme'] and r['note'] and r['license']!='待核许可' for r in curated))
        self.assertNotIn('1306',json.dumps(data))
        self.assertEqual(self.call('/../.baymax/profile.json')[0],404)
        self.assertEqual(self.call('/data/community.sqlite3')[0],404)
        self.assertEqual(self.call('/api/catalog',headers={'Host':'evil.example'})[0],403)
    def test_posts_replies_persist_and_delete_cascades(self):
        payload={'author':'测试者','title':'实际使用问题','body':'<script>alert(1)</script>','project':'wger-project/wger','kind':'求助'}
        code,res=self.call('/api/posts',payload);self.assertEqual(code,201)
        code,comment=self.call('/api/comments',{'post':res['id'],'author':'测试者','body':'回复内容'});self.assertEqual(code,201)
        code,data=self.call('/api/community');self.assertEqual(data['posts'][0]['replies'],1)
        self.assertTrue(data['posts'][0]['mine']);self.assertNotIn('owner',data['posts'][0])
        with self.server.connect() as db:self.assertEqual(db.execute('SELECT body FROM posts').fetchone()[0],payload['body'])
        other=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.call('/api/catalog',client=other)
        self.assertEqual(self.call('/api/delete',{'type':'posts','id':res['id']},client=other)[0],403)
        self.assertEqual(self.call('/api/delete',{'type':'posts','id':res['id']})[0],200)
        self.assertEqual(self.call('/api/community')[1]['comments'],[])
    def test_submission_queue_and_duplicate(self):
        p={'url':'https://github.com/example/bodycommons-testing-only','name':'测试投稿','description':'只用于检查的文字','category':'body'}
        code,result=self.call('/api/submissions',p);self.assertEqual(code,201)
        self.assertEqual(self.call('/api/submissions',p)[0],409)
        self.assertEqual(self.call('/api/community')[1]['submissions'][0]['name'],p['name'])
        self.assertEqual(self.call('/api/delete',{'type':'submissions','id':result['id']})[0],200)
        for url in ['javascript:alert(1)','https://github.com.evil.com/a/b','https://github.com/a/b?x=1','https://github.com/a/b/issues']:
            self.assertEqual(self.call('/api/submissions',{**p,'url':url})[0],400)
    def test_boundaries_and_csrf(self):
        p={'author':'人','title':'测试','body':'内容','project':'missing','kind':'讨论'}
        self.assertEqual(self.call('/api/posts',p)[0],400)
        self.assertEqual(self.call('/api/posts',{**p,'project':''},headers={'Origin':'https://evil.example'})[0],403)
        self.assertEqual(self.call('/api/posts',[])[0],400)
        self.assertEqual(self.call('/api/posts',{**p,'project':'','title':'x'*101})[0],400)
        self.assertEqual(self.call('/api/comments',{'post':999,'author':'人','body':'回复'})[0],400)
        self.assertEqual(self.call('/api/delete',{'type':'posts;DROP TABLE posts','id':1})[0],400)
    def test_creator_sources_are_not_unverified_plans(self):
        code,data=self.call('/api/creators');self.assertEqual(code,200)
        self.assertEqual(len(data['videos']),10)
        self.assertEqual(data['confirmedPlans'],[])
        for video in data['videos']:
            self.assertTrue(video['url'].startswith('https://www.douyin.com/video/'))
            self.assertFalse(video['reviewedTranscript'])
            self.assertIsNone(video['plan'])
            self.assertEqual(video['claims'],[])
    def test_video_queue_validation_and_ownership(self):
        p={'url':'https://www.douyin.com/video/123456789','creator':'测试作者','title':'验证用视频','topic':'训练与动作','notes':'仅验证投稿流程'}
        code,res=self.call('/api/video-submissions',p);self.assertEqual(code,201)
        self.assertEqual(self.call('/api/video-submissions',p)[0],409)
        self.assertTrue(self.call('/api/community')[1]['videos'][0]['mine'])
        for url in ['javascript:alert(1)','https://www.douyin.com.evil.com/video/123','https://user@www.douyin.com/video/123']:
            self.assertEqual(self.call('/api/video-submissions',{**p,'url':url})[0],400)
        self.assertEqual(self.call('/api/delete',{'type':'video_submissions','id':res['id']})[0],200)
        self.assertEqual(self.call('/api/community')[1]['videos'],[])
    def test_write_rate_limit(self):
        p={'author':'人','title':'测试','body':'内容','project':'','kind':'讨论'}
        for _ in range(15):self.assertEqual(self.call('/api/posts',p)[0],201)
        self.assertEqual(self.call('/api/posts',p)[0],429)

if __name__=='__main__':unittest.main()
