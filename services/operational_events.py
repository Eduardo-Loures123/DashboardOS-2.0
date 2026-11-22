"""Pure operational rules (Etapa 3A), deliberately disconnected from the outbox.

Input/output snapshots are JSON-compatible values owned by the caller. Supplying
the saved snapshot makes reanalysis stable; this module never persists anything.
It neither resolves recipients nor creates internal notifications/email messages.
"""
from copy import deepcopy
from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import json
from zoneinfo import ZoneInfo

from .dashboard_service import categoria
from .schema import STATUS


TIMEZONE = ZoneInfo('America/Sao_Paulo')
SNAPSHOT_FORMAT = 1  # This is an in-memory contract, not a database migration.
DATE_FIELDS = {'OrdensServico': 'previsao', 'Acessos': 'vencimento', 'Renovacoes': 'solicitacao'}
FOLLOW_UP = {'OrdensServico': {'Pendente', 'Em andamento'}, 'Acessos': {'Ativo'},
             'Renovacoes': set(STATUS['Renovacoes']) - {'Concluída', 'Rejeitada'}}
ALERTS = {'31 a 45 dias': 'preventive', 'Até 30 dias': 'urgent',
          'Vencem hoje': 'due_today', 'Vencidos': 'overdue'}


@dataclass(frozen=True)
class OperationalEvent:
    """One logical change; channels can later project it independently."""
    identity: str
    sheet: str
    code: str
    generation: int
    revision: int
    date_revision: int
    reasons: tuple[str, ...]
    status: str
    date_value: str
    band: str | None
    deadline_alert: str | None
    occurred_on: str
    supersedes: str | None


@dataclass(frozen=True)
class OperationalAnalysis:
    events: tuple[OperationalEvent, ...]
    snapshot: dict


def local_day(now=None):
    """Dates are explicit business days; datetimes must include an offset."""
    if now is None:
        return datetime.now(TIMEZONE).date()
    if isinstance(now, datetime):
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError('Informe data/hora com fuso horário.')
        return now.astimezone(TIMEZONE).date()
    if isinstance(now, date):
        return now
    raise ValueError('Informe uma data ou data/hora com fuso horário.')


def _current(sheet, row, today):
    code = row.get('codigo')
    if not isinstance(code, str) or not code.strip():
        raise ValueError('Código de registro inválido.')
    status = row.get('status')
    if status not in STATUS[sheet]:
        raise ValueError('Estado operacional desconhecido.')
    try:
        value = date.fromisoformat(row[DATE_FIELDS[sheet]])
    except (KeyError, TypeError, ValueError):
        raise ValueError('Data operacional ausente ou inválida.') from None
    active = status in FOLLOW_UP[sheet]
    band = None if sheet == 'Renovacoes' else (
        categoria((value - today).days) if active else 'Encerrado')
    return code, {'status': status, 'date': value.isoformat(), 'band': band}, value


def _identity(sheet, code, generation, revision, current, reasons):
    # No run timestamp: replaying the same transition gives the same identity.
    key = json.dumps([SNAPSHOT_FORMAT, sheet, code, generation, revision, current, reasons],
                     ensure_ascii=False, sort_keys=True)
    return 'operational:' + hashlib.sha256(key.encode('utf-8')).hexdigest()


def _transition(sheet, code, current, value, old, today, baseline):
    present = old is not None and old['present']
    created = not present
    generation = (old['generation'] + 1 if old else 1) if created else old['generation']
    date_revision = old['date_revision'] if present else 0
    reasons = []
    if created:
        reasons.append('restored' if old else 'created')
    else:
        for field, reason in [('status', 'status_changed'), ('date', 'date_changed'), ('band', 'band_changed')]:
            if old[field] != current[field]: reasons.append(reason)
        if old['date'] != current['date']: date_revision += 1
        was_active = old['status'] in FOLLOW_UP[sheet]
        active = current['status'] in FOLLOW_UP[sheet]
        if was_active and not active: reasons.append('monitoring_ended')
        if active and not was_active: reasons.append('reactivated')

    # Removing/reinserting the same code does not authorize a second reminder.
    reminder_handled = old['reminder_handled'] if old else False
    if sheet == 'Renovacoes':
        seven_days = (today - value).days >= 7
        if baseline:
            # Do not turn a pre-activation overdue reminder into a later send.
            reminder_handled = seven_days
        elif seven_days and current['status'] in FOLLOW_UP[sheet] and not reminder_handled:
            reasons.append('seven_day_reminder')
            reminder_handled = True
        # Editing solicitacao never resets a reminder already handled.

    changed = bool(reasons)
    revision = (old['revision'] + 1 if old else 1) if changed else old['revision']
    if baseline: revision = 0
    event = None
    # Creation outside an attention band establishes a reference, not a deadline
    # notification. Renewals always classify creation, including terminal status.
    notify = (not created or sheet == 'Renovacoes' or current['band'] in ALERTS)
    latest = old['latest_event'] if old else None
    if changed and not baseline and notify:
        identity = _identity(sheet, code, generation, revision, current, reasons)
        event = OperationalEvent(identity, sheet, code, generation, revision, date_revision,
                                 tuple(reasons), current['status'], current['date'], current['band'],
                                 ALERTS.get(current['band']), today.isoformat(), latest)
        latest = identity
    state = {**current, 'generation': generation, 'revision': revision, 'date_revision': date_revision,
             'present': True, 'reminder_handled': reminder_handled, 'latest_event': latest}
    return state, event


def analyze_operational_events(raw, previous=None, now=None):
    """Analyze complete inventories without I/O or mutation of supplied values.

    None means first activation: seed all references, emitting no events. Later
    calls must include every monitored sheet; missing sheets are rejected rather
    than accidentally treating their records as removed. Removed codes retain
    tombstones so a later reappearance cannot reuse an old event identity.
    """
    today = local_day(now)
    baseline = previous is None
    if not baseline:
        if previous.get('format') != SNAPSHOT_FORMAT or not previous.get('initialized'):
            raise ValueError('Snapshot operacional incompatível.')
        if today < date.fromisoformat(previous['as_of']):
            raise ValueError('A análise não pode retroceder o dia do snapshot.')
    records = {} if baseline else deepcopy(previous['records'])
    events = []
    for sheet in DATE_FIELDS:
        if sheet not in raw:
            raise ValueError('Inventário operacional incompleto.')
        old_records = records.setdefault(sheet, {})
        seen = set()
        for row in raw[sheet]:
            code, current, value = _current(sheet, row, today)
            if code in seen: raise ValueError('Código operacional duplicado na mesma planilha.')
            seen.add(code)
            state, event = _transition(sheet, code, current, value, old_records.get(code), today, baseline)
            old_records[code] = state
            if event: events.append(event)
        for code in set(old_records) - seen:
            old_records[code]['present'] = False
    snapshot = {'format': SNAPSHOT_FORMAT, 'initialized': True, 'as_of': today.isoformat(), 'records': records}
    return OperationalAnalysis(tuple(sorted(events, key=lambda e: (e.sheet, e.code))), snapshot)


def equivalent_events(first, second):
    return first.identity == second.identity


def is_superseded(event, snapshot):
    """Supersession is advice for future projections, never an outbox update."""
    state = snapshot['records'].get(event.sheet, {}).get(event.code)
    return (state is None or not state['present'] or state['generation'] != event.generation
            or state['revision'] != event.revision or state['latest_event'] != event.identity)
