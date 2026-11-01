from .dashboard_service import filtered, categoria
def consultar(data, filtros=None):
    return filtered(data['Acessos'],filtros or {},'vencimento')
