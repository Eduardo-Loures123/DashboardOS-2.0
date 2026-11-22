"""3C.2A isolated repository. No file opening, Flask, SMTP, scheduler or auto-migration.

The connection and checkpoint are supplied by a trusted server caller. The
checkpoint MUST be anchored independently of a database/snapshot being restored.
Incarnation tokens must originate at durable create/delete producers, never UI.
This module implements that boundary, not the missing production producers.
"""
from dataclasses import dataclass
import json
import sqlite3

from . import email_recipient_policy as policy
from .email_recipient_schema import PersistenceError, transaction, utc_now, verify_schema


@dataclass(frozen=True)
class IdentityCheckpoint:
    epoch: str
    revision: int
    source_revision: int
    source_token: str


@dataclass(frozen=True)
class TeamIncarnation:
    code: str
    incarnation: str


@dataclass(frozen=True)
class RecordIncarnation:
    module: str
    code: str
    incarnation: str
    team_code: str
    operational_generation: int


@dataclass(frozen=True)
class IdentityManifest:
    """Complete inventory, emitted by a future trusted durable producer."""
    epoch: str
    source_revision: int
    source_token: str
    teams: tuple[TeamIncarnation, ...]
    records: tuple[RecordIncarnation, ...]


@dataclass(frozen=True)
class PersistedPolicy:
    accounts: tuple
    primary_designations: tuple
    authorizations: tuple
    issues: tuple[str, ...]


def _one(db, sql, args=()):
    cursor = db.execute(sql, args)
    row = cursor.fetchone()
    return None if row is None else dict(zip((c[0] for c in cursor.description), row))


def _many(db, sql, args=()):
    cursor = db.execute(sql, args)
    names = tuple(c[0] for c in cursor.description)
    return [dict(zip(names, row)) for row in cursor]


def _id(value):
    return policy._identifier(value)


