"""3C.2A temporary SQLite only. No real database/Excel, application or SMTP."""
import ast
from dataclasses import replace
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from services.email_recipient_schema import (
    DDL, DIGEST, VERSION, PersistenceError, migrate_recipient_schema, verify_schema,
)
from services.email_recipient_repository import (
    EmailRecipientRepository, IdentityCheckpoint, IdentityManifest, TeamIncarnation, RecordIncarnation,
)
from tests import test_email_recipient_policy as policy_fixtures

ROOT = Path(__file__).resolve().parents[1]


def source_statements(filename, function):
    """Read the real schema declarations as literals, WITHOUT importing services."""
    tree = ast.parse((ROOT / 'services' / filename).read_text(encoding='utf-8-sig'))
    node = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == function)
    assignment = next(n for n in node.body if isinstance(n, ast.Assign) and
                      any(isinstance(t, ast.Name) and t.id == 'statements' for t in n.targets))
    return ast.literal_eval(assignment.value)


def synthetic_db(path):
    db = sqlite3.connect(path, timeout=5, check_same_thread=False)
    db.execute('PRAGMA foreign_keys=ON')
    db.executescript('''CREATE TABLE users(id TEXT PRIMARY KEY,password_hash TEXT NOT NULL);
        CREATE TABLE sessions(token_hash TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),expires REAL NOT NULL);
        CREATE TABLE attempts(client TEXT NOT NULL,occurred REAL NOT NULL);''')
    for statement in source_statements('enterprise_service.py', 'schema') + source_statements('profile_service.py', 'profile_schema'):
        db.execute(statement)
    for uid, role in [('root', 'superadmin'), ('root2', 'superadmin'), ('admin', 'admin'), ('alice', 'user'), ('bob', 'user')]:
        db.execute('INSERT INTO users VALUES (?,?)', (uid, 'fictional-password-hash'))
        db.execute('INSERT INTO account(user_id,role,email,verified,email_alerts) VALUES (?,?,?,1,1)',
                   (uid, role, uid + '@example.test'))
        db.execute('INSERT INTO profile_logins VALUES (?,?)', (uid, 'login-' + uid))
    db.execute("INSERT INTO sessions VALUES ('fictional-session','alice',9999999999)")
    db.execute("INSERT INTO events VALUES (1,'fictional-old-event','test','title','fictional body','','2026-01-01')")
    db.execute("INSERT INTO notifications VALUES (1,1,'alice',NULL,0)")
    db.execute("INSERT INTO outbox VALUES (1,1,'alice','alice@example.test','subject','fictional historic body',2,'pending',0,NULL)")
    db.execute("INSERT INTO mail_attempts VALUES (1,1,'2026-01-01','failure','fictional')")
    db.execute("INSERT INTO snapshots VALUES ('OrdensServico','O1','fictional legacy snapshot')")
    db.commit()
    return db


