# DashboardOS 2.0 — Etapa 3C.2C / P3

## A. Resumo executivo

Implementada e validada uma infraestrutura **isolada** de publicações de
continuidade, com provedores em memória/arquivo temporário e classificação
verificável de recuperação. Nenhum escritor real foi conectado.

O protocolo inclui checkpoint completo, cadeia de recibos P2, digest do diário,
histórico de publicações, CAS, testemunho externo conhecido e reservas anteriores
às mutações SQLite. Preparações e abortos são considerados mesmo sem mudança
no checkpoint de identidades.

A captura e a autorização de intenções são somente de leitura. P3 não executa
`prepare`, `commit`, `abort`, invalidação de época ou recuperação de negócio.
Essas mutações continuam pertencendo à unidade P2 autorizada, invocada
explicitamente pelo chamador nos testes sintéticos.

Não houve migração, mudança de schema ou alteração de infraestrutura P2. Não
foram implementados provedor remoto, S3, recursos AWS, Excel, SMTP ou integração
operacional. Não houve avanço para P4–P7 ou preparação de release.

## B. Arquivos

Criados nesta etapa:

| Arquivo | Responsabilidade |
| --- | --- |
| `services/continuity_anchor.py` | Contratos, evidência SQLite, autorização de intenções, provedores e publicação condicional. |
| `services/identity_recovery.py` | Classificador somente de leitura com evidências, bloqueios e ações permitidas. |
| `tests/test_continuity_anchor.py` | 37 testes de contrato, intenções, concorrência e arquivo temporário. |
| `tests/test_identity_recovery.py` | 32 testes de falhas, restaurações sintéticas e classificações. |
| `scripts/testar_continuidade_identidades.py` | Executor P3 usando o guard sintético existente. |
| `CONTINUIDADE_IDENTIDADES_3C2C_P3.md` | Este relatório. |

Nenhum arquivo anterior foi modificado. Aplicação, Excel/importação, autenticação,
rotas, observadores, Central e interface permanecem fora da implementação.

A inspeção inicial foi estática: relatórios 3C.2A/P1/P2, schemas v1/v2,
repositório/checkpoints, planejador, diário e testes/executores correspondentes.
A revisão confirmou que `prepare` e `abort` P2 não avançam o checkpoint v1, e
que a cadeia local isoladamente não comprova atualidade após restauração integral.

## C. Contrato da âncora

### Evidências e publicações imutáveis

`SQLiteEvidence` é capturado numa transação consistente com `PRAGMA query_only=ON`,
restaurando a configuração anterior no final. Verifica schema/cadeia P2, FKs,
histórico de estados, checkpoint e registro de identidades. Se o último recibo
corresponde ao checkpoint atual, suas identidades finais precisam corresponder
às linhas presentes. Até um callback de autorização mal configurado que tente
escrever é bloqueado nesse contexto de leitura.

A evidência contém eventos ordenados e um digest por prefixo do diário. Cada
evento vincula operação, digest imutável da requisição, estado, data, hash do
motivo e, quando confirmado, o recibo verificado. Isso permite conferir o prefixo
anterior sem confundir o estado atual da linha com seu histórico de preparação.

`AnchorPublication` representa:

- Ambiente e época.
- `control_sequence`: passo lógico de intenção/transição ancorada.
- `publication_sequence`: cada atualização externa efetivamente publicada.
- `IdentityCheckpoint`: revisão administrativa, revisão/token do produtor e época.
- `journal_sequence`: posição dos eventos P2 ancorados.
- `receipt_sequence`: posição na cadeia de recibos confirmados.
- Última operação e último recibo confirmados; digest dessa cadeia.
- Digest do prefixo do diário e do histórico de identidades.
- Estado externo e operação pendente, quando existente.
- IDs/digests da publicação anterior e atual.
- `file_evidence=None`, reservado para P4, sem inventar prova de Excel.

