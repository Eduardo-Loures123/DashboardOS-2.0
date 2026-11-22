from functools import wraps
import click
from flask import Blueprint, g, request, jsonify, render_template, session, redirect, send_file
from .enterprise_service import EnterpriseService
from .mail_service import process_outbox


def register(app, auth, store, pages):
    service = EnterpriseService(auth)
    app.config['ENTERPRISE'] = service
    from .profile_service import ProfileService
    profiles=ProfileService(auth,service)
    app.config['PROFILES']=profiles
    store.observer = lambda raw: service.scan(raw) if service.ready() else None
    bp = Blueprint('enterprise', __name__)

    @app.context_processor
    def account_preferences():
        appearance = {}
        if g.user and g.user['role'] != 'guest' and service.ready():
            appearance = service.profile(g.user['id'])['appearance']
        return {'account_appearance': appearance}

    def allowed(super_only=False):
        def decorate(fn):
            @wraps(fn)
            def wrapped(*args, **kwargs):
                if not g.user or g.user['role'] == 'guest':
                    return jsonify(error='Entre com uma conta cadastrada.'), 403
                if super_only and g.user['role'] != 'superadmin':
                    return jsonify(error='Disponível apenas para superadministradores.'), 403
                if not service.ready():
                    return jsonify(error='Migração empresarial pendente. Consulte o procedimento de atualização.'), 503
                return fn(*args, **kwargs)
            return wrapped
        return decorate

    def payload():
        value = request.get_json(silent=True)
        if not isinstance(value, dict):
            raise ValueError('Dados inválidos.')
        return value

    @bp.get('/ajuda')
    def help_page():
        return render_template('help.html',page='ajuda',title='Ajuda e suporte',pages=pages,csrf=session['csrf'],user=g.user)

    @bp.get('/perfil')
    @allowed()
    def profile_page():
        return render_template('account.html', page='perfil', title='Meu perfil', pages=pages, csrf=session['csrf'], user=g.user)

    @bp.get('/configuracoes')
    @bp.get('/settings')
    @allowed()
    def preferences_redirect():
        return redirect('/perfil?tab=preferences')

    @bp.get('/administracao')
    @allowed(True)
    def admin_page():
        return render_template('account.html', page='administracao', title='Administração', pages=pages, csrf=session['csrf'], user=g.user)

    @bp.route('/api/profile', methods=['GET', 'PUT'])
    @allowed()
    def profile():
        if request.method == 'GET':
            return jsonify(profiles.profile(g.user['id']))
        sensitive = profiles.update(g.user['id'], payload())
        if sensitive:
            auth.revoke(session.get('auth_token'))
            session.clear()
            return jsonify(message='Perfil atualizado. Entre novamente para continuar.', redirect='/login')
        return jsonify(message='Perfil atualizado.',profile=profiles.profile(g.user['id']))

    @bp.get('/api/profile/login-availability')
    @allowed()
    def login_availability():
        return jsonify(available=profiles.login_available(g.user['id'],request.args.get('login','')))

    @bp.route('/api/profile/avatar',methods=['GET','POST','DELETE'])
    @allowed()
    def avatar():
        if request.method=='GET':
            path=profiles.avatar_path(g.user['id'])
            if path is None or not path.is_file(): return jsonify(error='Foto não cadastrada.'),404
            return send_file(path,mimetype='image/webp',max_age=0)
        if request.method=='POST':
            request.max_content_length=6*1024*1024
            try:profiles.set_avatar(g.user['id'],request.files.get('photo'))
            except OSError:return jsonify(error='Não foi possível armazenar a foto. Verifique as permissões e o espaço local.'),503
        else:
            try:profiles.remove_avatar(g.user['id'])
            except OSError:return jsonify(error='Não foi possível remover a foto. Verifique o armazenamento local.'),503
        return jsonify(message='Foto atualizada.',profile=profiles.profile(g.user['id']))

    @bp.route('/api/profile/email-change',methods=['POST','DELETE'])
    @allowed()
    def email_change():
        if request.method=='DELETE': profiles.cancel_email(g.user['id'])
        else:
            data=payload()
            profiles.change_email(g.user['id'],data.get('email'),data.get('current_password',''))
        return jsonify(message='Solicitação preparada. A entrega do código ainda não está habilitada.' if request.method=='POST' else 'Solicitação cancelada.',delivery_available=False,profile=profiles.profile(g.user['id']))

    @bp.post('/api/profile/email-change/confirm')
    @allowed()
    def email_change_confirm():
        profiles.confirm_email(g.user['id'],payload().get('token'))
        return jsonify(message='Endereço confirmado.',profile=profiles.profile(g.user['id']))

    @bp.get('/api/profile/activities')
    @allowed()
    def activities():
        return jsonify(profiles.activities(g.user['id'],request.args.get('operation',''),request.args.get('q',''),request.args.get('page',1)))

    @app.cli.command('migrar-perfil')
    @click.confirmation_option(prompt='Criar backup e aplicar atualização aditiva do perfil no banco configurado?')
    def migrate_profile():
        click.echo('Perfil atualizado. Backup: '+str(profiles.migrate()))

    @app.cli.command('limpar-atividades')
    def cleanup_activities():
        click.echo('Atividades expiradas removidas: '+str(profiles.cleanup_activities()))

    @bp.route('/api/profile/verification', methods=['GET', 'POST'])
    @allowed()
    def verify_request():
        if request.method == 'GET':
            return jsonify(service.verification_status(g.user['id']))
        service.token(g.user['id'], g.user['id'], 'verify')
        return jsonify(message='Solicitação registrada. A mensagem está na fila e ainda não foi enviada.', **service.verification_status(g.user['id']))

    @bp.post('/api/profile/verify')
    @allowed()
    def verify():
        service.consume(payload().get('token'), 'verify', uid=g.user['id'])
        return jsonify(message='E-mail confirmado.')

    @bp.route('/api/admin/users', methods=['GET', 'POST'])
    @allowed(True)
    def users():
        if request.method == 'GET':
            return jsonify(users=service.users())
        uid = service.create_user(g.user['id'], payload())
        return jsonify(user_id=uid, message='Conta criada.'), 201

    @bp.put('/api/admin/users/<uid>')
    @allowed(True)
    def manage(uid):
        service.manage(g.user['id'], uid, payload())
        return jsonify(message='Conta atualizada; sessões anteriores revogadas.')

    @bp.post('/api/admin/users/<uid>/reset')
    @allowed(True)
    def reset(uid):
        data = payload()
        # Reauthentication for issuing a credential reset.
        password = data.get('current_password', '')
        if not isinstance(password, str) or len(password) > 256:
            raise ValueError('Senha inválida.')
        valid, _ = auth.authenticate(g.user['id'], password, request.remote_addr or 'local')
        if not valid:
            return jsonify(error='Confirme sua senha atual.'), 403
        token = service.token(g.user['id'], uid, 'reset')
        return jsonify(token=token, message='Código de uso único, válido por 30 minutos. Entregue ao titular por um canal seguro.')

    @bp.get('/redefinir-senha')
    def reset_page():
        return render_template('reset.html', csrf=session['csrf'])

    @bp.post('/api/auth/reset')
    def reset_consume():
        data = payload()
        service.require_ready()
        service.consume(data.get('token'), 'reset', password=data.get('password'))
        return jsonify(message='Senha redefinida. Entre com sua nova senha.')

    @bp.route('/api/notifications', methods=['GET', 'POST'])
    @allowed()
    def notifications():
        if request.method == 'GET':
            rows = service.notifications(g.user['id'])
            with auth.connect() as db:
                unread = db.execute('SELECT COUNT(*) FROM notifications WHERE user_id=? AND deleted=0 AND read_at IS NULL', (g.user['id'],)).fetchone()[0]
            return jsonify(notifications=rows, unread=unread)
        service.notification_action(g.user['id'], payload().get('action'))
        return jsonify(message='Central atualizada.')

    @bp.post('/api/notifications/<int:nid>')
    @allowed()
    def notification(nid):
        service.notification_action(g.user['id'], payload().get('action'), nid)
        return jsonify(message='Notificação atualizada.')

    @bp.route('/api/admin/announcements', methods=['GET', 'POST'])
    @allowed(True)
    def announcements():
        if request.method == 'GET':
            return jsonify(announcements=service.history('announcements'))
        data = payload()
        if data.get('confirmed') is not True:
            raise ValueError('Confirme a publicação após revisar a prévia.')
        service.announce(g.user['id'], data)
        return jsonify(message='Comunicado publicado.'), 201

    @bp.get('/api/admin/audit')
    @allowed(True)
    def audit():
        return jsonify(audit=service.history('audit'))

    @app.cli.command('migrar-contas')
    @click.confirmation_option(prompt='Criar backup e aplicar migração aditiva no banco configurado?')
    def migrate():
        backup = service.migrate()
        click.echo('Migração concluída. Backup: ' + str(backup))

    @app.cli.command('promover-superadmin')
    @click.option('--id', 'uid', prompt='ID do administrador existente')
    @click.password_option(prompt='Senha atual', confirmation_prompt=False)
    def promote(uid, password):
        try:
            service.promote_initial(uid.strip().casefold(), password)
        except ValueError as error:
            raise click.ClickException(str(error))
        click.echo('Conta existente associada a superadministrador.')

    @app.cli.command('processar-alertas')
    def process():
        from .mail_service import email_suspended
        if email_suspended():
            raise click.ClickException("Processador legado suspenso nesta release.")
        service.require_ready()
        # Hold Excel lock through snapshot transaction to serialize scans with writes.
        with store.lock():
            count = service.scan(store._read())
        sent = process_outbox(auth)
        click.echo(f'Eventos: {count}; e-mails enviados: {sent}.')

    @app.cli.command('processar-emails')
    def emails():
        """Processa somente a fila de e-mails, sem observar ou modificar o Excel."""
        from .mail_service import mail_configuration
        service.require_ready()
        config = mail_configuration()
        if not config['enabled']:
            raise click.ClickException('Envio desativado. Configure o provedor e autorize a ativação.')
        if config['missing']:
            raise click.ClickException('Configuração ausente: ' + ', '.join(config['missing']))
        click.echo(f'Mensagens aceitas pelo provedor: {process_outbox(auth)}.')

    app.register_blueprint(bp)
