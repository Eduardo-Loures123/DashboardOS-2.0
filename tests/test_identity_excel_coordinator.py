"""P4 exclusively fictional workbooks, accounts, SQLite and external anchor."""
from copy import deepcopy
from dataclasses import replace, FrozenInstanceError
from pathlib import Path
import sqlite3
import threading
import unittest
from unittest.mock import patch

from services.schema import SCHEMA
from services.identity_planner import ProposedOperation, RecordKey
from services.identity_operation_journal import IdentityOperationJournal, _history
from services.continuity_anchor import witness, AnchorError, FileEvidenceReferences, VerifiedFileProof, capture_sqlite_evidence
from services.identity_excel_coordinator import (
    IdentityExcelCoordinator, SyntheticWorkbookStore, CoordinationError, file_hash, read_receipts,
)
from services.identity_excel_recovery import assess_excel_recovery
from tests.test_continuity_anchor import scenario


class Interrupted(RuntimeError): pass


def setup(case, *, file=False):
    scenario(case, file=file)
    case.root = Path(case.fx.temp.name)
    case.before = {module: [{column: row.get(column, '') for column in columns} for row in case.fx.before[module]]
                   for module, columns in SCHEMA.items()}
    case.proposed = deepcopy(case.before); case.proposed['Funcionarios'][0]['equipe'] = 'T2'
    case.operation = case.fx.operation
    case.store = SyntheticWorkbookStore(case.root, case.root / 'current.xlsx')
    case.store.write(case.store.current, case.before)
    case.initial_hash = file_hash(case.store.current)
    case.coordinator = IdentityExcelCoordinator(case.store, case.fx.journal, case.publisher,
        expected_witness=case.expected, initial_file_hash=case.initial_hash)
    case.options = dict(actor_id='alice', authorization_ref='business-decision-1', policy_version='synthetic-policy-1')


def execute(case): return case.coordinator.execute(case.proposed, case.operation, **case.options)


def stop_at(case, boundary):
    def hook(current):
        if current == boundary: raise Interrupted(boundary)
    case.coordinator.fault_hook = hook
    with case.assertRaisesRegex(Interrupted, boundary): execute(case)
    case.coordinator.fault_hook = lambda _: None


def restart(case):
    # New connection, new journal/coordinator; retain only the independent witness.
    db = sqlite3.connect(case.fx.path); db.execute('PRAGMA foreign_keys=ON'); case.addCleanup(db.close)
    journal = IdentityOperationJournal(db, case.fx.original_checkpoint, case.fx.producer)
    case.coordinator = IdentityExcelCoordinator(SyntheticWorkbookStore(case.root, case.store.current), journal, case.publisher,
        expected_witness=case.coordinator.expected_witness, initial_file_hash=case.initial_hash)


