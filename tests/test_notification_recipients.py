"""Recipient authorization with fictional records only; no DB, queue or SMTP."""
import copy
from dataclasses import asdict, replace
from datetime import date
import json
import unittest
from unittest.mock import patch

from services.operational_events import analyze_operational_events
from services.notification_recipients import (EmployeeAccountLink, ManagerDesignation,
    confirm_employee_link, confirm_manager_designation, resolve_recipients)


DAY = date(2026, 11, 4)


def fictional_account(uid, **changes):
    return {**dict(user_id=uid, role='user', state='active', email=uid + '@example.test',
                   verified=1, internal_alerts=1, email_alerts=1), **changes}


class RecipientTests(unittest.TestCase):
    def setUp(self):
        self.accounts = [fictional_account(uid) for uid in ('staff1', 'staff2', 'manager', 'other')]
        self.accounts.append(fictional_account('root', role='superadmin'))
        self.raw = {
            'Funcionarios': [dict(codigo='FUNC0001', nome='Nome Semelhante', email='staff1@example.test', equipe='EQ0001'),
                            dict(codigo='FUNC0002', nome='Nome Semelhante', email='staff2@example.test', equipe='EQ0001')],
            'Equipes': [dict(codigo='EQ0001', responsavel='FUNC0002')],
            'OrdensServico': [dict(codigo='OS0001', funcionario='FUNC0001', status='Pendente', previsao='2026-11-06')],
            'Acessos': [dict(codigo='AC0001', funcionario='FUNC0001', status='Ativo', vencimento='2026-11-06')],
            'Renovacoes': [dict(codigo='REN0001', acesso='AC0001', responsavel='FUNC0002', status='Pendente', solicitacao='2026-11-03')],
        }
        self.baseline = analyze_operational_events(self.raw, now=DAY).snapshot
        self.use_event('OrdensServico')

    def use_event(self, sheet):
        if sheet == 'OrdensServico': self.raw[sheet][0]['status'] = 'Em andamento'
        elif sheet == 'Acessos': self.raw[sheet][0]['vencimento'] = '2026-11-04'
        else: self.raw[sheet][0]['status'] = 'Solicitada'
        result = analyze_operational_events(self.raw, self.baseline, DAY)
        self.snapshot = result.snapshot
        self.event = next(e for e in result.events if e.sheet == sheet)

    def account(self, uid):
        return next(a for a in self.accounts if a['user_id'] == uid)

    def link(self, employee='FUNC0001', uid='staff1', actor='root'):
        return confirm_employee_link(employee, uid, actor_id=actor,
                                     accounts=self.accounts, employees=self.raw['Funcionarios'])

    def manager(self, uid='manager', actor='root'):
        return confirm_manager_designation(self.event, self.snapshot, uid, actor_id=actor, accounts=self.accounts)

    def resolve(self, links=(), managers=()):
        return resolve_recipients(self.event, self.raw, self.accounts, snapshot=self.snapshot,
                                  employee_links=links, manager_designations=managers)

    def test_confirmed_employee_account_receives_both_channels(self):
        result = self.resolve([self.link()])
        self.assertEqual(result.internal_user_ids, ('staff1',))
        self.assertEqual(result.email_user_ids, ('staff1',))
        self.assertEqual(result.decisions[0].authorization_sources, ('record_employee:FUNC0001',))

    def test_employee_without_link_has_no_automatic_recipient(self):
        result = self.resolve()
        self.assertFalse(result.has_recipients)
        self.assertIn('employee_without_confirmed_account:FUNC0001', result.issues)
        self.assertIn('no_eligible_recipients', result.issues)

    def test_pending_and_unattributed_links_are_not_authorization(self):
        for link in (EmployeeAccountLink('FUNC0001', 'staff1'),
                     EmployeeAccountLink('FUNC0001', 'staff1', True),
                     EmployeeAccountLink('FUNC0001', 'staff1', True, ''),
                     replace(self.link(), active=False)):
            with self.subTest(link=link): self.assertFalse(self.resolve([link]).has_recipients)

    def test_express_manager_designation_is_sufficient_without_employee_link(self):
        result = self.resolve(managers=[self.manager()])
        self.assertEqual(result.email_user_ids, ('manager',))
        self.assertEqual(result.decisions[0].authorization_sources, ('designated_manager',))

    def test_no_manager_does_not_add_administrators(self):
        self.account('other')['role'] = 'admin'
        result = self.resolve([self.link()])
        self.assertEqual(result.email_user_ids, ('staff1',))
        self.assertIn('no_designated_manager', result.issues)
        self.assertNotIn('root', result.internal_user_ids)

    def test_multiple_managers_are_sorted_and_deduplicated(self):
        first, second = self.manager('manager'), self.manager('other')
        result = self.resolve(managers=[second, first, first])
        self.assertEqual(result.internal_user_ids, ('manager', 'other'))
        self.assertEqual(result.email_user_ids, ('manager', 'other'))

    def test_employee_who_is_also_manager_is_one_recipient_with_two_sources(self):
        link, manager = self.link(), self.manager('staff1')
        result = self.resolve([link, link], [manager, manager])
        self.assertEqual(result.email_user_ids, ('staff1',))
        self.assertEqual(len(result.decisions), 1)
        self.assertEqual(result.decisions[0].authorization_sources,
                         ('designated_manager', 'record_employee:FUNC0001'))

    def test_inactive_and_blocked_accounts_are_ineligible_for_both_channels(self):
        link = self.link()
        for state in ('inactive', 'blocked'):
            self.account('staff1')['state'] = state
            result = self.resolve([link])
            self.assertFalse(result.has_recipients)
            self.assertIn('account_not_active', result.decisions[0].email_denials)

    def test_unverified_email_does_not_disable_internal_channel(self):
        self.account('staff1')['verified'] = 0
        result = self.resolve([self.link()])
        self.assertEqual(result.internal_user_ids, ('staff1',))
        self.assertEqual(result.email_user_ids, ())
        self.assertIn('email_unverified', result.decisions[0].email_denials)

    def test_email_opt_out_does_not_disable_internal_channel(self):
        self.account('staff1')['email_alerts'] = 0
        result = self.resolve([self.link()])
        self.assertEqual(result.internal_user_ids, ('staff1',))
        self.assertEqual(result.email_user_ids, ())

    def test_internal_opt_out_does_not_disable_email_channel(self):
        self.account('staff1')['internal_alerts'] = 0
        result = self.resolve([self.link()])
        self.assertEqual(result.internal_user_ids, ())
        self.assertEqual(result.email_user_ids, ('staff1',))

    def test_missing_and_invalid_email_disable_only_email_channel(self):
        link = self.link()
        for address in ('', '   ', None, 'not-an-address', 'bad\n@example.test'):
            self.account('staff1')['email'] = address
            result = self.resolve([link])
            self.assertEqual(result.internal_user_ids, ('staff1',))
            self.assertEqual(result.email_user_ids, ())

    def test_preferences_are_rechecked_on_every_resolution(self):
        link = self.link()
        first = self.resolve([link])
        self.account('staff1').update(email_alerts=0, internal_alerts=0)
        self.assertFalse(self.resolve([link]).has_recipients)
        self.assertEqual(first.email_user_ids, ('staff1',))

    def test_revoked_manager_authorization_removes_future_eligibility(self):
        manager = self.manager()
        self.assertTrue(self.resolve(managers=[manager]).has_recipients)
        self.assertFalse(self.resolve(managers=[replace(manager, active=False)]).has_recipients)

    def test_link_change_uses_current_confirmed_association_only(self):
        old = self.link()
        self.assertEqual(self.resolve([old]).email_user_ids, ('staff1',))
        new = self.link(uid='staff2')
        result = self.resolve([replace(old, active=False), new])
        self.assertEqual(result.email_user_ids, ('staff2',))

    def test_ambiguous_employee_to_multiple_accounts_fails_closed(self):
        result = self.resolve([self.link(), self.link(uid='staff2')])
        self.assertFalse(result.has_recipients)
        self.assertIn('ambiguous_employee_account_link:FUNC0001', result.issues)

    def test_ambiguous_account_to_multiple_employees_fails_closed(self):
        result = self.resolve([self.link(), self.link('FUNC0002', 'staff1')])
        self.assertFalse(result.has_recipients)

    def test_similar_names_and_matching_email_never_authorize(self):
        self.account('staff1')['display_name'] = 'Nome Semelhante'
        self.assertEqual(self.account('staff1')['email'], self.raw['Funcionarios'][0]['email'])
        self.assertFalse(self.resolve().has_recipients)
        self.assertFalse(self.resolve([self.link('FUNC0002', 'staff2')]).has_recipients)

    def test_team_responsible_is_not_an_express_manager_grant(self):
        result = self.resolve([self.link('FUNC0002', 'staff2')])
        self.assertFalse(result.has_recipients)
        self.assertIn('no_designated_manager', result.issues)

    def test_only_active_superadmin_can_confirm_links_and_managers(self):
        for role, state in [('user', 'active'), ('admin', 'active'), ('superadmin', 'inactive'), ('superadmin', 'blocked')]:
            self.account('other').update(role=role, state=state)
            with self.subTest(role=role, state=state):
                with self.assertRaises(PermissionError): self.link(actor='other')
                with self.assertRaises(PermissionError): self.manager(actor='other')

    def test_confirmation_rejects_missing_employee_or_account(self):
        with self.assertRaises(ValueError): self.link('DOES-NOT-EXIST')
        with self.assertRaises(ValueError): self.link(uid='missing')
        with self.assertRaises(ValueError): self.manager('missing')

    def test_manager_role_does_not_grant_record_editing_permissions(self):
        before = copy.deepcopy(self.accounts)
        result = self.resolve(managers=[self.manager('staff2')])
        self.assertEqual(result.email_user_ids, ('staff2',))
        self.assertEqual(self.accounts, before)
        self.assertEqual(self.account('staff2')['role'], 'user')

    def test_integration_with_os_and_access_uses_record_employee(self):
        link = self.link()
        for sheet in ('OrdensServico', 'Acessos'):
            self.use_event(sheet)
            self.assertEqual(self.resolve([link]).email_user_ids, ('staff1',))

    def test_renewal_involves_responsible_and_linked_access_holder(self):
        self.use_event('Renovacoes')
        result = self.resolve([self.link(), self.link('FUNC0002', 'staff2')])
        self.assertEqual(result.email_user_ids, ('staff1', 'staff2'))
        sources = {d.user_id: d.authorization_sources for d in result.decisions}
        self.assertEqual(sources['staff1'], ('access_holder:FUNC0001',))
        self.assertEqual(sources['staff2'], ('renewal_responsible:FUNC0002',))

    def test_renewal_responsible_and_holder_same_person_is_not_duplicated(self):
        self.raw['Renovacoes'][0]['responsavel'] = 'FUNC0001'
        self.use_event('Renovacoes')
        result = self.resolve([self.link()])
        self.assertEqual(result.email_user_ids, ('staff1',))
        self.assertEqual(len(result.decisions[0].authorization_sources), 2)

    def test_manager_grant_is_scoped_by_record_type_code_and_generation(self):
        grant = self.manager()
        for changed in (replace(grant, sheet='Acessos'), replace(grant, code='OS0002'),
                        replace(grant, generation=2), replace(grant, confirmed=False)):
            self.assertFalse(self.resolve(managers=[changed]).has_recipients)

    def test_access_manager_is_not_implicitly_manager_of_renewal(self):
        self.use_event('Acessos'); grant = self.manager()
        self.use_event('Renovacoes')
        self.assertFalse(self.resolve(managers=[grant]).has_recipients)

    def test_missing_linked_access_reports_gap_without_broadcasting(self):
        self.use_event('Renovacoes'); self.raw['Acessos'] = []
        result = self.resolve([self.link('FUNC0002', 'staff2')])
        self.assertEqual(result.email_user_ids, ('staff2',))
        self.assertIn('linked_access_missing', result.issues)

    def test_missing_employee_does_not_fall_back_to_email_or_team(self):
        link = self.link(); self.raw['Funcionarios'] = []
        result = self.resolve([link])
        self.assertFalse(result.has_recipients)
        self.assertIn('involved_employee_missing', result.issues)

    def test_missing_account_is_diagnosed_and_not_eligible(self):
        link = self.link(); self.accounts = [a for a in self.accounts if a['user_id'] != 'staff1']
        result = self.resolve([link])
        self.assertFalse(result.has_recipients)
        self.assertIn('account_missing', result.decisions[0].email_denials)

    def test_unknown_role_and_string_preferences_are_not_opt_in(self):
        link = self.link()
        self.account('staff1')['role'] = 'guest'
        self.assertFalse(self.resolve([link]).has_recipients)
        self.account('staff1').update(role='user', internal_alerts='true', email_alerts='1', verified='1')
        self.assertFalse(self.resolve([link]).has_recipients)

    def test_newer_event_or_changed_record_invalidates_old_resolution(self):
        link = self.link()
        self.raw['OrdensServico'][0]['status'] = 'Concluída'
        self.assertIn('record_changed_since_event', self.resolve([link]).issues)
        self.snapshot = analyze_operational_events(self.raw, self.snapshot, DAY).snapshot
        self.assertIn('event_superseded', self.resolve([link]).issues)
        with self.assertRaises(ValueError): self.manager()

    def test_removed_record_cannot_route_to_previous_recipients(self):
        link = self.link(); self.raw['OrdensServico'] = []
        result = self.resolve([link])
        self.assertFalse(result.has_recipients)
        self.assertIn('record_missing', result.issues)

    def test_deterministic_resolution_and_safe_audit_metadata(self):
        links = [self.link(), self.link('FUNC0002', 'staff2')]
        managers = [self.manager('manager'), self.manager('other')]
        first = self.resolve(links, managers)
        second = self.resolve(list(reversed(links)), list(reversed(managers)))
        self.assertEqual(first, second)
        audit = json.dumps(asdict(first))
        self.assertNotIn('@', audit)
        self.assertNotIn('Nome Semelhante', audit)
        self.assertEqual(first.event_identity, self.event.identity)

    def test_ambiguous_employee_link_does_not_revoke_separate_express_manager_grant(self):
        result = self.resolve([self.link(), self.link(uid='staff2')], [self.manager('staff1')])
        self.assertEqual(result.email_user_ids, ('staff1',))
        self.assertEqual(result.decisions[0].authorization_sources, ('designated_manager',))

    def test_resolver_does_not_mutate_inputs_open_database_or_touch_smtp(self):
        link, grant = self.link(), self.manager()
        before = copy.deepcopy((self.raw, self.accounts, self.snapshot))
        with patch('builtins.open', side_effect=AssertionError('No files')), \
             patch('sqlite3.connect', side_effect=AssertionError('No DB')) as db, \
             patch('smtplib.SMTP', side_effect=AssertionError('No SMTP')) as smtp, \
             patch('socket.create_connection', side_effect=AssertionError('No network')):
            result = self.resolve([link], [grant])
        self.assertEqual((self.raw, self.accounts, self.snapshot), before)
        self.assertTrue(result.has_recipients)
        db.assert_not_called(); smtp.assert_not_called()

    def test_address_confirmation_is_not_an_operational_event(self):
        with self.assertRaises(ValueError):
            resolve_recipients({'purpose': 'verify'}, self.raw, self.accounts, snapshot=self.snapshot)

    def test_duplicate_account_and_employee_identifiers_fail_closed(self):
        self.accounts.append(dict(self.accounts[0]))
        with self.assertRaises(ValueError): self.resolve()
        self.accounts.pop()
        self.raw['Funcionarios'].append(dict(self.raw['Funcionarios'][0]))
        with self.assertRaises(ValueError): self.resolve()

    def test_reassignment_of_record_changes_current_authorized_recipient(self):
        links = [self.link(), self.link('FUNC0002', 'staff2')]
        self.assertEqual(self.resolve(links).email_user_ids, ('staff1',))
        self.raw['OrdensServico'][0]['funcionario'] = 'FUNC0002'
        self.assertEqual(self.resolve(links).email_user_ids, ('staff2',))
