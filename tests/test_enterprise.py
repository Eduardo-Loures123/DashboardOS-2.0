import copy
import hashlib
import json
import secrets
import sqlite3
import time
from datetime import date, timedelta
from unittest.mock import patch
from app import create_app
from services.auth_service import AuthService
from services.enterprise_service import EnterpriseService
from services.mail_service import process_outbox
from tests.common import DataCase, login_admin, enable_mock_mail


class EnterpriseTests(DataCase):
    def setUp(self):
        super().setUp()
        enable_mock_mail(self)
        self.app = create_app(self.path); self.app.testing = True
        self.client = self.app.test_client(); self.auth = self.app.config['AUTH']
        self.service = self.app.config['ENTERPRISE']
        self.password = secrets.token_urlsafe(24)
        self.headers = login_admin(self.app, self.client, 'principal', self.password)

    def promote(self):
        self.service.promote_initial('principal', self.password)

    def test_migration_copy_and_preservation(self):
        directory = self.path.parent / 'legacy'; directory.mkdir()
        with sqlite3.connect(directory / 'auth.sqlite3') as db:
            db.executescript('CREATE TABLE users(id TEXT PRIMARY KEY,password_hash TEXT NOT NULL);CREATE TABLE sessions(token_hash TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),expires REAL NOT NULL);CREATE TABLE attempts(client TEXT,occurred REAL);')
            db.execute('INSERT INTO users VALUES (?,?)', ('legado', 'hash-preservado'))
        db.close()
        auth = AuthService(directory); service = EnterpriseService(auth)
        self.assertFalse(service.ready())
        before = auth.path.read_bytes()
        backup = service.migrate()
        self.assertTrue(backup.exists())
        with sqlite3.connect(backup) as db:
            self.assertEqual(db.execute('SELECT id,password_hash FROM users').fetchall(), [('legado', 'hash-preservado')])
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        db.close()
        self.assertEqual(service.profile('legado')['role'], 'admin')
        self.assertIsNone(service.profile('legado')['created'])
        with auth.connect() as db:
            self.assertEqual(db.execute('SELECT password_hash FROM users').fetchone()[0], 'hash-preservado')
        service.migrate()
        self.assertEqual(len(service.users()), 1)

    def test_permission_matrix_and_last_superadmin(self):
        for endpoint in ['/api/admin/users', '/api/admin/audit', '/api/admin/announcements']:
            self.assertEqual(self.client.get(endpoint).status_code, 403)
        self.promote()
        self.assertEqual(self.client.get('/administracao').status_code, 200)
        self.assertEqual(self.client.get('/api/admin/users').status_code, 200)
        result = self.client.put('/api/admin/users/principal', json={'state': 'inactive'}, headers=self.headers)
        self.assertEqual(result.status_code, 400)
        uid = self.service.create_user('principal', {'user_id': 'reader', 'password': self.password, 'role': 'user'})
        user = self.app.test_client(); user.get('/login')
        with user.session_transaction() as session: headers = {'X-CSRF-Token': session['csrf']}
        user.post('/login', json={'user_id': uid, 'password': self.password}, headers=headers)
        with user.session_transaction() as session: headers = {'X-CSRF-Token': session['csrf']}
        self.assertEqual(user.post('/api/records/Equipes', json={}, headers=headers).status_code, 403)
        self.assertEqual(user.get('/api/admin/users').status_code, 403)
        self.assertEqual(user.get('/api/profile').status_code, 200)
        self.assertEqual(user.put('/api/profile', json={'role': 'superadmin'}, headers=headers).status_code, 200)
        self.assertEqual(self.service.profile(uid)['role'], 'user')
        self.service.manage('principal', uid, {'state': 'blocked'})
        self.assertEqual(user.get('/api/profile').status_code, 401)
        self.assertEqual(self.auth.authenticate(uid, self.password, 'test')[1], 401)

    def test_profile_password_identifier_and_private_fields(self):
        self.promote()
        response = self.client.get('/api/profile')
        self.assertNotIn('password_hash', response.text)
        self.assertNotIn(self.password, response.text)
        for data in [{'email': 'bad'}, {'email': 'mail@example.test'}, {'password': 'short', 'current_password': self.password}, {'appearance': {'theme': 'invalid'}}, {'internal_alerts': 'false'}]:
            self.assertEqual(self.client.put('/api/profile', json=data, headers=self.headers).status_code, 400)
        self.service.create_user('principal', {'user_id': 'duplicate', 'password': self.password})
        self.assertEqual(self.client.put('/api/profile', json={'user_id': 'duplicate', 'current_password': self.password}, headers=self.headers).status_code, 400)
        self.assertEqual(self.client.put('/api/profile', json={'display_name': '<script>text</script>', 'appearance': {'theme': 'dark'}}, headers=self.headers).status_code, 200)
        result = self.client.put('/api/profile', json={'user_id': 'renamed', 'password': self.password + 'new', 'current_password': self.password}, headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json['redirect'], '/login')
        self.assertEqual(self.auth.authenticate('renamed', self.password, 'test')[1], 401)
        self.assertEqual(self.auth.authenticate('renamed', self.password + 'new', 'test')[1], 200)
        self.assertEqual(self.service.profile('renamed')['role'], 'superadmin')

    def test_verification_and_reset_single_use_expiration(self):
        self.promote()
        self.service.update_profile('principal', {'email': 'mail@example.test', 'current_password': self.password})
        self.assertFalse(self.service.profile('principal')['verified'])
        self.assertIsNone(self.service.token('principal', 'principal', 'verify'))
        sent = []
        self.assertEqual(process_outbox(self.auth, lambda *args: sent.append(args)), 1)
        token = sent[0][2].split(': ')[-1]
        with self.assertRaises(ValueError): self.service.consume(token, 'verify', uid='other')
        self.service.consume(token, 'verify', uid='principal')
        self.assertTrue(self.service.profile('principal')['verified'])
        with self.assertRaises(ValueError): self.service.consume(token, 'verify')
        token = self.service.token('principal', 'principal', 'reset')
        self.service.consume(token, 'reset', password=self.password + 'new')
        with self.assertRaises(ValueError): self.service.consume(token, 'reset', password=self.password)
        token = self.service.token('principal', 'principal', 'reset')
        with self.auth.connect() as db: db.execute('UPDATE tokens SET expires=0')
        with self.assertRaises(ValueError): self.service.consume(token, 'reset', password=self.password)

    def test_scan_real_transitions_restart_dedup_boundaries(self):
        self.promote(); raw = copy.deepcopy(self.raw); today = date(2026, 11, 1)
        row = raw['OrdensServico'][0]; row['status'] = 'Pendente'; row['previsao'] = (today + timedelta(days=46)).isoformat()
        self.assertEqual(self.service.scan(raw, today), 0)
        self.assertEqual(self.service.scan(raw, today), 0)
        # Advance only the selected record's date, keeping all other records stable.
        for days in (45, 31, 30, 1, 0, -1):
            row['previsao'] = (today + timedelta(days=days)).isoformat()
            self.assertGreater(self.service.scan(raw, today), 0)
            self.assertEqual(EnterpriseService(self.auth).scan(raw, today), 0)
        previous = len(self.service.notifications('principal'))
        row['status'] = 'Em andamento'; self.service.scan(raw, today)
        row['status'] = 'Pendente'; self.service.scan(raw, today)
        self.assertGreater(len(self.service.notifications('principal')), previous)
        access = raw['Acessos'][0]; access['vencimento'] = today.isoformat(); access['status'] = 'Ativo'
        self.assertGreater(self.service.scan(raw, today), 0)
        self.assertGreater(self.service.scan(raw, today + timedelta(days=1)), 0)
        self.assertEqual(self.service.scan(raw, today + timedelta(days=1)), 0)
        rows = self.service.notifications('principal'); self.assertTrue(rows)
        self.assertTrue(any('/acessos?q=' in r['link'] for r in rows))

    def test_notifications_ownership_announcements_history(self):
        self.promote(); self.service.create_user('principal', {'user_id': 'reader', 'password': self.password})
        self.assertEqual(self.client.post('/api/admin/announcements', json={'title': 'Aviso', 'message': 'Manutenção'}, headers=self.headers).status_code, 400)
        result = self.client.post('/api/admin/announcements', json={'title': 'Aviso', 'message': '<script>Texto</script>', 'recipients': ['principal'], 'confirmed': True}, headers=self.headers)
        self.assertEqual(result.status_code, 201)
        self.assertEqual(self.service.notifications('reader'), [])
        data = self.client.get('/api/notifications').json
        self.assertEqual(data['unread'], 1)
        nid = data['notifications'][0]['id']
        self.service.notification_action('reader', 'delete', nid)
        self.assertEqual(len(self.service.notifications('principal')), 1)
        self.assertEqual(self.client.post('/api/notifications/'+str(nid), json={'action': 'read'}, headers=self.headers).status_code, 200)
        self.assertEqual(self.client.get('/api/notifications').json['unread'], 0)
        self.client.post('/api/notifications', json={'action': 'delete'}, headers=self.headers)
        self.assertEqual(self.service.notifications('principal'), [])
        self.assertEqual(len(self.service.history('announcements')), 1)
        self.assertTrue(self.service.history('audit'))
        with self.auth.connect() as db: self.assertEqual(db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0], 0)

    def test_email_disabled_failures_retries_and_preferences(self):
        self.promote()
        with self.auth.connect() as db:
            db.execute("UPDATE account SET email='mail@example.test',verified=1,email_alerts=1")
            self.service.emit(db, 'test', 'operational', 'Title', 'Body', '/acessos')
        with patch.dict('os.environ', {'DASHBOARD_MAIL_ENABLED': 'false'}):
            self.assertEqual(process_outbox(self.auth), 0)
        def fail(*args): raise OSError('secret provider detail')
        for index in range(3):
            self.assertEqual(process_outbox(self.auth, fail), 0)
            with self.auth.connect() as db:
                row = db.execute('SELECT * FROM outbox').fetchone()
                self.assertEqual(row['attempts'], index + 1)
                self.assertEqual(row['last_error'], 'OSError')
                if index < 2:
                    self.assertEqual(row['status'], 'pending'); self.assertGreater(row['next_attempt'], time.time())
                else: self.assertEqual(row['status'], 'failed')
                db.execute('UPDATE outbox SET next_attempt=0')
        self.assertEqual(process_outbox(self.auth, lambda *args: None), 0)
        with self.auth.connect() as db:
            self.service.emit(db, 'test2', 'operational', 'Title', 'Body', '/acessos')
        self.assertEqual(process_outbox(self.auth, lambda *args: None), 1)
        self.assertEqual(process_outbox(self.auth, lambda *args: None), 0)

    def test_csrf_guests_and_data_unchanged(self):
        before = hashlib.sha256(self.path.read_bytes()).hexdigest()
        for endpoint in ['/api/profile', '/api/admin/users', '/api/notifications', '/api/profile/verify', '/api/auth/reset']:
            self.assertEqual(self.client.post(endpoint, json={}).status_code, 403)
        guest = self.app.test_client(); guest.get('/login')
        with guest.session_transaction() as session: headers = {'X-CSRF-Token': session['csrf']}
        guest.post('/auth/guest', json={}, headers=headers)
        for endpoint in ['/perfil', '/administracao', '/api/profile', '/api/admin/users', '/api/notifications']:
            self.assertEqual(guest.get(endpoint).status_code, 403)
        self.assertEqual(before, hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_crud_emits_transitions_without_dashboard_reload(self):
        self.promote()
        row = dict(self.raw['OrdensServico'][0])
        row['status'] = 'Pendente' if row['status'] == 'Em andamento' else 'Em andamento'; row['conclusao'] = ''
        code = row['codigo']
        response = self.client.put('/api/records/OrdensServico/' + code, json=row, headers=self.headers)
        self.assertEqual(response.status_code, 200, response.json)
        rows = self.service.notifications('principal')
        self.assertTrue(any(code in r['title'] and 'status:' in r['message'] for r in rows))
        count = len(rows)
        self.client.put('/api/records/OrdensServico/' + code, json=row, headers=self.headers)
        self.assertEqual(len(self.service.notifications('principal')), count)
        self.assertEqual(self.app.test_cli_runner().invoke(args=['processar-alertas']).exit_code, 0)
        self.assertEqual(len(self.service.notifications('principal')), count)

    def test_ambiguous_smtp_never_automatically_resends(self):
        self.promote()
        with self.auth.connect() as db:
            db.execute("UPDATE account SET email='mail@example.test',verified=1,email_alerts=1")
            self.service.emit(db, 'ambiguous', 'operational', 'Title', 'Body', '/acessos')
        def fail(*args): raise TimeoutError('sensitive provider detail')
        process_outbox(self.auth, fail)
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM outbox').fetchone()[0], 'uncertain')
            self.assertEqual(db.execute('SELECT error_type FROM mail_attempts').fetchone()[0], 'TimeoutError')
        self.assertEqual(process_outbox(self.auth, lambda *args: None), 0)