class CoordinatorTests(unittest.TestCase):
    def setUp(self): setup(self)

    def test_end_to_end_schema_receipts_and_indirect_transfer(self):
        old = _history(self.fx.db); result = execute(self)
        current, meta = self.store.read(self.store.current)
        self.assertEqual(current, self.proposed); self.assertEqual(meta['operation_id'], self.operation.operation_id)
        self.assertEqual(file_hash(self.store.current), result.after_hash)
        intent, frames = read_receipts(self.store, self.operation.operation_id)
        self.assertEqual([f['phase'] for f in frames], ['intent','staged','replace_intent','replaced','complete'])
        self.assertTrue(self.store.paths(self.operation.operation_id)['backup'].exists())
        self.assertFalse(self.store.paths(self.operation.operation_id)['stage'].exists())
        self.assertEqual(result.publication_digest, self.provider.read()[-1].digest)
        self.assertEqual(self.provider.read()[-1].file_evidence.file_receipt_digest, frames[-1]['digest'])
        after = _history(self.fx.db)
        for code, module in [('O1','OrdensServico'),('A1','Acessos'),('R1','Renovacoes')]:
            old_id = next(i for i in old if i.key == RecordKey(module,code))
            new = next(i for i in after if i.key == old_id.key and i.present)
            self.assertEqual(new.incarnation, old_id.incarnation)
            self.assertEqual(new.generation, old_id.generation + 1)
            self.assertEqual(new.operational_generation, old_id.operational_generation)
        with self.assertRaises(FrozenInstanceError): result.after_hash = 'other'

    def test_repeated_request_returns_original_receipt_without_writes(self):
        first = execute(self); rows = tuple(self.fx.db.iterdump()); history = self.provider.read()
        self.assertEqual(execute(self), first)
        self.assertEqual(tuple(self.fx.db.iterdump()), rows); self.assertEqual(self.provider.read(), history)

    def test_same_id_different_content_refused(self):
        execute(self); self.proposed['Funcionarios'][0]['nome'] = 'Outro'
        with self.assertRaisesRegex(CoordinationError,'content_conflict'): execute(self)

    def test_two_instances_lock_excludes_second_and_preserves_winner(self):
        other_db = sqlite3.connect(self.fx.path, check_same_thread=False); other_db.execute('PRAGMA foreign_keys=ON')
        self.addCleanup(other_db.close)
        other_journal = IdentityOperationJournal(other_db,self.fx.original_checkpoint,self.fx.producer)
        other = IdentityExcelCoordinator(SyntheticWorkbookStore(self.root, self.store.current), other_journal,
            self.publisher, expected_witness=self.expected, initial_file_hash=self.initial_hash)
        errors = []
        def competing():
            try: other.execute(self.proposed, replace(self.operation, operation_id='other-operation'), **self.options)
            except Exception as exc: errors.append(str(exc))
        def hook(boundary):
            if boundary == 'before_replace':
                thread = threading.Thread(target=competing); thread.start(); thread.join(5)
                self.assertFalse(thread.is_alive())
        self.coordinator.fault_hook = hook; execute(self)
        self.assertEqual(errors, ['exclusive_lock_unavailable'])

    def test_external_edit_immediately_before_replace_not_overwritten(self):
        changed = deepcopy(self.before); changed['Funcionarios'][0]['nome'] = 'Edicao externa'
        def hook(boundary):
            if boundary == 'before_replace': self.store.write(self.store.current, changed)
        self.coordinator.fault_hook = hook
        with self.assertRaisesRegex(CoordinationError,'current_file_changed'): execute(self)
        self.assertEqual(self.store.read(self.store.current)[0], changed)
        self.assertEqual(self.fx.journal.checkpoint, self.fx.original_checkpoint)

    def test_existing_external_change_blocks_before_reservation(self):
        self.store.write(self.store.current, self.proposed)
        with self.assertRaisesRegex(CoordinationError,'current_file_changed'): execute(self)
        self.assertEqual(len(self.provider.read()), 1)

    def test_staging_incomplete_refused_before_replace(self):
        def hook(boundary):
            if boundary == 'after_staging_write': self.store.paths(self.operation.operation_id)['stage'].write_bytes(b'broken-xlsx')
        self.coordinator.fault_hook = hook
        with self.assertRaises(Exception): execute(self)
        self.assertEqual(file_hash(self.store.current), self.initial_hash)
        self.assertEqual(self.fx.journal.checkpoint, self.fx.original_checkpoint)

    def test_staging_hash_divergence_refused(self):
        def hook(boundary):
            if boundary == 'after_staging_verify':
                with self.store.paths(self.operation.operation_id)['stage'].open('ab') as stream: stream.write(b'changed')
        self.coordinator.fault_hook = hook
        with self.assertRaisesRegex(CoordinationError,'staging_hash_mismatch'): execute(self)
        self.assertEqual(file_hash(self.store.current), self.initial_hash)

    def test_failure_inside_prepare_leaves_reserved_without_sql_rows(self):
        with patch.object(self.fx.journal,'prepare',side_effect=Interrupted('prepare')):
            with self.assertRaises(Interrupted): execute(self)
        self.assertIsNone(self.coordinator._row(self.operation.operation_id))
        self.assertEqual(self.provider.read()[-1].state, 'reserved')
        restart(self); execute(self)

    def test_failure_inside_staging_can_retry_original_request(self):
        with patch.object(self.store,'write',side_effect=OSError('synthetic staging failure')):
            with self.assertRaises(OSError): execute(self)
        restart(self); execute(self)

    def test_failure_copying_backup_preserves_current_and_blocks_ambiguous_partial_copy(self):
        original = Path.open
        def failing_open(path, *args, **kwargs):
            if path.name == 'previous.xlsx' and args and args[0] == 'xb':
                path.write_bytes(b'partial')
                raise OSError('backup-failed')
            return original(path, *args, **kwargs)
        with patch.object(Path,'open',failing_open):
            with self.assertRaisesRegex(OSError,'backup-failed'): execute(self)
        self.assertEqual(file_hash(self.store.current),self.initial_hash)
        with self.assertRaisesRegex(CoordinationError,'backup_hash_mismatch'): execute(self)

    def test_directory_sync_failure_after_replace_can_resume(self):
        original = self.store.sync_directory
        def fail_current(directory):
            if Path(directory) == self.store.current.parent: raise OSError('directory-sync-failed')
            return original(directory)
        with patch.object(self.store,'sync_directory',side_effect=fail_current):
            with self.assertRaisesRegex(OSError,'directory-sync-failed'): execute(self)
        self.assertNotEqual(file_hash(self.store.current),self.initial_hash)
        self.assertEqual(self.coordinator._row(self.operation.operation_id)['status'],'prepared')
        restart(self); execute(self)

    def test_publication_provider_failure_after_sql_commit_can_resume(self):
        original = self.provider.compare_and_swap
        def fail_commit(expected, publication):
            if publication.state == 'committed': raise OSError('publication-failed')
            return original(expected, publication)
        with patch.object(self.provider,'compare_and_swap',side_effect=fail_commit):
            with self.assertRaisesRegex(OSError,'publication-failed'): execute(self)
        self.assertEqual(self.coordinator._row(self.operation.operation_id)['status'],'committed')
        restart(self); execute(self)

    def test_final_publication_failure_leaves_complete_local_receipt_for_resume(self):
        original = self.provider.compare_and_swap
        def fail_complete(expected, publication):
            if publication.file_evidence and publication.file_evidence.file_phase == 'complete': raise OSError('final-publication-failed')
            return original(expected, publication)
        with patch.object(self.provider,'compare_and_swap',side_effect=fail_complete):
            with self.assertRaisesRegex(OSError,'final-publication-failed'): execute(self)
        self.assertEqual(assess_excel_recovery(self.coordinator,self.operation.operation_id).status,'publication_pending')
        restart(self); execute(self)

    def test_failure_inside_replace_does_not_commit_sql(self):
        import services.identity_excel_coordinator as module
        original = module.os.replace
        def fail_stage(source, target):
            if Path(source).name == 'staging.xlsx': raise OSError('replace-failed')
            return original(source, target)
        with patch.object(module.os,'replace',side_effect=fail_stage):
            with self.assertRaisesRegex(OSError,'replace-failed'): execute(self)
        self.assertEqual(file_hash(self.store.current), self.initial_hash)
        self.assertEqual(self.coordinator._row(self.operation.operation_id)['status'],'prepared')
        restart(self); execute(self)

    def test_missing_stage_blocks_and_preserves_backup(self):
        stop_at(self,'before_replace'); paths = self.store.paths(self.operation.operation_id); paths['stage'].unlink()
        with self.assertRaises(OSError): execute(self)
        self.assertTrue(paths['backup'].exists()); self.assertEqual(file_hash(self.store.current),self.initial_hash)

    def test_missing_backup_blocks_after_replace_without_restoration(self):
        stop_at(self,'after_replace'); paths = self.store.paths(self.operation.operation_id); paths['backup'].unlink()
        current = file_hash(self.store.current)
        with self.assertRaises(OSError): execute(self)
        self.assertEqual(file_hash(self.store.current), current)

    def test_cancel_and_aborted_replay_are_idempotent(self):
        stop_at(self,'after_prepare')
        first = self.coordinator.cancel(self.proposed, self.operation, **self.options)
        self.assertEqual(self.coordinator.cancel(self.proposed, self.operation, **self.options),first)
        with self.assertRaisesRegex(CoordinationError,'aborted'): execute(self)
        self.assertEqual(file_hash(self.store.current),self.initial_hash)

    def test_cannot_cancel_after_replace_intention(self):
        stop_at(self,'before_replace')
        with self.assertRaisesRegex(CoordinationError,'cancellation_unsafe'):
            self.coordinator.cancel(self.proposed,self.operation,**self.options)

    def test_revoked_authorization_cannot_finish_interrupted_operation(self):
        stop_at(self,'after_replace')
        self.fx.producer._authorize = lambda _: False
        with self.assertRaisesRegex(ValueError,'business_operation_not_authorized'): execute(self)
        self.assertEqual(self.coordinator._row(self.operation.operation_id)['status'],'prepared')

    def test_replay_authorizer_cannot_write_sqlite(self):
        execute(self); original = self.fx.producer._authorize
        def bad_policy(request):
            self.fx.db.execute("UPDATE account SET state='blocked' WHERE user_id='alice'")
            return original(request)
        self.fx.producer._authorize = bad_policy
        with self.assertRaises(sqlite3.OperationalError): execute(self)
        self.assertEqual(self.fx.db.execute("SELECT state FROM account WHERE user_id='alice'").fetchone()[0],'active')

    def test_obsolete_checkpoint_never_replaces_file(self):
        stop_at(self,'after_backup')
        # A second trusted administrative synchronization is an unjournaled divergence.
        self.fx.db.execute('UPDATE email_identity_state SET revision=revision+1'); self.fx.db.commit()
        with self.assertRaisesRegex(ValueError,'divergent'): execute(self)
        self.assertEqual(file_hash(self.store.current),self.initial_hash)

    def test_upload_cannot_supply_identity_columns_or_unknown_sheet(self):
        for module, field in [('OrdensServico','incarnation'), ('Funcionarios','uuid')]:
            proposed = deepcopy(self.proposed); proposed[module][0][field] = 'untrusted-token'
            with self.assertRaisesRegex(CoordinationError,'columns_invalid'):
                self.coordinator.execute(proposed,self.operation,**self.options)
        proposed = deepcopy(self.proposed); proposed['_identity_receipt'] = []
        with self.assertRaisesRegex(CoordinationError,'sheets_invalid'):
            self.coordinator.execute(proposed,self.operation,**self.options)

    def test_missing_references_and_duplicate_codes_refused(self):
        for mutate in (lambda p: p['OrdensServico'][0].update(funcionario='absent'),
                       lambda p: p['OrdensServico'].append(deepcopy(p['OrdensServico'][0]))):
            proposed = deepcopy(self.proposed); mutate(proposed)
            with self.assertRaisesRegex(CoordinationError,'references_invalid'):
                self.coordinator.execute(proposed,self.operation,**self.options)

    def test_create_allocates_fresh_durable_token_and_response_retry_does_not_duplicate(self):
        self.proposed = deepcopy(self.before)
        row = deepcopy(self.before['OrdensServico'][0]); row['codigo'] = 'O3'; self.proposed['OrdensServico'].append(row)
        self.operation = ProposedOperation('create-3','create','OrdensServico','O3')
        first = execute(self); restart(self); self.assertEqual(execute(self),first)
        identities = [i for i in _history(self.coordinator.journal.db) if i.key == RecordKey('OrdensServico','O3')]
        self.assertEqual(len(identities),1); self.assertNotEqual(identities[0].incarnation,'O3')

    def test_import_new_preserves_absent_rows_and_upsert_requires_continuation(self):
        self.proposed = deepcopy(self.before)
        row = deepcopy(self.before['OrdensServico'][0]); row['codigo'] = 'O3'; self.proposed['OrdensServico'].append(row)
        self.operation = ProposedOperation('import-new','import',mode='new',targets=(RecordKey('OrdensServico','O3'),))
        execute(self)
        self.assertEqual(len(self.store.read(self.store.current)[0]['OrdensServico']),3)
        proposed = deepcopy(self.proposed); proposed['OrdensServico'][0]['descricao'] = 'Atualizada'
        operation = ProposedOperation('import-upsert','import',mode='upsert',targets=(RecordKey('OrdensServico','O1'),))
        with self.assertRaisesRegex(CoordinationError,'identity_plan_invalid'):
            self.coordinator.execute(proposed,operation,**self.options)

    def test_upsert_with_explicit_continuation_preserves_identity(self):
        old = _history(self.fx.db); self.proposed = deepcopy(self.before)
        self.proposed['OrdensServico'][0]['descricao'] = 'Atualizada'
        key = RecordKey('OrdensServico','O1')
        self.operation = ProposedOperation('import-upsert','import',mode='upsert',targets=(key,),continuations=(key,))
        execute(self); self.assertEqual(_history(self.fx.db),old)

    def test_old_completed_replay_after_later_operation_keeps_latest_file_and_checkpoint(self):
        first = execute(self); old_proposed = deepcopy(self.proposed); old_operation = self.operation
        self.proposed['OrdensServico'][0]['descricao'] = 'Edicao posterior'
        self.operation = ProposedOperation('second','update','OrdensServico','O1'); execute(self)
        latest_hash = file_hash(self.store.current); latest_checkpoint = self.fx.journal.checkpoint
        result = self.coordinator.execute(old_proposed,old_operation,**self.options)
        self.assertEqual(result,first); self.assertEqual(file_hash(self.store.current),latest_hash)
        self.assertEqual(self.fx.journal.checkpoint,latest_checkpoint)

    def test_path_escape_and_non_temporary_root_refused(self):
        with self.assertRaisesRegex(CoordinationError,'temporary_root_required'):
            SyntheticWorkbookStore(Path(__file__).resolve().parents[1], Path(__file__))
        with self.assertRaisesRegex(CoordinationError,'outside_sandbox'):
            self.store.path(self.root.parent / 'escape.xlsx')

    def test_unsealed_file_proof_cannot_be_published(self):
        stop_at(self,'before_replace'); intent,frames = read_receipts(self.store,self.operation.operation_id)
        with self.assertRaisesRegex(AnchorError,'file_evidence_untrusted'):
            self.publisher.publish_file(capture_sqlite_evidence(self.fx.db), VerifiedFileProof(self.coordinator._refs(intent,frames[-1]),'x'),
                publication_id='untrusted',expected=self.coordinator.expected_witness)


def _fault_test(boundary):
    def test(self):
        stop_at(self,boundary); restart(self); result = execute(self)
        self.assertEqual(result.after_hash,file_hash(self.store.current))
        self.assertEqual(self.coordinator._row(self.operation.operation_id)['status'],'committed')
        self.assertEqual(assess_excel_recovery(self.coordinator,self.operation.operation_id).status,'consistent')
    return test


for _boundary in ('before_reserve','after_reserve','before_prepare','after_prepare','before_backup','after_backup',
                  'before_staging','after_staging_write','after_staging_verify','before_replace','after_replace',
                  'before_directory_sync','after_sqlite_commit','after_commit_publication','after_complete_publication'):
    setattr(CoordinatorTests,'test_restart_after_' + _boundary,_fault_test(_boundary))
