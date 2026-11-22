# DashboardOS — Demonstração integrada de notificações P5-A

Implementação local em 09/11/2026. Escopo autorizado: A1–A6, exclusivamente fictício e isolado. Não é ativação de produção e não inicia P5-B, P6 ou P7.

## Iniciar para a entrevista

Abra um terminal na pasta `DashboardOS_2.0` e execute:

```powershell
.\.venv\Scripts\python.exe -B scripts/demonstrar_notificacoes.py
```

Abra **http://127.0.0.1:5095**. Se necessário, escolha outra porta com `--port 5096`.

- Conta administrativa fictícia: **root**.
- Senha de todas as contas fictícias: **Demo-Notificacoes-2026!** (já preenchida na tela de entrada).
- Cada execução sem `--retomar` cria uma demonstração nova em `%TEMP%\dashboardos-p5a-*`, às 08:55 do dia local em `America/Sao_Paulo`.
- Nenhum agendamento roda. Relógio, composição e entrega dependem de cliques explícitos.
- Encerre com **Ctrl+C**. Os arquivos temporários são preservados para permitir retomada, não apagados automaticamente.
- O terminal informa o caminho exato. Para retomar o mesmo estado, execute:

```powershell
.\.venv\Scripts\python.exe -B scripts/demonstrar_notificacoes.py --retomar "C:\Users\SEU_USUARIO\AppData\Local\Temp\dashboardos-p5a-CAMINHO_INFORMADO"
```

Não use `python app.py` para esta demonstração. Não use os comandos operacionais `processar-alertas` ou `processar-emails`.

## Roteiro de apresentação — aproximadamente 4 minutos

1. Entre como **root**. Mostre a faixa **AMBIENTE DE DEMONSTRAÇÃO**, relógio às 08:55, zero eventos e cinco mensagens legadas fictícias preservadas.
2. Em **Operação coordenada**, selecione **Em andamento** e confirme a alteração da OS001. Confira **1 operação confirmada**, **1 evento persistente** e o aviso na Central.
3. Clique **Repetir última operação**. Os números continuam em 1: a mesma identificação retorna o mesmo resultado sem reaplicar a alteração.
4. Clique **Simular 09:00 → Preparar resumo → Simular entrega**. Três resumos são elegíveis: root, alice e somente-email. A caixa da conta conectada mostra uma entrega **SIMULADA**. Repita preparação e entrega: nenhuma duplicação.
5. Use **Trocar conta** para entrar como **alice**: ela tem aviso interno e resumo. Como **bob**, de outra equipe: nenhum detalhe restrito. Como **somente-email**: há resumo, mas nenhuma notificação interna. Permissão de e-mail não foi convertida em permissão interna.
6. Volte como **root**. Clique **Próximo dia · 08:55**. A REN001, inicialmente com 6 dias, produz o lembrete dos **7 dias**. Clique **Recuperação · 11:30 → Preparar resumo**.
7. No cartão de **alice**, clique **Revogar** antes de entregar. **Simular entrega** registra somente duas entregas novas. Como alice, o novo resumo aparece cancelado e os detalhes internos deixam de estar disponíveis. Conteúdo histórico restrito também é ocultado na leitura.
8. Opcional: pare e retome o mesmo diretório. Relógio, recibos, eventos e entregas continuam persistidos. **Retomar / conferir provas** reprocessa solicitações pendentes sob as mesmas validações, sem inventar uma nova operação.

Para repetir o ensaio desde o início, encerre e execute novamente **sem** `--retomar`. Restrições são deliberadamente irreversíveis pela interface; reiniciar uma demonstração nova é a forma de restaurar as contas fictícias.

## Arquivos criados

