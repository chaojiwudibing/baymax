"""Local resource community. Public files only; personal Baymax files are never served."""
import argparse
from contextlib import contextmanager
import json
import re
import secrets
import sqlite3
import sys
import threading
from datetime import datetime, timezone
from http import cookies
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit, parse_qs

ROOT = Path(__file__).resolve().parent
SCRIPT_ROOT = ROOT.parent / 'scripts'
if not SCRIPT_ROOT.is_dir(): SCRIPT_ROOT = ROOT.parent / 'baymax/scripts'
sys.path.insert(0, str(SCRIPT_ROOT))
from life_plan import compile_plan
from calendar_sync import calendar, sync, CalDAV
class CommunityServer(ThreadingHTTPServer):
    daemon_threads = True
    def __init__(self, address, database, calendar_config=None, calendar_state=None):
        self.database = str(database)
        self.calendar_config = calendar_config
        self.calendar_state = Path(calendar_state) if calendar_state else None
        self.calendar_stop = threading.Event()
        self.catalog = json.loads((ROOT / 'data/catalog.json').read_text())
        self.plans = json.loads((ROOT / 'data/plans.json').read_text(encoding='utf-8'))
        self.creators = json.loads((ROOT / 'data/creators.json').read_text())
        self.resource_ids = {r['id'] for r in self.catalog['resources']}
        super().__init__(address, Handler)
        with self.connect() as db:
            db.executescript('''
            CREATE TABLE IF NOT EXISTS calendar_status(owner TEXT NOT NULL,id TEXT NOT NULL,revision INTEGER NOT NULL,status TEXT NOT NULL,result TEXT NOT NULL,PRIMARY KEY(owner,id));
            CREATE TABLE IF NOT EXISTS life_plans(owner TEXT NOT NULL, id TEXT NOT NULL, revision INTEGER NOT NULL, payload TEXT NOT NULL, request TEXT NOT NULL, PRIMARY KEY(owner,id));
            CREATE TABLE IF NOT EXISTS life_revisions(owner TEXT NOT NULL,id TEXT NOT NULL,revision INTEGER NOT NULL,payload TEXT NOT NULL,PRIMARY KEY(owner,id,revision));
            CREATE TABLE IF NOT EXISTS life_records(owner TEXT NOT NULL,plan TEXT NOT NULL,event TEXT NOT NULL,status TEXT NOT NULL,note TEXT NOT NULL,updated TEXT NOT NULL,PRIMARY KEY(owner,plan,event));
            CREATE TABLE IF NOT EXISTS posts(id INTEGER PRIMARY KEY, owner TEXT NOT NULL, author TEXT NOT NULL, title TEXT NOT NULL, body TEXT NOT NULL, project TEXT NOT NULL, kind TEXT NOT NULL, created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS comments(id INTEGER PRIMARY KEY, post INTEGER NOT NULL REFERENCES posts(id) ON DELETE CASCADE, owner TEXT NOT NULL, author TEXT NOT NULL, body TEXT NOT NULL, created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS submissions(id INTEGER PRIMARY KEY, owner TEXT NOT NULL, url TEXT NOT NULL UNIQUE, name TEXT NOT NULL, description TEXT NOT NULL, category TEXT NOT NULL, created TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS video_submissions(id INTEGER PRIMARY KEY, owner TEXT NOT NULL, url TEXT NOT NULL UNIQUE, creator TEXT NOT NULL, title TEXT NOT NULL, topic TEXT NOT NULL, notes TEXT NOT NULL, created TEXT NOT NULL);
            ''')
        if self.calendar_config:
            with self.connect() as db: db.execute("UPDATE calendar_status SET status='queued' WHERE status='syncing'")
            self.calendar_thread=threading.Thread(target=self.calendar_worker,daemon=True)
            self.calendar_thread.start()
    def server_close(self):
        self.calendar_stop.set()
        super().server_close()
    def calendar_worker(self):
        # One worker serializes revisions. Pending work survives server restarts in SQLite.
        while not self.calendar_stop.wait(1):
            with self.connect() as db:
                db.execute("BEGIN IMMEDIATE")
                row=db.execute("SELECT owner,id,revision FROM calendar_status WHERE status='queued' ORDER BY rowid LIMIT 1").fetchone()
                if not row: continue
                stored=db.execute('SELECT payload FROM life_plans WHERE owner=? AND id=?',(row['owner'],row['id'])).fetchone()
                if not stored:continue
                db.execute("UPDATE calendar_status SET status='syncing' WHERE owner=? AND id=?",(row['owner'],row['id']))
            plan=json.loads(stored['payload'])
            try:
                config=json.loads(Path(self.calendar_config).read_text())
                state=self.calendar_state/(row['owner']+'-'+row['id']+'.json')
                result=sync(plan,state,CalDAV(config),details=config.get('include_details',True))
                status='conflicts' if result['conflicts'] else 'synced'
            except Exception:
                status='failed';result={'error':'同步未完成，请在本机检查账号权限、网络及同步状态；未声称手机送达'}
            with self.connect() as db:
                db.execute('UPDATE calendar_status SET status=?,result=? WHERE owner=? AND id=? AND revision=?',(status,json.dumps(result,ensure_ascii=False),row['owner'],row['id'],plan['revision']))
    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.database, timeout=5)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db: yield db
        finally: db.close()

