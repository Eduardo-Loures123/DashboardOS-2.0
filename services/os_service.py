from .dashboard_service import filtered
def consultar(data, filtros=None):
    return filtered(data['OrdensServico'],filtros or {},'abertura')
