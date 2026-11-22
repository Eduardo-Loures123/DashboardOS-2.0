"""Etapa 3B: pure, fail-closed resolution using explicitly confirmed grants.

No repository, Flask route, outbox or SMTP integration is installed here. Inputs
must come from a trusted caller, not request JSON. Confirmation helpers check the
existing active-superadmin policy; future persistence must enforce that policy
and audit grants/revocations atomically. Metadata is not a signed authorization.
"""
from collections import defaultdict
from dataclasses import dataclass
import re

from .enterprise_service import ROLES
from .operational_events import DATE_FIELDS, OperationalEvent, is_superseded


@dataclass(frozen=True)
class EmployeeAccountLink:
    employee_code: str
    user_id: str
    confirmed: bool = False
    confirmed_by: str | None = None
    active: bool = True


@dataclass(frozen=True)
class ManagerDesignation:
    sheet: str
    code: str
    generation: int
    user_id: str
    confirmed: bool = False
    confirmed_by: str | None = None
    active: bool = True


@dataclass(frozen=True)
class RecipientDecision:
    user_id: str
    authorization_sources: tuple[str, ...]
    internal_denials: tuple[str, ...]
    email_denials: tuple[str, ...]


@dataclass(frozen=True)
class RecipientResolution:
    event_identity: str
    internal_user_ids: tuple[str, ...]
    email_user_ids: tuple[str, ...]
    decisions: tuple[RecipientDecision, ...]
    issues: tuple[str, ...]

    @property
    def has_recipients(self):
        return bool(self.internal_user_ids or self.email_user_ids)


def _index(rows, field):
    result = {}
    for row in rows:
        code = row.get(field)
        if not isinstance(code, str) or not code.strip() or code in result:
            raise ValueError('Identificador ausente ou duplicado no inventário de destinatários.')
        result[code] = row
    return result


def _superadmin(actor_id, accounts):
    actor = accounts.get(actor_id)
    if not actor or actor.get('state') != 'active' or actor.get('role') != 'superadmin':
        raise PermissionError('Superadministrador ativo necessário para confirmar vínculos.')


def confirm_employee_link(employee_code, user_id, *, actor_id, accounts, employees):
    """Return metadata only. Does not write or replace any existing association."""
    indexed = _index(accounts, 'user_id')
    _superadmin(actor_id, indexed)
    if employee_code not in _index(employees, 'codigo') or user_id not in indexed:
        raise ValueError('Funcionário ou conta inexistente.')
    if indexed[user_id].get('role') not in ROLES:
        raise ValueError('Conta de destinatário inválida.')
    return EmployeeAccountLink(employee_code, user_id, True, actor_id)


def confirm_manager_designation(event, snapshot, user_id, *, actor_id, accounts):
    """An express grant for this record generation; never a role-wide grant."""
    indexed = _index(accounts, 'user_id')
    _superadmin(actor_id, indexed)
    if user_id not in indexed or indexed[user_id].get('role') not in ROLES:
        raise ValueError('Conta de gestor inexistente ou inválida.')
    if not isinstance(event, OperationalEvent) or is_superseded(event, snapshot):
        raise ValueError('Evento ausente ou superado para designação.')
    return ManagerDesignation(event.sheet, event.code, event.generation, user_id, True, actor_id)


def _confirmed(grant):
    return (grant.confirmed is True and grant.active is True
            and isinstance(grant.confirmed_by, str) and bool(grant.confirmed_by.strip()))


def _enabled(value):
    # SQLite uses 0/1; do not treat strings such as 'false' or '0' as opt-in.
    return value is True or type(value) is int and value == 1


