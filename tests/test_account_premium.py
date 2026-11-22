"""Email and account regressions; all writes use temporary databases."""
import os
import smtplib
import time
from unittest.mock import patch
from app import create_app
from services.mail_service import process_outbox, mail_configuration, smtp_send
from tests.common import DataCase, login_admin, enable_mock_mail


class AccountPremiumTests(DataCase):
    def setUp(self):
        super().setUp()
        enable_mock_mail(self)
        self.app = create_app(self.path)
        self.client = self.app.test_client()
        self.auth = self.app.config['AUTH']
        self.service = self.app.config['ENTERPRISE']
        self.password = 'isolated-test-password-123'
        self.headers = login_admin(self.app, self.client, 'premium', self.password)
        self.service.update_profile('premium', {'email': 'account@example.test', 'current_password': self.password})
        self.client.post('/login', json={'user_id': 'premium', 'password': self.password}, headers=self.headers)
        with self.client.session_transaction() as session:
            self.headers = {'X-CSRF-Token': session['csrf']}

    def request_code(self):
        return self.client.post('/api/profile/verification', json={}, headers=self.headers)

    def test_queue_delivery_confirmation_and_private_status(self):
        with patch.dict(os.environ, {'DASHBOARD_MAIL_ENABLED': 'false'}):
            response = self.request_code()
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json['state'], 'queued')
            self.assertFalse(response.json['delivery_available'])
            self.assertEqual(process_outbox(self.auth), 0)
        sent = []
        self.assertEqual(process_outbox(self.auth, lambda *args: sent.append(args)), 1)
        raw = sent[0][2].split(': ')[-1]
        status = self.client.get('/api/profile/verification')
        self.assertEqual(status.json['state'], 'sent')
        self.assertNotIn(raw, status.text)
        with self.auth.connect() as db:
            row = db.execute('SELECT digest,expires FROM tokens').fetchone()
            self.assertNotEqual(row['digest'], raw)
            self.assertAlmostEqual(row['expires']-time.time(), 1800, delta=10)
        response = self.client.post('/api/profile/verify', json={'token': raw}, headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.service.verification_status('premium')['state'], 'verified')
        self.assertEqual(self.client.post('/api/profile/verify', json={'token': raw}, headers=self.headers).status_code, 400)

    def test_resend_cooldown_invalidation_and_expiration(self):
        self.assertEqual(self.request_code().status_code, 200)
        with self.auth.connect() as db:
            first = db.execute('SELECT body FROM outbox').fetchone()[0].split(': ')[-1]
        self.assertEqual(self.request_code().status_code, 400)
        with self.auth.connect() as db:
            db.execute("UPDATE audit SET occurred='2000-01-01T00:00:00+00:00' WHERE action='token.verify'")
        self.assertEqual(self.request_code().status_code, 200)
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM outbox ORDER BY id LIMIT 1').fetchone()[0], 'cancelled')
            second = db.execute('SELECT body FROM outbox ORDER BY id DESC LIMIT 1').fetchone()[0].split(': ')[-1]
        with self.assertRaises(ValueError):
            self.service.consume(first, 'verify', uid='premium')
        with self.auth.connect() as db:
            db.execute('UPDATE tokens SET expires=0')
        with self.assertRaises(ValueError):
            self.service.consume(second, 'verify', uid='premium')
        self.assertFalse(self.service.profile('premium')['verified'])

    def test_invalid_attempts_persist_and_block(self):
        for _ in range(5):
            self.assertEqual(self.client.post('/api/profile/verify', json={'token': 'wrong'}, headers=self.headers).status_code, 400)
        response = self.client.post('/api/profile/verify', json={'token': 'wrong'}, headers=self.headers)
        self.assertIn('dez minutos', response.json['error'])
        with self.auth.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE action='verification.invalid'").fetchone()[0], 5)

    def test_expired_queue_never_sends_and_hourly_limit(self):
        self.request_code()
        with self.auth.connect() as db:
            db.execute('UPDATE tokens SET expires=0')
        sent = []
        self.assertEqual(process_outbox(self.auth, lambda *args: sent.append(args)), 0)
        self.assertEqual(sent, [])
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM outbox').fetchone()[0], 'cancelled')
            db.execute("DELETE FROM audit WHERE action='token.verify'")
            from services.enterprise_service import stamp
            for _ in range(5):
                db.execute("INSERT INTO audit(actor,action,target,occurred) VALUES ('premium','token.verify','premium',?)", (stamp(),))
        self.assertEqual(self.request_code().status_code, 400)

    def test_missing_configuration_and_smtp_tls(self):
        with patch.dict(os.environ, {'DASHBOARD_MAIL_ENABLED': 'true', 'DASHBOARD_EMAIL_SUSPENDED': 'false'}, clear=True):
            self.assertFalse(mail_configuration()['ready'])
            self.assertIn('DASHBOARD_SMTP_HOST', mail_configuration()['missing'])
            self.assertEqual(self.request_code().status_code, 200)
            self.assertEqual(process_outbox(self.auth), 0)
            self.assertEqual(self.service.verification_status('premium')['state'], 'failed')
        config = {'DASHBOARD_EMAIL_SUSPENDED': 'false', 'DASHBOARD_MAIL_ENABLED': 'true', 'DASHBOARD_SMTP_HOST': 'smtp.example.test', 'DASHBOARD_MAIL_FROM': 'sender@example.test', 'DASHBOARD_SMTP_USER': 'test-user', 'DASHBOARD_SMTP_PASSWORD': 'test-secret'}
        with patch.dict(os.environ, config, clear=True), patch('services.mail_service.smtplib.SMTP') as smtp:
            smtp.return_value.send_message.return_value = {}
            smtp.return_value.quit.return_value = (221, b'Bye')
            smtp_send('recipient@example.test', 'Test', 'Isolated test')
            client = smtp.return_value
            client.starttls.assert_called_once()
            client.login.assert_called_once_with('test-user', 'test-secret')
            client.send_message.assert_called_once()

    def test_connection_and_authentication_failures_are_sanitized(self):
        self.request_code()
        with patch('services.mail_service.smtp_send', side_effect=ConnectionRefusedError('private detail')):
            with patch.dict(os.environ, {'DASHBOARD_MAIL_ENABLED': 'true'}):
                self.assertEqual(process_outbox(self.auth), 0)
        self.assertEqual(self.service.verification_status('premium')['state'], 'retrying')
        with self.auth.connect() as db:
            db.execute('UPDATE outbox SET next_attempt=0')
        def rejected(*args):
            raise smtplib.SMTPAuthenticationError(535, b'private credential detail')
        self.assertEqual(process_outbox(self.auth, rejected), 0)
        self.assertEqual(self.service.verification_status('premium')['state'], 'failed')
        self.assertNotIn('private', self.client.get('/api/profile/verification').text)

    def test_preferences_and_batch_actions_are_scoped_to_account(self):
        self.service.update_profile('premium', {'appearance': {'theme': 'dark', 'font': 'large'}, 'email_alerts': False})
        self.assertEqual(create_app(self.path).config['ENTERPRISE'].profile('premium')['appearance']['theme'], 'dark')
        self.auth.create_admin('another', self.password)
        with self.auth.connect() as db:
            self.service.emit(db, 'isolated-event', 'operational', 'Test', 'Body', '/acessos')
            self.assertEqual(db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0], 0)
        self.service.notification_action('premium', 'read')
        self.assertIsNotNone(self.service.notifications('premium')[0]['read_at'])
        self.assertIsNone(self.service.notifications('another')[0]['read_at'])
        self.service.notification_action('premium', 'delete')
        self.assertEqual(self.service.notifications('premium'), [])
        self.assertEqual(len(self.service.notifications('another')), 1)
