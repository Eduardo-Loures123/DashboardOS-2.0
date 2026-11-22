# DashboardOS 2.0 — Etapa 3C.2C / Fase P4

Coordenador isolado Excel–SQLite–Âncora, staging, recibos e recuperação idempotente.

Data de consolidação documental: 09/11/2026. Este relatório descreve o código e as execuções já existentes. A finalização documental criou somente este arquivo; não executou novamente testes, serviços ou operações de negócio.

## A. Resumo executivo

A P4 implementa um protocolo de coordenação exclusivamente sintético entre uma planilha XLSX temporária, o diário transacional SQLite da P2 e os provedores de âncora simulados da P3. Reutiliza o planejador P1, suas regras de identidades e dependências, a autorização técnica P2, reservas externas e publicações condicionais P3.

Foram implementados staging com leitura de conferência, cópia anterior preservada, hashes SHA-256, recibos encadeados, intenção de substituição publicada antes de `os.replace`, confirmação SQLite posterior à substituição, publicação final e repetição idempotente. A classificação de recuperação é separada das chamadas explícitas de execução e cancelamento. Estados sem prova suficiente são bloqueados; não existe restauração automática da planilha.

A última execução P4 registrada terminou com **65 testes aprovados**, além de **347 aprovados** nas suítes anteriores: **412 testes no conjunto das execuções**, incluindo os testes de isolamento dos respectivos executores. Os 19 arquivos reais tiveram caminhos, tamanhos e hashes preservados na verificação registrada.

O encerramento é da **P4 isolada e sintética**. Não representa liberação para produção, integração com escritores reais ou atomicidade conjunta Excel–SQLite–âncora. P5, P6 e P7 não foram executadas.

## B. Arquivos criados e modificados

Os caminhos abaixo são relativos a `DashboardOS_2.0`.

| Arquivo | Papel na P4 |
| --- | --- |
| `services/identity_excel_coordinator.py` | Novo: armazenamento XLSX sintético, validação, lock de arquivo, protocolo de execução/cancelamento e recibos. |
| `services/identity_excel_recovery.py` | Novo: diagnóstico somente de leitura e classificação das ações admissíveis. |
| `tests/test_identity_excel_coordinator.py` | Novo: protocolo, identidades, importação, falhas, repetição, autorização e concorrência. |
| `tests/test_identity_excel_recovery.py` | Novo: diagnóstico, rollback, indisponibilidade, ausência/adulteração de provas e retomada. |
| `scripts/testar_coordenador_excel_identidades.py` | Novo: executor P4 sobre o guard sintético existente. |
| `services/continuity_anchor.py` | Extensão interna P3: referências verificáveis de arquivo, provas seladas, transições e publicações de arquivo sem novo evento SQL. |
| `tests/p4-coordinator-result.log` | Registro da última execução P4: 65 testes, `OK`. |
| `tests/p4-p3-regression-result.log` | Registro de regressão P3: 71 testes, `OK`. |
| `tests/p4-protected-before.json` e `tests/p4-protected-after.json` | Inventários de caminhos, tamanhos e SHA-256 dos 19 arquivos protegidos. |
| `COORDENACAO_EXCEL_IDENTIDADES_3C2C_P4.md` | Este relatório de encerramento documental. |

A extensão em P3 é necessária porque uma fase de arquivo pode mudar sem avançar o diário SQLite. `FileEvidenceReferences`, `VerifiedFileProof`, o argumento opcional `file_proof` de `reserve_intent` e `publish_file` vinculam essas fases à operação e ao estado SQL verificado. A cadeia conserva as provas durante publicações SQL; o provedor de arquivo temporário também as desserializa. Chamadores exclusivos de P3 continuam sem evidência de arquivo. A regressão P3 permaneceu aprovada.

A P4 não modificou `app.py`, `services/excel_service.py`, `services/import_coordinator.py`, autenticação, rotas, interface, correio ou configurações operacionais. O coordenador não é importado automaticamente pela aplicação real. Alterações preexistentes no workspace não são atribuídas a esta fase.

## C. Arquitetura Excel–SQLite–Âncora

