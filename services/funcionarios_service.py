from .dashboard_service import filtered
def consultar(data, filtros=None):
    return filtered(data['Funcionarios'],filtros or {},'admissao')
