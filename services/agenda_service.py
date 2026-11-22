"""Read-only operational presentation derived from the already filtered dataset."""
from datetime import date, timedelta


def agenda(data, today=None):
    today = today or date.today()
    events = []
    orders = [r for r in data['OrdensServico'] if r['status'] != 'Concluída']
    accesses = [r for r in data['Acessos'] if r['status'] == 'Ativo']
    renewals = [r for r in data['Renovacoes'] if r['status'] not in ('Concluída', 'Rejeitada')]
    for rows, kind, field, page, title in (
        (orders, 'os', 'previsao', 'ordens-servico', 'descricao'),
        (accesses, 'acesso', 'vencimento', 'acessos', 'sistema'),
        (renewals, 'renovacao', 'solicitacao', 'renovacoes', 'observacoes'),
    ):
        for row in rows:
            if not row.get(field):
                continue
            events.append(dict(date=row[field], kind=kind, code=row['codigo'],
                               title=row.get(title) or row['codigo'], status=row['status'], page=page))
    return dict(events=sorted(events, key=lambda e: (e['date'], e['code'])), attention=[
        dict(label='OS com previsão vencida', value=sum(bool(r.get('previsao')) and r['previsao'] < today.isoformat() for r in orders)),
        dict(label='OS previstas em até 7 dias', value=sum(today.isoformat() <= r.get('previsao','') <= (today + timedelta(days=7)).isoformat() for r in orders)),
    ])
