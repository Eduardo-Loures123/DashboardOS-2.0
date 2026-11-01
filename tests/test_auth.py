import hashlib,secrets,sqlite3,time
from app import create_app,PAGES
from tests.common import DataCase,login_admin

class AuthTests(DataCase):
    def setUp(self):
        super().setUp();self.app=create_app(self.path);self.app.testing=True;self.client=self.app.test_client();self.auth=self.app.config['AUTH']
        self.client.get('/login')
    def csrf(self,client=None):
        with (client or self.client).session_transaction() as session:return {'X-CSRF-Token':session['csrf']}
    def guest(self):return self.client.post('/auth/guest',json={},headers=self.csrf())
    def test_anonimo_login_csrf_e_cookies(self):
        self.assertEqual(self.client.get('/').location,'/login')
        self.assertEqual(self.client.get('/api/data/dashboard').status_code,401)
        for endpoint in ['/login','/auth/guest','/auth/logout','/api/records/Funcionarios']:
            self.assertEqual(self.client.post(endpoint,json={}).status_code,403)
        response=self.client.get('/login');self.assertIn('Bem-vindo ao DashboardOS',response.text)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        cookie=self.client.get_cookie('session');self.assertTrue(cookie.http_only);self.assertEqual(cookie.same_site,'Strict')
    def test_hashes_ids_e_cli_primeiro_administrador(self):
        password=secrets.token_urlsafe(24)
        result=self.app.test_cli_runner().invoke(args=['criar-admin'],input='local-admin\n'+password+'\n'+password+'\n')
        self.assertEqual(result.exit_code,0,result.output);self.assertNotIn(password,result.output)
        with self.auth.connect() as db:row=db.execute('SELECT * FROM users').fetchone()
        self.assertNotEqual(row['password_hash'],password);self.assertTrue(row['password_hash'].startswith('scrypt:'))
        self.assertNotIn(password,self.auth.path.read_bytes().decode('latin1'))
        with self.assertRaises(ValueError):self.auth.create_admin('local-admin',password)
        with self.assertRaises(ValueError):self.auth.create_admin('a',password)
        with self.assertRaises(ValueError):self.auth.create_admin('outro','curta')
    def test_login_valido_invalido_rotacao_e_persistencia(self):
        password=secrets.token_urlsafe(24);self.auth.create_admin('admin-local',password);before=self.csrf()
        for uid,pwd in [('ausente',password),('admin-local','incorreta')]:
            response=self.client.post('/login',json={'user_id':uid,'password':pwd},headers=self.csrf())
            self.assertEqual(response.status_code,401);self.assertEqual(response.json['error'],'ID ou senha inválidos.')
        response=self.client.post('/login',json={'user_id':'ADMIN-LOCAL','password':password},headers=self.csrf());self.assertEqual(response.status_code,200)
        self.assertNotEqual(before,self.csrf())
        for _ in range(2):self.assertEqual(self.client.get('/api/data/dashboard').json['user']['role'],'admin')
        cookie=self.client.get_cookie('session').value
        second=create_app(self.path).test_client();second.set_cookie('session',cookie)
        self.assertEqual(second.get('/api/data/dashboard').json['user']['id'],'admin-local')
    def test_visitante_leituras_e_bloqueio_de_todas_as_escritas(self):
        self.assertEqual(self.guest().status_code,200);before=hashlib.sha256(self.path.read_bytes()).hexdigest()
        for page in PAGES:
            self.assertEqual(self.client.get('/'+page).status_code,200)
            self.assertEqual(self.client.get('/api/data/'+page).status_code,200)
            self.assertEqual(self.client.get('/api/export/'+page).status_code,200)
        for sheet,rows in self.raw.items():
            for method,url in [('POST','/api/records/'+sheet),('PUT','/api/records/'+sheet+'/'+rows[0]['codigo']),('DELETE','/api/records/'+sheet+'/'+rows[0]['codigo'])]:
                response=self.client.open(url,method=method,json=dict(rows[0],role='admin'),headers=self.csrf())
                self.assertEqual(response.status_code,403,response.json)
        self.assertEqual(before,hashlib.sha256(self.path.read_bytes()).hexdigest())
        page=self.client.get('/funcionarios').text
        self.assertIn('Fazer login',page);self.assertNotIn('Trocar usuário',page)
    def test_logout_revoga_cookie_antigo(self):
        login_admin(self.app,self.client);cookie=self.client.get_cookie('session').value
        self.assertEqual(self.client.post('/auth/logout',json={},headers=self.csrf()).status_code,200)
        self.assertEqual(self.client.get('/api/data/dashboard').status_code,401)
        replay=self.app.test_client();replay.set_cookie('session',cookie)
        self.assertEqual(replay.get('/api/data/dashboard').status_code,401)
    def test_admin_para_visitante_e_outro_admin(self):
        login_admin(self.app,self.client);old_cookie=self.client.get_cookie('session').value;old_csrf=self.csrf()
        self.assertEqual(self.guest().status_code,200)
        self.assertEqual(self.client.get('/api/data/dashboard').json['user']['role'],'guest')
        self.assertEqual(self.client.post('/api/records/Equipes',json={},headers=self.csrf()).status_code,403)
        replay=self.app.test_client();replay.set_cookie('session',old_cookie)
        self.assertEqual(replay.post('/api/records/Equipes',json={},headers=old_csrf).status_code,403)
        password=secrets.token_urlsafe(24);self.auth.create_admin('outro-admin',password)
        self.assertEqual(self.client.post('/auth/logout',json={},headers=self.csrf()).status_code,200)
        self.client.get('/login')
        self.client.post('/login',json={'user_id':'outro-admin','password':password},headers=self.csrf())
        self.assertEqual(self.client.get('/api/data/dashboard').json['user']['id'],'outro-admin')
    def test_sessao_expirada_e_arquivos_privados(self):
        login_admin(self.app,self.client)
        for path in ['/dados/dados_dashboard.xlsx','/instance/auth.sqlite3','/instance/session.key','/static/../instance/auth.sqlite3']:
            self.assertNotEqual(self.client.get(path).status_code,200)
        with self.auth.connect() as db:db.execute('UPDATE sessions SET expires=?',(time.time()-1,))
        self.assertEqual(self.client.get('/api/data/dashboard').status_code,401)
    def test_limite_tentativas_e_payload_invalido(self):
        for _ in range(10):self.assertEqual(self.client.post('/login',json={'user_id':'ausente','password':'invalida'},headers=self.csrf()).status_code,401)
        self.assertEqual(self.client.post('/login',json={'user_id':'ausente','password':'invalida'},headers=self.csrf()).status_code,429)
        self.assertEqual(self.client.post('/login',json=['invalido'],headers=self.csrf()).status_code,400)
