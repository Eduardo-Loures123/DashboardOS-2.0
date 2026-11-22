"""P5-A orchestration on exclusively fictional, caller-created temporary files.

No app import, scheduler, legacy processor or network transport. P1-P4 remain
unchanged. A durable inbox bridges confirmed P4 operations to atomic projections.
The local witness is simulated, NOT an independent production trust domain.
"""
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import secrets
import sqlite3
import tempfile
import time
from zoneinfo import ZoneInfo

from werkzeug.security import generate_password_hash, check_password_hash
from .schema import SCHEMA, STATUS
from .enterprise_service import schema as enterprise_schema
from .excel_service import ExcelService
from .email_recipient_schema import migrate_recipient_schema
from .email_recipient_repository import (EmailRecipientRepository, IdentityCheckpoint,
    IdentityManifest, TeamIncarnation, RecordIncarnation)
from .identity_operation_schema import migrate_identity_journal
from .identity_operation_journal import IdentityOperationJournal, TrustedProducer, BusinessAuthorization
from .identity_planner import ProposedOperation
from .continuity_anchor import (TemporaryFileAnchorProvider, AnchorPublisher, AnchorWitness,
    approve_bootstrap, capture_sqlite_evidence, verify_witness, witness)
from .identity_excel_coordinator import IdentityExcelCoordinator, SyntheticWorkbookStore, file_hash
from .identity_excel_recovery import assess_excel_recovery
from .operational_events import analyze_operational_events, OperationalEvent, FOLLOW_UP
from .notification_recipients import ManagerDesignation, resolve_recipients

TZ = ZoneInfo('America/Sao_Paulo')
PASSWORD = 'Demo-Notificacoes-2026!'
USERS = ('root', 'alice', 'bob', 'sem-consentimento', 'nao-verificado', 'somente-email')


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(',', ':'))


def delivery_window(now):
    return (now.hour, now.minute, now.second, now.microsecond) >= (9,0,0,0) and (now.hour, now.minute, now.second, now.microsecond) <= (12,0,0,0)


def fictional_inventory(day):
    date = lambda days: (day + timedelta(days=days)).isoformat()
    return {
        'Funcionarios': [dict(codigo='F1', nome='Ana Exemplo', equipe='T1', cargo='Analista',
            email='ana@example.test', admissao=date(-100), status='Ativo'),
            dict(codigo='F2', nome='Bruno Exemplo', equipe='T2', cargo='Analista',
            email='bruno@example.test', admissao=date(-100), status='Ativo')],
        'Equipes': [dict(codigo='T1', nome='Operações Alfa', responsavel='F1'),
                    dict(codigo='T2', nome='Operações Beta', responsavel='F2')],
        'OrdensServico': [dict(codigo='OS001', descricao='Revisar acesso fictício da equipe Alfa',
            funcionario='F1', abertura=date(-2), previsao=date(10), conclusao='',
            prioridade='Alta', status='Pendente')],
        'Acessos': [dict(codigo='AC001', funcionario='F1', sistema='Portal fictício',
            concessao=date(-30), vencimento=date(15), status='Ativo')],
        'Renovacoes': [dict(codigo='REN001', acesso='AC001', solicitacao=date(-6),
            status='Pendente', responsavel='F1', observacoes='Solicitação fictícia de renovação')],
    }


