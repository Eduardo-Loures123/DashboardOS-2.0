"""P2: isolated SQLite unit of work. No paths, Flask, Excel or external anchor.

TrustedProducer is a server configuration boundary, NOT a JSON authorizer or a
cryptographic sandbox against malicious Python/SQLite owners. Business policy
must be configured internally and is rechecked inside every transaction.
"""
from dataclasses import asdict, dataclass, field
import hashlib
import json
import uuid

from .email_recipient_schema import PersistenceError, transaction, utc_now
from .email_recipient_repository import (
    EmailRecipientRepository, IdentityCheckpoint, IdentityManifest, TeamIncarnation,
    RecordIncarnation, _many, _one,
)
from .identity_operation_schema import verify_journal_schema
from . import identity_planner as planner


def _json(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def _hash(value):
    return hashlib.sha256(_json(value).encode('utf-8')).hexdigest()


def _canonical_operation(operation):
    value = asdict(operation)
    for name in ('targets', 'continuations'):
        value[name] = sorted(value[name], key=lambda key: (key['module'], key['code']))
    return value


def _label(value):
    if not planner._text(value):
        raise PersistenceError('identity_operation_identifier_invalid')
    return value


@dataclass(frozen=True)
class AuthorizationRequest:
    actor_id: str
    operation_id: str
    plan_fingerprint: str
    origin: str
    authorization_ref: str
    policy_version: str
    kind: str
    module: str | None
    record_code: str | None
    account_role: str


@dataclass(frozen=True)
class BusinessAuthorization:
    actor_id: str
    operation_id: str
    plan_fingerprint: str
    authorization_ref: str
    policy_version: str


@dataclass(frozen=True)
class ProducerContext:
    actor_id: str
    operation_id: str
    plan_fingerprint: str
    origin: str
    authorization_ref: str
    policy_version: str
    _issuer: object = field(default=None, init=False, repr=False, compare=False)


class TrustedProducer:
    """Instantiate only from trusted server configuration, never a request handler's JSON.

    The callback must implement current business authorization. A boolean return
    is insufficient. It is NOT allowed to designate/grant/revoke permissions.
    """
    def __init__(self, origin, authorize):
        self.origin = _label(origin)
        if not callable(authorize): raise PersistenceError('business_authorizer_required')
        self._authorize = authorize
        self._seal = object()

    def issue(self, actor_id, operation, plan, *, authorization_ref, policy_version):
        if type(plan) is not planner.IdentityPlan or type(operation) is not planner.ProposedOperation:
            raise PersistenceError('identity_plan_and_operation_required')
        context = ProducerContext(_label(actor_id), _label(operation.operation_id), _label(plan.plan_fingerprint), self.origin,
                                  _label(authorization_ref), _label(policy_version))
        object.__setattr__(context, '_issuer', self._seal)
        return context


@dataclass(frozen=True)
class PreparedOperation:
    operation_id: str
    receipt_id: str
    status: str
    plan_fingerprint: str


@dataclass(frozen=True)
class IdentityReceipt:
    receipt_id: str
    operation_id: str
    sequence: int
    previous_digest: str | None
    digest: str
    plan_fingerprint: str
    checkpoint: IdentityCheckpoint
    affected_identities_json: str  # canonical immutable metadata; no inventory rows
    committed_at: str


def _history(db):
    identities = []
    for row in _many(db, 'SELECT * FROM email_team_identities ORDER BY code,generation'):
        identities.append(planner.DurableIdentity(planner.RecordKey('Equipes', row['code']),
            row['incarnation'], row['generation'], row['present'] == 1))
    for row in _many(db, 'SELECT * FROM email_record_identities ORDER BY module,code,generation'):
        identities.append(planner.DurableIdentity(planner.RecordKey(row['module'], row['code']),
            row['incarnation'], row['generation'], row['present'] == 1, row['team_code'],
            row['team_generation'], row['operational_generation']))
    return tuple(identities)


def _request_content(row):
    """Only immutable journal columns, reconstructible without original personal data."""
    names = ('operation_id', 'origin', 'kind', 'actor_id', 'authorization_ref', 'policy_version',
             'module', 'record_code', 'before_fingerprint', 'after_fingerprint', 'history_fingerprint',
             'plan_fingerprint', 'epoch', 'expected_revision', 'expected_source_revision',
             'expected_source_token', 'plan_json', 'operation_json', 'allocations_json')
    return {name: row[name] for name in names}


def _receipt(row):
    payload = json.loads(row['payload_json'])
    return IdentityReceipt(row['receipt_id'], row['operation_id'], row['sequence'], row['previous_digest'],
        row['digest'], payload['plan_fingerprint'], IdentityCheckpoint(**payload['checkpoint']),
        _json(payload['affected_identities']), row['committed_at'])


def verify_journal_integrity(db):
    """Verify the whole chain and terminal state correspondence, without repairing."""
    verify_journal_schema(db)
    operations = {r['operation_id']: r for r in _many(db, 'SELECT * FROM email_identity_operations')}
    for operation in operations.values():
        if operation['request_digest'] != _hash(_request_content(operation)):
            raise PersistenceError('operation_payload_digest_mismatch')
        events = _many(db, 'SELECT status,occurred_at,reason FROM email_identity_operation_events WHERE operation_id=? ORDER BY id', (operation['operation_id'],))
        expected = [dict(status='prepared', occurred_at=operation['prepared_at'], reason=None)]
        if operation['status'] != 'prepared':
            expected.append(dict(status=operation['status'], occurred_at=operation['committed_at'] or operation['aborted_at'], reason=operation['reason']))
        if events != expected: raise PersistenceError('operation_history_mismatch')
    previous = None; committed = set()
    for sequence, receipt in enumerate(_many(db, 'SELECT * FROM email_identity_receipts ORDER BY sequence'), 1):
        operation = operations.get(receipt['operation_id'])
        try:
            payload = json.loads(receipt['payload_json'])
            original_plan = json.loads(operation['plan_json']) if operation else {}
            expected_checkpoint = dict(epoch=operation['epoch'], revision=operation['expected_revision'],
                source_revision=operation['expected_source_revision'], source_token=operation['expected_source_token']) if operation else {}
            result_checkpoint = dict(epoch=operation['epoch'], revision=operation['expected_revision'] + 1,
                source_revision=operation['expected_source_revision'] + 1, source_token=receipt['receipt_id']) if operation else {}
            valid = (operation is not None and operation['status'] == 'committed'
                and operation['receipt_id'] == receipt['receipt_id']
                and receipt['sequence'] == sequence and receipt['previous_digest'] == previous
                and receipt['payload_json'] == _json(payload) and receipt['digest'] == _hash(payload)
                and payload['operation_id'] == receipt['operation_id'] and payload['receipt_id'] == receipt['receipt_id']
                and payload['sequence'] == sequence and payload['previous_digest'] == previous
                and payload['request_digest'] == operation['request_digest']
                and payload['expected_checkpoint'] == expected_checkpoint and payload['checkpoint'] == result_checkpoint
                and payload['affected_identities'] == dict(ended=original_plan['tombstones'], created=original_plan['identities_to_create'])
                and payload['plan_fingerprint'] == operation['plan_fingerprint']
                and payload['committed_at'] == receipt['committed_at'] == operation['committed_at'])
        except (KeyError, TypeError, ValueError):
            valid = False
        if not valid: raise PersistenceError('receipt_chain_invalid')
        previous = receipt['digest']; committed.add(receipt['operation_id'])
    if committed != {key for key, row in operations.items() if row['status'] == 'committed'}:
        raise PersistenceError('committed_receipt_missing')


class IdentityOperationJournal:
    """Owns BEGIN IMMEDIATE; nested/external transactions are deliberately refused."""
    def __init__(self, db, checkpoint, producer):
        if type(producer) is not TrustedProducer: raise PersistenceError('trusted_producer_required')
        self.repository = EmailRecipientRepository(db, checkpoint)
        self.db = db
        self.producer = producer

    @property
    def checkpoint(self):
        return self.repository.checkpoint

    def _check(self):
        verify_journal_integrity(self.db)
        self.repository._check(ready=True)

    def _authorize(self, context, operation, plan):
        if (type(context) is not ProducerContext or context._issuer is not self.producer._seal
                or context.origin != self.producer.origin or context.plan_fingerprint != plan.plan_fingerprint
                or context.operation_id != operation.operation_id):
            raise PersistenceError('producer_context_untrusted')
        account = _one(self.db, 'SELECT state,role FROM account WHERE user_id=?', (context.actor_id,))
        if account is None or account['state'] != 'active' or account['role'] not in ('superadmin', 'admin', 'user'):
            raise PersistenceError('producer_actor_not_active')
        request = AuthorizationRequest(context.actor_id, operation.operation_id, plan.plan_fingerprint,
            context.origin, context.authorization_ref, context.policy_version, operation.kind,
            operation.module, operation.code, account['role'])
        decision = self.producer._authorize(request)
        expected = BusinessAuthorization(context.actor_id, operation.operation_id, plan.plan_fingerprint,
                                          context.authorization_ref, context.policy_version)
        if type(decision) is not BusinessAuthorization or decision != expected:
            raise PersistenceError('business_operation_not_authorized')

    def _candidate(self, before, proposed, operation, plan, context, allocations):
        if type(plan) is not planner.IdentityPlan or type(operation) is not planner.ProposedOperation:
            raise PersistenceError('identity_plan_and_operation_required')
        if not plan.applicable or not plan.ready_for_manifest:
            raise PersistenceError('identity_plan_not_ready')
        self._authorize(context, operation, plan)
        try:
            before_hash = planner._digest(planner._canonical_inventory(planner._inventory(before)))
            after_hash = planner._digest(planner._canonical_inventory(planner._inventory(proposed)))
        except planner._Refusal as error:
            raise PersistenceError(error.issue.code) from None
        if (before_hash, after_hash) != (plan.before_fingerprint, plan.after_fingerprint):
            raise PersistenceError('inventory_fingerprint_mismatch')
        canonical = _canonical_operation(operation)
        if type(allocations) not in (tuple, list) or any(type(a) is not planner.TokenAllocation for a in allocations):
            raise PersistenceError('identity_allocations_invalid')
        allocations_json = _json([asdict(a) for a in sorted(allocations, key=lambda a: a.key)])
        # Context is the original plan's context, even for matching receipt replay.
        # Expected checkpoint comes from the currently supplied context only for a
        # new request. Persisted expected values are checked separately on replay.
        return dict(operation_id=_label(operation.operation_id), origin=context.origin, kind=operation.kind,
            actor_id=context.actor_id, authorization_ref=context.authorization_ref, policy_version=context.policy_version,
            module=operation.module, record_code=operation.code, before_fingerprint=before_hash, after_fingerprint=after_hash,
            history_fingerprint=plan.history_fingerprint, plan_fingerprint=plan.plan_fingerprint,
            plan_json=_json(asdict(plan)), operation_json=_json(canonical), allocations_json=allocations_json)

    def _compare(self, row, candidate):
        if any(row[key] != value for key, value in candidate.items()):
            raise PersistenceError('operation_id_content_conflict')

    def _validate_plan(self, before, proposed, operation, plan, allocations):
        expected = self.checkpoint
        context = planner.PlanningContext(expected.epoch, expected.revision, expected.source_revision, expected.source_token)
        actual = planner.plan_identity_transition(before, proposed, operation, _history(self.db), context=context, allocations=allocations)
        if not actual.applicable or actual != plan:
            raise PersistenceError('identity_plan_stale_or_forged')
        return actual

    def _manifest(self, plan, receipt_id, checkpoint=None):
        checkpoint = checkpoint or self.checkpoint
        teams = tuple(TeamIncarnation(i.key.code, i.incarnation) for i in plan.resulting_identities if i.key.module == 'Equipes')
        records = tuple(RecordIncarnation(i.key.module, i.key.code, i.incarnation, i.team_code, i.operational_generation)
                        for i in plan.resulting_identities if i.key.module != 'Equipes')
        return IdentityManifest(checkpoint.epoch, checkpoint.source_revision + 1, receipt_id, teams, records)

    def prepare(self, before, proposed, operation, plan, *, authorization, allocations=()):
        with transaction(self.db):
            self._check()
            candidate = self._candidate(before, proposed, operation, plan, authorization, allocations)
            row = _one(self.db, 'SELECT * FROM email_identity_operations WHERE operation_id=?', (operation.operation_id,))
            if row:
                self._compare(row, candidate)
                if row['status'] == 'aborted': raise PersistenceError('identity_operation_aborted')
                if row['status'] == 'committed':
                    return _receipt(_one(self.db, 'SELECT * FROM email_identity_receipts WHERE operation_id=?', (operation.operation_id,)))
                self._validate_plan(before, proposed, operation, plan, allocations)
            else:
                self._validate_plan(before, proposed, operation, plan, allocations)
                checkpoint = self.checkpoint
                row = dict(candidate, epoch=checkpoint.epoch, expected_revision=checkpoint.revision,
                           expected_source_revision=checkpoint.source_revision, expected_source_token=checkpoint.source_token)
                row['request_digest'] = _hash(_request_content(row))
                row.update(receipt_id=uuid.uuid4().hex, status='prepared', prepared_at=utc_now())
                self.db.execute('INSERT INTO email_identity_operations (' + ','.join(row) + ') VALUES (' + ','.join('?' for _ in row) + ')', tuple(row.values()))
            return PreparedOperation(row['operation_id'], row['receipt_id'], row['status'], row['plan_fingerprint'])

    def _write_receipt(self, row, plan, checkpoint):
        previous = _one(self.db, 'SELECT sequence,digest FROM email_identity_receipts ORDER BY sequence DESC LIMIT 1')
        now = utc_now()
        affected = dict(ended=[asdict(i) for i in plan.tombstones], created=[asdict(i) for i in plan.identities_to_create])
        payload = dict(receipt_id=row['receipt_id'], operation_id=row['operation_id'],
            sequence=previous['sequence'] + 1 if previous else 1, previous_digest=previous['digest'] if previous else None,
            request_digest=row['request_digest'], plan_fingerprint=plan.plan_fingerprint,
            expected_checkpoint=dict(epoch=row['epoch'], revision=row['expected_revision'],
                source_revision=row['expected_source_revision'], source_token=row['expected_source_token']),
            checkpoint=asdict(checkpoint), affected_identities=affected, committed_at=now)
        digest = _hash(payload)
        self.db.execute('INSERT INTO email_identity_receipts VALUES (?,?,?,?,?,?,?)',
            (row['receipt_id'], row['operation_id'], payload['sequence'], payload['previous_digest'], digest, _json(payload), now))
        self.db.execute("UPDATE email_identity_operations SET status='committed',committed_at=? WHERE operation_id=?", (now, row['operation_id']))
        return _receipt(_one(self.db, 'SELECT * FROM email_identity_receipts WHERE operation_id=?', (row['operation_id'],)))

    def _after_commit(self, receipt):
        """No-op response boundary, also used to test lost responses after COMMIT."""
        return receipt

    def commit(self, before, proposed, operation, plan, *, authorization, allocations=(), manifest=None):
        checkpoint = None
        with transaction(self.db):
            self._check()
            candidate = self._candidate(before, proposed, operation, plan, authorization, allocations)
            row = _one(self.db, 'SELECT * FROM email_identity_operations WHERE operation_id=?', (operation.operation_id,))
            if row is None: raise PersistenceError('identity_operation_not_prepared')
            self._compare(row, candidate)
            original_checkpoint = IdentityCheckpoint(row['epoch'], row['expected_revision'], row['expected_source_revision'], row['expected_source_token'])
            expected = self._manifest(plan, row['receipt_id'], original_checkpoint)
            if manifest is not None and (type(manifest) is not IdentityManifest or manifest != expected):
                raise PersistenceError('identity_manifest_plan_mismatch')
            if row['status'] == 'aborted': raise PersistenceError('identity_operation_aborted')
            if row['status'] == 'committed':
                receipt = _receipt(_one(self.db, 'SELECT * FROM email_identity_receipts WHERE operation_id=?', (operation.operation_id,)))
            else:
                self._validate_plan(before, proposed, operation, plan, allocations)
                self.repository._synchronize_manifest(expected)
                current = _history(self.db)
                present = tuple(planner.PlannedIdentity(i.key, i.incarnation, i.generation, i.team_code, i.team_generation,
                                                       i.operational_generation) for i in sorted(current, key=lambda i: i.key) if i.present)
                if present != plan.resulting_identities or not all(tombstone in current for tombstone in plan.tombstones):
                    raise PersistenceError('persisted_identity_generation_mismatch')
                self.repository._audit(authorization.actor_id, None, 'identity.operation.commit', operation.operation_id,
                                       'success', {'origin': authorization.origin, 'receipt_id': row['receipt_id']})
                self.db.execute('UPDATE email_identity_state SET revision=revision+1 WHERE slot=1')
                state = self.repository._state()
                checkpoint = IdentityCheckpoint(state['epoch'], state['revision'], state['source_revision'], state['source_token'])
                receipt = self._write_receipt(row, plan, checkpoint)
                verify_journal_integrity(self.db)
        if checkpoint is not None:
            self.repository.checkpoint = checkpoint
        return self._after_commit(receipt)

    def abort(self, operation, plan, *, authorization, reason):
        _label(reason)
        with transaction(self.db):
            self._check()
            self._authorize(authorization, operation, plan)
            row = _one(self.db, 'SELECT * FROM email_identity_operations WHERE operation_id=?', (operation.operation_id,))
            if row is None: raise PersistenceError('identity_operation_not_prepared')
            if row['operation_json'] != _json(_canonical_operation(operation)) or row['plan_json'] != _json(asdict(plan)):
                raise PersistenceError('operation_id_content_conflict')
            if (row['actor_id'], row['origin'], row['plan_fingerprint'], row['authorization_ref'], row['policy_version']) != (
                    authorization.actor_id, authorization.origin, plan.plan_fingerprint, authorization.authorization_ref, authorization.policy_version):
                raise PersistenceError('producer_context_operation_mismatch')
            if row['status'] == 'committed': raise PersistenceError('identity_operation_already_committed')
            if row['status'] == 'aborted':
                if row['reason'] != reason: raise PersistenceError('operation_id_content_conflict')
                return PreparedOperation(row['operation_id'], row['receipt_id'], row['status'], row['plan_fingerprint'])
            self.db.execute("UPDATE email_identity_operations SET status='aborted',aborted_at=?,reason=? WHERE operation_id=?", (utc_now(), reason, operation.operation_id))
            return PreparedOperation(row['operation_id'], row['receipt_id'], 'aborted', row['plan_fingerprint'])
