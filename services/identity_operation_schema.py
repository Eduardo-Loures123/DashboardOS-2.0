"""P2 additive v2 extension; explicit caller-owned SQLite connection only."""
import hashlib

from .email_recipient_schema import (
    DIGEST as BASE_DIGEST, PersistenceError,
    normalized, transaction, utc_now, check_integrity, verify_schema, _verify_declared_schema,
)

VERSION = 2
DDL = (
    """CREATE TABLE email_identity_journal_schema (
 version INTEGER PRIMARY KEY CHECK(version=2), base_digest TEXT NOT NULL,
 digest TEXT NOT NULL, applied_at TEXT NOT NULL)""",
    """CREATE TABLE email_identity_operations (
 operation_id TEXT PRIMARY KEY NOT NULL CHECK(length(operation_id)>0),
 origin TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('create','update','delete','recreate','import')),
 actor_id TEXT NOT NULL REFERENCES account(user_id), authorization_ref TEXT NOT NULL, policy_version TEXT NOT NULL,
 module TEXT, record_code TEXT, before_fingerprint TEXT NOT NULL, after_fingerprint TEXT NOT NULL,
 history_fingerprint TEXT NOT NULL, plan_fingerprint TEXT NOT NULL,
 epoch TEXT NOT NULL, expected_revision INTEGER NOT NULL CHECK(typeof(expected_revision)='integer' AND expected_revision>=0),
 expected_source_revision INTEGER NOT NULL CHECK(typeof(expected_source_revision)='integer' AND expected_source_revision>=0), expected_source_token TEXT NOT NULL,
 receipt_id TEXT NOT NULL UNIQUE, request_digest TEXT NOT NULL, plan_json TEXT NOT NULL, operation_json TEXT NOT NULL, allocations_json TEXT NOT NULL,
 status TEXT NOT NULL CHECK(status IN ('prepared','committed','aborted')),
 prepared_at TEXT NOT NULL, committed_at TEXT, aborted_at TEXT, reason TEXT,
 CHECK((kind='import' AND module IS NULL AND record_code IS NULL) OR
 (kind!='import' AND module IS NOT NULL AND module IN ('Equipes','Funcionarios','OrdensServico','Acessos','Renovacoes') AND record_code IS NOT NULL)),
 CHECK((status='prepared' AND committed_at IS NULL AND aborted_at IS NULL AND reason IS NULL)
 OR (status='committed' AND committed_at IS NOT NULL AND aborted_at IS NULL AND reason IS NULL)
 OR (status='aborted' AND committed_at IS NULL AND aborted_at IS NOT NULL AND reason IS NOT NULL AND length(reason)>0)))""",
    "CREATE INDEX email_identity_operation_status ON email_identity_operations(status,prepared_at)",
    """CREATE TABLE email_identity_receipts (
 receipt_id TEXT PRIMARY KEY NOT NULL, operation_id TEXT NOT NULL UNIQUE REFERENCES email_identity_operations(operation_id),
 sequence INTEGER NOT NULL UNIQUE CHECK(typeof(sequence)='integer' AND sequence>0),
 previous_digest TEXT UNIQUE REFERENCES email_identity_receipts(digest), digest TEXT NOT NULL UNIQUE,
 payload_json TEXT NOT NULL, committed_at TEXT NOT NULL,
 CHECK((sequence=1 AND previous_digest IS NULL) OR (sequence>1 AND previous_digest IS NOT NULL)))""",
    """CREATE TABLE email_identity_operation_events (
 id INTEGER PRIMARY KEY AUTOINCREMENT, operation_id TEXT NOT NULL REFERENCES email_identity_operations(operation_id),
 status TEXT NOT NULL CHECK(status IN ('prepared','committed','aborted')), occurred_at TEXT NOT NULL, reason TEXT)""",
    "CREATE INDEX email_identity_operation_event_owner ON email_identity_operation_events(operation_id,id)",
    """CREATE TRIGGER email_identity_operation_initial BEFORE INSERT ON email_identity_operations
 WHEN NEW.status!='prepared' OR EXISTS(SELECT 1 FROM email_identity_operations WHERE operation_id=NEW.operation_id)
 BEGIN SELECT RAISE(ABORT,'operation must start prepared and cannot replace history'); END""",
    """CREATE TRIGGER email_identity_operation_no_delete BEFORE DELETE ON email_identity_operations
 BEGIN SELECT RAISE(ABORT,'operation history is immutable'); END""",
    """CREATE TRIGGER email_identity_operation_transition BEFORE UPDATE ON email_identity_operations
 WHEN OLD.status!='prepared' OR NEW.status NOT IN ('committed','aborted')
 OR (NEW.status='committed' AND NOT EXISTS(SELECT 1 FROM email_identity_receipts WHERE operation_id=OLD.operation_id AND receipt_id=OLD.receipt_id))
 OR (NEW.status='aborted' AND EXISTS(SELECT 1 FROM email_identity_receipts WHERE operation_id=OLD.operation_id))
 BEGIN SELECT RAISE(ABORT,'invalid operation transition'); END""",
    """CREATE TRIGGER email_identity_operation_prepared_event AFTER INSERT ON email_identity_operations
 BEGIN INSERT INTO email_identity_operation_events(operation_id,status,occurred_at) VALUES (NEW.operation_id,'prepared',NEW.prepared_at); END""",
    """CREATE TRIGGER email_identity_operation_terminal_event AFTER UPDATE ON email_identity_operations
 BEGIN INSERT INTO email_identity_operation_events(operation_id,status,occurred_at,reason)
 VALUES (NEW.operation_id,NEW.status,coalesce(NEW.committed_at,NEW.aborted_at),NEW.reason); END""",
    """CREATE TRIGGER email_identity_receipt_insert BEFORE INSERT ON email_identity_receipts
 WHEN NOT EXISTS(SELECT 1 FROM email_identity_operations WHERE operation_id=NEW.operation_id AND receipt_id=NEW.receipt_id AND status='prepared')
 OR NEW.sequence!=(SELECT coalesce(max(sequence),0)+1 FROM email_identity_receipts)
 OR NEW.previous_digest IS NOT (SELECT digest FROM email_identity_receipts ORDER BY sequence DESC LIMIT 1)
 BEGIN SELECT RAISE(ABORT,'invalid receipt or chain position'); END""",
)