Todos os DTOs retornados são congelados e usam valores imutáveis. Identificadores
de publicação são explícitos; o digest é calculado do conteúdo canônico, sem
incluir o próprio digest ou o marcador interno de confiança.

`AnchorWitness` contém ambiente, época, sequência, ID e digest da última
publicação conhecida pelo chamador. Deve ser mantido por uma fonte confiável,
independente do estado que pode ser restaurado. Não deve ser obtido do navegador
ou substituído automaticamente pelo valor do arquivo que está sendo verificado.

### Provedores

`AnchorProvider` define `read()` e `compare_and_swap(expected, publication)`,
permitindo uma implementação remota futura sem dependência de fornecedor.

| Provedor | Garantia nesta P3 | Limite |
| --- | --- | --- |
| `MemoryAnchorProvider` | Histórico imutável pela API, validação e CAS sob lock. | Volátil, destinado a contrato/concorrência simulada. |
| `TemporaryFileAnchorProvider` | Histórico fora do SQLite, lock entre instâncias, arquivo temporário, sincronização, substituição e CAS. | Exclusivamente em raiz temporária; não é provedor de produção nem proteção contra rollback integral da máquina. |

O provedor de arquivo exige raiz temporária existente e diretório contido nela.
Recusa o diretório do projeto. Usa um contêiner JSON com todo o histórico;
publicações anteriores não são descartadas na atualização.

A escrita faz flush/fsync do arquivo temporário, `os.replace` e fsync do diretório
quando suportado. No host Windows, o caminho implementado não oferece fsync do
diretório: `directory_sync_supported=False`. O caminho POSIX está implementado,
mas não foi homologado fisicamente em outro sistema operacional nesta execução.

**Substituição atômica não equivale a durabilidade garantida em todo sistema
operacional, filesystem ou hardware.** Uma falha de sincronização após a troca
pode deixar a nova publicação visível com resposta incerta. Repetição idêntica
confere o histórico e tenta sincronizar novamente antes de retornar.

Lock abandonado, armazenamento incompleto ou arquivo ilegível resultam em
bloqueio. O provedor não remove silenciosamente locks nem promove um staging
órfão a referência atual. Os testes descartam suas raízes temporárias ao final.

## D. Publicação, sequências e idempotência

### Inicialização

`approve_bootstrap` exige superadministrador ativo, checkpoint esperado válido,
continuidade pronta e diário P2 vazio, dentro de uma transação somente de leitura.
Produz uma permissão interna vinculada ao snapshot e ao ambiente.

`AnchorPublisher.bootstrap` consome essa permissão explicitamente. Não existe
inicialização automática quando falta a âncora. Diário não vazio, permissão
reconstruída, ambiente errado ou tentativa de substituir uma referência existente
são recusados. O bootstrap é para inicialização administrativa controlada de um
ambiente; não é procedimento de restauração ou de recuperação de âncora perdida.

### Fluxo recomendado: reservar antes de cada mutação P2

```text
aprovação inicial -> baseline

autorização de intenção prepare -> reserved(intent)
chamada explícita P2.prepare    -> SQLite prepared
publicação da prova            -> prepared

autorização de intenção commit/abort -> decision_pending
chamada explícita P2.commit/abort    -> SQLite committed/aborted
publicação da prova terminal        -> committed/aborted
```

`capture_authorized_intent` revalida a autorização de negócio, conteúdo e
precondições P2 numa transação de leitura. Para preparar, calcula o digest da
requisição que a P2 registrará, sem fabricar o ID de recibo ainda inexistente.
Para commit/aborto, exige a operação preparada correspondente. A intenção de
aborto também é vinculada ao hash do motivo exato.

`reserve_intent` publica essa intenção antes da mutação. Se a escrita SQLite
não ocorrer, falhar ou desaparecer numa restauração, a intenção independente
continua pendente. A recuperação não chamará esse estado de consistente nem
reexecutará o negócio por suposição.

Exemplo dos contadores num fluxo com reservas:

