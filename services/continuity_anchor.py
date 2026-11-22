"""P3 isolated publication protocol and test providers. No remote services or Excel.

Providers and caller-held witnesses form a trust boundary, not a cryptographic
defence against an owner who can replace every file and witness. TemporaryFile
is a test provider only. A seal rejects accidental browser DTO reconstruction;
it does not authenticate hostile Python running in the server process.
"""
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field, replace
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from threading import RLock
from typing import Protocol
import uuid

from .email_recipient_schema import PersistenceError, transaction
from .email_recipient_repository import IdentityCheckpoint, EmailRecipientRepository, _one, _many
from .identity_operation_journal import verify_journal_integrity, _history, _request_content
from .identity_planner import PlannedIdentity

_SEAL = object()


class AnchorError(ValueError):
    """Machine-readable refusal, without raw provider/SQLite data."""


class AnchorUnavailable(AnchorError):
    pass


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _digest(value):
    return hashlib.sha256(_json(value).encode()).hexdigest()


def _label(value):
    if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9._:/-]{1,250}', value):
        raise AnchorError('anchor_identifier_invalid')
    return value


def _sealed(value):
    object.__setattr__(value, '_seal', _SEAL)
    return value


@dataclass(frozen=True)
class JournalObservation:
    sequence: int
    operation_id: str
    status: str
    event_digest: str
    request_digest: str
    receipt_id: str
    expected_checkpoint: IdentityCheckpoint
    receipt_sequence: int | None = None
    receipt_digest: str | None = None
    receipt_previous_digest: str | None = None
    result_checkpoint: IdentityCheckpoint | None = None
    reason_digest: str | None = None


@dataclass(frozen=True)
class SQLiteEvidence:
    checkpoint: IdentityCheckpoint
    ready: bool
    events: tuple[JournalObservation, ...]
    prefix_digests: tuple[str, ...]  # index 0 is the empty journal
    identity_digest: str
    latest_operation_id: str | None
    latest_receipt_id: str | None
    receipt_sequence: int
    chain_digest: str | None
    _seal: object = field(default=None, init=False, repr=False, compare=False)

    @property
    def journal_sequence(self): return len(self.events)

    @property
    def journal_digest(self): return self.prefix_digests[-1]


def _checkpoint(row):
    value = IdentityCheckpoint(row['epoch'], row['revision'], row['source_revision'], row['source_token'])
    if (type(value.epoch) is not str or not value.epoch or type(value.revision) is not int or value.revision < 0
            or type(value.source_revision) is not int or value.source_revision < 0 or type(value.source_token) is not str):
        raise AnchorError('sqlite_checkpoint_invalid')
    return value


@contextmanager
def _read_transaction(db):
    """Prevent even a misconfigured authorization callback from writing SQLite."""
    if db.in_transaction: raise PersistenceError('idle_connection_required')
    previous = db.execute('PRAGMA query_only').fetchone()[0]
    db.execute('PRAGMA query_only=ON')
    try:
        with transaction(db, write=False): yield
    finally:
        db.execute('PRAGMA query_only=' + ('ON' if previous else 'OFF'))


