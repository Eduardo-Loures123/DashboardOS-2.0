from datetime import date
from tests.common import DataCase
from services.dashboard_service import categoria,enrich,summary,filtered

class IndicatorTests(DataCase):
    def test_limites_sem_sobreposicao(self):
        expected={-1:'Vencidos',0:'Vencem hoje',1:'Até 30 dias',30:'Até 30 dias',31:'31 a 45 dias',45:'31 a 45 dias',46:'Após 45 dias'}
        for n,label in expected.items():self.assertEqual(categoria(n),label)
    def test_indicadores(self):
        data=enrich(self.raw); k,charts=summary(data)
        self.assertEqual(k['Funcionários'],len(self.raw['Funcionarios']));self.assertEqual(k['Equipes'],len(self.raw['Equipes']))
        self.assertEqual(k['Ordens de serviço'],len(self.raw['OrdensServico']));self.assertEqual(k['Acessos'],len(self.raw['Acessos']))
        self.assertEqual(k['Concluídas']+k['Pendentes']+k['Em andamento'],len(self.raw['OrdensServico']))
        self.assertEqual(k['Concluídas'],sum(r['status']=='Concluída' for r in self.raw['OrdensServico']))
        for label,test in [('Vencidos',lambda d:d<0),('Até 30 dias',lambda d:0<=d<=30),('31 a 45 dias',lambda d:31<=d<=45)]:
            self.assertEqual(k[label],sum(test((date.fromisoformat(r['vencimento'])-date.today()).days) for r in self.raw['Acessos'] if r['status']=='Ativo'))
        self.assertEqual(k['Renovações pendentes'],sum(r['status'] not in ['Concluída','Rejeitada'] for r in self.raw['Renovacoes']))
        self.assertEqual(sum(sum(trace['y']) for trace in charts['teams']['data']),len(self.raw['OrdensServico']))
        self.assertEqual(sum(charts['donut']['data'][0]['values']),len(self.raw['OrdensServico']))
        self.assertEqual(sum(r['quantidade_funcionarios'] for r in data['Equipes']),len(self.raw['Funcionarios']))
    def test_filtros(self):
        data=enrich(self.raw)
        result=filtered(data['OrdensServico'],{'equipe':'EQ0001','status':'Pendente','prioridade':'Alta','inicio':'2000-01-01','fim':'2099-01-01'},'abertura')
        self.assertTrue(result)
        self.assertTrue(all(r['equipe']=='EQ0001' and r['status']=='Pendente' and r['prioridade']=='Alta' for r in result))
        self.assertEqual(filtered(data['OrdensServico'],{'inicio':'2099-01-01'},'abertura'),[])
        self.assertEqual(filtered(data['Funcionarios'],{'q':'FUNC0001'})[0]['codigo'],'FUNC0001')