| Publicação | Controle | Diário P2 ancorado | Publicação externa |
| --- | ---: | ---: | ---: |
| Baseline | 0 | 0 | 1 |
| Intenção de preparar | 1 | 0 | 2 |
| Preparação comprovada | 1 | 1 | 3 |
| Intenção terminal | 2 | 1 | 4 |
| Terminal comprovado | 2 | 2 | 5 |

A materialização de um passo reservado não incrementa novamente sua sequência
de controle. A sequência externa avança em toda nova publicação. Já as revisões
administrativa/do produtor pertencem ao checkpoint SQLite e podem não mudar
numa preparação ou aborto. Nenhum contador substitui os demais.

### Conferência e CAS

O publicador exige histórico íntegro e testemunho esperado. Compara ambiente,
época, predecessor, prefixo do diário, identidade da operação, digest da
requisição, checkpoint, recibo e transição permitida. Um commit precisa do recibo
P2 correto; um aborto precisa do estado terminal comprovado. Decisão reservada
incompatível ou motivo de aborto diferente são recusados.

O provedor faz CAS sobre a referência esperada, não escolhe um estado apenas
porque sua revisão é maior. Há no máximo um vencedor para a mesma versão
anterior. Um perdedor encontra conflito ou indisponibilidade do lock de arquivo.

Mesmos ID e conteúdo retornam o recibo original. Mesmo ID com conteúdo diferente
é recusado. Repetir uma publicação histórica não retrocede o head atual. ETag
não é utilizado como digest criptográfico.

`publish` também permite publicar, explicitamente, uma próxima prova P2 já
existente; `reserve=True` reserva uma preparação que já foi gravada. Esse caminho
é útil para inspecionar/reparar publicações pendentes, mas **não protege
retroativamente o intervalo anterior à reserva**. Para prevenir perda silenciosa
nesse intervalo, o futuro coordenador deve usar as reservas pré-SQL descritas
acima, aguardar seu reconhecimento e impedir escritas fora do protocolo.

Se várias transições ocorreram sem suas publicações intermediárias, a P3 não
inventa snapshots anteriores: recusa avanço e classifica evidência insuficiente.

## E. Recuperação verificável

`assess_recovery` lê a âncora, verifica seu histórico/testemunho e compara a
evidência SQLite capturada. Retorna `RecoveryAssessment` com estado, evidências
utilizadas/ausentes, ações permitidas/proibidas, necessidade de aprovação
administrativa e motivo técnico.

| Estado | Critério principal | Ação possível, sempre explícita |
| --- | --- | --- |
| `consistent` | Checkpoint, diário, cadeia e identidades correspondem à âncora. | Usar snapshot SQL confirmado; se preparado, aguardar decisão P2 autorizada. |
| `pending_publication` | Há exatamente a próxima preparação comprovada ainda não publicada. | Reservar/publicar a preparação. |
| `recoverable_publish` | Commit com recibo válido ainda não publicado, ou preparação correspondente à reserva. | Publicar a prova existente, sem repetir negócio. |
| `recoverable_abort` | Aborto SQLite comprovado ainda não publicado. | Publicar o aborto já ocorrido; não executar um novo aborto SQL. |
| `rollback_detected` | SQLite atrás do diário ancorado, checkpoint atrás, preparação reservada desaparecida ou provedor atrás de testemunho conhecido. | Bloquear e solicitar revisão administrativa. |
| `divergent` | Ambiente/época, prefixo, cadeia de publicações ou estado diferem. | Bloquear; não escolher baseline pelo maior contador. |
| `insufficient_evidence` | Falta recibo/prova, há lacuna intermediária ou intenção reservada sem correspondente SQL. | Bloquear e preservar evidências para decisão autorizada. |
| `anchor_unavailable` | Provedor indisponível, ocupado ou com armazenamento não legível. | Repetir somente a leitura, sem presumir sucesso/falha da publicação. |

