"""Operational events and queue: fictional data, temporary files, no network."""
import copy
import json
import os
import smtplib
import tempfile
import threading
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

from openpyxl import Workbook
from services.auth_service import AuthService
from services.enterprise_service import EnterpriseService
from services.excel_service import ExcelService
from services.mail_service import process_outbox
from services.schema import SCHEMA
from tests.common import enable_mock_mail


TODAY = date(2026, 11, 4)
SMTP_CONFIG = {
    'DASHBOARD_MAIL_ENABLED': 'true', 'DASHBOARD_SMTP_HOST': 'smtp.example.test',
    'DASHBOARD_SMTP_PORT': '587', 'DASHBOARD_MAIL_FROM': 'sender@example.test',
    'DASHBOARD_SMTP_USER': 'sender@example.test', 'DASHBOARD_SMTP_PASSWORD': 'fictional-secret',
}


def fictional_data():
    due = (TODAY + timedelta(days=46)).isoformat()
    return {
        'Funcionarios': [dict(codigo='FUNC0001', nome='Pessoa Fictícia', equipe='EQ0001',
                             cargo='Teste', email='person@example.test', admissao='2020-01-01', status='Ativo')],
        'Equipes': [dict(codigo='EQ0001', nome='Equipe Fictícia', responsavel='FUNC0001')],
        'OrdensServico': [dict(codigo='OS0001', descricao='OS fictícia', funcionario='FUNC0001',
                               abertura='2020-01-01', previsao=due, conclusao='', prioridade='Média', status='Pendente')],
        'Acessos': [dict(codigo='AC0001', funcionario='FUNC0001', sistema='Sistema Fictício',
                         concessao='2020-01-01', vencimento=due, status='Ativo')],
        'Renovacoes': [dict(codigo='REN0001', acesso='AC0001', solicitacao='2026-01-01',
                            status='Pendente', responsavel='FUNC0001', observacoes='Fictício')],
    }


def write_workbook(path, data):
    book = Workbook(); book.remove(book.active)
    for sheet, fields in SCHEMA.items():
        ws = book.create_sheet(sheet); ws.append(fields)
        for row in data[sheet]:
            ws.append([row.get(field, '') for field in fields])
    book.save(path); book.close()


