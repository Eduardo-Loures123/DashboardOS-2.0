"""3C.2A additive DDL. Explicit caller-owned connection; never opens any database.

Not registered with Flask/AuthService. Applying this to a real database requires
a separately approved migration/backup procedure. No operational data is seeded.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import re
import sqlite3
import uuid

VERSION = 1
MODULES_SQL = "('OrdensServico','Acessos','Renovacoes')"
REVOCATION_SQL = """CHECK((active=1 AND revoked_by IS NULL AND revoked_at IS NULL AND revocation_reason IS NULL)
 OR (active=0 AND revoked_by IS NOT NULL AND revoked_at IS NOT NULL AND revocation_reason IS NOT NULL AND length(trim(revocation_reason))>0))"""

# No executescript: it can commit a caller's transaction before executing DDL.
DDL = (
    """CREATE TABLE email_recipient_schema (
 version INTEGER PRIMARY KEY CHECK(version=1), digest TEXT NOT NULL, applied_at TEXT NOT NULL)""",
    """CREATE TABLE email_identity_state (
 slot INTEGER PRIMARY KEY CHECK(slot=1), epoch TEXT NOT NULL CHECK(length(epoch)>0),
 revision INTEGER NOT NULL CHECK(revision>=0), source_revision INTEGER NOT NULL CHECK(source_revision>=0),
 source_token TEXT NOT NULL, ready INTEGER NOT NULL CHECK(ready IN (0,1)))""",
    """CREATE TABLE email_team_identities (
 code TEXT NOT NULL CHECK(length(trim(code))>0), generation INTEGER NOT NULL CHECK(typeof(generation)='integer' AND generation>0),
 incarnation TEXT NOT NULL CHECK(length(trim(incarnation))>0), present INTEGER NOT NULL CHECK(present IN (0,1)),
 PRIMARY KEY(code,generation))""",
    "CREATE UNIQUE INDEX email_team_current ON email_team_identities(code) WHERE present=1",
    f"""CREATE TABLE email_record_identities (
 module TEXT NOT NULL CHECK(module IN {MODULES_SQL}), code TEXT NOT NULL CHECK(length(trim(code))>0),
 generation INTEGER NOT NULL CHECK(typeof(generation)='integer' AND generation>0), incarnation TEXT NOT NULL CHECK(length(trim(incarnation))>0),
 team_code TEXT NOT NULL, team_generation INTEGER NOT NULL CHECK(team_generation>0),
 operational_generation INTEGER NOT NULL CHECK(typeof(operational_generation)='integer' AND operational_generation>0),
 present INTEGER NOT NULL CHECK(present IN (0,1)), PRIMARY KEY(module,code,generation),
 UNIQUE(module,code,generation,team_code,team_generation,operational_generation),
 FOREIGN KEY(team_code,team_generation) REFERENCES email_team_identities(code,generation))""",
    "CREATE UNIQUE INDEX email_record_current ON email_record_identities(module,code) WHERE present=1",
    f"""CREATE TABLE email_primary_designations (
 designation_id TEXT PRIMARY KEY NOT NULL CHECK(length(trim(designation_id))>0),
 account_id TEXT NOT NULL REFERENCES account(user_id), approved_by TEXT NOT NULL REFERENCES account(user_id),
 approved_at TEXT NOT NULL, active INTEGER NOT NULL CHECK(active IN (0,1)),
 revoked_by TEXT REFERENCES account(user_id), revoked_at TEXT, revocation_reason TEXT,
 {REVOCATION_SQL})""",
    "CREATE UNIQUE INDEX email_primary_single_active ON email_primary_designations(active) WHERE active=1",
    f"""CREATE TABLE email_recipient_authorizations (
 grant_id TEXT PRIMARY KEY NOT NULL CHECK(length(trim(grant_id))>0),
 account_id TEXT NOT NULL REFERENCES account(user_id), module TEXT NOT NULL CHECK(module IN {MODULES_SQL}),
 scope TEXT NOT NULL CHECK(scope IN ('module','team','record')), epoch TEXT NOT NULL,
 team_code TEXT, team_generation INTEGER, record_code TEXT, record_generation INTEGER, operational_generation INTEGER,
 approved_by TEXT NOT NULL REFERENCES account(user_id), approved_at TEXT NOT NULL,
 active INTEGER NOT NULL CHECK(active IN (0,1)), revoked_by TEXT REFERENCES account(user_id),
 revoked_at TEXT, revocation_reason TEXT, {REVOCATION_SQL},
 CHECK((scope='module' AND team_code IS NULL AND team_generation IS NULL AND record_code IS NULL AND record_generation IS NULL AND operational_generation IS NULL)
 OR (scope='team' AND team_code IS NOT NULL AND team_generation>0 AND team_generation IS NOT NULL AND record_code IS NULL AND record_generation IS NULL AND operational_generation IS NULL)
 OR (scope='record' AND team_code IS NOT NULL AND team_generation IS NOT NULL AND team_generation>0 AND record_code IS NOT NULL AND record_generation IS NOT NULL AND record_generation>0 AND operational_generation IS NOT NULL AND operational_generation>0)),
 FOREIGN KEY(team_code,team_generation) REFERENCES email_team_identities(code,generation),
 FOREIGN KEY(module,record_code,record_generation,team_code,team_generation,operational_generation)
 REFERENCES email_record_identities(module,code,generation,team_code,team_generation,operational_generation))""",
    "CREATE UNIQUE INDEX email_grant_module_active ON email_recipient_authorizations(account_id,module) WHERE active=1 AND scope='module'",
    "CREATE UNIQUE INDEX email_grant_team_active ON email_recipient_authorizations(account_id,module,team_code,team_generation) WHERE active=1 AND scope='team'",
    "CREATE UNIQUE INDEX email_grant_record_active ON email_recipient_authorizations(account_id,module,record_code,record_generation,team_code,team_generation) WHERE active=1 AND scope='record'",
    "CREATE INDEX email_grant_owner ON email_recipient_authorizations(account_id,module,active)",
    """CREATE TABLE email_recipient_audit (
 id INTEGER PRIMARY KEY AUTOINCREMENT, actor_id TEXT REFERENCES account(user_id), affected_account TEXT,
 operation TEXT NOT NULL, object_id TEXT NOT NULL, occurred_at TEXT NOT NULL,
 result TEXT NOT NULL CHECK(result IN ('success','rejected')), details TEXT NOT NULL,
 CHECK(result='rejected' OR actor_id IS NOT NULL))""",
    """CREATE TRIGGER email_audit_no_update BEFORE UPDATE ON email_recipient_audit
 BEGIN SELECT RAISE(ABORT,'email audit is append-only'); END""",
    """CREATE TRIGGER email_audit_no_delete BEFORE DELETE ON email_recipient_audit
 BEGIN SELECT RAISE(ABORT,'email audit is append-only'); END""",
    """CREATE TRIGGER email_audit_no_replace BEFORE INSERT ON email_recipient_audit
 WHEN EXISTS(SELECT 1 FROM email_recipient_audit WHERE id=NEW.id)
 BEGIN SELECT RAISE(ABORT,'email audit is append-only'); END""",
)

# History is append-only except for a single active -> revoked / present -> tombstone transition.
for _table, _flag in (
    ('email_primary_designations', 'active'),
    ('email_recipient_authorizations', 'active'),
    ('email_team_identities', 'present'),
    ('email_record_identities', 'present'),
):
    # Explicit immutable columns, with NULL-safe IS comparisons.
    _columns = {
        'email_primary_designations': ('designation_id', 'account_id', 'approved_by', 'approved_at'),
        'email_recipient_authorizations': ('grant_id', 'account_id', 'module', 'scope', 'epoch', 'team_code',
            'team_generation', 'record_code', 'record_generation', 'operational_generation', 'approved_by', 'approved_at'),
        'email_team_identities': ('code', 'generation', 'incarnation'),
        'email_record_identities': ('module', 'code', 'generation', 'incarnation', 'team_code', 'team_generation', 'operational_generation'),
    }[_table]
    _changed = ' OR '.join(f'NEW.{col} IS NOT OLD.{col}' for col in _columns)
    _match = ' AND '.join(f'{col} IS NEW.{col}' for col in _columns[:1 if _table not in ('email_team_identities', 'email_record_identities') else (2 if _table == 'email_team_identities' else 3)])
    DDL += (
        f"CREATE TRIGGER {_table}_immutable BEFORE UPDATE ON {_table} WHEN {_changed} OR OLD.{_flag}!=1 OR NEW.{_flag}!=0 BEGIN SELECT RAISE(ABORT,'immutable history'); END",
        f"CREATE TRIGGER {_table}_no_delete BEFORE DELETE ON {_table} BEGIN SELECT RAISE(ABORT,'immutable history'); END",
        f"CREATE TRIGGER {_table}_no_replace BEFORE INSERT ON {_table} WHEN EXISTS(SELECT 1 FROM {_table} WHERE {_match}) BEGIN SELECT RAISE(ABORT,'immutable history'); END",
    )


def normalized(sql):
    return re.sub(r'\s+', ' ', sql).strip().rstrip(';')


DIGEST = hashlib.sha256('\n'.join(normalized(sql) for sql in DDL).encode()).hexdigest()


class PersistenceError(ValueError):
    """Machine-readable failure without SQL parameters, profile data or secrets."""


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def prerequisites(db):
    for table, required in {
        'users': {'id': 'TEXT', 'password_hash': 'TEXT'},
        'account': {'user_id': 'TEXT', 'role': 'TEXT', 'state': 'TEXT', 'email': 'TEXT',
                    'verified': 'INTEGER', 'email_alerts': 'INTEGER'},
    }.items():
        columns = {r[1]: r for r in db.execute('PRAGMA table_info(' + table + ')')}
        if any(name not in columns or columns[name][2].upper() != kind for name, kind in required.items()):
            raise PersistenceError('base_schema_incompatible')
        key = 'id' if table == 'users' else 'user_id'
        if columns[key][5] != 1:
            raise PersistenceError('base_identity_incompatible')
    if not any(r[2] == 'users' and r[3] == 'user_id' and r[4] == 'id'
               for r in db.execute('PRAGMA foreign_key_list(account)')):
        raise PersistenceError('base_identity_foreign_key_missing')


@contextmanager
def transaction(db, *, write=True):
    if not isinstance(db, sqlite3.Connection) or db.in_transaction:
        raise PersistenceError('idle_connection_required')
    if db.execute('PRAGMA foreign_keys').fetchone()[0] != 1:
        raise PersistenceError('foreign_keys_required')
    db.execute('BEGIN IMMEDIATE' if write else 'BEGIN')
    try:
        yield
        db.commit()
    except BaseException:
        db.rollback()
        raise


def check_integrity(db):
    if [r[0] for r in db.execute('PRAGMA integrity_check')] != ['ok']:
        raise PersistenceError('integrity_check_failed')
    if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise PersistenceError('foreign_key_check_failed')


def verify_schema(db):
    # Known additive extensions are verified as a whole, never ignored by prefix.
    if db.execute(
            "SELECT 1 FROM sqlite_master WHERE name='email_identity_journal_schema'").fetchone():
        from .identity_operation_schema import verify_journal_schema
        return verify_journal_schema(db)
    return _verify_declared_schema(db)


def _verify_declared_schema(db, extension_ddl=()):
    """Internal exact-definition verifier; extension declarations are code, not input."""
    prerequisites(db)
    objects = {r[0]: normalized(r[1]) for r in db.execute(
        "SELECT name,sql FROM sqlite_master WHERE sql IS NOT NULL AND name GLOB 'email_*'")}
    # UNIQUE INDEX has a different name position.
    expected = {(sql.split()[3] if sql.startswith('CREATE UNIQUE INDEX') else sql.split()[2]): normalized(sql)
                for sql in DDL + extension_ddl}
    if objects != expected:
        raise PersistenceError('recipient_schema_incompatible')
    versions = db.execute('SELECT version,digest FROM email_recipient_schema').fetchall()
    if len(versions) != 1 or tuple(versions[0]) != (VERSION, DIGEST):
        raise PersistenceError('recipient_schema_version_incompatible')


def migrate_recipient_schema(db):
    """Explicit additive transaction. Returns epoch; no implicit approval/backup."""
    with transaction(db):
        prerequisites(db)
        check_integrity(db)
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name GLOB 'email_*'").fetchone()
        if exists:
            verify_schema(db)
        else:
            for statement in DDL:
                db.execute(statement)
            db.execute('INSERT INTO email_recipient_schema VALUES (?,?,?)', (VERSION, DIGEST, utc_now()))
            db.execute('INSERT INTO email_identity_state VALUES (1,?,0,0,\'\',0)', (uuid.uuid4().hex,))
            verify_schema(db)
        check_integrity(db)
        row = db.execute('SELECT epoch FROM email_identity_state WHERE slot=1').fetchone()
        if row is None:
            raise PersistenceError('identity_state_missing')
        return row[0]