Os estados `recoverable_*` **não executam recuperação**. O chamador deve decidir
explicitamente por uma publicação com prova e CAS atuais. Não há executor de
recuperação SQL, redefinição de época ou restauração de permissões nesta fase.

Uma intenção pendente sem prova terminal é ambígua: pode ser falha anterior à
mutação ou restauração posterior. É bloqueada e requer revisão, não commit ou
aborto automáticos. Falha na captura de evidência também não produz um snapshot
substituto; códigos como recibo ausente/adulterado são conservados como diagnóstico.

## F. Matriz de falhas executada

Todos os cenários abaixo utilizaram dados fictícios e provedores temporários/
simulados. Não se restaurou qualquer arquivo real.

| # | Cenário | Resultado observado |
| --- | --- | --- |
| 1 | Reinício consistente | Nova conexão SQLite corresponde à âncora. |
| 2 | Falha antes de preparar | Sem mutação; baseline permanece consistente. |
| 3 | Falha depois de preparar | Prova SQL gera publicação pendente, sem replay. |
| 4 | Antes de publicar preparação | Pendência explícita; com reserva pré-SQL, a intenção continua visível. |
| 5 | Depois de publicar preparação | Estado consistente preparado, sem permissão para commit automático. |
| 6 | Falha durante confirmação SQL | P2 faz rollback; preparação publicada permanece válida. |
| 7 | Commit SQL sem publicação | `recoverable_publish`, exigindo recibo correto. |
| 8 | Publicação efetiva com resposta perdida | Repetição retorna o recibo existente, sem duplicar histórico. |
| 9 | Aborto confirmado sem publicação | `recoverable_abort`; checkpoint de identidades pode continuar igual. |
| 10 | Publicação repetida | Idempotência de ID/conteúdo; conteúdo diferente recusado. |
| 11 | Duas publicações concorrentes | Um vencedor em memória e entre duas instâncias de arquivo. |
| 12 | SQLite antigo restaurado | Diário atrás da âncora: rollback detectado. |
| 13 | SQLite e seu diário restaurados juntos | A referência independente permanece mais recente e detecta o retrocesso. |
| 14 | Âncora antiga apresentada como atual | Testemunho mais recente detecta o rollback do provedor. |
| 15 | Recibo ausente | Captura recusada; falta de evidência explícita. |
| 16 | Recibo adulterado | Verificação P2 recusa mesmo com trigger restaurado no teste. |
| 17 | Cadeia de digests quebrada | Recusa de predecessor SQL ou cadeia externa inválida. |
| 18 | Sequência externa interrompida | Divergência, sem preencher lacunas por inferência. |
| 19 | Operação pendente sem prova | Bloqueio e solicitação de evidência/decisão administrativa. |
| 20 | Provedor indisponível | `anchor_unavailable`, somente leitura/retry permitido. |
| 21 | Época divergente | Bloqueio; não avança para época escolhida automaticamente. |
| 22 | Ambiente divergente | Publicação e classificação recusam o contexto errado. |
| 23 | Falha de criação, escrita/sync ou troca do arquivo | Head anterior preservado antes da troca; erro após troca exige confirmação/retry. |
| 24 | Reinício após publicação incompleta | Provedor reaberto recupera repetição idêntica; staging órfão sem head bloqueia. |
| 25 | Tentativa de retroceder âncora | CAS/encadeamento/testemunho impedem sobrescrita silenciosa. |
| 26 | Recuperação repetida | Classificação determinística não altera nada; publicação explícita repetida é idempotente. |

Casos adicionais incluem rollback de aborto com checkpoint idêntico, reserva
anterior à preparação desaparecida, decisão terminal reservada sem prova,
tentativa de publicar commit sob intenção de aborto, razão de aborto diferente,
DTOs reconstruídos, identidades que discordam do recibo e callback tentando
escrever durante captura de intenção.

