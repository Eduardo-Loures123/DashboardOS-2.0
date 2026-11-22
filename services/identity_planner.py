"""P1: pure identity planning. No repositories, clock, random tokens or I/O.

Inventories, complete history and continuity context are trusted caller inputs,
not browser proof. Allocations are symbolic until a future coordinator supplies
fresh tokens. A plan does not authorize, commit or deliver anything.
"""
from collections.abc import Mapping
from dataclasses import asdict, dataclass, replace
import hashlib
import json

from .schema import SCHEMA

MODULES = ('Acessos', 'OrdensServico', 'Renovacoes')
TRACKED = ('Equipes',) + MODULES
RELATIONS = (('Funcionarios', 'equipe', 'Equipes'), ('Equipes', 'responsavel', 'Funcionarios'),
             ('OrdensServico', 'funcionario', 'Funcionarios'), ('Acessos', 'funcionario', 'Funcionarios'),
             ('Renovacoes', 'acesso', 'Acessos'), ('Renovacoes', 'responsavel', 'Funcionarios'))


@dataclass(frozen=True, order=True)
class RecordKey:
    module: str
    code: str


@dataclass(frozen=True)
class DurableIdentity:
    key: RecordKey
    incarnation: str
    generation: int
    present: bool
    team_code: str | None = None
    team_generation: int | None = None
    operational_generation: int | None = None


@dataclass(frozen=True)
class PlanningContext:
    epoch: str
    revision: int
    source_revision: int
    source_token: str
    history_complete: bool = True


@dataclass(frozen=True)
class ProposedOperation:
    operation_id: str
    kind: str  # create, update, delete, recreate, import
    module: str | None = None
    code: str | None = None
    mode: str | None = None  # new/upsert only
    targets: tuple[RecordKey, ...] = ()  # exact uploaded keys, not the whole final inventory
    continuations: tuple[RecordKey, ...] = ()  # explicit existing objects updated by upsert


@dataclass(frozen=True)
class TokenAllocation:
    key: RecordKey
    token: str


@dataclass(frozen=True)
class AllocationNeed:
    operation_id: str
    key: RecordKey


@dataclass(frozen=True)
class PlannedIdentity:
    key: RecordKey
    incarnation: str | AllocationNeed
    generation: int
    team_code: str | None = None
    team_generation: int | None = None
    operational_generation: int | None = None


@dataclass(frozen=True)
class IdentityTransition:
    key: RecordKey
    action: str
    before: DurableIdentity | None
    after: PlannedIdentity | None
    reasons: tuple[str, ...]
    changed_fields: tuple[str, ...]


@dataclass(frozen=True)
class DependencyImpact:
    source: RecordKey
    target: RecordKey
    fields: tuple[str, ...]


@dataclass(frozen=True)
class PlanIssue:
    code: str
    module: str = ''
    record_code: str = ''
    field: str = ''


@dataclass(frozen=True)
class IdentityPlan:
    operation_type: str
    module: str | None = None
    record_code: str | None = None
    applicable: bool = False
    direct_transitions: tuple[IdentityTransition, ...] = ()
    indirect_transitions: tuple[IdentityTransition, ...] = ()
    preserved_identities: tuple[PlannedIdentity, ...] = ()
    identities_to_end: tuple[DurableIdentity, ...] = ()
    identities_to_create: tuple[PlannedIdentity, ...] = ()
    tombstones: tuple[DurableIdentity, ...] = ()
    resulting_identities: tuple[PlannedIdentity, ...] = ()
    allocations_needed: tuple[AllocationNeed, ...] = ()
    affected_dependencies: tuple[DependencyImpact, ...] = ()
    import_outcomes: tuple[tuple[RecordKey, str], ...] = ()
    issues: tuple[PlanIssue, ...] = ()
    before_fingerprint: str = ''
    after_fingerprint: str = ''
    history_fingerprint: str = ''
    context_fingerprint: str = ''
    plan_fingerprint: str = ''

    @property
    def ready_for_manifest(self):
        return self.applicable and not self.allocations_needed


class _Refusal(Exception):
    def __init__(self, issue):
        self.issue = issue


def _deny(code, key=None, field=''):
    raise _Refusal(PlanIssue(code, key.module if key else '', key.code if key else '', field))


def _text(value):
    return type(value) is str and 0 < len(value) <= 250 and value == value.strip()


def _positive(value):
    return type(value) is int and value > 0


def _key(key):
    if type(key) is not RecordKey or type(key.module) is not str or key.module not in SCHEMA or not _text(key.code):
        _deny('record_key_invalid')
    return key


