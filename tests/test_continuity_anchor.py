"""P3 providers and publication protocol, entirely synthetic."""
from dataclasses import asdict, FrozenInstanceError, replace
import json
import sqlite3
from pathlib import Path
import threading
import unittest
from unittest.mock import patch

from services.continuity_anchor import (
    AnchorError, AnchorUnavailable, AnchorPublisher, AnchorWitness, BootstrapPermit,
    MemoryAnchorProvider, TemporaryFileAnchorProvider, approve_bootstrap, capture_sqlite_evidence,
    verify_publications, verify_witness, witness, capture_authorized_intent,
)
from services.email_recipient_schema import PersistenceError
from tests import test_identity_operation_journal as p2_fixtures


def scenario(case, *, file=False):
    fixture = p2_fixtures.JournalTests('test_prepare_does_not_change_identities_or_checkpoint')
    fixture.setUp(); case.addCleanup(fixture.doCleanups)
    case.fx = fixture
    root = Path(fixture.temp.name)
    case.provider = TemporaryFileAnchorProvider(root / 'independent-anchor', temporary_root=root) if file else MemoryAnchorProvider()
    case.publisher = AnchorPublisher('synthetic-local', case.provider)
    case.permit = approve_bootstrap(fixture.db, actor_id='root', environment='synthetic-local',
                                    expected_checkpoint=fixture.original_checkpoint)
    case.baseline = case.publisher.bootstrap(case.permit, publication_id='baseline-1')
    case.expected = case.baseline.witness


def capture(case):
    return capture_sqlite_evidence(case.fx.db, expected_checkpoint=case.fx.journal.checkpoint)


def publish_prepared(case, *, reserve=False):
    case.fx.prepare(); evidence = capture(case)
    if reserve:
        receipt = case.publisher.publish(evidence, publication_id='reserve-1', expected=case.expected, reserve=True)
        case.expected = receipt.witness
    receipt = case.publisher.publish(evidence, publication_id='prepared-1', expected=case.expected)
    case.expected = receipt.witness
    return evidence


def reserve_authorized(case, action, publication_id, *, reason=None):
    intent = capture_authorized_intent(case.fx.journal, case.fx.before, case.fx.proposed,
        case.fx.operation, case.fx.plan, authorization=case.fx.authorization, allocations=case.fx.allocations,
        action=action, reason=reason)
    receipt = case.publisher.reserve_intent(intent, publication_id=publication_id, expected=case.expected)
    case.expected = receipt.witness
    return intent


