"""Configuração de produção; nenhum dado demonstrativo é gerado aqui."""
import os
from pathlib import Path
from werkzeug.middleware.proxy_fix import ProxyFix


def configure(app, root, path=None, auth_directory=None):
    production = os.environ.get('DASHBOARD_ENV', 'development') == 'production'
    excel = Path(path or os.environ.get('DASHBOARD_EXCEL_PATH', root/'dados/dados_dashboard.xlsx')).resolve()
    auth = Path(auth_directory or os.environ.get('DASHBOARD_AUTH_DIRECTORY', Path(path).parent/'instance' if path else root/'instance')).resolve()
    hosts = [h.strip() for h in os.environ.get('DASHBOARD_ALLOWED_HOSTS', '127.0.0.1,localhost').split(',') if h.strip()]
    if production:
        secret = os.environ.get('SECRET_KEY', '')
        if len(secret) < 64 or len(set(secret)) < 8:
            raise RuntimeError('SECRET_KEY deve conter ao menos 64 caracteres aleatórios.')
        if not os.environ.get('DASHBOARD_ALLOWED_HOSTS') or any(h in ('*', '') or '/' in h or ':' in h for h in hosts):
            raise RuntimeError('Configure os nomes DNS permitidos, sem esquema ou porta.')
        for location in (excel, auth):
            if location.is_relative_to(root):
                raise RuntimeError('Dados de produção devem ficar fora do código.')
        if not excel.is_file() or not (auth/'auth.sqlite3').is_file():
            raise RuntimeError('Copie os dados existentes antes de iniciar a produção.')
        app.config.update(SECRET_KEY=secret, DEBUG=False, TESTING=False)
        # Exatamente um Nginx local; socket Unix impede conexão remota direta.
        # Nginx sobrescreve estes dois cabeçalhos; demais X-Forwarded-* são ignorados.
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=0, x_port=0, x_prefix=0)
    app.config.update(PRODUCTION=production, EXCEL_PATH=excel, AUTH_DIRECTORY=auth, ALLOWED_HOSTS=hosts)
    return production
