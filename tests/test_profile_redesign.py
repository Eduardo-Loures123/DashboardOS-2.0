"""Profile persistence and security; every write is in a temporary directory."""
import copy
from io import BytesIO
import secrets
import sqlite3
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch
from PIL import Image
from app import create_app
from scripts.limpar_atividades import cleanup
from services.profile_service import ProfileService
from tests.common import DataCase,login_admin


class ProfileRedesignTests(DataCase):
    def setUp(self):
        super().setUp()
        self.app=create_app(self.path);self.client=self.app.test_client()
        self.auth=self.app.config['AUTH'];self.enterprise=self.app.config['ENTERPRISE'];self.profiles=self.app.config['PROFILES']
        self.password=secrets.token_urlsafe(20)
        self.headers=login_admin(self.app,self.client,'owner',self.password)

    def update(self,values):
        return self.client.put('/api/profile',json=values,headers=self.headers)

    def image(self,format='PNG'):
        output=BytesIO();Image.new('RGB',(30,25),'blue').save(output,format=format);output.seek(0);return output

    def test_login_changes_preserve_permanent_key_hash_role_and_relationships(self):
        before=self.profiles.profile('owner');key=before['account_id']
        with self.auth.connect() as db:
            old=db.execute('SELECT password_hash FROM users WHERE id=?',(key,)).fetchone()[0]
            db.execute("UPDATE account SET email='old@example.test',verified=1,email_alerts=1 WHERE user_id=?",(key,))
            self.enterprise.emit(db,'identity-event','operational','Test','Safe','/acessos')
            queue=[tuple(r) for r in db.execute('SELECT * FROM outbox')]
        result=self.update({'user_id':'OWNER.NEW','current_password':self.password})
        self.assertEqual(result.status_code,200);self.assertEqual(result.json['redirect'],'/login')
        self.assertEqual(self.auth.authenticate('Owner.New',self.password,'test')[0],key)
        self.assertEqual(self.auth.authenticate('owner',self.password,'test')[1],401)
        profile=self.profiles.profile(key)
        self.assertEqual(profile['user_id'],'owner.new');self.assertEqual(profile['account_id'],key);self.assertEqual(profile['role'],before['role'])
        with self.auth.connect() as db:
            self.assertEqual(db.execute('SELECT password_hash FROM users WHERE id=?',(key,)).fetchone()[0],old)
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM outbox')],queue)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM sessions WHERE user_id=?',(key,)).fetchone()[0],0)
        self.assertEqual(self.profiles.login_available(key,'owner.new'),True)

    def test_case_insensitive_duplicate_login_and_current_password_required(self):
        self.auth.create_admin('other',self.password)
        self.assertEqual(self.update({'user_id':'OTHER','current_password':self.password}).status_code,400)
        self.assertEqual(self.update({'user_id':'free.name','current_password':'wrong'}).status_code,400)
        self.assertEqual(self.update({'user_id':'bad id','current_password':self.password}).status_code,400)
        self.assertFalse(self.client.get('/api/profile/login-availability?login=OTHER').json['available'])

    def test_concurrent_login_reservation_has_one_winner(self):
        self.auth.create_admin('other',self.password)
        def change(uid):
            try:self.profiles.update(uid,{'user_id':'shared','current_password':self.password});return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(change,['owner','other']))
        self.assertEqual(sum(results),1)

    def test_name_saves_but_role_and_state_cannot_be_escalated(self):
        self.assertEqual(self.update({'display_name':'Nome atualizado','role':'superadmin','state':'blocked'}).status_code,200)
        data=self.profiles.profile('owner');self.assertEqual(data['display_name'],'Nome atualizado');self.assertEqual(data['role'],'admin');self.assertEqual(data['state'],'active')
        self.assertEqual(self.update({'display_name':''}).status_code,400)

    def test_password_confirm_and_revoke_other_sessions_without_logging_secret(self):
        self.auth.start('owner')
        self.assertEqual(self.update({'password':'another-secure-password','password_confirmation':'different','current_password':self.password}).status_code,400)
        self.assertEqual(self.update({'password':'another-secure-password','password_confirmation':'another-secure-password','current_password':self.password}).status_code,200)
        self.assertEqual(self.auth.authenticate('owner','another-secure-password','test')[1],200)
        with self.auth.connect() as db:
            audit=str([tuple(r) for r in db.execute('SELECT actor,action,target FROM audit')])
        self.assertNotIn(self.password,audit);self.assertNotIn('another-secure-password',audit)

    def test_avatar_upload_replace_remove_and_persistence(self):
        first=self.client.post('/api/profile/avatar',data={'photo':(self.image(),'photo.png')},headers=self.headers)
        self.assertEqual(first.status_code,200,first.json);old=self.profiles.avatar_path('owner')
        self.assertTrue(old.is_file());self.assertEqual(self.client.get('/api/profile/avatar').content_type,'image/webp')
        second=self.client.post('/api/profile/avatar',data={'photo':(self.image('JPEG'),'photo.jpg')},headers=self.headers)
        self.assertEqual(second.status_code,200);self.assertFalse(old.exists())
        current=self.profiles.avatar_path('owner');self.assertTrue(current.exists())
        self.assertIsNotNone(create_app(self.path).config['PROFILES'].profile('owner')['avatar_url'])
        self.assertEqual(self.client.delete('/api/profile/avatar',headers=self.headers).status_code,200)
        self.assertFalse(current.exists());self.assertIsNone(self.profiles.profile('owner')['avatar_url'])

    def test_avatar_rejects_executable_mime_spoof_and_oversize(self):
        for payload,name in [(BytesIO(b'MZ executable'),'photo.png'),(self.image(),'photo.svg'),(BytesIO(b'0'*(5*1024*1024+1)),'photo.png')]:
            response=self.client.post('/api/profile/avatar',data={'photo':(payload,name)},headers=self.headers)
            self.assertEqual(response.status_code,400,response.json)
        self.assertIsNone(self.profiles.avatar_path('owner'))
        response=self.client.post('/api/profile/avatar',data={'photo':(BytesIO(b'0'*(7*1024*1024)),'photo.png')},headers=self.headers)
        self.assertEqual(response.status_code,413);self.assertIn('5 MB',response.json['error'])
        with patch.object(self.profiles,'set_avatar',side_effect=PermissionError('private-path-secret')):
            response=self.client.post('/api/profile/avatar',data={'photo':(self.image(),'photo.png')},headers=self.headers)
        self.assertEqual(response.status_code,503);self.assertNotIn('private-path-secret',response.text)

    def test_avatar_permissions_and_webp(self):
        guest=self.app.test_client()
        self.assertIn(guest.get('/api/profile/avatar').status_code,(401,403))
        response=self.client.post('/api/profile/avatar',data={'photo':(self.image('WEBP'),'photo.webp')},headers=self.headers)
        self.assertEqual(response.status_code,200)
        self.auth.create_admin('other',self.password);other=self.app.test_client()
        other.get('/login')
        with other.session_transaction() as s:csrf=s['csrf']
        other.post('/login',json={'user_id':'other','password':self.password},headers={'X-CSRF-Token':csrf})
        self.assertEqual(other.get('/api/profile/avatar?user_id=owner').status_code,404)

    def test_pending_email_preserves_old_address_preferences_and_outbox(self):
        with self.auth.connect() as db:
            db.execute("UPDATE account SET email='old@example.test',verified=1,email_alerts=1 WHERE user_id='owner'")
            self.enterprise.emit(db,'old-event','operational','Title','Body','/acessos')
            before=[tuple(r) for r in db.execute('SELECT * FROM outbox')]
        code=self.profiles.change_email('owner','NEW@EXAMPLE.TEST',self.password)
        p=self.profiles.profile('owner');self.assertEqual(p['email'],'old@example.test');self.assertTrue(p['verified']);self.assertEqual(p['pending_email']['address'],'new@example.test')
        with self.auth.connect() as db:
            self.assertNotEqual(db.execute('SELECT digest FROM profile_email_changes').fetchone()[0],code)
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM outbox')],before)
        self.profiles.confirm_email('owner',code)
        p=self.profiles.profile('owner');self.assertEqual(p['email'],'new@example.test');self.assertTrue(p['verified']);self.assertTrue(p['email_alerts'])
        with self.auth.connect() as db:self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM outbox')],before)

    def test_email_expiration_cancel_invalid_attempts_and_no_automatic_optin(self):
        code=self.profiles.change_email('owner','new@example.test',self.password)
        with self.auth.connect() as db:db.execute('UPDATE profile_email_changes SET expires=0')
        with self.assertRaises(ValueError):self.profiles.confirm_email('owner',code)
        self.assertEqual(self.profiles.profile('owner')['email'],'')
        self.profiles.cancel_email('owner')
        code=self.profiles.change_email('owner','new@example.test',self.password)
        for _ in range(5):
            with self.assertRaises(ValueError):self.profiles.confirm_email('owner','invalid')
        with self.assertRaises(ValueError):self.profiles.confirm_email('owner',code)
        self.profiles.cancel_email('owner')
        code=self.profiles.change_email('owner','new@example.test',self.password)
        self.profiles.confirm_email('owner',code)
        self.assertFalse(self.profiles.profile('owner')['email_alerts'])

    def test_email_route_never_exposes_code_or_modifies_main_queue(self):
        response=self.client.post('/api/profile/email-change',json={'email':'new@example.test','current_password':self.password},headers=self.headers)
        self.assertEqual(response.status_code,200);self.assertFalse(response.json['delivery_available']);self.assertNotIn('digest',response.text);self.assertNotIn('token',response.json)
        with self.auth.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM outbox').fetchone()[0],0)
        self.assertEqual(self.client.delete('/api/profile/email-change',headers=self.headers).status_code,200)

    def test_unique_verified_email_and_concurrent_confirmations(self):
        self.auth.create_admin('other',self.password)
        first=self.profiles.change_email('owner','shared@example.test',self.password)
        second=self.profiles.change_email('other','SHARED@example.test',self.password)
        self.profiles.confirm_email('owner',first)
        with self.assertRaises(ValueError):self.profiles.confirm_email('other',second)
        self.assertEqual(self.profiles.profile('other')['email'],'')

    def test_internal_always_on_and_email_requires_verified_address(self):
        self.assertEqual(self.update({'email_alerts':True}).status_code,400)
        self.assertEqual(self.update({'internal_alerts':False}).status_code,200)
        with self.auth.connect() as db:
            db.execute("UPDATE account SET internal_alerts=0 WHERE user_id='owner'")
            self.enterprise.emit(db,'general','operational','Title','Safe body','/acessos')
        self.assertEqual(len(self.enterprise.notifications('owner')),1)
        self.assertTrue(self.profiles.profile('owner')['internal_alerts'])

    def test_only_successful_operations_record_activity_and_owner_is_session_bound(self):
        record=dict(self.raw['Acessos'][0]);record['sistema']='Fictício'
        result=self.client.put('/api/records/Acessos/'+record['codigo'],json=record,headers=self.headers)
        self.assertEqual(result.status_code,200)
        invalid=dict(record,status='Invalid')
        self.assertEqual(self.client.put('/api/records/Acessos/'+record['codigo'],json=invalid,headers=self.headers).status_code,400)
        self.auth.create_admin('other',self.password);self.profiles.record_activity('other','create','Acessos','SECRET-CODE')
        result=self.client.get('/api/profile/activities?user_id=other').json
        self.assertEqual(result['total'],1);self.assertEqual(result['activities'][0]['operation'],'update');self.assertNotIn('SECRET-CODE',str(result))

    def test_activity_search_pagination_idempotence_and_retention_boundary(self):
        now=time.time();cutoff=now-30*86400
        self.profiles.record_activity('owner','create','Acessos','TEST001','operation-one')
        self.profiles.record_activity('owner','create','Acessos','TEST001','operation-one')
        self.profiles.record_activity('owner','delete','Equipes','TEST002')
        with self.auth.connect() as db:
            db.execute('UPDATE profile_activities SET occurred=? WHERE record_code=?',(cutoff,'TEST001'))
            users=[tuple(r) for r in db.execute('SELECT * FROM users')]
        with patch('services.profile_service.time.time',return_value=now):
            self.assertEqual(self.profiles.activities('owner')['total'],1)
        self.assertEqual(cleanup(self.auth.path,False,now),1)
        self.assertEqual(cleanup(self.auth.path,True,now),1)
        self.assertEqual(self.profiles.activities('owner','delete','TEST002')['total'],1)
        with self.auth.connect() as db:
            self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM users')],users)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM profile_activities').fetchone()[0],1)
        with self.assertRaises(ValueError):self.profiles.activities('owner',page=-1)

    def test_additive_migration_on_legacy_copy_preserves_every_existing_row(self):
        # Rebuild only a dedicated temporary legacy fixture, never original data.
        target=self.path.parent/'legacy';target.mkdir()
        with sqlite3.connect(target/'auth.sqlite3') as db:
            db.executescript('CREATE TABLE users(id TEXT PRIMARY KEY,password_hash TEXT NOT NULL);INSERT INTO users VALUES (\'legacy\',\'unchanged-hash\');')
        db.close()
        from services.auth_service import AuthService
        from services.enterprise_service import EnterpriseService
        auth=AuthService(target);enterprise=EnterpriseService(auth);enterprise.migrate()
        service=ProfileService(auth,enterprise)
        with auth.connect() as db:
            before={name:[tuple(r) for r in db.execute('SELECT * FROM '+name)] for name in ['users','account','outbox','tokens','audit']}
        backup=service.migrate();self.assertTrue(backup.exists());service.migrate()
        with auth.connect() as db:
            for name,rows in before.items():self.assertEqual([tuple(r) for r in db.execute('SELECT * FROM '+name)],rows)
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