class AnchorTests(unittest.TestCase):
    def setUp(self): scenario(self)

    def test_empty_journal_bootstrap_is_explicit_administrative_and_idempotent(self):
        before = tuple(self.fx.db.iterdump())
        self.assertEqual(self.publisher.bootstrap(self.permit, publication_id='baseline-1'), self.baseline)
        self.assertEqual(tuple(self.fx.db.iterdump()), before)
        with self.assertRaisesRegex(PersistenceError, 'active_superadmin_required'):
            approve_bootstrap(self.fx.db, actor_id='alice', environment='synthetic-local', expected_checkpoint=self.fx.journal.checkpoint)

    def test_bootstrap_cannot_be_reconstructed_from_browser_or_rebase_nonempty_journal(self):
        for permit in (asdict(self.permit), BootstrapPermit(self.permit.environment, self.permit.evidence), replace(self.permit)):
            with self.assertRaisesRegex(AnchorError, 'bootstrap_authority_required'):
                self.publisher.bootstrap(permit, publication_id='forged-baseline')
        self.fx.prepare()
        with self.assertRaisesRegex(AnchorError, 'bootstrap_requires_empty_journal'):
            approve_bootstrap(self.fx.db, actor_id='root', environment='synthetic-local', expected_checkpoint=self.fx.journal.checkpoint)

    def test_baseline_cannot_overwrite_current_publication(self):
        publish_prepared(self)
        with self.assertRaisesRegex(AnchorError, 'anchor_cas_conflict'):
            self.publisher.bootstrap(self.permit, publication_id='another-baseline')

    def test_reservation_preparation_and_commit_use_distinct_sequences(self):
        publish_prepared(self, reserve=True)
        self.fx.commit(); receipt = self.publisher.publish(capture(self), publication_id='committed-1', expected=self.expected)
        history = self.provider.read()
        self.assertEqual([p.state for p in history], ['baseline','reserved','prepared','committed'])
        self.assertEqual([p.publication_sequence for p in history], [1,2,3,4])
        self.assertEqual([p.control_sequence for p in history], [0,1,1,2])
        self.assertEqual([p.journal_sequence for p in history], [0,0,1,2])
        self.assertEqual(history[-1].receipt_sequence, 1)
        self.assertEqual(history[-1].checkpoint, self.fx.journal.checkpoint)
        self.assertEqual(receipt.witness, witness(history[-1]))
        self.assertIsNone(history[-1].file_evidence)

    def test_abort_publication_is_anchored_even_when_identity_checkpoint_does_not_advance(self):
        publish_prepared(self)
        previous = self.fx.journal.checkpoint
        self.fx.journal.abort(self.fx.operation, self.fx.plan, authorization=self.fx.authorization, reason='cancelled')
        self.publisher.publish(capture(self), publication_id='aborted-1', expected=self.expected)
        head = self.provider.read()[-1]
        self.assertEqual(head.state, 'aborted')
        self.assertEqual(head.checkpoint, previous)
        self.assertEqual(head.journal_sequence, 2)
        self.assertEqual(head.receipt_sequence, 0)
        self.assertIsNone(head.latest_receipt_id)
        self.assertNotEqual(head.journal_digest, self.provider.read()[-2].journal_digest)

    def test_idempotent_publication_returns_original_receipt_without_modifying_history(self):
        self.fx.prepare(); evidence = capture(self)
        first = self.publisher.publish(evidence, publication_id='prepared-1', expected=self.expected)
        before = self.provider.read()
        self.assertEqual(self.publisher.publish(evidence, publication_id='prepared-1', expected=self.expected), first)
        self.assertEqual(self.provider.read(), before)

    def test_same_publication_id_different_content_is_refused(self):
        self.fx.prepare(); evidence = capture(self)
        self.publisher.publish(evidence, publication_id='publication-1', expected=self.expected)
        with self.assertRaisesRegex(AnchorError, 'publication_id_content_conflict'):
            self.publisher.publish(evidence, publication_id='publication-1', expected=self.expected, reserve=True)

    def test_old_publication_replay_does_not_rewind_new_head(self):
        self.fx.prepare(); preparation = capture(self); old_expected = self.expected
        prepared = self.publisher.publish(preparation, publication_id='prepared-1', expected=old_expected)
        self.fx.commit(); committed = self.publisher.publish(capture(self), publication_id='committed-1', expected=prepared.witness)
        self.assertEqual(self.publisher.publish(preparation, publication_id='prepared-1', expected=old_expected), prepared)
        self.assertEqual(witness(self.provider.read()[-1]), committed.witness)

    def test_stale_expected_publication_cannot_create_a_new_update(self):
        self.fx.prepare(); evidence = capture(self)
        self.publisher.publish(evidence, publication_id='prepared-1', expected=self.expected)
        with self.assertRaisesRegex(AnchorError, 'anchor_cas_conflict'):
            self.publisher.publish(evidence, publication_id='stale-prepared', expected=self.expected)

    def test_environment_and_epoch_are_not_selected_by_numeric_revision(self):
        self.fx.prepare(); evidence = capture(self)
        with self.assertRaisesRegex(AnchorError, 'environment_mismatch'):
            AnchorPublisher('other-environment', self.provider).publish(evidence, publication_id='wrong', expected=self.expected)
        from services.email_recipient_repository import EmailRecipientRepository
        admin = EmailRecipientRepository(self.fx.db, self.fx.journal.checkpoint)
        admin.invalidate_continuity('other-epoch', actor_id='root', reason='synthetic-recovery')
        with self.assertRaisesRegex(AnchorError, 'epoch_mismatch'):
            self.publisher.publish(capture_sqlite_evidence(self.fx.db), publication_id='wrong-epoch', expected=self.expected)

    def test_publisher_rejects_dto_dict_and_modified_evidence(self):
        self.fx.prepare(); evidence = capture(self)
        for candidate in (asdict(evidence), replace(evidence), replace(evidence, checkpoint=replace(evidence.checkpoint, revision=999))):
            with self.assertRaisesRegex(AnchorError, 'evidence_untrusted'):
                self.publisher.publish(candidate, publication_id='forged', expected=self.expected)

    def test_provider_rejects_raw_publication_even_with_correct_digest(self):
        publication = self.provider.read()[0]
        with self.assertRaisesRegex(AnchorError, 'publication_untrusted'):
            self.provider.compare_and_swap(None, replace(publication))

    def test_missing_prepared_publication_cannot_be_skipped_to_publish_commit(self):
        self.fx.prepare(); self.fx.commit()
        with self.assertRaisesRegex(AnchorError, 'journal_publication_gap'):
            self.publisher.publish(capture(self), publication_id='skipped', expected=self.expected)

    def test_captured_evidence_is_immutable_and_does_not_write_sqlite(self):
        before = tuple(self.fx.db.iterdump())
        evidence = capture(self)
        self.assertEqual(tuple(self.fx.db.iterdump()), before)
        with self.assertRaises(FrozenInstanceError): evidence.ready = False
        with self.assertRaises(FrozenInstanceError): evidence.checkpoint.revision = 999

    def test_checkpoint_assertion_cannot_be_ignored_by_evidence_capture(self):
        checkpoint = replace(self.fx.journal.checkpoint, revision=999)
        with self.assertRaisesRegex(AnchorError, 'sqlite_checkpoint_mismatch'):
            capture_sqlite_evidence(self.fx.db, expected_checkpoint=checkpoint)

    def test_two_concurrent_publications_have_at_most_one_cas_winner(self):
        self.fx.prepare(); evidence = capture(self); barrier = threading.Barrier(2); results = []; lock = threading.Lock()
        def run(index):
            barrier.wait(timeout=5)
            try:
                self.publisher.publish(evidence, publication_id='prepared-' + str(index), expected=self.expected)
                outcome = 'published'
            except AnchorError as error: outcome = str(error)
            with lock: results.append(outcome)
        threads = [threading.Thread(target=run, args=(index,)) for index in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=10)
        self.assertEqual(sorted(results), ['anchor_cas_conflict', 'published'])
        self.assertEqual(len(self.provider.read()), 2)

    def test_publication_history_and_receipt_metadata_are_verifiable(self):
        publish_prepared(self); self.fx.commit()
        self.publisher.publish(capture(self), publication_id='committed-1', expected=self.expected)
        history = self.provider.read()
        self.assertEqual(verify_publications(history), history[-1])
        self.assertEqual(verify_witness(history, self.baseline.witness), history[-1])
        value = str([asdict(p) for p in history])
        for forbidden in ('alice@example.test', 'fictional-password-hash', 'fictional-session', 'Equipe 1'):
            self.assertNotIn(forbidden, value)


