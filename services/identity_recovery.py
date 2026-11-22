"""P3 read-only classification. Never replays SQLite, publishes or resets an epoch."""
from dataclasses import dataclass

from .continuity_anchor import (
    AnchorError, AnchorUnavailable, AnchorPublisher, SQLiteEvidence, _SEAL,
    verify_witness, witness,
)


@dataclass(frozen=True)
class RecoveryAssessment:
    status: str
    evidence_used: tuple[str, ...]
    missing_evidence: tuple[str, ...]
    allowed_actions: tuple[str, ...]
    prohibited_actions: tuple[str, ...]
    requires_administrative_approval: bool
    reason: str


_FORBIDDEN = ('automatic_sqlite_mutation', 'automatic_business_replay', 'automatic_baseline_reset',
              'overwrite_anchor_without_cas', 'restore_historical_permissions')


def _result(status, reason, *, used=(), missing=(), allowed=(), admin=True):
    return RecoveryAssessment(status, tuple(used), tuple(missing), tuple(allowed), _FORBIDDEN, admin, reason)


def assess_recovery(provider, *, environment, expected_witness, evidence, evidence_error=None):
    """Accept captured SQLite facts + provider history and a caller-trusted witness.

    No 'recoverable' status executes anything. For an explicitly chosen repair,
    the trusted caller must invoke publication separately using current proofs.
    If capture_sqlite_evidence failed, pass None and retain its safe error code
    in the caller's diagnostic context; do not manufacture replacement evidence.
    """
    try:
        history = provider.read()
        head = verify_witness(history, expected_witness)
        if head.environment != environment:
            return _result('divergent', 'anchor_environment_mismatch', used=('provider_history', 'trusted_witness'))
    except (AnchorUnavailable, OSError):
        return _result('anchor_unavailable', 'anchor_provider_unavailable', missing=('available_anchor',), allowed=('retry_read_only',), admin=False)
    except AnchorError as error:
        code = str(error)
        if code == 'anchor_rollback_detected':
            return _result('rollback_detected', code, used=('trusted_witness',), missing=('current_publication_history',))
        status = 'insufficient_evidence' if code in ('anchor_missing', 'trusted_witness_required') else 'divergent'
        return _result(status, code, used=('provider_history',), missing=('verified_current_anchor',))
    used = ('provider_history', 'trusted_witness', 'sqlite_journal', 'sqlite_receipts', 'sqlite_checkpoint')
    if type(evidence) is not SQLiteEvidence or evidence._seal is not _SEAL:
        errors = {'committed_receipt_missing', 'receipt_chain_invalid', 'operation_payload_digest_mismatch',
                  'operation_history_mismatch', 'journal_sequence_interrupted', 'sqlite_identity_receipt_mismatch'}
        reason = evidence_error if evidence_error in errors else 'verified_sqlite_evidence_required'
        missing = ('verified_sqlite_evidence', 'committed_receipt') if reason == 'committed_receipt_missing' else ('verified_sqlite_evidence',)
        return _result('insufficient_evidence', reason, used=used[:2], missing=missing)
    if evidence.checkpoint.epoch != head.epoch:
        return _result('divergent', 'sqlite_epoch_mismatch', used=used)
    if not evidence.ready:
        return _result('divergent', 'sqlite_continuity_unavailable', used=used)
    n = head.journal_sequence
    if evidence.journal_sequence < n:
        return _result('rollback_detected', 'sqlite_journal_behind_anchor', used=used)
    if evidence.prefix_digests[n] != head.journal_digest:
        return _result('divergent', 'sqlite_journal_prefix_mismatch', used=used)
    if evidence.journal_sequence == n:
        if (evidence.checkpoint.revision < head.checkpoint.revision
                or evidence.checkpoint.source_revision < head.checkpoint.source_revision):
            return _result('rollback_detected', 'sqlite_checkpoint_behind_anchor', used=used)
        if head.state == 'reserved':
            if head.pending.phase == 'intent':
                return _result('insufficient_evidence', 'reserved_intent_without_prepared_sqlite_evidence', used=used,
                               missing=('prepared_sqlite_operation', 'authorized_recovery_decision'))
            return _result('rollback_detected', 'reserved_preparation_missing_in_sqlite', used=used)
        if head.state == 'decision_pending':
            return _result('insufficient_evidence', 'reserved_decision_without_terminal_sqlite_evidence', used=used,
                           missing=('terminal_sqlite_operation', 'authorized_recovery_decision'))
        matches = (evidence.checkpoint == head.checkpoint and evidence.chain_digest == head.chain_digest
                   and evidence.receipt_sequence == head.receipt_sequence and evidence.identity_digest == head.identity_digest
                   and evidence.latest_operation_id == head.latest_operation_id and evidence.latest_receipt_id == head.latest_receipt_id)
        if matches:
            action = 'await_authorized_p2_decision' if head.pending else 'use_confirmed_sqlite_snapshot'
            return _result('consistent', 'sqlite_and_anchor_match', used=used, allowed=(action,), admin=False)
        if (evidence.checkpoint.revision < head.checkpoint.revision
                or evidence.checkpoint.source_revision < head.checkpoint.source_revision):
            return _result('rollback_detected', 'sqlite_checkpoint_behind_anchor', used=used)
        return _result('divergent', 'sqlite_state_changed_without_anchored_journal_transition', used=used)
    if evidence.journal_sequence != n + 1:
        return _result('insufficient_evidence', 'unpublished_intermediate_states', used=used,
                       missing=('verified_intermediate_publications',))
    try:
        publication = AnchorPublisher(environment, provider)._build(head, evidence, 'assessment-only')
    except AnchorError as error:
        return _result('insufficient_evidence', str(error), used=used, missing=('valid_next_publication_transition',))
    if publication.state == 'aborted':
        return _result('recoverable_abort', 'sqlite_abort_proven_not_published', used=used,
                       allowed=('explicitly_publish_proven_abort',), admin=False)
    if publication.state == 'committed':
        return _result('recoverable_publish', 'sqlite_commit_proven_not_published', used=used,
                       allowed=('explicitly_publish_existing_commit_receipt',), admin=False)
    if head.state == 'reserved':
        return _result('recoverable_publish', 'reserved_preparation_proven_in_sqlite', used=used,
                       allowed=('explicitly_publish_preparation',), admin=False)
    return _result('pending_publication', 'sqlite_preparation_not_published', used=used,
                   allowed=('explicitly_reserve_or_publish_preparation',), admin=False)
