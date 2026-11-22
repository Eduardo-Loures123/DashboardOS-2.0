"""One-shot previews and recoverable Excel/SQLite import commits; no event emission."""
from collections import OrderedDict
from datetime import date, datetime
from pathlib import Path
from threading import RLock
import hashlib
import json
import logging
import os
import secrets
import shutil
import time

from .dashboard_service import categoria
from .excel_import_service import compare_upload, read_upload, safe_filename


class ImportConflict(ValueError):
    pass


def fingerprint(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


class ImportCoordinator:
    ttl=600

    def __init__(self,store,auth,enterprise):
        self.store=store;self.auth=auth;self.enterprise=enterprise
        self.pending=OrderedDict();self.mutex=RLock()
        self.journal=store.path.with_name(store.path.name+'.import-journal.json')
        store.recover=self.recover

    def _prune(self):
        for token in list(self.pending):
            if self.pending[token]['expires']<time.time():del self.pending[token]
        while len(self.pending)>=8:self.pending.popitem(last=False)

    def preview(self,content,name,mode,owner):
        if mode not in ('new','upsert'):raise ValueError('Modo de importação inválido.')
        tables,errors=read_upload(content,name)
        with self.mutex:
            self._prune()
            with self.store.lock():
                current=self.store._read();base=fingerprint(self.store.path)
                _,result=compare_upload(self.store,current,tables,mode,errors)
            for token in list(self.pending):
                if self.pending[token]['owner']==owner:del self.pending[token]
            token=secrets.token_urlsafe(32)
            self.pending[token]=dict(owner=owner,tables=tables,errors=errors,name=safe_filename(name),mode=mode,
                                     base=base,result=result,expires=time.time()+self.ttl,done=False)
            return dict(result,token=token,filename=safe_filename(name),mode=mode,expires_in=self.ttl)

    def _get(self,token,owner):
        if not isinstance(token,str):raise ImportConflict('Prévia inválida. Analise o arquivo novamente.')
        entry=self.pending.get(token)
        if not entry or entry['owner']!=owner or entry['expires']<time.time():
            raise ImportConflict('Prévia expirada ou indisponível. Analise o arquivo novamente.')
        return entry

    def cancel(self,token,owner):
        with self.mutex:
            self._get(token,owner);del self.pending[token]

    def _snapshot(self,db,candidate,changes):
        # Suppress only imported transitions. Existing events/outbox are untouched.
        today=date.today()
        by_code={sheet:{row['codigo']:row for row in rows} for sheet,rows in candidate.items()}
        for change in changes:
            sheet=change['sheet'];code=change['code']
            if sheet not in ('OrdensServico','Acessos'):continue
            row=by_code[sheet][code]
            field='previsao' if sheet=='OrdensServico' else 'vencimento'
            active=row['status'] not in ('Concluída','Revogado')
            current=dict(status=row['status'],due=row[field],band=categoria((date.fromisoformat(row[field])-today).days) if active else 'Encerrado')
            old=db.execute('SELECT payload FROM snapshots WHERE sheet=? AND code=?',(sheet,code)).fetchone()
            old=json.loads(old['payload']) if old else {}
            current['version']=old.get('version',0)+int(bool(old) and any(old.get(k)!=current[k] for k in ('status','due','band')))
            db.execute('INSERT INTO snapshots VALUES (?,?,?) ON CONFLICT(sheet,code) DO UPDATE SET payload=excluded.payload',
                       (sheet,code,json.dumps(current)))

    def _write_journal(self,info):
        temp=self.journal.with_suffix('.tmp')
        try:
            with temp.open('w',encoding='utf-8') as stream:
                json.dump(info,stream);stream.flush();os.fsync(stream.fileno())
            os.replace(temp,self.journal)
        finally:temp.unlink(missing_ok=True)

    def recover(self):
        """Called under the same Excel lock by every reader, writer and scanner."""
        if not self.journal.exists():return
        try:
            info=json.loads(self.journal.read_text(encoding='utf-8'))
            backup_name=info['backup']
            if Path(backup_name).name!=backup_name:raise ValueError('Invalid backup')
            backup=self.store.path.parent/'backups'/backup_name
            with self.auth.connect() as db:
                committed=db.execute("SELECT 1 FROM audit WHERE action='import.excel.confirm' AND target=?",(info['receipt'],)).fetchone()
            actual=fingerprint(self.store.path)
            if actual not in (info['before'],info['after']):raise ValueError('Inventory changed')
            if not committed and actual==info['after']:
                if fingerprint(backup)!=info['before']:raise ValueError('Backup mismatch')
                restore=self.store.path.with_name(secrets.token_hex(16)+'.restore.xlsx')
                try:shutil.copy2(backup,restore);os.replace(restore,self.store.path)
                finally:restore.unlink(missing_ok=True)
            if committed and actual!=info['after']:raise ValueError('Commit mismatch')
            self.journal.unlink()
        except Exception:
            raise ImportConflict('Recuperação da importação pendente. Interrompa gravações e consulte o administrador.') from None

    def confirm(self,token,owner,actor):
        with self.mutex:
            entry=self._get(token,owner)
            if entry['done']:return dict(entry['completion'],replayed=True)
            if not entry['result']['can_confirm']:raise ImportConflict('A prévia possui erros ou não contém alterações para confirmar.')
            if not self.enterprise.ready():raise ImportConflict('Armazenamento administrativo indisponível para registrar a importação.')
            with self.store.lock():
                if fingerprint(self.store.path)!=entry['base']:
                    del self.pending[token]
                    raise ImportConflict('Os dados mudaram após a análise. Analise o arquivo novamente antes de confirmar.')
                candidate,result=compare_upload(self.store,self.store._read(),entry['tables'],entry['mode'],entry['errors'])
                if not result['can_confirm']:raise ImportConflict('A validação mudou. Analise o arquivo novamente.')
                backup_dir=self.store.path.parent/'backups';backup_dir.mkdir(exist_ok=True)
                backup=backup_dir/('import_'+datetime.now().strftime('%Y%m%d_%H%M%S_%f')+'_'+secrets.token_hex(4)+'.xlsx')
                staged=self.store.path.with_name(secrets.token_hex(16)+'.import.xlsx')
                receipt=json.dumps(dict(id=token,filename=entry['name'],totals=result['totals']),ensure_ascii=False,sort_keys=True)
                committed=False
                try:
                    self.store._write_workbook(staged,candidate,preserve_extra=True)
                    # Force staged bytes out before recording recovery metadata.
                    with staged.open('rb+') as stream:os.fsync(stream.fileno())
                    shutil.copy2(self.store.path,backup)
                    self._write_journal(dict(backup=backup.name,before=entry['base'],after=fingerprint(staged),receipt=receipt))
                    with self.auth.connect() as db:
                        db.execute('BEGIN IMMEDIATE')
                        try:
                            self._snapshot(db,candidate,result['changes'])
                            self.enterprise.audit(db,actor,'import.excel.confirm',receipt)
                            os.replace(staged,self.store.path)
                            db.commit()
                            committed=True
                        except Exception:
                            db.rollback()
                            raise
                    self.recover()  # Receipt committed: retain inventory, remove journal.
                except Exception as error:
                    logging.getLogger(__name__).warning('Falha na confirmação da importação (%s).',type(error).__name__)
                    # No receipt => restore inventory, leaving notifications and audit rolled back.
                    if not committed:
                        self.recover()
                        raise ImportConflict('A importação não foi concluída. Os dados foram preservados; tente analisar novamente.') from None
                finally:staged.unlink(missing_ok=True)
                completion=dict(message='Importação concluída.',totals=result['totals'],sheets=result['sheets'],filename=entry['name'])
                entry.update(done=True,completion=completion)
                return completion