| Arquivo | Responsabilidade |
| --- | --- |
| `services/demo_guard.py` | Guard do processo: bloqueia dados reais, credenciais, saída de rede, SMTP, processos filhos e escrita fora da demonstração. |
| `services/demo_notifications.py` | Inicialização fictícia, coordenação P1–P4, inbox durável, projeções 3A/3B/3C.2A, relógio, restrições, composição e transporte simulado. |
| `services/demo_web.py` | Aplicação Flask independente, autenticação fictícia, sessão separada, CSRF, autorização de administração e APIs exclusivas `/demo/api/*`. |
| `scripts/demonstrar_notificacoes.py` | Entrada isolada; não importa `app.py`. Somente HTTP local em `127.0.0.1`. |
| `scripts/testar_demonstracao_notificacoes.py` | Testes de integração P5-A com rede e dados reais bloqueados. |
| `scripts/verificar_isolamento_demo.py` | Exercita o guard real, incluindo tentativas bloqueadas de leitura do banco/Excel operacional. |
| `scripts/testar_regressao_p5a.py` | Copia somente código para diretório temporário, gera planilha fictícia e executa regressões operacionais e DOM fora dos dados reais. |
| `templates/demo_notifications.html` | Interface exclusiva da demonstração, sem inclusão nas rotas operacionais. |
| `static/css/demo-notifications.css` | Estilo empresarial escuro e responsivo, restrito à tela nova. |
| `static/js/demo-notifications.js` | Interações manuais sem polling, timers, bibliotecas externas ou endpoints operacionais. |
| `tests/test_demo_notifications.py` | Integração, falhas, retomada, segurança de conteúdo, concorrência e legado fictício. |
| `tests/demo_notifications.browser.cjs` | Ensaio Playwright reproduzível contra uma demonstração nova na porta 5095. |
| `DEMONSTRACAO_NOTIFICACOES_P5A.md` | Este relatório e roteiro. |

Os arquivos preexistentes de aplicação, autenticação, scanner, outbox, importação e P1–P4 não foram editados. Mudanças anteriores já presentes no workspace não pertencem à P5-A. `VERSION` continua sendo a única fonte da versão exibida, sem incremento: esta entrega é uma demonstração separada, não uma release operacional.

## Funcionamento e consistência

### A1 — Isolamento

O launcher cria uma raiz temporária própria antes de importar serviços. Não usa caminhos operacionais de variáveis de ambiente, não abre o banco de autenticação real e não importa a aplicação operacional global. A inicialização das tabelas e concessões ocorre somente sobre o SQLite fictício novo.

O guard restringe também os arquivos temporários internos de openpyxl. Bibliotecas e assets locais podem ser lidos; banco/Excel em `instance`/`dados`, `.env`, `.aws` e credenciais AWS são bloqueados. SQLite só pode abrir arquivos dentro da demonstração. Conexões de saída, DNS externo, SMTP, processos filhos e bind fora do HTTP local autorizado são recusados. O navegador acessa apenas o servidor local e assets locais; essa entrada HTTP é a exceção necessária à apresentação. Não há acesso AWS.

As credenciais públicas são exclusivamente fictícias. Há login por senha, sessão assinada com chave temporária persistida, cookie próprio HttpOnly/SameSite, expiração, CSRF, validação de Host, limite de requisição e limitação de tentativas de login. Contas não administrativas não podem alterar OS, relógio, permissões ou executar entregas.

### A2 e A3 — Coordenação, eventos e retomada

Reutiliza `SyntheticWorkbookStore`, `IdentityExcelCoordinator`, `IdentityOperationJournal`, planejador P1, `TemporaryFileAnchorProvider`, testemunho P3 e classificador P4. Antes da operação, reutiliza a validação de negócio de `ExcelService.validate`. O callback de autorização permite somente a edição fictícia da OS001 pelo superadministrador root.

Antes de chamar P4, persiste em `demo_requests` a identificação da operação, inventário proposto e instante controlado. P4 confirma os artefatos/recibos; depois o detector 3A produz eventos. Snapshot 3A, eventos, destinatários, avisos e marca de progresso são gravados em uma transação SQLite da projeção. A preparação das decisões acontece antes da escrita, respeitando as transações próprias do repositório existente.

Se houver falha entre o commit P4 e a projeção, a solicitação permanece pendente. Na retomada, reapresenta a mesma requisição a P4; recibos impedem reaplicação. Falha durante a projeção reverte snapshot, eventos e progresso juntos. Uma nova identificação com conteúdo repetido não inventa uma transição inexistente. Mesma identificação com conteúdo diferente é recusada.

O primeiro snapshot é baseline: zero eventos retroativos. A referência não é reinicializada silenciosamente na retomada. Uma divergência no arquivo, testemunho, checkpoint ou cadeia bloqueia o fluxo.

### A4 — Autorização por canal

Há duas equipes e contas inteiramente fictícias. Concessões de e-mail são criadas pelo repositório 3C.2A, aprovadas explicitamente por root e ancoradas na baseline. A política 3C.1 revalida os escopos, identidade durável, conta ativa, endereço sintaticamente válido, verificação e consentimento. A conta bob possui concessões apenas para T2; os registros apresentados pertencem à T1.

