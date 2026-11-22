"""Administrator-only, CSRF-protected import endpoints."""
from functools import wraps
import hashlib

from flask import Blueprint, g, jsonify, request, session

from .excel_import_service import MAX_UPLOAD
from .import_coordinator import ImportConflict, ImportCoordinator


def register(app,store,auth):
    coordinator=ImportCoordinator(store,auth,app.config['ENTERPRISE'])
    app.config['IMPORTS']=coordinator
    bp=Blueprint('excel_import',__name__)

    def admin(fn):
        @wraps(fn)
        def wrapped(*args,**kwargs):
            if not g.user or g.user['role'] not in ('admin','superadmin'):
                return jsonify(error='Importação disponível apenas para administradores.'),403
            return fn(*args,**kwargs)
        return wrapped

    def owner():
        return hashlib.sha256((g.user['id']+':'+str(session.get('auth_token',''))).encode()).hexdigest()

    def token():
        payload=request.get_json(silent=True)
        if not isinstance(payload,dict) or set(payload)!={'token'}:raise ValueError('Informe a identificação da prévia.')
        return payload['token']

    @bp.errorhandler(ImportConflict)
    def conflict(error):return jsonify(error=str(error)),409

    @bp.post('/api/import/preview')
    @admin
    def preview():
        if set(request.files)!={'file'} or set(request.form)!={'mode'} or len(request.files.getlist('file'))!=1 or len(request.form.getlist('mode'))!=1:
            raise ValueError('Selecione um único arquivo e o modo de importação.')
        upload=request.files['file'];content=upload.stream.read(MAX_UPLOAD+1)
        result=coordinator.preview(content,upload.filename,request.form['mode'],owner())
        return jsonify(result)

    @bp.post('/api/import/confirm')
    @admin
    def confirm():return jsonify(coordinator.confirm(token(),owner(),g.user['id']))

    @bp.post('/api/import/cancel')
    @admin
    def cancel():
        coordinator.cancel(token(),owner())
        return jsonify(message='Prévia descartada. Nenhum registro foi importado.')

    app.register_blueprint(bp)