def _capture(db):
    verify_journal_integrity(db)
    if db.execute('PRAGMA foreign_key_check').fetchone() is not None:
        raise AnchorError('sqlite_foreign_key_invalid')
    state = _one(db, 'SELECT * FROM email_identity_state WHERE slot=1')
    if state is None: raise AnchorError('sqlite_checkpoint_missing')
    checkpoint = _checkpoint(state)
    operations = {row['operation_id']: row for row in _many(db, 'SELECT * FROM email_identity_operations')}
    receipts = {row['operation_id']: row for row in _many(db, 'SELECT * FROM email_identity_receipts ORDER BY sequence')}
    observations = []; prefixes = [_digest([])]
    for sequence, event in enumerate(_many(db, 'SELECT * FROM email_identity_operation_events ORDER BY id'), 1):
        if event['id'] != sequence: raise AnchorError('journal_sequence_interrupted')
        operation = operations[event['operation_id']]
        expected = IdentityCheckpoint(operation['epoch'], operation['expected_revision'],
            operation['expected_source_revision'], operation['expected_source_token'])
        receipt = receipts.get(event['operation_id']) if event['status'] == 'committed' else None
        payload = json.loads(receipt['payload_json']) if receipt else None
        observation = JournalObservation(sequence, event['operation_id'], event['status'],
            _digest(dict(id=event['id'], operation_id=event['operation_id'], status=event['status'],
                occurred_at=event['occurred_at'], reason_digest=_digest(event['reason']),
                request_digest=operation['request_digest'], receipt_digest=receipt['digest'] if receipt else None)),
            operation['request_digest'], operation['receipt_id'], expected,
            receipt['sequence'] if receipt else None, receipt['digest'] if receipt else None,
            receipt['previous_digest'] if receipt else None, IdentityCheckpoint(**payload['checkpoint']) if payload else None,
            _digest(event['reason']) if event['status'] == 'aborted' else None)
        observations.append(observation)
        prefixes.append(_digest([prefixes[-1], asdict(observation)]))
    history = _history(db)
    latest = max(receipts.values(), key=lambda row: row['sequence']) if receipts else None
    if latest:
        payload = json.loads(latest['payload_json'])
        # A fresh receipt whose checkpoint is current must describe actual rows,
        # rather than an independently restored identity registry.
        if IdentityCheckpoint(**payload['checkpoint']) == checkpoint:
            plan = json.loads(operations[latest['operation_id']]['plan_json'])
            present = [asdict(PlannedIdentity(i.key, i.incarnation, i.generation, i.team_code,
                i.team_generation, i.operational_generation)) for i in sorted(history, key=lambda i: i.key) if i.present]
            if present != plan['resulting_identities']:
                raise AnchorError('sqlite_identity_receipt_mismatch')
    return _sealed(SQLiteEvidence(checkpoint, state['ready'] == 1, tuple(observations), tuple(prefixes),
        _digest([asdict(i) for i in history]), latest['operation_id'] if latest else None,
        latest['receipt_id'] if latest else None, latest['sequence'] if latest else 0, latest['digest'] if latest else None))


def capture_sqlite_evidence(db, *, expected_checkpoint=None):
    """Read-only consistent snapshot. It is evidence, never an automatic trusted baseline."""
    with _read_transaction(db):
        evidence = _capture(db)
        if expected_checkpoint is not None and evidence.checkpoint != expected_checkpoint:
            raise AnchorError('sqlite_checkpoint_mismatch')
        return evidence


@dataclass(frozen=True)
class AuthorizedIntent:
    action: str
    operation_id: str
    request_digest: str
    evidence: SQLiteEvidence
    reason_digest: str | None = None
    _seal: object = field(default=None, init=False, repr=False, compare=False)


def capture_authorized_intent(journal, before, proposed, operation, plan, *, authorization,
                              action='prepare', allocations=(), reason=None):
    """Authorize/read P2 preconditions before mutation; never calls prepare/commit/abort.

    The coordinator must reserve this fact externally BEFORE invoking the P2
    mutation explicitly. This is not permission to apply business state itself.
    """
    if action not in ('prepare','commit','abort'): raise AnchorError('intent_action_invalid')
    if action == 'abort': _label(reason)
    elif reason is not None: raise AnchorError('intent_reason_invalid')
    with _read_transaction(journal.db):
        journal._check()
        candidate = journal._candidate(before, proposed, operation, plan, authorization, allocations)
        row = _one(journal.db, 'SELECT * FROM email_identity_operations WHERE operation_id=?', (operation.operation_id,))
        if action == 'prepare':
            if row is not None: raise AnchorError('intent_operation_already_exists')
            journal._validate_plan(before, proposed, operation, plan, allocations)
            checkpoint = journal.checkpoint
            candidate.update(epoch=checkpoint.epoch, expected_revision=checkpoint.revision,
                expected_source_revision=checkpoint.source_revision, expected_source_token=checkpoint.source_token)
            request_digest = _digest(_request_content(candidate))
        else:
            if row is None or row['status'] != 'prepared': raise AnchorError('intent_prepared_operation_required')
            journal._compare(row, candidate)
            if action == 'commit': journal._validate_plan(before, proposed, operation, plan, allocations)
            request_digest = row['request_digest']
        return _sealed(AuthorizedIntent(action, operation.operation_id, request_digest,
            _capture(journal.db), _digest(reason) if action == 'abort' else None))


@dataclass(frozen=True)
class BootstrapPermit:
    environment: str
    evidence: SQLiteEvidence
    _seal: object = field(default=None, init=False, repr=False, compare=False)