Sem reservas anteriores à mutação, uma transição que desapareceu antes de ser
observada externamente não pode ser descoberta por hashes locais. Essa janela
foi identificada na revisão e motivou as reservas pré-SQL, sem modificar a P2.

## G. Segurança e limites de confiança

- Contextos/evidências devem vir de funções internas, não JSON do navegador.
  Um marcador por processo impede reconstruções acidentais e `replace`, mas
  não é assinatura ou defesa contra Python hostil no mesmo processo.
- Testemunhos, ambiente e provedor devem ser configurados por fonte confiável.
  Digest fornecido pelo cliente não comprova integridade ou autorização.
- A captura de intenção reutiliza autoridade de negócio P2 atual. O bootstrap
  requer administração; produtor técnico não designa titular nem concede/revoga
  permissões. Publicar recibo é registrar continuidade, não autorizar envio.
- A P3 só lê SQLite; chamadas P2 mutantes nos testes são explícitas e autorizadas.
  Mesmo `query_only` é restaurado após erro. Não se enfraqueceu a unidade P2.
- A publicação não contém senhas, e-mails, sessões, nomes ou corpos de mensagens.
  Motivos são representados por hash; IDs devem ser técnicos e livres de segredos.
- Hashes detectam inconsistência sob a fronteira confiável. Um administrador que
  substitua banco, âncora e testemunhos, recalculando todos os hashes, não é
  autenticado/detectado somente por essa técnica.
- Um arquivo fora do SQLite ainda pertence à máquina. Restaurar tudo, inclusive
  o último testemunho conhecido, está fora da garantia do provedor temporário.
- Locks abandonados e evidência insuficiente bloqueiam; não há remoção de lock,
  rebaseline ou recuperação ambígua automática.

## H. Compatibilidade e P4

P1/P2/3C.2A não foram alterados. A P3 consome os verificadores e auxiliares
internos da P2 para ler evidência e autorizar intenções; as regressões continuam
necessárias se esses contratos internos mudarem. Não existem chamadas novas
nos produtores reais.

Reservas e classificação não interceptam chamadas diretas à P2. O futuro
coordenador deverá serializar escritores, esperar confirmação da reserva antes
da mutação, revalidar as precondições e obedecer aos bloqueios da classificação.
Escritores que ignorem esse protocolo não recebem garantias de continuidade.

Alteração administrativa de checkpoint sem evento de diário correspondente é
recusada para publicação normal. A P2 não fornece prova suficiente para inventar
uma transição administrativa externa. Um protocolo administrativo próprio
continuará necessário em etapa autorizada.

`FileEvidenceReferences` reserva campos para hash do Excel confirmado, operação
de substituição, recibo do staging e referência à cópia anterior. Nesta P3,
`file_evidence` é obrigatoriamente `None`; nenhum hash ou recibo XLSX é inventado.
O ID de publicação externa já está presente nos recibos de publicação.

A P4 deverá tratar XLSX sintético, staging/backup, integração com `os.replace`,
reconciliação arquivo/banco e o vínculo desses fatos ao protocolo. O `os.replace`
usado nesta P3 troca somente o JSON da âncora temporária.

## I. Testes executados

```powershell
python -B scripts/testar_continuidade_identidades.py
# Ran 71 tests ... OK

python -B scripts/testar_diario_identidades.py
# Ran 58 tests ... OK

python -B scripts/testar_persistencia_destinatarios.py
# Ran 163 tests ... OK

python -B scripts/testar_planejador_identidades.py
# Ran 55 tests ... OK
```

P3: **69 testes novos + 2 do guard**. O executor anterior cobre 3A, 3B, 3C.1 e
3C.2A. P1 e P2 foram executadas separadamente, preservando seus próprios contratos
de isolamento. Os guards compartilhados são reexecutados; não se devem somar
os resultados como se todos fossem casos novos.

As rodadas P3 passaram em 54, 60, 69, 70 e 71 casos. A expansão incluiu reservas
pré-SQL e leitura estrita, fechamento de janelas de restauração e reabertura do
provedor de arquivo com intenção/decisão pendente. Não houve falha automatizada
nas rodadas executadas. As alterações de revisão não removeram testes anteriores.

