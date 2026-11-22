"""Standalone authenticated demonstration UI. Never registered in operational app."""
from datetime import datetime, timedelta
from pathlib import Path
import secrets
import time

from flask import Flask, jsonify, render_template, request, session, redirect
from .demo_notifications import DemoNotifications, PASSWORD, USERS, TZ


def create_demo_app(directory):
    root=Path(__file__).resolve().parents[1]
    demo=DemoNotifications(directory)
    with demo.locked() as db:
        secret=demo.meta(db,'secret')
    app=Flask('dashboardos_p5a',template_folder=str(root/'templates'),static_folder=str(root/'static'))
    app.config.update(SECRET_KEY=secret,SESSION_COOKIE_NAME='dashboardos_p5a',
        SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',MAX_CONTENT_LENGTH=8192,
        PERMANENT_SESSION_LIFETIME=timedelta(hours=4),DEMO=demo)
    failures={}

    @app.before_request
    def protect():
        if request.host.split(':')[0] not in ('127.0.0.1','localhost'):
            return jsonify(error='Host não permitido.'),403
        if 'csrf' not in session:
            session['csrf']=secrets.token_hex(24)
        if request.method=='POST':
            token=request.headers.get('X-CSRF-Token') or request.form.get('csrf','')
            if not secrets.compare_digest(str(token),session['csrf']):
                return jsonify(error='Sessão inválida. Recarregue a demonstração.'),403
        if request.path.startswith('/demo/api/') and not session.get('uid'):
            return jsonify(error='Entre com uma conta fictícia.'),401

    @app.after_request
    def headers(response):
        response.headers.update({'Cache-Control':'no-store','X-Content-Type-Options':'nosniff',
            'X-Frame-Options':'DENY','Referrer-Policy':'same-origin',
            'Content-Security-Policy':"default-src 'self'; style-src 'self'; script-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; form-action 'self'"})
        return response

    @app.errorhandler(ValueError)
    def invalid(error):return jsonify(error=str(error)),409

    @app.errorhandler(PermissionError)
    def forbidden(error):return jsonify(error=str(error)),403

    @app.errorhandler(500)
    def internal(error):return jsonify(error='Operação interrompida. Use Retomar para conferir as provas; não apague arquivos.'),500

    @app.get('/')
    def index():
        return render_template('demo_notifications.html',uid=session.get('uid'),csrf=session['csrf'],
            users=USERS,password=PASSWORD,version=(root/'VERSION').read_text(encoding='utf-8').strip())

    @app.post('/demo/login')
    def login():
        uid=request.form.get('uid','');key=request.remote_addr or 'local';now=time.time()
        failures[key]=[t for t in failures.get(key,[]) if now-t<60]
        if len(failures[key])>=10:return jsonify(error='Aguarde um minuto antes de tentar novamente.'),429
        if uid not in USERS or not demo.authenticate(uid,request.form.get('password','')):
            failures[key].append(now);return jsonify(error='Credenciais fictícias inválidas.'),401
        failures.pop(key,None);session.clear();session['uid']=uid;session['csrf']=secrets.token_hex(24)
        session.permanent=True
        return redirect('/')

    @app.post('/demo/logout')
    def logout():session.clear();return redirect('/')

    def payload():
        data=request.get_json(silent=True)
        if not isinstance(data,dict):raise ValueError('Requisição inválida.')
        return data

    @app.get('/demo/api/state')
    def state():return jsonify(demo.view(session['uid']))

    @app.post('/demo/api/order')
    def order():
        data=payload()
        if set(data)!={'operation_id','status'}:raise ValueError('Campos inesperados.')
        return jsonify(demo.change_order(session['uid'],data['operation_id'],data['status']))

    @app.post('/demo/api/recover')
    def recover():demo.recover(session['uid']);return jsonify(message='Provas verificadas; projeções retomadas sem duplicação.')

    @app.post('/demo/api/clock')
    def clock():
        data=payload();command=data.get('command')
        # Read clock as admin without depending on pending view projections.
        with demo.locked() as db:
            demo.admin(db,session['uid']);now=demo.clock(db)
        if command=='09':
            target=now.replace(hour=9,minute=0,second=0,microsecond=0)
        elif command=='recovery':target=now.replace(hour=11,minute=30,second=0,microsecond=0)
        elif command=='day':target=(now+timedelta(days=1)).replace(hour=8,minute=55,second=0,microsecond=0)
        elif command=='custom':
            target=datetime.fromisoformat(str(data.get('time','')))
        else:raise ValueError('Comando de relógio inválido.')
        count=demo.advance(session['uid'],target)
        return jsonify(message=f'Relógio avançado. {count} novo(s) evento(s).')

    @app.post('/demo/api/compose')
    def compose():return jsonify(message=f'{demo.compose(session["uid"])} resumo(s) preparado(s).')

    @app.post('/demo/api/deliver')
    def deliver():return jsonify(message=f'{demo.deliver(session["uid"])} entrega(s) simulada(s). Nenhum e-mail enviado.')

    @app.post('/demo/api/restrict')
    def restrict():
        data=payload();demo.restriction(session['uid'],data.get('uid'),data.get('action'))
        return jsonify(message='Restrição aplicada. Próximas leituras e entregas revalidam o acesso.')

    return app
