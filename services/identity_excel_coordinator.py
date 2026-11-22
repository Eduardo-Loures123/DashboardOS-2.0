"""P4 synthetic-only coordinator. Explicit dependencies; no operational imports.

This is a recoverable protocol, NOT a transaction across XLSX, SQLite and anchor.
The caller supplies a retained independent witness and a trusted authorization
producer. Local receipt digests detect corruption; they are not authorization.
"""
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path
import tempfile
import uuid

from openpyxl import Workbook, load_workbook
from .schema import SCHEMA
from . import identity_planner as p1
from .identity_operation_journal import _history
from .email_recipient_repository import _one
from .continuity_anchor import (
    FileEvidenceReferences, _verified_file_proof, _json, _digest,
    capture_sqlite_evidence, capture_authorized_intent, verify_witness, witness,
    _read_transaction,
)


class CoordinationError(ValueError):
    """Technical refusal; never contains operational rows."""


def file_hash(path):
    with Path(path).open('rb') as stream:
        digest = hashlib.sha256()
        for block in iter(lambda: stream.read(65536), b''): digest.update(block)
    return digest.hexdigest()


def inventory_digest(inventory):
    return _digest({module: sorted(rows, key=lambda r: r['codigo']) for module, rows in inventory.items()})


def validate_inventory(inventory):
    if type(inventory) is not dict or set(inventory) != set(SCHEMA):
        raise CoordinationError('workbook_sheets_invalid')
    for module, rows in inventory.items():
        if type(rows) not in (list, tuple): raise CoordinationError('workbook_rows_invalid')
        for row in rows:
            if type(row) is not dict or set(row) != set(SCHEMA[module]) or any(type(v) is not str for v in row.values()):
                raise CoordinationError('workbook_columns_invalid')
    # P1 validates unique visible codes and all five modules' foreign references.
    try: p1._inventory(inventory)
    except (p1._Refusal, ValueError, TypeError, KeyError): raise CoordinationError('workbook_references_invalid') from None


class SyntheticWorkbookStore:
    """Only a caller-created temporary sandbox; never accepts project paths."""
    def __init__(self, root, current):
        self.root = Path(root).resolve()
        raw = Path(current)
        if not self.root.is_dir() or not self.root.is_relative_to(Path(tempfile.gettempdir()).resolve()):
            raise CoordinationError('temporary_root_required')
        self.current = self.path(raw)
        self.lock_path = self.current.with_suffix(self.current.suffix + '.identity.lock')
        self.directory_sync_supported = os.name != 'nt' and hasattr(os, 'O_DIRECTORY')

    def path(self, value):
        raw = Path(value)
        absolute = raw.absolute()
        if any(p.is_symlink() for p in (absolute, *absolute.parents)):
            raise CoordinationError('symlink_forbidden')
        resolved = raw.resolve()
        if not resolved.is_relative_to(self.root): raise CoordinationError('path_outside_sandbox')
        return resolved

    def paths(self, operation_id):
        token = hashlib.sha256(operation_id.encode()).hexdigest()
        directory = self.path(self.root / ('operation-' + token))
        return {name: self.path(directory / filename) for name, filename in
                (('intent','intent.json'),('receipts','receipts.json'),('stage','staging.xlsx'),('backup','previous.xlsx'))}

    @contextmanager
    def locked(self):
        self.path(self.current); self.path(self.lock_path)
        try: fd = os.open(self.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except OSError: raise CoordinationError('exclusive_lock_unavailable') from None
        try: yield
        finally:
            os.close(fd)
            self.lock_path.unlink(missing_ok=True)

    def sync_directory(self, directory):
        if not self.directory_sync_supported: return False
        fd = os.open(self.path(directory), os.O_RDONLY | os.O_DIRECTORY)
        try: os.fsync(fd)
        finally: os.close(fd)
        return True

    def sync_file(self, path):
        with self.path(path).open('rb+') as stream: os.fsync(stream.fileno())

    def write_json(self, path, value):
        path = self.path(path); temporary = self.path(path.with_suffix('.tmp'))
        with temporary.open('w', encoding='utf-8') as stream:
            stream.write(_json(value)); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary, path); self.sync_directory(path.parent)

    def read(self, path):
        path = self.path(path)
        book = load_workbook(path, read_only=True, data_only=False)
        try:
            if set(book.sheetnames) not in (set(SCHEMA), set(SCHEMA) | {'_identity_receipt'}):
                raise CoordinationError('workbook_sheets_invalid')
            inventory = {}
            for module, columns in SCHEMA.items():
                rows = list(book[module].iter_rows())
                if not rows or [c.value for c in rows[0]] != list(columns):
                    raise CoordinationError('workbook_columns_invalid')
                inventory[module] = []
                for cells in rows[1:]:
                    if len(cells) != len(columns) or any(c.data_type == 'f' for c in cells):
                        raise CoordinationError('workbook_cell_invalid')
                    values = [c.value if c.value is not None else '' for c in cells]
                    if any(type(v) is not str for v in values): raise CoordinationError('workbook_cell_invalid')
                    inventory[module].append(dict(zip(columns, values)))
            metadata = {}
            if '_identity_receipt' in book.sheetnames:
                for key, value in book['_identity_receipt'].iter_rows(values_only=True):
                    if key in metadata or type(key) is not str or type(value) is not str:
                        raise CoordinationError('workbook_metadata_invalid')
                    metadata[key] = value
            validate_inventory(inventory)
            return inventory, metadata
        finally: book.close()

    def write(self, path, inventory, metadata=None):
        validate_inventory(inventory)
        book = Workbook(); book.remove(book.active)
        try:
            for module, columns in SCHEMA.items():
                sheet = book.create_sheet(module); sheet.append(list(columns))
                for row in inventory[module]:
                    sheet.append([row[c] for c in columns])
                    for cell in sheet[sheet.max_row]: cell.data_type = 's'
            if metadata:
                sheet = book.create_sheet('_identity_receipt'); sheet.sheet_state = 'veryHidden'
                for key, value in sorted(metadata.items()): sheet.append([key, value])
            book.save(self.path(path)); self.sync_file(path)
        finally: book.close()


