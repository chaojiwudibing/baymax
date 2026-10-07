#!/usr/bin/env python3
"""Time-gated Microsoft To Do delivery. Run one cloud worker per list."""
import argparse
import hashlib
import json
import os
import re
import sqlite3
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlencode, quote, urlsplit
from urllib.request import Request, HTTPRedirectHandler, build_opener

GRAPH = 'https://graph.microsoft.com/v1.0'
SCOPES = 'https://graph.microsoft.com/Tasks.ReadWrite offline_access'


def instant(value):
    d = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if d.tzinfo is None:
        raise ValueError('Every schedule time needs a UTC offset')
    return d.astimezone(timezone.utc)


def load_plan(path):
    p = json.loads(Path(path).read_text(encoding='utf-8'))
    if p.get('schema_version') != 1 or not isinstance(p.get('events'), list):
        raise ValueError('Invalid reminder manifest')
    seen = set()
    for e in p['events']:
        if not re.fullmatch(r'[a-f0-9]{32}', e.get('id', '')) or e['id'] in seen:
            raise ValueError('Invalid or duplicate event ID')
        seen.add(e['id'])
        instant(e['at'])
        if not isinstance(e.get('title'), str) or not e['title'].strip() or not isinstance(e.get('body'), str):
            raise ValueError('Invalid event content')
    return p


