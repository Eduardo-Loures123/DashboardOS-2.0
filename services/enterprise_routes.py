from functools import wraps
import click
from flask import Blueprint, g, request, jsonify, render_template, session, redirect
from .enterprise_service import EnterpriseService
from .mail_service import process_outbox


def register(app, auth, store, pages):
    service = EnterpriseService(auth)
    app.config['ENTERPRISE'] = service
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

    @bp.get('/perfil')
    @allowed()
    def profile_page():
        return render_template('account.html', page='perfil', title='Meu perfil', pages=pages, csrf=session['csrf'], user=g.user)

    @bp.get('/administracao')
    @allowed(True)
    def admin_page():
        return render_template('account.html', page='administracao', title='Administração', pages=pages, csrf=session['csrf'], user=g.user)

    @bp.route('/api/profile', methods=['GET', 'PUT'])
    @allowed()
    def profile():
        if request.method == 'GET':
            return jsonify(service.profile(g.user['id']))
        uid, sensitive = service.update_profile(g.user['id'], payload())
        if sensitive:
            auth.revoke(session.get('auth_token'))
            session.clear()
            return jsonify(message='Perfil atualizado. Entre novamente para continuar.', redirect='/login')
        return jsonify(message='Perfil atualizado.')

    @bp.post('/api/profile/verification')
    @allowed()
    def verify_request():
        service.token(g.user['id'], g.user['id'], 'verify')
        return jsonify(message='Confirmação enfileirada. O envio depende da configuração e ativação do provedor de e-mail.')

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
        service.require_ready()
        # Hold Excel lock through snapshot transaction to serialize scans with writes.
        with store.lock():
            count = service.scan(store._read())
        sent = process_outbox(auth)
        click.echo(f'Eventos: {count}; e-mails enviados: {sent}.')

    app.register_blueprint(bp)
