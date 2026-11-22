"""Isolated visual fixture. Run from project root; never uses the real SQLite."""
from pathlib import Path
import os
import secrets
import shutil
import sys
from datetime import datetime, timedelta, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
preview = ROOT / 'diagnosticos' / 'premium-preview'
preview.mkdir(parents=True, exist_ok=True)
directory = preview / ('instance-' + secrets.token_hex(6))
os.environ['DASHBOARD_AUTH_DIRECTORY'] = str(directory)
os.environ['DASHBOARD_ENV'] = 'development'
os.environ['DASHBOARD_MAIL_ENABLED'] = 'false'
copied = preview / 'dados-teste.xlsx'
shutil.copy2(ROOT / 'dados/dados_dashboard.xlsx', copied)
os.environ['DASHBOARD_EXCEL_PATH'] = str(copied)
from app import app

auth = app.config['AUTH']
service = app.config['ENTERPRISE']
password = secrets.token_urlsafe(24)
(preview / 'login.key').write_text(password, encoding='ascii')
auth.create_admin('visual-teste', password)
auth.create_admin('outro-teste', secrets.token_urlsafe(24))
with auth.connect() as db:
    db.execute("UPDATE account SET display_name='Ambiente de teste',email='preview@example.test' WHERE user_id='visual-teste'")
    for index in range(9):
        titles = ['Atualização do sistema', 'Ordem de serviço pendente', 'Acesso próximo do vencimento']
        messages = ['Aviso ilustrativo exclusivo do ambiente isolado.', 'Uma ordem de teste precisa de atenção.', 'Confira os dados de teste do acesso relacionado.']
        service.emit(db, 'preview:' + str(index), 'operational' if index % 3 else 'announcement', titles[index % 3], messages[index % 3], '/acessos', email=False)
        occurred = (datetime.now(timezone.utc)-timedelta(days=index)).isoformat()
        db.execute('UPDATE events SET occurred=? WHERE event_key=?', (occurred, 'preview:' + str(index)))
    db.execute("UPDATE notifications SET read_at=? WHERE user_id='visual-teste' AND id IN (SELECT id FROM notifications WHERE user_id='visual-teste' ORDER BY id LIMIT 2)", (datetime.now(timezone.utc).isoformat(),))
print('Isolated preview: http://127.0.0.1:5001/login', flush=True)
app.run(host='127.0.0.1', port=5001, debug=False)
