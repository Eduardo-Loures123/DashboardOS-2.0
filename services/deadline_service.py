"""Read-only deadline views. Business bands and monitored statuses already exist."""
from datetime import date

from .dashboard_service import categoria
from .operational_events import FOLLOW_UP


def order_deadlines(rows, today=None):
    today = today or date.today()
    result = []
    for source in rows:
        row = dict(source)
        try:
            remaining = (date.fromisoformat(row.get('previsao', '')) - today).days
        except (ValueError, TypeError):
            remaining = None
        row['dias'] = remaining
        row['situacao'] = ('Encerrado' if row.get('status') not in FOLLOW_UP['OrdensServico']
                           else 'Sem prazo válido' if remaining is None else categoria(remaining))
        result.append(row)
    return result