def _decision(uid, sources, account):
    common = []
    if account is None:
        common.append('account_missing')
        account = {}
    else:
        if account.get('state') != 'active': common.append('account_not_active')
        if account.get('role') not in ROLES: common.append('account_role_invalid')
    internal = list(common)
    email = list(common)
    if not _enabled(account.get('internal_alerts')): internal.append('internal_opt_out')
    address = account.get('email')
    if not isinstance(address, str) or not address.strip(): email.append('email_missing')
    elif not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', address): email.append('email_invalid')
    if not _enabled(account.get('verified')): email.append('email_unverified')
    if not _enabled(account.get('email_alerts')): email.append('email_opt_out')
    return RecipientDecision(uid, tuple(sorted(sources)), tuple(internal), tuple(email))


def email_eligibility_denials(account):
    """Pure shared eligibility only; does not decide content access or internal notices."""
    return _decision('', (), account).email_denials


def resolve_recipients(event, raw, accounts, *, snapshot, employee_links=(), manager_designations=()):
    """Resolve current grants/preferences, with deterministic safe reason codes.

    A renewal involves its responsavel and the titular of its linked acesso.
    Equipes.responsavel is not a manager-notification grant. Ambiguous employee
    associations are excluded, pending a business decision on cardinality.
    Channel preferences are independent. No messages or audit rows are written.
    """
    if not isinstance(event, OperationalEvent) or event.sheet not in DATE_FIELDS:
        raise ValueError('Somente eventos operacionais da Etapa 3A são aceitos.')
    indexed_accounts = _index(accounts, 'user_id')
    people = _index(raw.get('Funcionarios', ()), 'codigo')
    records = _index(raw.get(event.sheet, ()), 'codigo')
    row = records.get(event.code)
    def empty(reason):
        return RecipientResolution(event.identity, (), (), (), (reason,))
    if row is None: return empty('record_missing')
    if is_superseded(event, snapshot): return empty('event_superseded')
    if row.get('status') != event.status or row.get(DATE_FIELDS[event.sheet]) != event.date_value:
        return empty('record_changed_since_event')

    involved = defaultdict(set)
    issues = set()
    if event.sheet == 'Renovacoes':
        involved[row.get('responsavel')].add('renewal_responsible')
        access = _index(raw.get('Acessos', ()), 'codigo').get(row.get('acesso'))
        if access: involved[access.get('funcionario')].add('access_holder')
        else: issues.add('linked_access_missing')
    else:
        involved[row.get('funcionario')].add('record_employee')

    by_employee = defaultdict(set)
    by_account = defaultdict(set)
    for link in employee_links:
        if not isinstance(link, EmployeeAccountLink): raise ValueError('Modelo de vínculo inválido.')
        if _confirmed(link):
            by_employee[link.employee_code].add(link.user_id)
            by_account[link.user_id].add(link.employee_code)
    authorized = defaultdict(set)
    for employee, sources in involved.items():
        if employee not in people:
            issues.add('involved_employee_missing')
            continue
        targets = by_employee.get(employee, set())
        if not targets:
            issues.add('employee_without_confirmed_account:' + employee)
        elif len(targets) != 1 or any(len(by_account[uid]) != 1 for uid in targets):
            issues.add('ambiguous_employee_account_link:' + employee)
        else:
            authorized[next(iter(targets))].update(source + ':' + employee for source in sources)

    for grant in manager_designations:
        if not isinstance(grant, ManagerDesignation): raise ValueError('Modelo de designação inválido.')
        if (_confirmed(grant) and grant.sheet == event.sheet and grant.code == event.code
                and grant.generation == event.generation):
            authorized[grant.user_id].add('designated_manager')
    if not any('designated_manager' in sources for sources in authorized.values()):
        issues.add('no_designated_manager')

    decisions = tuple(_decision(uid, sources, indexed_accounts.get(uid)) for uid, sources in sorted(authorized.items()))
    internal = tuple(d.user_id for d in decisions if not d.internal_denials)
    email = tuple(d.user_id for d in decisions if not d.email_denials)
    if not internal and not email: issues.add('no_eligible_recipients')
    return RecipientResolution(event.identity, internal, email, decisions, tuple(sorted(issues)))
