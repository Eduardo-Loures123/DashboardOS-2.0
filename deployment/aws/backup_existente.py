"""Backup offline, sem importar app ou iniciar recuperação; escritores parados."""
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sqlite3
import sys


def backup(destination, code, config):
    sources = {
        'excel': Path(os.environ['DASHBOARD_EXCEL_PATH']).resolve(strict=True).parent,
        'auth': Path(os.environ['DASHBOARD_AUTH_DIRECTORY']).resolve(strict=True),
        'code': Path(code).resolve(strict=True),
        'config': Path(config).resolve(strict=True),
    }
    target = Path(destination).resolve() / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S_%fZ')
    if any(target.is_relative_to(p if p.is_dir() else p.parent) for p in sources.values()):
        raise RuntimeError('Backup deve ficar fora das origens.')
    target.mkdir(parents=True, mode=0o700)
    manifest = {}
    for label, source in sources.items():
        files = list(source.rglob('*')) if source.is_dir() else [source]
        for path in files:
            relative = path.relative_to(source) if source.is_dir() else Path(source.name)
            if label == 'code' and set(relative.parts) & {'.venv', '.git', '__pycache__', 'node_modules'}:
                continue
            if path.is_symlink():
                raise RuntimeError('Link na origem: revisar backup manualmente.')
            if not path.is_file():
                continue
            copied = target / label / relative
            copied.parent.mkdir(parents=True, exist_ok=True)
            before = hashlib.sha256(path.read_bytes()).hexdigest()
            shutil.copy2(path, copied)
            if before != hashlib.sha256(copied.read_bytes()).hexdigest() or before != hashlib.sha256(path.read_bytes()).hexdigest():
                raise RuntimeError('Origem mudou ou copia divergiu; backup incompleto.')
            manifest[str(copied.relative_to(target))] = before
    with closing(sqlite3.connect((target/'auth/auth.sqlite3').as_uri()+'?mode=ro', uri=True)) as db:
        if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise RuntimeError('Backup SQLite invalido.')
    # SQLite pode atualizar SHM apenas na copia; manifeste os bytes finais.
    manifest = {str(p.relative_to(target)): hashlib.sha256(p.read_bytes()).hexdigest() for p in target.rglob('*') if p.is_file()}
    (target/'manifest.json').write_text(json.dumps({'sources': {k: str(v) for k, v in sources.items()}, 'sha256': manifest}, indent=2), encoding='utf-8')
    (target/'COMPLETE').write_text('Backup verificado; privado, nao publicar.\n', encoding='utf-8')
    return target


if __name__ == '__main__':
    if len(sys.argv) != 5 or sys.argv[1] != '--writers-stopped':
        raise SystemExit('Uso: backup_existente.py --writers-stopped DESTINO RELEASE_ATUAL ARQUIVO_ENV; parar todos os escritores antes.')
    os.umask(0o077)
    print(backup(*sys.argv[2:]))
