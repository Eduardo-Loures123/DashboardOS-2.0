"""P5-A fictional-only integration, failure, authorization and concurrency tests."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from services.demo_notifications import DemoNotifications, PASSWORD, TZ
from services.demo_web import create_demo_app


class DemoTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='dashboardos-p5a-')
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.demo=DemoNotifications(self.root)
        self.start=datetime(2026,11,9,8,55,tzinfo=TZ)
        self.demo.initialize(self.start)
        self.legacy=self.rows('SELECT * FROM outbox')

    def rows(self,sql):
        with closing(sqlite3.connect(self.demo.path)) as db:return db.execute(sql).fetchall()

    def edit(self,key='operation-0001',status='Em andamento'):
        return self.demo.change_order('root',key,status)

    def morning(self,hour=9,minute=0,day=0):
        self.demo.advance('root',(self.start+timedelta(days=day)).replace(hour=hour,minute=minute))

    def tearDown(self):
        self.assertEqual(self.rows('SELECT * FROM outbox'),self.legacy)

    def test_baseline_has_no_retroactive_events_or_empty_digest(self):
        self.assertEqual(self.demo.view('root')['events'],0)
        self.morning();self.assertEqual(self.demo.compose('root'),0)
        self.assertEqual(self.demo.deliver('root'),0)
        self.assertEqual(self.rows('SELECT * FROM demo_events'),[])

    def test_full_flow_and_idempotent_replay_survive_restart(self):
        self.edit();self.assertEqual(len(self.demo.view('alice')['notices']),1)
        self.assertEqual(self.demo.view('bob')['notices'],[])
        self.assertEqual(self.demo.view('somente-email')['notices'],[])
        self.morning();self.assertEqual(self.demo.compose('root'),3)
        self.assertEqual(self.demo.deliver('root'),3)
        self.demo=DemoNotifications(self.root)
        self.assertTrue(self.edit()['replayed'])
        self.assertEqual(self.demo.compose('root'),0);self.assertEqual(self.demo.deliver('root'),0)
        self.assertEqual(self.demo.view('root')['operations'],1)
        self.assertEqual(self.demo.view('root')['events'],1)
        self.assertEqual(len(self.rows('SELECT * FROM demo_deliveries')),3)

    def test_idempotency_key_conflict_and_invalid_status_do_not_write(self):
        self.edit()
        with self.assertRaises(ValueError):self.edit(status='Pendente')
        with self.assertRaises(ValueError):self.edit('operation-0002','Inválido')
        self.assertEqual(self.demo.view('root')['operations'],1)

    def test_internal_permission_does_not_follow_email_and_wrong_team_denied(self):
        self.edit();self.morning();self.demo.compose('root');self.demo.deliver('root')
        self.assertEqual(self.demo.view('somente-email')['notices'],[])
        self.assertEqual(len(self.demo.view('somente-email')['outbox']),1)
        self.assertEqual(self.demo.view('bob')['notices'],[])
        self.assertEqual(self.demo.view('bob')['outbox'],[])
        for uid in ('sem-consentimento','nao-verificado'):
            self.assertEqual(self.demo.view(uid)['outbox'],[])

    def test_revocation_between_preparation_and_delivery_revalidates_both_channels(self):
        self.edit();self.morning();self.demo.compose('root')
        self.demo.restriction('root','alice','revoke')
        self.demo=DemoNotifications(self.root)
        self.assertEqual(self.demo.view('alice')['notices'],[])
        self.assertEqual(self.demo.deliver('root'),2)
        self.assertEqual(self.demo.view('alice')['outbox'][0]['status'],'cancelled')

    def test_optout_and_unverify_after_composition_are_respected(self):
        self.edit();self.morning();self.demo.compose('root')
        self.demo.restriction('root','alice','optout')
        self.demo.restriction('root','somente-email','unverify')
        self.assertEqual(self.demo.deliver('root'),1)
        self.assertEqual(len(self.demo.view('alice')['notices']),1)

    def test_historic_simulated_mail_is_not_an_access_bypass_after_revocation(self):
        self.edit();self.morning();self.demo.compose('root');self.demo.deliver('root')
        self.assertIn('OS001',self.demo.view('alice')['outbox'][0]['body'])
        self.demo.restriction('root','alice','revoke')
        state=self.demo.view('alice')
        self.assertEqual(state['notices'],[])
        self.assertNotIn('OS001',state['outbox'][0]['body'])
        self.assertIn('OS001',self.rows("SELECT body FROM demo_deliveries WHERE recipient='alice@example.test'")[0][0])

    def test_superseded_event_never_delivered_and_not_replaced_in_prepared_digest(self):
        self.edit();self.morning();self.demo.compose('root')
        self.edit('operation-0002','Concluída')
        self.assertEqual(self.demo.deliver('root'),0)
        self.assertEqual(self.rows('SELECT * FROM demo_deliveries'),[])
        self.assertEqual(self.demo.compose('root'),0)

    def test_day_seven_reminder_is_persistent_and_never_repeated(self):
        self.morning(day=1,hour=8,minute=55)
        events=self.rows('SELECT payload FROM demo_events')
        reminders=[json.loads(r[0]) for r in events if 'seven_day_reminder' in json.loads(r[0])['reasons']]
        self.assertEqual(len(reminders),1)
        self.demo=DemoNotifications(self.root)
        self.morning(day=2,hour=8,minute=55)
        reminders=[r for r in self.rows('SELECT payload FROM demo_events') if 'seven_day_reminder' in r[0]]
        self.assertEqual(len(reminders),1)

    def test_day_seven_email_is_not_repeated_as_a_reminder_in_later_daily_summary(self):
        self.morning(day=1);self.demo.compose('root');self.demo.deliver('root')
        self.morning(day=2);self.demo.compose('root');self.demo.deliver('root')
        messages=self.rows("SELECT body FROM demo_deliveries WHERE recipient='root@example.test' ORDER BY digest_id")
        self.assertEqual(len(messages),2)
        self.assertIn('seven_day_reminder',messages[0][0])
        self.assertNotIn('seven_day_reminder',messages[1][0])
        self.assertIn('Pendência atual',messages[1][0])

    def test_clock_window_before_nine_recovery_at_twelve_and_expiration(self):
        self.edit();self.assertEqual(self.demo.compose('root'),0)
        self.morning(hour=12);self.assertEqual(self.demo.compose('root'),3)
        self.demo.advance('root',self.start.replace(hour=12,minute=0,second=1))
        self.assertEqual(self.demo.deliver('root'),0)
        with self.assertRaises(ValueError):self.morning()

    def test_recovery_at_1130_and_no_next_day_delivery_of_old_digest(self):
        self.edit();self.morning(hour=11,minute=30)
        self.assertEqual(self.demo.compose('root'),3)
        self.morning(day=1)
        self.assertEqual(self.demo.deliver('root'),0)

    def test_failure_after_p4_commit_replays_persistent_inbox(self):
        def fail(boundary):
            if boundary=='after_p4_commit':raise RuntimeError('injected')
        self.demo.fault=fail
        with self.assertRaises(RuntimeError):self.edit()
        self.assertEqual(len(self.rows('SELECT * FROM email_identity_receipts')),1)
        self.assertEqual(self.rows('SELECT * FROM demo_events'),[])
        self.demo=DemoNotifications(self.root);self.demo.recover('root')
        self.assertEqual(self.demo.view('root')['events'],1)
        self.assertTrue(self.edit()['replayed'])

    def test_interrupted_excel_replace_requires_same_request_recovery_before_projection(self):
        def fail(boundary):
            if boundary=='after_replace':raise RuntimeError('injected')
        self.demo.fault=fail
        with self.assertRaises(RuntimeError):self.edit()
        self.assertEqual(self.rows('SELECT * FROM demo_events'),[])
        with self.assertRaises(ValueError):self.demo.view('root')
        self.demo=DemoNotifications(self.root);self.demo.recover('root')
        self.assertEqual(self.demo.view('root')['events'],1)
        self.assertEqual(self.demo.view('root')['operations'],1)

    def test_delivery_at_exact_twelve_is_allowed(self):
        self.edit();self.morning(hour=12)
        self.assertEqual(self.demo.compose('root'),3)
        self.assertEqual(self.demo.deliver('root'),3)

    def test_active_unread_notifications_are_not_lost_by_restart(self):
        self.edit();before=self.demo.view('alice')['notices']
        self.demo=DemoNotifications(self.root)
        self.assertEqual(self.demo.view('alice')['notices'],before)
        self.assertEqual(self.demo.view('root')['recovery']['status'],'consistent')

    def test_projection_failure_rolls_back_event_snapshot_and_progress(self):
        def fail(boundary):
            if boundary=='before_projection_commit':raise RuntimeError('injected')
        self.demo.fault=fail
        with self.assertRaises(RuntimeError):self.edit()
        self.assertEqual(self.rows('SELECT * FROM demo_events'),[])
        self.assertEqual(self.rows('SELECT projected FROM demo_requests'),[(0,)])
        self.demo=DemoNotifications(self.root);self.demo.recover('root')
        self.assertEqual(self.demo.view('root')['events'],1)

    def test_delivery_crash_is_atomic_simulation_and_retries_once(self):
        self.edit();self.morning();self.demo.compose('root')
        def fail(boundary):
            if boundary=='before_delivery_commit':raise RuntimeError('injected')
        self.demo.fault=fail
        with self.assertRaises(RuntimeError):self.demo.deliver('root')
        self.assertEqual(self.rows('SELECT * FROM demo_deliveries'),[])
        self.demo=DemoNotifications(self.root)
        self.assertEqual(self.demo.deliver('root'),3)
        self.assertEqual(self.demo.deliver('root'),0)

    def test_concurrent_repeated_operation_and_delivery_have_one_effect(self):
        with ThreadPoolExecutor(max_workers=3) as pool:
            list(pool.map(lambda _:DemoNotifications(self.root).change_order('root','concurrent-0001','Em andamento'),range(3)))
        self.assertEqual(self.demo.view('root')['operations'],1)
        self.morning()
        with ThreadPoolExecutor(max_workers=3) as pool:
            counts=list(pool.map(lambda _:DemoNotifications(self.root).compose('root'),range(3)))
        self.assertEqual(sum(counts),3)
        with ThreadPoolExecutor(max_workers=3) as pool:
            counts=list(pool.map(lambda _:DemoNotifications(self.root).deliver('root'),range(3)))
        self.assertEqual(sum(counts),3)

    def test_legacy_five_rows_are_untouched_by_all_new_processing(self):
        self.edit();self.morning();self.demo.compose('root');self.demo.deliver('root')
        self.assertEqual(len(self.legacy),5)
        self.assertEqual(self.rows('SELECT status,attempts FROM outbox'),[('pending',0)]*5)

    def test_tampered_workbook_blocks_projection_and_delivery(self):
        self.edit();self.morning();self.demo.compose('root')
        with self.demo.store.current.open('ab') as stream:stream.write(b'tampered')
        with self.assertRaises(ValueError):self.demo.deliver('root')
        self.assertEqual(self.rows('SELECT * FROM demo_deliveries'),[])

    def test_non_admin_cannot_mutate_clock_order_permission_or_delivery(self):
        for call in (lambda:self.demo.change_order('alice','unauthorised-1','Em andamento'),
                     lambda:self.demo.advance('alice',self.start+timedelta(days=1)),
                     lambda:self.demo.compose('alice'),lambda:self.demo.deliver('alice'),
                     lambda:self.demo.restriction('alice','bob','revoke')):
            with self.assertRaises(PermissionError):call()

    def test_web_auth_csrf_and_user_scoped_state(self):
        app=create_demo_app(self.root);app.testing=True;client=app.test_client()
        self.assertEqual(client.get('/demo/api/state').status_code,401)
        self.assertEqual(client.post('/demo/api/deliver',json={}).status_code,403)
        html=client.get('/');self.assertIn('AMBIENTE DE DEMONSTRAÇÃO',html.text)
        with client.session_transaction() as s:csrf=s['csrf']
        self.assertEqual(client.post('/demo/login',data={'uid':'alice','password':PASSWORD,'csrf':csrf}).status_code,302)
        with client.session_transaction() as s:csrf=s['csrf']
        self.assertEqual(client.post('/demo/api/deliver',json={},headers={'X-CSRF-Token':csrf}).status_code,403)
        state=client.get('/demo/api/state').json
        self.assertNotIn('order',state);self.assertNotIn('legacy',state);self.assertNotIn('users',state)
        self.assertEqual(client.get('/demo/api/state',headers={'Host':'evil.example'}).status_code,403)


if __name__=='__main__':unittest.main()
