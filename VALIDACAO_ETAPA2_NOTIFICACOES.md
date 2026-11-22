# Etapa 2 — Validação isolada de eventos e fila de e-mails

Data: 04/11/2026 (America/Sao_Paulo).

## Escopo e arquivos

Foram analisados:

- `services/enterprise_service.py`: `schema`, `scan`, `emit`, `token`, `update_profile` e leitura das notificações.
- `services/mail_service.py`: `SMTPTransportError`, `smtp_send` e `process_outbox`.
- `services/enterprise_routes.py`: `register`, observador da planilha, `processar-alertas` e `processar-emails`.
- `services/dashboard_service.py`: `categoria` e `enrich`.
- `services/excel_service.py`: `mutate`, lock, observação antes/depois da gravação e recuperação de falhas.
- `services/auth_service.py`, `services/production.py` e `app.py`: transações, seleção do banco e inicialização do Flask.
- `services/schema.py`, testes empresariais/SMTP existentes e executores de testes.

Arquivos adicionados nesta etapa:

1. `tests/test_notification_pipeline.py`: 26 testes, com SQLite novo e Excel fictício em cada cenário.
2. `scripts/testar_notificacoes.py`: executor isolado, com bloqueio de rede e de SQLite fora da pasta temporária do sistema.
3. Este relatório.

Arquivo existente modificado: `tests/frontend.test.cjs`, somente duas regressões do eixo Y. Elas usavam o limite fixo `44` do Excel anterior. Com dados sintéticos o limite correto passou a `38,5`: os testes agora verificam cobertura dos valores e estabilidade durante hover, e mantêm a expectativa `44` em uma série sintética explícita com máximo `40`. Nenhum código visual foi alterado.

Nenhum componente da aplicação foi alterado nesta etapa. As correções SMTP da Etapa 1 foram preservadas. Não foi necessário corrigir o código de produção para aprovar os cenários de confiabilidade testados. Os testes que descrevem lacunas de negócio afirmam o comportamento atual; sua aprovação não significa que essas lacunas foram resolvidas.

## Isolamento e reversão

Evidências e cópias anteriores à etapa: `diagnosticos/etapa2-notificacoes-20261104-165922/`.

- `before/` preserva os serviços e testes existentes analisados antes das inclusões.
- `baseline.json` registra hashes iniciais e somente IDs/estados/números de tentativas das cinco pendências, sem conteúdo de mensagem.
- `preservation.json` registra a conferência final.
- `python-tests.txt` e `frontend-tests.txt` contêm os resultados das suítes.
- `node-no-network.cjs` bloqueia conexões de rede nos testes Node.

Os testes novos criam todos os registros do zero, com endereços `example.test` e usuários fictícios. Nenhum banco principal é copiado ou importado. O executor também substitui, em memória, a origem da cópia de Excel usada pelos testes antigos por uma planilha sintética recém-gerada com `scripts/gerar_dados.py`. Assim, a regressão completa não importa OS, acessos ou funcionários reais.

A inicialização global de `app.py` é direcionada a um banco temporário vazio antes da importação. As variáveis usadas para isolamento existem apenas no processo de testes e são restauradas no encerramento. Não há leitura/exibição de credenciais SMTP reais. Os testes SMTP usam credenciais fictícias e objetos simulados. Hooks bloqueiam resolução DNS, conexão de socket e envio SMTP real; conexões SQLite fora da pasta temporária são recusadas. Cada banco dos 26 cenários passa por `integrity_check` e `foreign_key_check` ao final.

Para reverter esta etapa basta remover os três arquivos novos listados acima e restaurar `tests/frontend.test.cjs` de `before/tests/frontend.test.cjs`. Os serviços existentes não precisam ser restaurados, pois não foram modificados. As cópias `before/` ficam disponíveis para comparação; não restaurar bancos nem desfazer alterações anteriores do usuário.

## Eventos operacionais observados

O scanner compara `status`, data de vencimento (`due`) e faixa (`band`) com o snapshot anterior. Cada campo alterado produz um evento próprio, com chave formada por planilha, código, versão da transição e campo. Há unicidade por chave de evento e por evento/usuário na fila e nas notificações.