_IMMUTABLE_OPERATION = (
    'operation_id', 'origin', 'kind', 'actor_id', 'authorization_ref', 'policy_version', 'module', 'record_code',
    'before_fingerprint', 'after_fingerprint', 'history_fingerprint', 'plan_fingerprint', 'epoch',
    'expected_revision', 'expected_source_revision', 'expected_source_token', 'receipt_id',
    'request_digest', 'plan_json', 'operation_json', 'allocations_json', 'prepared_at',
)
DDL += ("CREATE TRIGGER email_identity_operation_payload BEFORE UPDATE ON email_identity_operations WHEN " +
        ' OR '.join(f'NEW.{name} IS NOT OLD.{name}' for name in _IMMUTABLE_OPERATION) +
        " BEGIN SELECT RAISE(ABORT,'operation payload is immutable'); END",)
for _table, _key in (('email_identity_receipts', 'receipt_id'), ('email_identity_operation_events', 'id')):
    DDL += (
        f"CREATE TRIGGER {_table}_no_update BEFORE UPDATE ON {_table} BEGIN SELECT RAISE(ABORT,'immutable journal history'); END",
        f"CREATE TRIGGER {_table}_no_delete BEFORE DELETE ON {_table} BEGIN SELECT RAISE(ABORT,'immutable journal history'); END",
        f"CREATE TRIGGER {_table}_no_replace BEFORE INSERT ON {_table} WHEN EXISTS(SELECT 1 FROM {_table} WHERE {_key}=NEW.{_key}) BEGIN SELECT RAISE(ABORT,'immutable journal history'); END",
    )

DELTA_DIGEST = hashlib.sha256('\n'.join(normalized(sql) for sql in DDL).encode()).hexdigest()
DIGEST = hashlib.sha256((BASE_DIGEST + '\n' + DELTA_DIGEST).encode()).hexdigest()


def verify_journal_schema(db):
    _verify_declared_schema(db, DDL)
    rows = db.execute('SELECT version,base_digest,digest FROM email_identity_journal_schema').fetchall()
    if len(rows) != 1 or tuple(rows[0]) != (VERSION, BASE_DIGEST, DIGEST):
        raise PersistenceError('journal_schema_version_incompatible')


def migrate_identity_journal(db):
    """Validate v1, then install v2 atomically. Never rewrites v1 DDL/data/version."""
    with transaction(db):
        if db.execute("SELECT 1 FROM sqlite_master WHERE name='email_identity_journal_schema'").fetchone():
            verify_journal_schema(db)
        else:
            verify_schema(db)
            check_integrity(db)
            for statement in DDL:
                db.execute(statement)
            db.execute('INSERT INTO email_identity_journal_schema VALUES (?,?,?,?)',
                       (VERSION, BASE_DIGEST, DIGEST, utc_now()))
            verify_journal_schema(db)
        check_integrity(db)
    return DIGEST