def _digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def _inventory(raw):
    if not isinstance(raw, Mapping) or set(raw) != set(SCHEMA):
        _deny('inventory_incomplete_or_unknown_modules')
    indexed = {}
    for module in sorted(SCHEMA):
        if type(raw[module]) not in (list, tuple): _deny('inventory_rows_invalid')
        indexed[module] = {}
        for row in raw[module]:
            if not isinstance(row, Mapping) or any(type(k) is not str or type(v) is not str for k, v in row.items()):
                _deny('inventory_row_invalid')
            key = _key(RecordKey(module, row.get('codigo')))
            if key.code in indexed[module]: _deny('record_code_duplicate', key)
            indexed[module][key.code] = dict(row)
    for module, field, target in RELATIONS:
        for code, row in sorted(indexed[module].items()):
            if row.get(field) not in indexed[target]:
                _deny('reference_missing', RecordKey(module, code), field)
    return indexed


def _canonical_inventory(indexed):
    return {module: [rows[code] for code in sorted(rows)] for module, rows in sorted(indexed.items())}


def _team(indexed, key):
    row = indexed[key.module][key.code]
    access = indexed['Acessos'][row['acesso']] if key.module == 'Renovacoes' else row
    return indexed['Funcionarios'][access['funcionario']]['equipe']


def _path(indexed, key):
    """Authorization dependency path, excluding renewal responsible's team."""
    if key.module not in MODULES or key.code not in indexed[key.module]: return ()
    row = indexed[key.module][key.code]
    path = []
    if key.module == 'Renovacoes':
        path.append((RecordKey('Acessos', row['acesso']), 'Renovacoes.acesso'))
        row = indexed['Acessos'][row['acesso']]
    employee = row['funcionario']
    path.extend(((RecordKey('Funcionarios', employee), 'funcionario'),
                 (RecordKey('Equipes', indexed['Funcionarios'][employee]['equipe']), 'Funcionarios.equipe')))
    return tuple(path)


def _history(identities, before):
    if type(identities) not in (tuple, list): _deny('identity_history_invalid')
    grouped = {}; owners = {}
    for identity in identities:
        if type(identity) is not DurableIdentity: _deny('identity_history_untrusted')
        key = _key(identity.key)
        if key.module not in TRACKED or not _text(identity.incarnation) or not _positive(identity.generation) or type(identity.present) is not bool:
            _deny('identity_shape_invalid', key)
        if identity.incarnation == key.code: _deny('incarnation_is_visible_code', key)
        if identity.incarnation in owners and owners[identity.incarnation] != key:
            _deny('incarnation_reused', key)
        owners[identity.incarnation] = key
        if key.module == 'Equipes':
            if any(v is not None for v in (identity.team_code, identity.team_generation, identity.operational_generation)):
                _deny('team_identity_shape_invalid', key)
        elif not _text(identity.team_code) or not _positive(identity.team_generation) or not _positive(identity.operational_generation):
            _deny('record_identity_shape_invalid', key)
        grouped.setdefault(key, []).append(identity)
    latest = {}; all_teams = {}
    for key, rows in sorted(grouped.items()):
        rows.sort(key=lambda i: i.generation)
        if [i.generation for i in rows] != list(range(1, len(rows) + 1)):
            _deny('identity_generation_gap_or_duplicate', key)
        used = set(); previous = None
        for index, identity in enumerate(rows):
            if identity.present and index != len(rows) - 1: _deny('identity_presence_ambiguous', key)
            same_life = previous is not None and previous.incarnation == identity.incarnation
            if identity.incarnation in used and not same_life: _deny('incarnation_reused', key)
            if key.module == 'Equipes' and identity.incarnation in used: _deny('incarnation_reused', key)
            if key.module in MODULES:
                expected = identity.operational_generation if previous is None else previous.operational_generation + (0 if same_life else 1)
                if identity.operational_generation != expected: _deny('operational_generation_incompatible', key)
                if same_life and (identity.team_code, identity.team_generation) == (previous.team_code, previous.team_generation):
                    _deny('identity_generation_without_change', key)
            used.add(identity.incarnation); previous = identity
            if key.module == 'Equipes': all_teams[(key.code, identity.generation)] = identity
        latest[key] = rows[-1]
        if rows[-1].present != (key.code in before[key.module]): _deny('identity_inventory_mismatch', key)
    for module in TRACKED:
        for code in sorted(before[module]):
            key = RecordKey(module, code)
            if key not in latest: _deny('identity_missing', key)
    for key, rows in grouped.items():
        if key.module == 'Equipes': continue
        for identity in rows:
            if (identity.team_code, identity.team_generation) not in all_teams: _deny('identity_team_history_missing', key)
        current = latest[key]
        if current.present:
            team = _team(before, key)
            actual_team = latest[RecordKey('Equipes', team)]
            if (current.team_code, current.team_generation) != (team, actual_team.generation):
                _deny('identity_team_mismatch', key)
    canonical = [asdict(identity) for key in sorted(grouped) for identity in grouped[key]]
    return latest, set(owners), _digest(canonical)


