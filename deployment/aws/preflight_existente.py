"""Preflight somente leitura; nao importa app, nao migra, nao recupera Excel."""
from contextlib import closing
import os
from pathlib import Path
import sqlite3
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))

def check():
    if os.environ.get('DASHBOARD_ENV')!='production':raise RuntimeError('DASHBOARD_ENV deve ser production.')
    excel=Path(os.environ['DASHBOARD_EXCEL_PATH']).resolve(strict=True)
    auth=Path(os.environ['DASHBOARD_AUTH_DIRECTORY']).resolve(strict=True)
    dbpath=(auth/'auth.sqlite3').resolve(strict=True)
    if excel.is_relative_to(ROOT) or auth.is_relative_to(ROOT):raise RuntimeError('Dados devem estar fora da release.')
    secret=os.environ.get('SECRET_KEY','')
    if len(secret)<64 or len(set(secret))<8:raise RuntimeError('SECRET_KEY incompativel; nao alterar sem avaliar sessoes existentes.')
    hosts=os.environ.get('DASHBOARD_ALLOWED_HOSTS','').split(',')
    if any(not h.strip() or h.strip()=='*' or '/' in h or ':' in h for h in hosts):raise RuntimeError('ALLOWED_HOSTS invalido.')
    from services.mail_service import email_suspended
    if not email_suspended():raise RuntimeError('DASHBOARD_EMAIL_SUSPENDED=false proibido nesta release.')
    from services.enterprise_service import schema
    with closing(sqlite3.connect(':memory:')) as expected:
        expected.execute('CREATE TABLE users(id TEXT PRIMARY KEY,password_hash TEXT NOT NULL)')
        expected.execute('CREATE TABLE sessions(token_hash TEXT PRIMARY KEY,user_id TEXT REFERENCES users(id),expires REAL NOT NULL)')
        expected.execute('CREATE TABLE attempts(client TEXT NOT NULL,occurred REAL NOT NULL)')
        schema(expected)
        with closing(sqlite3.connect(dbpath.as_uri()+'?mode=ro',uri=True)) as actual:
            actual.execute('PRAGMA query_only=ON')
            if actual.execute('PRAGMA integrity_check').fetchone()[0]!='ok':raise RuntimeError('SQLite invalido.')
            if actual.execute('PRAGMA foreign_key_check').fetchone():raise RuntimeError('SQLite tem referencias invalidas.')
            for table, in expected.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"):
                wanted={x[1] for x in expected.execute('PRAGMA table_info("'+table+'")')}
                found={x[1] for x in actual.execute('PRAGMA table_info("'+table+'")')}
                if not wanted<=found:raise RuntimeError('Estrutura incompativel: '+table+'. Pare; migracao exige autorizacao.')
            indexes={x[0] for x in actual.execute("SELECT name FROM sqlite_master WHERE type='index'")}
            if 'profile_verified_email' not in indexes:raise RuntimeError('Indice de e-mail verificado ausente. Pare; migracao exige autorizacao.')
    from openpyxl import load_workbook
    from services.schema import SCHEMA
    workbook=load_workbook(excel,read_only=True,data_only=False)
    try:
        for sheet,columns in SCHEMA.items():
            if sheet not in workbook.sheetnames:raise RuntimeError('Aba ausente: '+sheet)
            header=next(workbook[sheet].iter_rows(values_only=True))
            if not set(columns)<=set(header):raise RuntimeError('Colunas incompativeis: '+sheet)
    finally:workbook.close()
    for location in (excel.parent,auth):
        if not os.access(location,os.R_OK|os.W_OK|os.X_OK):raise RuntimeError('Permissoes insuficientes para usuario do servico.')
    if not os.access(excel,os.R_OK|os.W_OK) or not os.access(dbpath,os.R_OK|os.W_OK):raise RuntimeError('Arquivos nao gravaveis pelo servico.')
    if (excel.parent/(excel.name+'.import-journal.json')).exists():raise RuntimeError('Diario de recuperacao pendente; inspecionar antes da troca.')
    print('Preflight de leitura aprovado; nenhuma migracao ou envio executado.')

if __name__=='__main__':
    try:check()
    except Exception as error:
        print('BLOQUEADO:',str(error),file=sys.stderr);sys.exit(1)
