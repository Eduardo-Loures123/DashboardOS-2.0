from contextlib import closing
import os
import secrets
from unittest.mock import patch
from app import create_app
from tests.common import DataCase
from deployment.aws.backup import backup
import sqlite3

class ProductionTests(DataCase):
    def environment(self):
        return dict(DASHBOARD_ENV='production', SECRET_KEY=secrets.token_hex(32), DASHBOARD_ALLOWED_HOSTS='dashboard.example.test', DASHBOARD_EXCEL_PATH=str(self.path), DASHBOARD_AUTH_DIRECTORY=str(self.path.parent/'instance'))

    def test_fail_closed(self):
        with patch.dict(os.environ, {'DASHBOARD_ENV':'production','SECRET_KEY':''}):
            with self.assertRaises(RuntimeError):create_app(self.path)

    def test_https_proxy_permissions_and_backup(self):
        create_app(self.path)  # autenticação isolada, nunca o banco original
        with patch.dict(os.environ, self.environment()):
            app=create_app();app.testing=True;client=app.test_client()
            base='https://dashboard.example.test'
            response=client.get('/login',base_url=base,headers={'X-Forwarded-Host':'evil.test','X-Forwarded-Proto':'https','X-Forwarded-For':'203.0.113.5'})
            self.assertEqual(response.status_code,200)
            self.assertIn('Secure',response.headers['Set-Cookie'])
            self.assertIn('HttpOnly',response.headers['Set-Cookie'])
            self.assertIn('Strict-Transport-Security',response.headers)
            self.assertEqual(client.get('/login',base_url='https://evil.test').status_code,403)
            with client.session_transaction(base_url=base) as session:csrf=session['csrf']
            self.assertEqual(client.post('/auth/guest',base_url=base,headers={'X-CSRF-Token':csrf}).status_code,302)
            self.assertEqual(client.get('/api/data/dashboard',base_url=base).status_code,200)
            with client.session_transaction(base_url=base) as session:csrf=session['csrf']
            self.assertEqual(client.post('/api/records/Equipes',base_url=base,json={},headers={'X-CSRF-Token':csrf}).status_code,403)
            for url in ['/dados/dados_dashboard.xlsx','/instance/auth.sqlite3','/static/../instance/auth.sqlite3']:
                self.assertNotEqual(client.get(url,base_url=base).status_code,200)
            auth=app.config['AUTH'];auth.create_admin('persistido',secrets.token_urlsafe(24))
            target=backup(self.path,auth.path,self.path.parent/'backups-deploy')
            self.assertEqual((target/'dados_dashboard.xlsx').read_bytes(),self.path.read_bytes())
            with closing(sqlite3.connect(target/'auth.sqlite3')) as db:
                self.assertEqual(db.execute('SELECT id FROM users').fetchone()[0],'persistido')
            self.assertTrue((target/'COMPLETE').exists())
            self.assertTrue(create_app().config['AUTH'].has_admin())

    def test_random_hex_secret_need_not_contain_every_hex_digit(self):
        create_app(self.path)
        environment=self.environment()
        # Chave aleatória válida que deliberadamente não usa o dígito f.
        environment['SECRET_KEY']=''.join(secrets.choice('0123456789abcde') for _ in range(64))
        with patch.dict(os.environ,environment):
            app=create_app()
            self.assertFalse(app.debug)
            self.assertFalse(app.testing)
