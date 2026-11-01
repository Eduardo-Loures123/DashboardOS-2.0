# Preparação do pacote de transferência — 29/10/2026

Nenhum comando foi executado na AWS e nenhum arquivo foi enviado. Código e dados seguem separados. A configuração existente foi revisada para Ubuntu 24.04 LTS e o guia foi reescrito para o servidor que já tem Python e Nginx.

## Alterados nesta etapa

- requirements.txt: acrescentados Click explícito e Gunicorn condicionado ao Linux; bibliotecas anteriores preservadas.
- deployment/aws/requirements.txt: passa a incluir o requirements.txt principal, sem duplicar Gunicorn.
- services/production.py: DEBUG e TESTING explicitamente desativados ao configurar produção; corrigida a validação que rejeitava chaves aleatórias hexadecimais por não conterem todos os 16 dígitos possíveis.
- app.py: corrigida somente a codificação da mensagem que recusa execução direta em produção.
- deployment/aws/DEPLOY_AWS.md: transferência só do código, estratégia privada separada para dados, comandos Ubuntu/Windows, ambiente, permissões, HTTPS e operação.

- tests/test_production.py: regressão para aceitar segredo hexadecimal aleatório válido sem exigir todos os dígitos.

## Criados nesta etapa

- deployment/aws/.env.example: modelo sem segredo, compatível com o modelo dashboardos.env.example existente.
- deployment/aws/build_package.py: empacotamento por lista explícita e verificação do conteúdo byte a byte.
- deployment/aws/RELATORIO_TRANSFERENCIA.md: este relatório.
- ../DashboardOS_2.0_deploy.tar.gz: pacote de aplicação sem dados persistentes.
- ../DashboardOS_2.0_deploy.tar.gz.sha256: integridade do pacote.

Permaneceram sem alterações os templates, CSS, JavaScript, serviços de negócio, indicadores, filtros, animações e regras dos cadastros. A configuração Gunicorn, Nginx, systemd e os scripts de instalação, atualização e backup da preparação anterior continuam no pacote.

## Dados separados

Origem: dados/dados_dashboard.xlsx → /var/lib/dashboardos/excel/dados_dashboard.xlsx.
Origem: instance/auth.sqlite3 → /var/lib/dashboardos/auth/auth.sqlite3.

A planilha existente é a única fonte Excel necessária, mesmo se os dados forem fictícios. O SQLite é necessário para preservar os usuários. Nenhum desses arquivos está no pacote, nem foi copiado para um pacote privado nesta etapa. instance/session.key NÃO deve ser transferido: a produção usa SECRET_KEY do servidor; será necessário novo login. Backups e arquivos temporários também não acompanham a implantação.

## Testes executados

- python scripts/testar.py: 31 testes aprovados, com escritas em cópias temporárias; autenticação, visitante, permissões, CSRF, limitação de login, rotas, estáticos, CRUD, filtros, indicadores, exportação, concorrência, persistência e backup.
- node --test --test-isolation=none tests/frontend.test.cjs: 34 testes DOM/eventos aprovados, com fixtures existentes. Não constitui renderização visual real.
- bash -n: sintaxe dos cinco scripts shell validada com Git Bash local, sem executá-los.
- ast.parse: sintaxe Python dos arquivos de aplicação/configuração/empacotamento revisados validada.
- requirements.txt: sintaxe e seleção condicional de Gunicorn para Linux verificadas.
- Pacote extraído em diretório temporário: inicialização em configuração de produção, debug desativado, login, cookie Secure, visitante, oito páginas e APIs, estáticos e bloqueio de escrita aprovados. Excel de teste copiado e banco de teste independente.
- Conferência por SHA-256: Excel, SQLite e session.key originais preservados durante a conferência final.
- Empacotador: confere a lista de membros, ausência de dados/credenciais/temporários, nomes seguros e igualdade byte a byte com os arquivos selecionados.

Limitação: não houve execução de Gunicorn, Nginx, systemd, Python 3.12 ou TLS em Linux. A validação de execução no Ubuntu permanece para a implantação autorizada. O teste do pacote extraído é local no Windows, com dependências Python já instaladas, dados isolados e configuração de produção; não valida instalação de wheels Linux.

## Operação

Python: mínimo adotado 3.11, recomendado 3.12 no Ubuntu 24.04. Entrada WSGI app:app. Um worker sync, uma thread e socket Unix /run/dashboardos/app.sock. Gunicorn não expõe porta de rede. Produção exige SECRET_KEY e dados persistentes externos ao código; nenhum usuário padrão é criado.

As variáveis e os comandos exatos estão no DEPLOY_AWS.md. O pacote não contém .env real, banco de autenticação, planilha, session.key, .venv, node_modules, .git ou __pycache__.
