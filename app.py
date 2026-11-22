from pathlib import Path
from io import BytesIO
import os, secrets
from datetime import date, timedelta
import click
import pandas as pd
from flask import Flask, render_template, request, jsonify, send_file, session, redirect, url_for, g
from services.excel_service import ExcelService
from services.schema import SCHEMA, LABELS, STATUS
from services.dashboard_service import enrich, filtered, summary, overview
from services.auth_service import AuthService
from services.production import configure

ROOT=Path(__file__).resolve().parent
APP_VERSION=(ROOT/'VERSION').read_text(encoding='utf-8').strip()
PAGES={'dashboard':('Visão Geral',None),'funcionarios':('Funcionários','Funcionarios'),'equipes':('Equipes','Equipes'),'ordens-servico':('Ordens de Serviço','OrdensServico'),'acessos':('Acessos','Acessos'),'vencimentos':('Vencimentos','Acessos'),'renovacoes':('Renovações','Renovacoes'),'relatorios':('Relatórios',None)}
DATES={'Funcionarios':'admissao','OrdensServico':'abertura','Acessos':'vencimento','Renovacoes':'solicitacao'}
FILTERS={'dashboard':['equipe','status','prioridade','inicio','fim'],'funcionarios':['equipe','cargo','status'],'equipes':['responsavel'],'ordens-servico':['equipe','funcionario','status','prioridade','inicio','fim'],'acessos':['equipe','funcionario','sistema','situacao'],'vencimentos':['equipe','sistema','situacao'],'renovacoes':['status','responsavel','inicio','fim'],'relatorios':['equipe','inicio','fim']}

