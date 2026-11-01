# DashboardOS 2.0 — transferência para Ubuntu 24.04 LTS

Revisado em 29/10/2026. A EC2, Python e Nginx já existem. Nenhum comando deste guia foi executado no servidor. A página Welcome to nginx confirma o Nginx; a liberação final do dashboard exige HTTPS válido.

## Diagnóstico e conteúdo

- Entrada: app.py; objeto Flask app; fábrica create_app. Gunicorn usa app:app.
- Python mínimo adotado: 3.11; recomendado no Ubuntu 24.04: Python 3.12 do sistema. Ambiente Windows de teste: Python 3.11.2. Verifique `python3 --version` no servidor.
- Dependências diretas no requirements.txt: Flask, Werkzeug, pandas, openpyxl, Plotly, Click e Gunicorn (somente Linux). pip instala as dependências transitivas. Nenhuma biblioteca anterior foi removida. Plotly.js já acompanha static/js/plotly.min.js; não há build Node para executar a aplicação.
- Dados locais: dados/dados_dashboard.xlsx e instance/auth.sqlite3. O arquivo instance/session.key é o segredo de desenvolvimento; NÃO transferir. Produção usa novo SECRET_KEY no ambiente. Isso exige novo login sem excluir usuários.
- Excel contém as abas Funcionarios, Equipes, OrdensServico, Acessos e Renovacoes. Mesmo que os dados iniciais sejam fictícios, o arquivo pode ter sido editado: somente a planilha existente deve ser transferida, separadamente e após aprovação. Não executar scripts/gerar_dados.py.
- AuthService usa hashes scrypt e sessões revogáveis SQLite. Login /login; visitante /auth/guest; saída /auth/logout. CSRF, limite de tentativas e autorização de todas as escritas /api/records são verificados no backend. Visitantes mantêm consultas, filtros e exportações, sem escrita administrativa.
- O pacote inclui todos os 11 templates HTML, todos os CSS e JavaScript locais, todos os módulos services, app.py, requirements.txt e configurações deployment/aws. Não houve edição de templates, CSS, JavaScript, cálculos ou cadastros.
- pathlib já garante caminhos independentes do Windows. Não foram encontradas APIs exclusivas de Windows nos módulos da aplicação. Linux diferencia maiúsculas/minúsculas; preserve os nomes. Scripts shell usam LF. Gunicorn é dependência Linux e não deve ser executado no Windows. systemd/Nginx/TLS ainda exigem validação no Ubuntu.

## Pacote de código

Arquivo no Windows: `C:\Users\eduar\OneDrive\Área de Trabalho\Dashboard_New\DashboardOS_2.0_deploy.tar.gz`.

Para reconstruir, no PowerShell dentro de DashboardOS_2.0: `python deployment/aws/build_package.py`.

A seleção é explícita. Não entram dados, instance, backups, .env reais, chaves, credenciais, .git, .venv, node_modules, testes, fixtures, gerador de dados, temporários ou __pycache__. .env.example e dashboardos.env.example contêm somente placeholders. O arquivo .sha256 ao lado permite verificar integridade. Não há dados persistentes no pacote.

## Transferência futura — somente após sua autorização

No PowerShell, a partir da pasta Dashboard_New:

```powershell
$key = Read-Host 'Caminho da chave SSH privada existente'
$server = Read-Host 'IPv4 ou DNS real da sua EC2'
Get-FileHash .\DashboardOS_2.0_deploy.tar.gz -Algorithm SHA256
scp -i $key .\DashboardOS_2.0_deploy.tar.gz .\DashboardOS_2.0_deploy.tar.gz.sha256 "ubuntu@${server}:"
ssh -i $key "ubuntu@$server"
```

Para transferir dados em outro momento, primeiro pare a aplicação local, feche o Excel e pause alterações/sincronização dos arquivos. Faça uma cópia privada consistente, usando lock do Excel e API de backup SQLite. O comando abaixo cria backup local somente quando você decidir executá-lo, não integra o pacote:

```powershell
cd .\DashboardOS_2.0
python -c "from pathlib import Path; from deployment.aws.backup import backup; print(backup(Path('dados/dados_dashboard.xlsx'), Path('instance/auth.sqlite3'), Path('../DashboardOS_dados_privados')))"
```

Selecione o diretório com marca COMPLETE emitido pelo comando. Não publique seu conteúdo: o SQLite contém hashes e sessões. Transfira apenas os dois arquivos desse backup por SSH/SCP, para um diretório privado de staging no servidor. Nunca transfira session.key ou o ambiente local. Não gere nem migre os dados. Os comandos SCP para os dados devem ser executados apenas após aprovação explícita da transferência privada:

```powershell
$backup = Read-Host 'Caminho completo do backup COMPLETE escolhido'
scp -i $key "$backup\dados_dashboard.xlsx" "$backup\auth.sqlite3" "ubuntu@${server}:dashboardos-data/"
```

