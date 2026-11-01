from io import BytesIO
import pandas as pd
from app import create_app,PAGES
from tests.common import DataCase,login_admin

class RouteTests(DataCase):
    def setUp(self):
        super().setUp();self.app=create_app(self.path);self.app.testing=True;self.client=self.app.test_client()
        self.headers=login_admin(self.app,self.client)
    def test_paginas_apis_exportacoes(self):
        for page in PAGES:
            with self.subTest(page=page):
                self.assertEqual(self.client.get('/'+page).status_code,200)
                result=self.client.get('/api/data/'+page);self.assertEqual(result.status_code,200)
                self.assertIn('indicators',result.json)
                export=self.client.get('/api/export/'+page);self.assertEqual(export.status_code,200)
                book=pd.ExcelFile(BytesIO(export.data));self.assertTrue(book.sheet_names)
        self.assertEqual(self.client.get('/inexistente').status_code,404)
    def test_crud_todas_tabelas(self):
        for sheet in ['Funcionarios','Equipes','OrdensServico','Acessos','Renovacoes']:
            with self.subTest(sheet=sheet):
                record=dict(self.raw[sheet][0]);record.pop('codigo')
                result=self.client.post('/api/records/'+sheet,json=record,headers=self.headers);self.assertEqual(result.status_code,200,result.json)
                code=result.json['codigo'];key={'Funcionarios':'nome','Equipes':'nome','OrdensServico':'descricao','Acessos':'sistema','Renovacoes':'observacoes'}[sheet];record[key]='Alterado em teste'
                result=self.client.put('/api/records/'+sheet+'/'+code,json=record,headers=self.headers);self.assertEqual(result.status_code,200,result.json)
                self.assertEqual(next(r for r in self.store.read()[sheet] if r['codigo']==code)[key],'Alterado em teste')
                self.assertEqual(self.client.delete('/api/records/'+sheet+'/'+code,headers=self.headers).status_code,200)
    def test_filtros_isolados_exportacao(self):
        result=self.client.get('/api/data/funcionarios?equipe=EQ0001&status=Ativo').json
        self.assertTrue(result['rows']);self.assertTrue(all(r['equipe']=='EQ0001' and r['status']=='Ativo' for r in result['rows']))
        self.assertEqual(len(self.client.get('/api/data/funcionarios').json['rows']),len(self.raw['Funcionarios']))
        book=pd.read_excel(BytesIO(self.client.get('/api/export/funcionarios?equipe=EQ0001').data))
        self.assertEqual(len(book),sum(r['equipe']=='EQ0001' for r in self.raw['Funcionarios']))
        filtered=self.client.get('/api/data/dashboard?equipe=EQ0001').json
        self.assertEqual(filtered['indicators']['Funcionários'],len(book))
        self.assertEqual(len(self.client.get('/api/data/relatorios').json['reports']),7)
    def test_csrf_dados_invalidos_e_host(self):
        self.assertEqual(self.client.post('/api/records/Funcionarios',json={}).status_code,403)
        self.assertEqual(self.client.post('/api/records/Funcionarios',json={},headers=self.headers).status_code,400)
        self.assertEqual(self.client.get('/',headers={'Host':'example.com'}).status_code,403)
    def test_formula_exportacao(self):
        record=dict(self.raw['Renovacoes'][0],observacoes='=1+1')
        self.store.mutate('Renovacoes',record,'REN0001')
        frame=pd.read_excel(BytesIO(self.client.get('/api/export/renovacoes').data))
        self.assertEqual(frame.iloc[0]['observacoes'],"'=1+1")
    def test_configuracao_graficos_e_dialogos(self):
        from pathlib import Path
        root=Path(__file__).resolve().parents[1]
        js=(root/'static/js/charts.js').read_text(encoding='utf-8')
        for value in ['displayModeBar:false','scrollZoom:false','doubleClick:false','dragmode:false','fixedrange:true']:self.assertIn(value,js)
        self.assertIn('showModal()', (root/'static/js/modals.js').read_text(encoding='utf-8'))
        self.assertIn('data-chart="teams"',self.client.get('/').text)
