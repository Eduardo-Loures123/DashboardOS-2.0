"""P4 read-only diagnosis. Execution/cancellation are explicit coordinator calls."""
from dataclasses import dataclass
from .identity_excel_coordinator import read_receipts, file_hash, CoordinationError
from .continuity_anchor import capture_sqlite_evidence, verify_witness, AnchorUnavailable, AnchorError


@dataclass(frozen=True)
class ExcelRecoveryAssessment:
    status: str
    reason: str
    allowed_actions: tuple[str, ...] = ()
    prohibited_actions: tuple[str, ...] = ('automatic_restore', 'automatic_commit', 'automatic_identity_recreation')
    requires_administrator: bool = False


def assess_excel_recovery(coordinator, operation_id):
    """Never takes a lock, rewrites a receipt, or updates the caller's witness."""
    def result(status, reason, allowed=(), admin=False):
        return ExcelRecoveryAssessment(status, reason, allowed, requires_administrator=admin)
    store = coordinator.store
    if store.lock_path.exists(): return result('insufficient_evidence','busy_or_stale_lock', admin=True)
    try:
        history = coordinator.publisher.provider.read()
        head = verify_witness(history, coordinator.expected_witness)
    except AnchorUnavailable: return result('anchor_unavailable','provider_unavailable', admin=True)
    except AnchorError as exc: return result('insufficient_evidence',str(exc), admin=True)
    try:
        intent, frames = read_receipts(store, operation_id)
        frame = frames[-1]; paths = store.paths(operation_id)
        actual = file_hash(store.current)
        evidence = capture_sqlite_evidence(coordinator.journal.db)
        old_file = actual == intent['before_hash']
        sql_old = evidence.journal_sequence < head.journal_sequence
        file_old = old_file and head.file_evidence is not None and head.file_evidence.confirmed_excel_hash != actual
        if sql_old:
            return result('file_and_database_rollback_detected' if file_old else 'database_rollback_detected', 'journal_behind_independent_anchor', admin=True)
        if file_old: return result('file_rollback_detected','file_behind_independent_anchor', admin=True)
        if (evidence.prefix_digests[head.journal_sequence] != head.journal_digest
                or evidence.journal_sequence > head.journal_sequence + 1):
            return result('divergent','journal_prefix_or_gap', admin=True)
        if evidence.journal_sequence == head.journal_sequence and (
                evidence.checkpoint != head.checkpoint or evidence.identity_digest != head.identity_digest
                or evidence.chain_digest != head.chain_digest):
            return result('divergent','sqlite_state_without_journal_proof', admin=True)
        publications = [p for p in history if p.file_evidence and p.file_evidence.operation_id == operation_id]
        references = [coordinator._refs(intent, f) for f in frames]
        if any(p.file_evidence not in references for p in publications):
            return result('insufficient_evidence','external_receipt_mismatch', admin=True)
        row = coordinator._row(operation_id)
        if row and row['status'] == 'aborted':
            return result('aborted','operation_terminal', ('explicit_cancel',) if frame['phase'] != 'cancelled' else ())
        if frame['phase'] != 'intent' or paths['backup'].exists():
            if file_hash(paths['backup']) != intent['before_hash']:
                return result('insufficient_evidence','backup_hash_mismatch', admin=True)
        if frame['after_hash'] is not None and paths['stage'].exists() and file_hash(paths['stage']) != frame['after_hash']:
            return result('insufficient_evidence','staging_hash_mismatch', admin=True)
        if frame['phase'] == 'complete':
            coordinator._validate_complete(frame, history)
            if head.file_evidence is None or actual != head.file_evidence.confirmed_excel_hash:
                return result('divergent','current_file_changed', admin=True)
            if head.file_evidence.operation_id == operation_id:
                coordinator._validate_artifacts(intent, frame, current_after=True)
            if not row or row['status'] != 'committed': return result('divergent','missing_sql_commit', admin=True)
            final = next((p for p in publications if p.publication_id == frame['publication_id']), None)
            return result('consistent' if final else 'publication_pending',
                          'completed_response_may_have_been_lost' if final else 'final_file_publication_missing', ('explicit_execute',))
        if actual not in (intent['before_hash'], frame['after_hash']):
            return result('divergent','unrecognized_current_file', admin=True)
        if frame['phase'] == 'intent':
            return result('staging_pending','same_request_and_current_authorization_required', ('explicit_execute','explicit_cancel') if row else ('explicit_execute',))
        if actual == intent['before_hash']:
            coordinator._validate_artifacts(intent, frame)
            return result('replacement_pending','verified_stage_waiting', ('explicit_execute',))
        coordinator._validate_artifacts(intent, frame, current_after=True)
        if row and row['status'] == 'committed':
            return result('sqlite_committed_publication_pending','verified_sql_receipt_waiting', ('explicit_execute',))
        if row and row['status'] == 'prepared':
            return result('file_replaced_sqlite_pending','explicit_reauthorization_required', ('explicit_execute',))
        return result('insufficient_evidence','file_without_sql_preparation', admin=True)
    except (OSError, ValueError, KeyError, TypeError, StopIteration):
        return result('insufficient_evidence','artifacts_missing_or_invalid', admin=True)
