"""P3 classification uses synthetic SQLite/provider evidence; no recovery writes."""
from dataclasses import asdict, replace
from copy import deepcopy
import sqlite3
from pathlib import Path
import unittest
from unittest.mock import patch

from services.continuity_anchor import (
    AnchorError, AnchorUnavailable, AnchorPublisher, MemoryAnchorProvider,
    capture_sqlite_evidence, witness,
)
from services.identity_recovery import assess_recovery
from services.email_recipient_repository import EmailRecipientRepository
from services.email_recipient_schema import PersistenceError
from tests.test_continuity_anchor import scenario, capture, publish_prepared, reserve_authorized


class RecoveryTests(unittest.TestCase):
    def setUp(self): scenario(self)

    def assess(self, evidence=None, **overrides):
        args = dict(environment='synthetic-local', expected_witness=self.expected,
                    evidence=capture(self) if evidence is None else evidence)
        args.update(overrides)
        return assess_recovery(self.provider, **args)

    def test_normal_restart_reopens_sqlite_and_matches_anchor(self):
        checkpoint = self.fx.journal.checkpoint
        self.fx.db.close()
        db = sqlite3.connect(self.fx.path); self.addCleanup(db.close); db.execute('PRAGMA foreign_keys=ON')
        evidence = capture_sqlite_evidence(db, expected_checkpoint=checkpoint)
        self.assertEqual(self.assess(evidence).status, 'consistent')

    def test_failure_before_preparation_does_not_need_or_execute_recovery(self):
        with patch.object(self.fx.journal, '_validate_plan', side_effect=RuntimeError('before prepare')):
            with self.assertRaises(RuntimeError): self.fx.prepare()
        self.assertEqual(self.assess().status, 'consistent')
        self.assertEqual(len(self.provider.read()), 1)

    def test_prepared_but_not_published_is_pending_publication(self):
        self.fx.prepare(); decision = self.assess()
        self.assertEqual(decision.status, 'pending_publication')
        self.assertEqual(decision.allowed_actions, ('explicitly_reserve_or_publish_preparation',))
        self.assertFalse(decision.requires_administrative_approval)

    def test_reserved_preparation_is_recoverable_without_mutating_sqlite(self):
        self.fx.prepare(); evidence = capture(self)
        self.expected = self.publisher.publish(evidence, publication_id='reserve-1', expected=self.expected, reserve=True).witness
        before = tuple(self.fx.db.iterdump()); decision = self.assess(evidence)
        self.assertEqual(decision.status, 'recoverable_publish')
        self.assertEqual(decision.reason, 'reserved_preparation_proven_in_sqlite')
        self.assertEqual(tuple(self.fx.db.iterdump()), before)

    def test_published_preparation_is_consistent_but_not_permission_to_commit_automatically(self):
        publish_prepared(self)
        decision = self.assess()
        self.assertEqual(decision.status, 'consistent')
        self.assertEqual(decision.allowed_actions, ('await_authorized_p2_decision',))
        self.assertIn('automatic_sqlite_mutation', decision.prohibited_actions)

    def test_failure_during_sqlite_confirmation_leaves_published_preparation_consistent(self):
        publish_prepared(self); actual = self.fx.journal.repository._synchronize_manifest
        def fail(manifest):
            actual(manifest)
            raise RuntimeError('after partial sync')
        with patch.object(self.fx.journal.repository, '_synchronize_manifest', side_effect=fail):
            with self.assertRaises(RuntimeError): self.fx.commit()
        decision = self.assess()
        self.assertEqual(decision.status, 'consistent')
        self.assertEqual(self.fx.db.execute('SELECT status FROM email_identity_operations').fetchone()[0], 'prepared')

    def test_sqlite_commit_without_publication_is_recoverable_publish(self):
        publish_prepared(self); self.fx.commit()
        evidence = capture(self); decision = self.assess(evidence)
        self.assertEqual(decision.status, 'recoverable_publish')
        self.assertEqual(decision.allowed_actions, ('explicitly_publish_existing_commit_receipt',))
        self.expected = self.publisher.publish(evidence, publication_id='committed-1', expected=self.expected).witness
        self.assertEqual(self.assess().status, 'consistent')

    def test_response_lost_after_publication_can_be_retried_idempotently(self):
        publish_prepared(self); self.fx.commit(); evidence = capture(self)
        actual = self.provider.compare_and_swap
        def lost(*args):
            actual(*args)
            raise AnchorUnavailable('response lost after CAS')
        with patch.object(self.provider, 'compare_and_swap', side_effect=lost):
            with self.assertRaises(AnchorUnavailable):
                self.publisher.publish(evidence, publication_id='committed-1', expected=self.expected)
        self.assertEqual(self.assess(evidence).status, 'consistent')
        receipt = self.publisher.publish(evidence, publication_id='committed-1', expected=self.expected)
        self.assertEqual(len(self.provider.read()), 3)
        self.assertEqual(receipt.witness, witness(self.provider.read()[-1]))

    def test_proven_abort_not_published_is_recoverable_abort_not_automatic_sql_abort(self):
        publish_prepared(self)
        self.fx.journal.abort(self.fx.operation, self.fx.plan, authorization=self.fx.authorization, reason='cancelled')
        evidence = capture(self); before = tuple(self.fx.db.iterdump())
        decision = self.assess(evidence)
        self.assertEqual(decision.status, 'recoverable_abort')
        self.assertEqual(decision.allowed_actions, ('explicitly_publish_proven_abort',))
        self.assertEqual(tuple(self.fx.db.iterdump()), before)
        self.expected = self.publisher.publish(evidence, publication_id='aborted-1', expected=self.expected).witness
        self.assertEqual(self.assess().status, 'consistent')

    def backup(self, name):
        db = sqlite3.connect(Path(self.fx.temp.name) / name); self.addCleanup(db.close)
        db.execute('PRAGMA foreign_keys=ON'); self.fx.db.backup(db)
        return db

    def test_old_sqlite_and_its_journal_restored_together_are_detected(self):
        old = self.backup('old-sqlite.sqlite3')
        publish_prepared(self); self.fx.commit()
        self.expected = self.publisher.publish(capture(self), publication_id='committed-1', expected=self.expected).witness
        decision = self.assess(capture_sqlite_evidence(old))
        self.assertEqual(decision.status, 'rollback_detected')
        self.assertEqual(decision.reason, 'sqlite_journal_behind_anchor')
        self.assertTrue(decision.requires_administrative_approval)

    def test_abort_rollback_is_detected_even_with_identical_identity_checkpoint(self):
        publish_prepared(self); old = self.backup('old-prepared.sqlite3')
        self.fx.journal.abort(self.fx.operation, self.fx.plan, authorization=self.fx.authorization, reason='cancelled')
        self.expected = self.publisher.publish(capture(self), publication_id='aborted-1', expected=self.expected).witness
        evidence = capture_sqlite_evidence(old)
        self.assertEqual(evidence.checkpoint, self.provider.read()[-1].checkpoint)
        self.assertEqual(self.assess(evidence).status, 'rollback_detected')

    def test_old_anchor_presented_as_current_is_detected_by_retained_witness(self):
        publish_prepared(self)
        self.provider._history = self.provider.read()[:1]  # simulated independent-store rollback
        self.assertEqual(self.assess().status, 'rollback_detected')

    def test_absent_anchor_is_not_an_automatic_baseline_request(self):
        decision = assess_recovery(MemoryAnchorProvider(), environment='synthetic-local', expected_witness=self.expected, evidence=capture(self))
        self.assertEqual(decision.status, 'insufficient_evidence')
        self.assertIn('automatic_baseline_reset', decision.prohibited_actions)

    def test_missing_receipt_blocks_capture_and_publication(self):
        publish_prepared(self); self.fx.commit()
        sql = self.fx.db.execute("SELECT sql FROM sqlite_master WHERE name='email_identity_receipts_no_delete'").fetchone()[0]
        self.fx.db.execute('DROP TRIGGER email_identity_receipts_no_delete')
        self.fx.db.execute('DELETE FROM email_identity_receipts'); self.fx.db.execute(sql); self.fx.db.commit()
        with self.assertRaisesRegex(PersistenceError, 'committed_receipt_missing'): capture(self)
        decision = assess_recovery(
            self.provider, environment='synthetic-local', expected_witness=self.expected, evidence=None, evidence_error='committed_receipt_missing')
        self.assertEqual(decision.status, 'insufficient_evidence')
        self.assertIn('committed_receipt', decision.missing_evidence)

    def test_tampered_receipt_blocks_evidence_even_when_schema_is_restored(self):
        publish_prepared(self); self.fx.commit()
        sql = self.fx.db.execute("SELECT sql FROM sqlite_master WHERE name='email_identity_receipts_no_update'").fetchone()[0]
        self.fx.db.execute('DROP TRIGGER email_identity_receipts_no_update')
        self.fx.db.execute("UPDATE email_identity_receipts SET digest='tampered'"); self.fx.db.execute(sql); self.fx.db.commit()
        with self.assertRaisesRegex(PersistenceError, 'receipt_chain_invalid'): capture(self)
        decision = assess_recovery(self.provider, environment='synthetic-local', expected_witness=self.expected,
                                   evidence=None, evidence_error='receipt_chain_invalid')
        self.assertEqual(decision.status, 'insufficient_evidence')

    def test_broken_publication_digest_chain_is_divergent(self):
        publish_prepared(self)
        history = self.provider.read()
        self.provider._history = (history[0], replace(history[1], previous_digest='0' * 64))
        self.assertEqual(self.assess().status, 'divergent')

    def test_interrupted_publication_sequence_is_not_filled_by_guessing(self):
        publish_prepared(self)
        history = self.provider.read()
        self.provider._history = (history[0], replace(history[1], publication_sequence=3))
        self.assertEqual(self.assess().status, 'divergent')

    def test_pending_operation_without_verified_evidence_is_blocked(self):
        publish_prepared(self)
        decision = assess_recovery(self.provider, environment='synthetic-local', expected_witness=self.expected, evidence=None)
        self.assertEqual(decision.status, 'insufficient_evidence')
        self.assertFalse(decision.allowed_actions)

    def test_provider_unavailable_produces_explicit_read_only_retry(self):
        with patch.object(self.provider, 'read', side_effect=AnchorUnavailable('injected unavailability')):
            decision = self.assess()
        self.assertEqual(decision.status, 'anchor_unavailable')
        self.assertEqual(decision.allowed_actions, ('retry_read_only',))

    def test_wrong_epoch_and_environment_are_divergent(self):
        decision = self.assess(environment='other-environment')
        self.assertEqual(decision.status, 'divergent')
        admin = EmailRecipientRepository(self.fx.db, self.fx.journal.checkpoint)
        admin.invalidate_continuity('new-epoch', actor_id='root', reason='synthetic-recovery')
        self.assertEqual(self.assess(capture_sqlite_evidence(self.fx.db)).status, 'divergent')

    def test_capture_does_not_authorize_missing_preparation_publication_after_commit(self):
        self.fx.prepare(); self.fx.commit()
        decision = self.assess()
        self.assertEqual(decision.status, 'insufficient_evidence')
        self.assertEqual(decision.reason, 'unpublished_intermediate_states')
        self.assertTrue(decision.requires_administrative_approval)

    def test_administrative_checkpoint_change_without_journal_proof_is_not_auto_published(self):
        admin = EmailRecipientRepository(self.fx.db, self.fx.journal.checkpoint)
        admin.designate_primary('synthetic-principal', 'admin', actor_id='root')
        evidence = capture_sqlite_evidence(self.fx.db)
        self.assertEqual(self.assess(evidence).status, 'divergent')
        self.assertEqual(len(self.provider.read()), 1)

    def test_classification_is_repeatable_immutable_and_performs_no_recovery(self):
        self.fx.prepare(); evidence = capture(self)
        before = tuple(self.fx.db.iterdump()); history = self.provider.read()
        first = self.assess(evidence)
        self.assertEqual(self.assess(evidence), first)
        self.assertEqual(tuple(self.fx.db.iterdump()), before)
        self.assertEqual(self.provider.read(), history)

    def test_browser_dicts_and_replaced_evidence_do_not_prove_integrity(self):
        evidence = capture(self)
        for value in (asdict(evidence), replace(evidence)):
            with self.subTest(value=type(value)):
                decision = self.assess(value)
                self.assertEqual(decision.status, 'insufficient_evidence')

    def test_publisher_and_recovery_do_not_change_administrative_tables(self):
        before = {name: list(self.fx.db.execute('SELECT * FROM ' + name)) for name in
                  ('account','users','email_primary_designations','email_recipient_authorizations')}
        publish_prepared(self); self.fx.commit()
        self.publisher.publish(capture(self), publication_id='committed-1', expected=self.expected)
        self.assess()
        after = {name: list(self.fx.db.execute('SELECT * FROM ' + name)) for name in before}
        self.assertEqual(before, after)

    def test_broken_sqlite_receipt_predecessor_blocks_capture(self):
        publish_prepared(self); self.fx.commit()
        self.expected = self.publisher.publish(capture(self), publication_id='committed-1', expected=self.expected).witness
        self.fx.before = deepcopy(self.fx.proposed); self.fx.proposed['Funcionarios'][0]['equipe'] = 'T1'
        self.fx.operation = replace(self.fx.operation, operation_id='operation-2'); self.fx.replan()
        self.fx.prepare()
        self.expected = self.publisher.publish(capture(self), publication_id='prepared-2', expected=self.expected).witness
        self.fx.commit()
        sql = self.fx.db.execute("SELECT sql FROM sqlite_master WHERE name='email_identity_receipts_no_update'").fetchone()[0]
        self.fx.db.execute('PRAGMA foreign_keys=OFF')
        self.fx.db.execute('DROP TRIGGER email_identity_receipts_no_update')
        self.fx.db.execute("UPDATE email_identity_receipts SET previous_digest=? WHERE sequence=2", ('0' * 64,))
        self.fx.db.execute(sql); self.fx.db.commit(); self.fx.db.execute('PRAGMA foreign_keys=ON')
        with self.assertRaisesRegex(PersistenceError, 'receipt_chain_invalid'): capture(self)

    def test_identity_registry_disagrees_with_latest_confirmed_receipt(self):
        publish_prepared(self); self.fx.commit()
        self.fx.db.execute("INSERT INTO email_team_identities VALUES ('ghost-team',1,'unproven-life',1)"); self.fx.db.commit()
        with self.assertRaisesRegex(AnchorError, 'sqlite_identity_receipt_mismatch'): capture(self)

    def test_browser_witness_dict_does_not_become_trusted_server_context(self):
        self.assertEqual(self.assess(expected_witness=asdict(self.expected)).status, 'insufficient_evidence')

    def test_reserved_operation_cannot_be_discarded_by_restoring_preparation_away(self):
        original = self.backup('before-reservation.sqlite3')
        self.fx.prepare()
        self.expected = self.publisher.publish(capture(self), publication_id='reserved-1', expected=self.expected, reserve=True).witness
        decision = self.assess(capture_sqlite_evidence(original))
        self.assertEqual(decision.status, 'rollback_detected')
        self.assertEqual(decision.reason, 'reserved_preparation_missing_in_sqlite')

    def test_pre_sql_intent_prevents_unseen_restored_preparation_appearing_consistent(self):
        original = self.backup('before-pre-sql-reservation.sqlite3')
        reserve_authorized(self, 'prepare', 'intent-prepare')
        before_mutation = self.assess()
        self.assertEqual(before_mutation.status, 'insufficient_evidence')
        self.assertEqual(before_mutation.reason, 'reserved_intent_without_prepared_sqlite_evidence')
        self.fx.prepare()
        self.assertEqual(self.assess().status, 'recoverable_publish')
        restored = self.assess(capture_sqlite_evidence(original))
        self.assertEqual(restored.status, 'insufficient_evidence')
        self.assertTrue(restored.requires_administrative_approval)
        self.assertFalse(restored.allowed_actions)

    def test_reserved_abort_prevents_restored_prepared_state_from_being_silently_reused(self):
        publish_prepared(self); old = self.backup('before-abort-intent.sqlite3')
        reserve_authorized(self, 'abort', 'intent-abort', reason='cancelled')
        self.assertEqual(self.assess().status, 'insufficient_evidence')
        self.fx.journal.abort(self.fx.operation, self.fx.plan, authorization=self.fx.authorization, reason='cancelled')
        self.assertEqual(self.assess().status, 'recoverable_abort')
        restored = self.assess(capture_sqlite_evidence(old))
        self.assertEqual(restored.status, 'insufficient_evidence')
        self.assertEqual(restored.reason, 'reserved_decision_without_terminal_sqlite_evidence')
        self.expected = self.publisher.publish(capture(self), publication_id='aborted-1', expected=self.expected).witness
        self.assertEqual(self.assess().status, 'consistent')
        self.assertEqual(self.assess(capture_sqlite_evidence(old)).status, 'rollback_detected')

    def test_reserved_commit_without_committed_sqlite_proof_is_not_automatically_reexecuted(self):
        publish_prepared(self)
        reserve_authorized(self, 'commit', 'intent-commit')
        decision = self.assess()
        self.assertEqual(decision.status, 'insufficient_evidence')
        self.assertEqual(decision.reason, 'reserved_decision_without_terminal_sqlite_evidence')
        self.assertIn('automatic_business_replay', decision.prohibited_actions)
        self.fx.commit()
        self.assertEqual(self.assess().status, 'recoverable_publish')
