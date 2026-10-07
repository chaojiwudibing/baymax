import copy
import json
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from reminder_bridge import deliver, load_plan, request, Graph
from unittest.mock import patch
from export_reminders import export


class FakeGraph:
    list_id = 'test-list'
    def __init__(self): self.tasks, self.calls, self.fail = {}, [], False
    def known(self): return dict(self.tasks)
    def create(self, event, now):
        self.calls.append(event['id'])
        if self.fail: raise TimeoutError('Connection lost after sending')
        self.tasks[event['id']] = 'remote-' + event['id']
        return self.tasks[event['id']]


class Reminders(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.state = Path(self.tmp.name) / 'private.sqlite'
        self.now = datetime(2030, 1, 1, 4, 30, tzinfo=timezone.utc)
        self.graph = FakeGraph()
    def plan(self, shifts):
        return {'events': [dict(id=('%032x' % (i + 1)), at=(self.now + timedelta(minutes=shift)).isoformat(), title='Synthetic meal', body='No real health data') for i, shift in enumerate(shifts)]}
    def test_future_never_published_and_old_backlog_not_flooded(self):
        result = deliver(self.plan([-1440, -16, 0, 150]), self.state, self.graph, self.now)
        self.assertEqual(result['created'], 1); self.assertEqual(len(self.graph.calls), 1)
    def test_restart_and_completed_remote_not_recreated(self):
        plan = self.plan([0]); deliver(plan, self.state, self.graph, self.now)
        self.graph.tasks.clear()  # Removal or edited marker must not recreate the task.
        self.assertEqual(deliver(plan, self.state, self.graph, self.now)['created'], 0)
        self.assertEqual(len(self.graph.calls), 1)
    def test_remote_marker_without_local_state_prevents_duplicate(self):
        plan = self.plan([0]); self.graph.tasks[plan['events'][0]['id']] = 'completed-task'
        self.assertEqual(deliver(plan, self.state, self.graph, self.now)['already_sent'], 1)
        self.assertFalse(self.graph.calls)
    def test_uncertain_timeout_never_blindly_reposts(self):
        plan = self.plan([0]); self.graph.fail = True
        self.assertEqual(deliver(plan, self.state, self.graph, self.now)['needs_attention'], 1)
        self.graph.fail = False
        self.assertEqual(deliver(plan, self.state, self.graph, self.now)['needs_attention'], 1)
        self.assertEqual(len(self.graph.calls), 1)
        self.graph.tasks[plan['events'][0]['id']] = 'accepted-before-timeout'
        self.assertEqual(deliver(plan, self.state, self.graph, self.now)['already_sent'], 1)
    def test_token_cannot_be_sent_to_foreign_pagination_url(self):
        with self.assertRaises(ValueError): request('GET', 'https://example.org/next', bearer='synthetic')
    def test_graph_payload_uses_alarm_and_never_updates_existing_notes(self):
        tokens = Path(self.tmp.name) / 'tokens.json'
        tokens.write_text(json.dumps({'access_token': 'synthetic', 'expires_at': 99999999999}))
        graph = Graph(tokens, 'test-list')
        event = self.plan([0])['events'][0]
        with patch('reminder_bridge.request', return_value={'id': 'created'}) as send:
            self.assertEqual(graph.create(event, self.now), 'created')
            args = send.call_args.args
            self.assertEqual(args[0], 'POST')
            payload = args[2]
            self.assertTrue(payload['isReminderOn'])
            self.assertEqual(payload['reminderDateTime'], {'dateTime': '2030-01-01T04:31:00', 'timeZone': 'UTC'})
            self.assertIn('[Baymax:' + event['id'] + ']', payload['body']['content'])
    def test_refreshed_credentials_are_persisted_without_echo(self):
        tokens = Path(self.tmp.name) / 'tokens.json'
        tokens.write_text(json.dumps({'client_id': 'synthetic-app', 'refresh_token': 'old', 'expires_at': 0}))
        graph = Graph(tokens, 'test-list')
        with patch('reminder_bridge.request', return_value={'access_token': 'new-access', 'refresh_token': 'new-refresh', 'expires_in': 3600}):
            self.assertEqual(graph.access(), 'new-access')
        self.assertEqual(json.loads(tokens.read_text())['refresh_token'], 'new-refresh')
    def test_invalid_clock_or_duplicate_manifest_rejected(self):
        path = Path(self.tmp.name) / 'plan.json'; plan = self.plan([0]); plan['schema_version'] = 1
        plan['events'][0]['at'] = '2030-01-01T12:30:00'; path.write_text(json.dumps(plan))
        with self.assertRaises(ValueError): load_plan(path)
        plan = self.plan([0]); plan['schema_version'] = 1; plan['events'] *= 2; path.write_text(json.dumps(plan))
        with self.assertRaises(ValueError): load_plan(path)
    def test_export_excludes_profile_and_revisions_keep_ids(self):
        meal = dict(type='早餐', time='09:30', name='Synthetic dish', ingredients=[dict(food='Synthetic ingredient', grams=10, weight_basis='干重')], steps=['Cook'], storage='Fresh')
        meals = [dict(meal, type=k) for k in ('早餐', '午餐', '晚餐')]
        audit = dict(profile={'private_weight': 'DO_NOT_EXPORT'}, days=[dict(date=(self.now.date() + timedelta(days=i)).isoformat(), meals=meals) for i in range(30)])
        first = export(audit, 'synthetic-period')
        self.assertEqual(len(first['events']), 124)
        self.assertNotIn('DO_NOT_EXPORT', json.dumps(first))
        changed = copy.deepcopy(audit); changed['days'][0]['meals'][0]['name'] = 'Revised dish'
        self.assertEqual([e['id'] for e in first['events']], [e['id'] for e in export(changed, 'synthetic-period')['events']])


if __name__ == '__main__': unittest.main()