`IdentityExcelCoordinator` recebe explicitamente `SyntheticWorkbookStore`, diário P2, publicador P3, testemunho esperado, hash inicial confiável e, opcionalmente, um hook de falha para testes. Não escolhe banco ou planilha operacional por padrão. A raiz de arquivos deve existir sob o diretório temporário; caminhos fora dela e links simbólicos são recusados.

O chamador fornece o inventário proposto completo, `ProposedOperation`, ator, referência de autorização e versão de política. O coordenador lê o inventário anterior, captura evidências SQLite, confere continuidade com a âncora e planeja a transição. Tokens novos são alocados internamente com UUID, conforme as necessidades P1; não são aceitos como identidade durável de uploads.

O fluxo normal é:

1. Obter exclusão sobre a planilha e validar cadeia externa, testemunho, arquivo atual e estado SQLite.
2. Planejar com P1; persistir intenção local, receita de reconstrução do plano e primeiro recibo.
3. Capturar intenção autorizada e reservar externamente a preparação, incluindo a prova de arquivo inicial.
4. Preparar na P2 e publicar a preparação na P3.
5. Criar/conferir cópia anterior e staging; persistir/publicar a fase `staged`.
6. Reservar a decisão de commit; persistir/publicar `replace_intent`.
7. Revalidar plano, autorização e arquivos; substituir via `os.replace`, sincronizar e publicar `replaced`.
8. Confirmar na P2 e publicar o commit SQL na P3.
9. Persistir o recibo `complete`, publicar sua prova e devolver `CoordinatedReceipt`.

Persistir uma intenção local não confirma identidades. Reserva, preparação, troca de arquivo, commit SQL e publicação são passos distintos, sujeitos a falhas entre eles. A P2 conserva sua transação SQLite; a P4 não cria uma transação distribuída.

### Esquema XLSX sintético

| Aba | Colunas na ordem exigida |
| --- | --- |
| `Funcionarios` | `codigo`, `nome`, `equipe`, `cargo`, `email`, `admissao`, `status` |
| `Equipes` | `codigo`, `nome`, `responsavel` |
| `OrdensServico` | `codigo`, `descricao`, `funcionario`, `abertura`, `previsao`, `conclusao`, `prioridade`, `status` |
| `Acessos` | `codigo`, `funcionario`, `sistema`, `concessao`, `vencimento`, `status` |
| `Renovacoes` | `codigo`, `acesso`, `solicitacao`, `status`, `responsavel`, `observacoes` |

As linhas operacionais usam strings. A leitura rejeita fórmulas nas células operacionais, cabeçalhos incompatíveis e abas desconhecidas. A escrita força tipo textual. A P1 valida códigos únicos e relações funcionário–equipe, equipe–responsável, OS/acesso–funcionário e renovação–acesso/responsável. A equipe efetiva de uma renovação decorre do titular do acesso, não da equipe do responsável pela renovação.

O inventário proposto não aceita abas ou colunas extras de identidade. Em importação `new`/`upsert`, os alvos e continuações explícitos obedecem à P1; ausência no conjunto importado não é convertida automaticamente em exclusão. A P4 não implementa um novo parser de uploads nem substitui todas as validações de negócio da aplicação.

## D. Máquina de estados e pré-condições

As fases de arquivo e os estados P2/P3 são máquinas relacionadas, mas distintas. Um recibo local pode estar persistido enquanto sua publicação ainda falta.

| Fase local de arquivo | Condições e efeito |
| --- | --- |
| `intent` | Requisição, hash anterior, contexto, plano e alocações vinculados. Antes de preparar SQL, exige reserva P3. |
| `staged` | Cópia anterior íntegra; staging legível, hash calculado, inventário e metadados correspondentes ao plano. |
| `replace_intent` | Preparação publicada, decisão de commit reservada e intenção de troca persistida/publicada antes de substituir. |
| `replaced` | Arquivo atual corresponde ao novo hash; cópia anterior permanece válida; prova publicada antes do commit SQL. |
| `complete` | Recibo SQLite confirmado e publicação SQL verificados; recibo final local e publicação final de arquivo. |
| `cancelled` | Cancelamento explícito compatível com o estado anterior; aborto SQL publicado; arquivo anterior continua atual. |

