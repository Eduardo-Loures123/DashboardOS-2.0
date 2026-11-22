"""Loopback-only preview on fictional, temporary data. No production imports."""
from pathlib import Path
import os
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))

if __name__=='__main__':
    with tempfile.TemporaryDirectory(prefix='dashboardos-profile-preview-') as temp:
        directory=Path(temp)
        os.environ.update(DASHBOARD_ENV='development',DASHBOARD_AUTH_DIRECTORY=str(directory/'instance'),DASHBOARD_EXCEL_PATH=str(directory/'fictional.xlsx'),DASHBOARD_MAIL_ENABLED='false')
        def guard(event,args):
            if event in ('socket.connect','smtplib.send') or event=='socket.getaddrinfo' and args[0]!='127.0.0.1': raise RuntimeError('Outbound network forbidden in isolated preview')
            if event=='sqlite3.connect' and not Path(str(args[0])).resolve().is_relative_to(directory): raise RuntimeError('Database outside preview forbidden')
        sys.addaudithook(guard)
        from scripts.gerar_dados import gerar
        gerar(directory/'fictional.xlsx')
        from app import create_app
        from flask import session,redirect
        app=create_app(directory/'fictional.xlsx',directory/'instance');auth=app.config['AUTH'];auth.create_admin('visual.test','fictional-preview-password')
        app.config['ENTERPRISE'].update_profile('visual.test',{'display_name':'Conta de demonstração'})
        for op,mod,code in [('create','OrdensServico','OS0001'),('update','Acessos','AC0002'),('delete','Equipes','EQTEST')]:
            app.config['PROFILES'].record_activity('visual.test',op,mod,code)
        @app.get('/_preview/session')
        def preview_session():
            import secrets
            session.clear();session['auth_token']=auth.start('visual.test');session['csrf']=secrets.token_hex(24)
            return redirect('/perfil')
        app.run(host='127.0.0.1',port=5099,debug=False,use_reloader=False)