def _operation(value):
    value = dict(value)
    for name in ('targets','continuations'):
        value[name] = tuple(p1.RecordKey(**key) for key in value[name])
    return p1.ProposedOperation(**value)


def _recipe(intent):
    history = tuple(p1.DurableIdentity(**dict(item, key=p1.RecordKey(**item['key']))) for item in intent['history'])
    allocations = tuple(p1.TokenAllocation(p1.RecordKey(**item['key']), item['token']) for item in intent['allocations'])
    return _operation(intent['operation']), history, allocations, p1.PlanningContext(**intent['context'])


def read_receipts(store, operation_id):
    """Read and validate the local chain; external binding is checked separately."""
    paths = store.paths(operation_id)
    try:
        intent = json.loads(paths['intent'].read_text(encoding='utf-8'))
        frames = json.loads(paths['receipts'].read_text(encoding='utf-8'))
        body = dict(intent); body.pop('digest')
        if intent['digest'] != _digest(body) or intent['operation']['operation_id'] != operation_id or not frames:
            raise CoordinationError('receipt_invalid')
        previous = None
        edges = {None: ('intent',), 'intent': ('staged','cancelled'), 'staged': ('replace_intent','cancelled'),
                 'replace_intent': ('replaced',), 'replaced': ('complete',)}
        for n, frame in enumerate(frames, 1):
            content = dict(frame); content.pop('digest')
            if (frame['digest'] != _digest(content) or frame['sequence'] != n or frame['intent_digest'] != intent['digest']
                    or frame['previous_digest'] != (previous['digest'] if previous else None)
                    or frame['phase'] not in edges.get(previous['phase'] if previous else None, ())):
                raise CoordinationError('receipt_invalid')
            if (frame['operation_id'] != operation_id or frame['before_hash'] != intent['before_hash']
                    or any(frame[name] != intent[name] for name in ('staging_id','backup_id','replace_id'))):
                raise CoordinationError('receipt_binding_invalid')
            if previous and previous['after_hash'] is not None and frame['after_hash'] != previous['after_hash']:
                raise CoordinationError('receipt_binding_invalid')
            previous = frame
        return intent, frames
    except CoordinationError: raise
    except (OSError, ValueError, KeyError, TypeError): raise CoordinationError('receipt_missing_or_invalid') from None


@dataclass(frozen=True)
class CoordinatedReceipt:
    operation_id: str
    before_hash: str
    after_hash: str
    staging_id: str
    backup_id: str
    replace_id: str
    file_receipt_digest: str
    sqlite_receipt_id: str
    sqlite_receipt_digest: str
    publication_id: str
    publication_digest: str


