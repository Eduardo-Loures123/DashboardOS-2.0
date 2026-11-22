"""Local profile features. No SMTP, outbox processing or automatic jobs."""
from contextlib import closing
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
import json
import logging
import re
import secrets
import sqlite3
import time
import warnings

from werkzeug.security import check_password_hash
from .enterprise_service import identifier, password_hash, text, stamp


def profile_schema(db):
    """Additive; legacy identity, password hashes and historical rows stay intact."""
    statements = [
        'CREATE TABLE IF NOT EXISTS profile_logins(user_id TEXT PRIMARY KEY REFERENCES users(id) ON UPDATE CASCADE, login TEXT NOT NULL COLLATE NOCASE UNIQUE)',
        'CREATE TABLE IF NOT EXISTS profile_avatars(user_id TEXT PRIMARY KEY REFERENCES users(id) ON UPDATE CASCADE, filename TEXT NOT NULL, revision TEXT NOT NULL)',
        'CREATE TABLE IF NOT EXISTS profile_email_changes(user_id TEXT PRIMARY KEY REFERENCES users(id) ON UPDATE CASCADE, address TEXT NOT NULL, digest TEXT NOT NULL, expires REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0, created REAL NOT NULL)',
        'CREATE TABLE IF NOT EXISTS profile_activities(id INTEGER PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id) ON UPDATE CASCADE,operation TEXT NOT NULL,module TEXT NOT NULL,record_code TEXT NOT NULL,summary TEXT NOT NULL,occurred REAL NOT NULL,operation_id TEXT NOT NULL UNIQUE)',
        'CREATE INDEX IF NOT EXISTS profile_activity_owner_time ON profile_activities(user_id,occurred DESC,id DESC)',
        "CREATE UNIQUE INDEX IF NOT EXISTS profile_verified_email ON account(lower(trim(email))) WHERE verified=1 AND email!=''",
    ]
    for statement in statements: db.execute(statement)
    for uid, in db.execute('SELECT id FROM users').fetchall():
        if not db.execute('SELECT 1 FROM profile_logins WHERE user_id=?', (uid,)).fetchone():
            db.execute('INSERT INTO profile_logins VALUES (?,?)', (uid, identifier(uid)))