As transições locais permitidas são `intent → staged → replace_intent → replaced → complete`, e `intent/staged → cancelled`. Estados terminais não aceitam outra fase local.

Na P3, a sequência normal contém `reserved`, `prepared`, `decision_pending` com `commit_intent`, e `committed`. Publicações intermediárias de arquivo mantêm o estado SQL, avançam os contadores de publicação/controle e verificam que checkpoint, digests, recibos, operação e pendência SQL não foram alterados. O fluxo de cancelamento usa intenção de aborto e estado `aborted`.

Antes das mutações pertinentes são conferidos fingerprints, checkpoint, histórico, autorização e reserva. Repetições terminais também revalidam a autorização atual, sob transação de leitura que impede gravação pelo callback nessa conferência. O mesmo ID com outra requisição é recusado. Um replay concluído retorna o recibo original e não retrocede o arquivo/checkpoint de uma operação posterior comprovada.

Uma interrupção depois da troca, mas antes de `replaced`, é identificada pelo hash novo, metadados e cópia anterior. A ausência do staging consumido nessa janela é esperada. Nenhuma dessas observações autoriza recriar identidades a partir da aparência da planilha.

## E. Staging, cópias anteriores e backups

Cada operação utiliza `operation-<SHA-256 do ID>` sob a raiz temporária, com `intent.json`, `receipts.json`, `staging.xlsx` e `previous.xlsx`. O arquivo de lock fica junto à planilha atual, não nesse diretório por operação.

`previous.xlsx` é copiado em modo exclusivo, sincronizado e comparado ao hash anterior. Uma cópia já existente não é silenciosamente substituída: se estiver parcial ou divergente, a operação bloqueia. A cópia é preservada inclusive após a conclusão; não há rotina automática de limpeza ou restauração.

O staging é construído a partir do inventário proposto, sincronizado, reaberto com openpyxl e comparado ao fingerprint do inventário e aos metadados previstos. O SHA-256 do arquivo é calculado e conferido novamente antes da substituição. A conferência se repete na retomada conforme a fase e o arquivo esperado.

A aba sintética `_identity_receipt`, marcada `veryHidden`, contém `operation_id`, `replace_id`, `staging_id` e `plan_fingerprint`. Ela é separada das cinco abas operacionais e não contém tokens duráveis fornecidos por upload. Seu conteúdo é comparado à intenção e ao plano; não constitui âncora independente nem é adotado na planilha real por esta fase.

A troca exige o mesmo filesystem, conferido por `st_dev`, e usa `os.replace`. Arquivos JSON são escritos em temporário, sincronizados e substituídos. Há sincronização de diretórios quando suportada; no Windows, `sync_directory` retorna `False`. Isso limita as garantias de persistência após queda de energia, ainda que a substituição tenha retornado com sucesso.

## F. Recibos, hashes e vinculações

O protocolo distingue três provas: hash dos bytes XLSX, fingerprint do inventário/plano e recibos SQL/publicações externas. Um hash de arquivo sozinho não comprova autorização.

| Artefato | Conteúdo e vínculo |
| --- | --- |
| `intent.json` | Operação, digest da requisição, hash anterior, fingerprints anterior/proposto, contexto P1, histórico de identidades, alocações, fingerprint do plano, IDs de staging/backup/troca e metadados esperados. |
| `receipts.json` | Sequência de fases, digest anterior, digest da intenção, operação, hashes anterior/novo, IDs de artefatos e ID previsto da publicação de cada fase. Na conclusão, inclui ID/digest do recibo SQLite e da publicação SQL. |
| `FileEvidenceReferences` | Hash confirmado, hashes anterior/proposto, IDs de operação/troca/cópia, fingerprint do plano, digest da intenção (`staging_receipt`), fase e digests de recibo atual/anterior. |
| `CoordinatedReceipt` | Dataclass congelada com operação, hashes, IDs dos artefatos, digest do recibo de arquivo, ID/digest SQL e ID/digest da publicação final. |

