"""Etapa 3A: fictional inventories and caller-owned snapshots, no external I/O."""
import copy
from dataclasses import asdict
from datetime import date, datetime, timedelta, timezone
import json
import unittest
from unittest.mock import patch

from services.operational_events import (analyze_operational_events, equivalent_events,
                                         is_superseded, local_day)
from services.schema import STATUS


DAY = date(2026, 11, 4)


def inventory():
    return {'OrdensServico': [], 'Acessos': [], 'Renovacoes': []}


def record(sheet, days=46, status=None, code='TEST0001'):
    field = {'OrdensServico': 'previsao', 'Acessos': 'vencimento', 'Renovacoes': 'solicitacao'}[sheet]
    state = status or {'OrdensServico': 'Pendente', 'Acessos': 'Ativo', 'Renovacoes': 'Pendente'}[sheet]
    return {'codigo': code, 'status': state, field: (DAY + timedelta(days=days)).isoformat()}


class OperationalRulesTests(unittest.TestCase):
    def start(self, sheet='OrdensServico', days=46, status=None):
        raw = inventory(); raw[sheet] = [record(sheet, days, status)]
        return raw, analyze_operational_events(raw, now=DAY).snapshot

    def test_exact_deadline_boundaries_for_os_and_access(self):
        for sheet in ('OrdensServico', 'Acessos'):
            field = 'previsao' if sheet == 'OrdensServico' else 'vencimento'
            for days, band, alert in [(45, '31 a 45 dias', 'preventive'), (31, '31 a 45 dias', 'preventive'),
                                      (30, 'Até 30 dias', 'urgent'), (1, 'Até 30 dias', 'urgent'),
                                      (0, 'Vencem hoje', 'due_today'), (-1, 'Vencidos', 'overdue')]:
                with self.subTest(sheet=sheet, days=days):
                    raw, before = self.start(sheet)
                    raw[sheet][0][field] = (DAY + timedelta(days=days)).isoformat()
                    result = analyze_operational_events(raw, before, DAY)
                    self.assertEqual(len(result.events), 1)
                    self.assertEqual((result.events[0].band, result.events[0].deadline_alert), (band, alert))
                    self.assertEqual(result.events[0].date_revision, 1)

    def test_more_than_45_days_has_no_proximity_alert(self):
        raw, before = self.start(days=50)
        self.assertEqual(analyze_operational_events(raw, before, DAY + timedelta(days=1)).events, ())
        raw['OrdensServico'][0]['previsao'] = (DAY + timedelta(days=60)).isoformat()
        event, = analyze_operational_events(raw, before, DAY).events
        self.assertIsNone(event.deadline_alert)
        self.assertEqual(event.reasons, ('date_changed',))

    def test_first_activation_never_emits_urgent_or_old_records(self):
        raw = inventory()
        for sheet in ('OrdensServico', 'Acessos'):
            raw[sheet] = [record(sheet, days, code=str(i)) for i, days in enumerate((45, 31, 30, 1, 0, -10))]
        raw['Renovacoes'] = [record('Renovacoes', -20, state, state) for state in STATUS['Renovacoes']]
        result = analyze_operational_events(raw, now=DAY)
        self.assertEqual(result.events, ())
        self.assertEqual(analyze_operational_events(raw, result.snapshot, DAY).events, ())
        # Old seven-day reminders must not appear on a later scan either.
        self.assertFalse(any(e.sheet == 'Renovacoes' for e in
                             analyze_operational_events(raw, result.snapshot, DAY + timedelta(days=1)).events))

    def test_clock_crosses_each_band_once_with_fixed_deadline(self):
        raw, snapshot = self.start()
        for elapsed, expected in [(1, 'preventive'), (16, 'urgent'), (46, 'due_today'), (47, 'overdue')]:
            result = analyze_operational_events(raw, snapshot, DAY + timedelta(days=elapsed))
            event, = result.events
            self.assertEqual(event.deadline_alert, expected)
            self.assertEqual(event.reasons, ('band_changed',))
            self.assertEqual(event.date_revision, 0)
            self.assertEqual(analyze_operational_events(raw, result.snapshot, DAY + timedelta(days=elapsed)).events, ())
            snapshot = result.snapshot

    def test_skip_bands_emits_only_current_state(self):
        raw, snapshot = self.start()
        event, = analyze_operational_events(raw, snapshot, DAY + timedelta(days=48)).events
        self.assertEqual(event.deadline_alert, 'overdue')
        self.assertEqual(event.reasons, ('band_changed',))

    def test_simultaneous_changes_are_one_event(self):
        raw, snapshot = self.start()
        raw['OrdensServico'][0].update(status='Em andamento', previsao=DAY.isoformat())
        event, = analyze_operational_events(raw, snapshot, DAY).events
        self.assertEqual(set(event.reasons), {'status_changed', 'date_changed', 'band_changed'})
        self.assertEqual(event.deadline_alert, 'due_today')

    def test_same_band_date_change_starts_new_date_revision(self):
        raw, snapshot = self.start(days=20)
        raw['OrdensServico'][0]['previsao'] = (DAY + timedelta(days=25)).isoformat()
        result = analyze_operational_events(raw, snapshot, DAY)
        event, = result.events
        self.assertEqual(event.reasons, ('date_changed',))
        self.assertEqual(event.date_revision, 1)
        self.assertEqual(analyze_operational_events(raw, result.snapshot, DAY).events, ())

    def test_completion_and_revocation_end_deadline_alerts(self):
        for sheet, closed in [('OrdensServico', 'Concluída'), ('Acessos', 'Revogado')]:
            with self.subTest(sheet=sheet):
                raw, snapshot = self.start(sheet, days=1)
                raw[sheet][0]['status'] = closed
                result = analyze_operational_events(raw, snapshot, DAY)
                event, = result.events
                self.assertIn('monitoring_ended', event.reasons)
                self.assertIsNone(event.deadline_alert)
                self.assertEqual(event.band, 'Encerrado')
                self.assertEqual(analyze_operational_events(raw, result.snapshot, DAY + timedelta(days=50)).events, ())

    def test_reopening_and_reactivation_use_current_state_only(self):
        for sheet, closed, active in [('OrdensServico', 'Concluída', 'Pendente'), ('Acessos', 'Revogado', 'Ativo')]:
            raw, snapshot = self.start(sheet, days=-3, status=closed)
            raw[sheet][0]['status'] = active
            result = analyze_operational_events(raw, snapshot, DAY)
            event, = result.events
            self.assertIn('reactivated', event.reasons)
            self.assertEqual(event.deadline_alert, 'overdue')
            self.assertEqual(analyze_operational_events(raw, result.snapshot, DAY).events, ())

    def test_editing_closed_record_is_information_without_deadline_alert(self):
        raw, snapshot = self.start(status='Concluída')
        raw['OrdensServico'][0]['previsao'] = DAY.isoformat()
        event, = analyze_operational_events(raw, snapshot, DAY).events
        self.assertEqual(event.reasons, ('date_changed',))
        self.assertIsNone(event.deadline_alert)

    def test_new_records_after_activation_respect_attention_bands(self):
        empty = analyze_operational_events(inventory(), now=DAY).snapshot
        for sheet in ('OrdensServico', 'Acessos'):
            for days, count in [(46, 0), (45, 1), (0, 1), (-1, 1)]:
                raw = inventory(); raw[sheet] = [record(sheet, days)]
                result = analyze_operational_events(raw, empty, DAY)
                self.assertEqual(len(result.events), count)
                self.assertEqual(analyze_operational_events(raw, result.snapshot, DAY).events, ())

    def test_renewal_creation_in_all_existing_states(self):
        empty = analyze_operational_events(inventory(), now=DAY).snapshot
        for state in STATUS['Renovacoes']:
            with self.subTest(state=state):
                raw = inventory(); raw['Renovacoes'] = [record('Renovacoes', -1, state)]
                event, = analyze_operational_events(raw, empty, DAY).events
                self.assertEqual(event.reasons, ('created',))
                self.assertEqual(event.status, state)
                self.assertIsNone(event.deadline_alert)
                self.assertIsNone(event.band)

    def test_renewal_status_changes_in_all_existing_states(self):
        raw, snapshot = self.start('Renovacoes', days=-1)
        for state in STATUS['Renovacoes'][1:] + ['Pendente']:
            raw['Renovacoes'][0]['status'] = state
            result = analyze_operational_events(raw, snapshot, DAY)
            event, = result.events
            self.assertIn('status_changed', event.reasons)
            snapshot = result.snapshot

    def test_seven_day_reminder_for_each_follow_up_status(self):
        for state in ('Pendente', 'Solicitada', 'Em análise', 'Aprovada'):
            with self.subTest(state=state):
                raw, snapshot = self.start('Renovacoes', days=-6, status=state)
                self.assertEqual(analyze_operational_events(raw, snapshot, DAY).events, ())
                result = analyze_operational_events(raw, snapshot, DAY + timedelta(days=1))
                event, = result.events
                self.assertEqual(event.reasons, ('seven_day_reminder',))
                self.assertEqual(analyze_operational_events(raw, result.snapshot, DAY + timedelta(days=2)).events, ())

    def test_closed_renewals_have_no_seven_day_reminder(self):
        for state in ('Concluída', 'Rejeitada'):
            raw, snapshot = self.start('Renovacoes', days=-6, status=state)
            self.assertEqual(analyze_operational_events(raw, snapshot, DAY + timedelta(days=1)).events, ())

    def test_missed_seventh_day_is_handled_once_after_initial_baseline(self):
        raw, snapshot = self.start('Renovacoes', days=-2)
        result = analyze_operational_events(raw, snapshot, DAY + timedelta(days=10))
        event, = result.events
        self.assertIn('seven_day_reminder', event.reasons)
        self.assertEqual(analyze_operational_events(raw, result.snapshot, DAY + timedelta(days=11)).events, ())

    def test_reminder_and_status_change_are_consolidated(self):
        raw, snapshot = self.start('Renovacoes', days=-6)
        raw['Renovacoes'][0]['status'] = 'Em análise'
        event, = analyze_operational_events(raw, snapshot, DAY + timedelta(days=1)).events
        self.assertEqual(set(event.reasons), {'status_changed', 'seven_day_reminder'})

    def test_changing_request_date_or_reopening_does_not_repeat_reminder(self):
        raw, snapshot = self.start('Renovacoes', days=-6)
        result = analyze_operational_events(raw, snapshot, DAY + timedelta(days=1))
        raw['Renovacoes'][0].update(solicitacao=(DAY - timedelta(days=8)).isoformat(), status='Concluída')
        closed = analyze_operational_events(raw, result.snapshot, DAY + timedelta(days=1))
        raw['Renovacoes'][0]['status'] = 'Pendente'
        reopened = analyze_operational_events(raw, closed.snapshot, DAY + timedelta(days=2))
        self.assertEqual(len(reopened.events), 1)
        self.assertNotIn('seven_day_reminder', reopened.events[0].reasons)

    def test_approval_does_not_extend_related_access(self):
        raw, snapshot = self.start('Renovacoes', days=-1)
        raw['Acessos'] = [record('Acessos', days=-1)]
        snapshot = analyze_operational_events(raw, snapshot, DAY).snapshot
        before = copy.deepcopy(raw)
        raw['Renovacoes'][0]['status'] = 'Aprovada'
        result = analyze_operational_events(raw, snapshot, DAY)
        self.assertEqual(raw['Acessos'], before['Acessos'])
        self.assertEqual(len(result.events), 1)
        self.assertEqual(result.snapshot['records']['Acessos']['TEST0001']['band'], 'Vencidos')

    def test_replay_from_same_snapshot_has_equivalent_identity(self):
        raw, snapshot = self.start()
        raw['OrdensServico'][0]['status'] = 'Em andamento'
        first = analyze_operational_events(raw, snapshot, DAY)
        second = analyze_operational_events(raw, snapshot, DAY)
        self.assertTrue(equivalent_events(first.events[0], second.events[0]))
        self.assertEqual(first, second)

    def test_different_changes_from_same_checkpoint_are_not_equivalent(self):
        raw, snapshot = self.start()
        raw['OrdensServico'][0]['previsao'] = DAY.isoformat()
        first = analyze_operational_events(raw, snapshot, DAY)
        raw['OrdensServico'][0]['previsao'] = (DAY - timedelta(days=1)).isoformat()
        second = analyze_operational_events(raw, snapshot, DAY)
        self.assertFalse(equivalent_events(first.events[0], second.events[0]))

    def test_removing_and_restoring_renewal_does_not_repeat_handled_reminder(self):
        raw, snapshot = self.start('Renovacoes', days=-6)
        first = analyze_operational_events(raw, snapshot, DAY + timedelta(days=1))
        removed = analyze_operational_events(inventory(), first.snapshot, DAY + timedelta(days=1))
        restored = analyze_operational_events(raw, removed.snapshot, DAY + timedelta(days=2))
        event, = restored.events
        self.assertIn('restored', event.reasons)
        self.assertNotIn('seven_day_reminder', event.reasons)

    def test_json_checkpoint_restores_deduplication_after_restart(self):
        raw, snapshot = self.start('Renovacoes', days=-6)
        result = analyze_operational_events(raw, snapshot, DAY + timedelta(days=1))
        restored = json.loads(json.dumps(result.snapshot))
        self.assertEqual(analyze_operational_events(raw, restored, DAY + timedelta(days=2)).events, ())
        json.dumps(asdict(result.events[0]))

    def test_aba_status_transitions_get_distinct_identities(self):
        raw, snapshot = self.start()
        identities = []
        for state in ('Em andamento', 'Pendente', 'Em andamento'):
            raw['OrdensServico'][0]['status'] = state
            result = analyze_operational_events(raw, snapshot, DAY)
            identities.append(result.events[0].identity)
            snapshot = result.snapshot
        self.assertEqual(len(set(identities)), 3)

    def test_newer_state_supersedes_previous_event_without_mutating_it(self):
        raw, snapshot = self.start()
        raw['OrdensServico'][0]['previsao'] = DAY.isoformat()
        first = analyze_operational_events(raw, snapshot, DAY)
        event = first.events[0]; original = asdict(event)
        self.assertFalse(is_superseded(event, first.snapshot))
        raw['OrdensServico'][0]['status'] = 'Concluída'
        second = analyze_operational_events(raw, first.snapshot, DAY)
        self.assertTrue(is_superseded(event, second.snapshot))
        self.assertEqual(second.events[0].supersedes, event.identity)
        self.assertEqual(asdict(event), original)

    def test_removed_and_recreated_code_cannot_reuse_old_identity(self):
        raw, snapshot = self.start(days=1)
        first = analyze_operational_events(raw, snapshot, DAY + timedelta(days=1))
        removed = analyze_operational_events(inventory(), first.snapshot, DAY + timedelta(days=1))
        self.assertTrue(is_superseded(first.events[0], removed.snapshot))
        recreated = analyze_operational_events(raw, removed.snapshot, DAY + timedelta(days=1))
        event, = recreated.events
        self.assertIn('restored', event.reasons)
        self.assertEqual(event.generation, 2)
        self.assertNotEqual(first.events[0].identity, event.identity)

    def test_same_code_in_different_sheets_has_distinct_identity(self):
        raw = inventory()
        empty = analyze_operational_events(raw, now=DAY).snapshot
        for sheet in raw: raw[sheet] = [record(sheet, 1)]
        result = analyze_operational_events(raw, empty, DAY)
        self.assertEqual(len({event.identity for event in result.events}), 3)

    def test_inputs_are_not_mutated_and_no_io_or_channel_delivery_occurs(self):
        raw, snapshot = self.start()
        raw['OrdensServico'][0]['status'] = 'Em andamento'
        before_raw, before_snapshot = copy.deepcopy(raw), copy.deepcopy(snapshot)
        with patch('builtins.open', side_effect=AssertionError('No files')), \
             patch('sqlite3.connect', side_effect=AssertionError('No database')) as db, \
             patch('smtplib.SMTP', side_effect=AssertionError('No SMTP')) as smtp, \
             patch('socket.create_connection', side_effect=AssertionError('No network')):
            result = analyze_operational_events(raw, snapshot, DAY)
        self.assertEqual(raw, before_raw); self.assertEqual(snapshot, before_snapshot)
        db.assert_not_called(); smtp.assert_not_called()
        self.assertEqual(len(result.events), 1)
        self.assertFalse(hasattr(result, 'outbox'))

    def test_midnight_uses_sao_paulo_not_utc_and_is_not_nine_am_scheduling(self):
        raw, snapshot = self.start(days=1)
        before_midnight = datetime(2026, 11, 5, 2, 59, tzinfo=timezone.utc)
        midnight = datetime(2026, 11, 5, 3, 0, tzinfo=timezone.utc)
        self.assertEqual(local_day(before_midnight), DAY)
        self.assertEqual(analyze_operational_events(raw, snapshot, before_midnight).events, ())
        result = analyze_operational_events(raw, snapshot, midnight)
        self.assertEqual(result.events[0].deadline_alert, 'due_today')
        self.assertEqual(result.events[0].occurred_on, '2026-11-05')
        self.assertEqual(analyze_operational_events(raw, result.snapshot,
                         datetime(2026, 11, 5, 12, 0, tzinfo=timezone.utc)).events, ())

    def test_reminder_uses_calendar_days_across_month_boundary(self):
        raw, snapshot = self.start('Renovacoes', days=-6)
        self.assertEqual(raw['Renovacoes'][0]['solicitacao'], '2026-10-29')
        result = analyze_operational_events(raw, snapshot, datetime(2026, 11, 5, 3, tzinfo=timezone.utc))
        self.assertEqual(result.events[0].reasons, ('seven_day_reminder',))

    def test_naive_time_and_backwards_business_date_are_rejected(self):
        raw, snapshot = self.start()
        with self.assertRaises(ValueError): analyze_operational_events(raw, snapshot, datetime(2026, 11, 4))
        with self.assertRaises(ValueError): analyze_operational_events(raw, snapshot, DAY - timedelta(days=1))

    def test_unknown_state_missing_date_and_incomplete_inventory_fail_safely(self):
        for changes in ({'status': 'Inventado'}, {'previsao': ''}, {'previsao': '2026-02-30'}):
            raw, snapshot = self.start()
            raw['OrdensServico'][0].update(changes)
            original = copy.deepcopy(snapshot)
            with self.assertRaises(ValueError): analyze_operational_events(raw, snapshot, DAY)
            self.assertEqual(snapshot, original)
        with self.assertRaises(ValueError): analyze_operational_events({'OrdensServico': []}, now=DAY)

    def test_duplicate_codes_are_rejected_without_returning_duplicate_events(self):
        raw, snapshot = self.start()
        raw['OrdensServico'].append(dict(raw['OrdensServico'][0]))
        with self.assertRaises(ValueError): analyze_operational_events(raw, snapshot, DAY)

    def test_snapshot_contract_is_not_the_existing_enterprise_database_schema(self):
        with self.assertRaises(ValueError): analyze_operational_events(inventory(), {'format': 999}, DAY)
