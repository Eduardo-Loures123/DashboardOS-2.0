"""Local visual QA using synthetic records only; never opens the main stores."""
from pathlib import Path
from datetime import date,timedelta
import os
import secrets
import sys
import types

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
preview=ROOT/'diagnosticos'/'data-tools-preview'
preview.mkdir(parents=True,exist_ok=True)
directory=preview/('instance-'+secrets.token_hex(6));directory.mkdir()
os.environ['DASHBOARD_AUTH_DIRECTORY']=str(directory)
os.environ['DASHBOARD_EXCEL_PATH']=str(directory/'synthetic.xlsx')
os.environ['DASHBOARD_ENV']='development'
os.environ['DASHBOARD_MAIL_ENABLED']='false'
# The installed Python's unittest CLI is empty; reuse the existing test fixtures.
stub=types.ModuleType('unittest.main');stub.TestProgram=stub.main=lambda *a,**kw:None
sys.modules['unittest.main']=stub
from tests.test_excel_import import inventory,workbook_bytes
from app import app

raw=inventory();today=date.today()
raw['OrdensServico']=[]
for index,remaining in enumerate([-5,0,10,30,31,45,60,90,120,-10],1):
    raw['OrdensServico'].append(dict(inventory()['OrdensServico'][0],codigo=f'OS{index:04}',descricao=f'Ordem fictícia {index}',previsao=(today+timedelta(days=remaining)).isoformat(),
                                    status='Concluída' if index==10 else 'Em andamento' if index%2==0 else 'Pendente',conclusao=today.isoformat() if index==10 else ''))
raw['Acessos']=[dict(raw['Acessos'][0],codigo=f'AC{index:04}',sistema=f'Recurso fictício {index}',vencimento=(today+timedelta(days=remaining)).isoformat()) for index,remaining in enumerate([-5,0,10,31,60],1)]
store=app.config['STORE'];store._write_workbook(store.path,raw)
password=secrets.token_urlsafe(24)
app.config['AUTH'].create_admin('visual-import',password)
(preview/'login.key').write_text(password,encoding='ascii')
source={'Acessos':[dict(raw['Acessos'][2],sistema='Recurso revisado'),dict(raw['Acessos'][-1],codigo='AC0006',sistema='Novo recurso fictício')]}
(preview/'import-valid.xlsx').write_bytes(workbook_bytes(source))
(preview/'import-invalid.xlsx').write_bytes(workbook_bytes({'Acessos':[dict(raw['Acessos'][0],funcionario='FUNC9999')]}))
print('Synthetic preview: http://127.0.0.1:5002/login',flush=True)
app.run(host='127.0.0.1',port=5002,debug=False)
