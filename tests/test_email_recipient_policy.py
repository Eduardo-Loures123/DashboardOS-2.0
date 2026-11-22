"""3C.1: fictional accounts/inventories only; no Flask, database or delivery."""
import copy
from dataclasses import asdict, replace
from datetime import date
import sys
import unittest

from services.operational_events import analyze_operational_events
from services.email_recipient_policy import (
    EmailAccount, EmailAuthorization, PrimaryDesignation, PolicyInputError,
    approve_primary_designation, identify_primary_admin, evaluate_email_eligibility,
    approve_email_authorization, revoke_email_authorization,
    resolve_email_recipients, revalidate_email_recipients,
)

DAY = date(2026, 11, 4)


class EmailPolicyTests(unittest.TestCase):
    def setUp(self):
        self.accounts = [EmailAccount(uid, role, 'active', uid + '@example.test', 1, 1)
                         for uid, role in [('root', 'superadmin'), ('root2', 'superadmin'),
                                           ('z-primary', 'admin'), ('alice', 'user'), ('bob', 'user')]]
        self.raw = {
            'Equipes': [dict(codigo='T1'), dict(codigo='T2')],
            'Funcionarios': [dict(codigo='F1', equipe='T1'), dict(codigo='F2', equipe='T2')],
            'OrdensServico': [dict(codigo='O1', funcionario='F1', status='Pendente', previsao='2026-11-06'),
                              dict(codigo='O2', funcionario='F2', status='Pendente', previsao='2026-11-06')],
            'Acessos': [dict(codigo='A1', funcionario='F1', status='Ativo', vencimento='2026-11-06')],
            'Renovacoes': [dict(codigo='R1', acesso='A1', responsavel='F2', status='Pendente', solicitacao='2026-11-03')],
        }
        self.snapshot = analyze_operational_events(self.raw, now=DAY).snapshot
        self.make_event()
        self.primary = approve_primary_designation('p1', 'z-primary', actor_id='root', accounts=self.accounts)

    def make_event(self, module='OrdensServico', code=None):
        row = next(r for r in self.raw[module] if code is None or r['codigo'] == code)
        if module == 'OrdensServico': row['status'] = 'Em andamento' if row['status'] == 'Pendente' else 'Pendente'
        elif module == 'Acessos': row['vencimento'] = '2026-11-04'
        else: row['status'] = 'Solicitada'
        result = analyze_operational_events(self.raw, self.snapshot, DAY)
        self.snapshot = result.snapshot
        self.event = next(e for e in result.events if e.sheet == module and e.code == row['codigo'])

    def change_account(self, uid='alice', **changes):
        self.accounts = [replace(a, **changes) if a.account_id == uid else a for a in self.accounts]

    def grant(self, uid='alice', module='OrdensServico', scope='module', grant_id='g1', **constraints):
        return approve_email_authorization(grant_id, uid, module, scope, actor_id='root',
                                           accounts=self.accounts, raw=self.raw, snapshot=self.snapshot, **constraints)

    def resolve(self, grants=(), **overrides):
        policy = dict(snapshot=self.snapshot, primary_designations=(self.primary,), authorizations=grants)
        policy.update(overrides)
        return resolve_email_recipients(self.event, self.raw, self.accounts, **policy)

    def decision(self, result, uid='alice'):
        return next(d for d in result.decisions if d.account_id == uid)

    def test_primary_explicit_unique_designation(self):
        result = identify_primary_admin(self.accounts, [self.primary])
        self.assertEqual((result.account_id, result.issues), ('z-primary', ()))

    def test_primary_missing_never_selects_one_of_multiple_superadmins(self):
        result = identify_primary_admin(self.accounts)
        self.assertIsNone(result.account_id)
        self.assertEqual(result.issues, ('primary_designation_missing',))

    def test_primary_duplicate_even_same_designation_is_ambiguous(self):
        other = approve_primary_designation('p2', 'root2', actor_id='root', accounts=self.accounts)
        for designations in ([self.primary, self.primary], [self.primary, other]):
            with self.subTest(designations=designations):
                self.assertEqual(identify_primary_admin(self.accounts, designations).issues,
                                 ('primary_designation_ambiguous',))

    def test_primary_missing_account_after_approval(self):
        self.accounts = [a for a in self.accounts if a.account_id != 'z-primary']
        self.assertEqual(identify_primary_admin(self.accounts, [self.primary]).issues, ('primary_account_missing',))

    def test_primary_inactive_or_blocked_after_approval(self):
        for state in ('inactive', 'blocked'):
            self.change_account('z-primary', state=state)
            self.assertEqual(identify_primary_admin(self.accounts, [self.primary]).issues, ('primary_account_not_active',))

    def test_primary_incompatible_role_after_approval(self):
        self.change_account('z-primary', role='user')
        self.assertEqual(identify_primary_admin(self.accounts, [self.primary]).issues, ('primary_role_invalid',))

    def test_primary_factory_rejects_invalid_targets(self):
        for uid, reason in [('missing', 'primary_account_missing'), ('alice', 'primary_role_invalid')]:
            with self.subTest(uid=uid), self.assertRaisesRegex(PolicyInputError, reason):
                approve_primary_designation('p2', uid, actor_id='root', accounts=self.accounts)
        self.change_account('z-primary', state='inactive')
        with self.assertRaisesRegex(PolicyInputError, 'primary_account_not_active'):
            approve_primary_designation('p2', 'z-primary', actor_id='root', accounts=self.accounts)

    def test_login_email_and_name_changes_preserve_stable_identity(self):
        grant = self.grant('z-primary')
        self.change_account('z-primary', login='new-login', email='new@example.test', display_name='Novo nome')
        result = self.resolve([grant])
        self.assertEqual(result.primary_account_id, 'z-primary')
        self.assertEqual(result.email_account_ids, ('z-primary',))

    def test_primary_priority_only_with_explicit_content_authorization(self):
        self.assertEqual(self.resolve([self.grant()]).email_account_ids, ('alice',))
        self.assertIn('authorization_missing', self.decision(self.resolve(), 'z-primary').authorization_denials)
        result = self.resolve([self.grant(), self.grant('z-primary', grant_id='gp')])
        self.assertEqual(result.email_account_ids, ('z-primary', 'alice'))

    def test_ineligible_primary_has_no_automatic_substitute(self):
        grant = self.grant('z-primary')
        self.change_account('z-primary', verified=False)
        result = self.resolve([grant])
        self.assertFalse(result.email_account_ids)
        self.assertIn('email_unverified', self.decision(result, 'z-primary').eligibility_denials)
        self.assertEqual(self.resolve([grant, self.grant(grant_id='ga')]).email_account_ids, ('alice',))

    def test_missing_or_ambiguous_primary_does_not_broaden_secondary_grants(self):
        for designations in ((), (self.primary, self.primary)):
            result = self.resolve([self.grant()], primary_designations=designations)
            self.assertIsNone(result.primary_account_id)
            self.assertEqual(result.email_account_ids, ('alice',))
            self.assertFalse(self.decision(result, 'root').email_allowed)

    def test_eligibility_and_strict_opt_in(self):
        good = self.accounts[-2]
        self.assertEqual(evaluate_email_eligibility(good), ())
        for change, reason in [({'verified': False}, 'email_unverified'), ({'verified': '1'}, 'email_unverified'),
                               ({'verified': 1.0}, 'email_unverified'), ({'email_alerts': 'true'}, 'email_opt_out'),
                               ({'email_alerts': False}, 'email_opt_out'), ({'state': 'blocked'}, 'account_not_active'),
                               ({'state': 'inactive'}, 'account_not_active'), ({'email': ''}, 'email_missing'),
                               ({'email': 'invalid'}, 'email_invalid'), ({'role': 'visitor'}, 'account_role_invalid')]:
            with self.subTest(change=change):
                self.assertIn(reason, evaluate_email_eligibility(replace(good, **change)))
        self.assertIn('account_missing', evaluate_email_eligibility(None))

    def test_module_grant_for_each_supported_module(self):
        for module in ('OrdensServico', 'Acessos', 'Renovacoes'):
            with self.subTest(module=module):
                if module != 'OrdensServico': self.make_event(module)
                self.assertEqual(self.resolve([self.grant(module=module)]).email_account_ids, ('alice',))

    def test_team_grant_for_each_supported_module(self):
        for module in ('OrdensServico', 'Acessos', 'Renovacoes'):
            with self.subTest(module=module):
                if module != 'OrdensServico': self.make_event(module)
                self.assertEqual(self.resolve([self.grant(module=module, scope='team', team_code='T1')]).email_account_ids, ('alice',))
                wrong = self.grant(module=module, scope='team', team_code='T2')
                self.assertIn('team_mismatch', self.decision(self.resolve([wrong])).authorization_denials)

    def test_record_grant_for_each_supported_module(self):
        for module, code in [('OrdensServico', 'O1'), ('Acessos', 'A1'), ('Renovacoes', 'R1')]:
            with self.subTest(module=module):
                if module != 'OrdensServico': self.make_event(module)
                grant = self.grant(module=module, scope='record', record_code=code)
                self.assertEqual((grant.team_code, grant.generation), ('T1', self.event.generation))
                self.assertEqual(self.resolve([grant]).email_account_ids, ('alice',))

    def test_other_record_same_module_is_denied(self):
        grant = self.grant(scope='record', record_code='O1')
        # Same team deliberately: the code restriction must still be checked.
        self.raw['OrdensServico'][1]['funcionario'] = 'F1'
        self.make_event(code='O2')
        self.assertIn('record_mismatch', self.decision(self.resolve([grant])).authorization_denials)

    def test_other_team_is_denied_despite_forged_visual_team(self):
        grant = self.grant(scope='team', team_code='T1')
        self.raw['OrdensServico'][1]['equipe'] = 'T1'
        self.make_event(code='O2')
        self.assertIn('team_mismatch', self.decision(self.resolve([grant])).authorization_denials)

    def test_renewal_responsible_team_does_not_broaden_access_holder_team(self):
        self.make_event('Renovacoes')
        grant = self.grant(module='Renovacoes', scope='team', team_code='T2')
        self.assertFalse(self.resolve([grant]).email_account_ids)

    def test_other_module_is_denied(self):
        grant = self.grant(module='Acessos')
        self.assertIn('module_mismatch', self.decision(self.resolve([grant])).authorization_denials)

    def test_revoked_grant_cannot_authorize(self):
        grant = revoke_email_authorization(self.grant(), actor_id='root', accounts=self.accounts)
        self.assertEqual(grant.revoked_by, 'root')
        self.assertIn('authorization_revoked', self.decision(self.resolve([grant])).authorization_denials)

    def test_record_grant_does_not_follow_a_team_move(self):
        grant = self.grant(scope='record', record_code='O1')
        self.raw['Funcionarios'][0]['equipe'] = 'T2'
        self.assertIn('team_mismatch', self.decision(self.resolve([grant])).authorization_denials)

    def test_record_recreation_requires_new_generation_grant(self):
        grant = self.grant(scope='record', record_code='O1')
        row = self.raw['OrdensServico'].pop(0)
        self.snapshot = analyze_operational_events(self.raw, self.snapshot, DAY).snapshot
        self.raw['OrdensServico'].append(row)
        result = analyze_operational_events(self.raw, self.snapshot, DAY)
        self.snapshot = result.snapshot
        self.event = next(e for e in result.events if e.code == 'O1')
        self.assertGreater(self.event.generation, grant.generation)
        self.assertIn('record_generation_mismatch', self.decision(self.resolve([grant])).authorization_denials)

    def test_no_cross_grant_mixing_or_implicit_employee_manager_access(self):
        grants = [self.grant(scope='team', team_code='T2'),
                  self.grant(module='Acessos', scope='team', team_code='T1', grant_id='g2')]
        self.assertFalse(self.resolve(grants).email_account_ids)
        self.assertTrue(all('authorization_missing' in d.authorization_denials for d in self.resolve().decisions))

    def test_multiple_complete_grants_deduplicate_recipient_and_keep_sources(self):
        result = self.resolve([self.grant(grant_id='z'), self.grant(scope='team', team_code='T1', grant_id='a')])
        self.assertEqual(result.email_account_ids, ('alice',))
        self.assertEqual(self.decision(result).authorization_sources, ('a', 'z'))

    def test_approval_requires_current_active_superadmin(self):
        for uid in ('alice', 'z-primary', 'missing'):
            with self.subTest(uid=uid), self.assertRaisesRegex(PolicyInputError, 'active_superadmin_required'):
                approve_primary_designation('p2', 'root2', actor_id=uid, accounts=self.accounts)
        self.change_account('root', state='blocked')
        with self.assertRaisesRegex(PolicyInputError, 'active_superadmin_required'): self.grant()

    def test_scope_shapes_wildcards_unknown_targets_and_teams_rejected(self):
        for kwargs in [dict(module='*'), dict(scope='*'), dict(uid='missing'),
                       dict(team_code='T1'), dict(scope='team', team_code='missing'),
                       dict(scope='team', team_code='T1', record_code='O1'),
                       dict(scope='record', record_code='missing'),
                       dict(scope='record', record_code='O1', team_code='T2')]:
            with self.subTest(kwargs=kwargs), self.assertRaises(PolicyInputError): self.grant(**kwargs)

    def test_browser_metadata_and_unsealed_or_reconstructed_grants_are_rejected(self):
        grant = self.grant()
        for untrusted in [asdict(grant), EmailAuthorization('g', 'alice', 'OrdensServico', 'module', 'root'),
                          replace(grant, module='Acessos'), copy.deepcopy(grant)]:
            with self.subTest(kind=type(untrusted)), self.assertRaisesRegex(PolicyInputError, 'authorization_untrusted'):
                self.resolve([untrusted])
        self.assertEqual(identify_primary_admin(self.accounts, [asdict(self.primary)]).issues,
                         ('primary_designation_untrusted',))
        direct = PrimaryDesignation('p', 'root', 'root')
        self.assertEqual(identify_primary_admin(self.accounts, [direct]).issues, ('primary_designation_untrusted',))
        with self.assertRaisesRegex(PolicyInputError, 'account_inventory_untrusted'):
            resolve_email_recipients(self.event, self.raw, [asdict(self.accounts[0])], snapshot=self.snapshot)

    def test_duplicate_account_record_or_grant_identity_rejected(self):
        grant = self.grant()
        with self.assertRaisesRegex(PolicyInputError, 'authorization_identity_duplicate'): self.resolve([grant, grant])
        self.accounts.append(self.accounts[0])
        with self.assertRaisesRegex(PolicyInputError, 'account_identity_duplicate'): self.resolve()
        self.accounts.pop()
        self.raw['OrdensServico'].append(self.raw['OrdensServico'][0].copy())
        with self.assertRaisesRegex(PolicyInputError, 'record_identity_duplicate'): self.resolve()

    def test_missing_references_deny_even_with_module_grant(self):
        grant = self.grant()
        for key, reason in [('Funcionarios', 'record_employee_missing'), ('Equipes', 'record_team_missing'),
                            ('OrdensServico', 'record_missing')]:
            original = self.raw[key]; self.raw[key] = []
            result = self.resolve([grant])
            self.assertFalse(result.email_account_ids)
            self.assertIn(reason, result.issues)
            self.raw[key] = original
        self.make_event('Renovacoes')
        self.raw['Acessos'] = []
        self.assertIn('linked_access_missing', self.resolve().issues)

    def test_changed_raw_record_denies_email(self):
        grant = self.grant()
        self.raw['OrdensServico'][0]['previsao'] = '2026-12-01'
        self.assertIn('record_changed_since_snapshot', self.resolve([grant]).issues)
        self.assertFalse(self.resolve([grant]).email_account_ids)

    def test_superseded_event_denied(self):
        grant = self.grant(); old = self.event
        self.make_event()
        self.event = old
        self.assertIn('event_superseded', self.resolve([grant]).issues)
        self.assertFalse(self.resolve([grant]).email_account_ids)

    def test_event_status_or_date_mismatch_denied(self):
        grant = self.grant(); original = self.event
        for change in (dict(status='forged'), dict(date_value='2026-12-01')):
            self.event = replace(original, **change)
            self.assertIn('record_changed_since_event', self.resolve([grant]).issues)
            self.assertFalse(self.resolve([grant]).email_account_ids)

    def test_malformed_snapshots_fail_closed(self):
        grant = self.grant()
        for snapshot in ({}, {'format': 1, 'initialized': True, 'records': []},
                         {'format': 1, 'initialized': True, 'records': {'OrdensServico': []}}):
            with self.subTest(snapshot=snapshot):
                self.assertFalse(self.resolve([grant], snapshot=snapshot).email_account_ids)

    def test_revalidation_revocation_and_removed_grant(self):
        grant = self.grant(); prepared = self.resolve([grant])
        for grants in ((), (revoke_email_authorization(grant, actor_id='root', accounts=self.accounts),)):
            result = revalidate_email_recipients(prepared, self.event, self.raw, self.accounts,
                                               snapshot=self.snapshot, authorizations=grants)
            self.assertFalse(result.email_account_ids)

    def test_revalidation_uses_current_account_state_email_and_preferences(self):
        grant = self.grant(); prepared = self.resolve([grant]); original = self.accounts[:]
        for changes in [dict(state='inactive'), dict(state='blocked'), dict(email=''),
                        dict(verified=False), dict(email_alerts=False), dict(role='visitor')]:
            with self.subTest(changes=changes):
                self.accounts = original[:]; self.change_account(**changes)
                result = revalidate_email_recipients(prepared, self.event, self.raw, self.accounts,
                                                   snapshot=self.snapshot, authorizations=[grant])
                self.assertFalse(result.email_account_ids)

    def test_deleted_account_denied_with_structured_reason(self):
        grant = self.grant()
        self.accounts = [a for a in self.accounts if a.account_id != 'alice']
        self.assertIn('account_missing', self.decision(self.resolve([grant])).eligibility_denials)
        self.assertFalse(self.resolve([grant]).email_account_ids)

    def test_revalidation_cannot_add_new_recipient_or_new_primary(self):
        grant = self.grant(); prepared = self.resolve([grant])
        primary = approve_primary_designation('p2', 'root2', actor_id='root', accounts=self.accounts)
        result = revalidate_email_recipients(prepared, self.event, self.raw, self.accounts,
                                            snapshot=self.snapshot, primary_designations=[primary],
                                            authorizations=[grant, self.grant('bob', grant_id='gb'),
                                                            self.grant('root2', grant_id='gr')])
        self.assertEqual(result.email_account_ids, ('alice',))
        self.assertIn('not_in_prepared_recipients', self.decision(result, 'root2').authorization_denials)

    def test_revalidation_rejects_other_prepared_event(self):
        prepared = self.resolve([self.grant()])
        with self.assertRaisesRegex(PolicyInputError, 'prepared_resolution_mismatch'):
            revalidate_email_recipients(prepared, replace(self.event, identity='other'), self.raw,
                                       self.accounts, snapshot=self.snapshot)

    def test_revalidation_uses_current_team_and_event_revision(self):
        grant = self.grant(scope='record', record_code='O1')
        prepared = self.resolve([grant])
        self.raw['Funcionarios'][0]['equipe'] = 'T2'
        result = revalidate_email_recipients(prepared, self.event, self.raw, self.accounts,
                                            snapshot=self.snapshot, authorizations=[grant])
        self.assertFalse(result.email_account_ids)
        self.raw['Funcionarios'][0]['equipe'] = 'T1'
        old_event = self.event
        self.make_event()
        result = revalidate_email_recipients(prepared, old_event, self.raw, self.accounts,
                                            snapshot=self.snapshot, authorizations=[grant])
        self.assertFalse(result.email_account_ids)
        self.assertIn('event_superseded', result.issues)

    def test_denied_grant_never_cancels_a_separate_complete_explicit_grant(self):
        denied = self.grant(scope='team', team_code='T2', grant_id='wrong-team')
        valid = self.grant(scope='record', record_code='O1', grant_id='record')
        result = self.resolve([denied, valid])
        self.assertEqual(result.email_account_ids, ('alice',))
        self.assertEqual(self.decision(result).authorization_sources, ('record',))

    def test_input_objects_unchanged_and_no_internal_or_legacy_delivery_contract(self):
        grant = self.grant()
        before = copy.deepcopy((self.raw, self.snapshot, self.accounts))
        result = self.resolve([grant])
        self.assertEqual((self.raw, self.snapshot, self.accounts), before)
        self.assertTrue(grant.active)
        self.assertFalse(hasattr(result, 'internal_user_ids'))
        self.assertFalse(hasattr(result, 'outbox'))
        for module in ('app', 'services.mail_service', 'services.auth_service', 'services.enterprise_routes'):
            self.assertNotIn(module, sys.modules)

