# DashboardOS 2.1.3 — preparação local para a EC2 existente

Estado: correção operacional preparada; **não publicada**. Nenhuma AWS acessada,
nenhum deploy, SMTP, migração real ou processamento da fila histórica executado.

## Projeto e proteção

Projeto correto: `Dashboard_New/DashboardOS_2.0`, não a cópia temporária do patch.
Entrada: `app.py`, factory `create_app`, WSGI `app:app`. Backend Flask; SQLite em
`instance/auth.sqlite3` e Excel `dados/dados_dashboard.xlsx` no desenvolvimento.
Em produção os caminhos são externos e definidos pelo ambiente existente.
Preservar também avatares, chave de sessão, backups, diários de importação e
configurações. Há alterações locais anteriores, preservadas sem reset/commit.

Backup privado anterior às correções:
`../backups_locais/preparacao_aws_20261109_192912/original_completo.zip`.
562 arquivos conferidos por SHA256, incluindo 19 persistentes. Manifesto, diff e
status anteriores estão ao lado. Esse backup contém dados/possíveis segredos:
**não publicar nem enviar como pacote de código**. A adaptação suspensa está em
`email_suspenso_NAO_PUBLICAR.zip`, no mesmo diretório, separada da release.

## Correções desta etapa

- Nome no cabeçalho agora abre `/perfil`, assim como a foto; foco por teclado e
  estilo preservados. Dados e gravação continuam usando os controles existentes.
- Envio e seleção da fila legada bloqueados por padrão, antes de conectar ao
  SQLite. Ausência/valor inválido de `DASHBOARD_EMAIL_SUSPENDED` mantém suspensão;
  somente o valor explícito `false` pode liberar a barreira, proibido nesta
  publicação. O CLI legado de alertas também para antes de observar o Excel.
  Não é uma implementação nova de notificações ou de isolamento por destinatário.
- Empacotamento inclui `VERSION` e os SVGs/imagens necessários ao estilo atual
  (o builder antigo os omitia). Exclui demonstração, adaptação de e-mail,
  componentes não integrados P1–P4, timers, instalador/deploy antigos, dados,
  segredos, caches, `.git` e ambientes locais. `operational_events.py` permanece
  apenas porque a visualização operacional de vencimentos usa suas constantes;
  isso não integra a cadeia experimental de envio.
- Preflight somente leitura e backup offline para atualização do servidor
  existente. O roteiro não reinstala unidades, Nginx ou HTTPS.

Arquivos alterados nesta etapa: `VERSION`, `CHANGELOG.md`, `templates/base.html`,
`static/css/sprint-layout.css`, `services/mail_service.py`,
`services/enterprise_routes.py`, `.env.example`, `deployment/aws/.env.example`,
`deployment/aws/dashboardos.env.example`, `deployment/aws/build_package.py`.
Criados: este relatório, `deployment/aws/ATUALIZAR_EXISTENTE.md`,
`deployment/aws/preflight_existente.py`, `deployment/aws/backup_existente.py`,
`scripts/testar_release_operacional.py`, `tests/test_release_operacional.py`.
Alterações anteriores do projeto foram mantidas; não atribuir todo o diff Git
a esta etapa.

## Validação direcionada

Em cópia temporária com Excel gerado e SQLite fictícios, guardas bloquearam rede,
SMTP e abertura dos dados originais. Primeiro lote: **39 testes backend passaram**,
cobrindo login/logout, sessão/CSRF, perfil/nome/avatar, troca de e-mail com prova de
identidade, persistência, CRUD das cinco tabelas, filtros, indicadores, produção,
backup e suspensão de envio. Frontend: **98/98 testes passaram**, com fixtures
geradas nessa cópia. Sem repetir a suíte completa ou os testes extensos do patch.
Conferência adicional: matriz administrativa/último superadministrador e preflight
somente leitura, incluindo rejeição de schema incompleto, passaram (2 testes). O helper novo de backup offline passou em outro teste
isolado, com hashes da origem preservados e manifesto da cópia conferido.
Total: **42 testes backend aprovados**, mais os 98 de frontend. `pip check`
confirmou ausência de conflitos nas dependências instaladas.

