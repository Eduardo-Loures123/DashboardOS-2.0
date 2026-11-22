# Reformulação local do perfil, navegação e marca

Implementação iniciada em 04/11/2026 e concluída em 05/11/2026 (America/Sao_Paulo). Versão preservada: `2.1.2`. Sem deploy, alterações AWS ou envios reais de e-mail.

## Entrega por etapa

| Etapa | Resultado |
|---|---|
| 1 — Auditoria | Mapeados templates, scripts, autenticação, relações textuais, verificação antiga, notificações e dependências. Preservadas cópias antes das alterações. |
| 2 — Perfil visual | Cabeçalho com identidade real, iniciais/foto, função informativa, data somente quando disponível, quatro abas acessíveis e cartões claro/escuro. |
| 3 — Conta e foto | Modo somente leitura inicial, edição explícita, validação de mudanças, salvar/cancelar, proteção de rascunhos, disponibilidade de login e fotos com prévia/upload/substituição/remoção. |
| 4 — Segurança | Senha atual, nova senha e confirmação, mostrar/ocultar, validação de 12–256 caracteres, hashes existentes e revogação de sessões. |
| 5 — E-mail | Endereço pendente separado do atual, código com hash/validade/tentativas, cancelamento, confirmação transacional, unicidade de endereços verificados e preferência individual. Entrega continua desativada. |
| 6 — Atividades | Registro das operações CRUD concluídas, histórico individual, busca/filtros/paginação, expiração de 30 dias e manutenção local independente. |
| 7 — Sidebar | Navegação preservada, agrupamento de acompanhamento, estado persistido por usuário, marca no modo recolhido, menu móvel expansível e ajuda em diálogo local. |
| 8 — Identidade | Símbolo D vetorial azul/ciano adaptado da referência, wordmark, favicon, PNG de 512 pixels, metadados de atalho e login. Sem service worker ou cache offline. |
| 9 — Validação | Testes Python/frontend, ensaio da migração, aplicação local, comparação de dados e testes visuais/funcionais pelo Playwright em dados temporários. |

## Arquivos criados

- `services/profile_service.py`.
- `static/js/profile.js`.
- `static/css/profile-redesign.css`.
- `static/brand/dashboardos-symbol.svg`.
- `static/brand/dashboardos-icon.png`.
- `static/brand/manifest.webmanifest`.
- `scripts/limpar_atividades.py`.
- `scripts/preparar_limpeza_atividades.py`.
- `scripts/preview_profile_redesign.py` — somente demonstração temporária em loopback, sem banco principal.
- `tests/test_profile_redesign.py`.
- Este relatório.

## Arquivos existentes modificados

- `app.py`: atividades após operações concluídas e resposta JSON para limite de upload.
- `services/auth_service.py`: autenticação pelo login separado, identificação interna estável e dados de apresentação.
- `services/enterprise_service.py`: integração de esquema novo em bancos novos/migrações explícitas, compatibilidade administrativa e avisos gerais internos sem dados pessoais/free text.
- `services/enterprise_routes.py`: operações de perfil, foto, disponibilidade, e-mail pendente, atividades e comandos explícitos de migração/manutenção.
- `static/js/enterprise.js`: administração/central preservadas; perfil separado; apresentação do login atualizado.
- `static/js/sidebar.js`: preservação do estado desktop e menu móvel independente.
- `static/js/icons.js`: ícone de câmera no catálogo existente.
- `templates/base.html`, `templates/_brand.html`, `templates/login.html`.
- `requirements.txt`: Pillow `>=12,<13`; instalado no venv local como `12.3.0`.
- `scripts/testar_notificacoes.py`: nova suíte selecionável e suporte seguro a SQLite URI exclusivamente temporário.
- `tests/frontend.test.cjs`: adaptação ao perfil com abas, seletor de pesquisa da central mais específico e cinco novos testes de estado/rascunhos/preferências legadas.
- `tests/test_notification_pipeline.py`: expectativa da nova política de notificações gerais internas.

