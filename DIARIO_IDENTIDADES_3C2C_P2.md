# DashboardOS 2.0 — Etapa 3C.2C / P2

## A. Resumo executivo

Implementados e testados somente em SQLite sintético/temporário:

- Migração explícita e transacional da base v1 para uma extensão aditiva v2.
- Diário com preparação, confirmação, aborto e histórico de estados.
- Recibos imutáveis com sequência, resultados e cadeia de digests SHA-256.
- Unidade de trabalho que revalida o P1, sincroniza identidades, confere gerações,
  audita, avança checkpoint e confirma recibo na mesma transação SQLite.
- Separação entre contexto técnico do produtor e autoridade administrativa.

Nenhuma integração operacional foi ativada. Não foram abertos banco ou planilha
reais, executados CRUD, SMTP, workers, timers ou recursos AWS. P3–P7 permanecem
fora desta implementação. A recuperação entre Excel, SQLite e âncora **não**
está implementada. Não houve incremento de versão do produto ou release.

## B. Arquivos

Criados:

| Arquivo | Responsabilidade |
| --- | --- |
| `services/identity_operation_schema.py` | DDL, checksums, verificação e migração aditiva v2. |
| `services/identity_operation_journal.py` | Contextos de produtor, diário, recibos, validação da cadeia e unidade transacional. |
| `tests/test_identity_operation_journal.py` | 56 testes novos de persistência, segurança, falhas e concorrência. |
| `scripts/testar_diario_identidades.py` | Entrada P2 no executor protegido de SQLite sintético. |
| `DIARIO_IDENTIDADES_3C2C_P2.md` | Este relatório. |

Modificados após inspeção das dependências:

| Arquivo | Alteração e compatibilidade |
| --- | --- |
| `services/email_recipient_schema.py` | `verify_schema(db)` reconhece a extensão v2 conhecida e confere suas definições completas. API anterior mantida, DDL/checksum v1 intactos. |
| `services/email_recipient_repository.py` | Extraída a participação interna `_synchronize_manifest`, sem commit próprio. `sync_identities(manifest, actor_id=...)` mantém assinatura, transação, superadmin, auditoria e bloqueios anteriores. |
| `scripts/testar_persistencia_destinatarios.py` | Seleção opcional de suítes, mantendo o conjunto padrão. Bloqueios adicionais de importação de Excel/Flask e execução de processos. Nenhum teste anterior removido. |

P1, política 3C.1, eventos 3A, rotas, aplicação, Excel, importação, autenticação,
Central e interface não foram alterados. As demais mudanças preexistentes no
workspace não pertencem à P2.

## C. Esquema v2

### Estratégia aditiva

A tabela v1 `email_recipient_schema` possui `CHECK(version=1)`. Para preservar
integralmente sua definição e suas linhas, a versão efetiva 2 é registrada na
nova tabela `email_identity_journal_schema`, com referência ao checksum da base.
Não houve reconstrução, renomeação ou atualização da tabela de versão v1.

`migrate_identity_journal(connection)` exige uma v1 existente e válida, conexão
ociosa e FKs habilitadas. Usa `BEGIN IMMEDIATE`, DDL individual, verificações de
integridade e rollback em falha. Não usa startup, importação automática, Flask ou
abertura de caminhos de banco. Na reexecução, apenas verifica o esquema completo.

Uma instalação sem v1 é recusada; sua criação continua sendo uma operação
explícita separada. Objetos desconhecidos, checksums/versões divergentes e
definições adulteradas são rejeitados. Não há reparo silencioso.

### Tabelas e colunas

| Tabela | Campos principais |
| --- | --- |
| `email_identity_journal_schema` | `version` PK fixada em 2, `base_digest`, `digest`, `applied_at`. |
| `email_identity_operations` | `operation_id` PK; `origin`, `kind`, `actor_id`, `authorization_ref`, `policy_version`; módulo/código; quatro fingerprints; época/revisões/token esperados; `receipt_id` único; `request_digest`; JSON canônico do plano, operação e alocações; estado; datas UTC de preparação/confirmação/aborto; motivo. |
| `email_identity_receipts` | `receipt_id` PK, `operation_id` único/FK, sequência inteira positiva única, digest anterior com FK para recibo anterior, digest próprio único, payload canônico e data UTC. |
| `email_identity_operation_events` | ID autoincremental, operação/FK, estado, data UTC e motivo. Histórico gerado por triggers. |