Teste adicional do pacote extraído: inicialização WSGI com configuração de produção
e dados fictícios, login, oito páginas, API de perfil/dashboard e todos os estáticos
aprovados, com SMTP e acesso aos dados originais bloqueados. Log:
`%TEMP%/dashboardos-package-smoke-ak1rv9ke/smoke.log`.
Conferência final dos hashes: os 19 arquivos persistentes são idênticos ao backup;
a cópia do banco anterior contém exatamente cinco mensagens `pending`, preservadas.

Logs do lote: `%TEMP%/dashboardos-release-operacional-dcp4i2mf/`.
O runner `scripts/testar_release_operacional.py` reproduz as verificações essenciais
em cópia fictícia; nunca rodar os testes de escrita diretamente com Excel real.
Suítes antigas que simulam envio precisam liberar explicitamente a nova suspensão
apenas dentro de mocks/ambiente isolado; não foram executadas nem usadas como
critério de aprovação desta versão sem e-mail.

Navegador real, servidor loopback e dados fictícios: perfil aberto por nome/foto,
nome alterado e preservado após reload, quatro gráficos carregados, filtro por
equipe aplicado à resposta real da API. Inspeção dos temas claro/escuro e telas
1440×900 e 390×844 sem transbordamento horizontal nos cenários observados.
Oito ciclos entre abas do perfil e janela ociosa sem requisições contínuas.
Nenhuma exceção JavaScript observada; o Chrome apenas sugeriu campo username em
formulários de senha. Não houve ensaio prolongado de memória/carga.
**O travamento relatado não foi reproduzido.** Evidências PNG estão na pasta pai,
fora do pacote de publicação.

## Pronto para apresentar e limites

Login/logout, perfil/nome/avatar, aparência, dashboard/gráficos/filtros, funcionários,
equipes, OS, acessos, vencimentos/urgências e regras administrativas foram cobertos
pelas verificações acima. Não houve necessidade de reformulação visual.

A troca de e-mail mantém confirmação de identidade: a solicitação fica pendente e
o endereço atual continua válido. Com envio suspenso, **a confirmação não pode ser
concluída pela interface**; não se entrega o código ao navegador nem se marca o
novo endereço como verificado. Recuperação administrativa existente preservada.

Não foi possível verificar o schema, os dados, a unidade, a versão Python ou a
capacidade da EC2 sem acesso ao servidor. Gunicorn/Linux/HTTPS reais ainda exigem
homologação no ambiente existente. O preflight deve bloquear a publicação caso
faltem tabelas/colunas/índice de perfil, permissões ou configuração. Nenhuma
migração automática foi preparada como atalho. Eventual migração exige ensaio
sobre cópia do banco do servidor e autorização específica.

Processos antigos de envio já ativos devem ser identificados e parados na janela
autorizada: não recebem a barreira nova enquanto usam código antigo. Não ativar
timers nem reprocessar as cinco mensagens históricas. O mecanismo interno de
notificações já operacional não foi reescrito; o patch de alertas está suspenso.

## Entrega e atualização

Pacote somente código: `../DashboardOS_2.0_2.1.3_codigo.tar.gz` e `.sha256`.
Comandos de transferência/conferência, backup, preflight, troca atômica, smoke
test e rollback: [ATUALIZAR_EXISTENTE.md](deployment/aws/ATUALIZAR_EXISTENTE.md).
O pacote não transporta usuários, senhas, permissões, SQLite, Excel ou segredos.
Não restaurar dados automaticamente no rollback; preservar operações posteriores.

**Pronta para homologação e atualização controlada após autorização e preflight
do servidor. Não é aprovação incondicional de produção: os bloqueios de schema,
configuração e processos antigos devem ser descartados na EC2 antes da troca.**