class FileAnchorTests(unittest.TestCase):
    def setUp(self): scenario(self, file=True)

    def reopen(self):
        root = Path(self.fx.temp.name)
        return TemporaryFileAnchorProvider(self.provider.directory, temporary_root=root)

    def test_file_provider_reopens_independent_history_and_idempotent_receipt(self):
        self.fx.prepare(); evidence = capture(self)
        receipt = self.publisher.publish(evidence, publication_id='prepared-1', expected=self.expected)
        reopened = self.reopen()
        publisher = AnchorPublisher('synthetic-local', reopened)
        self.assertEqual(publisher.publish(evidence, publication_id='prepared-1', expected=self.expected), receipt)
        self.assertEqual(witness(reopened.read()[-1]), receipt.witness)
        self.assertNotEqual(self.provider.path, self.fx.path)

    def test_file_provider_refuses_project_directory(self):
        root = Path(__file__).resolve().parents[1]
        with self.assertRaisesRegex(AnchorError, 'temporary_anchor_directory_required'):
            TemporaryFileAnchorProvider(root / 'forbidden-anchor', temporary_root=root)
        self.assertFalse((root / 'forbidden-anchor').exists())

    def test_write_and_file_sync_failures_preserve_old_head(self):
        self.fx.prepare(); evidence = capture(self); before = self.provider.path.read_bytes()
        with patch.object(self.provider, '_sync_file', side_effect=OSError('injected file sync')):
            with self.assertRaisesRegex(AnchorUnavailable, 'write_or_sync_failed'):
                self.publisher.publish(evidence, publication_id='prepared-1', expected=self.expected)
        self.assertEqual(self.provider.path.read_bytes(), before)
        self.assertFalse(list(self.provider.directory.glob('*.tmp')))
        self.publisher.publish(evidence, publication_id='prepared-1', expected=self.expected)
    def test_replace_failure_preserves_old_publication_and_can_be_retried(self):
        self.fx.prepare(); evidence = capture(self); before = self.provider.path.read_bytes()
        with patch('services.continuity_anchor.os.replace', side_effect=OSError('injected replace')):
            with self.assertRaises(AnchorUnavailable):
                self.publisher.publish(evidence, publication_id='prepared-1', expected=self.expected)
        self.assertEqual(self.provider.path.read_bytes(), before)
        self.publisher.publish(evidence, publication_id='prepared-1', expected=self.expected)

    def test_directory_sync_failure_after_replace_is_recoverable_by_identical_retry(self):
        self.fx.prepare(); evidence = capture(self)
        with patch.object(self.provider, '_sync_directory', side_effect=OSError('injected directory sync')):
            with self.assertRaises(AnchorUnavailable):
                self.publisher.publish(evidence, publication_id='prepared-1', expected=self.expected)
        self.assertEqual(self.provider.read()[-1].publication_id, 'prepared-1')
        publisher = AnchorPublisher('synthetic-local', self.reopen())
        receipt = publisher.publish(evidence, publication_id='prepared-1', expected=self.expected)
        self.assertEqual(len(self.provider.read()), 2)
        self.assertEqual(receipt.publication_id, 'prepared-1')

    def test_stale_lock_is_not_silently_removed_or_used_as_current_head(self):
        self.provider.lock_path.write_text('synthetic-stale-lock', encoding='utf-8')
        with self.assertRaises(AnchorUnavailable): self.provider.read()
        self.assertTrue(self.provider.lock_path.exists())

    def test_missing_head_with_orphan_staging_does_not_become_empty_baseline(self):
        root = Path(self.fx.temp.name)
        provider = TemporaryFileAnchorProvider(root / 'interrupted-anchor', temporary_root=root)
        (provider.directory / 'orphan.tmp').write_text('{}', encoding='utf-8')
        with self.assertRaisesRegex(AnchorUnavailable, 'incomplete_anchor_storage'): provider.read()
        with self.assertRaisesRegex(AnchorUnavailable, 'incomplete_anchor_storage'):
            AnchorPublisher('synthetic-local', provider).bootstrap(self.permit, publication_id='new-baseline')

    def test_corrupt_file_and_truncated_publication_chain_are_refused(self):
        publish_prepared(self)
        payload = json.loads(self.provider.path.read_text(encoding='utf-8'))
        payload['publications'] = payload['publications'][1:]
        self.provider.path.write_text(json.dumps(payload), encoding='utf-8')
        with self.assertRaises(AnchorError): self.provider.read()

    def test_old_file_snapshot_is_detected_against_independent_current_witness(self):
        old = self.provider.path.read_bytes(); publish_prepared(self)
        expected = self.expected
        self.provider.path.write_bytes(old)  # synthetic restoration only
        with self.assertRaisesRegex(AnchorError, 'anchor_rollback_detected'):
            verify_witness(self.provider.read(), expected)

    def test_false_digest_in_file_is_refused(self):
        payload = json.loads(self.provider.path.read_text(encoding='utf-8'))
        payload['publications'][0]['digest'] = '0' * 64
        self.provider.path.write_text(json.dumps(payload), encoding='utf-8')
        with self.assertRaisesRegex(AnchorError, 'publication_history_invalid'): self.provider.read()

    def test_two_independent_file_providers_do_not_silently_overwrite_same_version(self):
        self.fx.prepare(); evidence = capture(self); barrier = threading.Barrier(2); results = []; lock = threading.Lock()
        publishers = [AnchorPublisher('synthetic-local', self.reopen()) for _ in range(2)]
        def run(index):
            barrier.wait(timeout=5)
            try:
                publishers[index].publish(evidence, publication_id='file-prepared-' + str(index), expected=self.expected)
                outcome = 'published'
            except AnchorError as error: outcome = str(error)
            with lock: results.append(outcome)
        threads = [threading.Thread(target=run, args=(index,)) for index in range(2)]
        for thread in threads: thread.start()
        for thread in threads: thread.join(timeout=10)
        self.assertTrue(all(not thread.is_alive() for thread in threads))
        self.assertEqual(results.count('published'), 1)
        self.assertTrue(all(result in ('published', 'anchor_cas_conflict', 'anchor_busy_or_stale_lock') for result in results))
        self.assertEqual(len(self.provider.read()), 2)

    def test_temporary_file_creation_failure_keeps_previous_head(self):
        self.fx.prepare(); evidence = capture(self); before = self.provider.path.read_bytes()
        original = Path.open
        def fail_temporary(path, *args, **kwargs):
            if path.suffix == '.tmp': raise OSError('injected temporary creation failure')
            return original(path, *args, **kwargs)
        with patch('services.continuity_anchor.Path.open', new=fail_temporary):
            with self.assertRaises(AnchorUnavailable):
                self.publisher.publish(evidence, publication_id='prepared-1', expected=self.expected)
        self.assertEqual(self.provider.path.read_bytes(), before)
        self.publisher.publish(evidence, publication_id='prepared-1', expected=self.expected)

    def test_pre_sql_intents_and_pending_decision_survive_file_provider_reopen(self):
        reserve_authorized(self, 'prepare', 'intent-prepare')
        self.provider = self.reopen(); self.publisher = AnchorPublisher('synthetic-local', self.provider)
        self.assertEqual(self.provider.read()[-1].pending.phase, 'intent')
        self.fx.prepare()
        self.expected = self.publisher.publish(capture(self), publication_id='prepared-1', expected=self.expected).witness
        reserve_authorized(self, 'abort', 'intent-abort', reason='cancelled')
        self.provider = self.reopen(); self.publisher = AnchorPublisher('synthetic-local', self.provider)
        self.assertEqual(self.provider.read()[-1].pending.phase, 'abort_intent')
        self.fx.journal.abort(self.fx.operation, self.fx.plan, authorization=self.fx.authorization, reason='cancelled')
        self.expected = self.publisher.publish(capture(self), publication_id='aborted-1', expected=self.expected).witness
        self.assertEqual(self.reopen().read()[-1].state, 'aborted')