A representação JSON usa chaves ordenadas, separadores compactos e texto Unicode; os digests são SHA-256. A cadeia local verifica sequência, transições e vínculos imutáveis. `receipts.json` é regravado atomicamente como uma lista crescente: não é armazenamento físico WORM. A publicação independente vincula seus digests e permite detectar discrepância com a prova retida.

O recibo `complete` referencia uma publicação de commit SQL já existente. A publicação final de arquivo referencia o digest desse recibo, evitando dependência circular de hashes. A validação compara o recibo SQL real com a publicação SQL correspondente e verifica estado `committed`, ID e digest da cadeia.

Os JSON de intenção/recibos não armazenam linhas operacionais pessoais completas nem credenciais; os dados fictícios completos ficam nos XLSX temporários. Retomar exige reapresentar o mesmo inventário proposto e contexto de autorização. O histórico técnico persistido não substitui a autorização atual nem concede permissões.

## G. Recuperação e estados de bloqueio

`assess_excel_recovery` consulta arquivos, recibos, diário, publicações e testemunho. Não cria lock, não atualiza o testemunho do coordenador e não confirma, publica, cancela ou restaura automaticamente. O retorno contém estado, motivo, ações admissíveis/proibidas e indicação de necessidade administrativa.

| Classificação | Significado / tratamento |
| --- | --- |
| `consistent` | Conclusão e publicação final verificadas; uma resposta pode ter sido perdida. Replay explícito pode recuperar o recibo. |
| `staging_pending` | Intenção conhecida; staging ainda não comprovado. Retomada exige mesma requisição e autorização atual. |
| `replacement_pending` | Arquivo anterior e staging conferidos, aguardando substituição explícita. |
| `file_replaced_sqlite_pending` | Arquivo novo conferido, mas SQL ainda preparado; requer execução explícita reautorizada. |
| `sqlite_committed_publication_pending` | Commit SQL comprovado; continuação explícita da publicação ainda necessária. |
| `publication_pending` | Recibo local completo, mas publicação final de arquivo ausente. |
| `aborted` | Operação SQL abortada; não pode ser reapresentada como execução nova. Pode faltar finalizar o cancelamento explícito. |
| `file_rollback_detected` | Arquivo anterior reapareceu diante de prova externa de versão posterior. Bloqueio. |
| `database_rollback_detected` | Diário SQLite atrás da âncora independente. Bloqueio. |
| `file_and_database_rollback_detected` | Retrocesso conjunto observado contra a âncora. Bloqueio. |
| `divergent` | Arquivo desconhecido, prefixo/lacuna SQL incompatível ou checkpoint sem prova correspondente. Bloqueio. |
| `insufficient_evidence` | Recibo/artefato ausente ou inválido, testemunho incompatível, lock ocupado/abandonado ou outra prova insuficiente. Bloqueio. |
| `anchor_unavailable` | Provedor indisponível; não se substitui a âncora por confiança no estado local. |

Uma âncora antiga diante do testemunho retido resulta em `insufficient_evidence`, com motivo `anchor_rollback_detected`. Não há reset automático de baseline ou escolha da maior revisão numérica como prova de continuidade.

As ações mutantes são chamadas separadas: `execute(...)` para execução/retomada e `cancel(...)` para cancelamento. Ambas exigem entradas correspondentes e autorização atual. `cancel` requer arquivo anterior ainda atual, operação SQL existente e fase compatível; não permite compensar automaticamente após intenção de substituição ou troca. Dependendo das provas publicadas, uma tentativa pode ser recusada mesmo que a classificação indique uma ação candidata. O diagnóstico não é uma autorização executável.

Backup ou staging obrigatórios ausentes, hashes divergentes, plano obsoleto e autorização revogada impedem continuação. Backups válidos não são apagados para resolver ambiguidade. Não existe recuperação administrativa implementada que decida restaurar dados reais.

## H. Concorrência e exclusão entre instâncias