def approve_bootstrap(db, *, actor_id, environment, expected_checkpoint):
    """Explicit administrative read-only approval, restricted to an empty P2 journal."""
    _label(environment)
    with _read_transaction(db):
        repository = EmailRecipientRepository(db, expected_checkpoint)
        repository._check(ready=True)
        repository._actor(actor_id)
        evidence = _capture(db)
        if evidence.journal_sequence or evidence.receipt_sequence:
            raise AnchorError('bootstrap_requires_empty_journal')
        return _sealed(BootstrapPermit(environment, evidence))


@dataclass(frozen=True)
class PendingOperation:
    operation_id: str
    request_digest: str
    receipt_id: str | None
    phase: str
    prepared_sequence: int
    prepared_digest: str | None
    reason_digest: str | None = None


@dataclass(frozen=True)
class FileEvidenceReferences:
    """P4 synthetic file proof. P3-only callers keep this evidence absent."""
    confirmed_excel_hash: str | None = None
    replace_operation_id: str | None = None
    staging_receipt: str | None = None
    previous_copy_ref: str | None = None
    operation_id: str | None = None
    proposed_excel_hash: str | None = None
    before_excel_hash: str | None = None
    plan_fingerprint: str | None = None
    file_phase: str | None = None
    file_receipt_digest: str | None = None
    previous_file_receipt_digest: str | None = None


@dataclass(frozen=True)
class VerifiedFileProof:
    references: FileEvidenceReferences
    request_digest: str
    _seal: object = field(default=None, init=False, repr=False, compare=False)


def _verified_file_proof(references, request_digest):
    """Internal P4 boundary: caller has checked the synthetic artifacts and receipt."""
    _verify_file_references(references)
    return _sealed(VerifiedFileProof(references, request_digest))


def _verify_file_references(refs):
    if type(refs) is not FileEvidenceReferences: raise AnchorError('file_evidence_untrusted')
    for value in (refs.confirmed_excel_hash, refs.before_excel_hash, refs.plan_fingerprint,
                  refs.staging_receipt, refs.file_receipt_digest):
        if type(value) is not str or not re.fullmatch('[0-9a-f]{64}', value): raise AnchorError('file_evidence_invalid')
    for value in (refs.operation_id, refs.replace_operation_id, refs.previous_copy_ref): _label(value)
    if refs.file_phase not in ('intent','staged','replace_intent','replaced','complete','cancelled'):
        raise AnchorError('file_phase_invalid')
    if refs.proposed_excel_hash is not None and not re.fullmatch('[0-9a-f]{64}', refs.proposed_excel_hash):
        raise AnchorError('file_evidence_invalid')
    if refs.file_phase in ('staged','replace_intent','replaced','complete') and refs.proposed_excel_hash is None:
        raise AnchorError('file_evidence_invalid')
    if refs.previous_file_receipt_digest is not None and not re.fullmatch('[0-9a-f]{64}', refs.previous_file_receipt_digest):
        raise AnchorError('file_evidence_invalid')
    expected = refs.proposed_excel_hash if refs.file_phase in ('replaced','complete') else refs.before_excel_hash
    if refs.confirmed_excel_hash != expected: raise AnchorError('file_confirmed_hash_invalid')


def _verify_file_transition(previous, current):
    if current is None:
        if previous is not None: raise AnchorError('file_evidence_removed')
        return
    _verify_file_references(current)
    if previous == current: return
    if previous is None or previous.operation_id != current.operation_id:
        if (current.file_phase != 'intent' or current.proposed_excel_hash is not None
                or current.previous_file_receipt_digest is not None or (previous is not None and
                (previous.file_phase not in ('complete','cancelled') or current.before_excel_hash != previous.confirmed_excel_hash))):
            raise AnchorError('file_operation_transition_invalid')
        return
    allowed = {'intent': ('staged','cancelled'), 'staged': ('replace_intent','cancelled'),
               'replace_intent': ('replaced',), 'replaced': ('complete',), 'complete': (), 'cancelled': ()}
    if current.file_phase not in allowed[previous.file_phase] or current.previous_file_receipt_digest != previous.file_receipt_digest:
        raise AnchorError('file_phase_transition_invalid')
    for name in ('before_excel_hash','operation_id','replace_operation_id','previous_copy_ref','staging_receipt','plan_fingerprint'):
        if getattr(previous, name) != getattr(current, name): raise AnchorError('file_binding_changed')
    if previous.proposed_excel_hash is not None and current.proposed_excel_hash != previous.proposed_excel_hash:
        raise AnchorError('file_binding_changed')


