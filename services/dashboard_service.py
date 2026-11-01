from datetime import date
from collections import Counter

def categoria(dias):
    if dias<0:return 'Vencidos'
    if dias==0:return 'Vencem hoje'
    if dias<=30:return 'Até 30 dias'
    if dias<=45:return '31 a 45 dias'
    return 'Após 45 dias'

def enrich(data,hoje=None):
    hoje=hoje or date.today(); people={r['codigo']:r for r in data['Funcionarios']}; access={r['codigo']:r for r in data['Acessos']}
    result={k:[dict(r) for r in rows] for k,rows in data.items()}
    for sheet in ['OrdensServico','Acessos','Renovacoes']:
        for row in result[sheet]:
            person=people.get(row.get('funcionario',access.get(row.get('acesso'),{}).get('funcionario')), {})
            row['equipe']=person.get('equipe',''); row['nome_funcionario']=person.get('nome','')
            if sheet=='Acessos':
                row['dias']=(date.fromisoformat(row['vencimento'])-hoje).days
                row['situacao']=categoria(row['dias'])
    for row in result['Equipes']:
        for key,sheet in [('quantidade_funcionarios','Funcionarios'),('quantidade_os','OrdensServico'),('quantidade_acessos','Acessos')]: row[key]=sum(r.get('equipe')==row['codigo'] for r in result[sheet])
    return result

def filtered(rows,filters,date_field=None,lookups=None):
    result=[]
    for row in rows:
        if any(v and k not in ['q','inicio','fim'] and str(row.get(k,''))!=v for k,v in filters.items()):continue
        if filters.get('q'):
            values=[]
            relations={'equipe':'Equipes','funcionario':'Funcionarios','responsavel':'Funcionarios','acesso':'Acessos'}
            for key,value in row.items():
                text=str(value) if value!='' else '—'
                related=(lookups or {}).get(relations.get(key),{}).get(value,{})
                if related:
                    label=related.get('nome',related.get('descricao',related.get('sistema',related['codigo'])))
                    text=label+' · '+related['codigo']
                elif len(text)==10 and text[:4].isdigit() and text[4:5]=='-' and text[7:8]=='-':
                    text=text[8:10]+'/'+text[5:7]+'/'+text[:4]
                values.append(text)
            if not any(filters['q'].casefold() in value.casefold() for value in values):continue
        if date_field and ((filters.get('inicio') and row.get(date_field,'')<filters['inicio']) or (filters.get('fim') and row.get(date_field,'')>filters['fim'])):continue
        result.append(row)
    return result

def summary(data):
    os=data['OrdensServico']; ac=[r for r in data['Acessos'] if r['status']=='Ativo']; ren=data['Renovacoes']
    counts=Counter(r['status'] for r in os)
    indicators={'Funcionários':len(data['Funcionarios']),'Equipes':len(data['Equipes']),'Ordens de serviço':len(os),'Concluídas':counts['Concluída'],'Pendentes':counts['Pendente'],'Em andamento':counts['Em andamento'],'Acessos':len(data['Acessos']),'Vencidos':sum(r['dias']<0 for r in ac),'Até 30 dias':sum(0<=r['dias']<=30 for r in ac),'31 a 45 dias':sum(31<=r['dias']<=45 for r in ac),'Renovações pendentes':sum(r['status'] not in ['Concluída','Rejeitada'] for r in ren)}
    teams=[r['codigo'] for r in data['Equipes']]
    months=sorted({r['abertura'][:7] for r in os})
    charts={
      'teams':{'title':'Ordens de serviço por equipe','data':[{'type':'bar','name':status,'x':teams,'y':[sum(r['equipe']==t and r['status']==status for r in os) for t in teams],'marker':{'color':color}} for status,color in [('Concluída','#12395B'),('Pendente','#FF9F0A'),('Em andamento','#90A9BF')]]},
      'trend':{'title':'Evolução das ordens de serviço','data':[{'type':'scatter','mode':'lines','fill':'tozeroy','name':status,'x':months,'y':[sum(r['abertura'].startswith(m) and r['status']==status for r in os) for m in months],'line':{'color':color,'shape':'spline'}} for status,color in [('Concluída','#12395B'),('Pendente','#FF9F0A')]]},
      'donut':{'title':'Situação das ordens','data':[{'type':'pie','hole':.78,'labels':['Concluída','Pendente','Em andamento'],'values':[counts[s] for s in ['Concluída','Pendente','Em andamento']],'marker':{'colors':['#12395B','#FF9F0A','#DCE5EE']},'textinfo':'none','sort':False}]}}
    return indicators,charts