O lock usa `os.open` com `O_CREAT | O_EXCL | O_WRONLY` sobre `<planilha>.identity.lock`. Instâncias que apontam para a mesma planilha disputam o mesmo arquivo, inclusive com objetos de armazenamento e conexões SQLite independentes. Falha de aquisição retorna `exclusive_lock_unavailable`; não há fallback para lock apenas em memória.

O lock cobre o protocolo de execução/cancelamento. Sua liberação normal ocorre em `finally`; um processo encerrado abruptamente pode deixar lock abandonado. Ele não é removido automaticamente por idade ou por tentativa de recuperação. O diagnóstico bloqueia diante de lock existente.

O teste de concorrência utiliza duas instâncias, conexões SQLite independentes e uma thread competidora durante a janela anterior à troca. Confirma que a segunda operação é recusada e que a vencedora preserva seu resultado. Não foi executado ensaio com dois processos independentes nem filesystem distribuído; a primitiva de exclusão é de arquivo.

Hashes são revalidados perto da substituição e o publicador usa CAS contra a cabeça verificada da cadeia. Um testemunho retido pode ser um prefixo válido: o coordenador verifica o histórico até a cabeça atual e publica contra ela, sem usar uma cabeça antiga diretamente como autorização para sobrescrever.

Os locks são **cooperativos**. Um editor que ignore o lock ainda pode alterar o arquivo entre a última conferência e `os.replace`; a P4 não implementa CAS de bytes no filesystem nem exclusão obrigatória contra qualquer aplicativo externo. O teste cobre alterações observáveis nas fronteiras injetadas, não elimina essa janela física.

## I. Testes executados e resultados

Os resultados abaixo são das execuções anteriores à criação deste relatório, não de uma nova execução documental. Comandos relativos à raiz `DashboardOS_2.0`:

| Suíte | Comando | Resultado final registrado |
| --- | --- | --- |
| P4 | `python -B scripts/testar_coordenador_excel_identidades.py` | **65 testes, OK**, 75,861 s; `tests/p4-coordinator-result.log`. |
| P1 | `python -B scripts/testar_planejador_identidades.py` | **55 testes, OK**; saída de execução da sessão de implementação. |
| P2 | `python -B scripts/testar_diario_identidades.py` | **58 testes, OK**; saída de execução da sessão de implementação. |
| P3 | `python -B scripts/testar_continuidade_identidades.py` | **71 testes, OK**; também registrado em `tests/p4-p3-regression-result.log` (25,777 s). |
| 3A–3C.2A | `python -B scripts/testar_persistencia_destinatarios.py` | **163 testes, OK**; saída de execução da sessão de implementação. |
| Total anterior | P1 + P2 + P3 + 3A–3C.2A | **347 aprovados**. |
| Total com P4 | Soma das execuções | **412 aprovados**. |

Não foram criados neste encerramento logs retrospectivos para P1/P2/base. A soma é de execuções de suítes, que incluem seus guards; não é uma contagem de 412 cenários de negócio exclusivos.

O executor P4 reutiliza o guard sintético de persistência: conexões SQLite e escritas restritas à raiz temporária, bloqueio de leitura em `dados`/`instance`, rede, SMTP, processos, Flask, serviços operacionais, `ATTACH` e extensões SQLite. Desativa bytecode e limita as threads opcionais OpenBLAS/OMP a uma no processo do executor. A sessão teve falhas ambientais preliminares de memória; o registro final citado acima terminou com `OK`.

As fixtures são fictícias, com XLSX openpyxl e SQLite temporários. Os testes conferem schema, dependências, preservação de encarnações/gerações, importação `new`/`upsert`, criação com token novo, replay após operação posterior e callbacks de autorização sem escrita na conferência de replay. As retomadas abrem nova conexão e novo coordenador; não simulam reinício completo do sistema operacional.

### Matriz de falhas solicitada

Os nomes de testes abaixo estão nos dois módulos P4. O prefixo `test_` foi omitido para facilitar a leitura; testes `restart_after_*` são gerados pelo laço de fronteiras do módulo de coordenação.