def create_app(path=None,auth_directory=None):
    app=Flask(__name__)
    app.config['APP_VERSION']=APP_VERSION
    @app.context_processor
    def version_context():
        return {'app_version': app.config['APP_VERSION']}
    production=configure(app, ROOT, path, auth_directory)
    auth=AuthService(app.config['AUTH_DIRECTORY'])
    app.secret_key=app.config.get('SECRET_KEY') or auth.secret();app.config['AUTH']=auth
    app.config.update(MAX_CONTENT_LENGTH=256*1024,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',SESSION_COOKIE_SECURE=production,PERMANENT_SESSION_LIFETIME=timedelta(hours=8))
    store=ExcelService(app.config['EXCEL_PATH']); app.config['STORE']=store
    @app.before_request
    def protect():
        if request.path=='/api/import/preview':
            from services.excel_import_service import MAX_UPLOAD
            request.max_content_length=MAX_UPLOAD+65536
            request.max_form_parts=4
        if request.host.split(':')[0] not in app.config['ALLOWED_HOSTS']:return jsonify(error='Host não permitido.'),403
        if 'csrf' not in session:session['csrf']=secrets.token_hex(24)
        g.user=auth.current(session.get('auth_token'))
        if request.method in ['POST','PUT','DELETE','PATCH']:
            token=request.headers.get('X-CSRF-Token') or request.form.get('csrf_token','')
            if not secrets.compare_digest(token,session['csrf']):return jsonify(error='Sessão inválida. Atualize a página.'),403
        if request.endpoint in ['static','login','guest','logout']:return
        if request.path.startswith('/api/records/') and (not g.user or g.user['role'] not in ('admin','superadmin')):
            return jsonify(error='Disponível apenas para administradores.'),403
        if not g.user:
            if request.path.startswith('/api/'):return jsonify(error='Faça login ou entre no modo visitante.',login_url='/login'),401
            if request.endpoint=='page_view':return redirect(url_for('login'))
    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='same-origin'
        if request.endpoint!='static':response.headers['Cache-Control']='no-store'
        if production:response.headers['Strict-Transport-Security']='max-age=31536000'
        return response
    @app.errorhandler(500)
    def internal(error):return jsonify(error='Erro interno. Consulte os logs do serviço.'),500
    @app.errorhandler(413)
    def oversized(error):return jsonify(error='A requisição excede o tamanho permitido. Arquivos Excel devem ter até 5 MB.' if request.path.startswith('/api/import/') else 'A requisição excede o tamanho permitido. Fotos devem ter até 5 MB.'),413
    def begin_session(user_id=None):
        auth.revoke(session.get('auth_token'));session.clear()
        session['auth_token']=auth.start(user_id);session['csrf']=secrets.token_hex(24);session.permanent=True
    @app.route('/login',methods=['GET','POST'])
    def login():
        error=None;status=200
        if request.method=='POST':
            payload=request.get_json(silent=True) or request.form
            if not hasattr(payload,'get'):return jsonify(error='Dados inválidos.'),400
            user_id=payload.get('user_id','');password=payload.get('password','')
            if not isinstance(user_id,str) or not isinstance(password,str) or len(user_id)>64 or len(password)>256:
                error='ID ou senha inválidos.';status=401
            else:
                user_id,status=auth.authenticate(user_id,password,request.remote_addr or 'local')
                if user_id:
                    begin_session(user_id)
                    return jsonify(redirect='/dashboard') if request.is_json else redirect('/dashboard')
                error='Muitas tentativas. Aguarde dez minutos.' if status==429 else 'ID ou senha inválidos.'
            if request.is_json:return jsonify(error=error),status
        return render_template('login.html',csrf=session['csrf'],error=error,has_admin=auth.has_admin(),user=None),status
    @app.post('/auth/guest')
    def guest():
        begin_session()
        return jsonify(redirect='/dashboard') if request.is_json else redirect('/dashboard')
    @app.post('/auth/logout')
    def logout():
        auth.revoke(session.get('auth_token'));session.clear()
        return jsonify(redirect='/login') if request.is_json else redirect('/login')
    @app.cli.command('criar-admin')
    @click.option('--id','user_id',prompt='ID do administrador')
    @click.option('--senha',prompt='Senha (mínimo 12 caracteres)',hide_input=True,confirmation_prompt=True)
    def criar_admin(user_id,senha):
        try:created=auth.create_admin(user_id,senha)
        except ValueError as error:raise click.ClickException(str(error))
        click.echo('Administrador criado: '+created)
    @app.errorhandler(ValueError)
    def invalid(error):return jsonify(error=str(error)),400
    @app.errorhandler(PermissionError)
    def permission(error):return jsonify(error='Não foi possível acessar a planilha. Feche o Excel e tente novamente.'),409
    @app.errorhandler(FileNotFoundError)
    def missing(error):return jsonify(error='Planilha indisponível. Contate o administrador.' if production else 'Planilha ausente. Execute python scripts/gerar_dados.py.'),503
    @app.get('/')
    @app.get('/<page>')
    def page_view(page='dashboard'):
        if page not in PAGES:return 'Página não encontrada',404
        return render_template(page.replace('-','_')+'.html',page=page,title=PAGES[page][0],pages=PAGES,csrf=session['csrf'],user=g.user)
    def view_sheet(page):
        if page=='vencimentos':
            kind=request.args.get('tipo','acessos')
            if kind not in ('acessos','os'):raise ValueError('Tipo de vencimento inválido.')
            return 'OrdensServico' if kind=='os' else 'Acessos'
        return PAGES[page][1]
    def view_filters(page):
        return ['equipe','funcionario','status','prioridade','situacao','inicio','fim'] if page=='vencimentos' and view_sheet(page)=='OrdensServico' else FILTERS[page]
    def get_data(page):
        if page not in PAGES:raise ValueError('Página inválida.')
        raw=store.read(); data=enrich(raw)
        filters={k:v for k,v in request.args.items() if k in view_filters(page)+['q'] and v}
        for key in ['inicio','fim']:
            if filters.get(key):
                try:date.fromisoformat(filters[key])
                except ValueError:raise ValueError('Data de filtro inválida.')
        if filters.get('inicio') and filters.get('fim') and filters['inicio']>filters['fim']:raise ValueError('A data final deve ser igual ou posterior à data inicial.')
        lookups={table:{row['codigo']:row for row in records} for table,records in raw.items()}
        if page in ['dashboard','relatorios']:
            team=filters.get('equipe')
            for sheet in data:
                relevant={k:v for k,v in filters.items() if k in ['equipe','q'] or sheet=='OrdensServico' or (page=='relatorios' and k in ['inicio','fim'])}
                if sheet=='Equipes' and team: data[sheet]=[r for r in data[sheet] if r['codigo']==team]
                else:data[sheet]=filtered(data[sheet],relevant,DATES.get(sheet),lookups)
            return raw,data,[]
        sheet=view_sheet(page)
        source=data[sheet]
        if page=='vencimentos' and sheet=='OrdensServico':
            from services.deadline_service import order_deadlines
            source=order_deadlines(source)
        return raw,data,filtered(source,filters,'previsao' if page=='vencimentos' and sheet=='OrdensServico' else DATES.get(sheet),lookups)
    def reports(data):
        count=lambda rows,key:[{'grupo':k,'quantidade':v} for k,v in pd.Series([r[key] for r in rows],dtype='str').value_counts().items()]
        return {'OS por equipe':count(data['OrdensServico'],'equipe'),'OS por status':count(data['OrdensServico'],'status'),'OS por período':count([dict(r,mes=r['abertura'][:7]) for r in data['OrdensServico']],'mes'),'Acessos por situação':count(data['Acessos'],'situacao'),'Vencimentos futuros':[r for r in data['Acessos'] if isinstance(r.get('dias'),int) and r['dias']>=0 and r['status']=='Ativo'],'Renovações pendentes':[r for r in data['Renovacoes'] if r['status'] not in ['Concluída','Rejeitada']],'Funcionários por equipe':count(data['Funcionarios'],'equipe')}
    @app.get('/api/data/<page>')
    def api_data(page):
        raw,data,rows=get_data(page); sheet=view_sheet(page)
        indicators,charts=summary(data)
        options={}
        base=enrich(raw)
        if page=='vencimentos' and sheet=='OrdensServico':
            from services.deadline_service import order_deadlines
            base[sheet]=order_deadlines(base[sheet])
        for key in view_filters(page):
            if key in ['inicio','fim']:continue
            options[key]=sorted({str(r[key]) for r in base[sheet or 'OrdensServico'] if key in r})
        lookups={k:[{'value':r['codigo'],'label':r.get('nome',r.get('descricao',r.get('sistema',r['codigo'])))+' · '+r['codigo']} for r in raw[k]] for k in ['Funcionarios','Equipes','Acessos']}
        columns=list(SCHEMA.get(sheet,[]))
        if sheet in ['OrdensServico','Acessos','Renovacoes']:columns+=['equipe','nome_funcionario'] if 'equipe' not in columns else ['nome_funcionario']
        if page in ['acessos','vencimentos']:columns+=['dias','situacao']
        if page=='equipes':columns+=['quantidade_funcionarios','quantidade_os','quantidade_acessos']
        from collections import Counter
        calendar=dict(Counter(r['previsao'] for r in data['OrdensServico'] if r['status']!='Concluída'))
        from services.agenda_service import agenda
        return jsonify(rows=rows,columns=columns,fields=SCHEMA.get(sheet,[]),labels=dict(LABELS,nome_funcionario='Nome do funcionário'),statuses=STATUS.get(sheet,[]),filters=options,filterFields=view_filters(page),lookups=lookups,indicators=indicators,charts=charts,calendar=calendar,overview=overview(data) if page=='dashboard' else {},agenda=agenda(data) if page=='dashboard' else {},version=app.config['APP_VERSION'],reports=reports(data) if page=='relatorios' else {},sheet=sheet,user={'role':g.user['role'],'id':g.user['id']})
    @app.route('/api/records/<sheet>',methods=['POST'])
    @app.route('/api/records/<sheet>/<code>',methods=['PUT','DELETE'])
    def records(sheet,code=None):
        if sheet not in SCHEMA:raise ValueError('Tabela inválida.')
        payload=request.get_json(silent=True)
        if request.method!='DELETE' and not isinstance(payload,dict):raise ValueError('Dados inválidos.')
        result=store.mutate(sheet,payload,code,request.method=='DELETE')
        try:
            app.config['PROFILES'].record_activity(g.user['id'],{'POST':'create','PUT':'update','DELETE':'delete'}[request.method],sheet,result)
        except Exception:
            # The Excel commit succeeded: never invite a duplicate operation.
            app.logger.error('Falha ao registrar atividade concluída; revisar armazenamento local.')
        return jsonify(codigo=result,message='Registro excluído.' if request.method=='DELETE' else 'Registro salvo com sucesso.')
    @app.get('/api/export/<page>')
    def export(page):
        _,data,rows=get_data(page); tables=reports(data) if page=='relatorios' else ({view_sheet(page):rows} if view_sheet(page) else data)
        output=BytesIO()
        with pd.ExcelWriter(output,engine='openpyxl') as writer:
            for name,records in tables.items():
                frame=pd.DataFrame(records)
                # Neutralize spreadsheet formulas in user-entered text.
                frame=frame.map(lambda v:"'"+v if isinstance(v,str) and v.startswith(('=','+','-','@')) else v)
                frame.to_excel(writer,sheet_name=name[:31],index=False)
        output.seek(0)
        return send_file(output,as_attachment=True,download_name=page+'.xlsx',mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    from services.enterprise_routes import register
    register(app,auth,store,PAGES)
    from services.import_routes import register as register_import
    register_import(app,store,auth)
    return app

app=create_app()
if __name__=='__main__':
    if app.config['PRODUCTION']:raise RuntimeError('Use Gunicorn em produção.')
    if not app.config['EXCEL_PATH'].exists():
        raise RuntimeError('Planilha ausente. Configure DASHBOARD_EXCEL_PATH com seus dados existentes.')
    app.run(host='127.0.0.1',port=int(os.environ.get('PORT','5000')),debug=False)