def private_json(path, data, replace=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not replace and path.exists():
        raise FileExistsError(path)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.baymax-')
    try:
        os.chmod(tmp, 0o600)
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        if replace:
            os.replace(tmp, path)
        else:
            os.link(tmp, path)  # Exclusive creation, including a concurrent writer.
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


class APIError(RuntimeError):
    def __init__(self, status, code='request_failed'):
        self.status, self.code = status, code
        super().__init__('Remote request failed (HTTP %s, %s)' % (status, code))


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def request(method, url, data=None, bearer=None, form=False):
    headers = {}
    if bearer:
        if urlsplit(url).hostname != 'graph.microsoft.com' or urlsplit(url).scheme != 'https':
            raise ValueError('Refusing to send credentials outside Microsoft Graph')
        headers['Authorization'] = 'Bearer ' + bearer
    payload = None
    if data is not None:
        payload = urlencode(data).encode() if form else json.dumps(data).encode()
        headers['Content-Type'] = 'application/x-www-form-urlencoded' if form else 'application/json'
    try:
        with build_opener(NoRedirect()).open(Request(url, data=payload, headers=headers, method=method), timeout=25) as r:
            return json.load(r)
    except HTTPError as e:
        try:
            error = json.loads(e.read()).get('error', 'request_failed')
            code = error.get('code', 'request_failed') if isinstance(error, dict) else error
        except (ValueError, AttributeError):
            code = 'request_failed'
        # Never echo remote response bodies, tokens, meal notes or credentials.
        raise APIError(e.code, re.sub(r'[^a-zA-Z0-9_]', '', str(code))[:80]) from None


def connect(client_id, path):
    if Path(path).exists():
        raise FileExistsError('Token file exists; do not replace another account')
    base = 'https://login.microsoftonline.com/consumers/oauth2/v2.0/'
    d = request('POST', base + 'devicecode', {'client_id': client_id, 'scope': SCOPES}, form=True)
    print('Open %s and enter %s. Sign in and review the requested task permissions.' %
          (d['verification_uri'], d['user_code']), flush=True)
    interval = int(d.get('interval', 5))
    deadline = time.monotonic() + int(d['expires_in'])
    while time.monotonic() < deadline:
        time.sleep(interval)
        try:
            token = request('POST', base + 'token', {'client_id': client_id,
                'grant_type': 'urn:ietf:params:oauth:grant-type:device_code', 'device_code': d['device_code']}, form=True)
            if 'refresh_token' not in token:
                raise ValueError('No refresh token returned; reconnect with offline_access')
            token.update(client_id=client_id, expires_at=time.time() + token['expires_in'])
            private_json(path, token, replace=False)
            print('Connected. Credentials saved privately; no meal plan uploaded.')
            return
        except APIError as e:
            if e.code == 'authorization_pending':
                continue
            if e.code == 'slow_down':
                interval += 5
                continue
            raise
    raise TimeoutError('Sign-in expired; run connect again')


class Graph:
    def __init__(self, tokens, list_id):
        self.tokens, self.list_id = Path(tokens), list_id
        self.token = json.loads(self.tokens.read_text())

    def access(self):
        if self.token.get('expires_at', 0) < time.time() + 120:
            fresh = request('POST', 'https://login.microsoftonline.com/consumers/oauth2/v2.0/token',
                {'client_id': self.token['client_id'], 'grant_type': 'refresh_token',
                 'refresh_token': self.token['refresh_token'], 'scope': SCOPES}, form=True)
            fresh.setdefault('refresh_token', self.token['refresh_token'])
            fresh.update(client_id=self.token['client_id'], expires_at=time.time() + fresh['expires_in'])
            private_json(self.tokens, fresh)
            self.token = fresh
        return self.token['access_token']

    def call(self, method, path, data=None):
        return request(method, GRAPH + path, data, self.access())

    def known(self):
        url = GRAPH + '/me/todo/lists/' + quote(self.list_id, safe='') + '/tasks?$top=100&$select=id,body,status'
        found = {}
        while url:
            page = request('GET', url, bearer=self.access())
            for t in page['value']:
                for key in re.findall(r'\[Baymax:([a-f0-9]{32})\]', t.get('body', {}).get('content', '')):
                    if key in found:
                        raise ValueError('Duplicate Baymax marker in destination; reconcile before sending')
                    found[key] = t['id']
            url = page.get('@odata.nextLink')
        return found

    def create(self, event, now):
        at = instant(event['at'])
        stamp = lambda d: {'dateTime': d.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S'), 'timeZone': 'UTC'}
        # Set an alarm in the near future: an already-past reminder may not notify.
        payload = {'title': event['title'], 'body': {'contentType': 'text',
            'content': event['body'] + '\n\n[Baymax:' + event['id'] + ']'},
            'dueDateTime': stamp(at), 'isReminderOn': True,
            'reminderDateTime': stamp(now + timedelta(seconds=60))}
        return self.call('POST', '/me/todo/lists/' + quote(self.list_id, safe='') + '/tasks', payload)['id']


def deliver(plan, state_path, graph, now, window_minutes=15):
    if now.tzinfo is None or not 1 <= window_minutes <= 60:
        raise ValueError('Use an aware clock and a 1–60 minute delivery window')
    now = now.astimezone(timezone.utc)
    due = [e for e in plan['events'] if now - timedelta(minutes=window_minutes) <= instant(e['at']) <= now]
    Path(state_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(str(state_path), timeout=30) as db:
        db.execute('CREATE TABLE IF NOT EXISTS delivery (event TEXT PRIMARY KEY, target TEXT NOT NULL, remote TEXT)')
        db.execute('BEGIN IMMEDIATE')
        # ponytail: one persisted SQLite state per cloud worker/list; no distributed workers.
        known = graph.known() if due else {}
        outcome = {'created': 0, 'already_sent': 0, 'needs_attention': 0,
                   'past_window_events': sum(instant(e['at']) < now - timedelta(minutes=window_minutes) for e in plan['events'])}
        for e in sorted(due, key=lambda x: instant(x['at'])):
            old = db.execute('SELECT target,remote FROM delivery WHERE event=?', (e['id'],)).fetchone()
            if old and old[0] != graph.list_id:
                raise ValueError('State belongs to another destination list')
            if e['id'] in known:
                db.execute('INSERT OR REPLACE INTO delivery VALUES (?,?,?)', (e['id'], graph.list_id, known[e['id']]))
                outcome['already_sent'] += 1
                continue
            if old:
                # User removal/completion and uncertain writes never cause an automatic repost.
                outcome['already_sent' if old[1] else 'needs_attention'] += 1
                continue
            db.execute('INSERT INTO delivery VALUES (?,?,NULL)', (e['id'], graph.list_id))
            db.commit()  # Persist intent before the irreversible remote POST.
            db.execute('BEGIN IMMEDIATE')
            try:
                remote = graph.create(e, now)
            except Exception:
                # A timeout can occur after creation. Keep pending and reconcile on next tick.
                outcome['needs_attention'] += 1
                continue
            db.execute('UPDATE delivery SET remote=? WHERE event=?', (remote, e['id']))
            outcome['created'] += 1
        return outcome


def main():
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest='command', required=True)
    c = sub.add_parser('connect'); c.add_argument('--client-id', required=True); c.add_argument('--tokens', required=True)
    c = sub.add_parser('create-list'); c.add_argument('--tokens', required=True)
    for name in ('preview', 'tick', 'serve'):
        c = sub.add_parser(name); c.add_argument('--manifest', required=True)
        c.add_argument('--window-minutes', type=int, default=15)
        if name != 'preview':
            c.add_argument('--tokens', required=True); c.add_argument('--list-id', required=True); c.add_argument('--state', required=True)
            c.add_argument('--allow-upload', action='store_true', help='User has authorized sending meal task details to this Microsoft account')
    args = p.parse_args()
    if args.command == 'connect': return connect(args.client_id, args.tokens)
    if args.command == 'create-list':
        print(Graph(args.tokens, '').call('POST', '/me/todo/lists', {'displayName': 'Baymax · 到时提醒'})['id']); return
    plan = load_plan(args.manifest)
    if args.command == 'preview':
        now = datetime.now(timezone.utc)
        current = sum(now - timedelta(minutes=args.window_minutes) <= instant(e['at']) <= now for e in plan['events'])
        print(json.dumps({'events': len(plan['events']), 'eligible_now': current, 'uploads': False})); return
    if not args.allow_upload:
        p.error('Sending meal details requires user authorization and --allow-upload')
    graph = Graph(args.tokens, args.list_id)
    while True:
        try:
            print(json.dumps(deliver(load_plan(args.manifest), args.state, graph, datetime.now(timezone.utc), args.window_minutes)), flush=True)
        except Exception:
            print(json.dumps({'error': 'Delivery unavailable; check account authorization, network and private state'}), flush=True)
            if args.command == 'tick': raise SystemExit(1)
        if args.command == 'tick': break
        time.sleep(60)


if __name__ == '__main__':
    main()