def previous_state(db):
    objects = tuple(db.execute("SELECT type,name,sql FROM sqlite_master WHERE name NOT GLOB 'email_*' AND name NOT LIKE 'sqlite_%' ORDER BY type,name"))
    tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT GLOB 'email_*' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    return objects, {name: tuple(db.execute('SELECT * FROM "' + name + '" ORDER BY rowid')) for name in tables}


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='email-policy-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'synthetic.sqlite3'
        self.db = synthetic_db(self.path)
        self.addCleanup(self.db.close)
        self.before = previous_state(self.db)
        epoch = migrate_recipient_schema(self.db)
        self.repo = EmailRecipientRepository(self.db, IdentityCheckpoint(epoch, 0, 0, ''))
        # Reuse fixture setup without importing/initializing the application.
        fixture = policy_fixtures.EmailPolicyTests('test_primary_explicit_unique_designation')
        fixture.setUp()
        self.raw, self.snapshot, self.event = fixture.raw, fixture.snapshot, fixture.event
        self.manifest = IdentityManifest(epoch, 1, 'source-1',
            (TeamIncarnation('T1', 'team-one-life-1'), TeamIncarnation('T2', 'team-two-life-1')),
            (RecordIncarnation('OrdensServico', 'O1', 'order-one-life-1', 'T1', 1),
             RecordIncarnation('OrdensServico', 'O2', 'order-two-life-1', 'T2', 1),
             RecordIncarnation('Acessos', 'A1', 'access-life-1', 'T1', 1),
             RecordIncarnation('Renovacoes', 'R1', 'renewal-life-1', 'T1', 1)))
        self.repo.sync_identities(self.manifest, actor_id='root')

    def grant(self, grant_id='g1', uid='alice', module='OrdensServico', scope='module', **kwargs):
        return self.repo.grant(grant_id, uid, module, scope, actor_id='root', raw=self.raw,
                               snapshot=self.snapshot, **kwargs)

    def sync(self, **changes):
        candidate = replace(self.manifest, source_revision=self.manifest.source_revision + 1,
                                source_token='source-' + str(self.manifest.source_revision + 1), **changes)
        self.repo.sync_identities(candidate, actor_id='root')
        self.manifest = candidate

    def resolve(self, prepared=None):
        return self.repo.resolve(self.event, self.raw, snapshot=self.snapshot, prepared=prepared)

    def test_schema_tables_indices_foreign_keys_and_version(self):
        verify_schema(self.db)
        self.assertEqual(tuple(self.db.execute('SELECT version,digest FROM email_recipient_schema').fetchone()), (VERSION, DIGEST))
        self.assertEqual(len(self.db.execute("SELECT sql FROM sqlite_master WHERE sql IS NOT NULL AND name GLOB 'email_*'").fetchall()), len(DDL))
        self.assertTrue(self.db.execute('PRAGMA foreign_key_list(email_recipient_authorizations)').fetchall())
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertEqual(self.db.execute('PRAGMA foreign_key_check').fetchall(), [])
        self.assertEqual(len([r for r in self.db.execute('PRAGMA index_list(email_recipient_authorizations)') if r[4]]), 3)

    def test_migration_preserves_all_previous_tables_rows_and_schema(self):
        self.assertEqual(previous_state(self.db), self.before)
        self.grant(); self.repo.designate_primary('p1', 'admin', actor_id='root')
        self.assertEqual(previous_state(self.db), self.before)

    def test_migration_reexecution_is_idempotent_without_seeding_grants(self):
        dump = tuple(self.db.iterdump())
        self.assertEqual(migrate_recipient_schema(self.db), self.repo.checkpoint.epoch)
        self.assertEqual(tuple(self.db.iterdump()), dump)
        self.assertEqual(self.db.execute('SELECT count(*) FROM email_primary_designations').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM email_recipient_authorizations').fetchone()[0], 0)

    def test_migration_rejects_name_collision_and_rolls_back(self):
        other = synthetic_db(Path(self.temp.name) / 'collision.sqlite3')
        self.addCleanup(other.close)
        other.execute('CREATE TABLE email_primary_designations(unrelated TEXT)'); other.commit()
        before = tuple(other.iterdump())
        with self.assertRaisesRegex(PersistenceError, 'schema_incompatible'): migrate_recipient_schema(other)
        self.assertEqual(tuple(other.iterdump()), before)

    def test_migration_rejects_missing_base_or_wrong_foreign_key(self):
        other = sqlite3.connect(Path(self.temp.name) / 'empty.sqlite3'); self.addCleanup(other.close)
        other.execute('PRAGMA foreign_keys=ON')
        with self.assertRaisesRegex(PersistenceError, 'base_schema_incompatible'): migrate_recipient_schema(other)
        self.assertFalse(other.execute("SELECT 1 FROM sqlite_master WHERE name GLOB 'email_*'").fetchone())
        other.executescript('''CREATE TABLE users(id TEXT PRIMARY KEY,password_hash TEXT NOT NULL);
            CREATE TABLE account(user_id TEXT PRIMARY KEY,role TEXT,state TEXT,email TEXT,verified INTEGER,email_alerts INTEGER);''')
        with self.assertRaisesRegex(PersistenceError, 'foreign_key_missing'): migrate_recipient_schema(other)

    def test_migration_rejects_tampered_version_or_missing_trigger(self):
        self.db.execute("UPDATE email_recipient_schema SET digest='incorrect'"); self.db.commit()
        with self.assertRaisesRegex(PersistenceError, 'version_incompatible'): migrate_recipient_schema(self.db)
        self.db.execute('UPDATE email_recipient_schema SET digest=?', (DIGEST,)); self.db.commit()
        self.db.execute('DROP TRIGGER email_audit_no_update'); self.db.commit()
        with self.assertRaisesRegex(PersistenceError, 'schema_incompatible'): migrate_recipient_schema(self.db)

    def test_foreign_keys_must_be_enabled_and_connection_idle(self):
        self.db.execute('PRAGMA foreign_keys=OFF')
        with self.assertRaisesRegex(PersistenceError, 'foreign_keys_required'): migrate_recipient_schema(self.db)
        self.db.execute('PRAGMA foreign_keys=ON'); self.db.execute('BEGIN')
        with self.assertRaisesRegex(PersistenceError, 'idle_connection_required'): migrate_recipient_schema(self.db)
        self.db.rollback()

    def test_first_primary_and_priority_do_not_grant_content(self):
        self.repo.designate_primary('p1', 'admin', actor_id='root')
        self.assertEqual(self.resolve().primary_account_id, 'admin')
        self.assertFalse(self.resolve().email_account_ids)
        self.grant(uid='admin'); self.grant('g2')
        self.assertEqual(self.resolve().email_account_ids, ('admin', 'alice'))

    def test_duplicate_primary_rejected_preserving_original_and_rejection_audit(self):
        self.repo.designate_primary('p1', 'admin', actor_id='root')
        with self.assertRaisesRegex(PersistenceError, 'primary_already_designated'):
            self.repo.designate_primary('p2', 'root2', actor_id='root')
        self.assertEqual(self.resolve().primary_account_id, 'admin')
        self.assertEqual(self.db.execute('SELECT result FROM email_recipient_audit ORDER BY id DESC LIMIT 1').fetchone()[0], 'rejected')

    def test_primary_replacement_and_revocation_preserve_history(self):
        self.repo.designate_primary('p1', 'admin', actor_id='root')
        self.repo.designate_primary('p2', 'root2', actor_id='root', replace_current=True, reason='approved-replacement')
        self.assertEqual(self.resolve().primary_account_id, 'root2')
        self.assertEqual(tuple(self.db.execute('SELECT active,revoked_by FROM email_primary_designations WHERE designation_id=\'p1\'').fetchone()), (0, 'root'))
        self.repo.revoke_primary('p2', actor_id='root', reason='responsibility-ended')
        self.assertIsNone(self.resolve().primary_account_id)
        self.assertEqual(self.db.execute('SELECT count(*) FROM email_primary_designations').fetchone()[0], 2)

    def test_primary_failed_replacement_restores_old_primary_and_audit(self):
        self.repo.designate_primary('p1', 'admin', actor_id='root')
        with self.assertRaisesRegex(PersistenceError, 'integrity_conflict'):
            self.repo.designate_primary('p1', 'root2', actor_id='root', replace_current=True, reason='replacement')
        self.assertEqual(self.resolve().primary_account_id, 'admin')
        self.assertFalse(self.db.execute("SELECT 1 FROM email_recipient_audit WHERE operation='primary.revoke'").fetchone())

    def test_primary_invalid_targets_and_unauthorized_approvers(self):
        for uid, reason in [('missing', 'target_account_missing'), ('alice', 'target_role_invalid')]:
            with self.subTest(uid=uid), self.assertRaisesRegex(PersistenceError, reason):
                self.repo.designate_primary('p-' + uid, uid, actor_id='root')
        self.db.execute("UPDATE account SET state='inactive' WHERE user_id='admin'"); self.db.commit()
        with self.assertRaisesRegex(PersistenceError, 'target_account_not_active'):
            self.repo.designate_primary('p-admin', 'admin', actor_id='root')
        for actor in ('admin', 'alice', 'unknown'):
            with self.subTest(actor=actor), self.assertRaisesRegex(PersistenceError, 'active_superadmin_required'):
                self.repo.designate_primary('p-x', 'root2', actor_id=actor)

    def test_admin_authority_is_checked_again_inside_transaction(self):
        self.repo.designate_primary('p1', 'admin', actor_id='root')
        self.db.execute("UPDATE account SET role='user' WHERE user_id='root'"); self.db.commit()
        with self.assertRaisesRegex(PersistenceError, 'active_superadmin_required'):
            self.repo.revoke_primary('p1', actor_id='root', reason='attempt')
        self.assertEqual(self.resolve().primary_account_id, 'admin')

    def test_all_scopes_persist_and_rehydrate_into_3c1(self):
        for grant_id, scope, constraints in [('module', 'module', {}), ('team', 'team', {'team_code': 'T1'}),
                                              ('record', 'record', {'record_code': 'O1'})]:
            self.grant(grant_id, scope=scope, **constraints)
        current = self.repo.load_policy()
        self.assertEqual(len(current.authorizations), 3)
        self.assertEqual(self.resolve().email_account_ids, ('alice',))
        alice = next(d for d in self.resolve().decisions if d.account_id == 'alice')
        self.assertEqual(alice.authorization_sources, ('module', 'record', 'team'))

    def test_active_uniqueness_handles_optional_null_fields_for_each_scope(self):
        for i, (scope, constraints) in enumerate([('module', {}), ('team', {'team_code': 'T1'}), ('record', {'record_code': 'O1'})]):
            self.grant('g' + str(i), scope=scope, **constraints)
            with self.assertRaisesRegex(PersistenceError, 'integrity_conflict'):
                self.grant('duplicate' + str(i), scope=scope, **constraints)

    def test_revoke_and_reauthorize_with_new_id_keeps_history(self):
        self.grant()
        prepared = self.resolve()
        self.repo.revoke('g1', actor_id='root', reason='revoked-by-owner')
        self.assertFalse(self.resolve(prepared).email_account_ids)
        self.grant('g2')
        self.assertEqual(self.resolve().email_account_ids, ('alice',))
        self.assertEqual(self.db.execute('SELECT count(*) FROM email_recipient_authorizations').fetchone()[0], 2)

    def test_unknown_target_invalid_scope_and_browser_metadata_rejected(self):
        for args in [dict(uid='missing'), dict(module='*'), dict(scope='unknown'), dict(team_code='T1'),
                     dict(scope='team', team_code='missing'), dict(scope='record', record_code='missing')]:
            with self.subTest(args=args), self.assertRaises(PersistenceError): self.grant(**args)
        with self.assertRaisesRegex(PersistenceError, 'identity_source_stale'):
            self.repo.sync_identities({'teams': []}, actor_id='root')

    def test_disabled_grantee_and_blocked_approver_cannot_create_grant(self):
        self.db.execute("UPDATE account SET state='inactive' WHERE user_id='alice'"); self.db.commit()
        with self.assertRaisesRegex(PersistenceError, 'target_account_not_active'): self.grant()
        self.db.execute("UPDATE account SET state='blocked' WHERE user_id='root'"); self.db.commit()
        with self.assertRaisesRegex(PersistenceError, 'active_superadmin_required'): self.grant()

    def test_sql_checks_and_foreign_keys_reject_invalid_grants(self):
        self.grant(scope='record', record_code='O1')
        row = dict(zip([r[1] for r in self.db.execute('PRAGMA table_info(email_recipient_authorizations)')],
                       self.db.execute('SELECT * FROM email_recipient_authorizations').fetchone()))
        for changes in [dict(account_id='missing'), dict(module='*'), dict(scope='*'), dict(active=2),
                        dict(record_generation=0), dict(operational_generation=0), dict(team_code='missing'),
                        dict(team_generation=2), dict(record_code='O2'), dict(scope='module'), dict(team_code=None),
                        dict(record_generation=None), dict(active=0)]:
            data = dict(row, grant_id='invalid', **changes)
            with self.subTest(changes=changes), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute('INSERT INTO email_recipient_authorizations (' + ','.join(data) + ') VALUES (' + ','.join('?' for _ in data) + ')', tuple(data.values()))
            self.db.rollback()

    def test_direct_sql_primary_singleton_and_foreign_keys(self):
        self.repo.designate_primary('p1', 'admin', actor_id='root')
        for account in ('root2', 'missing'):
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute('INSERT INTO email_primary_designations(designation_id,account_id,approved_by,approved_at,active) VALUES (?,?,?, ?,1)',
                                ('p2', account, 'root', '2026-11-08T12:00:00+00:00'))
            self.db.rollback()

    def test_generation_and_foreign_key_checks_on_identity_registry(self):
        for args in [('OrdensServico', 'bad', 0, 'token', 'T1', 1, 1, 1),
                     ('OrdensServico', 'bad', 1, 'token', 'missing', 1, 1, 1)]:
            with self.assertRaises(sqlite3.IntegrityError):
                self.db.execute('INSERT INTO email_record_identities VALUES (?,?,?,?,?,?,?,?)', args)
            self.db.rollback()

    def test_audit_is_append_only_including_replace(self):
        first = self.db.execute('SELECT * FROM email_recipient_audit ORDER BY id LIMIT 1').fetchone()
        for sql in ['UPDATE email_recipient_audit SET result=\'rejected\'', 'DELETE FROM email_recipient_audit']:
            with self.assertRaises(sqlite3.IntegrityError): self.db.execute(sql)
            self.db.rollback()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('INSERT OR REPLACE INTO email_recipient_audit VALUES (?,?,?,?,?,?,?,?)', first)
        self.db.rollback()
        self.assertEqual(tuple(self.db.execute('SELECT * FROM email_recipient_audit ORDER BY id LIMIT 1').fetchone()), tuple(first))

    def test_history_payload_ids_and_revoked_state_are_immutable(self):
        self.grant(); self.repo.revoke('g1', actor_id='root', reason='ended')
        for sql in ["UPDATE email_recipient_authorizations SET account_id='bob' WHERE grant_id='g1'",
                    "UPDATE email_recipient_authorizations SET active=1,revoked_by=NULL,revoked_at=NULL,revocation_reason=NULL WHERE grant_id='g1'",
                    'DELETE FROM email_recipient_authorizations', 'DELETE FROM email_record_identities']:
            with self.assertRaises(sqlite3.IntegrityError): self.db.execute(sql)
            self.db.rollback()

    def test_audit_has_utc_actor_account_operation_and_no_secrets(self):
        self.grant(); self.repo.revoke('g1', actor_id='root', reason='ended')
        entries = self.db.execute('SELECT actor_id,affected_account,operation,occurred_at,result,details FROM email_recipient_audit').fetchall()
        self.assertTrue(any(r[1] == 'alice' and r[2] == 'authorization.grant' for r in entries))
        self.assertTrue(all(r[0] == 'root' and r[3].endswith('+00:00') and r[4] == 'success' for r in entries))
        self.assertNotIn('fictional-password-hash', str(entries))
        self.assertNotIn('fictional-session', str(entries))

    def test_unexpected_transaction_failure_rolls_back_data_and_audit(self):
        before = tuple(self.db.iterdump()); checkpoint = self.repo.checkpoint
        with patch.object(self.repo, '_audit', side_effect=RuntimeError('injected failure')):
            with self.assertRaisesRegex(RuntimeError, 'injected failure'): self.grant()
        self.assertEqual(tuple(self.db.iterdump()), before)
        self.assertEqual(self.repo.checkpoint, checkpoint)

    def test_schema_creation_failure_rolls_back_entire_migration(self):
        other = synthetic_db(Path(self.temp.name) / 'rollback.sqlite3'); self.addCleanup(other.close)
        before = previous_state(other)
        def authorize(action, arg1, arg2, database, source):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_CREATE_INDEX and arg1 == 'email_record_current' else sqlite3.SQLITE_OK
        other.set_authorizer(authorize)
        with self.assertRaises(sqlite3.DatabaseError): migrate_recipient_schema(other)
        other.set_authorizer(None)
        self.assertEqual(previous_state(other), before)
        self.assertFalse(other.execute("SELECT 1 FROM sqlite_master WHERE name GLOB 'email_*'").fetchone())

    def test_restart_preserves_generation_and_rehydration(self):
        self.grant(scope='record', record_code='O1')
        checkpoint = self.repo.checkpoint
        other = sqlite3.connect(self.path); self.addCleanup(other.close)
        other.execute('PRAGMA foreign_keys=ON')
        restarted = EmailRecipientRepository(other, checkpoint)
        self.assertEqual(restarted.resolve(self.event, self.raw, snapshot=self.snapshot).email_account_ids, ('alice',))
        self.assertEqual(other.execute("SELECT generation FROM email_record_identities WHERE module='OrdensServico' AND code='O1'").fetchone()[0], 1)

    def test_record_delete_recreate_same_code_and_3a_generation_denies_old_grant(self):
        self.grant(scope='record', record_code='O1')
        original = self.manifest.records
        self.sync(records=tuple(r for r in original if r.code != 'O1'))
        self.assertFalse(self.resolve().email_account_ids)
        self.sync(records=tuple(replace(r, incarnation='order-one-life-2') if r.code == 'O1' else r for r in original))
        self.assertFalse(self.resolve().email_account_ids)
        self.assertIn('authorization_identity_stale:g1', self.resolve().issues)
        self.assertEqual(self.db.execute("SELECT generation,present FROM email_record_identities WHERE module='OrdensServico' AND code='O1' ORDER BY generation").fetchall(), [(1, 0), (2, 1)])

    def test_old_record_incarnation_cannot_return_after_tombstone(self):
        original = self.manifest.records
        self.sync(records=tuple(r for r in original if r.code != 'O1'))
        with self.assertRaisesRegex(PersistenceError, 'record_incarnation_reused'): self.sync(records=original)
        self.assertFalse(self.db.execute("SELECT 1 FROM email_record_identities WHERE code='O1' AND present=1").fetchone())

    def test_team_recreation_denies_old_team_grants(self):
        self.grant(scope='team', team_code='T1')
        self.sync(teams=tuple(replace(t, incarnation='team-one-life-2') if t.code == 'T1' else t for t in self.manifest.teams))
        self.assertFalse(self.resolve().email_account_ids)
        self.assertIn('authorization_identity_stale:g1', self.resolve().issues)

    def test_record_move_and_return_does_not_reactivate_old_record_grant(self):
        self.grant(scope='record', record_code='O1')
        original = self.manifest.records
        self.sync(records=tuple(replace(r, team_code='T2') if r.code == 'O1' else r for r in original))
        self.raw['Funcionarios'][0]['equipe'] = 'T2'
        self.assertFalse(self.resolve().email_account_ids)
        self.sync(records=original); self.raw['Funcionarios'][0]['equipe'] = 'T1'
        self.assertFalse(self.resolve().email_account_ids)

    def test_manifest_stale_duplicate_missing_team_and_invalid_generation_rejected(self):
        with self.assertRaisesRegex(PersistenceError, 'identity_source_stale'):
            self.repo.sync_identities(self.manifest, actor_id='root')
        for changes in [dict(teams=self.manifest.teams + self.manifest.teams[:1]),
                        dict(records=(replace(self.manifest.records[0], team_code='missing'),)),
                        dict(records=(replace(self.manifest.records[0], operational_generation=0),))]:
            with self.subTest(changes=changes), self.assertRaises(PersistenceError): self.sync(**changes)

    def test_source_sequence_cannot_skip_a_move_and_return_transition(self):
        self.grant(scope='record', record_code='O1')
        skipped = replace(self.manifest, source_revision=self.manifest.source_revision + 2, source_token='source-gap')
        with self.assertRaisesRegex(PersistenceError, 'identity_source_gap'):
            self.repo.sync_identities(skipped, actor_id='root')
        self.assertEqual(self.repo.checkpoint.source_revision, self.manifest.source_revision)
        with self.assertRaisesRegex(PersistenceError, 'identity_continuity_unavailable'): self.resolve()
        with self.assertRaisesRegex(PersistenceError, 'identity_recovery_required'): self.sync()

    def test_explicit_recovery_requires_new_epoch_fresh_lifetimes_and_new_grants(self):
        self.grant(scope='record', record_code='O1')
        self.repo.invalidate_continuity('externally-approved-new-epoch', actor_id='root', reason='lost-continuity')
        fresh = IdentityManifest(self.repo.checkpoint.epoch, 1, 'new-source-1',
            tuple(replace(t, incarnation=t.incarnation + '-reconciled') for t in self.manifest.teams),
            tuple(replace(r, incarnation=r.incarnation + '-reconciled') for r in self.manifest.records))
        self.repo.sync_identities(fresh, actor_id='root')
        self.assertFalse(self.resolve().email_account_ids)
        self.grant('fresh-grant', scope='record', record_code='O1')
        self.assertEqual(self.resolve().email_account_ids, ('alice',))

    def test_migration_and_repository_support_sqlite_row_factory(self):
        self.db.row_factory = sqlite3.Row
        verify_schema(self.db)
        self.assertEqual(migrate_recipient_schema(self.db), self.repo.checkpoint.epoch)
        self.grant()
        self.assertEqual(self.resolve().email_account_ids, ('alice',))

    def test_wrong_module_team_and_record_do_not_combine_after_rehydration(self):
        self.grant('wrong-team', scope='team', team_code='T2')
        self.grant('wrong-module', module='Acessos', scope='team', team_code='T1')
        self.assertFalse(self.resolve().email_account_ids)
        self.grant('wrong-record', scope='record', record_code='O2')
        self.assertFalse(self.resolve().email_account_ids)

    def test_revocation_audit_identifies_the_affected_account(self):
        self.grant(); self.repo.revoke('g1', actor_id='root', reason='ended')
        row = self.db.execute("SELECT affected_account,result FROM email_recipient_audit WHERE operation='authorization.revoke'").fetchone()
        self.assertEqual(tuple(row), ('alice', 'success'))

    def test_all_modules_can_be_persisted_without_broadening_module_scope(self):
        for module in ('OrdensServico', 'Acessos', 'Renovacoes'):
            self.grant('grant-' + module, module=module)
        self.assertEqual({g.module for g in self.repo.load_policy().authorizations},
                         {'OrdensServico', 'Acessos', 'Renovacoes'})

    def test_revalidation_denies_blocked_inactive_unverified_and_opt_out(self):
        self.grant(); prepared = self.resolve()
        for column, value in [('state', 'blocked'), ('state', 'inactive'), ('verified', 0), ('email_alerts', 0), ('email', '')]:
            self.db.execute("UPDATE account SET state='active',verified=1,email_alerts=1,email='alice@example.test' WHERE user_id='alice'")
            self.db.execute(f'UPDATE account SET {column}=? WHERE user_id=\'alice\'', (value,)); self.db.commit()
            with self.subTest(column=column, value=value): self.assertFalse(self.resolve(prepared).email_account_ids)

    def test_missing_registry_or_changed_raw_team_denies_even_module_scope(self):
        self.grant()
        self.raw['Funcionarios'][0]['equipe'] = 'T2'
        self.assertFalse(self.resolve().email_account_ids)
        self.assertIn('durable_record_identity_mismatch', self.resolve().issues)

    def test_operational_generation_rollback_rejected(self):
        self.sync(records=tuple(replace(r, operational_generation=2) if r.code == 'O1' else r for r in self.manifest.records))
        with self.assertRaisesRegex(PersistenceError, 'operational_generation_rollback'):
            self.sync(records=tuple(replace(r, operational_generation=1) if r.code == 'O1' else r for r in self.manifest.records))

    def test_unreconciled_or_invalidated_registry_cannot_authorize(self):
        self.grant()
        self.repo.invalidate_continuity('new-externally-anchored-epoch', actor_id='root', reason='restore-gap')
        with self.assertRaisesRegex(PersistenceError, 'identity_continuity_unavailable'): self.resolve()
        self.assertEqual(self.db.execute('SELECT active FROM email_recipient_authorizations').fetchone()[0], 0)
        self.assertEqual(self.db.execute('SELECT count(*) FROM email_record_identities WHERE present=1').fetchone()[0], 0)

    def test_stale_external_checkpoint_blocks_all_operations_without_data_changes(self):
        old = self.repo.checkpoint
        self.grant()
        stale = EmailRecipientRepository(self.db, old)
        before = tuple(self.db.iterdump())
        with self.assertRaisesRegex(PersistenceError, 'external_checkpoint_mismatch'): stale.load_policy()
        with self.assertRaisesRegex(PersistenceError, 'external_checkpoint_mismatch'):
            stale.designate_primary('p1', 'admin', actor_id='root')
        self.assertEqual(tuple(self.db.iterdump()), before)

    def test_restored_old_database_rejected_by_independent_checkpoint(self):
        backup = sqlite3.connect(Path(self.temp.name) / 'old-synthetic-copy.sqlite3'); self.addCleanup(backup.close)
        self.db.backup(backup)
        self.grant(); current_checkpoint = self.repo.checkpoint
        backup.execute('PRAGMA foreign_keys=ON')
        restored = EmailRecipientRepository(backup, current_checkpoint)
        with self.assertRaisesRegex(PersistenceError, 'external_checkpoint_mismatch'): restored.load_policy()

    def test_current_account_eligibility_and_no_new_prepared_recipients(self):
        self.grant(); prepared = self.resolve()
        self.grant('g-bob', uid='bob')
        self.assertEqual(self.resolve(prepared).email_account_ids, ('alice',))
        self.db.execute("UPDATE account SET verified=0 WHERE user_id='alice'"); self.db.commit()
        self.assertFalse(self.resolve(prepared).email_account_ids)

    def test_login_change_does_not_change_persistent_grantee(self):
        self.grant(); self.repo.designate_primary('p1', 'admin', actor_id='root')
        self.db.execute("UPDATE profile_logins SET login='new-login' WHERE user_id='alice'")
        self.db.execute("UPDATE account SET email='new@example.test' WHERE user_id='alice'"); self.db.commit()
        self.assertEqual(self.resolve().email_account_ids, ('alice',))

    def test_two_concurrent_primary_requests_commit_only_one(self):
        checkpoint = self.repo.checkpoint; barrier = threading.Barrier(2); results = []; lock = threading.Lock()
        def worker(index):
            db = sqlite3.connect(self.path, timeout=5)
            try:
                db.execute('PRAGMA foreign_keys=ON')
                repo = EmailRecipientRepository(db, checkpoint)
                barrier.wait(timeout=5)
                try:
                    repo.designate_primary('p' + str(index), 'admin', actor_id='root')
                    outcome = 'committed'
                except PersistenceError as exc:
                    outcome = str(exc)
                with lock: results.append(outcome)
            finally: db.close()
        workers = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for worker_thread in workers: worker_thread.start()
        for worker_thread in workers: worker_thread.join(timeout=10)
        self.assertTrue(all(not thread.is_alive() for thread in workers))
        self.assertEqual(sorted(results), ['committed', 'external_checkpoint_mismatch'])
        self.assertEqual(self.db.execute('SELECT count(*) FROM email_primary_designations WHERE active=1').fetchone()[0], 1)

