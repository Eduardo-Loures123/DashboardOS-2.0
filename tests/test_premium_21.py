from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

from app import create_app
from services.agenda_service import agenda
from services.dashboard_service import enrich
from tests.common import DataCase, login_admin


class PremiumPresentationTests(DataCase):
    def test_agenda_uses_real_records_without_mutation(self):
        data = enrich(self.raw)
        before = deepcopy(data)
        result = agenda(data)
        self.assertEqual(data, before)
        by_sheet = {name: {r['codigo']: r for r in rows} for name, rows in data.items()}
        for event in result['events']:
            sheet, field = {'os': ('OrdensServico', 'previsao'), 'acesso': ('Acessos', 'vencimento'),
                            'renovacao': ('Renovacoes', 'solicitacao')}[event['kind']]
            source = by_sheet[sheet][event['code']]
            self.assertEqual(event['date'], source[field])
            self.assertEqual(event['status'], source['status'])
        self.assertEqual(result['attention'][0]['value'], sum(
            r['status'] != 'Concluída' and r['previsao'] < date.today().isoformat() for r in data['OrdensServico']))

    def test_attention_boundaries_and_completed_records(self):
        today = date(2026, 11, 2)
        data = {'OrdensServico': [], 'Acessos': [], 'Renovacoes': []}
        original = self.raw['OrdensServico'][0]
        for i, (delta, status) in enumerate([(-1, 'Pendente'), (0, 'Pendente'), (7, 'Em andamento'),
                                            (8, 'Pendente'), (-2, 'Concluída')]):
            data['OrdensServico'].append(dict(original, codigo=str(i), status=status,
                                               previsao=(today + timedelta(days=delta)).isoformat()))
        result = agenda(data, today)
        self.assertEqual([r['value'] for r in result['attention']], [1, 2])
        self.assertEqual(len(result['events']), 4)
        self.assertEqual(agenda({'OrdensServico': [], 'Acessos': [], 'Renovacoes': []}, today)['events'], [])

    def test_version_brand_and_filtered_agenda(self):
        app = create_app(self.path)
        client = app.test_client()
        login_admin(app, client)
        version = (Path(__file__).resolve().parents[1] / 'VERSION').read_text().strip()
        for page in ['dashboard', 'equipes', 'relatorios']:
            html = client.get('/' + page).text
            self.assertIn('WORKSPACE / ' + version, html)
            self.assertIn('<b>' + version + '</b>', html)
            self.assertNotIn('DASHBOARDOS', html)
            self.assertNotIn('session-identity', html)
            self.assertNotIn('Trocar usuário', html)
        team = self.raw['Equipes'][0]['codigo']
        result = client.get('/api/data/dashboard?equipe=' + team).json
        self.assertEqual(result['version'], version)
        people = {r['codigo'] for r in self.raw['Funcionarios'] if r['equipe'] == team}
        expected = {r['codigo'] for r in self.raw['OrdensServico'] if r['funcionario'] in people and r['status'] != 'Concluída'}
        self.assertEqual({e['code'] for e in result['agenda']['events'] if e['kind'] == 'os'}, expected)