class IdentityExcelCoordinator:
    def __init__(self, store, journal, publisher, *, expected_witness, initial_file_hash, fault_hook=None):
        self.store = store; self.journal = journal; self.publisher = publisher
        self.expected_witness = expected_witness; self.initial_file_hash = initial_file_hash
        self.fault_hook = fault_hook or (lambda boundary: None)

    def _head(self):
        history = self.publisher.provider.read()
        head = verify_witness(history, self.expected_witness)
        if head.environment != self.publisher.environment: raise CoordinationError('environment_mismatch')
        self.expected_witness = witness(head)
        return history, head

    def _row(self, operation_id):
        return _one(self.journal.db, 'SELECT * FROM email_identity_operations WHERE operation_id=?', (operation_id,))

    def _frame(self, intent, frames, phase, after_hash=None, sql=None, sql_publication=None):
        frame = dict(sequence=len(frames)+1, previous_digest=frames[-1]['digest'] if frames else None,
            intent_digest=intent['digest'], operation_id=intent['operation']['operation_id'], phase=phase,
            before_hash=intent['before_hash'], after_hash=after_hash, staging_id=intent['staging_id'],
            backup_id=intent['backup_id'], replace_id=intent['replace_id'],
            sqlite_receipt_id=sql['receipt_id'] if sql else None,
            sqlite_receipt_digest=sql['digest'] if sql else None,
            sqlite_publication_id=sql_publication.publication_id if sql_publication else None,
            sqlite_publication_digest=sql_publication.digest if sql_publication else None,
            publication_id=self._pubid(intent, phase))
        frame['digest'] = _digest(frame)
        self.store.write_json(self.store.paths(frame['operation_id'])['receipts'], frames + [frame])
        frames.append(frame)
        return frame

    def _pubid(self, intent, step): return 'p4-' + intent['replace_id'] + '-' + step

    def _refs(self, intent, frame):
        return FileEvidenceReferences(confirmed_excel_hash=frame['after_hash'] if frame['phase'] in ('replaced','complete') else intent['before_hash'],
            replace_operation_id=intent['replace_id'], staging_receipt=intent['digest'], previous_copy_ref=intent['backup_id'],
            operation_id=intent['operation']['operation_id'], proposed_excel_hash=frame['after_hash'], before_excel_hash=intent['before_hash'],
            plan_fingerprint=intent['plan_fingerprint'], file_phase=frame['phase'], file_receipt_digest=frame['digest'],
            previous_file_receipt_digest=frame['previous_digest'])

    def _publish_frame(self, intent, frame, request_digest):
        history, head = self._head()
        if frame['phase'] == 'complete': self._validate_complete(frame, history)
        existing = next((p for p in history if p.publication_id == frame['publication_id']), None)
        refs = self._refs(intent, frame)
        if existing:
            if existing.file_evidence != refs: raise CoordinationError('external_file_receipt_conflict')
            return existing
        proof = _verified_file_proof(refs, request_digest)
        self.publisher.publish_file(capture_sqlite_evidence(self.journal.db), proof,
            publication_id=frame['publication_id'], expected=witness(head))
        return self._head()[1]

    def _validate_complete(self, frame, history):
        sql = _one(self.journal.db, 'SELECT * FROM email_identity_receipts WHERE operation_id=?', (frame['operation_id'],))
        publication = next((p for p in history if p.publication_id == frame['sqlite_publication_id']), None)
        if (not sql or sql['receipt_id'] != frame['sqlite_receipt_id'] or sql['digest'] != frame['sqlite_receipt_digest']
                or publication is None or publication.digest != frame['sqlite_publication_digest']
                or publication.state != 'committed' or publication.latest_receipt_id != sql['receipt_id']
                or publication.chain_digest != sql['digest']):
            raise CoordinationError('complete_receipt_binding_invalid')

    def _publish_sql(self, intent, step):
        history, head = self._head(); pubid = self._pubid(intent, step)
        existing = next((p for p in history if p.publication_id == pubid), None)
        if existing: return existing
        self.publisher.publish(capture_sqlite_evidence(self.journal.db), publication_id=pubid, expected=witness(head))
        return self._head()[1]

    def _validate_artifacts(self, intent, frame, *, current_after=False):
        paths = self.store.paths(intent['operation']['operation_id'])
        if file_hash(paths['backup']) != intent['before_hash']: raise CoordinationError('backup_hash_mismatch')
        before, _ = self.store.read(paths['backup'])
        if inventory_digest(before) != intent['before_inventory']: raise CoordinationError('backup_inventory_mismatch')
        target = self.store.current if current_after else paths['stage']
        if file_hash(target) != frame['after_hash']: raise CoordinationError('staging_hash_mismatch')
        inventory, metadata = self.store.read(target)
        if inventory_digest(inventory) != intent['after_inventory'] or metadata != intent['metadata']:
            raise CoordinationError('staging_plan_mismatch')

    def execute(self, proposed, operation, *, actor_id, authorization_ref, policy_version):
        """Explicit authorized execution/recovery. Same request required after restart."""
        validate_inventory(proposed)
        request = _digest(dict(operation=asdict(operation), inventory=inventory_digest(proposed), actor=actor_id,
                               authorization_ref=authorization_ref, policy_version=policy_version))
        with self.store.locked():
            history, head = self._head()
            evidence = capture_sqlite_evidence(self.journal.db)
            if (evidence.journal_sequence < head.journal_sequence or
                    evidence.prefix_digests[head.journal_sequence] != head.journal_digest):
                raise CoordinationError('database_rollback_or_divergence')
            if evidence.journal_sequence > head.journal_sequence + 1: raise CoordinationError('journal_gap')
            if evidence.journal_sequence == head.journal_sequence:
                if (evidence.checkpoint != head.checkpoint or evidence.identity_digest != head.identity_digest
                        or evidence.chain_digest != head.chain_digest):
                    raise CoordinationError('database_checkpoint_divergent')
                self.journal.repository.checkpoint = head.checkpoint
            paths = self.store.paths(operation.operation_id)
            if paths['intent'].exists():
                intent, frames = read_receipts(self.store, operation.operation_id)
                if intent['request'] != request: raise CoordinationError('operation_id_content_conflict')
                operation, old_history, allocations, context = _recipe(intent)
                before_path = self.store.current if file_hash(self.store.current) == intent['before_hash'] else paths['backup']
                before, _ = self.store.read(before_path)
            else:
                if paths['receipts'].exists() or self._row(operation.operation_id): raise CoordinationError('receipt_missing_or_invalid')
                if head.pending is not None or (head.file_evidence and head.file_evidence.file_phase not in ('complete','cancelled')):
                    raise CoordinationError('other_operation_pending')
                expected_hash = head.file_evidence.confirmed_excel_hash if head.file_evidence else self.initial_file_hash
                if file_hash(self.store.current) != expected_hash: raise CoordinationError('current_file_changed')
                if evidence.journal_sequence != head.journal_sequence or evidence.checkpoint != head.checkpoint:
                    raise CoordinationError('database_checkpoint_divergent')
                before, _ = self.store.read(self.store.current)
                checkpoint = evidence.checkpoint
                context = p1.PlanningContext(checkpoint.epoch, checkpoint.revision, checkpoint.source_revision, checkpoint.source_token)
                old_history = _history(self.journal.db)
                draft = p1.plan_identity_transition(before, proposed, operation, old_history, context=context)
                allocations = tuple(p1.TokenAllocation(need.key, uuid.uuid4().hex) for need in draft.allocations_needed)
                plan = p1.plan_identity_transition(before, proposed, operation, old_history, context=context, allocations=allocations)
                if not plan.ready_for_manifest: raise CoordinationError('identity_plan_invalid')
                identity = uuid.uuid4().hex; staging_id = uuid.uuid4().hex
                intent = dict(format=1, request=request, operation=asdict(operation), before_hash=expected_hash,
                    before_inventory=inventory_digest(before), after_inventory=inventory_digest(proposed),
                    context=asdict(context), history=[asdict(i) for i in old_history], allocations=[asdict(a) for a in allocations],
                    plan_fingerprint=plan.plan_fingerprint, staging_id=staging_id, backup_id=uuid.uuid4().hex,
                    replace_id=identity, metadata=dict(operation_id=operation.operation_id, replace_id=identity,
                        staging_id=staging_id, plan_fingerprint=plan.plan_fingerprint))
                intent['digest'] = _digest(intent)
                paths['intent'].parent.mkdir(exist_ok=False)
                self.store.write_json(paths['intent'], intent)
                frames = []; self._frame(intent, frames, 'intent')
            plan = p1.plan_identity_transition(before, proposed, operation, old_history, context=context, allocations=allocations)
            if inventory_digest(before) != intent['before_inventory'] or plan.plan_fingerprint != intent['plan_fingerprint'] or not plan.ready_for_manifest:
                raise CoordinationError('plan_fingerprint_mismatch')
            authorization = self.journal.producer.issue(actor_id, operation, plan, authorization_ref=authorization_ref, policy_version=policy_version)
            # Reauthorize even terminal replays. This callback is trusted server policy.
            with _read_transaction(self.journal.db):
                self.journal._authorize(authorization, operation, plan)
            row = self._row(operation.operation_id)
            if row and row['status'] == 'aborted': raise CoordinationError('identity_operation_aborted')
            if frames[-1]['phase'] == 'cancelled': raise CoordinationError('identity_operation_aborted')
            # A local receipt cannot outrun or replace an externally retained proof.
            own_pubs = [p for p in history if p.file_evidence and p.file_evidence.operation_id == operation.operation_id]
            for publication in own_pubs:
                if publication.file_evidence not in [self._refs(intent, f) for f in frames]:
                    raise CoordinationError('external_file_receipt_conflict')
            if frames[-1]['phase'] == 'complete':
                if head.file_evidence is None or file_hash(self.store.current) != head.file_evidence.confirmed_excel_hash:
                    raise CoordinationError('current_file_changed')
                if evidence.checkpoint != head.checkpoint or evidence.journal_sequence != head.journal_sequence:
                    raise CoordinationError('database_checkpoint_divergent')
                if head.file_evidence.operation_id == operation.operation_id:
                    self._validate_artifacts(intent, frames[-1], current_after=True)
                elif file_hash(paths['backup']) != intent['before_hash']:
                    raise CoordinationError('backup_hash_mismatch')
                final = self._publish_frame(intent, frames[-1], own_pubs[-1].pending.request_digest if own_pubs[-1].pending else self._request_digest(operation.operation_id))
                return self._result(intent, frames[-1], final)
            if head.file_evidence and head.file_evidence.operation_id != operation.operation_id and head.file_evidence.file_phase not in ('complete','cancelled'):
                raise CoordinationError('other_operation_pending')
            kwargs = dict(authorization=authorization, allocations=allocations)
            reserve_id = self._pubid(intent, 'intent')
            if not any(p.publication_id == reserve_id for p in history):
                self.fault_hook('before_reserve')
                technical = capture_authorized_intent(self.journal, before, proposed, operation, plan, **kwargs)
                self.publisher.reserve_intent(technical, publication_id=reserve_id, expected=witness(head),
                    file_proof=_verified_file_proof(self._refs(intent, frames[0]), technical.request_digest))
                self._head(); self.fault_hook('after_reserve')
            if row is None:
                self.fault_hook('before_prepare')
                self.journal.prepare(before, proposed, operation, plan, **kwargs)
                self.fault_hook('after_prepare')
            self._publish_sql(intent, 'prepared')
            request_digest = self._request_digest(operation.operation_id)
            frame = frames[-1]
            if frame['phase'] == 'intent':
                if file_hash(self.store.current) != intent['before_hash']: raise CoordinationError('current_file_changed')
                self.fault_hook('before_backup')
                if not paths['backup'].exists():
                    with self.store.current.open('rb') as source, paths['backup'].open('xb') as target:
                        for block in iter(lambda: source.read(65536), b''): target.write(block)
                        target.flush(); os.fsync(target.fileno())
                if file_hash(paths['backup']) != intent['before_hash']: raise CoordinationError('backup_hash_mismatch')
                self.fault_hook('after_backup'); self.fault_hook('before_staging')
                self.store.write(paths['stage'], proposed, intent['metadata'])
                self.fault_hook('after_staging_write')
                new_hash = file_hash(paths['stage'])
                candidate = dict(after_hash=new_hash)
                self._validate_artifacts(intent, candidate)
                self.fault_hook('after_staging_verify')
                if file_hash(paths['stage']) != new_hash: raise CoordinationError('staging_hash_mismatch')
                frame = self._frame(intent, frames, 'staged', new_hash)
            self._publish_frame(intent, frame, request_digest)
            if frame['phase'] == 'staged':
                self._validate_artifacts(intent, frame)
                _, head = self._head()
                if head.state != 'decision_pending':
                    technical = capture_authorized_intent(self.journal, before, proposed, operation, plan, action='commit', **kwargs)
                    self.publisher.reserve_intent(technical, publication_id=self._pubid(intent,'commit-intent'), expected=witness(head))
                    self._head()
                frame = self._frame(intent, frames, 'replace_intent', frame['after_hash'])
                self._publish_frame(intent, frame, request_digest)
            if frame['phase'] == 'replace_intent':
                actual = file_hash(self.store.current)
                if actual == intent['before_hash']:
                    self._validate_artifacts(intent, frame)
                    # P2 recomputation + current business authorization immediately before replace.
                    capture_authorized_intent(self.journal, before, proposed, operation, plan, action='commit', **kwargs)
                    self.fault_hook('before_replace')
                    if file_hash(self.store.current) != intent['before_hash']: raise CoordinationError('current_file_changed')
                    self._validate_artifacts(intent, frame)
                    if self.store.current.stat().st_dev != paths['stage'].stat().st_dev: raise CoordinationError('same_filesystem_required')
                    os.replace(paths['stage'], self.store.current)
                    self.fault_hook('after_replace')
                elif actual != frame['after_hash']: raise CoordinationError('current_file_changed')
                self._validate_artifacts(intent, frame, current_after=True)
                self.store.sync_file(self.store.current); self.fault_hook('before_directory_sync')
                self.store.sync_directory(self.store.current.parent)
                frame = self._frame(intent, frames, 'replaced', frame['after_hash'])
                self._publish_frame(intent, frame, request_digest)
            if frame['phase'] == 'replaced':
                self._validate_artifacts(intent, frame, current_after=True)
                row = self._row(operation.operation_id)
                if row['status'] != 'committed':
                    self.journal.commit(before, proposed, operation, plan, **kwargs)
                    self.fault_hook('after_sqlite_commit')
                sql_publication = self._publish_sql(intent, 'committed')
                self.fault_hook('after_commit_publication')
                sql = _one(self.journal.db, 'SELECT * FROM email_identity_receipts WHERE operation_id=?', (operation.operation_id,))
                frame = self._frame(intent, frames, 'complete', frame['after_hash'], sql, sql_publication)
            final = self._publish_frame(intent, frame, request_digest)
            self.fault_hook('after_complete_publication')
            return self._result(intent, frame, final)

    def _request_digest(self, operation_id):
        evidence = capture_sqlite_evidence(self.journal.db)
        return next(e.request_digest for e in evidence.events if e.operation_id == operation_id)

    def cancel(self, proposed, operation, *, actor_id, authorization_ref, policy_version, reason='cancelled'):
        """Explicit cancellation before a commit decision; never restores an XLSX."""
        with self.store.locked():
            intent, frames = read_receipts(self.store, operation.operation_id)
            request = _digest(dict(operation=asdict(operation), inventory=inventory_digest(proposed), actor=actor_id,
                authorization_ref=authorization_ref, policy_version=policy_version))
            if request != intent['request']: raise CoordinationError('operation_id_content_conflict')
            operation, history, allocations, context = _recipe(intent)
            if file_hash(self.store.current) != intent['before_hash']: raise CoordinationError('cancellation_unsafe')
            before, _ = self.store.read(self.store.current)
            plan = p1.plan_identity_transition(before, proposed, operation, history, context=context, allocations=allocations)
            if plan.plan_fingerprint != intent['plan_fingerprint']: raise CoordinationError('plan_fingerprint_mismatch')
            authorization = self.journal.producer.issue(actor_id, operation, plan, authorization_ref=authorization_ref, policy_version=policy_version)
            with _read_transaction(self.journal.db):
                self.journal._authorize(authorization, operation, plan)
            _, head = self._head(); row = self._row(operation.operation_id)
            if row is None or frames[-1]['phase'] not in ('intent','staged','cancelled'):
                raise CoordinationError('cancellation_unsafe')
            if row['status'] != 'aborted':
                self._publish_sql(intent, 'prepared'); _, head = self._head()
                if head.state == 'prepared':
                    technical = capture_authorized_intent(self.journal, before, proposed, operation, plan,
                        authorization=authorization, allocations=allocations, action='abort', reason=reason)
                    self.publisher.reserve_intent(technical, publication_id=self._pubid(intent,'abort-intent'), expected=witness(head))
                elif head.state != 'decision_pending' or head.pending.phase != 'abort_intent':
                    raise CoordinationError('cancellation_unsafe')
                self.journal.abort(operation, plan, authorization=authorization, reason=reason)
            self._publish_sql(intent, 'aborted')
            frame = frames[-1]
            if frame['phase'] != 'cancelled':
                frame = self._frame(intent, frames, 'cancelled', frame['after_hash'])
            self._publish_frame(intent, frame, self._request_digest(operation.operation_id))
            return frame['digest']

    def _result(self, intent, frame, publication):
        return CoordinatedReceipt(frame['operation_id'], intent['before_hash'], frame['after_hash'], intent['staging_id'],
            intent['backup_id'], intent['replace_id'], frame['digest'], frame['sqlite_receipt_id'],
            frame['sqlite_receipt_digest'], publication.publication_id, publication.digest)
