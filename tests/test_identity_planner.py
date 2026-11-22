"""P1: synthetic in-memory inventories and identity history only."""
import ast
from copy import deepcopy
from dataclasses import FrozenInstanceError, asdict, fields, replace
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from services.identity_planner import (
    AllocationNeed, DurableIdentity, PlanningContext, ProposedOperation, RecordKey,
    TokenAllocation, plan_identity_transition,
)

ROOT = Path(__file__).resolve().parents[1]


def inventory():
    return {
        'Equipes': [dict(codigo='T1', nome='Equipe 1', responsavel='F1'), dict(codigo='T2', nome='Equipe 2', responsavel='F2')],
        'Funcionarios': [dict(codigo='F1', equipe='T1', nome='Um'), dict(codigo='F2', equipe='T2', nome='Dois'), dict(codigo='F3', equipe='T1', nome='Tres')],
        'OrdensServico': [dict(codigo='O1', funcionario='F1', descricao='OS 1'), dict(codigo='O2', funcionario='F2', descricao='OS 2')],
        'Acessos': [dict(codigo='A1', funcionario='F1', sistema='Sistema 1'), dict(codigo='A2', funcionario='F2', sistema='Sistema 2')],
        'Renovacoes': [dict(codigo='R1', acesso='A1', responsavel='F2', observacoes='Um'), dict(codigo='R2', acesso='A2', responsavel='F1', observacoes='Dois')],
    }


def history(raw):
    people = {r['codigo']: r for r in raw['Funcionarios']}
    accesses = {r['codigo']: r for r in raw['Acessos']}
    result = []
    for module in ('Equipes', 'OrdensServico', 'Acessos', 'Renovacoes'):
        for row in raw[module]:
            team = None if module == 'Equipes' else people[(accesses[row['acesso']] if module == 'Renovacoes' else row)['funcionario']]['equipe']
            result.append(DurableIdentity(RecordKey(module, row['codigo']), module + '-' + row['codigo'] + '-life1',
                                          1, True, team, 1 if team else None, 1 if team else None))
    return tuple(result)


def advance_history(old, plan):
    """Fixture construction only. Does not apply anything to a repository or file."""
    ended = {(i.key, i.generation): i for i in plan.tombstones}
    result = [ended.get((i.key, i.generation), i) for i in old]
    for item in plan.identities_to_create:
        assert type(item.incarnation) is str
        result.append(DurableIdentity(item.key, item.incarnation, item.generation, True,
                                      item.team_code, item.team_generation, item.operational_generation))
    return tuple(result)