def _operation(operation, before, after):
    if type(operation) is not ProposedOperation or not _text(operation.operation_id): _deny('operation_invalid')
    if operation.kind not in ('create', 'update', 'delete', 'recreate', 'import'): _deny('operation_kind_invalid')
    if type(operation.targets) is not tuple or type(operation.continuations) is not tuple: _deny('operation_keys_invalid')
    for key in operation.targets + operation.continuations: _key(key)
    if len(set(operation.targets)) != len(operation.targets) or len(set(operation.continuations)) != len(operation.continuations):
        _deny('operation_key_duplicate')
    changed = {RecordKey(module, code) for module in SCHEMA for code in set(before[module]) | set(after[module])
               if before[module].get(code) != after[module].get(code)}
    outcomes = []
    if operation.kind == 'import':
        if operation.module is not None or operation.code is not None or operation.mode not in ('new', 'upsert'):
            _deny('import_operation_invalid')
        direct = set(operation.targets)
        if not changed <= direct: _deny('import_undeclared_change')
        existing = {key for key in direct if key.code in before[key.module]}
        required = existing if operation.mode == 'upsert' else set()
        if set(operation.continuations) != required: _deny('import_continuity_unproven')
        for key in sorted(direct):
            if key.code not in after[key.module]: _deny('import_deletion_forbidden', key)
            if key not in existing: outcome = 'added'
            elif operation.mode == 'new':
                if key in changed: _deny('import_new_updated_existing', key)
                outcome = 'ignored_existing'
            else: outcome = 'updated' if key in changed else 'unchanged'
            outcomes.append((key, outcome))
    else:
        key = _key(RecordKey(operation.module, operation.code))
        if operation.mode is not None or operation.targets or operation.continuations: _deny('operation_shape_invalid')
        if operation.kind == 'recreate' and key.module not in TRACKED: _deny('recreation_not_supported', key)
        present = (key.code in before[key.module], key.code in after[key.module])
        expected = {'create': (False, True), 'update': (True, True), 'delete': (True, False), 'recreate': (True, True)}
        if present != expected[operation.kind] or not changed <= {key}: _deny('operation_contradiction', key)
        direct = {key}
    return direct, changed, tuple(outcomes)


