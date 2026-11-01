from contextlib import closing
"""Execute com o mesmo usuário do serviço. SQLite usa API de backup."""
import os
import shutil
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from services.excel_service import ExcelService

def backup(excel, auth, destination):
    target = Path(destination)/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    target.mkdir(parents=True, mode=0o700)
    try:
        with ExcelService(excel).lock():
            shutil.copy2(excel, target/'dados_dashboard.xlsx')
            with closing(sqlite3.connect(auth)) as source, closing(sqlite3.connect(target/'auth.sqlite3')) as dest:
                source.backup(dest)
                if dest.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                    raise RuntimeError('Backup SQLite inválido')
        (target/'COMPLETE').touch()
    except Exception:
        (target/'INCOMPLETE').touch()
        raise
    return target

if __name__ == '__main__':
    print(backup(os.environ['DASHBOARD_EXCEL_PATH'], Path(os.environ['DASHBOARD_AUTH_DIRECTORY'])/'auth.sqlite3', '/var/lib/dashboardos/backups'))