class DemoNotifications:
    def __init__(self, directory, fault_hook=None):
        self.root = Path(directory).resolve()
        if (not self.root.is_relative_to(Path(tempfile.gettempdir()).resolve())
                or not self.root.name.startswith('dashboardos-p5a-')
                or any(p.is_symlink() for p in (Path(directory).absolute(), *Path(directory).absolute().parents))):
            raise ValueError('A demonstração exige diretório temporário próprio, sem links.')
        self.fault = fault_hook or (lambda boundary: None)
        self.path = self.root / 'demo.sqlite3'
        self.store = SyntheticWorkbookStore(self.root, self.root / 'fictional.xlsx')
        self.provider = TemporaryFileAnchorProvider(self.root / 'anchor-simulated', temporary_root=self.root)
        self.publisher = AnchorPublisher('p5a-fictional', self.provider)

    @contextmanager
    def locked(self):
        path = self.root / 'demo.lock'
        deadline = time.monotonic() + 15
        while True:
            try:
                fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                break
            except FileExistsError:
                if time.monotonic() > deadline:
                    raise ValueError('Demonstração ocupada ou lock abandonado. Não remova provas automaticamente.')
                time.sleep(.025)
        try:
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            db.execute('PRAGMA foreign_keys=ON')
            try:
                yield db
            finally:
                db.close()
        finally:
            os.close(fd)
            path.unlink()

    @staticmethod
    def meta(db, key):
        row = db.execute('SELECT value FROM demo_meta WHERE key=?', (key,)).fetchone()
        if row is None:
            raise ValueError('Metadados da demonstração ausentes; reinicialização automática proibida.')
        return json.loads(row[0])

    @staticmethod
    def put(db, key, value):
        db.execute('INSERT INTO demo_meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',
                   (key, encoded(value)))

    def clock(self, db):
        return datetime.fromisoformat(self.meta(db, 'clock')).astimezone(TZ)

    def save_witness(self, value):
        self.store.write_json(self.root / 'witness.json', asdict(value))

    def components(self, db):
        expected = AnchorWitness(**json.loads((self.root / 'witness.json').read_text(encoding='utf-8')))
        head = verify_witness(self.provider.read(), expected)
        journal = IdentityOperationJournal(db, head.checkpoint,
            TrustedProducer('p5a-demo-only', self.authorize_business))
        coordinator = IdentityExcelCoordinator(self.store, journal, self.publisher,
            expected_witness=expected, initial_file_hash=self.meta(db, 'initial_hash'), fault_hook=self.fault)
        return journal, coordinator

    @staticmethod
    def authorize_business(request):
        if (request.actor_id != 'root' or request.account_role != 'superadmin'
                or request.origin != 'p5a-demo-only' or request.module != 'OrdensServico'
                or request.record_code != 'OS001' or request.kind != 'update'
                or request.authorization_ref != 'demo-os-edit' or request.policy_version != 'p5a-1'):
            raise PermissionError('Operação fictícia não autorizada.')
        return BusinessAuthorization(request.actor_id, request.operation_id, request.plan_fingerprint,
                                     request.authorization_ref, request.policy_version)

    def initialize(self, now=None):
        if self.path.exists():
            raise ValueError('Diretório já inicializado. Use a retomada explícita.')
        now = now or datetime.now(TZ).replace(hour=8, minute=55, second=0, microsecond=0)
        if now.tzinfo is None:
            raise ValueError('Relógio exige fuso horário.')
        now = now.astimezone(TZ)
        raw = fictional_inventory(now.date())
        self.store.write(self.store.current, raw)
        with self.locked() as db:
            db.execute('CREATE TABLE users(id TEXT PRIMARY KEY,password_hash TEXT NOT NULL)')
            enterprise_schema(db)
            password_hash = generate_password_hash(PASSWORD)
            for uid in USERS:
                db.execute('INSERT INTO users VALUES (?,?)', (uid, password_hash))
                db.execute('INSERT INTO account(user_id,role,state,display_name,email,verified,email_alerts) '
                    'VALUES (?,?,\'active\',?,?,?,?)', (uid, 'superadmin' if uid == 'root' else 'user',
                    uid, uid + '@example.test', int(uid != 'nao-verificado'), int(uid != 'sem-consentimento')))
            for i in range(5):
                db.execute('INSERT INTO outbox(user_id,recipient,subject,body) VALUES (?,?,?,?)',
                    ('alice', 'alice@example.test', 'LEGADO FICTÍCIO ' + str(i+1), 'Nunca selecionar ou alterar.'))
            ddl = [
                'CREATE TABLE demo_meta(key TEXT PRIMARY KEY,value TEXT NOT NULL)',
                'CREATE TABLE demo_requests(id TEXT PRIMARY KEY, proposed TEXT NOT NULL, occurred TEXT NOT NULL, projected INTEGER NOT NULL DEFAULT 0)',
                'CREATE TABLE demo_events(id TEXT PRIMARY KEY,payload TEXT NOT NULL,occurred TEXT NOT NULL)',
                'CREATE TABLE demo_candidates(event_id TEXT NOT NULL REFERENCES demo_events(id),uid TEXT NOT NULL REFERENCES users(id),PRIMARY KEY(event_id,uid))',
                'CREATE TABLE demo_notices(event_id TEXT NOT NULL REFERENCES demo_events(id),uid TEXT NOT NULL REFERENCES users(id),read_at TEXT,PRIMARY KEY(event_id,uid))',
                'CREATE TABLE demo_internal(uid TEXT NOT NULL REFERENCES users(id),module TEXT NOT NULL,code TEXT NOT NULL,team TEXT NOT NULL,generation INTEGER NOT NULL,PRIMARY KEY(uid,module,code))',
                'CREATE TABLE demo_denials(uid TEXT PRIMARY KEY REFERENCES users(id),reason TEXT NOT NULL)',
                'CREATE TABLE demo_digests(id INTEGER PRIMARY KEY,uid TEXT NOT NULL REFERENCES users(id),day TEXT NOT NULL,payload TEXT NOT NULL,status TEXT NOT NULL CHECK(status IN (\'prepared\',\'simulated\',\'cancelled\')),UNIQUE(uid,day))',
                'CREATE TABLE demo_deliveries(digest_id INTEGER PRIMARY KEY REFERENCES demo_digests(id),recipient TEXT NOT NULL,body TEXT NOT NULL,delivered TEXT NOT NULL)',
            ]
            for sql in ddl:
                db.execute(sql)
            db.commit()
            epoch = migrate_recipient_schema(db)
            repo = EmailRecipientRepository(db, IdentityCheckpoint(epoch, 0, 0, ''))
            repo.sync_identities(IdentityManifest(epoch, 1, 'p5a-baseline',
                tuple(TeamIncarnation(t['codigo'], 'demo-team-' + t['codigo']) for t in raw['Equipes']),
                tuple(RecordIncarnation(m, r['codigo'], 'demo-life-' + r['codigo'], 'T1', 1)
                      for m in ('OrdensServico','Acessos','Renovacoes') for r in raw[m])), actor_id='root')
            baseline = analyze_operational_events(raw, now=now)
            for uid in USERS:
                for module in ('OrdensServico','Renovacoes'):
                    repo.grant(uid + '-' + module, uid, module, 'team', actor_id='root', raw=raw,
                        snapshot=baseline.snapshot, team_code='T2' if uid == 'bob' else 'T1')
            repo.designate_primary('demo-primary', 'root', actor_id='root')
            migrate_identity_journal(db)
            permit = approve_bootstrap(db, actor_id='root', environment='p5a-fictional', expected_checkpoint=repo.checkpoint)
            receipt = self.publisher.bootstrap(permit, publication_id='p5a-baseline')
            self.save_witness(receipt.witness)
            for uid in ('root','alice'):
                for module, code in [('OrdensServico','OS001'), ('Renovacoes','REN001')]:
                    db.execute('INSERT INTO demo_internal VALUES (?,?,?,?,1)', (uid,module,code,'T1'))
            for key, value in {'clock':now.isoformat(), 'snapshot':baseline.snapshot,
                    'initial_hash':file_hash(self.store.current), 'secret':secrets.token_hex(32),
                    'format':1, 'last_operation':None, 'last_scan':now.isoformat()}.items():
                self.put(db,key,value)
            db.commit()

    def _ready(self, db):
        journal, coordinator = self.components(db)
        head = verify_witness(self.provider.read(), coordinator.expected_witness)
        evidence = capture_sqlite_evidence(db)
        if (head.pending is not None or evidence.checkpoint != head.checkpoint
                or evidence.journal_digest != head.journal_digest
                or evidence.identity_digest != head.identity_digest or evidence.chain_digest != head.chain_digest
                or evidence.receipt_sequence != head.receipt_sequence
                or (head.file_evidence and head.file_evidence.file_phase != 'complete')
                or file_hash(self.store.current) != (head.file_evidence.confirmed_excel_hash
                    if head.file_evidence else self.meta(db, 'initial_hash'))):
            raise ValueError('Operação pendente ou divergência: retome a mesma operação antes de continuar.')
        return journal, coordinator

    def _event(self, row):
        value = json.loads(row['payload']); value['reasons'] = tuple(value['reasons'])
        return OperationalEvent(**value)

    def _internal(self, db, event, raw, snapshot):
        account_rows = [dict(r) for r in db.execute('SELECT * FROM account')]
        employee = {r['codigo']:r for r in raw['Funcionarios']}
        record = next((r for r in raw[event.sheet] if r['codigo'] == event.code), None)
        if not record:
            return ()
        if event.sheet == 'Renovacoes':
            access = next((r for r in raw['Acessos'] if r['codigo'] == record['acesso']), None)
            person = employee.get(access['funcionario']) if access else None
        else:
            person = employee.get(record['funcionario'])
        if not person:
            return ()
        grants = tuple(ManagerDesignation(event.sheet,event.code,event.generation,r['uid'],True,'root')
            for r in db.execute('SELECT * FROM demo_internal WHERE module=? AND code=? AND team=? AND generation=?',
                                (event.sheet,event.code,person['equipe'],event.generation))
            if not db.execute('SELECT 1 FROM demo_denials WHERE uid=?',(r['uid'],)).fetchone())
        return resolve_recipients(event,raw,account_rows,snapshot=snapshot,manager_designations=grants).internal_user_ids

    def _project(self, db, raw, at):
        analysis = analyze_operational_events(raw, previous=self.meta(db,'snapshot'), now=at)
        journal, _ = self._ready(db)
        projections=[]
        for event in analysis.events:
            decision = journal.repository.resolve(event,raw,snapshot=analysis.snapshot)
            recipients=[uid for uid in decision.email_account_ids
                if not db.execute('SELECT 1 FROM demo_denials WHERE uid=?',(uid,)).fetchone()]
            projections.append((event,recipients,self._internal(db,event,raw,analysis.snapshot)))
        for event,recipients,internal in projections:
            db.execute('INSERT OR IGNORE INTO demo_events VALUES (?,?,?)',
                       (event.identity,encoded(asdict(event)),at.isoformat()))
            for uid in recipients:
                db.execute('INSERT OR IGNORE INTO demo_candidates VALUES (?,?)',(event.identity,uid))
            for uid in internal:
                db.execute('INSERT OR IGNORE INTO demo_notices(event_id,uid) VALUES (?,?)',(event.identity,uid))
        self.put(db,'snapshot',analysis.snapshot)
        self.put(db,'last_scan',at.isoformat())
        self.fault('before_projection_commit')
        return len(analysis.events)

    def _drain(self, db):
        for request in db.execute('SELECT * FROM demo_requests WHERE projected=0 ORDER BY rowid').fetchall():
            proposed = json.loads(request['proposed'])
            journal, coordinator = self.components(db)
            try:
                coordinator.execute(proposed,ProposedOperation(request['id'],'update','OrdensServico','OS001'),
                    actor_id='root',authorization_ref='demo-os-edit',policy_version='p5a-1')
            finally:
                self.save_witness(coordinator.expected_witness)
            self.fault('after_p4_commit')
            raw, _ = self.store.read(self.store.current)
            with db:
                self._project(db,raw,datetime.fromisoformat(request['occurred']))
                db.execute('UPDATE demo_requests SET projected=1 WHERE id=?',(request['id'],))
                self.put(db,'last_operation',request['id'])

    @staticmethod
    def admin(db, uid):
        row = db.execute('SELECT role,state FROM account WHERE user_id=?',(uid,)).fetchone()
        if not row or row['role'] != 'superadmin' or row['state'] != 'active':
            raise PermissionError('Ação disponível somente para o administrador fictício.')

    def change_order(self, uid, operation_id, status):
        if (not isinstance(operation_id,str) or not 8 <= len(operation_id) <= 80
                or not all(c.isalnum() or c in '-_' for c in operation_id)):
            raise ValueError('Identificador de operação inválido.')
        if status not in STATUS['OrdensServico']:
            raise ValueError('Status inválido.')
        with self.locked() as db:
            self.admin(db,uid)
            existing = db.execute('SELECT proposed FROM demo_requests WHERE id=?',(operation_id,)).fetchone()
            if existing:
                if json.loads(existing[0])['OrdensServico'][0]['status'] != status:
                    raise ValueError('Identificador já utilizado com outro conteúdo.')
            else:
                self._drain(db)
                self._ready(db)
                raw,_ = self.store.read(self.store.current); proposed=deepcopy(raw)
                proposed['OrdensServico'][0]['status']=status
                proposed['OrdensServico'][0]['conclusao']=self.clock(db).date().isoformat() if status=='Concluída' else ''
                # Reuse all existing business and reference validations before P4.
                ExcelService(self.store.current).validate(proposed)
                with db:
                    db.execute('INSERT INTO demo_requests(id,proposed,occurred) VALUES (?,?,?)',
                               (operation_id,encoded(proposed),self.clock(db).isoformat()))
            self._drain(db)
            self._ready(db)
            return {'operation_id':operation_id,'replayed':existing is not None}

    def recover(self, uid):
        with self.locked() as db:
            self.admin(db,uid); self._drain(db); self._ready(db)

    def advance(self, uid, target):
        if not isinstance(target,datetime) or target.tzinfo is None:
            raise ValueError('Informe data e hora com fuso horário.')
        target=target.astimezone(TZ)
        with self.locked() as db:
            self.admin(db,uid); self._drain(db); self._ready(db)
            if target < self.clock(db) or target > self.clock(db)+timedelta(days=8):
                raise ValueError('Avance o relógio entre o instante atual e os próximos 8 dias.')
            raw,_=self.store.read(self.store.current)
            with db:
                count=self._project(db,raw,target)
                self.put(db,'clock',target.isoformat())
                return count

    def restriction(self, actor, uid, action):
        if uid not in USERS or uid=='root' or action not in ('revoke','optout','unverify'):
            raise ValueError('Controle restritivo inválido.')
        with self.locked() as db:
            self.admin(db,actor); self._drain(db); self._ready(db)
            with db:
                if action=='revoke':
                    db.execute('INSERT OR IGNORE INTO demo_denials VALUES (?,?)',(uid,'Revogação restritiva da demonstração'))
                else:
                    column='email_alerts' if action=='optout' else 'verified'
                    db.execute('UPDATE account SET '+column+'=0 WHERE user_id=?',(uid,))
                db.execute('INSERT INTO audit(actor,action,target,occurred) VALUES (?,?,?,?)',
                           (actor,'demo.restrict.'+action,uid,self.clock(db).isoformat()))

    def _eligible_items(self, db, uid, ids, raw, snapshot, repo):
        if db.execute('SELECT 1 FROM demo_denials WHERE uid=?',(uid,)).fetchone():
            return []
        result=[]
        for event_id in ids:
            row=db.execute('SELECT * FROM demo_events WHERE id=?',(event_id,)).fetchone()
            if not row or not db.execute('SELECT 1 FROM demo_candidates WHERE event_id=? AND uid=?',(event_id,uid)).fetchone():
                continue
            event=self._event(row)
            if uid in repo.resolve(event,raw,snapshot=snapshot).email_account_ids:
                result.append(asdict(event))
        return result

    def compose(self, uid):
        with self.locked() as db:
            self.admin(db,uid); self._drain(db)
            journal,_=self._ready(db);now=self.clock(db)
            if not delivery_window(now):
                return 0
            raw,_=self.store.read(self.store.current);count=0
            prepared=[]
            for user in db.execute('SELECT DISTINCT uid FROM demo_candidates').fetchall():
                ids=[r[0] for r in db.execute('SELECT event_id FROM demo_candidates WHERE uid=?',(user[0],))]
                # Capture an immutable allowlist: delivery may remove, never add items.
                items=self._eligible_items(db,user[0],ids,raw,self.meta(db,'snapshot'),journal.repository)
                items=[i for i in items if i['occurred_on']==now.date().isoformat()
                       or i['status'] in FOLLOW_UP[i['sheet']]]
                if items:
                    prepared.append((user[0],items))
            with db:
                for user_id,items in prepared:
                    cursor=db.execute("INSERT OR IGNORE INTO demo_digests(uid,day,payload,status) VALUES (?,?,?,'prepared')",
                        (user_id,now.date().isoformat(),encoded([i['identity'] for i in items])))
                    count+=cursor.rowcount
            return count

    def deliver(self, uid):
        with self.locked() as db:
            self.admin(db,uid);self._drain(db);journal,_=self._ready(db);now=self.clock(db)
            raw,_=self.store.read(self.store.current);count=0
            prepared=[]
            for digest in db.execute("SELECT * FROM demo_digests WHERE status='prepared'").fetchall():
                items=[]
                if digest['day']==now.date().isoformat() and delivery_window(now):
                    items=self._eligible_items(db,digest['uid'],json.loads(digest['payload']),raw,
                                              self.meta(db,'snapshot'),journal.repository)
                prepared.append((digest,items))
            with db:
                for digest,items in prepared:
                    if not items:
                        db.execute("UPDATE demo_digests SET status='cancelled' WHERE id=?",(digest['id'],));continue
                    account=db.execute('SELECT email FROM account WHERE user_id=?',(digest['uid'],)).fetchone()
                    body='Resumo diário • '+digest['day']+' • SIMULADO\n'+'\n'.join(
                        i['sheet']+' '+i['code']+' • '+i['status']+' • '+
                        (', '.join(i['reasons']) if i['occurred_on']==digest['day'] else 'Pendência atual') for i in items)
                    # This database insert IS the simulated transport. There is no sender callback or SMTP fallback.
                    db.execute('INSERT INTO demo_deliveries VALUES (?,?,?,?)',
                               (digest['id'],account[0],body,now.isoformat()))
                    self.fault('before_delivery_commit')
                    db.execute("UPDATE demo_digests SET status='simulated' WHERE id=?",(digest['id'],));count+=1
            return count

    def authenticate(self, uid, password):
        with self.locked() as db:
            row=db.execute("SELECT u.password_hash FROM users u JOIN account a ON a.user_id=u.id WHERE u.id=? AND a.state='active'",(uid,)).fetchone()
            return bool(row and isinstance(password,str) and len(password)<=200 and check_password_hash(row[0],password))

    def view(self, uid):
        with self.locked() as db:
            account=db.execute('SELECT user_id,role,state,verified,email_alerts FROM account WHERE user_id=?',(uid,)).fetchone()
            if not account or account['state']!='active':
                raise PermissionError('Faça login com uma conta fictícia ativa.')
            journal,coordinator=self._ready(db)
            raw,_=self.store.read(self.store.current);snapshot=self.meta(db,'snapshot')
            notices=[]
            for row in db.execute('SELECT e.*,n.read_at FROM demo_notices n JOIN demo_events e ON e.id=n.event_id WHERE n.uid=? ORDER BY e.rowid DESC',(uid,)):
                event=self._event(row)
                if uid in self._internal(db,event,raw,snapshot):
                    notices.append(dict(id=event.identity,module=event.sheet,code=event.code,status=event.status,
                        reasons=event.reasons,occurred=row['occurred'],read_at=row['read_at']))
            deliveries=[dict(r) for r in db.execute('SELECT d.id,d.uid,d.day,d.status,d.payload,v.body,v.delivered FROM demo_digests d '
                'LEFT JOIN demo_deliveries v ON v.digest_id=d.id WHERE d.uid=? ORDER BY d.id DESC',(uid,))]
            # Historic simulated mail is not a bypass around current content permission.
            # Keep the immutable delivery evidence, but redact details in the user API.
            for delivery in deliveries:
                ids=json.loads(delivery.pop('payload'))
                if delivery['body'] and len(self._eligible_items(db,uid,ids,raw,snapshot,journal.repository)) != len(ids):
                    delivery['body']='Conteúdo restrito indisponível após revalidação de acesso.'
            result=dict(user=dict(account),clock=self.clock(db).isoformat(),notices=notices,outbox=deliveries)
            if account['role']=='superadmin':
                result.update(order=raw['OrdensServico'][0],renewal=raw['Renovacoes'][0],users=[dict(r) for r in db.execute(
                    'SELECT user_id,verified,email_alerts,EXISTS(SELECT 1 FROM demo_denials x WHERE x.uid=account.user_id) AS revoked FROM account')],
                    events=db.execute('SELECT count(*) FROM demo_events').fetchone()[0],
                    operations=db.execute('SELECT count(*) FROM email_identity_receipts').fetchone()[0],
                    legacy=[dict(r) for r in db.execute('SELECT id,status,attempts,subject FROM outbox ORDER BY id')],
                    digests=[dict(r) for r in db.execute('SELECT id,uid,day,status FROM demo_digests ORDER BY id')],
                    last_operation=self.meta(db,'last_operation'),
                    recovery=asdict(assess_excel_recovery(coordinator,self.meta(db,'last_operation'))) if self.meta(db,'last_operation') else None)
            return result
