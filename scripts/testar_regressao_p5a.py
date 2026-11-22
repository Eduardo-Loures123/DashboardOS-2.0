"""Operational/DOM regressions in a disposable code copy with generated fiction.

Never imports app.py in this process or copies instance/dados. Output artifacts
stay in the OS temporary directory. Pure P1-P4 suites use their own runners.
"""
from pathlib import Path
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]

BOOTSTRAP=r'''
from pathlib import Path
import importlib.util,sys,types,os,runpy,socket
root=Path.cwd();sys.path.insert(0,str(root));sys.dont_write_bytecode=True
import platform;platform.uname()
from urllib.parse import urlsplit
from urllib.request import url2pathname
original=Path(sys.argv[2]).resolve()
def guard(event,args):
    if event in {'socket.connect','socket.connect_ex','socket.getaddrinfo','socket.sendto','smtplib.connect','smtplib.send','subprocess.Popen','os.system'}:
        raise AssertionError('Regression forbids network/processes')
    if event=='sqlite3.connect':
        location=str(args[0])
        if location.startswith('file:'):
            uri=urlsplit(location)
            if uri.netloc:raise AssertionError('Remote database forbidden')
            location=url2pathname(uri.path)
        import tempfile
        if not Path(location).resolve().is_relative_to(Path(tempfile.gettempdir()).resolve()):
            raise AssertionError('Real database forbidden')
    if event=='open' and isinstance(args[0],(str,bytes)):
        p=Path(args[0]).resolve()
        if any(p.is_relative_to(original/name) for name in ('dados','instance','.aws')):
            raise AssertionError('Original data forbidden')
sys.addaudithook(guard)
if sys.argv[1]=='fixtures':
    runpy.run_path(str(root/'scripts/preparar_testes_frontend.py'),run_name='__main__')
else:
    spec=importlib.util.find_spec('unittest')
    if Path(spec.origin).with_name('main.py').stat().st_size==0:
        stub=types.ModuleType('unittest.main');stub.TestProgram=stub.main=lambda *a,**k:None;sys.modules['unittest.main']=stub
    import unittest
    excluded={'test_continuity_anchor','test_email_recipient_policy','test_operational_events','test_notification_recipients','test_email_recipient_persistence','test_demo_notifications'}
    names=[p.stem for p in (root/'tests').glob('test_*.py') if not p.stem.startswith('test_identity_') and p.stem not in excluded]
    suite=unittest.TestSuite(unittest.defaultTestLoader.loadTestsFromName('tests.'+n) for n in sorted(names))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
'''


def protected():
    return {str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
            for name in ('instance','dados') for p in (ROOT/name).rglob('*') if p.is_file()}


def main():
    before=protected()
    directory=Path(tempfile.mkdtemp(prefix='dashboardos-p5a-regression-'))
    copied=directory/'code';copied.mkdir()
    print('Artifacts:',directory,flush=True)
    for name in ('services','scripts','tests','static','templates','deployment'):
        exclusions=('__pycache__','fixtures','*.log','*.json','*.png') if name=='tests' else ('__pycache__','*.log')
        shutil.copytree(ROOT/name,copied/name,ignore=shutil.ignore_patterns(*exclusions))
    for name in ('app.py','VERSION'):
        shutil.copy2(ROOT/name,copied/name)
    env=dict(os.environ,PYTHONDONTWRITEBYTECODE='1',PYTHONIOENCODING='utf-8',DASHBOARD_ENV='development',DASHBOARD_MAIL_ENABLED='false')
    for key in ('DASHBOARD_AUTH_DIRECTORY','DASHBOARD_EXCEL_PATH','SECRET_KEY'):
        env.pop(key,None)
    # Unit tests create their own children under the OS temp root.
    sys.path.insert(0,str(copied))
    from scripts.gerar_dados import gerar
    (copied/'dados').mkdir()
    gerar(copied/'dados/dados_dashboard.xlsx')
    (directory/'bootstrap.py').write_text(BOOTSTRAP,encoding='utf-8')
    outcomes={}
    def run(label,command,environment=env):
        with (directory/(label+'.log')).open('w',encoding='utf-8') as log:
            result=subprocess.run(command,cwd=copied,env=environment,stdout=log,stderr=subprocess.STDOUT)
        outcomes[label]=result.returncode
        print(label,'PASS' if result.returncode==0 else 'FAIL',flush=True)
    try:
        run('operational',[sys.executable,'-B',str(directory/'bootstrap.py'),'tests',str(ROOT)])
        run('fixtures',[sys.executable,'-B',str(directory/'bootstrap.py'),'fixtures',str(ROOT)])
        if outcomes['fixtures']==0:
            node_env=dict(env,NODE_PATH=str(ROOT/'node_modules'))
            run('frontend',['node','--test','--test-isolation=none','tests/frontend.test.cjs'],node_env)
    finally:
        after=protected()
        unchanged=before==after
        (directory/'result.json').write_text(json.dumps(dict(outcomes=outcomes,protected_unchanged=unchanged,
            protected_files=len(after)),indent=2),encoding='utf-8')
        print('Protected unchanged:',unchanged,'files:',len(after),flush=True)
    return 0 if unchanged and outcomes and all(code==0 for code in outcomes.values()) else 1


if __name__=='__main__':raise SystemExit(main())
