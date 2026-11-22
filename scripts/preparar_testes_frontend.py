"""Gera HTML e respostas reais da API para testes DOM, usando cópia do Excel."""
from pathlib import Path
import sys, tempfile, shutil, json, secrets
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app import create_app, PAGES

root=Path(__file__).resolve().parents[1]
output=root/'tests/fixtures';output.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as temp:
    copied=Path(temp)/'dados.xlsx'
    shutil.copy2(root/'dados/dados_dashboard.xlsx',copied)
    app=create_app(copied)
    with app.test_client() as client:
        login_html=client.get('/login')
        (output/'login.html').write_text(login_html.text,encoding='utf-8')
        password=secrets.token_urlsafe(24)
        app.config['AUTH'].create_admin('teste-admin',password)
        with client.session_transaction() as session:csrf=session['csrf']
        client.post('/login',json={'user_id':'teste-admin','password':password},headers={'X-CSRF-Token':csrf})
        for page in PAGES:
            html=client.get('/'+page)
            data=client.get('/api/data/'+page)
            if html.status_code!=200 or data.status_code!=200:raise RuntimeError('Falha ao preparar '+page)
            (output/(page+'.html')).write_text(html.text,encoding='utf-8')
            (output/(page+'.json')).write_text(json.dumps(data.json,ensure_ascii=False),encoding='utf-8')
        app.config['ENTERPRISE'].promote_initial('teste-admin',password)
        (output/'vencimentos-os.json').write_text(json.dumps(client.get('/api/data/vencimentos?tipo=os').json,ensure_ascii=False),encoding='utf-8')
        for page in ['perfil','administracao']:
            (output/(page+'.html')).write_text(client.get('/'+page).text,encoding='utf-8')
            data={'profile':client.get('/api/profile').json,'users':client.get('/api/admin/users').json['users']}
            (output/(page+'.json')).write_text(json.dumps(data,ensure_ascii=False),encoding='utf-8')
        with client.session_transaction() as session:csrf=session['csrf']
        client.post('/auth/guest',json={},headers={'X-CSRF-Token':csrf})
        for page in PAGES:
            (output/(page+'-guest.html')).write_text(client.get('/'+page).text,encoding='utf-8')
            (output/(page+'-guest.json')).write_text(json.dumps(client.get('/api/data/'+page).json,ensure_ascii=False),encoding='utf-8')
print('Fixtures de oito páginas preparadas a partir de cópia temporária do Excel.')
