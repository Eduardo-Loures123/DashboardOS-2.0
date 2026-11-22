"""Offline transport and temporary-outbox regression tests."""
import os
import smtplib
import ssl
from unittest import TestCase
from unittest.mock import patch, MagicMock
from services.mail_service import smtp_send, SMTPTransportError, process_outbox
from tests import test_account_premium
from tests.common import DataCase
from tests.common import login_admin, enable_mock_mail
from app import create_app

CONFIG = {'DASHBOARD_EMAIL_SUSPENDED': 'false', 'DASHBOARD_MAIL_ENABLED': 'true', 'DASHBOARD_SMTP_HOST': 'smtp.example.test',
          'DASHBOARD_MAIL_FROM': 'sender@example.test', 'DASHBOARD_SMTP_USER': 'test-user',
          'DASHBOARD_SMTP_PASSWORD': 'private-test-secret'}


class TransportTests(TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, CONFIG, clear=True); self.env.start()
        self.addCleanup(self.env.stop)
        self.network = patch('socket.create_connection', side_effect=AssertionError('Network forbidden'))
        self.network.start(); self.addCleanup(self.network.stop)
        self.smtp = patch('services.mail_service.smtplib.SMTP'); self.factory = self.smtp.start()
        self.addCleanup(self.smtp.stop)
        self.client = self.factory.return_value
        self.client.send_message.return_value = {}
        self.client.quit.return_value = (221, b'Bye')

    def send(self):
        return smtp_send('recipient@example.test', 'Test', 'Private body')

    def test_accepted_with_validated_tls_and_single_recipient(self):
        self.send()
        self.factory.assert_called_once_with('smtp.example.test', 587, timeout=20)
        context = self.client.starttls.call_args.kwargs['context']
        self.assertEqual(context.verify_mode, ssl.CERT_REQUIRED)
        self.assertTrue(context.check_hostname)
        self.assertEqual(self.client.send_message.call_args.kwargs['to_addrs'], ['recipient@example.test'])
        self.client.quit.assert_called_once(); self.client.close.assert_called_once()

    def test_pre_acceptance_failures(self):
        for stage, error in [('CONNECT', ConnectionRefusedError('secret')),
                             ('STARTTLS', ssl.SSLCertVerificationError('secret')),
                             ('AUTH', smtplib.SMTPAuthenticationError(535, b'secret'))]:
            with self.subTest(stage=stage):
                self.factory.side_effect = error if stage == 'CONNECT' else None
                self.client.starttls.side_effect = error if stage == 'STARTTLS' else None
                self.client.login.side_effect = error if stage == 'AUTH' else None
                with self.assertRaises(SMTPTransportError) as caught:
                    self.send()
                self.assertEqual(caught.exception.stage, stage)
                self.assertFalse(caught.exception.uncertain)
                self.assertNotIn('secret', str(caught.exception))
                self.assertEqual(caught.exception.permanent, stage != 'CONNECT')
        self.client.send_message.assert_not_called()

    def test_close_error_does_not_undo_acceptance_or_leak_details(self):
        self.client.quit.side_effect = smtplib.SMTPResponseException(500, b'private-test-secret')
        self.client.close.side_effect = OSError('Private body')
        with self.assertLogs('services.mail_service', level='INFO') as logs:
            self.send()
        output = ' '.join(logs.output)
        self.assertIn('accepted_close_error', output)
        self.assertIn('smtp_code=500', output)
        for secret in ['private-test-secret', 'Private body', 'recipient@example.test']:
            self.assertNotIn(secret, output)

    def test_transmission_disconnect_is_uncertain(self):
        self.client.send_message.side_effect = smtplib.SMTPServerDisconnected('private detail')
        with self.assertRaises(SMTPTransportError) as caught:
            self.send()
        self.assertTrue(caught.exception.uncertain)
        self.client.quit.assert_not_called(); self.client.close.assert_called_once()

    def test_explicit_rejection_is_not_uncertain(self):
        for code in (451, 550):
            self.client.send_message.side_effect = smtplib.SMTPDataError(code, b'private detail')
            with self.assertRaises(SMTPTransportError) as caught:
                self.send()
            self.assertFalse(caught.exception.uncertain)
            self.assertEqual(caught.exception.permanent, code == 550)
            self.assertEqual(caught.exception.smtp_code, code)

    def test_disabled_configuration_never_connects(self):
        os.environ['DASHBOARD_MAIL_ENABLED'] = 'false'
        with self.assertRaises(RuntimeError):
            self.send()
        self.factory.assert_not_called()


class QueueTransportTests(DataCase):
    request_code = test_account_premium.AccountPremiumTests.request_code

    def setUp(self):
        super().setUp()
        enable_mock_mail(self)
        self.app = create_app(self.path)
        self.client = self.app.test_client()
        self.auth = self.app.config['AUTH']
        self.service = self.app.config['ENTERPRISE']
        password = 'isolated-test-password-123'
        self.headers = login_admin(self.app, self.client, 'premium', password)
        self.service.update_profile('premium', {'email': 'account@example.test', 'current_password': password})
        self.client.post('/login', json={'user_id': 'premium', 'password': password}, headers=self.headers)
        with self.client.session_transaction() as session:
            self.headers = {'X-CSRF-Token': session['csrf']}
    def test_transport_uncertain_and_sending_are_never_retried(self):
        self.request_code()
        failure = SMTPTransportError('TRANSMIT', TimeoutError('private detail'))
        sender = MagicMock(side_effect=failure)
        self.assertEqual(process_outbox(self.auth, sender), 0)
        with self.auth.connect() as db:
            row = db.execute('SELECT status,attempts,last_error FROM outbox').fetchone()
            self.assertEqual(tuple(row), ('uncertain', 1, 'TimeoutError'))
            db.execute('UPDATE outbox SET next_attempt=0')
        self.assertEqual(process_outbox(self.auth, sender), 0)
        sender.assert_called_once()
        with self.auth.connect() as db:
            db.execute("UPDATE outbox SET status='sending'")
        self.assertEqual(process_outbox(self.auth, sender), 0)
        sender.assert_called_once()

    def test_quit_failure_is_recorded_sent_and_not_retried(self):
        self.request_code()
        with patch.dict(os.environ, CONFIG, clear=True), patch('services.mail_service.smtplib.SMTP') as smtp:
            smtp.return_value.send_message.return_value = {}
            smtp.return_value.quit.side_effect = smtplib.SMTPResponseException(500, b'private')
            self.assertEqual(process_outbox(self.auth), 1)
            self.assertEqual(process_outbox(self.auth), 0)
            smtp.return_value.send_message.assert_called_once()
        with self.auth.connect() as db:
            self.assertEqual(tuple(db.execute('SELECT status,attempts FROM outbox').fetchone()), ('sent', 1))