class EmailRecipientRepository:
    def __init__(self, db, checkpoint):
        if not isinstance(db, sqlite3.Connection) or type(checkpoint) is not IdentityCheckpoint:
            raise PersistenceError('connection_and_external_checkpoint_required')
        self.db = db
        self.checkpoint = checkpoint

    def _state(self):
        state = _one(self.db, 'SELECT * FROM email_identity_state WHERE slot=1')
        if state is None:
            raise PersistenceError('identity_state_missing')
        return state

    def _check(self, *, ready=False):
        verify_schema(self.db)
        state = self._state()
        actual = IdentityCheckpoint(state['epoch'], state['revision'], state['source_revision'], state['source_token'])
        if actual != self.checkpoint:
            raise PersistenceError('external_checkpoint_mismatch')
        if ready and state['ready'] != 1:
            raise PersistenceError('identity_continuity_unavailable')
        return state

    def _accounts(self):
        # Deliberately avoid ProfileService's presentation user_id/login alias.
        return tuple(policy.EmailAccount(r['user_id'], r['role'], r['state'], r['email'],
                                         r['verified'], r['email_alerts']) for r in _many(
            self.db, 'SELECT user_id,role,state,email,verified,email_alerts FROM account ORDER BY user_id'))

    def _actor(self, actor):
        row = _one(self.db, 'SELECT role,state FROM account WHERE user_id=?', (_id(actor),))
        if row is None or row['role'] != 'superadmin' or row['state'] != 'active':
            raise PersistenceError('active_superadmin_required')

    def _target(self, target, *, administrative=False):
        row = _one(self.db, 'SELECT role,state FROM account WHERE user_id=?', (_id(target),))
        if row is None:
            raise PersistenceError('target_account_missing')
        if row['state'] != 'active':
            raise PersistenceError('target_account_not_active')
        roles = policy.ADMIN_ROLES if administrative else {'superadmin', 'admin', 'user'}
        if row['role'] not in roles:
            raise PersistenceError('target_role_invalid')

    def _audit(self, actor, target, operation, object_id, result, details):
        known = self.db.execute('SELECT 1 FROM account WHERE user_id=?', (actor,)).fetchone()
        self.db.execute('''INSERT INTO email_recipient_audit
            (actor_id,affected_account,operation,object_id,occurred_at,result,details) VALUES (?,?,?,?,?,?,?)''',
            (actor if known else None, target, operation, object_id, utc_now(), result,
             json.dumps(details, sort_keys=True, separators=(',', ':'))))

    def _operate(self, actor, target, operation, object_id, callback):
        _id(actor); _id(object_id)
        if target is not None: _id(target)
        failure = None
        with transaction(self.db):
            self._check()
            self.db.execute('SAVEPOINT recipient_command')
            try:
                self._actor(actor)
                value = callback()
            except (PersistenceError, policy.PolicyInputError, sqlite3.IntegrityError) as exc:
                self.db.execute('ROLLBACK TO recipient_command')
                failure = 'integrity_conflict' if isinstance(exc, sqlite3.IntegrityError) else str(exc)
                value = None
            self.db.execute('RELEASE recipient_command')
            if failure in {'identity_source_gap', 'record_incarnation_reused',
                           'team_incarnation_reused', 'operational_generation_rollback'}:
                # Known loss of continuity must disable subsequent resolutions,
                # not merely reject this one manifest and keep old grants usable.
                self.db.execute('UPDATE email_identity_state SET ready=0 WHERE slot=1')
            if target is None and operation in ('primary.revoke', 'authorization.revoke'):
                table, key = ('email_primary_designations', 'designation_id') if operation == 'primary.revoke' else (
                    'email_recipient_authorizations', 'grant_id')
                affected = _one(self.db, f'SELECT account_id FROM {table} WHERE {key}=?', (object_id,))
                target = affected['account_id'] if affected else None
            self._audit(actor, target, operation, object_id, 'rejected' if failure else 'success',
                        {'reason': failure} if failure else {'schema': 1})
            self.db.execute('UPDATE email_identity_state SET revision=revision+1 WHERE slot=1')
            state = self._state()
            checkpoint = IdentityCheckpoint(state['epoch'], state['revision'], state['source_revision'], state['source_token'])
        # Publish only after COMMIT; the future caller must durably anchor this value.
        self.checkpoint = checkpoint
        if failure:
            raise PersistenceError(failure)
        return value

    def designate_primary(self, designation_id, account_id, *, actor_id, replace_current=False, reason=None):
        def command():
            self._target(account_id, administrative=True)
            current = _one(self.db, 'SELECT * FROM email_primary_designations WHERE active=1')
            if current:
                if replace_current is not True:
                    raise PersistenceError('primary_already_designated')
                self._revoke('email_primary_designations', 'designation_id', current['designation_id'], actor_id, reason)
                self._audit(actor_id, current['account_id'], 'primary.revoke', current['designation_id'],
                            'success', {'replacement_id': designation_id})
            self.db.execute('''INSERT INTO email_primary_designations
                (designation_id,account_id,approved_by,approved_at,active) VALUES (?,?,?,?,1)''',
                (designation_id, account_id, actor_id, utc_now()))
            return designation_id
        return self._operate(actor_id, account_id, 'primary.designate', designation_id, command)

    def _revoke(self, table, key, object_id, actor, reason):
        _id(reason)
        # table/key are constants selected by repository methods, never user SQL.
        row = _one(self.db, f'SELECT * FROM {table} WHERE {key}=?', (object_id,))
        if row is None or row['active'] != 1:
            raise PersistenceError('active_object_missing')
        self.db.execute(f'''UPDATE {table} SET active=0,revoked_by=?,revoked_at=?,revocation_reason=?
            WHERE {key}=?''', (actor, utc_now(), reason, object_id))
        return row['account_id']

    def revoke_primary(self, designation_id, *, actor_id, reason):
        def command():
            self._revoke('email_primary_designations', 'designation_id', designation_id, actor_id, reason)
        return self._operate(actor_id, None, 'primary.revoke', designation_id, command)

    def _team(self, code):
        row = _one(self.db, 'SELECT * FROM email_team_identities WHERE code=? AND present=1', (code,))
        if row is None:
            raise PersistenceError('team_identity_missing')
        return row

    def _record(self, module, code):
        row = _one(self.db, 'SELECT * FROM email_record_identities WHERE module=? AND code=? AND present=1', (module, code))
        if row is None:
            raise PersistenceError('record_identity_missing')
        return row

    def grant(self, grant_id, account_id, module, scope, *, actor_id, raw, snapshot,
              team_code=None, record_code=None):
        def command():
            self._check(ready=True)
            self._target(account_id)
            proposal = policy.approve_email_authorization(grant_id, account_id, module, scope,
                actor_id=actor_id, accounts=self._accounts(), raw=raw, snapshot=snapshot,
                team_code=team_code, record_code=record_code)
            team_generation = record_generation = operational_generation = None
            if proposal.team_code is not None:
                team_generation = self._team(proposal.team_code)['generation']
            if scope == 'record':
                record = self._record(module, record_code)
                if (record['team_code'], record['team_generation'], record['operational_generation']) != (
                        proposal.team_code, team_generation, proposal.generation):
                    raise PersistenceError('record_identity_mismatch')
                record_generation, operational_generation = record['generation'], record['operational_generation']
            self.db.execute('''INSERT INTO email_recipient_authorizations
                (grant_id,account_id,module,scope,epoch,team_code,team_generation,record_code,
                 record_generation,operational_generation,approved_by,approved_at,active)
                 VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)''',
                (grant_id, account_id, module, scope, self.checkpoint.epoch, proposal.team_code,
                 team_generation, proposal.record_code, record_generation, operational_generation, actor_id, utc_now()))
            return grant_id
        return self._operate(actor_id, account_id, 'authorization.grant', grant_id, command)

    def revoke(self, grant_id, *, actor_id, reason):
        def command():
            self._revoke('email_recipient_authorizations', 'grant_id', grant_id, actor_id, reason)
        return self._operate(actor_id, None, 'authorization.revoke', grant_id, command)

    def _synchronize_manifest(self, manifest):
        """Internal transaction participant. Caller must authorize and check continuity.

        Public administrative sync and the isolated P2 unit of work are the only
        intended callers. This method never commits or publishes a checkpoint.
        """
        if not self.db.in_transaction:
            raise PersistenceError('identity_transaction_required')
        def command():
            state = self._state()
            if state['ready'] == 0 and state['source_revision'] > 0:
                raise PersistenceError('identity_recovery_required')
            if (type(manifest) is not IdentityManifest or manifest.epoch != state['epoch']
                    or type(manifest.source_revision) is not int or manifest.source_revision <= state['source_revision']):
                raise PersistenceError('identity_source_stale')
            if manifest.source_revision != state['source_revision'] + 1:
                raise PersistenceError('identity_source_gap')
            _id(manifest.source_token)
            if manifest.source_token == state['source_token']:
                raise PersistenceError('identity_source_token_reused')
            teams = {}; records = {}
            for item in manifest.teams:
                if type(item) is not TeamIncarnation:
                    raise PersistenceError('identity_manifest_invalid')
                _id(item.code); _id(item.incarnation)
                if item.code in teams: raise PersistenceError('identity_manifest_duplicate')
                teams[item.code] = item
            for item in manifest.records:
                if type(item) is not RecordIncarnation:
                    raise PersistenceError('identity_manifest_invalid')
                _id(item.code); _id(item.incarnation); _id(item.team_code)
                if (item.module not in policy.DATE_FIELDS or item.team_code not in teams
                        or type(item.operational_generation) is not int or item.operational_generation < 1):
                    raise PersistenceError('identity_manifest_invalid')
                key = (item.module, item.code)
                if key in records: raise PersistenceError('identity_manifest_duplicate')
                records[key] = item
            for old in _many(self.db, 'SELECT * FROM email_team_identities WHERE present=1'):
                if old['code'] not in teams:
                    self.db.execute('UPDATE email_team_identities SET present=0 WHERE code=? AND generation=?',
                                    (old['code'], old['generation']))
            for code, item in teams.items():
                old = _one(self.db, 'SELECT * FROM email_team_identities WHERE code=? ORDER BY generation DESC LIMIT 1', (code,))
                if old and old['present'] and old['incarnation'] == item.incarnation:
                    continue
                if self.db.execute('SELECT 1 FROM email_team_identities WHERE code=? AND incarnation=?', (code, item.incarnation)).fetchone():
                    raise PersistenceError('team_incarnation_reused')
                if old and old['present']:
                    self.db.execute('UPDATE email_team_identities SET present=0 WHERE code=? AND generation=?', (code, old['generation']))
                self.db.execute('INSERT INTO email_team_identities VALUES (?,?,?,1)',
                                (code, old['generation'] + 1 if old else 1, item.incarnation))
            for old in _many(self.db, 'SELECT * FROM email_record_identities WHERE present=1'):
                if (old['module'], old['code']) not in records:
                    self.db.execute('UPDATE email_record_identities SET present=0 WHERE module=? AND code=? AND generation=?',
                                    (old['module'], old['code'], old['generation']))
            for (module, code), item in records.items():
                old = _one(self.db, 'SELECT * FROM email_record_identities WHERE module=? AND code=? ORDER BY generation DESC LIMIT 1', (module, code))
                team_generation = self._team(item.team_code)['generation']
                binding = (item.incarnation, item.team_code, team_generation, item.operational_generation)
                if old and old['present'] and binding == (old['incarnation'], old['team_code'], old['team_generation'], old['operational_generation']):
                    continue
                previous_incarnation = self.db.execute('SELECT 1 FROM email_record_identities WHERE module=? AND code=? AND incarnation=?',
                                                       (module, code, item.incarnation)).fetchone()
                if old and previous_incarnation and (not old['present'] or old['incarnation'] != item.incarnation):
                    raise PersistenceError('record_incarnation_reused')
                if old and old['present'] and old['incarnation'] == item.incarnation and item.operational_generation < old['operational_generation']:
                    raise PersistenceError('operational_generation_rollback')
                if old and old['present']:
                    self.db.execute('UPDATE email_record_identities SET present=0 WHERE module=? AND code=? AND generation=?', (module, code, old['generation']))
                self.db.execute('INSERT INTO email_record_identities VALUES (?,?,?,?,?,?,?,1)',
                    (module, code, old['generation'] + 1 if old else 1, item.incarnation, item.team_code,
                     team_generation, item.operational_generation))
            self.db.execute('UPDATE email_identity_state SET source_revision=?,source_token=?,ready=1 WHERE slot=1',
                            (manifest.source_revision, manifest.source_token))
        return command()

    def sync_identities(self, manifest, *, actor_id):
        """Explicit administrative sync; retains all 3C.2A authority checks."""
        return self._operate(actor_id, None, 'identity.sync', 'complete-inventory',
                             lambda: self._synchronize_manifest(manifest))

    def invalidate_continuity(self, new_epoch, *, actor_id, reason):
        """Explicit recovery barrier; never infer continuity from an old snapshot."""
        def command():
            _id(new_epoch); _id(reason)
            if new_epoch == self.checkpoint.epoch:
                raise PersistenceError('new_epoch_required')
            for row in _many(self.db, 'SELECT * FROM email_recipient_authorizations WHERE active=1'):
                self._revoke('email_recipient_authorizations', 'grant_id', row['grant_id'], actor_id, reason)
                self._audit(actor_id, row['account_id'], 'authorization.revoke', row['grant_id'], 'success', {'continuity_lost': True})
            self.db.execute('UPDATE email_record_identities SET present=0 WHERE present=1')
            self.db.execute('UPDATE email_team_identities SET present=0 WHERE present=1')
            self.db.execute("UPDATE email_identity_state SET epoch=?,source_revision=0,source_token='',ready=0 WHERE slot=1", (new_epoch,))
        return self._operate(actor_id, None, 'identity.invalidate', 'continuity', command)

    def _load(self):
        self._check(ready=True)
        accounts = self._accounts()
        primary = tuple(policy._sealed(policy.PrimaryDesignation(r['designation_id'], r['account_id'], r['approved_by']))
                        for r in _many(self.db, 'SELECT * FROM email_primary_designations WHERE active=1'))
        grants = []; issues = []
        for row in _many(self.db, 'SELECT * FROM email_recipient_authorizations ORDER BY grant_id'):
            current = row['epoch'] == self.checkpoint.epoch
            if row['scope'] != 'module':
                team = _one(self.db, 'SELECT * FROM email_team_identities WHERE code=? AND present=1', (row['team_code'],))
                current = current and team is not None and team['generation'] == row['team_generation']
            if row['scope'] == 'record':
                record = _one(self.db, 'SELECT * FROM email_record_identities WHERE module=? AND code=? AND present=1', (row['module'], row['record_code']))
                current = current and record is not None and record['generation'] == row['record_generation']
            if not current:
                issues.append('authorization_identity_stale:' + row['grant_id'])
                continue
            grants.append(policy._sealed(policy.EmailAuthorization(row['grant_id'], row['account_id'], row['module'],
                row['scope'], row['approved_by'], row['team_code'], row['record_code'], row['operational_generation'],
                row['active'] == 1, row['revoked_by'])))
        return PersistedPolicy(accounts, primary, tuple(grants), tuple(issues))

    def load_policy(self):
        """Snapshot only; it must be loaded again at future delivery time."""
        with transaction(self.db, write=False):
            return self._load()

    def resolve(self, event, raw, *, snapshot, prepared=None):
        """Rehydrate and evaluate 3C.1 within one consistent DB read transaction."""
        with transaction(self.db, write=False):
            current = self._load()
            kwargs = dict(snapshot=snapshot, primary_designations=current.primary_designations,
                          authorizations=current.authorizations)
            if prepared is None:
                result = policy.resolve_email_recipients(event, raw, current.accounts, **kwargs)
            else:
                result = policy.revalidate_email_recipients(prepared, event, raw, current.accounts, **kwargs)
            from dataclasses import replace
            identity, denials = policy._record_identity(event.sheet, event.code, raw, snapshot)
            durable = _one(self.db, 'SELECT * FROM email_record_identities WHERE module=? AND code=? AND present=1',
                           (event.sheet, event.code))
            team = None if identity is None else _one(self.db,
                'SELECT generation FROM email_team_identities WHERE code=? AND present=1', (identity.team_code,))
            if (denials or durable is None or team is None or
                    (durable['team_code'], durable['team_generation'], durable['operational_generation']) !=
                    (identity.team_code, team['generation'], identity.generation)):
                reason = ('durable_record_identity_mismatch',)
                result = replace(result, email_account_ids=(), issues=result.issues + reason,
                                 decisions=tuple(replace(d, event_denials=d.event_denials + reason) for d in result.decisions))
            return replace(result, issues=tuple(sorted(set(result.issues + current.issues))))