class IdentityPlannerTests(unittest.TestCase):
    def setUp(self):
        self.before = inventory(); self.after = deepcopy(self.before)
        self.identities = history(self.before)
        self.context = PlanningContext('epoch-test', 10, 4, 'source-4')

    def plan(self, kind='update', module='OrdensServico', code='O1', *, allocations=(), **changes):
        operation = ProposedOperation('operation-1', kind, module, code, **changes)
        return plan_identity_transition(self.before, self.after, operation, self.identities,
                                        context=self.context, allocations=allocations)

    def imported(self, mode, targets, continuations=()):
        return self.plan('import', None, None, mode=mode, targets=tuple(targets), continuations=tuple(continuations))

    def assert_refused(self, plan, reason=None):
        self.assertFalse(plan.applicable)
        self.assertFalse(plan.ready_for_manifest)
        self.assertTrue(plan.issues)
        if reason: self.assertEqual(plan.issues[0].code, reason)
        self.assertFalse(plan.direct_transitions or plan.indirect_transitions or plan.identities_to_create or plan.identities_to_end)

    def get(self, plan, module='OrdensServico', code='O1'):
        return next(i for i in plan.resulting_identities if i.key == RecordKey(module, code))

    def test_create_all_supported_entities_requires_allocation(self):
        for module, row in [('OrdensServico', dict(codigo='O3', funcionario='F1')),
                            ('Acessos', dict(codigo='A3', funcionario='F1')),
                            ('Renovacoes', dict(codigo='R3', acesso='A1', responsavel='F2')),
                            ('Equipes', dict(codigo='T3', responsavel='F1'))]:
            with self.subTest(module=module):
                self.after = deepcopy(self.before); self.after[module].append(row)
                plan = self.plan('create', module, row['codigo'])
                self.assertTrue(plan.applicable, plan.issues)
                self.assertFalse(plan.ready_for_manifest)
                need, = plan.allocations_needed
                self.assertIsInstance(self.get(plan, module, row['codigo']).incarnation, AllocationNeed)
                self.assertEqual(need.key, RecordKey(module, row['codigo']))
                self.assertFalse(plan.identities_to_end)

    def test_supplied_token_enables_manifest_readiness_without_generating_token(self):
        self.after['OrdensServico'].append(dict(codigo='O3', funcionario='F1'))
        allocation = TokenAllocation(RecordKey('OrdensServico', 'O3'), 'coordinator-fresh-token')
        plan = self.plan('create', code='O3', allocations=(allocation,))
        self.assertTrue(plan.ready_for_manifest)
        self.assertEqual(self.get(plan, code='O3').incarnation, allocation.token)

    def test_common_edit_preserves_every_identity_without_generation_change(self):
        self.after['OrdensServico'][0]['descricao'] = 'Nova descrição'
        plan = self.plan()
        self.assertTrue(plan.applicable)
        self.assertFalse(plan.identities_to_create or plan.identities_to_end)
        self.assertEqual(len(plan.preserved_identities), len(self.identities))
        self.assertEqual(plan.direct_transitions[0].changed_fields, ('descricao',))
        self.assertEqual(plan.direct_transitions[0].reasons, ('content_changed',))

    def test_noop_update_is_explicit_and_preserves_identity(self):
        plan = self.plan()
        self.assertTrue(plan.applicable)
        self.assertEqual(plan.direct_transitions[0].reasons, ('unchanged',))
        self.assertFalse(plan.identities_to_end)

    def test_names_and_team_responsible_do_not_change_generations(self):
        for module, field, value in [('Equipes', 'nome', 'Outro nome'), ('Equipes', 'responsavel', 'F3'),
                                     ('Funcionarios', 'nome', 'Novo nome'), ('Renovacoes', 'responsavel', 'F3')]:
            self.after = deepcopy(self.before); row = self.after[module][0]; row[field] = value
            with self.subTest(module=module, field=field):
                plan = self.plan(module=module, code=row['codigo'])
                self.assertTrue(plan.applicable, plan.issues)
                self.assertFalse(plan.identities_to_create or plan.identities_to_end)

    def test_delete_leaf_entities_produces_tombstone(self):
        for module in ('OrdensServico', 'Renovacoes'):
            self.after = deepcopy(self.before); row = self.after[module].pop(0)
            plan = self.plan('delete', module, row['codigo'])
            with self.subTest(module=module):
                self.assertTrue(plan.applicable)
                self.assertEqual(plan.identities_to_end[0].key.code, row['codigo'])
                self.assertFalse(plan.tombstones[0].present)
                self.assertEqual(plan.tombstones[0].incarnation, plan.identities_to_end[0].incarnation)

    def test_delete_access_and_team_without_dependents(self):
        for module, row in [('Equipes', dict(codigo='T3', responsavel='F1')),
                            ('Acessos', dict(codigo='A3', funcionario='F1'))]:
            self.before = inventory(); self.before[module].append(row)
            self.identities = history(self.before); self.after = deepcopy(self.before); self.after[module].pop()
            with self.subTest(module=module):
                self.assertTrue(self.plan('delete', module, row['codigo']).applicable)

    def test_delete_referenced_access_team_or_employee_is_refused(self):
        for module in ('Acessos', 'Equipes', 'Funcionarios'):
            self.after = deepcopy(self.before); row = self.after[module].pop(0)
            with self.subTest(module=module): self.assert_refused(self.plan('delete', module, row['codigo']), 'reference_missing')

    def test_deleted_code_recreated_uses_new_life_and_next_generations(self):
        self.after['OrdensServico'].pop(0); deleted = self.plan('delete')
        self.identities = advance_history(self.identities, deleted)
        self.before = deepcopy(self.after); self.after['OrdensServico'].append(dict(codigo='O1', funcionario='F1'))
        allocation = TokenAllocation(RecordKey('OrdensServico', 'O1'), 'new-life')
        plan = self.plan('create', allocations=(allocation,))
        self.assertTrue(plan.ready_for_manifest, plan.issues)
        current = self.get(plan)
        self.assertEqual((current.generation, current.operational_generation, current.incarnation), (2, 2, 'new-life'))
        self.assertFalse(plan.identities_to_end)  # original existence is already a tombstone

    def test_explicit_recreation_can_have_identical_business_data(self):
        plan = self.plan('recreate')
        self.assertTrue(plan.applicable)
        self.assertEqual(len(plan.identities_to_end), 1)
        self.assertEqual(self.get(plan).generation, 2)
        self.assertEqual(self.get(plan).operational_generation, 2)
        self.assertEqual(plan.direct_transitions[0].action, 'recreate')

    def test_recreation_cannot_reuse_current_or_old_token(self):
        token = self.identities[2].incarnation
        self.assert_refused(self.plan('recreate', allocations=(TokenAllocation(RecordKey('OrdensServico', 'O1'), token),)), 'incarnation_reused')
        self.after['OrdensServico'].pop(0); deleted = self.plan('delete')
        self.identities = advance_history(self.identities, deleted)
        self.before = deepcopy(self.after); self.after['OrdensServico'].append(dict(codigo='O1', funcionario='F1'))
        self.assert_refused(self.plan('create', allocations=(TokenAllocation(RecordKey('OrdensServico', 'O1'), token),)), 'incarnation_reused')

    def test_employee_transfer_fans_out_to_orders_accesses_and_renewals(self):
        self.after['Funcionarios'][0]['equipe'] = 'T2'
        plan = self.plan(module='Funcionarios', code='F1')
        self.assertTrue(plan.applicable)
        expected = {RecordKey('OrdensServico', 'O1'), RecordKey('Acessos', 'A1'), RecordKey('Renovacoes', 'R1')}
        self.assertEqual({t.key for t in plan.indirect_transitions}, expected)
        self.assertEqual({i.key for i in plan.identities_to_end}, expected)
        self.assertEqual({d.target for d in plan.affected_dependencies}, expected)
        for item in plan.identities_to_create:
            self.assertEqual((item.team_code, item.generation, item.operational_generation), ('T2', 2, 1))
            self.assertIsInstance(item.incarnation, str)

    def test_access_transfer_fans_out_to_linked_renewals(self):
        self.after['Acessos'][0]['funcionario'] = 'F2'
        plan = self.plan(module='Acessos', code='A1')
        self.assertEqual({t.key for t in plan.indirect_transitions}, {RecordKey('Renovacoes', 'R1')})
        self.assertEqual({i.key for i in plan.identities_to_create}, {RecordKey('Acessos', 'A1'), RecordKey('Renovacoes', 'R1')})
        self.assertEqual(self.get(plan, 'OrdensServico', 'O1').generation, 1)

    def test_same_team_access_transfer_records_path_change_without_invalidating_generation(self):
        self.after['Acessos'][0]['funcionario'] = 'F3'
        plan = self.plan(module='Acessos', code='A1')
        self.assertTrue(plan.applicable)
        self.assertFalse(plan.identities_to_end or plan.identities_to_create)
        self.assertEqual(plan.indirect_transitions[0].key, RecordKey('Renovacoes', 'R1'))
        self.assertIn('dependency_path_changed', plan.indirect_transitions[0].reasons)

    def test_renewal_transfer_to_other_access_changes_effective_team(self):
        self.after['Renovacoes'][0]['acesso'] = 'A2'
        plan = self.plan(module='Renovacoes', code='R1')
        self.assertTrue(plan.applicable)
        self.assertEqual(self.get(plan, 'Renovacoes', 'R1').team_code, 'T2')
        self.assertEqual(len(plan.identities_to_end), 1)

    def test_order_transfer_same_team_preserves_generation(self):
        self.after['OrdensServico'][0]['funcionario'] = 'F3'
        plan = self.plan()
        self.assertTrue(plan.applicable)
        self.assertFalse(plan.identities_to_end)
        self.assertIn('dependency_path_changed', plan.direct_transitions[0].reasons)

    def test_team_recreation_same_code_invalidates_all_bound_record_generations(self):
        plan = self.plan('recreate', 'Equipes', 'T1', allocations=(TokenAllocation(RecordKey('Equipes', 'T1'), 'new-team-life'),))
        self.assertTrue(plan.ready_for_manifest, plan.issues)
        self.assertEqual(len(plan.indirect_transitions), 3)
        self.assertEqual(len(plan.affected_dependencies), 3)
        for transition in plan.indirect_transitions:
            self.assertIn('team_incarnation_changed', transition.reasons)
            self.assertEqual(transition.before.incarnation, transition.after.incarnation)
            self.assertEqual(transition.after.team_generation, 2)

    def test_move_and_return_advances_binding_generation_without_reusing_old_generation(self):
        self.after['Funcionarios'][0]['equipe'] = 'T2'
        first = self.plan(module='Funcionarios', code='F1')
        self.identities = advance_history(self.identities, first)
        self.before = deepcopy(self.after); self.after['Funcionarios'][0]['equipe'] = 'T1'
        returned = self.plan(module='Funcionarios', code='F1')
        self.assertTrue(returned.applicable, returned.issues)
        self.assertEqual(self.get(returned).generation, 3)
        self.assertEqual(self.get(returned).operational_generation, 1)
        self.assertEqual(self.get(returned).incarnation, self.get(first).incarnation)

    def test_recreation_after_binding_changes_uses_lifetime_generation_not_binding_number(self):
        self.after['Funcionarios'][0]['equipe'] = 'T2'
        first = self.plan(module='Funcionarios', code='F1')
        self.identities = advance_history(self.identities, first); self.before = deepcopy(self.after)
        recreated = self.plan('recreate')
        self.assertTrue(recreated.applicable, recreated.issues)
        self.assertEqual((self.get(recreated).generation, self.get(recreated).operational_generation), (3, 2))

    def test_import_new_adds_and_preserves_absent_upload_records(self):
        self.after['OrdensServico'].append(dict(codigo='O3', funcionario='F1'))
        plan = self.imported('new', [RecordKey('OrdensServico', 'O3')])
        self.assertTrue(plan.applicable)
        self.assertEqual(plan.import_outcomes[0][1], 'added')
        self.assertEqual(self.get(plan, code='O2').generation, 1)
        self.assertEqual(len(plan.identities_to_create), 1)

    def test_import_new_existing_code_is_ignored_and_cannot_be_updated(self):
        target = RecordKey('OrdensServico', 'O1')
        plan = self.imported('new', [target])
        self.assertTrue(plan.applicable)
        self.assertEqual(plan.import_outcomes, ((target, 'ignored_existing'),))
        self.after['OrdensServico'][0]['descricao'] = 'Changed'
        self.assert_refused(self.imported('new', [target]), 'import_new_updated_existing')

    def test_upsert_requires_explicit_continuation_for_existing_record(self):
        key = RecordKey('OrdensServico', 'O1'); self.after['OrdensServico'][0]['descricao'] = 'Changed'
        self.assert_refused(self.imported('upsert', [key]), 'import_continuity_unproven')
        plan = self.imported('upsert', [key], [key])
        self.assertTrue(plan.applicable)
        self.assertEqual(plan.import_outcomes, ((key, 'updated'),))
        self.assertFalse(plan.identities_to_create)

    def test_upsert_employee_team_change_captures_indirect_transitions(self):
        key = RecordKey('Funcionarios', 'F1'); self.after['Funcionarios'][0]['equipe'] = 'T2'
        plan = self.imported('upsert', [key], [key])
        self.assertTrue(plan.applicable)
        self.assertEqual(len(plan.indirect_transitions), 3)

    def test_import_multiple_sheets_creates_linked_entities_in_one_plan(self):
        self.after['Equipes'].append(dict(codigo='T3', responsavel='F4'))
        self.after['Funcionarios'].append(dict(codigo='F4', equipe='T3'))
        self.after['OrdensServico'].append(dict(codigo='O3', funcionario='F4'))
        keys = [RecordKey('Equipes', 'T3'), RecordKey('Funcionarios', 'F4'), RecordKey('OrdensServico', 'O3')]
        plan = self.imported('new', keys)
        self.assertTrue(plan.applicable, plan.issues)
        self.assertEqual(self.get(plan, code='O3').team_code, 'T3')
        self.assertEqual(len(plan.allocations_needed), 2)

    def test_import_missing_uploaded_or_unmentioned_deleted_records_is_refused(self):
        self.after['OrdensServico'].pop(1)
        self.assert_refused(self.imported('upsert', [RecordKey('OrdensServico', 'O2')], [RecordKey('OrdensServico', 'O2')]), 'import_deletion_forbidden')
        self.assert_refused(self.imported('new', []), 'import_undeclared_change')

    def test_import_unknown_mode_and_duplicate_targets_are_refused(self):
        key = RecordKey('OrdensServico', 'O1')
        self.assert_refused(self.imported('replace', [key]), 'import_operation_invalid')
        self.assert_refused(self.imported('new', [key, key]), 'operation_key_duplicate')

    def test_upload_uuid_and_derived_team_do_not_establish_identity(self):
        self.after['OrdensServico'].append(dict(codigo='O3', funcionario='F1', uuid='stolen-token', equipe='T2'))
        plan = self.imported('new', [RecordKey('OrdensServico', 'O3')])
        self.assertTrue(plan.applicable)
        item = self.get(plan, code='O3')
        self.assertIsInstance(item.incarnation, AllocationNeed)
        self.assertEqual(item.team_code, 'T1')

    def test_duplicate_code_in_either_inventory_is_refused(self):
        for side in ('before', 'after'):
            rows = getattr(self, side)['OrdensServico']; rows.append(dict(rows[0]))
            with self.subTest(side=side): self.assert_refused(self.plan(), 'record_code_duplicate')
            rows.pop()

    def test_every_real_reference_is_validated_with_structured_location(self):
        for module, field in [('Funcionarios', 'equipe'), ('Equipes', 'responsavel'), ('OrdensServico', 'funcionario'),
                              ('Acessos', 'funcionario'), ('Renovacoes', 'acesso'), ('Renovacoes', 'responsavel')]:
            self.after = deepcopy(self.before); self.after[module][0][field] = 'missing'
            with self.subTest(module=module, field=field):
                plan = self.plan(module=module, code=self.after[module][0]['codigo'])
                self.assert_refused(plan, 'reference_missing')
                self.assertEqual((plan.issues[0].module, plan.issues[0].field), (module, field))

    def test_missing_modules_rows_and_non_string_values_are_refused(self):
        for change in ('missing-module', 'unknown-module', 'wrong-rows', 'wrong-row', 'wrong-value'):
            self.after = deepcopy(self.before)
            if change == 'missing-module': del self.after['Renovacoes']
            elif change == 'unknown-module': self.after['Unknown'] = []
            elif change == 'wrong-rows': self.after['Equipes'] = {}
            elif change == 'wrong-row': self.after['OrdensServico'] = [None]
            else: self.after['OrdensServico'][0]['codigo'] = 1
            with self.subTest(change=change): self.assert_refused(self.plan())

    def test_missing_history_and_incompatible_current_team_are_refused(self):
        original = self.identities
        self.identities = original[1:]
        self.assert_refused(self.plan(), 'identity_missing')
        self.identities = tuple(replace(i, team_code='T2') if i.key == RecordKey('OrdensServico', 'O1') else i for i in original)
        self.assert_refused(self.plan(), 'identity_team_mismatch')

    def test_generations_reject_zero_negative_bool_float_and_missing(self):
        original = self.identities
        for field in ('generation', 'team_generation', 'operational_generation'):
            for value in (0, -1, True, 1.5, None):
                self.identities = tuple(replace(i, **{field: value}) if i.key == RecordKey('OrdensServico', 'O1') else i for i in original)
                with self.subTest(field=field, value=value): self.assert_refused(self.plan())

    def test_duplicate_history_and_non_latest_present_generation_refused(self):
        self.identities += self.identities[:1]
        self.assert_refused(self.plan(), 'identity_generation_gap_or_duplicate')
        self.identities = history(self.before)
        original = next(i for i in self.identities if i.key == RecordKey('OrdensServico', 'O1'))
        self.identities += (replace(original, generation=2, team_code='T2'),)
        self.assert_refused(self.plan(), 'identity_presence_ambiguous')

    def test_identity_presence_must_match_inventory(self):
        self.identities = tuple(replace(i, present=False) if i.key == RecordKey('OrdensServico', 'O1') else i for i in self.identities)
        self.assert_refused(self.plan(), 'identity_inventory_mismatch')

    def test_raw_dictionary_is_not_identity_history(self):
        self.identities = tuple(asdict(i) for i in self.identities)
        self.assert_refused(self.plan(), 'identity_history_untrusted')

    def test_incomplete_history_context_is_not_a_baseline_request(self):
        self.context = replace(self.context, history_complete=False)
        self.assert_refused(self.plan(), 'identity_history_incomplete')

    def test_invalid_context_is_refused(self):
        for context in (None, replace(self.context, epoch=''), replace(self.context, revision=True),
                        replace(self.context, source_revision=-1), replace(self.context, source_token='')):
            self.context = context
            with self.subTest(context=context): self.assert_refused(self.plan(), 'continuity_context_invalid')

    def test_contradictory_operation_cannot_hide_other_mutations(self):
        self.after['Acessos'][0]['sistema'] = 'Hidden change'
        self.assert_refused(self.plan(), 'operation_contradiction')
        self.after = deepcopy(self.before)
        self.assert_refused(self.plan('create'), 'operation_contradiction')
        self.assert_refused(self.plan('delete'), 'operation_contradiction')

    def test_bad_operation_inputs_produce_refusal_instead_of_inferred_action(self):
        for operation in (None, {'kind': 'update'}, ProposedOperation('op', 'unknown'),
                          ProposedOperation('op', 'update', [], 'O1'), ProposedOperation('op', 'update', 'OrdensServico', ' O1')):
            plan = plan_identity_transition(self.before, self.after, operation, self.identities, context=self.context)
            with self.subTest(operation=operation): self.assert_refused(plan)

    def test_duplicate_or_irrelevant_allocations_are_refused(self):
        key = RecordKey('OrdensServico', 'O3'); self.after['OrdensServico'].append(dict(codigo='O3', funcionario='F1'))
        for allocations in [(TokenAllocation(key, 'fresh'), TokenAllocation(key, 'fresh2')),
                            (TokenAllocation(RecordKey('OrdensServico', 'O1'), 'fresh'),), ({'key': key, 'token': 'fresh'},)]:
            with self.subTest(allocations=allocations): self.assert_refused(self.plan('create', code='O3', allocations=allocations))

    def test_deterministic_across_repeated_calls_and_inventory_history_order(self):
        self.after['Funcionarios'][0]['equipe'] = 'T2'
        first = self.plan(module='Funcionarios', code='F1')
        self.assertEqual(first, self.plan(module='Funcionarios', code='F1'))
        self.before = {module: list(reversed(rows)) for module, rows in reversed(list(self.before.items()))}
        self.after = {module: list(reversed(rows)) for module, rows in reversed(list(self.after.items()))}
        self.identities = tuple(reversed(self.identities))
        self.assertEqual(first, self.plan(module='Funcionarios', code='F1'))

    def test_import_target_order_does_not_change_plan(self):
        keys = [RecordKey('OrdensServico', 'O1'), RecordKey('Acessos', 'A1')]
        self.assertEqual(self.imported('upsert', keys, keys), self.imported('upsert', keys[::-1], keys[::-1]))

    def test_team_delete_then_recreate_keeps_tombstone_and_requests_new_life(self):
        self.before['Equipes'].append(dict(codigo='T3', responsavel='F1'))
        self.identities = history(self.before); self.after = deepcopy(self.before); self.after['Equipes'].pop()
        deleted = self.plan('delete', 'Equipes', 'T3')
        self.identities = advance_history(self.identities, deleted)
        self.before = deepcopy(self.after); self.after['Equipes'].append(dict(codigo='T3', responsavel='F1'))
        plan = self.plan('create', 'Equipes', 'T3')
        self.assertTrue(plan.applicable, plan.issues)
        self.assertEqual(self.get(plan, 'Equipes', 'T3').generation, 2)
        old = next(i for i in self.identities if i.key == RecordKey('Equipes', 'T3'))
        self.assertFalse(old.present)

    def test_two_fresh_records_cannot_share_a_supplied_token(self):
        keys = (RecordKey('OrdensServico', 'O3'), RecordKey('Acessos', 'A3'))
        self.after['OrdensServico'].append(dict(codigo='O3', funcionario='F1'))
        self.after['Acessos'].append(dict(codigo='A3', funcionario='F1'))
        plan = plan_identity_transition(self.before, self.after,
            ProposedOperation('op', 'import', mode='new', targets=keys), self.identities, context=self.context,
            allocations=tuple(TokenAllocation(key, 'same-token') for key in keys))
        self.assert_refused(plan, 'incarnation_reused')

    def test_visible_code_cannot_serve_as_creation_identity(self):
        self.after['OrdensServico'].append(dict(codigo='O3', funcionario='F1'))
        self.assert_refused(self.plan('create', code='O3', allocations=(TokenAllocation(RecordKey('OrdensServico', 'O3'), 'O3'),)),
                            'incarnation_is_visible_code')
        self.after = deepcopy(self.before)
        self.identities = tuple(replace(i, incarnation=i.key.code) if i.key == RecordKey('OrdensServico', 'O1') else i for i in self.identities)
        self.assert_refused(self.plan(), 'incarnation_is_visible_code')

    def test_historical_old_life_cannot_be_reintroduced_as_current(self):
        key = RecordKey('OrdensServico', 'O1'); original = next(i for i in self.identities if i.key == key)
        self.identities = tuple(replace(i, present=False) if i.key == key else i for i in self.identities)
        self.identities += (replace(original, incarnation='second-life', generation=2, operational_generation=2, present=False),
                            replace(original, generation=3, operational_generation=3))
        self.assert_refused(self.plan(), 'incarnation_reused')

    def test_historical_team_reference_must_exist(self):
        self.identities = tuple(replace(i, team_generation=2) if i.key == RecordKey('OrdensServico', 'O1') else i for i in self.identities)
        self.assert_refused(self.plan(), 'identity_team_history_missing')

    def test_initial_operational_generation_can_come_from_a_valid_existing_3a_baseline(self):
        self.identities = tuple(replace(i, operational_generation=5) if i.key == RecordKey('OrdensServico', 'O1') else i for i in self.identities)
        plan = self.plan()
        self.assertTrue(plan.applicable, plan.issues)
        self.assertEqual(self.get(plan).operational_generation, 5)

    def test_bootstrap_complete_synthetic_import_requires_all_allocations(self):
        self.before = {module: [] for module in self.before}; self.identities = ()
        self.context = PlanningContext('new-epoch', 0, 0, '')
        keys = tuple(RecordKey(module, row['codigo']) for module, rows in self.after.items() for row in rows)
        plan = self.imported('new', keys)
        self.assertTrue(plan.applicable, plan.issues)
        self.assertEqual(len(plan.allocations_needed), 8)
        self.assertFalse(plan.ready_for_manifest)

    def test_arguments_untouched_and_outputs_deeply_immutable(self):
        self.after['Funcionarios'][0]['equipe'] = 'T2'
        before = deepcopy((self.before, self.after, self.identities, self.context))
        plan = self.plan(module='Funcionarios', code='F1')
        self.assertEqual((self.before, self.after, self.identities, self.context), before)
        with self.assertRaises(FrozenInstanceError): plan.applicable = False
        with self.assertRaises(FrozenInstanceError): plan.identities_to_create[0].generation = 99
        with self.assertRaises(FrozenInstanceError): plan.identities_to_create[0].key.code = 'Other'
        self.after['Funcionarios'][0]['equipe'] = 'T1'
        self.assertEqual(plan.identities_to_create[0].team_code, 'T2')

    def test_fingerprints_bind_inventory_history_context_operation_and_allocation(self):
        first = self.plan()
        self.after['OrdensServico'][0]['descricao'] = 'Changed'
        changed = self.plan()
        self.assertNotEqual(first.after_fingerprint, changed.after_fingerprint)
        self.context = replace(self.context, revision=11)
        self.assertNotEqual(changed.context_fingerprint, self.plan().context_fingerprint)
        self.assertNotEqual(changed.plan_fingerprint, self.plan().plan_fingerprint)

    def test_no_io_clock_random_or_operational_import_in_planner(self):
        source = (ROOT / 'services/identity_planner.py').read_text(encoding='utf-8')
        tree = ast.parse(source)
        imports = {n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)}
        imports |= {alias.name for n in ast.walk(tree) if isinstance(n, ast.Import) for alias in n.names}
        self.assertEqual(imports, {'collections.abc', 'dataclasses', 'hashlib', 'json', 'schema'})
        with patch('builtins.open', side_effect=AssertionError('I/O forbidden')):
            self.assertTrue(self.plan().applicable)
        for module in ('app', 'services.auth_service', 'services.excel_service', 'services.import_coordinator',
                       'services.email_recipient_repository', 'services.mail_service'):
            self.assertNotIn(module, sys.modules)

    def test_manifest_dto_fields_match_existing_3c2a_without_importing_repository(self):
        tree = ast.parse((ROOT / 'services/email_recipient_repository.py').read_text(encoding='utf-8'))
        dto = {node.name: tuple(n.target.id for n in node.body if isinstance(n, ast.AnnAssign))
               for node in tree.body if isinstance(node, ast.ClassDef)}
        self.assertEqual(dto['TeamIncarnation'], ('code', 'incarnation'))
        self.assertEqual(dto['RecordIncarnation'], ('module', 'code', 'incarnation', 'team_code', 'operational_generation'))
        self.assertEqual(dto['IdentityManifest'], ('epoch', 'source_revision', 'source_token', 'teams', 'records'))
        self.assertTrue({'epoch', 'revision', 'source_revision', 'source_token'} <= {f.name for f in fields(PlanningContext)})