O executor reutiliza o guard de SQLite sintético: conexões e escritas limitadas
a uma raiz temporária, bloqueio de dados reais, rede/SMTP/processos, Flask e
serviços operacionais, `ATTACH` e extensões. Usa exclusivamente fixtures fictícias.
Não cria bancos em `instance`; não abre XLSX. Os testes de arquivos e restauração
atuam somente em arquivos temporários e backups de SQLite sintético.

O executor geral e o bootstrap frontend recomendados em `AGENTS.md` não foram
utilizados porque inicializam aplicação/estruturas fora do escopo desta fase.
Não houve modificação ou homologação visual.

## J. Integridade dos arquivos reais

Por exigência da solicitação, o shell calculou hashes dos arquivos preexistentes
em `dados`/`instance`, fora dos processos de testes. Foi a única leitura desses
arquivos: não houve conexão ao banco real, leitura de células ou consulta de
conteúdo pessoal.

Os **19 arquivos** mantiveram caminhos, tamanhos e SHA-256 antes/depois. Nenhum
auxiliar SQLite ou arquivo de âncora foi criado nessas pastas.

| Arquivo | SHA-256 inalterado |
| --- | --- |
| `instance/auth.sqlite3` | `5F9AFB9698A639EAE26A3F57BA1F6ECD775704FCE64611AE36AFB432B20A7B62` |
| `dados/dados_dashboard.xlsx` | `4E1AD99271C9BD7D77A7FC406E41B9C540867DF531AE0495F454B072F9752EB1` |

As raízes temporárias foram descartadas depois dos testes. Contas, sessões,
preferências, Central, filas históricas e configurações reais não foram abertas
pelos testes nem alteradas. Não houve SMTP, worker, timer, deploy, push ou AWS.

## K. Limitações

- Não há provedor remoto real, credenciais, recursos AWS ou custos externos.
- O provedor de arquivo é de teste, carrega/grava todo o histórico e não foi
  dimensionado como armazenamento de produção.
- Não há garantia de durabilidade física em todos os sistemas operacionais;
  os testes de sincronização com falha são simulações, não corte de energia.
- A persistência do testemunho confiável fora do conjunto restaurável não foi
  instalada em ambiente real. Restaurar testemunho e âncora juntos pode ocultar
  retrocesso; a implantação futura deverá definir outro domínio de confiança.
- Recuperação classifica e bloqueia; não executa mutações SQL ou invalidação de
  época, nem resolve ambiguidades administrativas automaticamente.
- A proteção das janelas depende de reservas antes de cada mutação e de escritores
  que sigam o protocolo. Não se pode inferir uma preparação/aborto nunca ancorado
  que desapareceu por uma restauração fora desse protocolo.
- Não se publicam lacunas ou mudanças administrativas sem provas adequadas.
- Bootstrap exige ambiente inicial controlado e diário vazio; perda de âncora
  não autoriza reutilizar uma aprovação antiga como plano de recuperação.
- Nada foi integrado com Excel, CRUD, importação, eventos operacionais completos,
  resumo diário, outbox ou entrega. O protocolo completo de produção não está
  declarado implementado.

## L. Próximos passos

A P4 depende de autorização explícita para integrar o coordenador a planilhas
**sintéticas**, usar reservas prévias e conferir evidências reais do arquivo:
hash, staging, cópia anterior e recibo de substituição. Deve testar todas as
fronteiras Excel–SQLite–publicação antes de qualquer escritor real.

Continuam pendentes decisões sobre provedor independente de produção, retenção,
ACLs, persistência do último testemunho, disponibilidade e recuperação
administrativa. Migração principal e integração operacional exigem aprovações
separadas, backups consistentes e ensaio em cópia.

Não houve avanço automático para P4, P5, P6 ou P7.
