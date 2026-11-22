"""P4 diagnoses never mutate SQLite, files, receipts or the external witness."""
import json
from pathlib import Path
import shutil
import sqlite3
import unittest
from unittest.mock import patch

from services.continuity_anchor import AnchorUnavailable
from services.identity_excel_coordinator import file_hash, read_receipts, CoordinationError
from services.identity_excel_recovery import assess_excel_recovery
from tests.test_identity_excel_coordinator import setup, execute, stop_at, restart


class RecoveryTests(unittest.TestCase):
    def setUp(self): setup(self)

    def assess(self): return assess_excel_recovery(self.coordinator,self.operation.operation_id)

    def test_consistent_readonly_assessment_and_response_lost(self):
        stop_at(self,'after_complete_publication')
        dump = tuple(self.fx.db.iterdump()); pubs = self.provider.read(); expected = self.coordinator.expected_witness
        files = {p: file_hash(p) for p in self.root.rglob('*') if p.is_file()}
        self.assertEqual(self.assess().status,'consistent')
        self.assertEqual(tuple(self.fx.db.iterdump()),dump); self.assertEqual(self.provider.read(),pubs)
        self.assertEqual(self.coordinator.expected_witness,expected)
        self.assertEqual({p:file_hash(p) for p in files},files)

    def test_staging_pending_after_reservation(self):
        stop_at(self,'after_reserve'); self.assertEqual(self.assess().status,'staging_pending')

    def test_replacement_pending(self):
        stop_at(self,'before_replace'); self.assertEqual(self.assess().status,'replacement_pending')

    def test_replaced_sqlite_pending(self):
        stop_at(self,'after_replace'); self.assertEqual(self.assess().status,'file_replaced_sqlite_pending')

    def test_sqlite_committed_publication_pending(self):
        stop_at(self,'after_sqlite_commit'); self.assertEqual(self.assess().status,'sqlite_committed_publication_pending')

    def test_missing_receipt_blocks_execution(self):
        execute(self); self.store.paths(self.operation.operation_id)['receipts'].unlink()
        self.assertEqual(self.assess().status,'insufficient_evidence')
        with self.assertRaisesRegex(CoordinationError,'receipt_missing'): execute(self)

    def test_tampered_receipt_blocks_execution(self):
        execute(self); path = self.store.paths(self.operation.operation_id)['receipts']
        frames = json.loads(path.read_text()); frames[-1]['after_hash'] = '0'*64; path.write_text(json.dumps(frames))
        self.assertEqual(self.assess().status,'insufficient_evidence')
        with self.assertRaisesRegex(CoordinationError,'receipt_invalid'): execute(self)

    def test_missing_backup_is_insufficient_even_with_valid_current_file(self):
        execute(self); self.store.paths(self.operation.operation_id)['backup'].unlink()
        self.assertEqual(self.assess().status,'insufficient_evidence')

    def test_missing_staging_before_replace_is_insufficient(self):
        stop_at(self,'before_replace'); self.store.paths(self.operation.operation_id)['stage'].unlink()
        self.assertEqual(self.assess().status,'insufficient_evidence')

    def test_consumed_staging_after_replace_is_expected(self):
        stop_at(self,'after_replace'); self.assertFalse(self.store.paths(self.operation.operation_id)['stage'].exists())
        self.assertEqual(self.assess().status,'file_replaced_sqlite_pending')

    def test_file_restored_to_old_version(self):
        execute(self); shutil.copyfile(self.store.paths(self.operation.operation_id)['backup'],self.store.current)
        self.assertEqual(self.assess().status,'file_rollback_detected')
        with self.assertRaisesRegex(CoordinationError,'current_file_changed'): execute(self)

    def backup_db(self):
        path = self.root / 'old.sqlite3'; db = sqlite3.connect(path); self.fx.db.backup(db); db.close(); return path

    def restore_db(self, path):
        db = sqlite3.connect(path); db.backup(self.fx.db); db.close()

    def test_old_database_detected_by_independent_anchor(self):
        backup = self.backup_db(); execute(self); self.restore_db(backup)
        self.assertEqual(self.assess().status,'database_rollback_detected')
        with self.assertRaisesRegex(CoordinationError,'database_rollback'): execute(self)

    def test_old_database_and_old_file_detected_together(self):
        backup = self.backup_db(); execute(self); self.restore_db(backup)
        shutil.copyfile(self.store.paths(self.operation.operation_id)['backup'],self.store.current)
        self.assertEqual(self.assess().status,'file_and_database_rollback_detected')

    def test_old_anchor_cannot_override_retained_witness(self):
        old = self.provider.read(); execute(self); self.provider._history = old
        self.assertEqual(self.assess().reason,'anchor_rollback_detected')
        with self.assertRaisesRegex(ValueError,'anchor_rollback_detected'): execute(self)

    def test_anchor_unavailable_blocks_recovery(self):
        stop_at(self,'after_replace')
        with patch.object(self.provider,'read',side_effect=AnchorUnavailable('offline')):
            self.assertEqual(self.assess().status,'anchor_unavailable')
            with self.assertRaises(AnchorUnavailable): execute(self)

    def test_external_edit_is_divergent_and_never_automatically_restored(self):
        stop_at(self,'after_replace'); self.store.current.write_bytes(b'external-change'); current = file_hash(self.store.current)
        assessment = self.assess()
        self.assertEqual(assessment.status,'divergent'); self.assertFalse(assessment.allowed_actions)
        self.assertEqual(file_hash(self.store.current),current)

    def test_stale_lock_requires_explicit_administration(self):
        self.store.lock_path.write_text('simulated-crash')
        self.assertEqual(self.assess().reason,'busy_or_stale_lock')
        with self.assertRaisesRegex(CoordinationError,'exclusive_lock_unavailable'): execute(self)
        self.assertTrue(self.store.lock_path.exists())

    def test_persistent_file_anchor_survives_restart(self):
        # Independent fixture with the P3 durable temporary provider.
        case = unittest.TestCase(); setup(case,file=True); self.addCleanup(case.doCleanups)
        stop_at(case,'after_replace'); restart(case); execute(case)
        self.assertEqual(assess_excel_recovery(case.coordinator,case.operation.operation_id).status,'consistent')
