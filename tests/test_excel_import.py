"""Only synthetic inventories and temporary authentication databases are modified."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from datetime import date, datetime, timedelta
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch
import hashlib
import json
import secrets
import zipfile

from openpyxl import Workbook, load_workbook
from openpyxl.utils.datetime import to_excel

from app import create_app
from services.deadline_service import order_deadlines
from services.excel_import_service import read_upload, compare_upload, MAX_UPLOAD
from services.excel_service import ExcelService
from services.import_coordinator import ImportConflict, fingerprint
from services.schema import SCHEMA
from tests.common import login_admin


def inventory():
    today=date.today();past=(today-timedelta(days=90)).isoformat();future=(today+timedelta(days=90)).isoformat()
    return {'Funcionarios':[dict(codigo='FUNC0001',nome='Pessoa de teste',equipe='EQ0001',cargo='Analista',email='pessoa@example.test',admissao=past,status='Ativo')],
            'Equipes':[dict(codigo='EQ0001',nome='Equipe de teste',responsavel='FUNC0001')],
            'OrdensServico':[dict(codigo='OS0001',descricao='Ordem de teste',funcionario='FUNC0001',abertura=past,previsao=future,conclusao='',prioridade='Média',status='Pendente')],
            'Acessos':[dict(codigo='AC0001',funcionario='FUNC0001',sistema='Recurso de teste',concessao=past,vencimento=future,status='Ativo')],
            'Renovacoes':[dict(codigo='REN0001',acesso='AC0001',solicitacao=past,status='Pendente',responsavel='FUNC0001',observacoes='')]}


def workbook_bytes(data, headers=None):
    book=Workbook();book.remove(book.active)
    for name,rows in data.items():
        sheet=book.create_sheet(name);columns=(headers or {}).get(name,SCHEMA.get(name,['codigo']))
        sheet.append(columns)
        for row in rows:sheet.append([row.get(k,'') for k in columns])
    result=BytesIO();book.save(result);book.close();return result.getvalue()


class ImportBase(TestCase):
    def setUp(self):
        temp=TemporaryDirectory();self.addCleanup(temp.cleanup);self.root=Path(temp.name)
        self.path=self.root/'inventory.xlsx';self.raw=inventory()
        ExcelService._write_workbook(self.path,self.raw)
        self.app=create_app(self.path,auth_directory=self.root/'instance');self.app.testing=True
        self.store=self.app.config['STORE'];self.service=self.app.config['ENTERPRISE'];self.auth=self.app.config['AUTH'];self.imports=self.app.config['IMPORTS']
        self.client=self.app.test_client();self.password=secrets.token_urlsafe(24)
        self.headers=login_admin(self.app,self.client,'import-admin',self.password)
        self.initial=fingerprint(self.path)

    def preview(self,data,mode='upsert',client=None,headers=None):
        return (client or self.client).post('/api/import/preview',headers=headers or self.headers,
            data={'mode':mode,'file':(BytesIO(workbook_bytes(data)),'dados.xlsx')},content_type='multipart/form-data')

    def confirm(self,token):return self.client.post('/api/import/confirm',json={'token':token},headers=self.headers)

    def protected(self):
        with self.auth.connect() as db:
            return {table:[tuple(r) for r in db.execute('SELECT * FROM '+table)] for table in ('users','account','events','notifications','outbox','mail_attempts','tokens')}

class ImportTests(ImportBase):
    def test_preview_updates_no_inventory_or_notifications(self):
        source=deepcopy(self.raw);source['Acessos'][0]['sistema']='Recurso atualizado'
        before=self.protected();response=self.preview(source)
        self.assertEqual(response.status_code,200,response.json);self.assertTrue(response.json['can_confirm'])
        self.assertEqual(response.json['totals']['updated'],1);self.assertEqual(response.json['totals']['unchanged'],4)
        self.assertEqual(fingerprint(self.path),self.initial);self.assertEqual(self.protected(),before)
        self.assertFalse((self.root/'backups').exists())

    def test_roundtrip_own_exports_and_partial_sheet(self):
        for page in ('dashboard','funcionarios','equipes','ordens-servico','acessos','vencimentos','renovacoes'):
            response=self.client.get('/api/export/'+page);self.assertEqual(response.status_code,200)
            parsed,errors=read_upload(response.data,page+'.xlsx')
            _,analysis=compare_upload(self.store,self.raw,parsed,'upsert',errors)
            self.assertEqual(analysis['errors'],[],page);self.assertFalse(analysis['can_confirm'],page)

    def test_add_update_preserve_absent_records_and_replay_once(self):
        self.service.scan(self.raw)
        with self.auth.connect() as db:
            db.execute("UPDATE account SET email='import@example.test',verified=1,email_alerts=1 WHERE user_id='import-admin'")
            self.service.emit(db,'historical:test','operational','Histórico fictício','Não enviar','/acessos')
        source={'Acessos':[dict(self.raw['Acessos'][0],sistema='Atualizado'),dict(self.raw['Acessos'][0],codigo='AC0002')]}
        response=self.preview(source);token=response.json['token'];before=self.protected()
        with patch.object(self.store,'observer',side_effect=AssertionError('No notification scan')):
            result=self.confirm(token)
        self.assertEqual(result.status_code,200,result.json);self.assertEqual(result.json['totals']['added'],1);self.assertEqual(result.json['totals']['updated'],1)
        saved=self.store.read();self.assertEqual(len(saved['Acessos']),2);self.assertEqual(saved['Funcionarios'],self.raw['Funcionarios'])
        self.assertEqual(saved['Acessos'][0]['sistema'],'Atualizado');self.assertEqual(self.protected(),before)
        self.assertEqual(self.service.scan(saved),0)
        replay=self.confirm(token);self.assertTrue(replay.json['replayed']);self.assertEqual(len(self.store.read()['Acessos']),2)
        with self.auth.connect() as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE action='import.excel.confirm'").fetchone()[0],1)
        self.assertEqual(len(list((self.root/'backups').glob('import_*.xlsx'))),1)

    def test_new_only_ignores_existing(self):
        source={'Acessos':[dict(self.raw['Acessos'][0],sistema='Não aplicar'),dict(self.raw['Acessos'][0],codigo='AC0002')]}
        preview=self.preview(source,'new').json;self.assertEqual(preview['totals']['ignored'],1)
        self.assertEqual(self.confirm(preview['token']).status_code,200)
        self.assertEqual(self.store.read()['Acessos'][0],self.raw['Acessos'][0])

    def test_cross_sheet_relationships_resolved_after_all_merges(self):
        source={'Equipes':[dict(self.raw['Equipes'][0],codigo='EQ0002',responsavel='FUNC0002')],
                'Funcionarios':[dict(self.raw['Funcionarios'][0],codigo='FUNC0002',equipe='EQ0002')],
                'Acessos':[dict(self.raw['Acessos'][0],codigo='AC0002',funcionario='FUNC0002')]}
        preview=self.preview(source).json;self.assertEqual(preview['errors'],[])
        self.assertEqual(self.confirm(preview['token']).status_code,200);self.store.validate(self.store.read())

    def test_invalid_reference_duplicate_status_email_and_dates_block_everything(self):
        variants=[]
        for sheet,field,value in [('Acessos','funcionario','FUNC9999'),('Acessos','status','Desconhecido'),('Funcionarios','email','invalido'),('OrdensServico','previsao','2026-99-90'),('OrdensServico','conclusao',date.today().isoformat()),('Acessos','vencimento','05/06/2026')]:
            variants.append({sheet:[dict(self.raw[sheet][0],**{field:value})]})
        variants.append({'Acessos':[self.raw['Acessos'][0],self.raw['Acessos'][0]]})
        for data in variants:
            with self.subTest(data=data):
                response=self.preview(data);self.assertEqual(response.status_code,200,response.json)
                self.assertTrue(response.json['errors']);self.assertFalse(response.json['can_confirm'])
                self.assertEqual(self.confirm(response.json['token']).status_code,409)
                self.assertEqual(fingerprint(self.path),self.initial)

    def test_dates_native_serial_iso_timestamp_and_unambiguous_day_first(self):
        future=date.today()+timedelta(days=120)
        for value in (future,datetime.combine(future,datetime.min.time()),to_excel(future),future.isoformat(),future.isoformat()+'T14:30:00'):
            source={'Acessos':[dict(self.raw['Acessos'][0],vencimento=value)]}
            parsed,errors=read_upload(workbook_bytes(source),'data.xlsx');self.assertEqual(errors,[])
            self.assertEqual(parsed['Acessos'][0]['record']['vencimento'],future.isoformat())
        parsed,errors=read_upload(workbook_bytes({'Funcionarios':[dict(self.raw['Funcionarios'][0],admissao='25/12/2020')]}),'data.xlsx')
        self.assertEqual(errors,[]);self.assertEqual(parsed['Funcionarios'][0]['record']['admissao'],'2020-12-25')

    def test_empty_corrupt_disguised_missing_headers_unknown_tabs(self):
        for content,name in [(b'','vazio.xlsx'),(b'MZexecutable','arquivo.xlsx'),(b'PKinvalid','corrompido.xlsx'),(workbook_bytes(self.raw),'arquivo.exe'),(workbook_bytes({'Equipes':[]}),'vazio.xlsx'),(workbook_bytes({'Usuarios':[]}),'externo.xlsx'),(workbook_bytes({'Equipes':self.raw['Equipes']},{'Equipes':['codigo','nome']}),'faltando.xlsx')]:
            with self.subTest(name=name),self.assertRaises(ValueError):read_upload(content,name)
        self.assertEqual(fingerprint(self.path),self.initial)

    def test_formulas_and_external_links_are_rejected(self):
        response=self.preview({'Acessos':[dict(self.raw['Acessos'][0],sistema='=1+1')]})
        self.assertTrue(response.json['errors']);self.assertFalse(response.json['can_confirm'])
        source=workbook_bytes({'Acessos':self.raw['Acessos']});out=BytesIO()
        with zipfile.ZipFile(BytesIO(source)) as src,zipfile.ZipFile(out,'w') as dest:
            for item in src.infolist():
                payload=src.read(item)
                if item.filename=='_rels/.rels':payload=payload.replace(b'</Relationships>',b'<Relationship Id="evil" Type="external" Target="https://example.test" TargetMode="External"/></Relationships>')
                dest.writestr(item,payload)
        with self.assertRaisesRegex(ValueError,'externas'):read_upload(out.getvalue(),'external.xlsx')

    def test_limits_path_traversal_and_xml_entities(self):
        with self.assertRaises(ValueError):read_upload(b'x'*(MAX_UPLOAD+1),'large.xlsx')
        for name,payload in [('../evil.xml',b'<test/>'),('evil.xml',b'<!DOCTYPE t [<!ENTITY x "boom">]><t>&x;</t>')]:
            out=BytesIO()
            with zipfile.ZipFile(out,'w') as archive:archive.writestr(name,payload)
            with self.assertRaises(ValueError):read_upload(out.getvalue(),'evil.xlsx')
        book=Workbook();ws=book.active;ws.title='Equipes';ws.append(SCHEMA['Equipes']);ws.cell(5002,1,'EQ9999');out=BytesIO();book.save(out)
        with self.assertRaises(ValueError):read_upload(out.getvalue(),'excess.xlsx')

    def test_sensitive_columns_are_not_mapped(self):
        content=workbook_bytes({'Equipes':self.raw['Equipes']},{'Equipes':SCHEMA['Equipes']+['password_hash']})
        with self.assertRaisesRegex(ValueError,'password_hash'):read_upload(content,'sensivel.xlsx')

    def test_import_preserves_extra_existing_data_without_accepting_uploaded_extra_fields(self):
        self.raw['Equipes'][0]['nota_legada']='Preservar'
        self.raw['Acessos'][0]['nota_legada']='Também preservar'
        ExcelService._write_workbook(self.path,self.raw,preserve_extra=True)
        source={'Acessos':[{k:v for k,v in dict(self.raw['Acessos'][0],sistema='Revisado').items() if k in SCHEMA['Acessos']}]}
        preview=self.preview(source).json;self.assertEqual(self.confirm(preview['token']).status_code,200)
        result=self.store.read();self.assertEqual(result['Equipes'][0]['nota_legada'],'Preservar');self.assertEqual(result['Acessos'][0]['nota_legada'],'Também preservar')

    def test_stale_preview_rejected_after_other_writer(self):
        preview=self.preview({'Acessos':[dict(self.raw['Acessos'][0],sistema='Novo')]}).json
        self.store.mutate('Equipes',dict(self.raw['Equipes'][0],nome='Edição concorrente'),'EQ0001')
        result=self.confirm(preview['token']);self.assertEqual(result.status_code,409,result.json)
        self.assertEqual(self.store.read()['Acessos'],self.raw['Acessos'])

    def test_cancel_expiry_owner_and_tampering(self):
        source={'Acessos':[dict(self.raw['Acessos'][0],sistema='Novo')]}
        preview=self.preview(source).json;token=preview['token']
        with self.assertRaises(ImportConflict):self.imports.confirm(token,'another-session','import-admin')
        self.assertEqual(self.client.post('/api/import/confirm',json={'token':token,'rows':source},headers=self.headers).status_code,400)
        self.assertEqual(self.client.post('/api/import/cancel',json={'token':token},headers=self.headers).status_code,200)
        self.assertEqual(self.confirm(token).status_code,409)
        preview=self.preview(source).json;self.imports.pending[preview['token']]['expires']=0
        self.assertEqual(self.confirm(preview['token']).status_code,409);self.assertEqual(fingerprint(self.path),self.initial)

    def test_permission_backend_and_csrf(self):
        guest=self.app.test_client();guest.get('/login')
        with guest.session_transaction() as session:headers={'X-CSRF-Token':session['csrf']}
        self.assertEqual(guest.post('/api/import/preview',headers=headers).status_code,401)
        guest.post('/auth/guest',json={},headers=headers)
        with guest.session_transaction() as session:headers={'X-CSRF-Token':session['csrf']}
        self.assertEqual(guest.post('/api/import/preview',headers=headers).status_code,403)
        self.assertEqual(self.client.post('/api/import/confirm',json={'token':'unknown'}).status_code,403)
        self.assertEqual(self.client.get('/api/import/confirm').status_code,405)
        self.service.promote_initial('import-admin',self.password)
        self.service.create_user('import-admin',{'user_id':'reader','password':self.password,'role':'user'})
        user=self.app.test_client();user.get('/login')
        with user.session_transaction() as session:headers={'X-CSRF-Token':session['csrf']}
        user.post('/login',json={'user_id':'reader','password':self.password},headers=headers)
        with user.session_transaction() as session:headers={'X-CSRF-Token':session['csrf']}
        for endpoint in ('preview','confirm','cancel'):self.assertEqual(user.post('/api/import/'+endpoint,json={'token':'unknown'},headers=headers).status_code,403)
        self.assertNotIn('id="import-excel"',user.get('/acessos').text)

    def test_staging_failure_and_sqlite_failure_roll_back(self):
        source={'Acessos':[dict(self.raw['Acessos'][0],sistema='Novo')]}
        for target in ('stage','sqlite','replace'):
            preview=self.preview(source).json;before=self.protected()
            if target=='stage':mock=patch.object(self.store,'_write_workbook',side_effect=OSError('disk'))
            elif target=='sqlite':mock=patch.object(self.imports,'_snapshot',side_effect=RuntimeError('db'))
            else:
                import os
                original_replace=os.replace
                def fail_replace(source,dest):
                    if Path(dest)==self.path and str(source).endswith('.import.xlsx'):raise PermissionError('File held open')
                    return original_replace(source,dest)
                mock=patch('services.import_coordinator.os.replace',side_effect=fail_replace)
            with mock:self.assertEqual(self.confirm(preview['token']).status_code,409)
            self.assertEqual(fingerprint(self.path),self.initial);self.assertEqual(self.protected(),before)
            self.assertFalse(self.imports.journal.exists())

    def test_commit_failure_after_file_replacement_recovers_original(self):
        preview=self.preview({'Acessos':[dict(self.raw['Acessos'][0],sistema='Novo')]}).json
        original_connect=self.auth.connect
        from contextlib import contextmanager
        @contextmanager
        def failing_connect():
            with original_connect() as db:
                class Proxy:
                    def __getattr__(self,name):return getattr(db,name)
                    def commit(self):raise RuntimeError('Simulated SQLite commit failure')
                yield Proxy()
        with patch.object(self.auth,'connect',failing_connect):self.assertEqual(self.confirm(preview['token']).status_code,409)
        self.assertEqual(fingerprint(self.path),self.initial)
        with self.auth.connect() as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM audit WHERE action='import.excel.confirm'").fetchone()[0],0)

    def test_concurrent_coordinators_serialize_and_reject_stale_plan(self):
        from services.import_coordinator import ImportCoordinator
        first=ImportCoordinator(ExcelService(self.path),self.auth,self.service)
        second=ImportCoordinator(ExcelService(self.path),self.auth,self.service)
        source=workbook_bytes({'Acessos':[dict(self.raw['Acessos'][0],codigo='AC0002')]})
        a=first.preview(source,'a.xlsx','upsert','a');b=second.preview(source,'b.xlsx','upsert','b')
        def run(coordinator,token,owner):
            try:return coordinator.confirm(token,owner,'import-admin')['totals']['added']
            except ImportConflict:return 'conflict'
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(run,first,a['token'],'a'),pool.submit(run,second,b['token'],'b')]
            self.assertCountEqual([f.result() for f in futures],[1,'conflict'])
        self.assertEqual(len(self.store.read()['Acessos']),2)

    def test_pending_journal_recovery_and_committed_receipt(self):
        for committed in (False,True):
            ExcelService._write_workbook(self.path,self.raw)
            before=fingerprint(self.path);backup=self.root/'backups'/'recovery.xlsx';backup.parent.mkdir(exist_ok=True);backup.write_bytes(self.path.read_bytes())
            updated=deepcopy(self.raw);updated['Acessos'][0]['sistema']='Recuperado';ExcelService._write_workbook(self.path,updated)
            receipt='recovery-'+str(committed)
            self.imports._write_journal(dict(backup=backup.name,before=before,after=fingerprint(self.path),receipt=receipt))
            if committed:
                with self.auth.connect() as db:self.service.audit(db,'import-admin','import.excel.confirm',receipt)
            saved=self.store.read()
            self.assertEqual(saved['Acessos'][0]['sistema'],'Recuperado' if committed else self.raw['Acessos'][0]['sistema'])
            self.assertFalse(self.imports.journal.exists())


class DeadlineTests(ImportBase):
    def test_deadline_search_and_export_use_the_visible_classification(self):
        raw=deepcopy(self.raw)
        raw['OrdensServico'][0]['previsao']=date.today().isoformat()
        raw['Acessos'][0]['vencimento']=date.today().isoformat()
        ExcelService._write_workbook(self.path,raw)
        for query,sheet in [('', 'Acessos'),('tipo=os&','OrdensServico')]:
            response=self.client.get('/api/data/vencimentos?'+query+'q=Urgente')
            self.assertEqual(len(response.json['rows']),1,response.json)
            exported=self.client.get('/api/export/vencimentos?'+query+'q=Urgente')
            book=load_workbook(BytesIO(exported.data),read_only=True)
            try:self.assertEqual(book[sheet].max_row,2)
            finally:book.close()

    def test_access_missing_deadline_stays_visible_without_breaking_summaries(self):
        raw=deepcopy(self.raw);raw['Acessos'][0]['vencimento']=''
        ExcelService._write_workbook(self.path,raw)
        for page in ('dashboard','vencimentos','relatorios'):
            result=self.client.get('/api/data/'+page);self.assertEqual(result.status_code,200,result.json)
            if page=='vencimentos':self.assertEqual(result.json['rows'][0]['situacao'],'Sem prazo válido');self.assertIsNone(result.json['rows'][0]['dias'])

    def test_order_existing_rules_boundaries_completed_and_missing_date(self):
        today=date.today();rows=[]
        for remaining in (-1,0,30,31,45,46):rows.append(dict(self.raw['OrdensServico'][0],previsao=(today+timedelta(days=remaining)).isoformat()))
        rows+=[dict(rows[0],status='Concluída'),dict(rows[0],previsao=''),dict(rows[0],previsao='invalid')]
        result=order_deadlines(rows,today)
        self.assertEqual([r['situacao'] for r in result],['Vencidos','Vencem hoje','Até 30 dias','31 a 45 dias','31 a 45 dias','Após 45 dias','Encerrado','Sem prazo válido','Sem prazo válido'])
        self.assertIsNone(result[-1]['dias']);self.assertNotIn('situacao',rows[0])

    def test_deadline_api_filters_fields_export_and_no_record_mutation(self):
        ac=self.client.get('/api/data/vencimentos').json;os=self.client.get('/api/data/vencimentos?tipo=os').json
        self.assertEqual(ac['sheet'],'Acessos');self.assertEqual(os['sheet'],'OrdensServico')
        for field in ('dias','situacao','status','previsao','equipe','funcionario'):self.assertIn(field,os['columns'])
        self.assertIn('status',os['filterFields']);self.assertNotIn('sistema',os['filterFields'])
        self.assertEqual(self.client.get('/api/data/vencimentos?tipo=os&status=Concluída').json['rows'],[])
        self.assertEqual(self.client.get('/api/data/vencimentos?tipo=os&situacao=Após%2045%20dias').json['rows'][0]['codigo'],'OS0001')
        self.assertEqual(self.client.get('/api/data/vencimentos?tipo=invalid').status_code,400)
        self.assertEqual(self.client.get('/api/export/vencimentos?tipo=os').status_code,200)
        self.assertEqual(fingerprint(self.path),self.initial)
