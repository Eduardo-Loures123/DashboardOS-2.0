"""Etapa 3C.1: in-memory email policy, with no application or delivery integration.

Accounts, inventories and 3A snapshots MUST come from a trusted server caller.
Approval helpers return runtime capabilities, not persisted grants or signed JSON.
The private seal rejects accidental DTO reconstruction; it cannot authenticate a
malicious Python caller. Future repositories must authenticate/audit changes and
rehydrate approved rows through a separately reviewed server-only adapter.
"""
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

from .notification_recipients import email_eligibility_denials
from .operational_events import DATE_FIELDS, SNAPSHOT_FORMAT, OperationalEvent, is_superseded

_SEAL = object()
ADMIN_ROLES = frozenset(('admin', 'superadmin'))


class PolicyInputError(ValueError):
    """Safe machine-readable reason; never includes addresses or raw input."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class EmailAccount:
    account_id: str  # users.id / account.user_id, never the editable profile login
    role: str
    state: str
    email: str
    verified: bool | int
    email_alerts: bool | int
    login: str = ''  # presentation only
    display_name: str = ''


@dataclass(frozen=True)
class PrimaryDesignation:
    designation_id: str
    account_id: str
    approved_by: str
    active: bool = True
    _seal: object = field(default=None, init=False, repr=False, compare=False)


@dataclass(frozen=True)
class EmailAuthorization:
    grant_id: str
    account_id: str
    module: str
    scope: str
    approved_by: str
    team_code: str | None = None
    record_code: str | None = None
    generation: int | None = None
    active: bool = True
    revoked_by: str | None = None
    _seal: object = field(default=None, init=False, repr=False, compare=False)


@dataclass(frozen=True)
class PrimaryResolution:
    account_id: str | None
    issues: tuple[str, ...]


@dataclass(frozen=True)
class RecordIdentity:
    module: str
    code: str
    generation: int
    team_code: str


@dataclass(frozen=True)
class EmailDecision:
    account_id: str
    is_primary: bool
    authorization_sources: tuple[str, ...]
    authorization_denials: tuple[str, ...]
    eligibility_denials: tuple[str, ...]
    event_denials: tuple[str, ...] = ()

    @property
    def email_allowed(self):
        return bool(self.authorization_sources) and not (
            self.authorization_denials or self.eligibility_denials or self.event_denials)


@dataclass(frozen=True)
class EmailResolution:
    event_identity: str
    primary_account_id: str | None
    email_account_ids: tuple[str, ...]
    decisions: tuple[EmailDecision, ...]
    issues: tuple[str, ...]


def _identifier(value):
    if not isinstance(value, str) or not value.strip() or value != value.strip() or len(value) > 250:
        raise PolicyInputError('identifier_invalid')
    return value


def _accounts(accounts):
    result = {}
    for account in accounts:
        if type(account) is not EmailAccount:
            raise PolicyInputError('account_inventory_untrusted')
        uid = _identifier(account.account_id)
        if uid in result: raise PolicyInputError('account_identity_duplicate')
        result[uid] = account
    return result


def _rows(rows):
    if not isinstance(rows, (list, tuple)):
        raise PolicyInputError('record_inventory_invalid')
    result = {}
    for row in rows:
        if not isinstance(row, Mapping): raise PolicyInputError('record_inventory_invalid')
        code = _identifier(row.get('codigo'))
        if code in result: raise PolicyInputError('record_identity_duplicate')
        result[code] = row
    return result


def _actor(indexed, actor_id):
    actor = indexed.get(_identifier(actor_id))
    # Match the existing administrative authorization policy; do not promote anyone.
    if actor is None or actor.state != 'active' or actor.role != 'superadmin':
        raise PolicyInputError('active_superadmin_required')


def _sealed(value):
    object.__setattr__(value, '_seal', _SEAL)
    return value


def approve_primary_designation(designation_id, account_id, *, actor_id, accounts):
    """Validate a proposed designation in memory. No existing designation is replaced."""
    indexed = _accounts(accounts); _actor(indexed, actor_id)
    _identifier(designation_id); _identifier(account_id)
    account = indexed.get(account_id)
    if account is None: raise PolicyInputError('primary_account_missing')
    if account.state != 'active': raise PolicyInputError('primary_account_not_active')
    if account.role not in ADMIN_ROLES: raise PolicyInputError('primary_role_invalid')
    return _sealed(PrimaryDesignation(designation_id, account_id, actor_id))


def identify_primary_admin(accounts, designations=()):
    indexed = _accounts(accounts); active = []
    for designation in designations:
        if type(designation) is not PrimaryDesignation or designation._seal is not _SEAL:
            return PrimaryResolution(None, ('primary_designation_untrusted',))
        if designation.active is True: active.append(designation)
    if not active: return PrimaryResolution(None, ('primary_designation_missing',))
    if len(active) != 1: return PrimaryResolution(None, ('primary_designation_ambiguous',))
    account = indexed.get(active[0].account_id)
    if account is None: return PrimaryResolution(None, ('primary_account_missing',))
    if account.state != 'active': return PrimaryResolution(None, ('primary_account_not_active',))
    if account.role not in ADMIN_ROLES: return PrimaryResolution(None, ('primary_role_invalid',))
    return PrimaryResolution(account.account_id, ())


def evaluate_email_eligibility(account):
    if account is None: return email_eligibility_denials(None)
    if type(account) is not EmailAccount: raise PolicyInputError('account_inventory_untrusted')
    return email_eligibility_denials(dict(role=account.role, state=account.state,
                                        email=account.email, verified=account.verified,
                                        email_alerts=account.email_alerts))


def _record_identity(module, code, raw, snapshot):
    if module not in DATE_FIELDS: raise PolicyInputError('module_invalid')
    if (not isinstance(raw, Mapping) or not isinstance(snapshot, Mapping)
            or snapshot.get('format') != SNAPSHOT_FORMAT or snapshot.get('initialized') is not True):
        return None, ('snapshot_invalid',)
    row = _rows(raw.get(module, ())).get(code)
    if row is None: return None, ('record_missing',)
    records = snapshot.get('records')
    if not isinstance(records, Mapping) or not isinstance(records.get(module), Mapping):
        return None, ('snapshot_invalid',)
    state = records[module].get(code)
    if not isinstance(state, Mapping) or state.get('present') is not True:
        return None, ('record_snapshot_missing',)
    generation = state.get('generation')
    if type(generation) is not int or generation < 1: return None, ('snapshot_invalid',)
    if row.get('status') != state.get('status') or row.get(DATE_FIELDS[module]) != state.get('date'):
        return None, ('record_changed_since_snapshot',)
    if module == 'Renovacoes':
        access = _rows(raw.get('Acessos', ())).get(row.get('acesso'))
        if access is None: return None, ('linked_access_missing',)
        employee_code = access.get('funcionario')
    else: employee_code = row.get('funcionario')
    employee = _rows(raw.get('Funcionarios', ())).get(employee_code)
    if employee is None: return None, ('record_employee_missing',)
    team = employee.get('equipe')
    if team not in _rows(raw.get('Equipes', ())): return None, ('record_team_missing',)
    return RecordIdentity(module, code, generation, team), ()


def approve_email_authorization(grant_id, account_id, module, scope, *, actor_id, accounts,
                                raw, snapshot, team_code=None, record_code=None):
    """Explicit one-module grant. Record grants bind current generation AND team."""
    indexed = _accounts(accounts); _actor(indexed, actor_id)
    _identifier(grant_id); _identifier(account_id)
    if account_id not in indexed: raise PolicyInputError('authorization_account_missing')
    if module not in DATE_FIELDS: raise PolicyInputError('module_invalid')
    generation = None
    if scope == 'module':
        if team_code is not None or record_code is not None: raise PolicyInputError('scope_constraints_invalid')
    elif scope == 'team':
        _identifier(team_code)
        if record_code is not None or team_code not in _rows(raw.get('Equipes', ())):
            raise PolicyInputError('scope_constraints_invalid')
    elif scope == 'record':
        _identifier(record_code)
        record, issues = _record_identity(module, record_code, raw, snapshot)
        if issues: raise PolicyInputError(issues[0])
        if team_code is not None and team_code != record.team_code:
            raise PolicyInputError('scope_constraints_invalid')
        team_code, generation = record.team_code, record.generation
    else: raise PolicyInputError('scope_invalid')
    return _sealed(EmailAuthorization(grant_id, account_id, module, scope, actor_id,
                                      team_code, record_code, generation))


def revoke_email_authorization(grant, *, actor_id, accounts):
    _actor(_accounts(accounts), actor_id)
    if type(grant) is not EmailAuthorization or grant._seal is not _SEAL:
        raise PolicyInputError('authorization_untrusted')
    return _sealed(replace(grant, active=False, revoked_by=actor_id))


def _grant_denials(grant, record):
    if grant.active is not True: return ('authorization_revoked',)
    if grant.module != record.module: return ('module_mismatch',)
    if grant.team_code is not None and grant.team_code != record.team_code: return ('team_mismatch',)
    if grant.scope == 'record':
        if grant.record_code != record.code: return ('record_mismatch',)
        if grant.generation != record.generation: return ('record_generation_mismatch',)
    return ()


def resolve_email_recipients(event, raw, accounts, *, snapshot, primary_designations=(), authorizations=()):
    """Recompute content permission and email eligibility; never project internal notices."""
    if type(event) is not OperationalEvent: raise PolicyInputError('operational_event_required')
    indexed = _accounts(accounts)
    primary = identify_primary_admin(tuple(indexed.values()), primary_designations)
    grants = {}; candidates = set(indexed)
    for grant in authorizations:
        if type(grant) is not EmailAuthorization or grant._seal is not _SEAL:
            raise PolicyInputError('authorization_untrusted')
        if grant.grant_id in grants: raise PolicyInputError('authorization_identity_duplicate')
        grants[grant.grant_id] = grant; candidates.add(grant.account_id)
    record, event_issues = _record_identity(event.sheet, event.code, raw, snapshot)
    if not event_issues:
        try: superseded = is_superseded(event, snapshot)
        except (KeyError, TypeError): superseded = True
        if superseded: event_issues = ('event_superseded',)
        elif (event.generation != record.generation
              or snapshot['records'][event.sheet][event.code].get('status') != event.status
              or snapshot['records'][event.sheet][event.code].get('date') != event.date_value):
            event_issues = ('record_changed_since_event',)
    decisions = []
    for uid in sorted(candidates):
        owned = [g for g in grants.values() if g.account_id == uid]
        sources = []; denials = set()
        for grant in owned:
            reasons = _grant_denials(grant, record) if record is not None else ('record_not_current',)
            if reasons: denials.update(reasons)
            else: sources.append(grant.grant_id)
        if not owned: denials.add('authorization_missing')
        decisions.append(EmailDecision(uid, uid == primary.account_id, tuple(sorted(sources)),
                                       () if sources else tuple(sorted(denials)),
                                       evaluate_email_eligibility(indexed.get(uid)), event_issues))
    eligible = [d.account_id for d in decisions if d.email_allowed]
    eligible.sort(key=lambda uid: (uid != primary.account_id, uid))
    return EmailResolution(event.identity, primary.account_id, tuple(eligible), tuple(decisions),
                           tuple(sorted(set(primary.issues + event_issues))))


def revalidate_email_recipients(prepared, event, raw, accounts, **current_policy):
    """Use fresh trusted values before delivery; never add unprepared recipients."""
    if (type(prepared) is not EmailResolution or type(event) is not OperationalEvent
            or prepared.event_identity != event.identity):
        raise PolicyInputError('prepared_resolution_mismatch')
    current = resolve_email_recipients(event, raw, accounts, **current_policy)
    previous = set(prepared.email_account_ids)
    decisions = tuple(replace(d, authorization_denials=d.authorization_denials + ('not_in_prepared_recipients',))
                      if d.email_allowed and d.account_id not in previous else d for d in current.decisions)
    return replace(current, email_account_ids=tuple(uid for uid in current.email_account_ids if uid in previous),
                   decisions=decisions)