@dataclass(frozen=True)
class AnchorPublication:
    environment: str
    epoch: str
    control_sequence: int
    publication_sequence: int
    checkpoint: IdentityCheckpoint
    journal_sequence: int
    receipt_sequence: int
    latest_operation_id: str | None
    latest_receipt_id: str | None
    chain_digest: str | None
    journal_digest: str
    identity_digest: str
    state: str
    pending: PendingOperation | None
    previous_publication_id: str | None
    previous_digest: str | None
    publication_id: str
    file_evidence: FileEvidenceReferences | None
    digest: str
    _seal: object = field(default=None, init=False, repr=False, compare=False)


@dataclass(frozen=True)
class AnchorWitness:
    environment: str
    epoch: str
    publication_sequence: int
    publication_id: str
    digest: str


@dataclass(frozen=True)
class PublicationReceipt:
    publication_id: str
    digest: str
    publication_sequence: int
    previous_digest: str | None
    witness: AnchorWitness


def witness(publication):
    return AnchorWitness(publication.environment, publication.epoch, publication.publication_sequence,
                         publication.publication_id, publication.digest)


def _body(publication):
    value = asdict(publication)
    value.pop('_seal'); value.pop('digest')
    return value


def _make(**kwargs):
    value = AnchorPublication(**kwargs, digest='')
    return _sealed(replace(value, digest=_digest(_body(value))))


def _receipt(publication):
    return PublicationReceipt(publication.publication_id, publication.digest,
        publication.publication_sequence, publication.previous_digest, witness(publication))


def verify_publications(history):
    previous = None; identifiers = set()
    for sequence, publication in enumerate(history, 1):
        if type(publication) is not AnchorPublication: raise AnchorError('publication_untrusted')
        _label(publication.environment); _label(publication.publication_id)
        if type(publication.checkpoint) is not IdentityCheckpoint:
            raise AnchorError('publication_shape_invalid')
        _label(publication.epoch)
        counters = (publication.control_sequence, publication.publication_sequence,
                    publication.journal_sequence, publication.receipt_sequence,
                    publication.checkpoint.revision, publication.checkpoint.source_revision)
        if (any(type(value) is not int or value < 0 for value in counters)
                or type(publication.checkpoint) is not IdentityCheckpoint or publication.checkpoint.epoch != publication.epoch
                or type(publication.checkpoint.source_token) is not str):
            raise AnchorError('publication_shape_invalid')
        if (publication.publication_sequence != sequence or publication.publication_id in identifiers
                or publication.digest != _digest(_body(publication))):
            raise AnchorError('publication_history_invalid')
        if previous is None:
            if (publication.state != 'baseline' or publication.control_sequence != 0 or publication.journal_sequence != 0
                    or publication.previous_digest is not None or publication.previous_publication_id is not None
                    or publication.pending is not None or publication.receipt_sequence != 0):
                raise AnchorError('publication_baseline_invalid')
            if publication.file_evidence is not None: raise AnchorError('publication_baseline_invalid')
        else:
            if (publication.environment != previous.environment or publication.epoch != previous.epoch
                    or publication.previous_digest != previous.digest or publication.previous_publication_id != previous.publication_id):
                raise AnchorError('publication_predecessor_invalid')
            _verify_file_transition(previous.file_evidence, publication.file_evidence)
            if publication.state == previous.state and publication.file_evidence != previous.file_evidence:
                valid = (publication.journal_sequence == previous.journal_sequence and publication.checkpoint == previous.checkpoint
                    and publication.journal_digest == previous.journal_digest and publication.identity_digest == previous.identity_digest
                    and publication.chain_digest == previous.chain_digest and publication.pending == previous.pending
                    and publication.receipt_sequence == previous.receipt_sequence
                    and publication.latest_operation_id == previous.latest_operation_id
                    and publication.latest_receipt_id == previous.latest_receipt_id
                    and publication.control_sequence == previous.control_sequence + 1)
            elif publication.state == 'reserved':
                valid = (previous.state in ('baseline','committed','aborted') and publication.pending is not None
                    and publication.pending.phase in ('reserved','intent') and publication.journal_sequence == previous.journal_sequence
                    and publication.control_sequence == previous.control_sequence + 1)
            elif publication.state == 'prepared':
                valid = (previous.state in ('baseline','committed','aborted','reserved') and publication.pending is not None
                    and publication.pending.phase == 'prepared' and publication.journal_sequence == previous.journal_sequence + 1
                    and publication.control_sequence == previous.control_sequence + (0 if previous.state == 'reserved' else 1))
            elif publication.state == 'decision_pending':
                valid = (previous.state == 'prepared' and publication.pending is not None
                    and publication.pending.phase in ('commit_intent','abort_intent')
                    and publication.journal_sequence == previous.journal_sequence
                    and publication.control_sequence == previous.control_sequence + 1)
            else:
                valid = (publication.state in ('committed','aborted') and previous.state in ('prepared','decision_pending')
                    and publication.pending is None and publication.journal_sequence == previous.journal_sequence + 1
                    and publication.control_sequence == previous.control_sequence + (0 if previous.state == 'decision_pending' else 1))
            if not valid: raise AnchorError('publication_transition_invalid')
        identifiers.add(publication.publication_id); previous = publication
    return previous