class PipelineTests(unittest.TestCase):
    def setUp(self):
        enable_mock_mail(self)
        temp = tempfile.TemporaryDirectory(prefix='dashboardos-pipeline-')
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.auth = AuthService(self.root / 'instance')
        self.service = EnterpriseService(self.auth)
        self.raw = fictional_data()
        self.path = self.root / 'fictional.xlsx'
        write_workbook(self.path, self.raw)
        self.store = ExcelService(self.path)
        self.store.validate(self.raw)
        self.account('eligible')
        for target in ('socket.socket.connect', 'socket.getaddrinfo'):
            guard = patch(target, side_effect=AssertionError('Network forbidden in pipeline tests'))
            guard.start(); self.addCleanup(guard.stop)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM outbox'), 0)
        self.assertNotEqual(self.auth.path.resolve(), Path('instance/auth.sqlite3').resolve())

    def tearDown(self):
        with self.auth.connect() as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])

    def account(self, uid, **values):
        values = {**dict(email=uid + '@example.test', verified=1, email_alerts=1,
                         internal_alerts=1, state='active'), **values}
        with self.auth.connect() as db:
            db.execute('INSERT INTO users VALUES (?,?)', (uid, 'fictional-non-login-hash'))
            db.execute('INSERT INTO account(user_id,email,verified,email_alerts,internal_alerts,state) VALUES (?,?,?,?,?,?)',
                       (uid, values['email'], values['verified'], values['email_alerts'], values['internal_alerts'], values['state']))

    def rows(self, query, args=()):
        with self.auth.connect() as db:
            return [tuple(row) for row in db.execute(query, args)]

    def scalar(self, query, args=()):
        return self.rows(query, args)[0][0]

    def emit(self, key='fictional-event'):
        with self.auth.connect() as db:
            return self.service.emit(db, key, 'operational', 'Fictional event', 'Fictional body', '/acessos')

    @contextmanager
    def smtp(self, **failures):
        with patch.dict(os.environ, SMTP_CONFIG), patch('services.mail_service.smtplib.SMTP') as factory:
            client = factory.return_value
            client.send_message.return_value = {}
            client.quit.return_value = (221, b'Bye')
            for method, error in failures.items():
                if method == 'connect': factory.side_effect = error
                else: getattr(client, method).side_effect = error
            yield client

    def assert_counts(self, events, messages=None):
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM events'), events)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM outbox'), events if messages is None else messages)

    def test_first_observation_of_urgent_records_only_establishes_baseline(self):
        for sheet, field in [('OrdensServico', 'previsao'), ('Acessos', 'vencimento')]:
            original = self.raw[sheet][0]
            self.raw[sheet] = [dict(original, codigo=original['codigo'] + str(i),
                                    **{field: (TODAY + timedelta(days=days)).isoformat()})
                               for i, days in enumerate((45, 30, 0, -1))]
        self.assertEqual(self.service.scan(self.raw, TODAY), 0)
        self.assertEqual(self.service.scan(self.raw, TODAY), 0)
        self.assert_counts(0)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM snapshots'), 8)

    def test_fixed_due_dates_generate_exact_threshold_events_for_os_and_access(self):
        self.assertEqual(self.service.scan(self.raw, TODAY), 0)
        bands = ['31 a 45 dias', 'Até 30 dias', 'Vencem hoje', 'Vencidos']
        for index, (elapsed, band) in enumerate(zip((1, 16, 46, 47), bands), 1):
            with self.subTest(band=band):
                now = TODAY + timedelta(days=elapsed)
                self.assertEqual(self.service.scan(self.raw, now), 2)
                self.assert_counts(2 * index)
                self.assertEqual(self.scalar('SELECT COUNT(*) FROM events WHERE title LIKE ?', ('% · ' + band,)), 2)
                self.assertEqual(EnterpriseService(self.auth).scan(self.raw, now), 0)
        self.assertEqual(self.service.scan(self.raw, TODAY + timedelta(days=48)), 0)
        self.assertEqual(self.rows('SELECT DISTINCT status,attempts FROM outbox'), [('pending', 0)])
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM notifications'), 8)

    def test_due_date_change_emits_due_and_band_not_duplicate_rows(self):
        self.service.scan(self.raw, TODAY)
        for sheet, field in [('OrdensServico', 'previsao'), ('Acessos', 'vencimento')]:
            with self.subTest(sheet=sheet):
                self.raw[sheet][0][field] = (TODAY + timedelta(days=45)).isoformat()
                self.assertEqual(self.service.scan(self.raw, TODAY), 2)
                self.assertEqual(self.service.scan(self.raw, TODAY), 0)
        self.assert_counts(4)
        self.assertEqual(self.scalar('SELECT COUNT(DISTINCT event_key) FROM events'), 4)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM (SELECT event_id,user_id FROM outbox GROUP BY event_id,user_id)'), 4)

    def test_status_and_simultaneous_changes_emit_distinct_fields(self):
        self.service.scan(self.raw, TODAY)
        row = self.raw['OrdensServico'][0]
        row.update(status='Em andamento', previsao=TODAY.isoformat())
        self.assertEqual(self.service.scan(self.raw, TODAY), 3)
        self.assertEqual({key.rsplit(':', 1)[1] for key, in self.rows('SELECT event_key FROM events')}, {'status', 'due', 'band'})
        self.assertEqual(self.service.scan(self.raw, TODAY), 0)
        self.raw['Acessos'][0]['status'] = 'Revogado'
        self.assertEqual(self.service.scan(self.raw, TODAY), 2)
        self.assert_counts(5)

    def test_closed_records_do_not_cross_time_bands_but_due_edits_still_emit(self):
        self.raw['OrdensServico'][0].update(status='Concluída', conclusao=TODAY.isoformat())
        self.raw['Acessos'][0]['status'] = 'Revogado'
        self.service.scan(self.raw, TODAY)
        self.assertEqual(self.service.scan(self.raw, TODAY + timedelta(days=60)), 0)
        self.raw['OrdensServico'][0]['previsao'] = (TODAY + timedelta(days=20)).isoformat()
        self.assertEqual(self.service.scan(self.raw, TODAY), 1)
        self.assert_counts(1)

    def test_status_reversal_and_delete_recreate_preserve_event_versions(self):
        self.service.scan(self.raw, TODAY)
        row = self.raw['OrdensServico'][0]
        for status in ('Em andamento', 'Pendente', 'Em andamento'):
            row['status'] = status
            self.assertEqual(self.service.scan(self.raw, TODAY), 1)
        removed = self.raw['OrdensServico'].pop()
        self.assertEqual(self.service.scan(self.raw, TODAY), 0)
        self.raw['OrdensServico'].append(removed)
        self.assertEqual(self.service.scan(self.raw, TODAY), 2)
        self.assertEqual(self.service.scan(self.raw, TODAY), 0)
        self.assert_counts(5)
        self.assertEqual(self.scalar('SELECT COUNT(DISTINCT event_key) FROM events'), 5)

    def test_renewal_changes_do_not_generate_operational_events(self):
        self.service.scan(self.raw, TODAY)
        self.raw['Renovacoes'][0].update(status='Solicitada', solicitacao=TODAY.isoformat())
        self.assertEqual(self.service.scan(self.raw, TODAY), 0)
        self.assert_counts(0)

    def test_excel_observer_and_reconciliation_use_only_fictional_workbook(self):
        from app import create_app
        app = create_app(self.path, auth_directory=self.auth.directory)
        store = app.config['STORE']
        row = dict(self.raw['OrdensServico'][0], status='Em andamento')
        store.mutate('OrdensServico', row, code=row['codigo'])
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM events'), 1)
        self.assertEqual(self.service.scan(store.read()), 0)
        # A failed post-Excel observer is recoverable from the durable baseline.
        calls = []
        original = store.observer
        def interrupted(raw):
            calls.append(1)
            if len(calls) == 2: raise RuntimeError('simulated observer interruption')
            original(raw)
        store.observer = interrupted
        row['status'] = 'Pendente'
        with self.assertLogs('services.excel_service', level='ERROR'):
            store.mutate('OrdensServico', row, code=row['codigo'])
        self.assertEqual(store.read()['OrdensServico'][0]['status'], 'Pendente')
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM events'), 1)
        self.assertEqual(EnterpriseService(self.auth).scan(store.read()), 1)
        self.assert_counts(2)
        self.assertEqual(self.service.scan(store.read()), 0)

    def test_concurrent_scanners_emit_each_change_once(self):
        self.service.scan(self.raw, TODAY)
        self.raw['OrdensServico'][0]['status'] = 'Em andamento'
        barrier = threading.Barrier(2)
        def scan():
            barrier.wait(timeout=5)
            return EnterpriseService(self.auth).scan(copy.deepcopy(self.raw), TODAY)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(scan) for _ in range(2)]
            self.assertEqual(sorted(f.result(timeout=15) for f in futures), [0, 1])
        self.assert_counts(1)

    def test_emission_is_atomic_on_failure_and_retries_without_duplicates(self):
        with self.auth.connect() as db:
            db.execute("CREATE TRIGGER fail_test_outbox BEFORE INSERT ON outbox BEGIN SELECT RAISE(ABORT,'fictional failure'); END")
        import sqlite3
        with self.assertRaises(sqlite3.IntegrityError):
            self.emit()
        self.assert_counts(0)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM notifications'), 0)
        with self.auth.connect() as db: db.execute('DROP TRIGGER fail_test_outbox')
        self.assertTrue(self.emit()); self.assertFalse(self.emit())
        self.assert_counts(1)

    def test_preferences_at_event_creation_and_internal_alert_independence(self):
        for uid, values in [('inactive', {'state': 'inactive'}), ('blocked', {'state': 'blocked'}),
                            ('empty', {'email': ''}), ('unverified', {'verified': 0}),
                            ('optout', {'email_alerts': 0}), ('internaloff', {'internal_alerts': 0})]:
            self.account(uid, **values)
        self.emit()
        self.assertEqual(self.rows('SELECT user_id FROM outbox ORDER BY user_id'), [('eligible',), ('internaloff',)])
        self.assertEqual(self.rows('SELECT user_id FROM notifications ORDER BY user_id'),
                         [('eligible',), ('empty',), ('internaloff',), ('optout',), ('unverified',)])
        with self.smtp() as client:
            self.assertEqual(process_outbox(self.auth), 2)
            self.assertEqual(client.send_message.call_count, 2)

    def test_preferences_rechecked_after_queue_creation(self):
        changes = [('inactive', "state='inactive'", 'pending'), ('blocked', "state='blocked'", 'pending'),
                   ('empty', "email=''", 'cancelled'), ('changed', "email='new@example.test'", 'cancelled'),
                   ('unverified', 'verified=0', 'cancelled'), ('optout', 'email_alerts=0', 'cancelled')]
        for uid, _, _ in changes: self.account(uid)
        self.emit()
        with self.auth.connect() as db:
            for uid, change, _ in changes: db.execute('UPDATE account SET ' + change + ' WHERE user_id=?', (uid,))
        with self.smtp() as client:
            self.assertEqual(process_outbox(self.auth), 1)
            client.send_message.assert_called_once()
        self.assertEqual(self.rows("SELECT user_id,status,attempts FROM outbox WHERE user_id!='eligible' ORDER BY user_id"),
                         sorted((uid, status, 0) for uid, _, status in changes))

    def test_becoming_eligible_does_not_replay_an_existing_event(self):
        with self.auth.connect() as db: db.execute('UPDATE account SET verified=0')
        self.assertTrue(self.emit()); self.assert_counts(1, 0)
        with self.auth.connect() as db: db.execute('UPDATE account SET verified=1')
        self.assertFalse(self.emit()); self.assert_counts(1, 0)
        self.assertTrue(self.emit('next-event')); self.assert_counts(2, 1)

    def test_reactivation_resumes_previously_pending_operational_mail(self):
        self.emit()
        with self.auth.connect() as db: db.execute("UPDATE account SET state='inactive'")
        sender = MagicMock()
        self.assertEqual(process_outbox(self.auth, sender), 0)
        with self.auth.connect() as db: db.execute("UPDATE account SET state='active'")
        self.assertEqual(process_outbox(self.auth, sender), 1)
        sender.assert_called_once()

    def test_reservation_and_attempt_are_durable_before_sender_and_limit_is_respected(self):
        for i in range(3): self.emit('event-' + str(i))
        observed = []
        def sender(*args):
            observed.append(self.rows("SELECT o.status,o.attempts,m.result FROM outbox o JOIN mail_attempts m ON m.outbox_id=o.id WHERE o.status='sending'"))
        self.assertEqual(process_outbox(self.auth, sender, limit=1), 1)
        self.assertEqual(observed, [[('sending', 1, 'sending')]])
        self.assertEqual(self.rows('SELECT status,attempts FROM outbox ORDER BY id'), [('sent', 1), ('pending', 0), ('pending', 0)])
        self.assertEqual(self.rows('SELECT result,error_type FROM mail_attempts'), [('sent', None)])

    def test_reservation_failure_rolls_back_status_and_attempt_count(self):
        import sqlite3
        self.emit()
        with self.auth.connect() as db:
            db.execute("CREATE TRIGGER fail_test_attempt BEFORE INSERT ON mail_attempts BEGIN SELECT RAISE(ABORT,'fictional reservation failure'); END")
        sender = MagicMock()
        with self.assertRaises(sqlite3.IntegrityError): process_outbox(self.auth, sender)
        sender.assert_not_called()
        self.assertEqual(self.rows('SELECT status,attempts FROM outbox'), [('pending', 0)])
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM mail_attempts'), 0)
        with self.auth.connect() as db: db.execute('DROP TRIGGER fail_test_attempt')
        self.assertEqual(process_outbox(self.auth, sender), 1)

    def test_confirmation_mail_is_distinct_from_opted_out_operational_alerts(self):
        with self.auth.connect() as db: db.execute('UPDATE account SET verified=0,email_alerts=0')
        self.emit()
        self.assert_counts(1, 0)
        self.assertIsNone(self.service.token('eligible', 'eligible', 'verify'))
        self.assertEqual(self.rows('SELECT event_id,status FROM outbox'), [(None, 'pending')])
        with self.smtp() as client:
            self.assertEqual(process_outbox(self.auth), 1)
            client.send_message.assert_called_once()

    def test_eligibility_change_after_reservation_is_not_rechecked_during_smtp(self):
        # Characterization of the in-flight window, not a new permission policy.
        self.emit()
        def opt_out(*args):
            with self.auth.connect() as db: db.execute('UPDATE account SET email_alerts=0')
        with self.smtp(login=opt_out) as client:
            self.assertEqual(process_outbox(self.auth), 1)
            client.send_message.assert_called_once()
        self.assertEqual(self.scalar('SELECT email_alerts FROM account'), 0)
        self.assertEqual(self.scalar('SELECT status FROM outbox'), 'sent')

    def test_concurrent_workers_reserve_different_rows_once(self):
        for i in range(4): self.emit('parallel-' + str(i))
        barrier = threading.Barrier(2)
        sent = []; lock = threading.Lock()
        def sender(recipient, subject, body):
            with lock: sent.append((recipient, subject, body))
            barrier.wait(timeout=5)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures = [pool.submit(process_outbox, self.auth, sender) for _ in range(2)]
            self.assertEqual(sum(f.result(timeout=15) for f in futures), 4)
        self.assertEqual(len(sent), 4)
        self.assertEqual(self.rows('SELECT status,attempts FROM outbox'), [('sent', 1)] * 4)
        self.assertEqual(self.rows('SELECT outbox_id,COUNT(*) FROM mail_attempts GROUP BY outbox_id'), [(i, 1) for i in range(1, 5)])

    def test_transient_retry_backoff_then_acceptance(self):
        self.emit()
        with self.smtp(connect=ConnectionRefusedError('private provider text')) as client:
            self.assertEqual(process_outbox(self.auth), 0)
            client.send_message.assert_not_called()
        self.assertEqual(self.rows('SELECT status,attempts,last_error FROM outbox'), [('pending', 1, 'ConnectionRefusedError')])
        self.assertGreater(self.scalar('SELECT next_attempt FROM outbox'), time.time())
        with self.smtp() as client:
            self.assertEqual(process_outbox(self.auth), 0); client.send_message.assert_not_called()
            with self.auth.connect() as db: db.execute('UPDATE outbox SET next_attempt=0')
            self.assertEqual(process_outbox(self.auth), 1)
        self.assertEqual(self.rows('SELECT result FROM mail_attempts ORDER BY id'), [('pending',), ('sent',)])

    def test_explicit_temporary_rejection_exhausts_three_attempts(self):
        self.emit()
        with self.smtp(send_message=smtplib.SMTPDataError(451, b'private provider text')):
            for attempt in range(1, 4):
                self.assertEqual(process_outbox(self.auth), 0)
                self.assertEqual(self.rows('SELECT status,attempts FROM outbox'), [('failed' if attempt == 3 else 'pending', attempt)])
                with self.auth.connect() as db: db.execute('UPDATE outbox SET next_attempt=0')
        with self.smtp() as client:
            self.assertEqual(process_outbox(self.auth), 0); client.send_message.assert_not_called()

    def test_permanent_authentication_and_recipient_rejection_are_not_retried(self):
        for i, (method, error) in enumerate([
            ('login', smtplib.SMTPAuthenticationError(535, b'private provider text')),
            ('send_message', smtplib.SMTPRecipientsRefused({'eligible@example.test': (550, b'private provider text')})),
        ]):
            self.emit('permanent-' + str(i))
            with self.smtp(**{method: error}): self.assertEqual(process_outbox(self.auth), 0)
        self.assertEqual(self.rows('SELECT status,attempts FROM outbox'), [('failed', 1)] * 2)
        with self.smtp() as client:
            self.assertEqual(process_outbox(self.auth), 0); client.send_message.assert_not_called()
        self.assertNotIn('private', str(self.rows('SELECT last_error FROM outbox')))

    def test_uncertain_result_survives_restart_without_retry(self):
        self.emit()
        with self.smtp(send_message=smtplib.SMTPServerDisconnected('private provider text')):
            self.assertEqual(process_outbox(self.auth), 0)
        self.assertEqual(self.rows('SELECT status,attempts FROM outbox'), [('uncertain', 1)])
        restarted = AuthService(self.auth.directory)
        with self.smtp() as client:
            self.assertEqual(process_outbox(restarted), 0); client.send_message.assert_not_called()
        self.assertEqual(self.rows('SELECT result,error_type FROM mail_attempts'), [('uncertain', 'SMTPServerDisconnected')])

    def test_interrupt_during_send_preserves_sending_and_other_pending_rows(self):
        self.emit('first'); self.emit('second')
        class SimulatedStop(BaseException): pass
        with self.assertRaises(SimulatedStop):
            process_outbox(self.auth, MagicMock(side_effect=SimulatedStop()))
        self.assertEqual(self.rows('SELECT status,attempts FROM outbox'), [('sending', 1), ('pending', 0)])
        sender = MagicMock()
        self.assertEqual(process_outbox(AuthService(self.auth.directory), sender), 1)
        sender.assert_called_once()
        self.assertEqual(self.rows('SELECT status,attempts FROM outbox'), [('sending', 1), ('sent', 1)])

    def test_provider_acceptance_then_database_failure_never_automatically_resends(self):
        self.emit()
        original = self.auth.connect
        calls = []
        @contextmanager
        def interrupted():
            calls.append(1)
            if len(calls) == 2: raise OSError('simulated persistence interruption')
            with original() as db: yield db
        with self.smtp() as client, patch.object(self.auth, 'connect', interrupted):
            with self.assertRaises(OSError): process_outbox(self.auth)
            client.send_message.assert_called_once()
        self.assertEqual(self.rows('SELECT status,attempts FROM outbox'), [('sending', 1)])
        with self.smtp() as client:
            self.assertEqual(process_outbox(AuthService(self.auth.directory)), 0)
            client.send_message.assert_not_called()

    def test_accepted_mail_remains_sent_after_close_error_and_restart(self):
        self.emit()
        with self.smtp(quit=smtplib.SMTPResponseException(500, b'private provider text')) as client:
            self.assertEqual(process_outbox(self.auth), 1); client.send_message.assert_called_once()
        self.assertEqual(self.rows('SELECT status,attempts,last_error FROM outbox'), [('sent', 1, None)])
        with self.smtp() as client:
            self.assertEqual(process_outbox(AuthService(self.auth.directory)), 0)
            client.send_message.assert_not_called()