class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'public'), **kwargs)
    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        self.send_header('Cache-Control', 'no-store')
        super().end_headers()
    def valid_host(self):
        return self.headers.get('Host') in {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
    def owner(self):
        jar = cookies.SimpleCookie()
        try: jar.load(self.headers.get('Cookie', ''))
        except cookies.CookieError: return ''
        token = jar.get('community_session')
        return token.value if token and re.fullmatch(r'[a-f0-9]{64}', token.value) else ''
    def reply(self, status, data, session=None):
        payload = json.dumps(data, ensure_ascii=False).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(payload)))
        if session: self.send_header('Set-Cookie', f'community_session={session}; HttpOnly; SameSite=Strict; Path=/; Max-Age=31536000')
        self.end_headers()
        self.wfile.write(payload)
    def do_GET(self):
        if not self.valid_host(): return self.reply(403, {'error':'不允许的访问地址'})
        path = urlsplit(self.path).path
        if path == '/api/catalog': return self.reply(200, self.server.catalog, None if self.owner() else secrets.token_hex(32))
        if path == '/api/life-library': return self.reply(200,self.server.plans)
        if path in ('/api/life-plans','/api/life-export'):
            if not self.owner(): return self.reply(403,{'error':'请先打开本站建立本地会话'})
            with self.server.connect() as db:
                if path == '/api/life-plans':
                    rows=[dict(payload=json.loads(r['payload']),request=json.loads(r['request'])) for r in db.execute('SELECT payload,request FROM life_plans WHERE owner=? ORDER BY rowid DESC',(self.owner(),))]
                    records=[dict(r) for r in db.execute('SELECT plan,event,status,note,updated FROM life_records WHERE owner=?',(self.owner(),))]
                    syncs=[dict(r) for r in db.execute('SELECT id,revision,status,result FROM calendar_status WHERE owner=?',(self.owner(),))]
                    return self.reply(200,{'plans':rows,'records':records,'calendar':syncs,'calendar_connected':bool(self.server.calendar_config)})
                query=parse_qs(urlsplit(self.path).query);pid=query.get('id',[''])[0]
                row=db.execute('SELECT payload FROM life_plans WHERE owner=? AND id=?',(self.owner(),pid)).fetchone()
                if not row:return self.reply(404,{'error':'计划不存在或不属于当前浏览器'})
                plan=json.loads(row['payload']);kind=query.get('format',['json'])[0]
                if kind not in ('ics','json'):return self.reply(400,{'error':'不支持的导出格式'})
                if kind=='ics':
                    try: payload=calendar(plan,details=query.get('details',['1'])[0]=='1')
                    except ValueError as e:return self.reply(400,{'error':str(e)})
                else:
                    plan['records']=[dict(r) for r in db.execute('SELECT event,status,note,updated FROM life_records WHERE owner=? AND plan=?',(self.owner(),pid))]
                    payload=json.dumps(plan,ensure_ascii=False,indent=2).encode()
            self.send_response(200);self.send_header('Content-Type','text/calendar; charset=utf-8' if kind=='ics' else 'application/json; charset=utf-8')
            self.send_header('Content-Disposition',f'attachment; filename="baymax-{pid}-v{plan["revision"]}.{kind}"')
            self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload);return
        if path == '/api/creators': return self.reply(200, self.server.creators)
        if path == '/api/community':
            with self.server.connect() as db:
                posts = [dict(r) for r in db.execute('SELECT p.*, (SELECT COUNT(*) FROM comments c WHERE c.post=p.id) AS replies FROM posts p ORDER BY p.id DESC LIMIT 100')]
                comments = [dict(r) for r in db.execute('SELECT * FROM comments ORDER BY id LIMIT 2000')]
                videos = [dict(r) for r in db.execute('SELECT * FROM video_submissions ORDER BY id DESC LIMIT 100')]
                submissions = [dict(r) for r in db.execute('SELECT * FROM submissions ORDER BY id DESC LIMIT 100')]
            for row in posts + comments + submissions + videos:
                row['mine'] = row.pop('owner') == self.owner()
            return self.reply(200, {'posts':posts,'comments':comments,'submissions':submissions,'videos':videos})
        return super().do_GET()
    def do_POST(self):
        if not self.valid_host(): return self.reply(403, {'error':'不允许的访问地址'})
        origin = self.headers.get('Origin')
        allowed = {f'http://127.0.0.1:{self.server.server_port}', f'http://localhost:{self.server.server_port}'}
        if origin not in allowed or self.headers.get('X-Requested-With') != 'BodyCommons' or not self.owner():
            return self.reply(403, {'error':'请从本站页面提交'})
        if self.headers.get('Content-Type','').split(';')[0] != 'application/json':
            return self.reply(415, {'error':'请求格式不支持'})
        try:
            size = int(self.headers.get('Content-Length', '0'))
            if size < 1 or size > (3000000 if urlsplit(self.path).path == '/api/life-plans' else 16000): return self.reply(413, {'error':'内容过长'})
            data = json.loads(self.rfile.read(size))
            if not isinstance(data, dict): raise ValueError('内容格式不正确')
            now = datetime.now(timezone.utc).isoformat()
            path = urlsplit(self.path).path
            with self.server.connect() as db:
                if path == '/api/life-plans':
                    db.execute('BEGIN IMMEDIATE')
                    if not isinstance(data.get('id'),str):raise ValueError('计划编号无效')
                    row=db.execute('SELECT payload,revision FROM life_plans WHERE owner=? AND id=?',(self.owner(),data['id'])).fetchone()
                    if data.get('base_revision',0)!=(row['revision'] if row else 0):return self.reply(409,{'error':'计划已在其他页面修改，请重新打开后再编辑'})
                    if not row and db.execute('SELECT COUNT(*) FROM life_plans WHERE owner=?',(self.owner(),)).fetchone()[0]>=100:raise ValueError('已达到本地100份计划上限，请先备份整理')
                    plan=compile_plan(data,self.server.plans['modules'],json.loads(row['payload']) if row else None)
                    payload=json.dumps(plan,ensure_ascii=False)
                    db.execute('INSERT OR REPLACE INTO life_plans VALUES(?,?,?,?,?)',(self.owner(),plan['id'],plan['revision'],payload,json.dumps(data,ensure_ascii=False)))
                    db.execute('INSERT INTO life_revisions VALUES(?,?,?,?)',(self.owner(),plan['id'],plan['revision'],payload))
                    if self.server.calendar_config:
                        status='queued' if plan['status']=='ready' else 'blocked'
                        db.execute('INSERT OR REPLACE INTO calendar_status VALUES(?,?,?,?,?)',(self.owner(),plan['id'],plan['revision'],status,'{}'))
                    return self.reply(201,{'ok':True,'plan':plan})
                if path == '/api/life-records':
                    pid=self.field(data,'plan',80);event=self.field(data,'event',32)
                    row=db.execute('SELECT payload FROM life_plans WHERE owner=? AND id=?',(self.owner(),pid)).fetchone()
                    if not row or event not in {e['id'] for e in json.loads(row['payload'])['events']}:raise ValueError('只能记录自己的当前计划步骤')
                    status=data.get('status')
                    if status not in ('done','skipped','pending'):raise ValueError('记录状态无效')
                    note=self.field(data,'note',2000,optional=True)
                    db.execute('INSERT OR REPLACE INTO life_records VALUES(?,?,?,?,?,?)',(self.owner(),pid,event,status,note,now))
                    return self.reply(200,{'ok':True})
                # ISO dates are normalized with julianday for reliable comparisons.
                count = sum(db.execute(f"SELECT COUNT(*) FROM {table} WHERE owner=? AND julianday(created) > julianday('now','-1 minute')", (self.owner(),)).fetchone()[0] for table in ['posts','comments','submissions','video_submissions'])
                if count >= 15: return self.reply(429, {'error':'提交太频繁，请一分钟后再试'})
                if path == '/api/posts':
                    project = self.field(data, 'project', 200, optional=True)
                    if project and project not in self.server.resource_ids: raise ValueError('请选择目录中的项目')
                    kind = self.field(data, 'kind', 20)
                    if kind not in ['讨论','使用体验','求助']: raise ValueError('请选择有效的帖子类型')
                    cur = db.execute('INSERT INTO posts(owner,author,title,body,project,kind,created) VALUES(?,?,?,?,?,?,?)', (self.owner(),self.field(data,'author',30),self.field(data,'title',100),self.field(data,'body',4000),project,kind,now))
                elif path == '/api/comments':
                    post = data.get('post')
                    if type(post) is not int or not db.execute('SELECT id FROM posts WHERE id=?',(post,)).fetchone(): raise ValueError('帖子不存在')
                    cur = db.execute('INSERT INTO comments(post,owner,author,body,created) VALUES(?,?,?,?,?)',(post,self.owner(),self.field(data,'author',30),self.field(data,'body',2000),now))
                elif path == '/api/submissions':
                    url = self.field(data,'url',250)
                    parsed = urlsplit(url)
                    if parsed.scheme != 'https' or parsed.netloc != 'github.com' or parsed.query or parsed.fragment or not re.fullmatch(r'/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/?',parsed.path): raise ValueError('请填写 https://github.com/作者/仓库 形式的地址')
                    url = url.rstrip('/')
                    if any(r['url'].lower() == url.lower() for r in self.server.catalog['resources']): raise ValueError('这个仓库已经在目录中，可以在项目详情里补充讨论')
                    category = self.field(data,'category',30)
                    if category not in self.server.catalog['categories']: raise ValueError('请选择有效分类')
                    cur = db.execute('INSERT INTO submissions(owner,url,name,description,category,created) VALUES(?,?,?,?,?,?)',(self.owner(),url.lower(),self.field(data,'name',80),self.field(data,'description',1200),category,now))
                elif path == '/api/video-submissions':
                    url = self.field(data,'url',500)
                    parsed = urlsplit(url)
                    if parsed.scheme != 'https' or parsed.netloc not in ['www.douyin.com','jingxuan.douyin.com','v.douyin.com','www.bilibili.com','b23.tv','www.youtube.com','youtu.be'] or parsed.username or not parsed.path.strip('/'):
                        raise ValueError('请填写抖音、B站或 YouTube 的视频链接')
                    if any(v['url'] == url for v in self.server.creators['videos']): raise ValueError('这条视频已在来源库中')
                    topic = self.field(data,'topic',30)
                    if topic not in ['饮食与营养','训练与动作','身体与恢复']: raise ValueError('请选择有效主题')
                    cur = db.execute('INSERT INTO video_submissions(owner,url,creator,title,topic,notes,created) VALUES(?,?,?,?,?,?,?)',(self.owner(),url,self.field(data,'creator',60),self.field(data,'title',150),topic,self.field(data,'notes',6000,optional=True),now))
                elif path == '/api/delete':
                    table = data.get('type')
                    if table not in ['posts','comments','submissions','video_submissions'] or type(data.get('id')) is not int: raise ValueError('无效的删除请求')
                    cur = db.execute(f'DELETE FROM {table} WHERE id=? AND owner=?',(data['id'],self.owner()))
                    if not cur.rowcount: return self.reply(403,{'error':'只能删除当前浏览器提交的内容'})
                    return self.reply(200, {'ok':True})
                else: return self.reply(404, {'error':'地址不存在'})
                result_id = cur.lastrowid
            return self.reply(201, {'ok':True,'id':result_id})
        except sqlite3.IntegrityError: return self.reply(409, {'error':'这个资源已在待整理队列中'})
        except (ValueError, UnicodeDecodeError, KeyError, TypeError) as err: return self.reply(400, {'error':str(err) or '请检查填写的内容'})
        except sqlite3.Error: return self.reply(503, {'error':'暂时无法保存，请重试'})
    @staticmethod
    def field(data, key, limit, optional=False):
        value = data.get(key,'')
        if not isinstance(value,str) or len(value) > limit or ('\x00' in value): raise ValueError('字段格式不正确或内容过长')
        value = value.strip()
        if not value and not optional: raise ValueError('请填完整再提交')
        return value

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8848)
    parser.add_argument('--database',default=str(ROOT/'data/community.sqlite3'))
    parser.add_argument('--calendar-config')
    parser.add_argument('--calendar-state-dir')
    parser.add_argument('--allow-calendar-upload',action='store_true')
    args=parser.parse_args()
    Path(args.database).parent.mkdir(parents=True,exist_ok=True)
    if args.calendar_config and (not args.allow_calendar_upload or not args.calendar_state_dir):parser.error('连接日历需已获得上传授权，并设置 --allow-calendar-upload 和 --calendar-state-dir')
    server=CommunityServer(('127.0.0.1',args.port),args.database,args.calendar_config,args.calendar_state_dir)
    print(f'BodyCommons: http://127.0.0.1:{server.server_port}',flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()
