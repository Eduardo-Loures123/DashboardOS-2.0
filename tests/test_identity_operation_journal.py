"""P2: disposable SQLite and fictional data only, no application or Excel."""
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
from unittest.mock import patch

from services.email_recipient_schema import DDL as BASE_DDL, DIGEST as BASE_DIGEST, PersistenceError, migrate_recipient_schema, verify_schema
from services.email_recipient_repository import EmailRecipientRepository, IdentityCheckpoint, IdentityManifest, TeamIncarnation, RecordIncarnation
from services.identity_planner import PlanningContext, ProposedOperation, RecordKey, TokenAllocation, plan_identity_transition
from services.identity_operation_schema import DDL, DIGEST, migrate_identity_journal, verify_journal_schema
from services.identity_operation_journal import (
    BusinessAuthorization, ProducerContext, TrustedProducer, IdentityOperationJournal,
    IdentityReceipt, _history, verify_journal_integrity,
)
from tests import test_email_recipient_persistence as legacy_fixtures
from tests import test_identity_planner as p1_fixtures


def approve_business(request):
    return BusinessAuthorization(request.actor_id, request.operation_id, request.plan_fingerprint,
                                 request.authorization_ref, request.policy_version)


def table_rows(db, table):
    return tuple(tuple(row) for row in db.execute('SELECT * FROM "' + table + '" ORDER BY rowid'))


def v1_contents(db):
    names = [sql.split()[2] for sql in BASE_DDL if sql.startswith('CREATE TABLE')]
    return {name: table_rows(db, name) for name in names}