Antes desse último comando, crie o destino no SSH: `mkdir -m 700 ~/dashboardos-data`. O destino precisa ser novo; se já existir, confira o conteúdo antes de reutilizá-lo.

## Preparar o Ubuntu existente

Em SSH, depois das transferências autorizadas:

```bash
sha256sum -c ~/DashboardOS_2.0_deploy.tar.gz.sha256
mkdir -m 700 ~/dashboardos-upload
tar -xzf ~/DashboardOS_2.0_deploy.tar.gz -C ~/dashboardos-upload
cd ~/dashboardos-upload/DashboardOS_2.0
python3 --version
sudo bash deployment/aws/install.sh
```

install.sh usa apt para assegurar python3-venv, pip, rsync, Nginx e Certbot; não cria instância ou recurso AWS. Cria usuário sem login dashboardos e diretórios persistentes. Não reinstala o sistema operacional. Código em /opt/dashboardos/releases; dados em /var/lib/dashboardos. Ambos persistem no EBS, mas o EBS não substitui backup externo.

Importe os dados uma única vez. Estes comandos recusam sobrescrever destinos existentes:

```bash
sudo test ! -e /var/lib/dashboardos/excel/dados_dashboard.xlsx && sudo install -o dashboardos -g www-data -m 600 ~/dashboardos-data/dados_dashboard.xlsx /var/lib/dashboardos/excel/dados_dashboard.xlsx
sudo test ! -e /var/lib/dashboardos/auth/auth.sqlite3 && sudo install -o dashboardos -g www-data -m 600 ~/dashboardos-data/auth.sqlite3 /var/lib/dashboardos/auth/auth.sqlite3
sudo test ! -e /etc/dashboardos/dashboardos.env && sudo install -o root -g root -m 600 deployment/aws/.env.example /etc/dashboardos/dashboardos.env
sudo python3 - <<'PY'
from pathlib import Path
import secrets
p=Path('/etc/dashboardos/dashboardos.env')
s=p.read_text()
placeholder='SUBSTITUA_POR_SEGREDO_ALEATORIO_GERADO_NO_SERVIDOR'
if placeholder in s:
    p.write_text(s.replace(placeholder,secrets.token_hex(32)))
PY
sudo nano /etc/dashboardos/dashboardos.env
```

Configure as variáveis:

| Variável | Valor |
| --- | --- |
| DASHBOARD_ENV | production |
| SECRET_KEY | segredo aleatório gerado no servidor, ao menos 64 caracteres; não compartilhar |
| DASHBOARD_ALLOWED_HOSTS | seu domínio real, sem esquema, caminho ou porta; nomes exatos separados por vírgula |
| DASHBOARD_EXCEL_PATH | /var/lib/dashboardos/excel/dados_dashboard.xlsx |
| DASHBOARD_AUTH_DIRECTORY | /var/lib/dashboardos/auth |
| TZ | America/Sao_Paulo |

SECRET_KEY não deve mudar em cada atualização. Não habilite FLASK_DEBUG. O arquivo de ambiente deve usar valores simples sem espaços/expansões, compatíveis com shell e systemd; nunca carregar arquivos de terceiros. Produção recusa iniciar sem os arquivos persistentes e sem segredo seguro. Cookies Secure, HttpOnly, SameSite Strict e HSTS são habilitados; sessões continuam revogáveis no banco.

```bash
sudo bash deployment/aws/deploy.sh "$PWD"
sudo journalctl -u dashboardos -n 50 --no-pager
sudo bash /opt/dashboardos/current/deployment/aws/check.sh
```

O deploy cria uma release, instala requirements, registra versões em installed-requirements.txt, valida configuração e leitura do Excel e inicia systemd. Dados e ambiente não são sobrescritos por atualizações. Sem dados importados a inicialização falha deliberadamente. Não existe senha administrativa padrão.

## Gunicorn e proxy

Comando exato, executado pelo systemd com ambiente carregado, usuário dashboardos e diretório /opt/dashboardos/current:

```bash
/opt/dashboardos/current/.venv/bin/gunicorn -c deployment/aws/gunicorn.conf.py app:app
```

Para rodar manualmente para diagnóstico (pare primeiro o serviço, para não disputar o socket):

```bash
sudo systemctl stop dashboardos
sudo install -d -o dashboardos -g www-data -m 750 /run/dashboardos
sudo bash -c 'set -a; source /etc/dashboardos/dashboardos.env; set +a; cd /opt/dashboardos/current; exec runuser -u dashboardos --preserve-environment -- .venv/bin/gunicorn -c deployment/aws/gunicorn.conf.py app:app'
```