| Nº | Cenário | Evidência de cobertura |
| --- | --- | --- |
| 1 | Antes da reserva | `restart_after_before_reserve`. |
| 2 | Após reserva | `restart_after_after_reserve`; diagnóstico de staging pendente. |
| 3 | Durante preparação P2 | `failure_inside_prepare_leaves_reserved_without_sql_rows`; atomicidade interna coberta também pela P2. |
| 4 | Após preparação | `restart_after_after_prepare`. |
| 5 | Criação do staging | `failure_inside_staging_can_retry_original_request`. |
| 6 | Staging incompleto | `staging_incomplete_refused_before_replace`. |
| 7 | Hash do staging divergente | `staging_hash_divergence_refused`. |
| 8 | Criação da cópia anterior | `failure_copying_backup_preserves_current_and_blocks_ambiguous_partial_copy`. |
| 9 | Antes da substituição | `restart_after_before_replace`. |
| 10 | Durante substituição | `failure_inside_replace_does_not_commit_sql`. |
| 11 | Após `os.replace` | `restart_after_after_replace`. |
| 12 | Sincronização de diretório | `directory_sync_failure_after_replace_can_resume`; falha injetada, inclusive no ambiente Windows. |
| 13 | Arquivo novo sem commit SQL | `replaced_sqlite_pending`; retomada após troca. |
| 14 | Commit SQL sem publicação | `publication_provider_failure_after_sql_commit_can_resume`; `sqlite_committed_publication_pending`. |
| 15 | Publicação concluída, resposta perdida | `restart_after_after_complete_publication`; diagnóstico somente de leitura. |
| 16 | Operação repetida | `repeated_request_returns_original_receipt_without_writes`. |
| 17 | Mesmo ID, conteúdo diferente | `same_id_different_content_refused`. |
| 18 | Operações concorrentes | `two_instances_lock_excludes_second_and_preserves_winner`. |
| 19 | Alteração externa | `existing_external_change_blocks_before_reservation`; `external_edit_immediately_before_replace_not_overwritten`. |
| 20 | Banco anterior restaurado | `old_database_detected_by_independent_anchor`. |
| 21 | Arquivo anterior restaurado | `file_restored_to_old_version`. |
| 22 | Banco e arquivo restaurados | `old_database_and_old_file_detected_together`. |
| 23 | Âncora antiga | `old_anchor_cannot_override_retained_witness`. |
| 24 | Âncora indisponível | `anchor_unavailable_blocks_recovery`. |
| 25 | Recibo ausente | `missing_receipt_blocks_execution`. |
| 26 | Recibo adulterado | `tampered_receipt_blocks_execution`. |
| 27 | Cópia anterior ausente | `missing_backup_blocks_after_replace_without_restoration`; diagnóstico de backup ausente. |
| 28 | Staging ausente | `missing_stage_blocks_and_preserves_backup`; staging consumido após troca é aceito. |
| 29 | Operação abortada reapresentada | `cancel_and_aborted_replay_are_idempotent`. |
| 30 | Plano/checkpoint obsoleto | `obsolete_checkpoint_never_replaces_file`. |

Também há testes de falha da publicação final, conferência de recibos imutáveis, prova não selada, confinamento de caminhos, colunas de identidade externas e autorização revogada após substituição.

Não foram executados nesta fase os bootstraps geral/frontend que inicializam estruturas operacionais. Não houve alteração ou homologação visual. Os testes de falha de I/O são simulações por hooks/mocks, não ensaios de corte de energia.

## J. Integridade dos 19 arquivos reais

Os inventários `tests/p4-protected-before.json` e `tests/p4-protected-after.json` registram os 19 caminhos, tamanhos e SHA-256. A conferência posterior, registrada na sessão de verificação, encontrou **19 arquivos e zero diferenças** em relação à baseline, usando leitura UTF-8 do inventário.

Essa verificação utilizou somente metadados e hashing dos bytes pelo shell: não abriu conexão SQLite principal, não carregou o Excel real com openpyxl e não consultou células ou dados pessoais. Nesta finalização documental foram consultados os inventários existentes; não foi necessária nova leitura dos arquivos reais.