Permissões internas ficam em uma tabela própria da demonstração e são avaliadas com o resolver 3B, vinculadas a módulo, registro, equipe e geração. Não são deduzidas de concessões de e-mail. Root e alice têm concessões internas explícitas; somente-email não tem. A Central revalida o conteúdo em toda leitura. A caixa simulada também oculta detalhes históricos cujo acesso vigente não passa na revalidação; as evidências persistidas não são adulteradas.

**Revogação demonstrativa:** o repositório atual avança o checkpoint administrativo ao revogar uma concessão; P3 ainda não publica essa mudança administrativa isolada. Para não contornar esse controle, os grants iniciais permanecem ancorados e a demonstração registra uma restrição adicional em `demo_denials`, auditada e persistente, aplicada em ambos os canais. Essa restrição só retira acesso e não concede nem restaura permissões. Não representa implementação da publicação administrativa de revogações em produção.

### A5 — Resumo e entrega simulada

O relógio persistido usa `America/Sao_Paulo`, aceita somente avanços e não depende de timers. O compositor trabalha com eventos pós-baseline ainda vigentes, representando mudanças e a situação atual desses registros. Não produz uma fotografia retroativa de todas as pendências preexistentes ao corte de ativação.

A preparação é permitida entre **09:00 e 12:00 inclusive** do dia controlado. A identidade única é conta/dia nesta instância da demonstração. Resumos vazios não são criados; tentativas repetidas não criam outra linha. A composição captura uma lista de itens/destinatários previamente admitidos: a entrega pode retirar itens, nunca acrescentar destinatários ou eventos de surpresa.

Antes da entrega, recarrega política, identidade, preferências e snapshot; retira eventos superados e bloqueia revogação, opt-out ou perda de verificação. Resumos do dia anterior ou fora da janela são cancelados no fluxo novo. Um resumo cancelado ocupa sua chave diária; não se cria um segundo resumo naquele mesmo dia. Eventos posteriores ao corte permanecem para avaliação no próximo dia.

O transporte simulado **é uma inserção em `demo_deliveries`**. Não há callback configurável, SMTP ou fallback de rede. Registro de entrega e estado `simulated` são atômicos na mesma transação; uma falha antes do commit permite repetir sem efeito duplicado. Essa garantia vale para o transporte local fictício, não para aceitação SMTP real.

O detector 3A já fornece o lembrete único de renovação a partir de 7 dias, respeitando estado ativo e snapshot persistido. O cenário começa com 6 dias para que o avanço manual demonstre a transição. Em resumos de dias posteriores, um registro ainda aberto aparece como **Pendência atual**, sem repetir o alerta de sete dias ou uma mudança antiga como se fossem novos. Eventos encerrados de dias anteriores não viram pendências atuais.

### Legado

São inseridas cinco mensagens **fictícias** na outbox legada do banco temporário, todas `pending` e com zero tentativas. Nenhuma seleção, atualização ou transporte novo consulta essa outbox para entrega. Ela é lida somente para apresentar as evidências administrativas e verificar preservação nos testes.

As cinco mensagens históricas **reais** continuam fora do alcance do processo demo. Esta entrega não modifica ou protege contra uma execução futura deliberada do processador operacional antigo por outro processo: antes da ativação real será necessário bloquear essa entrada legada explicitamente.

## Validação

Comandos seguros para repetir:

```powershell
.\.venv\Scripts\python.exe -B scripts/testar_demonstracao_notificacoes.py
.\.venv\Scripts\python.exe -B scripts/verificar_isolamento_demo.py
.\.venv\Scripts\python.exe -B scripts/testar_regressao_p5a.py
.\.venv\Scripts\python.exe -B scripts/testar_planejador_identidades.py
.\.venv\Scripts\python.exe -B scripts/testar_diario_identidades.py
.\.venv\Scripts\python.exe -B scripts/testar_continuidade_identidades.py
.\.venv\Scripts\python.exe -B scripts/testar_coordenador_excel_identidades.py
```

O executor de regressão imprime o diretório temporário com `operational.log`, `fixtures.log`, `frontend.log` e `result.json`. Não usa o banco ou a planilha principal para alimentar testes. O preparo frontend é executado na cópia, não nos fixtures do projeto. Os testes puros continuam em processos separados para respeitar seus contratos de isolamento.

### Resultados finais