São **4 tabelas, 2 índices explícitos e 13 triggers novos**. As estruturas v1
permanecem com suas definições anteriores. Os índices explícitos são:

- `email_identity_operation_status(status, prepared_at)`;
- `email_identity_operation_event_owner(operation_id, id)`.

PKs e restrições `UNIQUE` também geram os índices internos correspondentes.

As restrições incluem tipo de operação enumerado, módulo/código compatíveis com
operações individuais/importação, revisões inteiras não negativas, estados
enumerados e metadados de data/motivo compatíveis com o estado. FKs vinculam o
ator à identidade persistente de `account` e os recibos/eventos à operação.

Triggers impedem:

- Inserir operação já terminal ou substituir/excluir uma operação existente.
- Alterar seus campos imutáveis, incluindo payload, fingerprints e origem.
- Transitar de um estado terminal ou retornar para `prepared`.
- Confirmar sem recibo correspondente ou abortar uma operação com recibo.
- Inserir recibo fora da próxima posição ou com predecessor incompatível.
- Atualizar, excluir ou substituir recibos/eventos por `INSERT OR REPLACE`.

### SQL e checksums

O SQL executável completo está em `identity_operation_schema.DDL`.
Não foi duplicado num script de migração operacional.

| Componente | SHA-256 |
| --- | --- |
| Base v1, preservada | `caf8e781139164fd25bb53d0a1f26b82e1d2b95bd37bfb15845649b722bfcfe3` |
| Declarações adicionais v2 | `7e972baa90c9ee3f0c3d80c276401a032d936b7c961942f8421023b9f57d53e0` |
| Composição v2 | `8816ae55ad3ac92a63c477cacbeceb7616cc8c6f7ee77611c60c993d80286883` |

O digest adicional deriva das declarações SQL normalizadas. O digest composto
é SHA-256 de `base_digest + '\n' + delta_digest`. A verificação também compara
as definições reais em `sqlite_master`; não confia apenas na linha de versão.

## D. Diário de operações

Estados:

```text
                 -> committed  (terminal, recibo obrigatório)
prepared --------|
                 -> aborted    (terminal, motivo obrigatório)
```

`prepare` revalida a autorização e o plano antes de registrar metadados e reservar
o ID do recibo. Não muda identidades, concessões ou o checkpoint v1.

`commit` exige operação preparada correspondente e confirma todas as alterações
de identidade/recibo em uma transação. `abort` valida o mesmo contexto/descrição
da operação, registra o motivo e preserva a linha. Repetir o mesmo aborto/motivo
é idempotente; alterar o motivo ou reutilizar o ID para outra ação é recusado.

Erros de validação antes de preparar não criam uma operação fictícia. Falhas
transacionais na confirmação deixam a operação em `prepared`, sem confirmação
parcial, para nova tentativa autorizada ou aborto explícito. Não são registradas
exceções completas ou entradas pessoais para justificar uma recusa.

O histórico `prepared`/terminal é inserido por triggers, na mesma transação de
cada mudança. Datas são geradas em UTC. Campos de contexto/motivo devem ser
referências técnicas sem segredos.

## E. Recibos e idempotência

Cada recibo contém operação/recibo original, sequência, digest anterior,
fingerprint do plano, digest da requisição, checkpoint anterior/resultante,
identidades criadas/encerradas e data de confirmação. O payload é JSON canônico;
o digest próprio é SHA-256 desse payload. O predecessor do primeiro recibo é
`NULL`; os seguintes referenciam o digest do recibo anterior.

O digest da requisição inclui a descrição canônica da operação, ator/origem,
referência e versão da autorização, fingerprints, checkpoint esperado, plano
completo e alocações. O diário não armazena as linhas dos inventários: guarda
seus fingerprints e metadados de identidade.

Mesmo ID e mesmo conteúdo:

- Se preparado, retorna a mesma reserva sem escrever uma segunda operação.
- Se confirmado, retorna o recibo original sem sincronizar novamente.
- Se abortado, preparação/confirmação são recusadas.

Mesmo ID com conteúdo, ator, autorização ou alocações diferentes é recusado.
Um manifesto fornecido opcionalmente deve coincidir com o manifesto canônico,
inclusive numa repetição confirmada.