class ProfileService:
    def __init__(self, auth, enterprise):
        self.auth, self.enterprise = auth, enterprise
        self.media = auth.directory / 'avatars'

    def ready(self):
        with self.auth.connect() as db:
            return bool(db.execute("SELECT 1 FROM sqlite_master WHERE name='profile_logins'").fetchone())

    def require_ready(self):
        if not self.ready(): raise ValueError('Atualização do perfil pendente. Execute migrar-perfil após validar o backup.')

    def migrate(self):
        backup = self.auth.directory / ('auth.before-profile.' + secrets.token_hex(8) + '.sqlite3')
        with self.auth.connect() as source, closing(sqlite3.connect(backup)) as dest:
            source.backup(dest)
            if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok': raise RuntimeError('Backup inválido.')
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            profile_schema(db)
            if db.execute('PRAGMA foreign_key_check').fetchall(): raise RuntimeError('Relacionamentos inválidos.')
        return backup

    def profile(self, uid):
        data = self.enterprise.profile(uid)
        data['account_id'] = data['user_id']
        if self.ready():
            with self.auth.connect() as db:
                login = db.execute('SELECT login FROM profile_logins WHERE user_id=?', (uid,)).fetchone()
                avatar = db.execute('SELECT revision FROM profile_avatars WHERE user_id=?', (uid,)).fetchone()
                pending = db.execute('SELECT address,expires,attempts FROM profile_email_changes WHERE user_id=? AND expires>?', (uid, time.time())).fetchone()
            data['user_id'] = login['login'] if login else uid
            data['avatar_url'] = '/api/profile/avatar?v=' + avatar['revision'] if avatar else None
            data['pending_email'] = dict(pending) if pending else None
        data.update(profile_ready=self.ready(), internal_alerts=True, delivery_available=False)
        return data

    def login_available(self, uid, value):
        self.require_ready(); login = identifier(value)
        with self.auth.connect() as db:
            used = db.execute('SELECT user_id FROM profile_logins WHERE login=? COLLATE NOCASE', (login,)).fetchone()
            reserved = db.execute('SELECT id FROM users WHERE id=? AND id!=?', (login, uid)).fetchone()
        return not reserved and (used is None or used['user_id'] == uid)

    def update(self, uid, data):
        self.require_ready()
        if not isinstance(data, dict): raise ValueError('Dados inválidos.')
        current = self.profile(uid)
        login = identifier(data.get('user_id', current['user_id']))
        name = text(data.get('display_name', current['display_name']), 120, True)
        if 'email' in data and data['email'] != current['email']:
            raise ValueError('Altere o endereço na aba E-mail e notificações.')
        for key in ('internal_alerts', 'email_alerts'):
            if key in data and type(data[key]) is not bool: raise ValueError('Preferência inválida.')
        if data.get('email_alerts') and not current['verified']:
            raise ValueError('Confirme o endereço antes de ativar alertas por e-mail.')
        appearance = data.get('appearance', current['appearance'])
        allowed = {'theme': ('light','dark','auto'), 'font': ('small','default','large','xlarge'),
                   'density': ('compact','default'), 'numbers': ('standard','compact')}
        if (not isinstance(appearance, dict) or set(appearance)-set(allowed)-{'reduceMotion'}
                or any(k in appearance and appearance[k] not in v for k,v in allowed.items())
                or 'reduceMotion' in appearance and type(appearance['reduceMotion']) is not bool):
            raise ValueError('Aparência inválida.')
        sensitive = login != current['user_id'] or bool(data.get('password'))
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            account = db.execute('SELECT a.*,u.password_hash FROM account a JOIN users u ON u.id=a.user_id WHERE a.user_id=?', (uid,)).fetchone()
            if not account or account['state']!='active': raise ValueError('Conta ativa necessária.')
            if data.get('email_alerts') and not account['verified']: raise ValueError('Confirme o endereço antes de ativar alertas por e-mail.')
            actual_login = db.execute('SELECT login FROM profile_logins WHERE user_id=?', (uid,)).fetchone()
            if actual_login and actual_login[0] != current['user_id']: raise ValueError('A conta foi atualizada em outra janela. Atualize a página.')
            if sensitive and not check_password_hash(account['password_hash'], text(data.get('current_password',''),256)):
                raise ValueError('Confirme a senha atual.')
            if not self.login_available(uid, login): raise ValueError('Identificador indisponível.')
            try:
                db.execute('INSERT INTO profile_logins VALUES (?,?) ON CONFLICT(user_id) DO UPDATE SET login=excluded.login', (uid,login))
            except sqlite3.IntegrityError: raise ValueError('Identificador indisponível.') from None
            if data.get('password'):
                if data.get('password_confirmation', data['password']) != data['password']: raise ValueError('As senhas não coincidem.')
                db.execute('UPDATE users SET password_hash=? WHERE id=?', (password_hash(data['password']),uid))
            db.execute('UPDATE account SET display_name=?,appearance=?,internal_alerts=1,email_alerts=? WHERE user_id=?',
                       (name,json.dumps(appearance),int(data.get('email_alerts',bool(account['email_alerts']))),uid))
            if sensitive: db.execute('DELETE FROM sessions WHERE user_id=?',(uid,))
            self.enterprise.audit(db,uid,'profile.update',uid)
        return sensitive

    def change_email(self, uid, address, password, code_factory=None):
        """Return a code to trusted delivery adapters only; routes never expose it."""
        self.require_ready(); address=text(address,254,True).casefold()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',address): raise ValueError('E-mail inválido.')
        now=time.time(); raw=code_factory() if code_factory else secrets.token_urlsafe(24)
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            user=db.execute('SELECT a.*,u.password_hash FROM account a JOIN users u ON u.id=a.user_id WHERE a.user_id=?',(uid,)).fetchone()
            if not user or user['state']!='active' or not check_password_hash(user['password_hash'],text(password,256)):
                raise ValueError('Confirme sua senha atual.')
            if user['email']==address and user['verified']: raise ValueError('Este endereço já está verificado.')
            if db.execute('SELECT 1 FROM account WHERE lower(trim(email))=? AND verified=1 AND user_id!=?',(address,uid)).fetchone(): raise ValueError('Endereço indisponível.')
            pending=db.execute('SELECT created FROM profile_email_changes WHERE user_id=?',(uid,)).fetchone()
            if pending and now-pending['created']<60: raise ValueError('Aguarde um minuto para solicitar novamente.')
            recent=db.execute("SELECT COUNT(*) FROM audit WHERE actor=? AND action='profile.email.request' AND occurred>?",(uid,datetime.fromtimestamp(now-3600,timezone.utc).isoformat())).fetchone()[0]
            if recent>=5: raise ValueError('Limite de cinco solicitações por hora.')
            db.execute('INSERT INTO profile_email_changes VALUES (?,?,?,?,0,?) ON CONFLICT(user_id) DO UPDATE SET address=excluded.address,digest=excluded.digest,expires=excluded.expires,attempts=0,created=excluded.created',
                       (uid,address,self.auth.digest(raw),now+1800,now))
            self.enterprise.audit(db,uid,'profile.email.request',uid)
        return raw

    def cancel_email(self, uid):
        self.require_ready()
        with self.auth.connect() as db:
            db.execute('DELETE FROM profile_email_changes WHERE user_id=?',(uid,))
            self.enterprise.audit(db,uid,'profile.email.cancel',uid)

    def confirm_email(self, uid, code):
        self.require_ready(); valid=False; unavailable=False
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            pending=db.execute('SELECT p.* FROM profile_email_changes p JOIN account a ON a.user_id=p.user_id WHERE p.user_id=? AND a.state=?',(uid,'active')).fetchone()
            if pending and pending['expires']>time.time() and pending['attempts']<5:
                if isinstance(code,str) and len(code)<=200 and secrets.compare_digest(pending['digest'],self.auth.digest(code.strip())):
                    try:
                        db.execute('UPDATE account SET email=?,verified=1 WHERE user_id=?',(pending['address'],uid))
                        db.execute('DELETE FROM profile_email_changes WHERE user_id=?',(uid,))
                        self.enterprise.audit(db,uid,'profile.email.confirm',uid)
                        valid=True
                    except sqlite3.IntegrityError: unavailable=True
                else: db.execute('UPDATE profile_email_changes SET attempts=attempts+1 WHERE user_id=?',(uid,))
        if unavailable: raise ValueError('Endereço indisponível.')
        if not valid: raise ValueError('Código inválido, expirado ou bloqueado.')

    def avatar_path(self, uid):
        self.require_ready()
        with self.auth.connect() as db: row=db.execute('SELECT filename FROM profile_avatars WHERE user_id=?',(uid,)).fetchone()
        if not row: return None
        if not re.fullmatch(r'[a-f0-9]{48}\.webp',row['filename']): raise ValueError('Imagem indisponível.')
        return self.media/row['filename']

    def set_avatar(self, uid, upload):
        from PIL import Image, ImageOps, UnidentifiedImageError
        self.require_ready()
        if not upload or Path(upload.filename or '').suffix.lower() not in ('.jpg','.jpeg','.png','.webp'): raise ValueError('Use JPG, PNG ou WebP.')
        payload=upload.stream.read(5*1024*1024+1)
        if len(payload)>5*1024*1024: raise ValueError('A foto deve ter no máximo 5 MB.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                with Image.open(BytesIO(payload)) as check:
                    if check.format not in ('JPEG','PNG','WEBP') or check.width*check.height>20_000_000 or getattr(check,'is_animated',False): raise ValueError('Imagem inválida, animada ou muito grande.')
                    check.verify()
                with Image.open(BytesIO(payload)) as image:
                    image=ImageOps.exif_transpose(image).convert('RGB');image.thumbnail((1024,1024))
                    output=BytesIO();image.save(output,format='WEBP',quality=88)
        except (UnidentifiedImageError,OSError,Image.DecompressionBombError,Image.DecompressionBombWarning):
            raise ValueError('O arquivo não contém uma imagem válida.') from None
        self.media.mkdir(parents=True,exist_ok=True);name=secrets.token_hex(24)+'.webp';target=self.media/name
        old=None
        try:
            with self.auth.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                old=self.avatar_path(uid)
                with target.open('xb') as handle: handle.write(output.getvalue())
                db.execute('INSERT INTO profile_avatars VALUES (?,?,?) ON CONFLICT(user_id) DO UPDATE SET filename=excluded.filename,revision=excluded.revision',(uid,name,secrets.token_hex(8)))
                self.enterprise.audit(db,uid,'profile.avatar.update',uid)
        except Exception:
            target.unlink(missing_ok=True);raise
        if old: self._retire_avatar(old)

    @staticmethod
    def _retire_avatar(path):
        try:path.unlink(missing_ok=True)
        except OSError as error:
            logging.getLogger(__name__).warning('Foto anterior preservada para revisão local: %s',type(error).__name__)

    def remove_avatar(self, uid):
        self.require_ready()
        with self.auth.connect() as db:
            db.execute('BEGIN IMMEDIATE');old=self.avatar_path(uid)
            db.execute('DELETE FROM profile_avatars WHERE user_id=?',(uid,))
            self.enterprise.audit(db,uid,'profile.avatar.remove',uid)
        if old: self._retire_avatar(old)

    def record_activity(self,uid,operation,module,code,operation_id=None):
        if not self.ready(): return
        if operation not in ('create','update','delete'): raise ValueError('Operação inválida.')
        label={'OrdensServico':'Ordens de serviço','Acessos':'Acessos','Funcionarios':'Funcionários','Equipes':'Equipes','Renovacoes':'Renovações'}.get(module,module)
        summary={'create':'Cadastro','update':'Edição','delete':'Exclusão'}[operation]+' · '+label
        with self.auth.connect() as db:
            db.execute('INSERT OR IGNORE INTO profile_activities(user_id,operation,module,record_code,summary,occurred,operation_id) VALUES (?,?,?,?,?,?,?)',
                       (uid,operation,module,text(code,100,True),summary,time.time(),operation_id or secrets.token_hex(24)))

    def activities(self,uid,operation='',query='',page=1):
        self.require_ready()
        if operation not in ('','create','update','delete'): raise ValueError('Filtro inválido.')
        try: page=int(page)
        except (ValueError,TypeError): raise ValueError('Página inválida.') from None
        if not 1<=page<=10000: raise ValueError('Página inválida.')
        query=text(query,120);clause='user_id=? AND occurred>?';params=[uid,time.time()-30*86400]
        if operation: clause+=' AND operation=?';params.append(operation)
        if query:
            escaped=query.replace('\\','\\\\').replace('%','\\%').replace('_','\\_')
            clause+=" AND (record_code LIKE ? ESCAPE '\\' OR summary LIKE ? ESCAPE '\\')";params.extend(['%'+escaped+'%']*2)
        with self.auth.connect() as db:
            total=db.execute('SELECT COUNT(*) FROM profile_activities WHERE '+clause,params).fetchone()[0]
            rows=[dict(r) for r in db.execute('SELECT id,operation,module,record_code,summary,occurred FROM profile_activities WHERE '+clause+' ORDER BY occurred DESC,id DESC LIMIT 20 OFFSET ?',(*params,(page-1)*20))]
        return {'activities':rows,'total':total,'page':page,'page_size':20}

    def cleanup_activities(self,now=None):
        self.require_ready()
        with self.auth.connect() as db:
            return db.execute('DELETE FROM profile_activities WHERE occurred<=?',((time.time() if now is None else now)-30*86400,)).rowcount