| Arquivo principal | SHA-256 preservado |
| --- | --- |
| `instance/auth.sqlite3` | `5F9AFB9698A639EAE26A3F57BA1F6ECD775704FCE64611AE36AFB432B20A7B62` |
| `dados/dados_dashboard.xlsx` | `4E1AD99271C9BD7D77A7FC406E41B9C540867DF531AE0495F454B072F9752EB1` |

Os inventários completos são a evidência dos demais 17 arquivos, incluindo cópias anteriores já existentes. Não foram criados auxiliares SQLite ou artefatos P4 em `dados`/`instance`. Contas, sessões, autenticação, histórico de notificações, outbox, configurações e interface reais não foram alterados pela P4. Não houve envio de e-mail, worker/timer, AWS, SSH, deploy ou push.

## K. Limitações e garantias não implementadas

- **Não há atomicidade conjunta Excel–SQLite–âncora.** Entre troca, commit e publicação podem existir estados intermediários persistentes. Recuperação exige provas e chamada explícita; pode bloquear.
- **Sincronização de diretório limitada no Windows.** O código não oferece a mesma garantia de persistência de entradas de diretório que busca em plataformas com `O_DIRECTORY`. `fsync` e retorno de `os.replace` não provam resistência universal a queda de energia.
- **Locks cooperativos.** Não impedem todo escritor externo que ignore o protocolo, não eliminam a janela entre conferência e troca e não foram homologados em filesystem distribuído. Lock abandonado requer decisão administrativa externa.
- **Provedores de âncora ainda simulados.** São `MemoryAnchorProvider` e `TemporaryFileAnchorProvider`; não existe serviço remoto de produção ou domínio de confiança implantado. Restaurar banco, arquivos, âncora e testemunho juntos pode ocultar rollback.
- O selo de provas é uma fronteira interna de processo, não defesa criptográfica contra código Python hostil ou um proprietário capaz de substituir todos os artefatos e testemunhos.
- A raiz temporária é uma restrição deliberada. Não há suporte autorizado a dados reais, migração principal, integração com CRUD/importador real, autenticação de produção ou adoção da aba interna no Excel real.
- A validação estrutural e de identidades não substitui todas as regras de datas, status, limites de upload e negócio do sistema. A P4 recebe inventário proposto, não um upload bruto.
- Não há restauração automática, compensação distribuída, resolução automática de ambiguidades, recuperação administrativa completa, expiração automática de locks ou política de limpeza/retenção de backups.
- Retomada depende da reapresentação da mesma requisição e de autorização atual. A presença de recibo ou hash não concede permissões. Falhas intermediárias podem exigir bloqueio e intervenção.
- A aba interna existe apenas nos XLSX sintéticos. Preservação de formatação, macros, recursos arbitrários de Excel e compatibilidade de exportação/importação real não foram homologadas.
- Não há captura de todos os escritores reais, processamento completo de eventos operacionais, nova outbox, compositor diário, integração SMTP ou ativação de notificações.

Esses limites são parte explícita do escopo P4; a aprovação dos testes sintéticos não deve ser convertida em garantia de produção.

## L. Próximas etapas P5, P6 e P7

A documentação obrigatória A–L encerra a pendência documental identificada após a implementação. Com os resultados registrados e a preservação dos dados verificada, não resta pendência documental para encerrar a **P4 sintética**, respeitadas as limitações acima.

P5, P6 e P7 permanecem **não iniciadas por este trabalho e dependentes de autorização específica**. Este relatório não redefine nem aprova seus escopos. Antes de qualquer integração operacional futura, deverão ser pactuados os produtores/escritores abrangidos, política real de autorização, provedor independente e persistência do testemunho, exclusão no ambiente alvo, retenção de provas/backups e procedimento administrativo para estados ambíguos.

Qualquer adoção da aba interna na planilha real, migração principal ou integração com rotas, notificações, outbox e entrega requer revisão e aprovação próprias, com ensaios em cópias isoladas e critérios de aceitação definidos. Nada foi executado automaticamente nessas fases, e o encerramento da P4 não autoriza avançar para P5.
