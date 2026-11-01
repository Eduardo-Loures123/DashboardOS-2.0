"""Credenciais e sessões revogáveis separadas dos dados empresariais."""
from pathlib import Path
from contextlib import contextmanager
import hashlib, re, secrets, sqlite3, time
from werkzeug.security import generate_password_hash, check_password_hash

class AuthService:
    def __init__(self,directory):
        self.directory=Path(directory);self.directory.mkdir(parents=True,exist_ok=True)
        self.path=self.directory/'auth.sqlite3'
        fresh=not self.path.exists()
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, password_hash TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(token_hash TEXT PRIMARY KEY, user_id TEXT REFERENCES users(id), expires REAL NOT NULL);
                CREATE TABLE IF NOT EXISTS attempts(client TEXT NOT NULL, occurred REAL NOT NULL);
            ''')
            if fresh:
                from .enterprise_service import schema
                schema(db)
        self.dummy_hash=generate_password_hash(secrets.token_hex(24))
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.row_factory=sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:yield db
        finally:db.close()
    def secret(self):
        path=self.directory/'session.key'
        try:
            with path.open('x',encoding='ascii') as handle:handle.write(secrets.token_hex(32))
        except FileExistsError:pass
        return path.read_text(encoding='ascii').strip()
    def create_admin(self,user_id,password):
        user_id=user_id.strip().casefold()
        if not re.fullmatch(r'[a-z0-9_.-]{3,64}',user_id):raise ValueError('Use ID de 3 a 64 caracteres: letras, números, ponto, hífen ou sublinhado.')
        if len(password)<12 or len(password)>256:raise ValueError('Use uma senha de 12 a 256 caracteres.')
        with self.connect() as db:
            try:db.execute('INSERT INTO users VALUES (?,?)',(user_id,generate_password_hash(password)))
            except sqlite3.IntegrityError:raise ValueError('Esse ID já está cadastrado.')
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='account'").fetchone():
                from .enterprise_service import stamp
                db.execute('INSERT INTO account(user_id,display_name,created) VALUES (?,?,?)',(user_id,user_id,stamp()))
        return user_id
    def has_admin(self):
        with self.connect() as db:return bool(db.execute('SELECT 1 FROM users LIMIT 1').fetchone())
    def authenticate(self,user_id,password,client):
        user_id=user_id.strip().casefold();client=hashlib.sha256(client.encode()).hexdigest();now=time.time()
        with self.connect() as db:
            db.execute('DELETE FROM attempts WHERE occurred < ?',(now-600,))
            if db.execute('SELECT COUNT(*) FROM attempts WHERE client=?',(client,)).fetchone()[0]>=10:
                return None,429
            row=db.execute('SELECT * FROM users WHERE id=?',(user_id,)).fetchone()
            valid=check_password_hash(row['password_hash'] if row else self.dummy_hash,password)
            if row and db.execute("SELECT 1 FROM sqlite_master WHERE name='account'").fetchone():
                account=db.execute('SELECT state FROM account WHERE user_id=?',(user_id,)).fetchone()
                valid=valid and bool(account and account['state']=='active')
            if not row or not valid:
                db.execute('INSERT INTO attempts VALUES (?,?)',(client,now));return None,401
            db.execute('DELETE FROM attempts WHERE client=?',(client,))
            if db.execute("SELECT 1 FROM sqlite_master WHERE name='account'").fetchone():
                from .enterprise_service import stamp
                db.execute('UPDATE account SET last_login=? WHERE user_id=?',(stamp(),user_id))
            return row['id'],200
    def start(self,user_id=None):
        token=secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('DELETE FROM sessions WHERE expires <= ?',(time.time(),))
            db.execute('INSERT INTO sessions VALUES (?,?,?)',(self.digest(token),user_id,time.time()+8*3600))
        return token
    @staticmethod
    def digest(token):return hashlib.sha256(token.encode()).hexdigest()
    def current(self,token):
        if not isinstance(token,str) or not token:return None
        with self.connect() as db:
            row=db.execute('SELECT user_id FROM sessions WHERE token_hash=? AND expires>?',(self.digest(token),time.time())).fetchone()
            if row is None:return None
            role='admin' if row['user_id'] else 'guest'
            if row['user_id'] and db.execute("SELECT 1 FROM sqlite_master WHERE name='account'").fetchone():
                account=db.execute('SELECT role,state FROM account WHERE user_id=?',(row['user_id'],)).fetchone()
                if not account or account['state']!='active':return None
                role=account['role']
        return {'id':row['user_id'] or 'Visitante','role':role,'preferences_key':hashlib.sha256((row['user_id'] or 'guest').encode()).hexdigest()[:24]}
    def revoke(self,token):
        if isinstance(token,str) and token:
            with self.connect() as db:db.execute('DELETE FROM sessions WHERE token_hash=?',(self.digest(token),))