| Cenário fictício | Resultado atual verificado |
|---|---|
| Primeira leitura de OS/acessos a 45 dias, 30 dias, hoje ou já vencidos | Apenas snapshot; zero eventos e zero mensagens, mesmo havendo usuário elegível. |
| Data fixa: passagem de 46 para 45 dias | Um evento de faixa por registro; título com `31 a 45 dias`. |
| Data fixa: passagem para 30 dias | Um evento de faixa por registro; título com `Até 30 dias`. |
| Data fixa: vencimento hoje | Um evento de faixa por registro; título com `Vencem hoje`. |
| Data fixa: dia seguinte ao vencimento | Um evento de faixa por registro; título com `Vencidos`. |
| Permanência na faixa vencida | Nenhum novo evento apenas pelo passar do tempo dentro da mesma faixa. |
| Alteração de data de 46 para 45 dias, sem avanço do relógio | Dois eventos: `due` e `band`; duas mensagens por usuário elegível. |
| OS: mudança simultânea de status, data e faixa | Três eventos distintos e três mensagens por usuário elegível. Não são duplicatas de uma mesma chave. |
| Acesso: revogação | Dois eventos quando mudam `status` e `band` para encerrado. |
| OS concluída e acesso revogado, com avanço de tempo | Não cruzam faixas de vencimento enquanto encerrados. |
| Mudança de data em OS concluída | Ainda produz evento de data; não existe supressão geral de mudanças de registros encerrados. |
| Status A → B → A → B | Cada transição ganha versão nova, sem colisão com eventos antigos. |
| Remoção e recriação do mesmo código | Tombstone preserva versão; não reutiliza chaves antigas. A remoção em si não produz evento. |
| Mudança de solicitação/status de renovação | Não gera evento operacional; `scan` observa somente OS e acessos. |
| Repetição da leitura ou reconstrução de `EnterpriseService` | Não gera novamente eventos da mesma transição. |
| Dois scanners simultâneos | Um emite a transição; o outro emite zero, sem duplicação. |
| Mutação pelo serviço Excel | Observador gera a transição sem depender de abrir o dashboard. |
| Falha no observador após salvar o Excel | Alteração permanece salva; uma varredura posterior reconcilia a transição uma vez. |

Na sequência temporal dos quatro limiares, uma OS e um acesso produziram exatamente oito eventos, oito notificações internas e oito mensagens pendentes para uma conta elegível. Nenhum envio é feito por `scan` ou `emit`.

## Fila, transações e SMTP simulado

| Verificação | Resultado |
|---|---|
| Criação da fila | `pending`, `attempts=0`, sem tentativa SMTP. |
| Falha na inserção da fila durante emissão | Evento e notificação interna também sofrem rollback; repetição posterior cria uma única emissão. |
| Reserva antes do remetente | `BEGIN IMMEDIATE` confirma `sending`, incremento da tentativa e `mail_attempts.result='sending'` antes de chamar o transporte. |
| Falha ao inserir a tentativa | Reserva e incremento sofrem rollback; mensagem continua `pending`, zero tentativas e remetente não chamado. |
| Limite de processamento | `limit=1` processa somente uma das três mensagens fictícias. |
| Dois processadores concorrentes | Quatro mensagens fictícias aceitas uma vez cada, uma tentativa por linha. |
| Falha de conexão antes da transmissão | Volta a `pending` com atraso; chamada antes do prazo não tenta enviar; após liberar o prazo no banco de teste a nova tentativa pode ser aceita. |
| Rejeição explícita SMTP 451 | Usa espera entre tentativas; após três tentativas passa a `failed`, sem nova tentativa automática. |
| Autenticação rejeitada 535 / destinatário rejeitado 550 | `failed` após uma tentativa; detalhes privados do provedor não são persistidos. |
| Desconexão durante transmissão | `uncertain`, uma tentativa; reinicialização não reenvia. |
| Interrupção após reserva e antes da confirmação | Linha e tentativa permanecem `sending`; reinicialização ignora essa linha e processa outras pendentes. |
| SMTP aceita, mas o banco falha antes de salvar `sent` | Continua `sending`; reinicialização não reenvia. A confirmação local exige revisão, pois não há transação distribuída com SMTP. |
| SMTP aceita, mas QUIT retorna erro | Permanece `sent`; reinicialização não reenvia. Correção da Etapa 1 preservada. |

Os estados `sent`, `failed`, `uncertain` e `sending` não são selecionados automaticamente para reenvio. Não existe garantia de entrega exatamente uma vez pelo protocolo SMTP; a política atual prefere interromper a automação quando há incerteza.

## Preferências e elegibilidade

