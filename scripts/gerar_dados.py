from pathlib import Path
import sys, random
from datetime import date, timedelta
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import pandas as pd
from services.schema import SCHEMA

def gerar(path, hoje=None):
    path=Path(path)
    if path.exists():
        raise FileExistsError('A planilha já existe. Não será substituída.')
    r=random.Random(42); hoje=hoje or date.today()
    dt=lambda n:(hoje+timedelta(days=n)).isoformat()
    data={k:[] for k in SCHEMA}
    nomes=['Aurora','Bruno','Cecília','Davi','Elisa','Felipe','Giovana','Hugo','Íris','Júlio']
    for i in range(1,11):
        data['Equipes'].append(dict(zip(SCHEMA['Equipes'],[f'EQ{i:04}',f'Equipe {i:02} — '+['Operações','Tecnologia','Projetos','Suporte','Qualidade','Infraestrutura','Financeiro','Atendimento','Segurança','Planejamento'][i-1],f'FUNC{i:04}'])))
    for i in range(1,101):
        data['Funcionarios'].append(dict(zip(SCHEMA['Funcionarios'],[f'FUNC{i:04}',f'{nomes[(i-1)%10]} Exemplo {i:03}',f'EQ{(i-1)%10+1:04}',r.choice(['Analista','Técnico','Coordenador']),f'pessoa{i:03}@example.com',dt(-r.randint(400,1800)), 'Inativo' if i%17==0 else 'Ativo'])))
    for i in range(1,501):
        abertura=-r.randint(5,180); status=r.choice(['Pendente','Em andamento','Concluída'])
        data['OrdensServico'].append(dict(zip(SCHEMA['OrdensServico'],[f'OS{i:04}',r.choice(['Manutenção preventiva','Atualização de ambiente','Inspeção técnica','Configuração de recurso'])+f' #{i}',f'FUNC{r.randint(1,100):04}',dt(abertura),dt(abertura+30),dt(abertura+4) if status=='Concluída' else '',r.choice(['Baixa','Média','Alta','Crítica']),status])))
        vencimento=[-r.randint(1,60),0,r.randint(1,30),r.randint(31,45),r.randint(46,240)][i%5]
        data['Acessos'].append(dict(zip(SCHEMA['Acessos'],[f'AC{i:04}',f'FUNC{r.randint(1,100):04}',r.choice(['ERP','VPN','CRM','Portal','BI']),dt(-365),dt(vencimento),'Revogado' if i%29==0 else 'Ativo'])))
    for i in range(1,151):
        data['Renovacoes'].append(dict(zip(SCHEMA['Renovacoes'],[f'REN{i:04}',f'AC{i:04}',dt(-r.randint(0,50)),r.choice(['Pendente','Solicitada','Em análise','Aprovada','Concluída','Rejeitada']),f'FUNC{r.randint(1,100):04}','Solicitação fictícia para acompanhamento.'])))
    path.parent.mkdir(parents=True,exist_ok=True)
    with pd.ExcelWriter(path,engine='openpyxl') as writer:
        for sheet,rows in data.items():
            pd.DataFrame(rows,columns=SCHEMA[sheet]).to_excel(writer,sheet_name=sheet,index=False)
            ws=writer.book[sheet]; ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
            for col in ws.columns: ws.column_dimensions[col[0].column_letter].width=24
    return data

if __name__=='__main__':
    gerar(Path(__file__).resolve().parents[1]/'dados/dados_dashboard.xlsx')
    print('Planilha criada: 100 funcionários, 10 equipes, 500 OS, 500 acessos e 150 renovações.')
