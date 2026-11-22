# Atualizar a EC2 existente — 2.1.3 preparada, não publicada

Não executar sem autorização. Este roteiro atualiza apenas código. Não usar
`install.sh`, `deploy.sh` ou `update.sh` antigos: eles podem substituir a unidade
systemd. Não reinstalar Nginx, Gunicorn do sistema, certificados ou infraestrutura.

## 1. Conferência e condição de parada

No servidor, após autorização, conferir sem exibir segredos:

```bash
sudo systemctl show dashboardos -p User -p Group -p WorkingDirectory -p ExecStart -p EnvironmentFiles
sudo systemctl is-active dashboardos nginx
readlink -f /opt/dashboardos/current
cat /opt/dashboardos/current/VERSION
sudo systemctl list-timers --all | grep -i dashboardos
```

Os comandos seguintes pressupõem a implantação já documentada:
`/opt/dashboardos/current` é link para uma release; serviço `dashboardos`, usuário
`dashboardos`, grupo `www-data`, ambiente `/etc/dashboardos/dashboardos.env`, socket
`/run/dashboardos/app.sock`. Se diferirem, **parar e adaptar o roteiro aos caminhos
reais**; não substituir unidades ou mover dados para forçar correspondência.
Identificar em sessão administrativa os caminhos das duas variáveis de dados, sem
publicar o conteúdo do arquivo de ambiente. Comparar estrutura/versão, não substituir
os dados do servidor por dados locais. Verificar espaço para backup e duas releases.

Auditar cron/timers/processos de alertas. Um processo antigo já em execução ainda
usa código antigo: sua parada precisa anteceder a atualização, dentro da janela
autorizada. Não habilitar timers nem retomar a fila histórica. A nova release bloqueia
o envio por padrão, inclusive se `DASHBOARD_MAIL_ENABLED=true`; a variável
`DASHBOARD_EMAIL_SUSPENDED=false` é proibida nesta publicação. Não copiar exemplos
de ambiente sobre a configuração existente.

## 2. Transferência e preparação sem afetar a versão ativa

Enviar somente o arquivo `DashboardOS_2.0_2.1.3_codigo.tar.gz` e seu `.sha256` por
SCP/SFTP para um diretório privado de staging. Nenhum comando de envio foi executado
localmente nesta preparação. No servidor:

```bash
sha256sum -c DashboardOS_2.0_2.1.3_codigo.tar.gz.sha256
tar -tzf DashboardOS_2.0_2.1.3_codigo.tar.gz
release="/opt/dashboardos/releases/2.1.3_$(date -u +%Y%m%dT%H%M%SZ)"
sudo install -d -m 755 "$release"
sudo tar -xzf DashboardOS_2.0_2.1.3_codigo.tar.gz --strip-components=1 -C "$release"
sudo python3 -m venv "$release/.venv"
sudo "$release/.venv/bin/pip" install -r "$release/requirements.txt"
sudo "$release/.venv/bin/pip" check
sudo "$release/.venv/bin/pip" freeze | sudo tee "$release/installed-requirements.txt" >/dev/null
```

Usar Python 3.11 ou superior. O entrypoint é `app:app`; manter **um worker sync e
uma thread** por causa do Excel e das prévias de importação em memória. Logs vão
para stdout/stderr e journal; recursos estáticos e Plotly são locais. Não executar
`python app.py` como serviço de produção. Gunicorn não foi executado no Windows.

## 3. Janela, backup verificável e preflight

Interromper os escritores externos/importações e os processadores legados identificados
na conferência; guardar seu estado anterior. Parar somente o serviço da aplicação,
mantendo Nginx/HTTPS existentes. Manter a janela até a validação terminar:

```bash
previous=$(readlink -f /opt/dashboardos/current)
sudo systemctl stop dashboardos
```

Em shell administrativo com `umask 077`, carregar o arquivo de ambiente existente
(arquivo confiável de administração, nunca fornecido por usuário) e definir `backup`
em diretório privado fora de releases, por exemplo `/var/backups/dashboardos/<UTC>`.
Copiar com `cp -a` a release anterior, o arquivo de ambiente e **as pastas completas**
`DASHBOARD_AUTH_DIRECTORY` e a pasta pai de `DASHBOARD_EXCEL_PATH`. Isso inclui banco,
WAL/SHM quando presentes, avatares, chave de sessão, backups, diários e recuperação.
Nenhum escritor pode continuar durante essa cópia. Registrar os caminhos de origem
e destino; verificar hashes de todos os arquivos copiados, SQLite `integrity_check`
na cópia e leitura do Excel na cópia. Não utilizar o helper antigo de backup para
esta conferência: ele adquire lock e pode iniciar recuperação automaticamente.
Sem backup completo e verificável, não continuar.

