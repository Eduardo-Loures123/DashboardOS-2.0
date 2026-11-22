"""Independent activity retention. No Flask import, SMTP or operational writes."""
import argparse
from contextlib import closing
from pathlib import Path
import sqlite3
import time


def cleanup(database, execute=False, now=None):
    path=Path(database).resolve()
    if not path.is_file(): raise ValueError('Banco existente obrigatório; não será criado.')
    cutoff=(time.time() if now is None else now)-30*86400
    with closing(sqlite3.connect(path.as_uri()+('?mode=rw' if execute else '?mode=ro'),uri=True)) as db, db:
        db.execute('PRAGMA foreign_keys=ON')
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='profile_activities'").fetchone(): raise ValueError('Estrutura de atividades ausente.')
        count=db.execute('SELECT COUNT(*) FROM profile_activities WHERE occurred<=?',(cutoff,)).fetchone()[0]
        if execute: db.execute('DELETE FROM profile_activities WHERE occurred<=?',(cutoff,))
    return count


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database',required=True)
    parser.add_argument('--execute',action='store_true',help='Remove only expired profile activities; default is read-only.')
    args=parser.parse_args()
    print(('Removidas: ' if args.execute else 'Prévia, sem alterações: ')+str(cleanup(args.database,args.execute)))
