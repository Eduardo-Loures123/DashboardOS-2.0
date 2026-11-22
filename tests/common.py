import tempfile, unittest
import shutil
import secrets
import os
from unittest.mock import patch
from pathlib import Path
from services.excel_service import ExcelService

def enable_mock_mail(case):
    """Exercise the legacy opt-in path with fake adapters, never real SMTP.

    ReleaseTests separately assert that absent/invalid opt-in blocks all work.
    Preserve this fixture only for transport/legacy compatibility tests.
    """
    enabled = patch.dict(os.environ, {'DASHBOARD_EMAIL_SUSPENDED': 'false'})
    enabled.start(); case.addCleanup(enabled.stop)
    network = patch('socket.create_connection', side_effect=AssertionError('Real SMTP forbidden in tests'))
    network.start(); case.addCleanup(network.stop)

def login_admin(app,client,user_id='teste-admin',password=None):
    password=password or secrets.token_urlsafe(24)
    app.config['AUTH'].create_admin(user_id,password)
    client.get('/login')
    with client.session_transaction() as session:csrf=session['csrf']
    response=client.post('/login',json={'user_id':user_id,'password':password},headers={'X-CSRF-Token':csrf})
    if response.status_code!=200:raise AssertionError(response.json)
    with client.session_transaction() as session:return {'X-CSRF-Token':session['csrf']}

class DataCase(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path=Path(self.temp.name)/'dados.xlsx'
        shutil.copy2(Path(__file__).resolve().parents[1]/'dados/dados_dashboard.xlsx',self.path)
        self.store=ExcelService(self.path)
        self.raw=self.store.read()
