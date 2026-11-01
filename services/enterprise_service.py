"""Persistência aditiva. Migração de bancos existentes somente por comando explícito."""
from datetime import datetime, timezone, date
from contextlib import closing
import json
import re
import secrets
import sqlite3
import time
from werkzeug.security import generate_password_hash, check_password_hash

ROLES = ('superadmin', 'admin', 'user')


def stamp():
    return datetime.now(timezone.utc).isoformat()


def text(value, maximum=250, required=False):
    if not isinstance(value, str) or len(value) > maximum or (required and not value.strip()):
        raise ValueError('Texto inválido ou acima do limite permitido.')
    return value.strip()


def identifier(value):
    value = text(value, 64, True).casefold()
    if not re.fullmatch(r'[a-z0-9_.-]{3,64}', value):
        raise ValueError('ID deve ter 3 a 64 caracteres: letras, números, ponto, hífen ou sublinhado.')
    return value


def password_hash(value):
    if not isinstance(value, str) or not 12 <= len(value) <= 256:
        raise ValueError('Use uma senha de 12 a 256 caracteres.')
    return generate_password_hash(value)


def schema(db):
    # Caller owns transaction: do not use executescript (implicit commit).
    statements = [
        "CREATE TABLE IF NOT EXISTS account(user_id TEXT PRIMARY KEY REFERENCES users(id) ON UPDATE CASCADE, role TEXT NOT NULL DEFAULT 'admin' CHECK(role IN ('superadmin','admin','user')), state TEXT NOT NULL DEFAULT 'active' CHECK(state IN ('active','blocked','inactive')), display_name TEXT NOT NULL DEFAULT '', email TEXT NOT NULL DEFAULT '', verified INTEGER NOT NULL DEFAULT 0, internal_alerts INTEGER NOT NULL DEFAULT 1, email_alerts INTEGER NOT NULL DEFAULT 0, appearance TEXT NOT NULL DEFAULT '{}', created TEXT, last_login TEXT)",
        "CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY, actor TEXT NOT NULL, action TEXT NOT NULL, target TEXT NOT NULL, occurred TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS tokens(digest TEXT PRIMARY KEY, user_id TEXT NOT NULL REFERENCES users(id) ON UPDATE CASCADE, purpose TEXT NOT NULL, value TEXT NOT NULL, expires REAL NOT NULL)",
        "CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY, event_key TEXT NOT NULL UNIQUE, kind TEXT NOT NULL, title TEXT NOT NULL, message TEXT NOT NULL, link TEXT NOT NULL, occurred TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS notifications(id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL REFERENCES events(id), user_id TEXT NOT NULL REFERENCES users(id) ON UPDATE CASCADE, read_at TEXT, deleted INTEGER NOT NULL DEFAULT 0, UNIQUE(event_id,user_id))",
        "CREATE TABLE IF NOT EXISTS snapshots(sheet TEXT NOT NULL, code TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(sheet,code))",
        "CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY, event_id INTEGER REFERENCES events(id), user_id TEXT NOT NULL REFERENCES users(id) ON UPDATE CASCADE, recipient TEXT NOT NULL, subject TEXT NOT NULL, body TEXT NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending', next_attempt REAL NOT NULL DEFAULT 0, last_error TEXT, UNIQUE(event_id,user_id))",
        "CREATE TABLE IF NOT EXISTS mail_attempts(id INTEGER PRIMARY KEY, outbox_id INTEGER NOT NULL REFERENCES outbox(id), occurred TEXT NOT NULL, result TEXT NOT NULL, error_type TEXT)",
        "CREATE TABLE IF NOT EXISTS announcements(id INTEGER PRIMARY KEY, actor TEXT NOT NULL, title TEXT NOT NULL, message TEXT NOT NULL, recipients TEXT NOT NULL, occurred TEXT NOT NULL)",
        "CREATE TABLE IF NOT EXISTS enterprise_version(version INTEGER PRIMARY KEY)",
        "INSERT OR IGNORE INTO enterprise_version VALUES (1)",
        "INSERT OR IGNORE INTO account(user_id,display_name) SELECT id,id FROM users",
    ]
    for statement in statements:
        db.execute(statement)


