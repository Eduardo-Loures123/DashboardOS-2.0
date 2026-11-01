from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tests.common import DataCase
from scripts.gerar_dados import gerar

class ExcelTests(DataCase):
    def test_quantidades_integridade_reprodutibilidade(self):
        data=self.store.read();self.store.validate(data)
        self.assertEqual(data,self.raw)
        generated=gerar(Path(self.temp.name)/'outro.xlsx')
        self.assertEqual({k:len(v) for k,v in generated.items()},{'Funcionarios':100,'Equipes':10,'OrdensServico':500,'Acessos':500,'Renovacoes':150})
        self.assertEqual(gerar(Path(self.temp.name)/'reproducao.xlsx'),generated)
        with self.assertRaises(FileExistsError):gerar(self.path)
    def test_crud_persistencia_e_backup(self):
        record=dict(self.raw['Acessos'][0]);record.pop('codigo');record['sistema']='Teste persistente'
        code=self.store.mutate('Acessos',record)
        self.assertEqual(next(r for r in self.store.read()['Acessos'] if r['codigo']==code)['sistema'],'Teste persistente')
        record['sistema']='Editado';self.store.mutate('Acessos',record,code)
        self.assertEqual(next(r for r in self.store.read()['Acessos'] if r['codigo']==code)['sistema'],'Editado')
        self.store.mutate('Acessos',code=code,delete=True)
        self.assertEqual(len(self.store.read()['Acessos']),len(self.raw['Acessos']))
        self.assertEqual(len(list((self.path.parent/'backups').glob('*.xlsx'))),3)
    def test_exclusao_relacionada_nao_altera_arquivo(self):
        before=self.path.read_bytes()
        for sheet,code in [('Funcionarios','FUNC0001'),('Equipes','EQ0001'),('Acessos','AC0001')]:
            with self.assertRaises(ValueError):self.store.mutate(sheet,code=code,delete=True)
        self.assertEqual(before,self.path.read_bytes())
    def test_validacao(self):
        for changes in [{'email':'invalido'},{'equipe':'EQ9999'},{'admissao':'2026-02-30'},{'nome':''},{'status':'Inválido'}]:
            with self.assertRaises(ValueError):self.store.mutate('Funcionarios',dict(self.raw['Funcionarios'][0],**changes),'FUNC0001')
        for changes in [{'previsao':'1900-01-01'},{'status':'Concluída','conclusao':''}]:
            with self.assertRaises(ValueError):self.store.mutate('OrdensServico',dict(self.raw['OrdensServico'][0],**changes),'OS0001')
    def test_gravacoes_concorrentes(self):
        record=dict(self.raw['Renovacoes'][0]);record.pop('codigo')
        with ThreadPoolExecutor(max_workers=2) as pool:codes=list(pool.map(lambda _:self.store.mutate('Renovacoes',record),range(2)))
        self.assertEqual(len(set(codes)),2);self.assertEqual(len(self.store.read()['Renovacoes']),len(self.raw['Renovacoes'])+2)