Não foram alterados o transporte SMTP, os módulos isolados `operational_events.py` e `notification_recipients.py`, a versão ou as configurações de produção. Alterações anteriores do usuário foram preservadas.

## Identidade e relações preservadas

`users.id` permanece a chave interna existente. Alterar o login pela API nova modifica exclusivamente `profile_logins.login`; não renomeia usuários, relações, históricos, permissões ou preferências do navegador.

O login é normalizado, validado e protegido por unicidade `COLLATE NOCASE`, adequada ao formato ASCII permitido. A disponibilidade na interface é uma prévia; o servidor confere novamente sob transação. A troca exige a senha atual e invalida sessões, solicitando novo login. Nomes internos antigos continuam reservados para evitar ambiguidade com relações legadas.

O perfil não permite alterar função/estado da conta. Administração e gravações operacionais continuam sob as permissões anteriores. A apresentação administrativa acompanha o login novo, mantendo os URLs internos associados à chave estável.

## Migração local executada

Banco:

`instance/auth.sqlite3` dentro deste projeto local.

Estruturas adicionadas:

| Estrutura | Finalidade |
|---|---|
| `profile_logins` | Login editável associado à identidade permanente |
| `profile_avatars` | Referência privada da imagem e revisão de apresentação |
| `profile_email_changes` | Novo endereço, hash do código, expiração, tentativas e criação |
| `profile_activities` | Autor interno, operação, módulo, código, resumo seguro, instante e identificador idempotente |

Foram adicionados índices de consulta e unicidade de endereços verificados. Não houve recriação do banco nem preenchimento de dados operacionais fictícios.

Procedimento:

1. Backup SQLite consistente pela API nativa e validação de integridade.
2. Migração e repetição idempotente em cópia isolada do banco original.
3. Comparação do conteúdo completo de todas as tabelas preexistentes, sem expor seus valores.
4. Aplicação aditiva ao banco local correto, por `ProfileService.migrate`, o mesmo procedimento do comando `migrar-perfil`.
5. Nova verificação de integridade, foreign keys, usuários/hashes e cinco pendências.

Backups:

- `diagnosticos/perfil-completo-20261104-215533/auth.original.backup.sqlite3`.
- `instance/auth.before-profile.1ad4d42c97403744.sqlite3` — backup imediatamente anterior à aplicação local.

Resultados em `migration-copy-validation.json` e `migration-local-result.json`, na pasta de evidências. Todas as linhas das tabelas anteriores permaneceram iguais na aplicação da migração. O arquivo do banco fica no mesmo caminho; seu hash físico muda por causa das estruturas adicionadas, não por substituição de dados.

Não houve atualização automática de esquema no startup de um banco existente. A preparação de bancos novos continua isolada; atualizações existentes são explícitas e possuem backup.

## Foto de perfil

Aceita JPG/PNG/WebP até 5 MB. Conteúdo é efetivamente decodificado, verificado, limitado a 20 milhões de pixels, sem animação, corrigido por orientação e recodificado em WebP de até 1024 pixels por lado, sem os metadados originais. Nomes internos são aleatórios e os arquivos ficam em `instance/avatars`, fora de `static`.

A rota autenticada serve apenas a imagem da própria conta. Troca e remoção não dependem do modo de edição das informações. A prévia ocorre antes do upload; cancelar não salva. As imagens anteriores são removidas após a atualização confirmada. Se o Windows impedir a exclusão de um arquivo antigo, a aplicação registra somente a classe da falha para revisão local, sem declarar que a nova foto falhou após já ter sido salva.

Sem imagem, reaparecem as iniciais. Cabeçalho superior e cartões de identidade/foto usam a mesma referência. O sidebar novo não possui um avatar separado; o acesso Meu perfil foi preservado.

## E-mail e notificações