class EnterpriseService:
    def __init__(self, auth):
        self.auth = auth

    def ready(self):
        with self.auth.connect() as db:
            return bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='enterprise_version'").fetchone())

    def require_ready(self):
        if not self.ready():
            raise ValueError('Execute a migração empresarial com backup antes de usar este recurso.')

    def migrate(self):
        backup = self.auth.directory / ('auth.before-next.' + secrets.token_hex(8) + '.sqlite3')
        with self.auth.connect() as source:
            with closing(sqlite3.connect(backup)) as dest:
                source.backup(dest)
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            before = [tuple(r) for r in db.execute('SELECT id,password_hash FROM users ORDER BY id')]
            schema(db)
            after = [tuple(r) for r in db.execute('SELECT id,password_hash FROM users ORDER BY id')]
            if before != after:
                raise RuntimeError('Integridade de credenciais não preservada.')
            self.audit(db, 'local-cli', 'schema.migrate', 'v1')
        return backup

    @staticmethod
    def audit(db, actor, action, target):
        db.execute('INSERT INTO audit(actor,action,target,occurred) VALUES (?,?,?,?)', (actor, action, target, stamp()))

    @staticmethod
    def public(row):
        result = dict(row)
        result['appearance'] = json.loads(result['appearance'])
        return result

    def profile(self, user_id):
        with self.auth.connect() as db:
            row = db.execute('SELECT * FROM account WHERE user_id=?', (user_id,)).fetchone()
            if not row:
                raise ValueError('Conta não encontrada.')
            return self.public(row)

    def users(self):
        with self.auth.connect() as db:
            return [self.public(r) for r in db.execute('SELECT * FROM account ORDER BY user_id')]

    def promote_initial(self, user_id, password):
        self.require_ready()
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT u.password_hash,a.role,a.state FROM users u JOIN account a ON a.user_id=u.id WHERE u.id=?', (identifier(user_id),)).fetchone()
            if not row or not check_password_hash(row['password_hash'], password) or row['state'] != 'active' or row['role'] != 'admin':
                raise ValueError('Administrador ativo ou senha inválidos.')
            if db.execute("SELECT 1 FROM account WHERE role='superadmin'").fetchone():
                raise ValueError('Já existe superadministrador. Utilize a administração autenticada.')
            db.execute("UPDATE account SET role='superadmin' WHERE user_id=?", (user_id,))
            self.audit(db, user_id, 'account.bootstrap', user_id)

    def create_user(self, actor, data):
        uid = identifier(data.get('user_id'))
        hashed = password_hash(data.get('password'))
        role = data.get('role', 'user')
        if role not in ROLES:
            raise ValueError('Permissão inválida.')
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.superadmin(db, actor)
            try:
                db.execute('INSERT INTO users(id,password_hash) VALUES (?,?)', (uid, hashed))
            except sqlite3.IntegrityError:
                raise ValueError('Esse ID já está cadastrado.')
            db.execute('INSERT INTO account(user_id,role,display_name,created) VALUES (?,?,?,?)', (uid, role, text(data.get('display_name', uid), 120, True), stamp()))
            self.audit(db, actor, 'account.create', uid)
        return uid

    @staticmethod
    def superadmin(db, actor):
        row = db.execute("SELECT 1 FROM account WHERE user_id=? AND role='superadmin' AND state='active'", (actor,)).fetchone()
        if not row:
            raise ValueError('Superadministrador ativo necessário.')

    def manage(self, actor, uid, data):
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.superadmin(db, actor)
            row = db.execute('SELECT * FROM account WHERE user_id=?', (uid,)).fetchone()
            if not row:
                raise ValueError('Conta não encontrada.')
            role, state = data.get('role', row['role']), data.get('state', row['state'])
            if role not in ROLES or state not in ('active', 'blocked', 'inactive'):
                raise ValueError('Permissão ou estado inválidos.')
            if row['role'] == 'superadmin' and row['state'] == 'active' and (role != 'superadmin' or state != 'active'):
                count = db.execute("SELECT COUNT(*) FROM account WHERE role='superadmin' AND state='active'").fetchone()[0]
                if count <= 1:
                    raise ValueError('Mantenha pelo menos um superadministrador ativo.')
            db.execute('UPDATE account SET role=?,state=?,display_name=? WHERE user_id=?', (role, state, text(data.get('display_name', row['display_name']), 120, True), uid))
            db.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
            self.audit(db, actor, 'account.manage', uid)

    def update_profile(self, uid, data):
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT a.*,u.password_hash FROM account a JOIN users u ON u.id=a.user_id WHERE a.user_id=?', (uid,)).fetchone()
            new_id = identifier(data.get('user_id', uid))
            email = text(data.get('email', row['email']), 254).casefold()
            if email and not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', email):
                raise ValueError('E-mail inválido.')
            sensitive = new_id != uid or email != row['email'] or bool(data.get('password'))
            if sensitive and not check_password_hash(row['password_hash'], text(data.get('current_password', ''), 256)):
                raise ValueError('Confirme a senha atual para alterar dados sensíveis.')
            appearance = data.get('appearance', json.loads(row['appearance']))
            if not isinstance(appearance, dict) or set(appearance) - {'theme', 'font', 'density', 'numbers', 'reduceMotion'}:
                raise ValueError('Preferências inválidas.')
            allowed = {'theme': ('light', 'dark', 'auto'), 'font': ('small', 'default', 'large', 'xlarge'), 'density': ('compact', 'default'), 'numbers': ('standard', 'compact')}
            if any(k in appearance and appearance[k] not in values for k, values in allowed.items()) or ('reduceMotion' in appearance and type(appearance['reduceMotion']) is not bool):
                raise ValueError('Aparência inválida.')
            for field in ('internal_alerts', 'email_alerts'):
                if field in data and type(data[field]) is not bool:
                    raise ValueError('Preferência de notificação inválida.')
            if new_id != uid:
                if db.execute('SELECT 1 FROM users WHERE id=?', (new_id,)).fetchone():
                    raise ValueError('Esse ID já está cadastrado.')
                # Sessions from legacy schema have no ON UPDATE CASCADE.
                db.execute('DELETE FROM sessions WHERE user_id=?', (uid,))
                db.execute('UPDATE users SET id=? WHERE id=?', (new_id, uid))
            if data.get('password'):
                db.execute('UPDATE users SET password_hash=? WHERE id=?', (password_hash(data['password']), new_id))
                db.execute('DELETE FROM sessions WHERE user_id=?', (new_id,))
            if email != row['email']:
                db.execute('DELETE FROM tokens WHERE user_id=? AND purpose=?', (new_id, 'verify'))
                db.execute("UPDATE outbox SET status='cancelled' WHERE user_id=? AND status='pending'", (new_id,))
            db.execute('UPDATE account SET display_name=?,email=?,verified=?,internal_alerts=?,email_alerts=?,appearance=? WHERE user_id=?', (text(data.get('display_name', row['display_name']), 120, True), email, row['verified'] if email == row['email'] else 0, int(data.get('internal_alerts', bool(row['internal_alerts']))), int(data.get('email_alerts', bool(row['email_alerts']))), json.dumps(appearance), new_id))
            self.audit(db, uid, 'profile.update', new_id)
        return new_id, sensitive

    def token(self, actor, uid, purpose):
        raw = secrets.token_urlsafe(32)
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if purpose == 'reset':
                self.superadmin(db, actor)
            elif actor != uid:
                raise ValueError('Conta inválida.')
            row = db.execute('SELECT email,state FROM account WHERE user_id=?', (uid,)).fetchone()
            if not row or row['state'] != 'active' or (purpose == 'verify' and not row['email']):
                raise ValueError('Conta ativa e endereço de e-mail necessários.')
            db.execute('DELETE FROM tokens WHERE user_id=? AND purpose=?', (uid, purpose))
            db.execute('INSERT INTO tokens VALUES (?,?,?,?,?)', (self.auth.digest(raw), uid, purpose, row['email'], time.time() + 1800))
            if purpose == 'verify':
                db.execute('INSERT INTO outbox(user_id,recipient,subject,body) VALUES (?,?,?,?)', (uid, row['email'], 'Confirme seu e-mail no DashboardOS', 'Código de confirmação (válido por 30 minutos): ' + raw))
            self.audit(db, actor, 'token.' + purpose, uid)
        # Verification token is delivered only to address, never returned to requester.
        return raw if purpose == 'reset' else None

    def consume(self, raw, purpose, password=None, uid=None):
        raw = text(raw, 200, True)
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row = db.execute('SELECT * FROM tokens WHERE digest=? AND purpose=? AND expires>?', (self.auth.digest(raw), purpose, time.time())).fetchone()
            if not row or (uid is not None and uid != row['user_id']):
                raise ValueError('Código inválido ou expirado.')
            if purpose == 'verify':
                db.execute('UPDATE account SET verified=1 WHERE user_id=? AND email=?', (row['user_id'], row['value']))
            else:
                db.execute('UPDATE users SET password_hash=? WHERE id=?', (password_hash(password), row['user_id']))
                db.execute('DELETE FROM sessions WHERE user_id=?', (row['user_id'],))
            db.execute('DELETE FROM tokens WHERE user_id=? AND purpose=?', (row['user_id'], purpose))
            self.audit(db, row['user_id'], 'token.consume.' + purpose, row['user_id'])

    @staticmethod
    def emit(db, key, kind, title, message, link, recipients=None, email=True):
        cursor = db.execute('INSERT OR IGNORE INTO events(event_key,kind,title,message,link,occurred) VALUES (?,?,?,?,?,?)', (key, kind, title, message, link, stamp()))
        if not cursor.rowcount:
            return False
        event_id = cursor.lastrowid
        users = db.execute("SELECT * FROM account WHERE state='active'").fetchall()
        for user in users:
            uid = user['user_id']
            if recipients is not None and uid not in recipients:
                continue
            if user['internal_alerts'] or kind == 'announcement':
                db.execute('INSERT INTO notifications(event_id,user_id) VALUES (?,?)', (event_id, uid))
            if email and user['email_alerts'] and user['verified'] and user['email']:
                db.execute('INSERT INTO outbox(event_id,user_id,recipient,subject,body) VALUES (?,?,?,?,?)', (event_id, uid, user['email'], title, message))
        return True

    def scan(self, raw, today=None):
        from .dashboard_service import categoria, enrich
        today = today or date.today()
        data = enrich(raw, today)
        count = 0
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            for sheet, field, page in [('OrdensServico', 'previsao', 'ordens-servico'), ('Acessos', 'vencimento', 'acessos')]:
                existing = {r['code']: r for r in db.execute('SELECT * FROM snapshots WHERE sheet=?', (sheet,))}
                current_codes = set()
                for row in data[sheet]:
                    code = row['codigo']; current_codes.add(code)
                    active = row['status'] not in ('Concluída', 'Revogado')
                    current = {'status': row['status'], 'due': row[field], 'band': categoria((date.fromisoformat(row[field]) - today).days) if active else 'Encerrado'}
                    previous = existing.get(code)
                    old = json.loads(previous['payload']) if previous else None
                    # First observation establishes baseline; it is not a change event.
                    if old is not None:
                        for key in ('status', 'due', 'band'):
                            if old[key] == current[key]:
                                continue
                            version = old.get('version', 0) + 1
                            event_key = f'{sheet}:{code}:{version}:{key}'
                            message = f"{row.get('descricao', row.get('sistema', ''))} · Responsável: {row.get('nome_funcionario', '')} · Equipe: {row.get('equipe', '')} · {key}: {old[key]} → {current[key]} · Vencimento: {current['due']} · Situação: {current['status']}"
                            count += self.emit(db, event_key, 'operational', code + ' · ' + current['band'], message, '/' + page + '?q=' + code)
                    current['version'] = (old.get('version', 0) + 1) if old and any(old[k] != current[k] for k in ('status', 'due', 'band')) else (old.get('version', 0) if old else 0)
                    db.execute('INSERT INTO snapshots VALUES (?,?,?) ON CONFLICT(sheet,code) DO UPDATE SET payload=excluded.payload', (sheet, code, json.dumps(current)))
                # Preserve tombstones/version so deleting and recreating a code cannot reuse keys.
                for code, old_row in existing.items():
                    if code not in current_codes:
                        old = json.loads(old_row['payload']); old['status'] = 'Removido'; old['band'] = 'Encerrado'
                        db.execute('UPDATE snapshots SET payload=? WHERE sheet=? AND code=?', (json.dumps(old), sheet, code))
        return count

    def notifications(self, uid):
        with self.auth.connect() as db:
            return [dict(r) for r in db.execute('SELECT n.id,n.read_at,e.title,e.message,e.link,e.occurred FROM notifications n JOIN events e ON e.id=n.event_id WHERE n.user_id=? AND n.deleted=0 ORDER BY n.id DESC LIMIT 200', (uid,))]

    def notification_action(self, uid, action, notification_id=None):
        if action not in ('read', 'delete'):
            raise ValueError('Ação inválida.')
        with self.auth.connect() as db:
            clause = 'user_id=?' + (' AND id=?' if notification_id is not None else '')
            params = (uid, notification_id) if notification_id is not None else (uid,)
            if action == 'read':
                db.execute('UPDATE notifications SET read_at=? WHERE ' + clause, (stamp(), *params))
            else:
                db.execute('UPDATE notifications SET deleted=1 WHERE ' + clause, params)

    def announce(self, actor, data):
        title = text(data.get('title'), 160, True)
        message = text(data.get('message'), 5000, True)
        recipients = data.get('recipients')
        if recipients is not None and (not isinstance(recipients, list) or not recipients or any(not isinstance(v, str) for v in recipients)):
            raise ValueError('Selecione destinatários válidos.')
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            self.superadmin(db, actor)
            active = {r[0] for r in db.execute("SELECT user_id FROM account WHERE state='active'")}
            selected = active if recipients is None else set(recipients)
            if not selected or not selected <= active:
                raise ValueError('Destinatário ausente ou inativo.')
            cursor = db.execute('INSERT INTO announcements(actor,title,message,recipients,occurred) VALUES (?,?,?,?,?)', (actor, title, message, json.dumps(sorted(selected)), stamp()))
            self.emit(db, 'announcement:' + str(cursor.lastrowid), 'announcement', title, message, '/perfil', selected, email=False)
            self.audit(db, actor, 'announcement.publish', str(cursor.lastrowid))

    def history(self, table):
        if table not in ('audit', 'announcements'):
            raise ValueError('Histórico inválido.')
        with self.auth.connect() as db:
            return [dict(r) for r in db.execute('SELECT * FROM ' + table + ' ORDER BY id DESC LIMIT 200')]