class IntentAnchorTests(unittest.TestCase):
    def setUp(self): scenario(self)

    def test_authorized_prepare_intent_precedes_sqlite_and_can_be_replayed(self):
        before = tuple(self.fx.db.iterdump()); previous = self.expected
        intent = reserve_authorized(self, 'prepare', 'intent-prepare')
        self.assertEqual(tuple(self.fx.db.iterdump()), before)
        self.assertEqual(self.provider.read()[-1].pending.phase, 'intent')
        self.assertEqual(self.provider.read()[-1].journal_sequence, 0)
        receipt = self.publisher.reserve_intent(intent, publication_id='intent-prepare', expected=previous)
        self.assertEqual(receipt.witness, self.expected)
        self.assertEqual(len(self.provider.read()), 2)

    def test_fully_reserved_commit_flow_retains_distinct_sequences(self):
        reserve_authorized(self, 'prepare', 'intent-prepare')
        self.fx.prepare()
        self.expected = self.publisher.publish(capture(self), publication_id='prepared-1', expected=self.expected).witness
        reserve_authorized(self, 'commit', 'intent-commit')
        self.assertEqual(self.provider.read()[-1].state, 'decision_pending')
        self.fx.commit()
        self.expected = self.publisher.publish(capture(self), publication_id='committed-1', expected=self.expected).witness
        history = self.provider.read()
        self.assertEqual([p.state for p in history], ['baseline','reserved','prepared','decision_pending','committed'])
        self.assertEqual([p.control_sequence for p in history], [0,1,1,2,2])
        self.assertEqual([p.journal_sequence for p in history], [0,0,1,1,2])
        self.assertEqual([p.publication_sequence for p in history], [1,2,3,4,5])

    def test_reserved_abort_is_bound_to_exact_reason_and_operation(self):
        publish_prepared(self)
        reserve_authorized(self, 'abort', 'intent-abort', reason='approved-cancel')
        self.fx.journal.abort(self.fx.operation, self.fx.plan, authorization=self.fx.authorization, reason='different-cancel')
        with self.assertRaisesRegex(AnchorError, 'reserved_decision_mismatch'):
            self.publisher.publish(capture(self), publication_id='aborted-1', expected=self.expected)

    def test_reserved_abort_cannot_publish_a_commit_instead(self):
        publish_prepared(self)
        reserve_authorized(self, 'abort', 'intent-abort', reason='approved-cancel')
        self.fx.commit()  # deliberate out-of-protocol P2 action, synthetic only
        with self.assertRaisesRegex(AnchorError, 'reserved_decision_mismatch'):
            self.publisher.publish(capture(self), publication_id='wrong-commit', expected=self.expected)

    def test_intent_requires_current_business_authority_and_live_p2_plan(self):
        self.fx.producer._authorize = lambda request: False
        with self.assertRaisesRegex(PersistenceError, 'business_operation_not_authorized'):
            reserve_authorized(self, 'prepare', 'forbidden-intent')
        self.assertEqual(len(self.provider.read()), 1)

    def test_browser_reconstructed_intent_is_not_a_technical_authority(self):
        intent = capture_authorized_intent(self.fx.journal, self.fx.before, self.fx.proposed,
            self.fx.operation, self.fx.plan, authorization=self.fx.authorization)
        for candidate in (asdict(intent), replace(intent)):
            with self.assertRaisesRegex(AnchorError, 'authorized_intent_required'):
                self.publisher.reserve_intent(candidate, publication_id='forged-intent', expected=self.expected)

    def test_evidence_authorization_callback_cannot_write_the_database(self):
        before = tuple(self.fx.db.iterdump())
        def wrong_callback(request):
            self.fx.db.execute("UPDATE account SET role='superadmin' WHERE user_id='alice'")
            return None
        self.fx.producer._authorize = wrong_callback
        with self.assertRaises(sqlite3.OperationalError):
            capture_authorized_intent(self.fx.journal, self.fx.before, self.fx.proposed,
                self.fx.operation, self.fx.plan, authorization=self.fx.authorization)
        self.assertEqual(tuple(self.fx.db.iterdump()), before)
        self.assertEqual(self.fx.db.execute('PRAGMA query_only').fetchone()[0], 0)