def plan_identity_transition(before, proposed, operation, identities, *, context, allocations=()):
    """Return a frozen complete plan, or a structured refusal with no partial actions.

    Context/history attestations must be verified by a future coordinator. No
    authorization or actual lineage can be established from this pure API alone.
    """
    kind = operation.kind if type(operation) is ProposedOperation and type(operation.kind) is str else ''
    try:
        if (type(context) is not PlanningContext or not _text(context.epoch)
                or type(context.revision) is not int or context.revision < 0
                or type(context.source_revision) is not int or context.source_revision < 0
                or type(context.source_token) is not str or (context.source_revision > 0 and not _text(context.source_token))):
            _deny('continuity_context_invalid')
        if context.history_complete is not True: _deny('identity_history_incomplete')
        old = _inventory(before); new = _inventory(proposed)
        latest, used_tokens, history_hash = _history(identities, old)
        direct, changed, outcomes = _operation(operation, old, new)
        dependency_sources = changed | (direct if operation.kind == 'recreate' else set())
        fresh = {RecordKey(module, code) for module in TRACKED for code in new[module]
                 if code not in old[module] or (operation.kind == 'recreate' and RecordKey(module, code) in direct)}
        supplied = {}
        if type(allocations) not in (tuple, list): _deny('allocations_invalid')
        for allocation in allocations:
            if type(allocation) is not TokenAllocation: _deny('allocation_untrusted')
            key = _key(allocation.key)
            if key not in fresh or key in supplied or not _text(allocation.token): _deny('allocation_invalid', key)
            if allocation.token == key.code: _deny('incarnation_is_visible_code', key)
            if allocation.token in used_tokens or allocation.token in supplied.values(): _deny('incarnation_reused', key)
            supplied[key] = allocation.token
        needs = tuple(AllocationNeed(operation.operation_id, key) for key in sorted(fresh) if key not in supplied)
        tokens = {key: supplied.get(key, AllocationNeed(operation.operation_id, key)) for key in fresh}
        result = {}; transitions = []; preserved = []; ended = []; created = []; impacts = []
        for key in sorted(set(latest) | {RecordKey(m, c) for m in TRACKED for c in new[m]},
                          key=lambda k: (k.module != 'Equipes', k.module, k.code)):
            previous = latest.get(key)
            if key.code not in new[key.module]:
                if previous.present:
                    ended.append(previous)
                    transitions.append(IdentityTransition(key, 'delete', previous, None, ('deleted',), ()))
                continue
            live = previous if previous and previous.present else None
            reasons = []
            if key in fresh: reasons.append('recreated' if previous else 'created')
            team_code = team_generation = op_generation = None
            if key.module in MODULES:
                team_code = _team(new, key)
                team_generation = result[RecordKey('Equipes', team_code)].generation
                op_generation = (previous.operational_generation + 1 if previous else 1) if key in fresh else live.operational_generation
                if live and (live.team_code, live.team_generation) != (team_code, team_generation):
                    reasons.append('effective_team_changed' if live.team_code != team_code else 'team_incarnation_changed')
                if live and _path(old, key) != _path(new, key): reasons.append('dependency_path_changed')
            identity_changed = key in fresh or bool(set(reasons) & {'effective_team_changed', 'team_incarnation_changed'})
            generation = (previous.generation + 1 if previous else 1) if identity_changed else live.generation
            candidate = PlannedIdentity(key, tokens[key] if key in fresh else live.incarnation,
                                        generation, team_code, team_generation, op_generation)
            result[key] = candidate
            fields = tuple(sorted(field for field in set(old[key.module].get(key.code, {})) | set(new[key.module][key.code])
                                  if old[key.module].get(key.code, {}).get(field) != new[key.module][key.code].get(field)))
            if identity_changed:
                created.append(candidate)
                if live: ended.append(live)
            else: preserved.append(candidate)
            if not reasons: reasons.append('content_changed' if key in changed else 'unchanged')
            action = ('recreate' if live else 'create') if key in fresh else ('rebind' if identity_changed else 'preserve')
            transition = IdentityTransition(key, action, live, candidate, tuple(reasons), fields)
            if key in direct or identity_changed or 'dependency_path_changed' in reasons: transitions.append(transition)
            if key.module in MODULES and (identity_changed or 'dependency_path_changed' in reasons):
                paths = set(_path(old, key)) | set(_path(new, key))
                for source in sorted({source for source, field in paths} & dependency_sources):
                    impacts.append(DependencyImpact(source, key, tuple(sorted({field for ref, field in paths if ref == source}))))
        for key in sorted(direct):
            if key.module == 'Funcionarios':
                fields = tuple(sorted(field for field in set(old[key.module].get(key.code, {})) | set(new[key.module].get(key.code, {}))
                                      if old[key.module].get(key.code, {}).get(field) != new[key.module].get(key.code, {}).get(field)))
                transitions.append(IdentityTransition(key, 'dependency_change' if fields else 'preserve', None, None,
                                                      ('employee_operation',) if fields else ('unchanged',), fields))
        canonical_operation = replace(operation, targets=tuple(sorted(operation.targets)), continuations=tuple(sorted(operation.continuations)))
        fingerprints = (_digest(_canonical_inventory(old)), _digest(_canonical_inventory(new)), history_hash, _digest(asdict(context)))
        plan_hash = _digest([*fingerprints, asdict(canonical_operation), [asdict(a) for a in sorted(allocations, key=lambda a: a.key)]])
        ended.sort(key=lambda i: i.key); created.sort(key=lambda i: i.key)
        return IdentityPlan(kind, operation.module, operation.code, True,
            tuple(sorted((t for t in transitions if t.key in direct), key=lambda t: t.key)),
            tuple(sorted((t for t in transitions if t.key not in direct), key=lambda t: t.key)),
            tuple(sorted(preserved, key=lambda i: i.key)), tuple(ended), tuple(created),
            tuple(replace(i, present=False) for i in ended), tuple(result[k] for k in sorted(result)), needs,
            tuple(sorted(impacts, key=lambda i: (i.source, i.target, i.fields))), outcomes, (), *fingerprints, plan_hash)
    except _Refusal as refusal:
        return IdentityPlan(kind, issues=(refusal.issue,))
