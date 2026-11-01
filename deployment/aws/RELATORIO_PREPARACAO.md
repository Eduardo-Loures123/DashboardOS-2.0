# Relatório da preparação AWS

Preparação concluída localmente em 28/10/2026. Não houve implantação ou criação de recursos AWS.

## Arquivos criados

- services/production.py: configuração por ambiente, segredo obrigatório, dados externos ao código, hosts permitidos e proxy confiável.
- tests/test_production.py: testes isolados de configuração, HTTPS, permissões, persistência e backup.
- deployment/aws/gunicorn.conf.py: um worker, uma thread, socket Unix e logs.
- deployment/aws/nginx.conf: modelo de proxy para domínio real, com bootstrap para Certbot.
- deployment/aws/dashboardos.service: systemd com usuário dedicado e restrição de escrita.
- deployment/aws/dashboardos.env.example: ambiente sem credenciais reais.
- deployment/aws/requirements.txt: dependência Gunicorn somente no Linux.
- deployment/aws/install.sh: instalação Ubuntu; não cria recursos AWS.
- deployment/aws/deploy.sh: releases isoladas, verificação, dados preservados e retorno ao código anterior em falha.
- deployment/aws/update.sh: entrada para atualização.
- deployment/aws/backup.py e backup.sh: lock do Excel, API de backup SQLite, verificação e marcas de conclusão.
- deployment/aws/check.sh: verificação de serviço e login pelo socket.
- deployment/aws/DEPLOY_AWS.md: diagnóstico, comandos Windows/Ubuntu, HTTPS, custos, atualização e restauração.
- deployment/aws/RELATORIO_PREPARACAO.md: este relatório.

## Arquivos modificados

- app.py: integração da configuração, cookie Secure e HSTS em produção, hosts configuráveis, erros genéricos e recusa de inicialização direta em produção.
- .gitignore: exclusão de planilhas, bancos, chaves e certificados privados.
- README.md: link para o guia AWS.

Não foram editados templates, CSS, JavaScript, serviços de indicadores, cadastros ou Excel. Usuários não foram apagados. Os testes de escrita utilizaram cópias temporárias. Os testes existentes de geração trabalham em diretórios temporários e não regeneram a fonte original.

## Validações executadas

- `python scripts/testar.py`: 30 testes Python aprovados. Autenticação, CSRF, limitação de login, modo visitante, autorização de todas as escritas, CRUD, indicadores, filtros, rotas, exportação, arquivos estáticos, persistência, concorrência e backup.
- Dois testes de produção repetidos isoladamente após os ajustes finais: aprovados.
- `node --test --test-isolation=none tests/frontend.test.cjs`: 34 testes DOM/eventos aprovados, usando fixtures existentes. Não substituem inspeção visual de CSS ou renderização real de Plotly.
- `python -m compileall -q app.py services/production.py deployment/aws/backup.py tests/test_production.py`: concluído sem erros.

A primeira execução detectou a restrição antiga a localhost, corrigida antes da aprovação final. Outro teste detectou conexões SQLite de backup não fechadas explicitamente; elas agora usam contextlib.closing.

O comando padrão npm foi impedido pela política PowerShell; npm.cmd contornou essa entrada, mas o runner Node com subprocessos recebeu EPERM. O modo sem isolamento passou, sem modificar a política do computador. Bash local não conseguiu criar seu pipe de sinais (Win32 erro 5); WSL não está instalado. Assim, não foi possível validar a sintaxe dos scripts com Bash neste ambiente nem executar Nginx, systemd, Certbot ou Gunicorn Linux. As instruções e arquivos estão preparados para validação no Ubuntu; isso não equivale a uma implantação validada em EC2.

Nenhum teste destrutivo foi executado na planilha original. Nenhuma senha administrativa padrão ou chave AWS foi criada ou solicitada. A pasta não contém metadados Git, portanto não houve auditoria de histórico remoto.

Antes de liberar o acesso público, será necessário validar Linux, TLS real, permissões do socket, reinício, restauração e consumo de memória. A implantação permanece aguardando autorização do usuário.
