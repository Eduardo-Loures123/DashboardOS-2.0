"""Protecoes da release; sem rede ou dados reais."""
import os
import unittest
from unittest.mock import Mock, patch
from services.mail_service import email_suspended, mail_configuration, process_outbox, smtp_send
from tests.common import DataCase, login_admin
from app import create_app

class ReleaseTests(DataCase):
    def test_nome_e_avatar_abrem_perfil_autenticado(self):
        app=create_app(self.path);client=app.test_client();login_admin(app,client)
        from html.parser import HTMLParser
        class Links(HTMLParser):
            found=[]
            def handle_starttag(self,tag,attrs):
                attrs=dict(attrs)
                if tag=='a' and attrs.get('class') in ('header-identity','account-avatar'):
                    self.found.append(attrs)
        parser=Links();parser.feed(client.get('/dashboard').text)
        self.assertEqual(len(parser.found),2)
        self.assertTrue(all(a.get('href')=='/perfil' for a in parser.found))
        self.assertEqual(client.get('/perfil').status_code,200)

    def test_suspensao_sem_marcador_nao_abre_fila_nem_smtp(self):
        with patch.dict(os.environ,{'DASHBOARD_MAIL_ENABLED':'true'},clear=True):
            auth=Mock();sender=Mock()
            self.assertTrue(email_suspended());self.assertFalse(mail_configuration()['enabled'])
            self.assertEqual(process_outbox(auth,sender),0)
            auth.connect.assert_not_called();sender.assert_not_called()
            with patch('services.mail_service.smtplib.SMTP') as smtp:
                with self.assertRaises(RuntimeError):smtp_send('fake@example.test','Test','Test')
                smtp.assert_not_called()

    def test_marcador_invalido_bloqueia_e_cli_legada_nao_le_excel(self):
        app=create_app(self.path)
        for value in ('true','','0','no','FALSE_WITH_TYPO'):
            with self.subTest(value=value),patch.dict(os.environ,{'DASHBOARD_EMAIL_SUSPENDED':value,'DASHBOARD_MAIL_ENABLED':'true'}):
                with patch.object(app.config['ENTERPRISE'],'scan') as scan:
                    result=app.test_cli_runner().invoke(args=['processar-alertas'])
                    self.assertNotEqual(result.exit_code,0);scan.assert_not_called()
                self.assertEqual(process_outbox(Mock(),Mock()),0)

    def test_preflight_somente_leitura_e_schema_incompativel(self):
        import hashlib
        import secrets
        from deployment.aws.preflight_existente import check
        app=create_app(self.path);auth=app.config['AUTH']
        env=dict(DASHBOARD_ENV='production',SECRET_KEY=secrets.token_hex(32),DASHBOARD_ALLOWED_HOSTS='dashboard.example.test',DASHBOARD_EXCEL_PATH=str(self.path),DASHBOARD_AUTH_DIRECTORY=str(auth.directory),DASHBOARD_EMAIL_SUSPENDED='true')
        before=hashlib.sha256(auth.path.read_bytes()).hexdigest()
        with patch.dict(os.environ,env):
            check()
            self.assertEqual(hashlib.sha256(auth.path.read_bytes()).hexdigest(),before)
            with auth.connect() as db:db.execute('DROP TABLE profile_email_changes')
            with self.assertRaisesRegex(RuntimeError,'Estrutura incompativel'):check()

    def test_backup_offline_verifica_copia_sem_modificar_origens(self):
        import hashlib
        import json
        from deployment.aws.backup_existente import backup
        app=create_app(self.path);auth=app.config['AUTH']
        code=self.path.parent/'release';code.mkdir();(code/'app.py').write_text('# fictional')
        config=self.path.parent/'runtime.env';config.write_text('# fictional')
        before=hashlib.sha256(auth.path.read_bytes()).hexdigest()
        with patch.dict(os.environ,dict(DASHBOARD_EXCEL_PATH=str(self.path),DASHBOARD_AUTH_DIRECTORY=str(auth.directory))):
            result=backup(self.path.parent.parent/'release-backups',code,config)
        self.assertTrue((result/'COMPLETE').exists())
        self.assertEqual(before,hashlib.sha256(auth.path.read_bytes()).hexdigest())
        manifest=json.loads((result/'manifest.json').read_text())['sha256']
        self.assertTrue(all(hashlib.sha256((result/name).read_bytes()).hexdigest()==digest for name,digest in manifest.items()))