- Na criação do evento, apenas contas ativas, com e-mail não vazio, verificado e preferência de e-mail habilitada recebem uma linha de alerta operacional na fila.
- Contas inativas/bloqueadas, sem endereço, sem verificação ou sem preferência de e-mail não recebem esse alerta. Desativar notificações internas não impede o e-mail quando o usuário é elegível para esse canal.
- Antes da reserva, a fila revalida endereço, verificação e preferência. Endereço alterado/removido, verificação revogada ou preferência desabilitada cancelam o alerta sem tentativa SMTP.
- Contas que ficam inativas/bloqueadas são ignoradas pelo seletor; suas linhas permanecem pendentes com zero tentativas. Ao reativar, podem receber mensagens antigas que ainda forem elegíveis. Não há prazo de validade específico para alertas operacionais.
- Se o usuário se torna elegível somente depois de um evento, repetir o mesmo evento não cria uma mensagem retroativa. O próximo evento novo pode gerar mensagem normalmente.
- Confirmação de endereço é um fluxo separado: uma solicitação válida pode enviar a confirmação com `verified=0` e `email_alerts=0`. Isso não é envio indevido de alerta operacional.
- Existe uma janela entre reserva e transmissão: a preferência é conferida ao reservar, mas uma alteração feita durante a conexão SMTP não é revalidada pelo transporte. O teste simula desativação durante o login e confirma que a mensagem em andamento ainda é aceita. Não foi introduzido bloqueio de transações durante a rede nem nova política de cancelamento nesta etapa.
- O evento operacional é distribuído a todas as contas elegíveis; `scan` não filtra responsáveis/equipes. Uma regra de destinatários por vínculo precisaria de aprovação de negócio.

## Execução e resultados

No PowerShell, dentro de `DashboardOS_2.0`:

```powershell
# Somente pipeline e regressões SMTP da Etapa 1, sem rede:
.\.venv\Scripts\python.exe -B scripts\testar_notificacoes.py

# Suíte Python completa, executando scripts/testar.py sob isolamento:
.\.venv\Scripts\python.exe -B scripts\testar_notificacoes.py --completo

# Fixtures DOM isoladas, executando scripts/preparar_testes_frontend.py:
.\.venv\Scripts\python.exe -B scripts\testar_notificacoes.py --frontend-fixtures

# Regressão DOM com bloqueio adicional de rede:
node --require ./diagnosticos/etapa2-notificacoes-20261104-165922/node-no-network.cjs --test --test-isolation=none tests/frontend.test.cjs
```

Os resultados finais e a verificação de preservação estão registrados nas evidências desta etapa. Os testes DOM são regressões funcionais, sem homologação visual e sem alteração de interface.

A suíte Python completa passou com **85 testes**, incluindo os **26 novos cenários**. Uma rodada inicial com 31 testes de pipeline/SMTP também passou antes da ampliação final. A primeira rodada DOM teve 54 aprovações e as duas falhas de expectativa fixa descritas acima, motivando somente a correção dos testes.

A repetição final aprovou **56 de 56 testes frontend**, sem falhas. `git diff --check` não encontrou erros de whitespace. A conferência final confirmou hashes idênticos do SQLite principal, Excel, `VERSION` e `mail_service.py`; os demais serviços e testes existentes preservados em `before/` também permaneceram idênticos, exceto a alteração de testes DOM explicitamente descrita. A integridade do SQLite principal permanece `ok`. As cinco mensagens originais, IDs 1 a 5, continuam `pending`, todas com `attempts=0`.

## Pendências para decisão e implementação na Etapa 3

1. Definir se a primeira observação deve alertar sobre registros já urgentes/vencidos e como evitar uma avalanche de alertas iniciais. Hoje não há envio inicial nem replay para usuários recém-elegíveis.
2. Definir se mudanças simultâneas devem virar uma mensagem consolidada por registro. Hoje são até três mensagens distintas por transição, sem duplicação técnica.
3. Definir validade/cancelamento de pendências antigas, especialmente após reativação, e política para mudanças de preferência com mensagens em processamento. A janela de envio em andamento não pode oferecer cancelamento absoluto após aceitação SMTP.
4. Decidir sobre alertas de renovação, remoção de registros, edição de registros encerrados e destinatários por responsável/equipe. São regras ausentes ou comportamentos atuais que exigem decisão, não correções aplicadas agora.
5. Definir procedimento de revisão de `uncertain`/`sending`, incluindo correlação segura com provedor e auditoria. Não resetar esses estados para `pending` automaticamente: isso pode duplicar mensagens já aceitas.
6. Definir frequência e operação do processamento em uma etapa autorizada. Atualmente o observador cobre gravações pelo ExcelService; passagem do tempo depende de uma varredura chamada explicitamente. Nenhum agendamento foi ativado.

Nenhuma nova regra foi implementada, nenhum envio real foi realizado e nenhum comando de processamento foi executado no banco principal. Não houve alteração de SMTP/credenciais, AWS, dados reais, interface ou versão.