def verify_witness(history, expected):
    head = verify_publications(history)
    if type(expected) is not AnchorWitness: raise AnchorError('trusted_witness_required')
    if type(expected.publication_sequence) is not int or expected.publication_sequence < 1:
        raise AnchorError('trusted_witness_required')
    if head is None: raise AnchorError('anchor_missing')
    if expected.environment != head.environment: raise AnchorError('anchor_environment_mismatch')
    if expected.epoch != head.epoch: raise AnchorError('anchor_epoch_mismatch')
    if expected.publication_sequence > len(history): raise AnchorError('anchor_rollback_detected')
    if expected.publication_sequence < 1 or witness(history[expected.publication_sequence - 1]) != expected:
        raise AnchorError('anchor_witness_divergent')
    return head


class AnchorProvider(Protocol):
    def read(self) -> tuple[AnchorPublication, ...]: ...
    def compare_and_swap(self, expected: AnchorWitness | None, publication: AnchorPublication) -> PublicationReceipt: ...


def _append(history, expected, publication):
    if type(publication) is not AnchorPublication or publication._seal is not _SEAL:
        raise AnchorError('publication_untrusted')
    head = verify_publications(history)
    for index, existing in enumerate(history):
        if existing.publication_id == publication.publication_id:
            if existing != publication: raise AnchorError('publication_id_content_conflict')
            if expected != (witness(history[index - 1]) if index else None):
                raise AnchorError('publication_predecessor_invalid')
            return history, _receipt(existing)
    if (head is None and expected is not None) or (head is not None and witness(head) != expected):
        raise AnchorError('anchor_cas_conflict')
    extended = history + (publication,)
    verify_publications(extended)
    return extended, _receipt(publication)


class MemoryAnchorProvider:
    def __init__(self):
        self._history = ()
        self._lock = RLock()

    def read(self):
        with self._lock:
            verify_publications(self._history)
            return self._history

    def compare_and_swap(self, expected, publication):
        with self._lock:
            self._history, result = _append(self._history, expected, publication)
            return result


