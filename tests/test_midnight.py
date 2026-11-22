"""Presentation aggregates and navigation must preserve data and permissions."""
from copy import deepcopy
from app import create_app
from services.dashboard_service import enrich, overview, summary
from tests.common import DataCase, login_admin


class MidnightTests(DataCase):
    def test_monthly_series_and_access_metadata_match_the_filtered_universe(self):
        data=enrich(self.raw);team=data['Equipes'][0]['codigo'];people={r['codigo'] for r in data['Funcionarios'] if r['equipe']==team}
        data['Equipes']=[r for r in data['Equipes'] if r['codigo']==team]
        data['OrdensServico']=[r for r in data['OrdensServico'] if r['funcionario'] in people]
        data['Acessos']=[r for r in data['Acessos'] if r['funcionario'] in people]
        before=deepcopy(data);_,charts=summary(data);result=overview(data)
        total,*statuses=charts['trend']['data']
        for index,month in enumerate(total['x']):
            self.assertEqual(total['y'][index],sum(trace['y'][index] for trace in statuses))
            for trace in statuses:self.assertEqual(trace['y'][index],sum(r['abertura'].startswith(month) and r['status']==trace['name'] for r in data['OrdensServico']))
        self.assertEqual(result['access_total'],len(data['Acessos']))
        self.assertEqual(sum(row['value'] for row in result['access_teams']),result['access_total'])
        dates=sorted(r['concessao'] for r in data['Acessos'])
        self.assertEqual(result['access_period'],{'start':dates[0],'end':dates[-1]})
        self.assertEqual(data,before)

    def test_empty_access_metadata_and_chart_totals_are_finite(self):
        data={key:[] for key in self.raw};result=overview(data);indicators,charts=summary(data)
        self.assertEqual(result['access_period'],{'start':None,'end':None});self.assertEqual(result['access_total'],0)
        self.assertEqual(result['access_teams'],[]);self.assertEqual(indicators['Ordens de serviço'],0)
        self.assertTrue(all(trace['y']==[] for trace in charts['trend']['data']))

    def test_overview_is_derived_and_does_not_mutate_records(self):
        data=enrich(self.raw);before=deepcopy(data)
        result=overview(data);indicators,charts=summary(data)
        expected=[r for r in data['OrdensServico'] if r['prioridade'] in ('Alta','Crítica') and r['status']!='Concluída']
        self.assertEqual({r['codigo'] for r in result['urgent']},{r['codigo'] for r in expected})
        self.assertEqual(indicators['Urgentes'],len(expected))
        self.assertEqual(sum(charts['trend']['data'][0]['y']),len(data['OrdensServico']))
        for item in result['access_teams']:
            team=next(t for t in data['Equipes'] if t['nome']==item['name'])
            self.assertEqual(item['value'],sum(r['equipe']==team['codigo'] for r in data['Acessos']))
        self.assertEqual(data,before)

    def test_preferences_redirects_and_help_preserve_guest_restrictions(self):
        app=create_app(self.path);client=app.test_client();headers=login_admin(app,client)
        for path in ('/configuracoes','/settings'):
            response=client.get(path)
            self.assertEqual(response.status_code,302)
            self.assertEqual(response.location,'/perfil?tab=preferences')
        self.assertNotIn('id="settings-button"',client.get('/dashboard').text)
        self.assertEqual(client.get('/ajuda').status_code,200)
        client.post('/auth/guest',json={},headers=headers)
        self.assertEqual(client.get('/ajuda').status_code,200)
        self.assertEqual(client.get('/configuracoes').status_code,403)
        self.assertEqual(client.get('/perfil').status_code,403)
        self.assertEqual(self.store.read(),self.raw)