**Toda repetição continua exigindo autoridade atual e checkpoint válido.** Não
se aceita checkpoint antigo para facilitar idempotência. Duas confirmações
concorrentes com o mesmo checkpoint têm um commit; a outra encontra divergência
e precisa de referência atual obtida por procedimento confiável.

Um replay de recibo antigo pode retornar seu checkpoint histórico, mas não
substitui `journal.checkpoint`, que permanece atual. O futuro publicador não
poderá usar um replay para retroceder uma âncora.

`verify_journal_integrity` confere o digest das requisições, o histórico de estados,
todos os recibos, sua sequência/encadeamento e a correspondência entre estado
confirmado e recibo. Metadados de resultado são conferidos contra o plano gravado.
Não faz reparos e não funciona como assinatura ou âncora independente.

## F. Integração com P1 e 3C.2A

Interface principal:

```python
producer = TrustedProducer('trusted-origin', current_business_authorizer)
journal = IdentityOperationJournal(connection, external_checkpoint, producer)
context = producer.issue(
    real_actor_id, operation, plan,
    authorization_ref='business-decision-id', policy_version='policy-version')
prepared = journal.prepare(
    before, proposed, operation, plan,
    authorization=context, allocations=allocations)
receipt = journal.commit(
    before, proposed, operation, plan,
    authorization=context, allocations=allocations)
```

O exemplo representa somente uma API interna isolada; não foi conectado a rotas.

Na transação de confirmação, a unidade:

1. Confere schema completo, cadeia, FKs habilitadas, época, checkpoint e `ready`.
2. Revalida conta ativa e autorização de negócio atual.
3. Confere os fingerprints dos inventários recebidos e o conteúdo preparado.
4. Lê o histórico real da conexão SQLite e reconstrói o contexto P1 atual.
5. Reexecuta o planejador com operação/alocações recebidas; exige igualdade
   completa com o plano, aplicável e sem alocações pendentes.
6. Gera o manifesto completo a partir das identidades resultantes, usando a
   próxima revisão de origem e o ID reservado do recibo como token.
7. Sincroniza pelo participante interno extraído da 3C.2A.
8. Compara identidades presentes, gerações e tombstones efetivamente gravados
   com o plano previsto. Divergência desfaz tudo.
9. Audita o ator real, avança a revisão do checkpoint e insere recibo/estado terminal.
10. Verifica o diário e faz commit. Só depois publica `journal.checkpoint` em memória.

`commit` é a entrada da unidade de trabalho. Não se fornece um caminho público
para aceitar transação externa já aberta ou desabilitar autoridade/checkpoint.
O participante `_synchronize_manifest` é privado, exige transação ativa e não é
API autorizada de uso independente. Seus chamadores internos são a operação
administrativa antiga e a unidade técnica já validada.

`sync_identities` público permanece administrativo e mantém os bloqueios da
3C.2A, incluindo a marcação de perda de continuidade. As APIs administrativas
anteriores continuam funcionando na base v1 e na base estendida v2.

Planos obsoletos por revisão, época, histórico, inventário, token ou geração são
recusados. `applicable=True`, dataclasses tipadas ou IDs conhecidos não dispensam
recomputação ou autorização.

## G. Segurança e autoridades

### Administrativa

Designação, concessão, revogação e invalidação administrativa continuam nas APIs
3C.2A, exigindo superadministrador ativo dentro da transação. O produtor técnico
não recebe métodos de concessão ou designação e não promove seu ator.

### Técnica

`TrustedProducer` é configurado no servidor com origem e callback de política
de negócio. Não pode ser construído a partir de JSON de requisição. O callback
é obrigatório e executado dentro da transação, inclusive em replay/aborto.

`ProducerContext` é vinculado em memória ao emissor, ator, operação, plano,
origem e referência/versão da decisão. Contextos reconstruídos, copiados por
`replace`, emitidos por outro produtor ou enviados como dicionário são recusados.

Além da conta ativa/papel reconhecido, a política precisa devolver exatamente
um `BusinessAuthorization` compatível com a requisição. Booleanos, JSON e decisões
de outro ator/operação não autorizam. Isso distingue um registro de transição
de identidade de uma operação administrativa sobre permissões.