class TemporaryFileAnchorProvider:
    """Test-only whole-history atomic container. No protection against full-machine rollback."""
    def __init__(self, directory, *, temporary_root):
        root = Path(temporary_root).resolve()
        self.directory = Path(directory).resolve()
        if not root.is_dir() or not root.is_relative_to(Path(tempfile.gettempdir()).resolve()) or not self.directory.is_relative_to(root):
            raise AnchorError('temporary_anchor_directory_required')
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path = self.directory / 'publications.json'
        self.lock_path = self.directory / 'anchor.lock'
        self.directory_sync_supported = os.name != 'nt' and hasattr(os, 'O_DIRECTORY')

    def _decode(self, value):
        if type(value) is not dict or set(value) != {'format','publications'} or value['format'] != 1 or type(value['publications']) is not list:
            raise AnchorError('anchor_file_invalid')
        history = []
        for item in value['publications']:
            item = dict(item)
            item['checkpoint'] = IdentityCheckpoint(**item['checkpoint'])
            item['pending'] = PendingOperation(**item['pending']) if item['pending'] is not None else None
            item['file_evidence'] = FileEvidenceReferences(**item['file_evidence']) if item['file_evidence'] is not None else None
            history.append(_sealed(AnchorPublication(**item)))
        verify_publications(tuple(history))
        return tuple(history)

    def _read_unlocked(self):
        try:
            if not self.path.exists():
                if any(self.directory.glob('*.tmp')):
                    raise AnchorUnavailable('incomplete_anchor_storage')
                return ()
            history = self._decode(json.loads(self.path.read_text(encoding='utf-8')))
            if not history: raise AnchorError('anchor_file_invalid')
            return history
        except AnchorError: raise
        except (OSError, ValueError, TypeError, KeyError): raise AnchorUnavailable('anchor_file_unreadable') from None

    def read(self):
        if self.lock_path.exists(): raise AnchorUnavailable('anchor_busy_or_stale_lock')
        return self._read_unlocked()

    @contextmanager
    def _locked(self):
        try: fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except OSError: raise AnchorUnavailable('anchor_busy_or_stale_lock') from None
        try: yield
        finally:
            os.close(fd)
            self.lock_path.unlink(missing_ok=True)

    def _sync_directory(self):
        if not self.directory_sync_supported: return False
        fd = os.open(self.directory, os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
        return True

    def _sync_file(self, stream):
        stream.flush(); os.fsync(stream.fileno())

    def _write(self, history):
        temporary = self.directory / (uuid.uuid4().hex + '.tmp')
        try:
            payload = dict(format=1, publications=[dict(_body(item), digest=item.digest) for item in history])
            with temporary.open('x', encoding='utf-8') as stream:
                stream.write(_json(payload)); self._sync_file(stream)
            os.replace(temporary, self.path)
            self._sync_directory()
        finally: temporary.unlink(missing_ok=True)

    def compare_and_swap(self, expected, publication):
        try:
            with self._locked():
                history = self._read_unlocked()
                extended, result = _append(history, expected, publication)
                if extended != history: self._write(extended)
                else:
                    with self.path.open('rb+') as stream: os.fsync(stream.fileno())
                    self._sync_directory()
                return result
        except AnchorError: raise
        except OSError: raise AnchorUnavailable('anchor_write_or_sync_failed') from None


class AnchorPublisher:
    """Trusted server-only publisher. Never invokes a P2 mutation or a recovery action."""
    def __init__(self, environment, provider):
        self.environment = _label(environment)
        self.provider = provider

    def bootstrap(self, permit, *, publication_id):
        if type(permit) is not BootstrapPermit or permit._seal is not _SEAL or permit.environment != self.environment:
            raise AnchorError('bootstrap_authority_required')
        evidence = permit.evidence
        if evidence._seal is not _SEAL or evidence.journal_sequence or not evidence.ready:
            raise AnchorError('bootstrap_evidence_invalid')
        publication = _make(environment=self.environment, epoch=evidence.checkpoint.epoch,
            control_sequence=0, publication_sequence=1, checkpoint=evidence.checkpoint, journal_sequence=0,
            receipt_sequence=0, latest_operation_id=None, latest_receipt_id=None, chain_digest=None,
            journal_digest=evidence.journal_digest, identity_digest=evidence.identity_digest, state='baseline',
            pending=None, previous_publication_id=None, previous_digest=None, publication_id=_label(publication_id), file_evidence=None)
        return self.provider.compare_and_swap(None, publication)

    def _build(self, previous, evidence, publication_id, *, reserve=False):
        if type(evidence) is not SQLiteEvidence or evidence._seal is not _SEAL: raise AnchorError('sqlite_evidence_untrusted')
        if evidence.checkpoint.epoch != previous.epoch: raise AnchorError('anchor_epoch_mismatch')
        if not evidence.ready: raise AnchorError('sqlite_continuity_unavailable')
        n = previous.journal_sequence
        if evidence.journal_sequence != n + 1: raise AnchorError('journal_publication_gap')
        if evidence.prefix_digests[n] != previous.journal_digest: raise AnchorError('journal_prefix_divergent')
        event = evidence.events[-1]
        pending = previous.pending
        if event.status == 'prepared':
            if previous.state not in ('baseline','committed','aborted','reserved'):
                raise AnchorError('pending_operation_conflict')
            candidate = PendingOperation(event.operation_id, event.request_digest, event.receipt_id,
                'reserved' if reserve else 'prepared', event.sequence, evidence.journal_digest)
            if previous.state == 'reserved':
                if reserve: raise AnchorError('pending_operation_conflict')
                if pending.phase == 'intent':
                    if (pending.operation_id, pending.request_digest, pending.prepared_sequence) != (
                            candidate.operation_id, candidate.request_digest, candidate.prepared_sequence):
                        raise AnchorError('pending_operation_conflict')
                elif pending != replace(candidate, phase='reserved'):
                    raise AnchorError('pending_operation_conflict')
            if (evidence.checkpoint != previous.checkpoint or event.expected_checkpoint != previous.checkpoint
                    or evidence.identity_digest != previous.identity_digest or evidence.chain_digest != previous.chain_digest
                    or evidence.receipt_sequence != previous.receipt_sequence):
                raise AnchorError('preparation_checkpoint_or_state_mismatch')
            state = 'reserved' if reserve else 'prepared'
            pending = candidate
            control = previous.control_sequence + (0 if previous.state == 'reserved' else 1)
        else:
            if reserve or previous.state not in ('prepared','decision_pending') or pending is None:
                raise AnchorError('prepared_publication_required')
            if (event.operation_id, event.request_digest, event.receipt_id) != (pending.operation_id, pending.request_digest, pending.receipt_id):
                raise AnchorError('pending_operation_conflict')
            if event.status == 'committed':
                if previous.state == 'decision_pending' and pending.phase != 'commit_intent':
                    raise AnchorError('reserved_decision_mismatch')
                if (event.result_checkpoint != evidence.checkpoint or event.expected_checkpoint != previous.checkpoint
                        or event.receipt_sequence != previous.receipt_sequence + 1 or event.receipt_previous_digest != previous.chain_digest
                        or evidence.chain_digest != event.receipt_digest or evidence.latest_receipt_id != event.receipt_id):
                    raise AnchorError('commit_receipt_or_checkpoint_mismatch')
            elif event.status == 'aborted':
                if previous.state == 'decision_pending' and (pending.phase != 'abort_intent' or pending.reason_digest != event.reason_digest):
                    raise AnchorError('reserved_decision_mismatch')
                if (evidence.checkpoint != previous.checkpoint or evidence.identity_digest != previous.identity_digest
                        or evidence.chain_digest != previous.chain_digest or evidence.receipt_sequence != previous.receipt_sequence):
                    raise AnchorError('abort_checkpoint_or_state_mismatch')
            else: raise AnchorError('journal_state_invalid')
            state = event.status; pending = None
            control = previous.control_sequence + (0 if previous.state == 'decision_pending' else 1)
        return _make(environment=self.environment, epoch=previous.epoch, control_sequence=control,
            publication_sequence=previous.publication_sequence + 1, checkpoint=evidence.checkpoint,
            journal_sequence=previous.journal_sequence if reserve else evidence.journal_sequence,
            receipt_sequence=evidence.receipt_sequence, latest_operation_id=evidence.latest_operation_id,
            latest_receipt_id=evidence.latest_receipt_id, chain_digest=evidence.chain_digest,
            journal_digest=previous.journal_digest if reserve else evidence.journal_digest,
            identity_digest=evidence.identity_digest, state=state, pending=pending,
            previous_publication_id=previous.publication_id, previous_digest=previous.digest, publication_id=_label(publication_id),
            file_evidence=previous.file_evidence)

    def _previous(self, publication_id, expected):
        history = self.provider.read()
        head = verify_witness(history, expected)
        if head.environment != self.environment: raise AnchorError('anchor_environment_mismatch')
        existing = next((p for p in history if p.publication_id == publication_id), None)
        if existing:
            if existing.publication_sequence == 1: raise AnchorError('publication_id_content_conflict')
            previous = history[existing.publication_sequence - 2]
            if witness(previous) != expected: raise AnchorError('publication_id_content_conflict')
        else:
            if witness(head) != expected: raise AnchorError('anchor_cas_conflict')
            previous = head
        return previous

    def reserve_intent(self, intent, *, publication_id, expected, file_proof=None):
        if type(intent) is not AuthorizedIntent or intent._seal is not _SEAL:
            raise AnchorError('authorized_intent_required')
        previous = self._previous(publication_id, expected)
        evidence = intent.evidence
        if (evidence._seal is not _SEAL or not evidence.ready or evidence.checkpoint.epoch != previous.epoch
                or evidence.checkpoint != previous.checkpoint or evidence.journal_sequence != previous.journal_sequence
                or evidence.journal_digest != previous.journal_digest or evidence.identity_digest != previous.identity_digest
                or evidence.chain_digest != previous.chain_digest or evidence.receipt_sequence != previous.receipt_sequence):
            raise AnchorError('intent_anchor_state_mismatch')
        if intent.action == 'prepare':
            if previous.pending is not None: raise AnchorError('pending_operation_conflict')
            state = 'reserved'
            pending = PendingOperation(intent.operation_id, intent.request_digest, None, 'intent', previous.journal_sequence + 1, None)
        else:
            if (previous.state != 'prepared' or previous.pending is None
                    or previous.pending.operation_id != intent.operation_id or previous.pending.request_digest != intent.request_digest):
                raise AnchorError('pending_operation_conflict')
            state = 'decision_pending'
            pending = replace(previous.pending, phase=intent.action + '_intent', reason_digest=intent.reason_digest)
        values = {name: getattr(previous, name) for name in _body(previous)}
        if file_proof is not None:
            if (type(file_proof) is not VerifiedFileProof or file_proof._seal is not _SEAL
                    or file_proof.request_digest != intent.request_digest
                    or file_proof.references.operation_id != intent.operation_id):
                raise AnchorError('file_evidence_untrusted')
            _verify_file_transition(previous.file_evidence, file_proof.references)
            values['file_evidence'] = file_proof.references
        publication = _make(**dict(values, control_sequence=previous.control_sequence + 1,
            publication_sequence=previous.publication_sequence + 1, state=state, pending=pending,
            previous_publication_id=previous.publication_id, previous_digest=previous.digest, publication_id=_label(publication_id)))
        return self.provider.compare_and_swap(expected, publication)

    def publish_file(self, evidence, file_proof, *, publication_id, expected):
        """P4 file-only control step, bound to unchanged verified SQLite state."""
        previous = self._previous(publication_id, expected)
        if type(evidence) is not SQLiteEvidence or evidence._seal is not _SEAL:
            raise AnchorError('sqlite_evidence_untrusted')
        if type(file_proof) is not VerifiedFileProof or file_proof._seal is not _SEAL:
            raise AnchorError('file_evidence_untrusted')
        refs = file_proof.references
        event = next((e for e in reversed(evidence.events) if e.operation_id == refs.operation_id), None)
        if event is None or event.request_digest != file_proof.request_digest:
            raise AnchorError('file_operation_mismatch')
        phase = refs.file_phase
        if ((phase in ('staged','replace_intent','replaced') and event.status != 'prepared')
                or (phase in ('replace_intent','replaced') and
                    (previous.state != 'decision_pending' or previous.pending is None or previous.pending.phase != 'commit_intent'))
                or (phase == 'complete' and (event.status != 'committed' or previous.state != 'committed'))
                or (phase == 'cancelled' and (event.status != 'aborted' or previous.state != 'aborted'))):
            raise AnchorError('file_sql_decision_mismatch')
        if (evidence.checkpoint != previous.checkpoint or evidence.journal_sequence != previous.journal_sequence
                or evidence.journal_digest != previous.journal_digest or evidence.identity_digest != previous.identity_digest
                or evidence.chain_digest != previous.chain_digest or not evidence.ready):
            raise AnchorError('file_sqlite_state_mismatch')
        if (evidence.receipt_sequence != previous.receipt_sequence or evidence.latest_operation_id != previous.latest_operation_id
                or evidence.latest_receipt_id != previous.latest_receipt_id):
            raise AnchorError('file_sqlite_state_mismatch')
        _verify_file_transition(previous.file_evidence, refs)
        values = {name: getattr(previous, name) for name in _body(previous)}
        publication = _make(**dict(values, file_evidence=refs, control_sequence=previous.control_sequence + 1,
            publication_sequence=previous.publication_sequence + 1, previous_publication_id=previous.publication_id,
            previous_digest=previous.digest, publication_id=_label(publication_id)))
        return self.provider.compare_and_swap(expected, publication)

    def publish(self, evidence, *, publication_id, expected, reserve=False):
        previous = self._previous(publication_id, expected)
        publication = self._build(previous, evidence, publication_id, reserve=reserve)
        return self.provider.compare_and_swap(expected, publication)