O fluxo novo não substitui o endereço no momento da solicitação. O endereço anterior e seu estado de verificação ficam válidos até a confirmação transacional. Cancelamento, expiração ou falha não os alteram.

O código tem validade de 30 minutos, hash no armazenamento, no máximo cinco tentativas por solicitação, intervalo de um minuto entre pedidos e limite de cinco pedidos por hora. O código não aparece em respostas HTTP, auditoria ou histórico de atividades. Confirmações concorrentes do mesmo endereço são protegidas por índice único. Confirmar não ativa automaticamente a preferência de e-mail.

**Entrega intencionalmente não integrada:** o serviço prepara a solicitação e disponibiliza o código apenas ao chamador interno confiável. A rota atual não o entrega a SMTP/fila nem o exibe ao usuário. A mensagem na interface informa essa indisponibilidade. Na futura integração autorizada, será necessário gerar/entregar um código válido pelo adaptador e preparar também o aviso de segurança ao endereço antigo. Não é possível obter um código real pela interface antes dessa integração.

As cinco mensagens históricas não são reutilizadas, reservadas, canceladas ou processadas por esse fluxo novo.

Notificações operacionais gerais internas não obedecem ao opt-out legado: destinam-se às contas ativas. Os novos avisos gerais de vencimento excluem descrição livre, nomes e outros dados pessoais. Comunicados com destinatários explícitos e eventos restritos preservam seus limites. O checkbox de internas foi substituído pelo estado “Sempre ativas”.

E-mail é uma preferência separada, habilitável somente com endereço verificado. O texto informa o futuro resumo único às 09:00, America/Sao_Paulo. Os módulos das Etapas 3A/3B foram preservados; sua política anterior de funcionários/gestores não foi ativada automaticamente para essa regra nova. A integração operacional definitiva permanece posterior.

## Atividades e limpeza automática autorizada

Operações CRUD suportadas registram atividades somente após a gravação Excel ser concluída. As atividades incluem identidade interna estável e apenas resumos seguros, sem senhas, códigos, tokens, conteúdo completo ou monitoramento de navegação/login.

A API usa exclusivamente o usuário autenticado, ignora tentativas de selecionar outra conta e retorna 20 registros por página. Busca por código/descrição segura e filtros de cadastro/edição/exclusão são executados sobre dados persistidos. A tabela é separada da auditoria técnica legada.

Cada registro expira individualmente após 30 × 24 horas, armazenadas como instante UTC. A consulta exclui imediatamente itens expirados. A remoção física é feita pelo comando independente `scripts/limpar_atividades.py`, que não importa Flask, autenticação, SMTP ou processadores da fila. O padrão do comando é somente prévia; remoção exige `--execute`.

Após autorização explícita adicional do usuário, foi registrada e ativada a tarefa Windows:

**`DashboardOS-Atividades-30dias-LOCAL`**

- Intervalo: 15 minutos.
- Apenas o SQLite local identificado.
- Exclusão somente de `profile_activities` já expiradas.
- Sem senha armazenada; contexto interativo do usuário Windows.
- Execução com menor privilégio, sem janela de terminal.
- Primeira execução verificada: `LastTaskResult = 0`.

A tarefa funciona sem Flask e sem visitas ao perfil, enquanto o computador estiver ligado e o usuário Windows estiver conectado. A remoção física pode ocorrer na próxima execução de manutenção; a interface deixa de mostrar o item no instante de expiração. Não foi criado serviço de e-mail nem agendamento do resumo operacional.

A definição de referência `limpeza-atividades-DESABILITADA.xml` continua segura por padrão; a tarefa foi habilitada no registro somente após a autorização. A evidência do estado efetivo e dos argumentos executados está em `activity-task-result.json`.

## Testes executados