O callback dos testes é uma política sintética permissiva **somente para operações
de negócio fictícias**. Não é uma política de produção instalada. O serviço
futuro deverá extrair o ator da autenticação confiável e implementar sua política
atual de negócio; receber `actor_id` do navegador não será suficiente.

O marcador em memória não é credencial criptográfica. A separação é de API e
fronteira do servidor, não um RBAC SQLite contra código Python hostil que possua
conexão irrestrita. A conexão, emissor e callback não podem ser expostos ao cliente.
Um proprietário capaz de remover triggers e recalcular toda a cadeia está fora
da garantia de imutabilidade comum; a âncora externa continua necessária.

Não são armazenadas senhas, sessões, tokens SMTP, endereços de e-mail, nomes,
conteúdo de inventários ou corpos históricos de mensagens no diário/recibos.
Tokens de criação são identificadores de existência, não tokens de autenticação.

## H. Falhas e recuperação SQLite

| Cenário testado | Resultado observado |
| --- | --- |
| Falha antes de preparar | Nenhuma linha nova. |
| Falha ao inserir o histórico de preparação | Rollback da preparação inteira. |
| Interrupção após preparação e fechamento da conexão | Nova conexão e contexto interno autorizado retomam a operação preparada. |
| Falha antes/durante sincronização | Identidades e diário permanecem no estado preparado anterior. |
| Falha após escrever identidades | Tombstones, identidades e checkpoint são desfeitos juntos. |
| Falha na auditoria | Sincronização desfeita. |
| Falha durante inserção do recibo | Identidades, auditoria e avanço do checkpoint desfeitos. |
| Falha após recibo/estado terminal, antes do commit | Rollback de todo o conjunto, inclusive eventos do diário. |
| Falha de commit SQLite injetada antes do commit efetivo | Rollback e nenhum checkpoint novo publicado. |
| Resposta perdida após commit efetivo | Repetição autorizada retorna o recibo existente, sem nova geração. |
| Duas conexões confirmando concorrentemente | Um commit; a outra recusa checkpoint divergente. |
| Plano antigo, manifesto errado ou gerações gravadas diferentes | Recusa e rollback. |
| Recibo adulterado, mesmo com trigger restaurado pelo teste | Verificação da cadeia recusa o diário. |
| Operação abortada reapresentada | Não pode ser confirmada ou reativada. |

São falhas controladas de SQLite/Python em dados sintéticos, não ensaios de queda
de energia, hardware ou recuperação Excel. Ambiguidade entre commit e publicação
externa, ou entre arquivo e banco, não foi resolvida nesta P2.

## I. Testes executados

```powershell
python -B scripts/testar_diario_identidades.py
# Ran 58 tests ... OK

python -B scripts/testar_persistencia_destinatarios.py
# Ran 163 tests ... OK

python -B scripts/testar_planejador_identidades.py
# Ran 55 tests ... OK
```

A P2 contém **56 testes novos + 2 do guard**. A suíte de persistência anterior
cobre 3A (34), 3B (39), 3C.1 (41), 3C.2A (47) e 2 do guard. A P1 contém 53
testes do planejador e 2 de isolamento. Os guards compartilhados são reexecutados;
os totais não representam apenas testes novos.

As rodadas incrementais passaram desde a primeira execução (44 casos P2),
seguida por expansão para 56 e 58. Não houve falha automatizada a corrigir.
O reforço incluiu CHECKs contra `NULL`/revisão fracionária, fechamento/reabertura
da conexão, verificação de manifesto/alocações também em replay e casos de
recriação/encadeamento. Nenhum teste anterior foi removido ou reduzido.

Validações incluem preservação de schemas/linhas v1 e legadas, valores binários
byte a byte, Unicode/NUL, FKs, schema/versão adulterados, DDL interrompida e
rollback, cadeia, bloqueio de alterações no histórico, idempotência, autoridade
revalidada dentro da transação, histórico obsoleto, tokens reapresentados,
recriação de equipe, exclusão/recriação de registro e retorno à equipe anterior.

As fixtures reutilizam o bootstrap sintético anterior, que extrai declarações
de schema por AST, sem inicializar serviços operacionais. O banco real não é
fonte da fixture. A preservação byte a byte refere-se aos **valores** armazenados,
incluindo BLOBs; não ao arquivo SQLite sintético inteiro, que muda ao receber DDL.