| Verificação | Resultado |
| --- | --- |
| Integração P5-A | **23 testes aprovados**. Inclui fluxo completo, baseline sem retroativos, chave idempotente conflitante, consentimento/verificação, canais separados, equipe incorreta, revogação, ocultação de histórico restrito, supersessão, janela até 12:00, lembrete único e pendência nos dias posteriores. |
| Falhas e concorrência P5-A | Incluídas nos 23: falha após `os.replace`, após commit P4, antes do commit da projeção, antes do commit da entrega; reinício; operação/composição/entrega concorrentes e repetidas. |
| Guard efetivo do processo | **5 testes aprovados**: leitura real/credenciais, conexão SQLite externa/URI, rede/DNS/bind, escrita/processos e banco temporário permitido. |
| Dashboard operacional em cópia fictícia | **131 testes aprovados**; nenhum teste alimentado por dados principais. |
| Fixtures + frontend existente | Preparo aprovado na cópia; **98 testes Node/jsdom aprovados**. |
| 3A–3C.2A, eventos/destinatários/persistência | **163 testes aprovados** no executor restrito existente. |
| P1 / P2 / P3 / P4 | Respectivamente **55 / 58 / 71 / 65 testes aprovados** em seus executores isolados. |
| Sintaxe | Python novo validado por AST; JavaScript da demonstração e roteiro Playwright validados por `node --check`. |
| Navegador real | Ensaio completo aprovado: operação → evento → Central → 09:00 → resumo → simulação → repetição → 7 dias → revogação; sem exceções JavaScript e sem falhas de rede inesperadas. |
| Layout | Conferido em **1920×1080, 1366×768 e 390×844**, sem rolagem horizontal. Inspeção visual real adicional em 1366×900 e 390×844, com marca oficial carregada. |
| Reinício real do servidor | Processo encerrado e reaberto com `--retomar`: **1 operação, 2 eventos, relógio 10/11/2026 às 11:30, recuperação `consistent`**, cinco legados fictícios `pending`/zero tentativas; conteúdo histórico da conta revogada ocultado. |
| Dados protegidos reais | **19 arquivos com caminhos e hashes SHA-256 preservados**, incluindo banco principal, backups e planilhas. O banco real não foi aberto para alimentar os testes. |

Os números dos executores incluem seus testes de guard; não representam contagem de testes únicos somada entre suítes. Algumas regressões SMTP registram falhas deliberadamente simuladas durante testes que passam; nenhuma conexão real é permitida.

Artefatos da execução operacional/DOM final: `%TEMP%\dashboardos-p5a-regression-702525iq\`, com `result.json` indicando três etapas aprovadas e `protected_unchanged=true`. Integração P5-A: `%TEMP%\p5a-final-integration-verified.log`. Regressões de componentes: `%TEMP%\p5a-regression-P1.log` até `P4.log`, e `p5a-regression-recipients.log`.

Capturas da interface final: [desktop](../artifacts/p5a-notificacoes-desktop-20261109.png) e [celular](../artifacts/p5a-notificacoes-mobile-20261109.png). São dados inteiramente fictícios. A inspeção visual é amostral, não homologação de todos os navegadores e resoluções.

## Limitações e pendências para produção

- Aplicação e rotas independentes: não existe ativação automática no dashboard operacional.
- Edição demonstrada: somente status da OS001; não há CRUD/importação geral P5-A. A validação de conclusão reutiliza o limite de data real do validador existente; a simulação temporal de resumo/lembrete não altera esse limite.
- Permissões e verificações iniciais são fixtures explícitas. Não há administração geral de concessões nem confirmação real de caixa postal.
- Resumo baseado em eventos pós-corte; ampliar para todas as pendências atuais exige regra de ativação e projeção próprias.
- Âncora e testemunho são locais/simulados. Restaurar todo o diretório pode ocultar rollback conjunto; não há domínio independente de confiança.
- Exclusão é cooperativa por arquivos de lock. Lock abandonado bloqueia o uso: não se apaga automaticamente nem se presume commit. Interrupções testadas por exceções/hooks e reinício de instâncias não provam resistência a corte de energia.
- Windows não fornece neste código a mesma sincronização de diretório de plataformas com `O_DIRECTORY`. Não se promete atomicidade conjunta Excel–SQLite–âncora.
- A entrega simulada é transacional; SMTP real permanece sujeito a resultados incertos e exige protocolo de tentativas/revisão sem promessa de exatamente uma entrega.
- Para produção: integrar e controlar todos os escritores, reconciliar o recuperador de importação existente com P4, homologar formato Excel e retenção de provas, implementar âncora independente/testemunho, publicação administrativa, migração autorizada, fila nova com exclusão explícita do legado, compositor completo e ativação separada de transporte/agendamento.

Não houve envio real, ativação de worker/timer, migração principal, edição de configurações operacionais, AWS, deploy, commit, push ou tag.