- Suíte completa: **174 testes Python aprovados**, incluindo **16 testes novos** de perfil.
- Regressão final do perfil: os mesmos 16 testes novamente aprovados, incluindo upload acima do limite e erro seguro de armazenamento.
- Frontend: **61 testes aprovados**, com cinco cenários novos de edição/rascunho/erro/e-mail pendente/preferência legada.
- Sintaxe de JavaScript e `git diff --check` sem erros.
- Migração na cópia real local, repetição idempotente e preservação de todas as tabelas anteriores aprovadas.
- Tarefa local de retenção registrada, habilitada e executada com código 0, sem processar e-mails.

Testes Python usam SMTP simulado e rede bloqueada, dados sintéticos e SQLite/Excel temporários. A atualização da expectativa de internas foi intencional, conforme a regra nova. A pesquisa da central foi restringida ao seu próprio campo no teste, pois o perfil agora também possui pesquisa de atividades.

### Playwright e inspeção visual

Servidor temporário em loopback, com dados inteiramente fictícios, separado do banco principal. Foram verificados:

- Quatro abas, somente leitura inicial e estado do botão Salvar.
- Alterar/restaurar/cancelar e confirmação de rascunhos.
- Formulário de senha e validação.
- Prévia, upload, três locais com imagem, persistência em nova sessão, remoção e iniciais.
- Preparação/cancelamento de e-mail com entrega desativada.
- Alteração do login, redirecionamento e autenticação com login novo em maiúsculas.
- Histórico com atividades fictícias, pesquisa/paginação e estado vazio nos testes DOM.
- Temas claro/escuro, menu móvel e rail recolhido com símbolo visível.
- Larguras 320, 390, 768, 1366 e 1536, sem rolagem horizontal da página.
- Todos os nove módulos navegados com HTTP 200; API administrativa continuou HTTP 403 para conta de teste com papel `admin`.
- Login local principal HTTP 200, marca nova visível e perfil sem autenticação HTTP 401, sem fazer login em conta real.

Imagens em `diagnosticos/perfil-completo-20261104-215533/`: `profile-light.png`, `profile-dark.png`, `profile-mobile-viewport.png` e `profile-collapsed.png`. Os nomes e atividades nessas capturas pertencem apenas ao ambiente de demonstração; não foram inseridos no principal.

## Preservação e limites

- Nenhum envio real, processamento da fila principal, deploy, acesso AWS ou publicação GitHub.
- Transporte SMTP e configurações de produção preservados.
- Cinco mensagens históricas continuam `pending`, com zero tentativas; conteúdo completo comparado com o backup.
- Excel real preservado por SHA-256; usuários, hashes, permissões e tabelas anteriores preservados na migração.
- Versão mantida em `2.1.2`, respeitando `VERSION` como fonte única.
- A aplicação local fica disponível em `http://127.0.0.1:5000`.

Excel e SQLite são armazenamentos distintos: se houver falha de armazenamento do histórico após salvar uma operação Excel, o sistema mantém a operação concluída e registra um erro técnico em vez de induzir uma repetição que poderia duplicar dados. O histórico do perfil não substitui uma auditoria transacional distribuída nem garante recuperação automática desse intervalo de falha.

A entrega de confirmações e os futuros resumos SMTP não foram ativados, conforme o limite do pedido. O manifest oferece identidade para atalhos compatíveis, sem prometer funcionamento offline.

## Evidências e reversão

Pasta: `diagnosticos/perfil-completo-20261104-215533/`.

Contém cópias `before/`, backup original consistente, manifests de hashes, resultados dos testes, migração ensaiada/aplicada, dados da tarefa local e evidências visuais. `preservation-final.json` registra a comparação final de conteúdo sem expor dados sensíveis.

Para uma reversão futura, desabilitar primeiro a tarefa local de retenção e parar o Flask. As cópias de código permitem comparação/restauração seletiva. Não restaurar cegamente um backup antigo do banco após usuários terem realizado novas operações: isso descartaria dados posteriores. As estruturas novas são aditivas e podem permanecer até um plano específico de reversão; logins alterados exigem preservar a camada de compatibilidade de autenticação. Nenhuma reversão destrutiva foi executada.