O runner P2 reutiliza o guard do executor de persistência e limita conexões e
escritas a uma raiz temporária descartável. Bloqueia acesso a `dados`/`instance`,
rede/SMTP, processos, importação da aplicação/serviços operacionais, `ATTACH` e
carregamento de extensões nas conexões fornecidas. Os bloqueios são testados.

A P1 é executada em processo separado: seu contrato proíbe qualquer conexão ou
importação do repositório, portanto não se mistura sua suíte pura ao processo
que carrega a P2. As suítes anteriores preservam suas regras e cobertura.

Não foram executados servidor, testes gerais com bootstrap Flask, preparação
frontend ou testes que utilizem dados reais. A restrição específica da P2
prevalece sobre a recomendação geral de `AGENTS.md`. Não houve alteração visual.

## J. Integridade dos dados reais

Os hashes foram lidos pelo shell, fora dos processos de testes, sem conexão ao
SQLite real nem leitura de células. Os **19 arquivos preexistentes** em `instance`
e `dados` mantiveram caminhos, tamanhos e hashes SHA-256 antes/depois. Não foram
criados bancos de teste ou auxiliares SQLite nessas pastas.

| Arquivo | SHA-256 preservado |
| --- | --- |
| `instance/auth.sqlite3` | `5F9AFB9698A639EAE26A3F57BA1F6ECD775704FCE64611AE36AFB432B20A7B62` |
| `dados/dados_dashboard.xlsx` | `4E1AD99271C9BD7D77A7FC406E41B9C540867DF531AE0495F454B072F9752EB1` |

Os processos de teste não acessaram dados reais: as tentativas explícitas nos
testes do guard foram recusadas antes do acesso. Conexões sintéticas foram
fechadas e as raízes temporárias descartadas ao término.

Não houve regravação de contas, senhas, sessões, notificações, outbox ou tentativas
SMTP reais. Central, configurações e interface permaneceram intactas. Não foram
executados AWS, deploy, commit ou push.

## K. Limitações para P3/P4

- Não existe âncora externa ou protocolo de publicação implementado. A cadeia
  local não detecta sozinha restauração consistente de todo o banco.
- Preparar/abortar altera o diário v2 sem avançar o checkpoint de identidades
  v1. A P3 deverá ancorar também esses estados de controle, não somente recibos
  confirmados ou `IdentityCheckpoint`.
- O checkpoint esperado continua sendo fornecido por uma fonte confiável externa
  ao banco restaurável. A P2 não o substitui automaticamente pelo estado do banco.
  Uma resposta perdida com checkpoint local ainda antigo exige o procedimento
  de continuidade futuro, em vez de dispensar a conferência.
- O diário não guarda inventários pessoais completos. Retomar exige que um
  coordenador confiável reapresente as mesmas entradas/operação/alocações.
- Sem integração Excel, os fingerprints comprovam correspondência entre as
  entradas fornecidas, o plano e o registro preparado; não comprovam sozinhos
  que uma planilha externa permaneceu atual.
- Não há staging/backup de Excel, recibo interno de XLSX, recuperação de arquivo,
  captura de todas as mutações reais ou suporte a edições manuais.
- A política de negócio de produção e a origem autenticada do ator ainda não
  estão conectadas. O emissor interno é uma fronteira de confiança, não um endpoint.
- A confirmação técnica exige a continuidade v1 já pronta. Bootstrap/recuperação
  administrativa permanecem explícitos, sem concessões ou designações automáticas.
- Não há persistência completa de eventos 3A, compositor diário, fila nova ou SMTP.
  A outbox histórica não foi consultada/processada como parte do mecanismo.

## L. Próximos passos sujeitos a aprovação

A futura P3 deve definir a âncora independente, sua atualização condicional,
recibos de publicação, recuperação de commit ambíguo e estados preparados/
abortados, primeiro com provedores simulados. P4 tratará a coordenação com Excel,
staging, recibos no arquivo e recuperação idempotente entre os recursos.

Migração principal, política de produção, captura nos produtores reais e
ativação de notificações exigem autorizações próprias, backup e testes em cópia
consistente conforme as etapas posteriores. Nada nesta implementação autoriza
essas ações ou garante o protocolo completo Excel–SQLite–âncora.

Não houve avanço para P3, P4, P5, P6 ou P7.