O helper novo executa a cópia offline e confere hashes e SQLite, sem importar a
aplicação. Depois de parar **todos** os escritores, no shell administrativo com
as variáveis reais exportadas:

```bash
umask 077
"$release/.venv/bin/python" -B "$release/deployment/aws/backup_existente.py" \
  --writers-stopped /var/backups/dashboardos "$previous" /etc/dashboardos/dashboardos.env
```

Ele preserva as duas pastas de dados completas, código anterior e ambiente em
diretório privado, com manifesto e marcador `COMPLETE`; não substitui arquivos
existentes. A `.venv` anterior permanece na release anterior e não é copiada.
Guardar o caminho impresso e conferir o Excel da cópia antes de prosseguir.

Ainda nesse shell, com as variáveis reais exportadas, executar o preflight como o
usuário da aplicação, a partir da nova release:

```bash
cd "$release"
sudo -u dashboardos --preserve-env=DASHBOARD_ENV,DASHBOARD_EXCEL_PATH,DASHBOARD_AUTH_DIRECTORY,DASHBOARD_ALLOWED_HOSTS,SECRET_KEY,DASHBOARD_EMAIL_SUSPENDED .venv/bin/python -B deployment/aws/preflight_existente.py
```

O preflight não importa `app`, não cria tabelas, não recupera diários nem envia
mensagens. Confere dados externos, estrutura empresarial/perfil, integridade,
colunas Excel, permissões, hosts, segredo e bloqueio de envio. Se faltar schema,
**não executar `migrar-contas`/`migrar-perfil` automaticamente**: manter release
anterior; uma migração precisa de análise, ensaio sobre cópia do banco do servidor,
backup e autorização específica. Não substituir o banco pelo local.

## 4. Troca controlada e verificação

Somente com preflight e backup aprovados, confirmar novamente que a unidade existente
aponta para `/opt/dashboardos/current` e usa a configuração Gunicorn relativa da release.

```bash
sudo ln -s "$release" /opt/dashboardos/current.2.1.3.next
sudo mv -Tf /opt/dashboardos/current.2.1.3.next /opt/dashboardos/current
sudo systemctl start dashboardos
sudo systemctl is-active dashboardos nginx
sudo journalctl -u dashboardos --since '-5 minutes' --no-pager
```

Não executar daemon-reload nem reinstalar unidades. Testar o socket existente com
`curl --fail --unix-socket /run/dashboardos/app.sock -H 'Host: DOMINIO_REAL' -H
'X-Forwarded-Proto: https' http://localhost/login` e o HTTPS público com
`curl --fail https://DOMINIO_REAL/login`. Fazer login com conta autorizada; abrir
perfil por nome e foto; consultar dashboard, quatro gráficos, filtros, temas,
funcionários/equipes/OS/acessos e verificar bloqueios de usuário/visitante.
Não gravar registros reais apenas para testar: usar cadastro fictício previamente
autorizado ou consultas. Confirmar versão 2.1.3 e ausência de erros no journal.
Verificar que as cinco mensagens históricas mantêm os mesmos IDs/status/valores
registrados antes da troca, por consulta somente leitura; não processar a fila.

## 5. Rollback

Se o preflight falhar, aponte nada: iniciar o serviço anterior após confirmar ausência
de escritores e causa resolvida. Se falhar após a troca, parar `dashboardos`, manter
escritores suspensos e apontar o link para `$previous`, de forma atômica como acima;
iniciar e verificar login/HTTPS/logs. Não retomar timers de e-mail no rollback.

Não restaurar banco/Excel automaticamente: esta atualização não migra dados e uma
restauração apagaria operações posteriores. Restaurar backup de dados exige decisão
separada, todos os escritores parados e revisão das alterações feitas após o backup.
Não voltar a uma versão que ignore contas bloqueadas/permissões do schema atual;
nesse caso manter aplicação parada até revisão. Preservar release e logs da falha.

Preservar sempre: dados do servidor e sua pasta completa, auth e avatares, chaves de
sessão, configuração com segredos, Nginx, TLS, unidades/drop-ins, backups e diários.
**Este roteiro foi preparado localmente; nenhuma operação na AWS foi executada.**