class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='identity-journal-synthetic-')
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'synthetic.sqlite3'
        self.db = legacy_fixtures.synthetic_db(self.path)
        self.addCleanup(self.db.close)
        self.db.execute('CREATE TABLE legacy_binary(id INTEGER PRIMARY KEY,payload BLOB,note TEXT)')
        self.db.execute('INSERT INTO legacy_binary VALUES (1,?,?)', (bytes(range(256)), 'acentos é e NUL\x00fim'))
        self.db.commit()
        epoch = migrate_recipient_schema(self.db)
        repository = EmailRecipientRepository(self.db, IdentityCheckpoint(epoch, 0, 0, ''))
        self.before = p1_fixtures.inventory()
        identities = p1_fixtures.history(self.before)
        manifest = IdentityManifest(epoch, 1, 'synthetic-baseline',
            tuple(TeamIncarnation(i.key.code, i.incarnation) for i in identities if i.key.module == 'Equipes'),
            tuple(RecordIncarnation(i.key.module, i.key.code, i.incarnation, i.team_code, i.operational_generation)
                  for i in identities if i.key.module != 'Equipes'))
        repository.sync_identities(manifest, actor_id='root')
        self.original_checkpoint = repository.checkpoint
        self.legacy_before = legacy_fixtures.previous_state(self.db)
        self.v1_before = v1_contents(self.db)
        self.v1_objects = tuple(tuple(r) for r in self.db.execute("SELECT type,name,sql FROM sqlite_master WHERE name GLOB 'email_*' ORDER BY name"))
        migrate_identity_journal(self.db)
        self.producer = TrustedProducer('synthetic-crud-producer', approve_business)
        self.journal = IdentityOperationJournal(self.db, self.original_checkpoint, self.producer)
        self.proposed = deepcopy(self.before); self.proposed['Funcionarios'][0]['equipe'] = 'T2'
        self.operation = ProposedOperation('operation-1', 'update', 'Funcionarios', 'F1')
        self.allocations = ()
        self.replan()

    def replan(self):
        checkpoint = self.journal.checkpoint
        self.plan = plan_identity_transition(self.before, self.proposed, self.operation, _history(self.db),
            context=PlanningContext(checkpoint.epoch, checkpoint.revision, checkpoint.source_revision, checkpoint.source_token),
            allocations=self.allocations)
        self.assertTrue(self.plan.ready_for_manifest, self.plan.issues)
        self.authorization = self.producer.issue('alice', self.operation, self.plan,
            authorization_ref='business-decision-1', policy_version='synthetic-policy-1')

    def prepare(self, **kwargs):
        params = dict(authorization=self.authorization, allocations=self.allocations); params.update(kwargs)
        return self.journal.prepare(self.before, self.proposed, self.operation, self.plan, **params)

    def commit(self, **kwargs):
        params = dict(authorization=self.authorization, allocations=self.allocations); params.update(kwargs)
        return self.journal.commit(self.before, self.proposed, self.operation, self.plan, **params)

    def test_additive_migration_preserves_v1_schema_rows_and_all_legacy_values(self):
        self.assertEqual(v1_contents(self.db), self.v1_before)
        self.assertEqual(legacy_fixtures.previous_state(self.db), self.legacy_before)
        original_names = {r[1] for r in self.v1_objects}
        now = tuple(tuple(r) for r in self.db.execute("SELECT type,name,sql FROM sqlite_master WHERE name GLOB 'email_*' ORDER BY name") if r[1] in original_names)
        self.assertEqual(now, self.v1_objects)
        self.assertEqual(table_rows(self.db, 'email_recipient_schema')[0][0:2], (1, BASE_DIGEST))
        self.assertEqual(table_rows(self.db, 'email_identity_journal_schema')[0][0:3], (2, BASE_DIGEST, DIGEST))
        self.assertEqual(self.db.execute('SELECT payload FROM legacy_binary').fetchone()[0], bytes(range(256)))
        self.assertFalse(table_rows(self.db, 'email_identity_operations'))

    def test_migration_reexecution_and_v1_entrypoint_are_idempotent(self):
        before = tuple(self.db.iterdump())
        self.assertEqual(migrate_identity_journal(self.db), DIGEST)
        self.assertEqual(migrate_recipient_schema(self.db), self.original_checkpoint.epoch)
        verify_schema(self.db); verify_journal_schema(self.db)
        self.assertEqual(tuple(self.db.iterdump()), before)

    def test_migration_failure_rolls_back_all_extension_objects(self):
        other = legacy_fixtures.synthetic_db(Path(self.temp.name) / 'migration-failure.sqlite3'); self.addCleanup(other.close)
        migrate_recipient_schema(other); before = tuple(other.iterdump())
        def authorize(action, first, second, database, source):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_CREATE_TABLE and first == 'email_identity_receipts' else sqlite3.SQLITE_OK
        other.set_authorizer(authorize)
        with self.assertRaises(sqlite3.DatabaseError): migrate_identity_journal(other)
        other.set_authorizer(None)
        self.assertEqual(tuple(other.iterdump()), before)

    def test_migration_rejects_tampered_base_schema(self):
        other = legacy_fixtures.synthetic_db(Path(self.temp.name) / 'tampered-v1.sqlite3'); self.addCleanup(other.close)
        migrate_recipient_schema(other)
        other.execute('DROP TRIGGER email_audit_no_update'); other.commit()
        with self.assertRaisesRegex(PersistenceError, 'schema_incompatible'): migrate_identity_journal(other)
        self.assertFalse(other.execute("SELECT 1 FROM sqlite_master WHERE name='email_identity_operations'").fetchone())

    def test_unknown_version_digest_and_unrecognized_objects_are_rejected(self):
        for column, value in [('digest', 'unknown'), ('base_digest', 'unknown')]:
            self.db.execute(f'UPDATE email_identity_journal_schema SET {column}=?', (value,)); self.db.commit()
            with self.subTest(column=column), self.assertRaisesRegex(PersistenceError, 'version_incompatible'):
                migrate_identity_journal(self.db)
            self.db.execute('UPDATE email_identity_journal_schema SET digest=?,base_digest=?', (DIGEST, BASE_DIGEST)); self.db.commit()
        self.db.execute('PRAGMA ignore_check_constraints=ON')
        self.db.execute('UPDATE email_identity_journal_schema SET version=99'); self.db.commit()
        self.db.execute('PRAGMA ignore_check_constraints=OFF')
        with self.assertRaisesRegex(PersistenceError, 'version_incompatible'): migrate_identity_journal(self.db)

    def test_foreign_keys_and_integrity_are_valid(self):
        self.prepare(); self.commit()
        self.assertEqual(self.db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
        self.assertFalse(self.db.execute('PRAGMA foreign_key_check').fetchall())
        self.assertTrue(self.db.execute('PRAGMA foreign_key_list(email_identity_receipts)').fetchall())

    def test_prepare_does_not_change_identities_or_checkpoint(self):
        before = v1_contents(self.db)
        prepared = self.prepare()
        self.assertEqual(prepared.status, 'prepared')
        self.assertEqual(v1_contents(self.db), before)
        self.assertEqual(self.journal.checkpoint, self.original_checkpoint)
        self.assertEqual([r[2] for r in table_rows(self.db, 'email_identity_operation_events')], ['prepared'])

    def test_confirm_is_atomic_and_records_real_user_without_admin_promotion(self):
        prepared = self.prepare(); receipt = self.commit()
        self.assertIsInstance(receipt, IdentityReceipt)
        self.assertEqual(receipt.receipt_id, prepared.receipt_id)
        self.assertEqual(receipt.checkpoint.revision, self.original_checkpoint.revision + 1)
        self.assertEqual(receipt.checkpoint.source_revision, self.original_checkpoint.source_revision + 1)
        self.assertEqual(receipt.checkpoint.source_token, receipt.receipt_id)
        self.assertEqual(self.db.execute("SELECT role FROM account WHERE user_id='alice'").fetchone()[0], 'user')
        self.assertEqual(legacy_fixtures.previous_state(self.db), self.legacy_before)
        self.assertEqual(self.db.execute("SELECT actor_id,status FROM email_identity_operations").fetchone(), ('alice', 'committed'))
        verify_journal_integrity(self.db)

    def test_matching_prepare_and_committed_replays_return_same_result(self):
        first = self.prepare(); self.assertEqual(self.prepare(), first)
        receipt = self.commit(); before = tuple(self.db.iterdump())
        self.assertEqual(self.commit(), receipt)
        self.assertEqual(self.prepare(), receipt)
        self.assertEqual(tuple(self.db.iterdump()), before)

    def test_same_operation_id_different_content_is_refused(self):
        self.prepare()
        self.proposed['Funcionarios'][0]['nome'] = 'A different fictional edit'
        self.replan()
        with self.assertRaisesRegex(PersistenceError, 'operation_id_content_conflict'): self.prepare()
        with self.assertRaisesRegex(PersistenceError, 'operation_id_content_conflict'): self.commit()

    def test_lost_response_after_commit_does_not_reapply_on_retry(self):
        self.prepare()
        with patch.object(self.journal, '_after_commit', side_effect=RuntimeError('response lost')):
            with self.assertRaisesRegex(RuntimeError, 'response lost'): self.commit()
        before = tuple(self.db.iterdump())
        receipt = self.commit()
        self.assertEqual(tuple(self.db.iterdump()), before)
        self.assertEqual(receipt.sequence, 1)
        self.assertEqual(len(table_rows(self.db, 'email_identity_receipts')), 1)

    def test_reopen_prepared_and_committed_operations(self):
        self.prepare()
        self.db.close()
        other = sqlite3.connect(self.path); self.addCleanup(other.close); other.execute('PRAGMA foreign_keys=ON')
        producer = TrustedProducer(self.producer.origin, approve_business)
        resumed = IdentityOperationJournal(other, self.original_checkpoint, producer)
        context = producer.issue('alice', self.operation, self.plan, authorization_ref='business-decision-1', policy_version='synthetic-policy-1')
        receipt = resumed.commit(self.before, self.proposed, self.operation, self.plan, authorization=context)
        reopened = IdentityOperationJournal(other, receipt.checkpoint, producer)
        self.assertEqual(reopened.commit(self.before, self.proposed, self.operation, self.plan, authorization=context), receipt)

    def test_stale_checkpoint_is_not_bypassed_even_for_matching_replay(self):
        self.prepare(); self.commit()
        stale = IdentityOperationJournal(self.db, self.original_checkpoint, self.producer)
        with self.assertRaisesRegex(PersistenceError, 'external_checkpoint_mismatch'):
            stale.commit(self.before, self.proposed, self.operation, self.plan, authorization=self.authorization)

    def test_aborted_operation_cannot_be_committed_reprepared_or_reused(self):
        self.prepare()
        aborted = self.journal.abort(self.operation, self.plan, authorization=self.authorization, reason='cancelled-before-confirmation')
        self.assertEqual(aborted.status, 'aborted')
        self.assertEqual(self.journal.abort(self.operation, self.plan, authorization=self.authorization, reason='cancelled-before-confirmation'), aborted)
        with self.assertRaisesRegex(PersistenceError, 'identity_operation_aborted'): self.commit()
        with self.assertRaisesRegex(PersistenceError, 'identity_operation_aborted'): self.prepare()
        self.assertEqual(v1_contents(self.db), self.v1_before)
        self.assertFalse(table_rows(self.db, 'email_identity_receipts'))

    def test_committed_operation_cannot_be_aborted(self):
        self.prepare(); self.commit()
        with self.assertRaisesRegex(PersistenceError, 'already_committed'):
            self.journal.abort(self.operation, self.plan, authorization=self.authorization, reason='late-cancel')

    def test_failed_validation_before_prepare_leaves_no_journal_entry(self):
        self.proposed['Funcionarios'][0]['nome'] = 'changed after planning'
        before = tuple(self.db.iterdump())
        with self.assertRaisesRegex(PersistenceError, 'inventory_fingerprint_mismatch'): self.prepare()
        self.assertEqual(tuple(self.db.iterdump()), before)

    def test_failure_during_prepare_including_event_insert_rolls_back(self):
        before = tuple(self.db.iterdump())
        def authorize(action, first, second, database, source):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_INSERT and first == 'email_identity_operation_events' else sqlite3.SQLITE_OK
        self.db.set_authorizer(authorize)
        with self.assertRaises(sqlite3.DatabaseError): self.prepare()
        self.db.set_authorizer(None)
        self.assertEqual(tuple(self.db.iterdump()), before)

    def test_failure_before_sync_keeps_prepared_state(self):
        self.prepare(); before = tuple(self.db.iterdump())
        with patch.object(self.journal.repository, '_synchronize_manifest', side_effect=RuntimeError('before sync')):
            with self.assertRaises(RuntimeError): self.commit()
        self.assertEqual(tuple(self.db.iterdump()), before)

    def test_failure_after_identity_writes_rolls_back_identities_audit_and_checkpoint(self):
        self.prepare(); before = tuple(self.db.iterdump()); actual = self.journal.repository._synchronize_manifest
        def fail(manifest):
            actual(manifest)
            raise RuntimeError('after identity writes')
        with patch.object(self.journal.repository, '_synchronize_manifest', side_effect=fail):
            with self.assertRaises(RuntimeError): self.commit()
        self.assertEqual(tuple(self.db.iterdump()), before)
        self.assertEqual(self.journal.checkpoint, self.original_checkpoint)

    def test_failure_after_receipt_and_terminal_event_rolls_back_everything(self):
        self.prepare(); before = tuple(self.db.iterdump()); actual = self.journal._write_receipt
        def fail(*args):
            actual(*args)
            raise RuntimeError('after receipt')
        with patch.object(self.journal, '_write_receipt', side_effect=fail):
            with self.assertRaises(RuntimeError): self.commit()
        self.assertEqual(tuple(self.db.iterdump()), before)
        self.assertEqual(self.journal.checkpoint, self.original_checkpoint)

    def test_failure_in_audit_rolls_back_sync(self):
        self.prepare(); before = tuple(self.db.iterdump())
        with patch.object(self.journal.repository, '_audit', side_effect=RuntimeError('audit unavailable')):
            with self.assertRaises(RuntimeError): self.commit()
        self.assertEqual(tuple(self.db.iterdump()), before)

    def test_sqlite_commit_failure_rolls_back_and_does_not_publish_checkpoint(self):
        self.prepare(); before = tuple(self.db.iterdump())
        class CommitFailure(sqlite3.Connection):
            def commit(self): raise sqlite3.OperationalError('injected commit failure')
        other = sqlite3.connect(self.path, factory=CommitFailure); self.addCleanup(other.close)
        other.execute('PRAGMA foreign_keys=ON')
        unit = IdentityOperationJournal(other, self.original_checkpoint, self.producer)
        with self.assertRaises(sqlite3.OperationalError):
            unit.commit(self.before, self.proposed, self.operation, self.plan, authorization=self.authorization)
        self.assertEqual(tuple(self.db.iterdump()), before)
        self.assertEqual(unit.checkpoint, self.original_checkpoint)

    def test_manifest_must_match_plan_and_reserved_receipt(self):
        prepared = self.prepare(); expected = self.journal._manifest(self.plan, prepared.receipt_id)
        for manifest in (asdict(expected), replace(expected, source_token='browser-token'),
                         replace(expected, records=expected.records[:-1]), replace(expected, source_revision=99)):
            with self.subTest(manifest=manifest), self.assertRaisesRegex(PersistenceError, 'manifest_plan_mismatch'):
                self.commit(manifest=manifest)
        self.assertIsInstance(self.commit(manifest=expected), IdentityReceipt)

    def test_manifest_is_validated_even_on_committed_replay(self):
        prepared = self.prepare(); expected = self.journal._manifest(self.plan, prepared.receipt_id)
        self.commit()
        with self.assertRaisesRegex(PersistenceError, 'manifest_plan_mismatch'):
            self.commit(manifest=replace(expected, epoch='old-epoch'))

    def test_plan_dataclass_and_applicable_flag_are_not_authorization(self):
        forged = replace(self.plan, resulting_identities=self.plan.resulting_identities[:-1])
        authorization = self.producer.issue('alice', self.operation, forged, authorization_ref='business-decision-1', policy_version='synthetic-policy-1')
        with self.assertRaisesRegex(PersistenceError, 'plan_stale_or_forged'):
            self.journal.prepare(self.before, self.proposed, self.operation, forged, authorization=authorization)

    def test_unallocated_plan_cannot_be_prepared(self):
        self.operation = ProposedOperation('new-record', 'create', 'OrdensServico', 'O3')
        self.proposed = deepcopy(self.before); self.proposed['OrdensServico'].append(dict(codigo='O3', funcionario='F1'))
        context = PlanningContext(**asdict(self.original_checkpoint))
        plan = plan_identity_transition(self.before, self.proposed, self.operation, _history(self.db), context=context)
        self.assertFalse(plan.ready_for_manifest)
        authorization = self.producer.issue('alice', self.operation, plan, authorization_ref='business-decision-1', policy_version='synthetic-policy-1')
        with self.assertRaisesRegex(PersistenceError, 'plan_not_ready'):
            self.journal.prepare(self.before, self.proposed, self.operation, plan, authorization=authorization)

    def test_context_dict_direct_dto_modified_copy_and_other_issuer_are_refused(self):
        contexts = [asdict(self.authorization), ProducerContext('alice', self.operation.operation_id,
            self.plan.plan_fingerprint, self.producer.origin, 'business-decision-1', 'synthetic-policy-1'),
            replace(self.authorization, actor_id='root'),
            TrustedProducer(self.producer.origin, approve_business).issue('alice', self.operation, self.plan,
                authorization_ref='business-decision-1', policy_version='synthetic-policy-1')]
        for context in contexts:
            with self.subTest(context=type(context)), self.assertRaisesRegex(PersistenceError, 'context_untrusted'):
                self.prepare(authorization=context)

    def test_business_policy_boolean_and_wrong_decision_are_refused(self):
        for policy in (lambda request: True, lambda request: {}, lambda request: BusinessAuthorization('root', request.operation_id, request.plan_fingerprint, request.authorization_ref, request.policy_version)):
            producer = TrustedProducer('synthetic-crud-producer', policy)
            unit = IdentityOperationJournal(self.db, self.original_checkpoint, producer)
            context = producer.issue('alice', self.operation, self.plan, authorization_ref='business-decision-1', policy_version='synthetic-policy-1')
            with self.assertRaisesRegex(PersistenceError, 'business_operation_not_authorized'):
                unit.prepare(self.before, self.proposed, self.operation, self.plan, authorization=context)

    def test_authority_is_rechecked_inside_transaction_on_commit_and_replay(self):
        requests = []
        def observe(request):
            requests.append(self.db.in_transaction)
            return approve_business(request)
        self.producer._authorize = observe
        self.prepare(); self.commit(); self.commit()
        self.assertEqual(requests, [True, True, True])
        self.producer._authorize = lambda request: False
        with self.assertRaisesRegex(PersistenceError, 'business_operation_not_authorized'): self.commit()

    def test_inactive_actor_and_revoked_business_authority_cannot_confirm(self):
        self.prepare()
        self.db.execute("UPDATE account SET state='blocked' WHERE user_id='alice'"); self.db.commit()
        with self.assertRaisesRegex(PersistenceError, 'producer_actor_not_active'): self.commit()
        self.assertEqual(self.db.execute('SELECT status FROM email_identity_operations').fetchone()[0], 'prepared')

    def test_technical_authority_cannot_designate_or_grant_administrative_permissions(self):
        with self.assertRaisesRegex(PersistenceError, 'active_superadmin_required'):
            self.journal.repository.designate_primary('not-authorized', 'admin', actor_id='alice')
        self.assertFalse(table_rows(self.db, 'email_primary_designations'))
        self.assertFalse(table_rows(self.db, 'email_recipient_authorizations'))
        self.assertFalse(hasattr(self.journal, 'designate_primary'))
        self.assertFalse(hasattr(self.journal, 'grant'))

    def test_external_transaction_cannot_bypass_checks(self):
        self.db.execute('BEGIN IMMEDIATE')
        with self.assertRaisesRegex(PersistenceError, 'idle_connection_required'): self.prepare()
        self.db.rollback()
        self.db.execute('PRAGMA foreign_keys=OFF')
        with self.assertRaisesRegex(PersistenceError, 'foreign_keys_required'): self.prepare()
        self.db.execute('PRAGMA foreign_keys=ON')

    def test_plan_obsolete_after_administrative_revision_is_refused(self):
        self.prepare()
        admin = EmailRecipientRepository(self.db, self.original_checkpoint)
        admin.designate_primary('p1', 'admin', actor_id='root')
        self.journal.repository.checkpoint = admin.checkpoint
        with self.assertRaisesRegex(PersistenceError, 'plan_stale_or_forged'): self.commit()
        self.assertFalse(table_rows(self.db, 'email_identity_receipts'))

    def test_identity_history_change_without_checkpoint_cannot_apply_old_plan(self):
        self.prepare()
        # Direct synthetic tamper: an extra historical team existence, no checkpoint update.
        self.db.execute("INSERT INTO email_team_identities VALUES ('deleted-team',1,'old-identity',0)"); self.db.commit()
        with self.assertRaisesRegex(PersistenceError, 'plan_stale_or_forged'): self.commit()

    def test_sql_cannot_rewrite_delete_replace_or_reactivate_journal_history(self):
        self.prepare()
        self.journal.abort(self.operation, self.plan, authorization=self.authorization, reason='cancelled')
        for sql in ["UPDATE email_identity_operations SET status='prepared',aborted_at=NULL,reason=NULL",
                    "UPDATE email_identity_operations SET origin='browser'", 'DELETE FROM email_identity_operations',
                    'DELETE FROM email_identity_operation_events', "UPDATE email_identity_operation_events SET reason='rewritten'"]:
            with self.subTest(sql=sql), self.assertRaises(sqlite3.IntegrityError): self.db.execute(sql)
            self.db.rollback()
        row = self.db.execute('SELECT * FROM email_identity_operations').fetchone()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('INSERT OR REPLACE INTO email_identity_operations VALUES (' + ','.join('?' for _ in row) + ')', row)
        self.db.rollback()

    def test_sql_cannot_commit_without_receipt_or_alter_receipt(self):
        self.prepare()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute("UPDATE email_identity_operations SET status='committed',committed_at='2026-01-01T00:00:00+00:00'")
        self.db.rollback(); self.commit()
        for sql in ["UPDATE email_identity_receipts SET digest='tampered'", 'DELETE FROM email_identity_receipts']:
            with self.assertRaises(sqlite3.IntegrityError): self.db.execute(sql)
            self.db.rollback()
        row = self.db.execute('SELECT * FROM email_identity_receipts').fetchone()
        with self.assertRaises(sqlite3.IntegrityError):
            self.db.execute('INSERT OR REPLACE INTO email_identity_receipts VALUES (?,?,?,?,?,?,?)', row)
        self.db.rollback()

    def test_tampered_receipt_is_rejected_even_after_attacker_restores_trigger(self):
        self.prepare(); self.commit()
        sql = self.db.execute("SELECT sql FROM sqlite_master WHERE name='email_identity_receipts_no_update'").fetchone()[0]
        self.db.execute('DROP TRIGGER email_identity_receipts_no_update')
        self.db.execute("UPDATE email_identity_receipts SET payload_json='{}'"); self.db.execute(sql); self.db.commit()
        with self.assertRaisesRegex(PersistenceError, 'receipt_chain_invalid'): self.commit()

    def test_two_operations_chain_and_preserve_old_binding_tombstones(self):
        self.prepare(); first = self.commit()
        self.before = deepcopy(self.proposed); self.proposed['Funcionarios'][0]['equipe'] = 'T1'
        self.operation = ProposedOperation('operation-2', 'update', 'Funcionarios', 'F1'); self.replan()
        self.prepare(); second = self.commit()
        self.assertEqual(second.previous_digest, first.digest)
        self.assertEqual(second.sequence, 2)
        self.assertEqual(self.db.execute("SELECT generation,present FROM email_record_identities WHERE module='OrdensServico' AND code='O1' ORDER BY generation").fetchall(), [(1, 0), (2, 0), (3, 1)])
        verify_journal_integrity(self.db)

    def test_creation_allocations_are_checked_even_on_replay(self):
        self.operation = ProposedOperation('create-1', 'create', 'OrdensServico', 'O3')
        self.proposed = deepcopy(self.before); self.proposed['OrdensServico'].append(dict(codigo='O3', funcionario='F1'))
        self.allocations = (TokenAllocation(RecordKey('OrdensServico', 'O3'), 'fresh-creation-token'),)
        self.replan(); self.prepare(); self.commit()
        with self.assertRaisesRegex(PersistenceError, 'operation_id_content_conflict'):
            self.commit(allocations=(replace(self.allocations[0], token='different-token'),))

    def test_concurrent_confirmations_do_not_duplicate_or_bypass_checkpoint(self):
        self.prepare(); checkpoint = self.original_checkpoint; barrier = threading.Barrier(2); outcomes = []; lock = threading.Lock()
        def run():
            db = sqlite3.connect(self.path, timeout=5)
            try:
                db.execute('PRAGMA foreign_keys=ON')
                producer = TrustedProducer(self.producer.origin, approve_business)
                unit = IdentityOperationJournal(db, checkpoint, producer)
                context = producer.issue('alice', self.operation, self.plan, authorization_ref='business-decision-1', policy_version='synthetic-policy-1')
                barrier.wait(timeout=5)
                try:
                    result = unit.commit(self.before, self.proposed, self.operation, self.plan, authorization=context)
                    outcome = 'committed' if isinstance(result, IdentityReceipt) else 'unexpected'
                except PersistenceError as error: outcome = str(error)
                with lock: outcomes.append(outcome)
            finally: db.close()
        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(sorted(outcomes), ['committed', 'external_checkpoint_mismatch'])
        self.assertEqual(len(table_rows(self.db, 'email_identity_receipts')), 1)

    def test_administrative_loss_of_continuity_still_blocks_technical_confirmation(self):
        self.prepare()
        admin = EmailRecipientRepository(self.db, self.original_checkpoint)
        admin.invalidate_continuity('new-epoch', actor_id='root', reason='synthetic-continuity-loss')
        self.journal.repository.checkpoint = admin.checkpoint
        with self.assertRaisesRegex(PersistenceError, 'identity_continuity_unavailable'): self.commit()

    def test_journal_contains_metadata_not_inventory_personal_values_or_legacy_messages(self):
        self.prepare(); self.commit()
        values = str(table_rows(self.db, 'email_identity_operations')) + str(table_rows(self.db, 'email_identity_receipts'))
        for forbidden in ('fictional-password-hash', 'fictional-session', 'fictional historic body', 'alice@example.test', 'Equipe 1'):
            self.assertNotIn(forbidden, values)

    def test_leaf_deletion_and_recreation_keep_history_and_allocate_new_lifetime(self):
        self.operation = ProposedOperation('delete-leaf', 'delete', 'OrdensServico', 'O1')
        self.proposed = deepcopy(self.before); self.proposed['OrdensServico'].pop(0)
        self.replan(); self.prepare(); first = self.commit()
        self.before = deepcopy(self.proposed)
        self.proposed['OrdensServico'].append(dict(codigo='O1', funcionario='F1'))
        self.operation = ProposedOperation('recreate-code', 'create', 'OrdensServico', 'O1')
        self.allocations = (TokenAllocation(RecordKey('OrdensServico', 'O1'), 'new-lifetime-for-reused-code'),)
        self.replan(); self.prepare(); receipt = self.commit()
        rows = self.db.execute("SELECT generation,present,incarnation,operational_generation FROM email_record_identities WHERE module='OrdensServico' AND code='O1' ORDER BY generation").fetchall()
        self.assertEqual([(r[0], r[1], r[3]) for r in rows], [(1, 0, 1), (2, 1, 2)])
        self.assertNotEqual(rows[0][2], rows[1][2])
        self.assertEqual(receipt.previous_digest, first.digest)

    def test_team_recreation_matches_planned_indirect_generations(self):
        self.operation = ProposedOperation('recreate-team', 'recreate', 'Equipes', 'T1')
        self.proposed = deepcopy(self.before)
        self.allocations = (TokenAllocation(RecordKey('Equipes', 'T1'), 'new-team-lifetime'),)
        self.replan(); self.prepare(); self.commit()
        self.assertEqual(self.db.execute("SELECT generation,present FROM email_team_identities WHERE code='T1' ORDER BY generation").fetchall(), [(1, 0), (2, 1)])
        rows = self.db.execute("SELECT generation,team_generation FROM email_record_identities WHERE team_code='T1' AND present=1").fetchall()
        self.assertEqual(rows, [(2, 2)] * 3)

    def test_reintroduced_historical_token_is_not_accepted_from_forged_plan(self):
        self.operation = ProposedOperation('create-other', 'create', 'OrdensServico', 'O3')
        self.proposed = deepcopy(self.before); self.proposed['OrdensServico'].append(dict(codigo='O3', funcionario='F1'))
        self.allocations = (TokenAllocation(RecordKey('OrdensServico', 'O3'), 'fresh-token'),)
        self.replan()
        self.allocations = (replace(self.allocations[0], token='OrdensServico-O1-life1'),)
        with self.assertRaisesRegex(PersistenceError, 'plan_stale_or_forged'): self.prepare()
        self.assertFalse(table_rows(self.db, 'email_identity_operations'))

    def test_failure_during_receipt_insert_rolls_back_sync_and_audit(self):
        self.prepare(); before = tuple(self.db.iterdump())
        def authorize(action, first, second, database, source):
            return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_INSERT and first == 'email_identity_receipts' else sqlite3.SQLITE_OK
        self.db.set_authorizer(authorize)
        with self.assertRaises(sqlite3.DatabaseError): self.commit()
        self.db.set_authorizer(None)
        self.assertEqual(tuple(self.db.iterdump()), before)
        self.assertEqual(self.journal.checkpoint, self.original_checkpoint)

    def test_mismatched_generations_after_sync_roll_back_instead_of_publishing_receipt(self):
        self.prepare(); before = tuple(self.db.iterdump()); actual = self.journal.repository._synchronize_manifest
        def faulty_sync(manifest):
            wrong = tuple(replace(record, incarnation='faulty-new-lifetime') if record.module == 'OrdensServico' and record.code == 'O1' else record for record in manifest.records)
            actual(replace(manifest, records=wrong))
        with patch.object(self.journal.repository, '_synchronize_manifest', side_effect=faulty_sync):
            with self.assertRaisesRegex(PersistenceError, 'persisted_identity_generation_mismatch'): self.commit()
        self.assertEqual(tuple(self.db.iterdump()), before)

    def test_unknown_extension_object_is_not_ignored(self):
        self.db.execute('CREATE TABLE email_unrecognized_extension(value TEXT)'); self.db.commit()
        with self.assertRaisesRegex(PersistenceError, 'schema_incompatible'): self.prepare()

    def test_abort_cannot_reuse_operation_id_with_different_operation_description(self):
        self.prepare()
        changed = replace(self.operation, kind='delete')
        with self.assertRaisesRegex(PersistenceError, 'operation_id_content_conflict'):
            self.journal.abort(changed, self.plan, authorization=self.authorization, reason='cancelled')
        self.assertEqual(self.db.execute('SELECT status FROM email_identity_operations').fetchone()[0], 'prepared')

    def test_technical_context_cannot_be_transferred_to_another_operation(self):
        self.operation = replace(self.operation, operation_id='different-operation')
        with self.assertRaisesRegex(PersistenceError, 'producer_context_untrusted'): self.prepare()

    def test_administrative_api_still_works_on_valid_v2_and_checks_superadmin(self):
        repository = EmailRecipientRepository(self.db, self.original_checkpoint)
        repository.designate_primary('synthetic-principal', 'admin', actor_id='root')
        repository.grant('synthetic-module-grant', 'alice', 'OrdensServico', 'module', actor_id='root', raw=self.before, snapshot={})
        repository.revoke('synthetic-module-grant', actor_id='root', reason='synthetic-test-ended')
        self.assertEqual(self.db.execute("SELECT active FROM email_recipient_authorizations WHERE grant_id='synthetic-module-grant'").fetchone()[0], 0)
        self.assertEqual(legacy_fixtures.previous_state(self.db), self.legacy_before)
        verify_journal_schema(self.db)

    def test_epoch_mismatch_is_not_accepted(self):
        self.journal.repository.checkpoint = replace(self.original_checkpoint, epoch='other-epoch')
        with self.assertRaisesRegex(PersistenceError, 'external_checkpoint_mismatch'): self.prepare()

    def test_coherent_actor_change_requires_new_id_not_reuse_of_old_operation(self):
        self.prepare()
        authorization = self.producer.issue('bob', self.operation, self.plan, authorization_ref='business-decision-1', policy_version='synthetic-policy-1')
        with self.assertRaisesRegex(PersistenceError, 'operation_id_content_conflict'): self.prepare(authorization=authorization)

    def test_committed_receipt_replay_does_not_cancel_later_valid_operations(self):
        self.prepare(); first = self.commit()
        old = (deepcopy(self.before), deepcopy(self.proposed), self.operation, self.plan, self.authorization)
        self.before = deepcopy(self.proposed); self.proposed['Funcionarios'][0]['equipe'] = 'T1'
        self.operation = replace(self.operation, operation_id='operation-2'); self.replan()
        self.prepare(); second = self.commit(); before = tuple(self.db.iterdump())
        result = self.journal.commit(*old[:4], authorization=old[4])
        self.assertEqual(result, first)
        self.assertEqual(self.journal.checkpoint, second.checkpoint)
        self.assertEqual(tuple(self.db.iterdump()), before)

    def test_sql_check_constraints_reject_invalid_operation_shapes_and_states(self):
        self.prepare()
        columns = [row[1] for row in self.db.execute('PRAGMA table_info(email_identity_operations)')]
        original = dict(zip(columns, self.db.execute('SELECT * FROM email_identity_operations').fetchone()))
        for changes in (dict(module=None), dict(module='*'), dict(record_code=None), dict(kind='unknown'),
                        dict(expected_revision=-1), dict(expected_revision=1.5), dict(expected_source_revision=1.5),
                        dict(actor_id='missing-account'), dict(status='unknown'), dict(status='aborted'), dict(status='committed')):
            data = dict(original, operation_id='invalid-operation', receipt_id='invalid-receipt', **changes)
            with self.subTest(changes=changes), self.assertRaises(sqlite3.IntegrityError):
                self.db.execute('INSERT INTO email_identity_operations (' + ','.join(data) + ') VALUES (' + ','.join('?' for _ in data) + ')', tuple(data.values()))
            self.db.rollback()

    def test_business_authorizer_cannot_be_a_boolean_configuration(self):
        with self.assertRaisesRegex(PersistenceError, 'business_authorizer_required'):
            TrustedProducer('untrusted-configuration', True)
