from pathlib import Path
from contextlib import contextmanager
from datetime import datetime, date
import os, shutil, time, uuid, logging
import pandas as pd
from .schema import SCHEMA, PREFIX, STATUS

class ExcelService:
    def __init__(self,path): self.path=Path(path); self.observer=None
    @contextmanager
    def lock(self):
        lock=Path(str(self.path)+'.lock'); deadline=time.monotonic()+10
        while True:
            try:
                fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY); break
            except FileExistsError:
                if time.monotonic()>deadline: raise ValueError('Planilha em uso. Tente novamente; se o sistema foi interrompido, remova o arquivo .lock com o servidor parado.')
                time.sleep(.05)
        try: yield
        finally: os.close(fd); lock.unlink(missing_ok=True)
    def read(self):
        with self.lock(): return self._read()
    def _read(self):
        with pd.ExcelFile(self.path,engine='openpyxl') as book:
            data={}
            for name,columns in SCHEMA.items():
                if name not in book.sheet_names:raise ValueError('Aba ausente na planilha: '+name)
                frame=pd.read_excel(book,sheet_name=name,dtype=str,keep_default_na=False)
                missing=set(columns)-set(frame.columns)
                if missing:raise ValueError('Colunas ausentes em '+name+': '+', '.join(sorted(missing)))
                data[name]=frame.to_dict('records')
            return data
    def validate(self,data):
        for sheet,rows in data.items():
            codes=[row['codigo'] for row in rows]
            if len(codes)!=len(set(codes)): raise ValueError('Código duplicado: '+sheet)
            for row in rows:
                for key in SCHEMA[sheet]:
                    if key not in ['conclusao','observacoes'] and not str(row.get(key,'')).strip(): raise ValueError('Campo obrigatório: '+key)
                if sheet in STATUS and row['status'] not in STATUS[sheet]: raise ValueError('Status inválido.')
                for key in ['admissao','abertura','previsao','conclusao','concessao','vencimento','solicitacao']:
                    if row.get(key):
                        try: date.fromisoformat(row[key])
                        except ValueError: raise ValueError('Data inválida: '+key)
                if sheet=='Funcionarios' and ('@' not in row['email'] or '.' not in row['email'].split('@')[-1]): raise ValueError('E-mail inválido.')
                if sheet=='OrdensServico':
                    if row['prioridade'] not in ['Baixa','Média','Alta','Crítica']: raise ValueError('Prioridade inválida.')
                    if row['previsao']<row['abertura']: raise ValueError('Previsão anterior à abertura.')
                    if (row['status']=='Concluída') != bool(row['conclusao']): raise ValueError('Informe conclusão apenas para OS concluídas.')
                    if row['conclusao'] and not row['abertura']<=row['conclusao']<=date.today().isoformat(): raise ValueError('Conclusão deve estar entre abertura e hoje.')
                if sheet=='Acessos' and row['vencimento']<row['concessao']: raise ValueError('Vencimento anterior à concessão.')
        refs=[('Funcionarios','equipe','Equipes'),('Equipes','responsavel','Funcionarios'),('OrdensServico','funcionario','Funcionarios'),('Acessos','funcionario','Funcionarios'),('Renovacoes','acesso','Acessos'),('Renovacoes','responsavel','Funcionarios')]
        for source,field,target in refs:
            valid={r['codigo'] for r in data[target]}
            if any(r[field] not in valid for r in data[source]): raise ValueError('Referência inválida ou registro relacionado: '+source+' / '+field+'. Remova ou transfira os vínculos antes de excluir.')
    def mutate(self,sheet,record=None,code=None,delete=False):
        with self.lock():
            data=self._read(); rows=data[sheet]
            before={name:[dict(row) for row in records] for name,records in data.items()} if self.observer else None
            if code and not any(r['codigo']==code for r in rows): raise ValueError('Registro não encontrado.')
            if delete: data[sheet]=[r for r in rows if r['codigo']!=code]
            else:
                if code is None:
                    used={r['codigo'] for r in rows}; n=1
                    while f'{PREFIX[sheet]}{n:04}' in used:n+=1
                    code=f'{PREFIX[sheet]}{n:04}'
                clean={k:str(record.get(k,'')).strip() for k in SCHEMA[sheet]}; clean['codigo']=code
                data[sheet]=[clean if r['codigo']==code else r for r in rows]
                if not any(r['codigo']==code for r in rows): data[sheet].append(clean)
            self.validate(data)
            if self.observer:self.observer(before)
            backup=self.path.parent/'backups'; backup.mkdir(exist_ok=True)
            shutil.copy2(self.path,backup/(datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'.xlsx'))
            temp=self.path.with_name(uuid.uuid4().hex+'.tmp.xlsx')
            try:
                with pd.ExcelWriter(temp,engine='openpyxl') as writer:
                    for name,records in data.items():
                        pd.DataFrame(records,columns=SCHEMA[name]).to_excel(writer,sheet_name=name,index=False)
                        ws=writer.book[name]; ws.freeze_panes='A2'; ws.auto_filter.ref=ws.dimensions
                        for cells in ws.iter_rows():
                            for cell in cells:
                                if isinstance(cell.value,str):cell.data_type='s'
                os.replace(temp,self.path)
                if self.observer:
                    try:self.observer(data)
                    except Exception:
                        # Excel commit already succeeded. Do not invite a duplicate
                        # create by reporting the operation as failed. Worker recovers
                        # pending transitions from the last durable snapshot.
                        logging.getLogger(__name__).exception('Falha ao registrar alertas após salvar; worker deve reconciliar.')
            except PermissionError: raise ValueError('Feche a planilha no Excel antes de salvar.')
            finally: temp.unlink(missing_ok=True)
            return code
