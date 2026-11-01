from io import BytesIO
from pathlib import Path
import hashlib
import pandas as pd
from app import create_app
from tests.common import DataCase,login_admin
from services.excel_service import ExcelService

class StabilityRoutes(DataCase):
    def setUp(self):
        super().setUp();self.app=create_app(self.path);self.app.testing=True;self.client=self.app.test_client()
        login_admin(self.app,self.client)
    def test_pesquisa_relacoes_e_exportacao_iguais(self):
        cases=[('funcionarios','equipe','Equipes','nome'),('equipes','responsavel','Funcionarios','nome'),('ordens-servico','funcionario','Funcionarios','nome'),('acessos','equipe','Equipes','nome'),('renovacoes','responsavel','Funcionarios','nome')]
        for page,key,table,label in cases:
            with self.subTest(page=page):
                rows=self.client.get('/api/data/'+page).json['rows'];value=rows[0][key]
                query=next(r[label] for r in self.raw[table] if r['codigo']==value)+' · '+value
                response=self.client.get('/api/data/'+page,query_string={'q':query})
                self.assertEqual(response.status_code,200)
                self.assertTrue(response.json['rows'])
                exported=pd.read_excel(BytesIO(self.client.get('/api/export/'+page,query_string={'q':query}).data))
                self.assertEqual(set(exported.codigo),{r['codigo'] for r in response.json['rows']})
    def test_filtros_todas_paginas_e_limites_periodo(self):
        for page in ['dashboard','funcionarios','equipes','ordens-servico','acessos','vencimentos','renovacoes','relatorios']:
            base=self.client.get('/api/data/'+page).json
            for field,options in base['filters'].items():
                if not options:continue
                response=self.client.get('/api/data/'+page,query_string={field:options[0]})
                self.assertEqual(response.status_code,200)
                for row in response.json['rows']:self.assertEqual(str(row[field]),options[0])
        for page in ['dashboard','ordens-servico','renovacoes','relatorios']:
            self.assertEqual(self.client.get('/api/data/'+page+'?inicio=2026-10-30&fim=2026-10-01').status_code,400)
            self.assertEqual(self.client.get('/api/data/'+page+'?inicio=invalido').status_code,400)
    def test_estados_vazios_relatorios_e_exportacao(self):
        for page in ['funcionarios','equipes','ordens-servico','acessos','vencimentos','renovacoes']:
            self.assertEqual(self.client.get('/api/data/'+page+'?q=nao-existe-xxxx').json['rows'],[])
            self.assertEqual(self.client.get('/api/export/'+page+'?q=nao-existe-xxxx').status_code,200)
        reports=self.client.get('/api/data/relatorios?equipe=EQ-inexistente').json['reports']
        self.assertTrue(all(not rows for rows in reports.values()))
    def test_html_ids_unicos_e_arquivos_estaticos(self):
        from html.parser import HTMLParser
        class Inspector(HTMLParser):
            def __init__(self):super().__init__();self.ids=[];self.assets=[];self.links=[]
            def handle_starttag(self,tag,attrs):
                attrs=dict(attrs)
                if 'id' in attrs:self.ids.append(attrs['id'])
                if tag=='script' and 'src' in attrs:self.assets.append(attrs['src'])
                if tag=='link' and attrs.get('rel')=='stylesheet':self.assets.append(attrs['href'])
                if tag=='a' and attrs.get('href','').startswith('/'):self.links.append(attrs['href'])
        for page in ['dashboard','funcionarios','equipes','ordens-servico','acessos','vencimentos','renovacoes','relatorios']:
            parser=Inspector();parser.feed(self.client.get('/'+page).text)
            self.assertEqual(len(parser.ids),len(set(parser.ids)),page)
            for asset in parser.assets:
                response=self.client.get(asset);self.assertEqual(response.status_code,200,asset);response.close()
            for link in parser.links:self.assertEqual(self.client.get(link).status_code,200,link)

class PreservationTests(DataCase):
    def test_schema_invalido_erro_explicito(self):
        path=Path(self.temp.name)/'quebrada.xlsx'
        with pd.ExcelWriter(path) as writer:pd.DataFrame([{'codigo':'A'}]).to_excel(writer,sheet_name='Funcionarios',index=False)
        with self.assertRaisesRegex(ValueError,'Colunas ausentes'):ExcelService(path).read()
    def test_fonte_original_preservada_apos_escrita_na_copia(self):
        source=Path(__file__).resolve().parents[1]/'dados/dados_dashboard.xlsx'
        before=hashlib.sha256(source.read_bytes()).hexdigest()
        record=dict(self.raw['Renovacoes'][0],observacoes='Teste somente na cópia')
        self.store.mutate('Renovacoes',record,record['codigo'])
        self.assertEqual(hashlib.sha256(source.read_bytes()).hexdigest(),before)