Ctrl+C encerra esse diagnóstico. Depois use `sudo systemctl start dashboardos`. Um worker sync e uma thread mantêm um escritor. Excel conserva lock, validação, backups pré-gravação e substituição atômica. Não remova locks com processos ativos e não edite o Excel externamente durante o uso. Nginx acessa apenas socket Unix /run/dashboardos/app.sock; nenhuma porta Gunicorn deve ser liberada no Security Group.

ProxyFix confia em exatamente um Nginx local. Nginx fixa Host e sobrescreve X-Forwarded-For/Proto; outros cabeçalhos de encaminhamento são ignorados. Não exponha esse socket ou coloque outro proxy sem rever a configuração. Arquivos estáticos são atendidos pelo Flask por trás do Nginx. Excel e SQLite não têm rota pública.

## Nginx e HTTPS

Use seu domínio real com registro A para o IPv4 da EC2. Não foi inventado domínio ou certificado. Confira custos de domínio e serviços adicionais antes de contratar. Em Ubuntu recém-instalado com o site padrão:

```bash
read -r -p 'Seu domínio real: ' DOMAIN
[[ "$DOMAIN" =~ ^[A-Za-z0-9.-]+$ ]] || exit 1
sed "s/__DOMAIN__/$DOMAIN/g" deployment/aws/nginx.conf | sudo tee /etc/nginx/sites-available/dashboardos >/dev/null
sudo ln -s /etc/nginx/sites-available/dashboardos /etc/nginx/sites-enabled/dashboardos
sudo test ! -L /etc/nginx/sites-enabled/default || sudo unlink /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl reload nginx
sudo certbot --nginx -d "$DOMAIN" --redirect
sudo nginx -t
sudo systemctl reload nginx
sudo certbot renew --dry-run
curl -I "https://$DOMAIN/login"
```

Não prossiga se nginx -t falhar. O modelo é bootstrap HTTP para Certbot adicionar TLS; não libere o dashboard até HTTPS e redirecionamento funcionarem. Não reinstale o modelo sobre o arquivo alterado pelo Certbot durante updates. Deixe SSH 22 só para seu IP; 80 para validação/redirecionamento e 443 para HTTPS; não abra 5000/8000.

HTTPS temporário: Cloudflare Quick Tunnels pode emitir um hostname aleatório para demonstração, sem SLA e sem indicação para produção. Não foi ativado. Ele exige configuração separada de Nginx em loopback e revisão da cadeia de proxy; não aplique o modelo público sem adaptação. Para a implantação contínua, use domínio e TLS válidos. Consulte a documentação oficial de Quick Tunnels se escolher essa alternativa.

## Backup, atualização e operação

```bash
sudo bash /opt/dashboardos/current/deployment/aws/backup.sh
sudo journalctl -u dashboardos -f
sudo tail -f /var/log/nginx/dashboardos.error.log
```

Backups em /var/lib/dashboardos/backups possuem COMPLETE ou INCOMPLETE. SQLite usa API de backup e integrity_check; Excel é copiado sob lock. O backup não é uma transação única entre arquivos independentes. Guarde também o ambiente em cofre privado. Não há exclusão automática: monitore espaço e retenção; backup no mesmo disco não protege contra perda do EBS. Agendamento opcional com cron: `0 3 * * * /bin/bash /opt/dashboardos/current/deployment/aws/backup.sh`; confira resultado e retenção antes de ativar.

Para restaurar, pare serviço e tarefas de backup, preserve o estado atual, valide SQLite e Excel do backup COMPLETE e somente então substitua os arquivos persistentes, com dashboardos:www-data e modo 600. Reinicie e valide login, usuários e indicadores. Restauração sobrescreve o estado atual e requer escolha explícita do backup; nunca é automática.

Atualização: envie e extraia outro pacote de código e execute `sudo bash deployment/aws/update.sh "$PWD"` no novo código. O script faz backup, troca a release e reverte o código em falha do check quando existe release anterior. Dados não são restaurados automaticamente. Há breve indisponibilidade.

## Testes e limites

Localmente: `python scripts/testar.py` e `node --test --test-isolation=none tests/frontend.test.cjs`. Os testes de escrita usam cópias temporárias; os testes DOM usam fixtures e não renderizam CSS ou Plotly. Não houve alteração de dados originais. Não foi executada implantação, SCP ou comando AWS.

No Ubuntu, ainda será necessário validar instalação das dependências, Gunicorn, nginx -t, systemd, TLS real, reinício, leitura/escrita em cópia isolada, restauração e consumo de memória. O fato de o pacote ter sido preparado no Windows não equivale a execução validada em Linux.

A instância já existe: confira faturamento, região, EBS, IPv4 e saída de dados. A elegibilidade ao Free Tier depende da conta, plano e prazo de créditos. Os scripts não contratam serviços adicionais nem garantem custo zero.
