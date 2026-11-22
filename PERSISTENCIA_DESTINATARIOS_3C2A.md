# DashboardOS 2.0 — Etapa 3C.2A

## A. Resumo executivo

Implementada e validada em 08/11/2026 uma camada SQLite aditiva **isolada** para
designações de principal, concessões, revogações, auditoria e identidade durável
de equipes e registros. A aplicação não importa nem ativa a camada nova.

A migração só foi executada em bancos descartáveis com dados inteiramente
fictícios. Nenhum backup/cópia do banco real foi necessário ou realizado.
Não houve migração principal, designação ou concessão real, SMTP, worker,
comando operacional, alteração visual, infraestrutura, push ou deploy.

Permanecem pendentes os produtores duráveis de identidade, a âncora independente
de continuidade e a aplicação autorizada da migração no ambiente real. Esta
etapa não persiste eventos operacionais completos, resumos ou mensagens SMTP.
Não foi incrementada a versão do produto nem preparada uma release.

## B. Arquivos desta etapa

Todos os arquivos abaixo foram **criados** nesta etapa:

| Arquivo | Responsabilidade |
| --- | --- |
| `services/email_recipient_schema.py` | DDL, versão, checksum, pré-condições, integridade e migração transacional explícita. |
| `services/email_recipient_repository.py` | Operações administrativas, registro de identidades, leitura confiável e adaptador da 3C.1. |
| `tests/test_email_recipient_persistence.py` | 47 testes de persistência/segurança com SQLite temporário. |
| `scripts/testar_persistencia_destinatarios.py` | Executor com isolamento de banco/filesystem, bloqueios de rede e importação operacional. |
| `PERSISTENCIA_DESTINATARIOS_3C2A.md` | Este relatório e procedimento futuro. |

Nenhum arquivo anterior foi modificado por esta etapa, incluindo o contrato e
os testes da 3C.1. As outras alterações já existentes no workspace permanecem
fora deste escopo. A nova dependência da política pura é unilateral: o repositório
importa a 3C.1; nenhum consumidor real importa o repositório.

## Inspeção inicial realizada

Foram lidos o contrato 3C.1, `email_recipient_policy.py`,
`notification_recipients.py`, os schemas de autenticação/enterprise/perfil,
`excel_service.py`, o contrato 3A e os testes/executores existentes, antes de
escrever a camada nova. Não foram instanciados os serviços operacionais.

- `AuthService.__init__` cria diretório e estruturas: não foi chamado/importado.
- `users.id` e `account.user_id` são a identidade interna. O login editável está
  em `profile_logins.login`. O campo de apresentação `user_id` de perfil não deve
  ser usado como identidade interna.
- As migrações existentes usam execução explícita, backup SQLite e transação.
  Seus métodos não foram invocados: executar o serviço inicializaria estruturas.
- O Excel contém códigos e referências textuais. `ExcelService.mutate` procura
  o primeiro número disponível; um código excluído pode ser reutilizado. Atualização
  preserva o código; exclusão remove a linha. Importações também podem substituir
  inventários. Nada disso foi alterado.
- A 3A mantém geração e tombstones no snapshot recebido; primeira ativação começa
  geração 1. Isso isoladamente não prova continuidade após reinício/restauração.

## C. Estrutura SQL

Versão própria: **1**, registrada em `email_recipient_schema`, independente de
`enterprise_version` e da versão do aplicativo. O SQL executável completo está
na tupla `DDL` de `services/email_recipient_schema.py`; o checksum SHA-256 é
calculado sobre essas declarações normalizadas. A conferência também compara
as definições reais de tabelas, índices e triggers em `sqlite_master`.

### Tabelas e colunas

| Tabela | Colunas |
| --- | --- |
| `email_recipient_schema` | `version` PK, `digest`, `applied_at` UTC. |
| `email_identity_state` | `slot` PK limitado a 1, `epoch`, `revision`, `source_revision`, `source_token`, `ready`. |
| `email_team_identities` | `code`, `generation` (PK composta), `incarnation`, `present`. |
| `email_record_identities` | `module`, `code`, `generation` (PK composta), `incarnation`, `team_code`, `team_generation`, `operational_generation`, `present`. |
| `email_primary_designations` | `designation_id` PK, `account_id`, `approved_by`, `approved_at`, `active`, `revoked_by`, `revoked_at`, `revocation_reason`. |
| `email_recipient_authorizations` | `grant_id` PK, `account_id`, `module`, `scope`, `epoch`, `team_code`, `team_generation`, `record_code`, `record_generation`, `operational_generation`, `approved_by`, `approved_at`, `active`, `revoked_by`, `revoked_at`, `revocation_reason`. |
| `email_recipient_audit` | `id` autoincremental, `actor_id`, `affected_account`, `operation`, `object_id`, `occurred_at`, `result`, `details`. |

O autoincremento da auditoria implica a tabela auxiliar padrão `sqlite_sequence`.
Nenhuma tabela anterior recebe colunas, alterações de schema ou preenchimentos.

### Restrições e índices

- FKs de contas/aprovadores/revogadores referenciam `account.user_id`, cuja
  referência a `users.id` é verificada como pré-condição. Exclusão de contas com
  histórico referenciado é bloqueada; não existe cascata de exclusão de auditoria.
- As referências de equipe e registro apontam para **linhas reais do novo registro
  de identidades**, não para supostas tabelas relacionais do Excel.
- A FK composta de autorização de registro exige que módulo, código, geração
  durável, equipe, geração da equipe e geração operacional pertençam à mesma
  identidade persistida. Não é possível misturar limites de registros diferentes.
- `CHECK`s restringem módulos a `OrdensServico`, `Acessos`, `Renovacoes`; escopos a
  `module`, `team`, `record`; flags a 0/1; gerações de identidades a inteiros positivos.
- A forma de módulo proíbe todos os campos opcionais de equipe/registro. Equipe
  exige equipe/geração e proíbe registro/gerações de registro. Registro exige
  todos os limites positivos e suas referências válidas.
- Revogação exige ator, data e motivo não vazio; uma linha ativa não pode trazer
  metadados de revogação. IDs de designação e concessão são imutáveis.
- `email_primary_single_active`: índice único parcial global sobre `active=1`.
- `email_team_current` e `email_record_current`: uma identidade presente por
  código de equipe ou par módulo/código de registro.
- `email_grant_module_active`, `email_grant_team_active`,
  `email_grant_record_active`: três índices únicos parciais separados, sobre os
  campos obrigatórios de cada escopo. Assim, `NULL` não permite duplicações ativas.
- `email_grant_owner`: índice de consulta por conta, módulo e estado.
- São 7 tabelas explícitas, 7 índices explícitos e 15 triggers. Os triggers
  bloqueiam alteração/exclusão/substituição da auditoria e alteração de payload,
  exclusão, substituição por `INSERT OR REPLACE` ou reativação de histórico.
  Designações/concessões só transitam de ativa para revogada; identidades só
  transitam de presente para tombstone. Nova aprovação exige ID novo.

## D. Contrato de persistência e adaptação da 3C.1

`migrate_recipient_schema(connection)` exige conexão ociosa com FKs habilitadas.
Não abre caminho de banco, não faz backup implícito, não se registra no startup
e não cria titular ou autorização. A chamada é explícita, não um comando Flask.
Disponibilizar a função não autoriza sua execução no banco real.

`EmailRecipientRepository(connection, external_checkpoint)` também não inicializa
schema ou serviços. APIs principais:

- `designate_primary`: cria a primeira designação; substituição requer
  `replace_current=True` e motivo, revogando a anterior na mesma transação.
- `revoke_primary`, `grant`, `revoke`: validam autoridade atual, modificam apenas
  estruturas novas e auditam a operação na mesma transação.
- `sync_identities`: consome manifesto completo, tipado e confiável.
- `invalidate_continuity`: recuperação administrativa explícita; muda época,
  revoga todas as concessões ativas, mantém histórico, cria tombstones e bloqueia
  resolução até uma nova reconciliação com identidades de criação novas.
- `load_policy`: lê um snapshot de contas/designações/concessões. O chamador
  deve carregá-lo novamente antes de futura entrega.
- `resolve`: lê contas e concessões numa transação de leitura consistente e
  chama a 3C.1. Com `prepared`, usa a revalidação que somente reduz destinatários.

O adaptador lê a identidade de `account.user_id` diretamente, confere vínculos
duráveis e só então reidrata objetos internos selados da 3C.1. Não aceita JSON
como concessão persistida. Essa utilização das funções privadas de selo é
intencional e restrita ao adaptador confiável; não transforma o selo em assinatura.
Uma futura mudança desse contrato requer testes de compatibilidade conjuntos.

Concessões antigas cujo vínculo durável não corresponde são excluídas e relatadas
como `authorization_identity_stale:<id>`. Concessões revogadas ainda compatíveis
são carregadas como inativas e recusadas pela 3C.1. A resolução confere também a
identidade durável do evento para **todos** os escopos, incluindo módulo, antes
de permitir qualquer destinatário.

Todos os limites da 3C.1 foram preservados: AND dentro de cada concessão, OR
somente entre concessões completas, principal prioritário sem acesso implícito,
sem substituto automático, e-mail verificado/opt-in, conta ativa e deduplicação.
Essas concessões não concedem acesso a telas, APIs ou notificações internas.

## E. Segurança e transações

As escritas começam com `BEGIN IMMEDIATE`, verificam schema/checkpoint e consultam
o papel/estado do aprovador **dentro da transação**. Exige-se superadministrador
ativo. Titular de designação deve ser administrador ativo; alvo de concessão
deve ser conta ativa com papel reconhecido. Revogar não exige que o alvo continue
ativo. Não há promoção, escolha automática de superadmin ou importação de
concessões legadas.

Uma troca de titular revoga o anterior, insere o novo e audita ambos atomicamente.
Erro de inserção restaura o titular e o histórico anteriores. Concessões e suas
revogações seguem a mesma atomicidade. Falha inesperada ou de auditoria desfaz
toda a transação. Os testes injetam esses erros.

Recusas administrativas esperadas, com identificadores válidos, fazem rollback
do comando por savepoint e registram `result=rejected`, sem executar a alteração
solicitada. A revisão do checkpoint avança para preservar também esse histórico.
Para ator inexistente, `actor_id=NULL`: não se atribui uma identidade inventada.
Ator conhecido, conta afetada, operação, ID e UTC são registrados. Não são
armazenados senhas, credenciais, corpos de mensagens ou tokens SMTP. Motivos
administrativos devem ser breves e livres de segredos.

Falhas de schema, conexão ocupada, checkpoint externo divergente ou erro inesperado
não produzem um falso evento de sucesso; a transação é desfeita. Na integração
futura, tentativas rejeitadas antes de existir um contexto confiável precisarão
de log externo de segurança. Triggers protegem operações comuns; não oferecem
proteção contra o proprietário do arquivo que possa remover triggers ou editar
o banco arbitrariamente. Permissões de arquivo e administração continuam necessárias.

## F. Identidades, códigos e restaurações

`IdentityManifest` carrega época, revisão sequencial e token da origem, mais:

- `TeamIncarnation(code, incarnation)` para cada equipe presente;
- `RecordIncarnation(module, code, incarnation, team_code, operational_generation)`
  para cada registro presente nos três módulos.

O token de criação (`incarnation`) precisa ser estável durante aquela existência
e novo após recriação. **Não pode ser inferido só pelo código ou por uma varredura
periódica.** O manifesto deve vir de um produtor durável, com cada transição
relevante em ordem. Saltos de revisão, reutilização indevida de token ou regressão
de geração detectada colocam o registro em `ready=0`. A resolução permanece
bloqueada até recuperação explícita, sem continuar usando as permissões anteriores.

Ao excluir um item, a linha anterior vira tombstone. Ao recriar com token novo,
a geração persistida cresce. Equipes também têm geração; recriar uma equipe
invalida suas concessões antigas. Troca de equipe ou mudança de geração operacional
cria nova geração durável de registro; retornar à equipe anterior não recupera
uma concessão antiga de registro. Gerações e tombstones sobrevivem ao fechamento
e reabertura do SQLite, comprovado em teste.

`IdentityCheckpoint(epoch, revision, source_revision, source_token)` é obrigatório.
É comparado integralmente com o estado do banco em toda operação. Cada transação
administrativa concluída avança `revision`; cada sincronização exige exatamente
a próxima `source_revision`. Duas instâncias com o mesmo checkpoint concorrendo
por uma escrita não têm sucesso simultâneo: a segunda encontra divergência.

O repositório publica `repo.checkpoint` somente após commit, inclusive quando
uma recusa esperada foi auditada. O consumidor futuro deve ancorá-lo duravelmente
fora do conjunto restaurável e apresentar o último valor nas próximas operações.
Reabrir banco não permite obter silenciosamente a referência de confiança do
próprio banco restaurado. Divergência bloqueia a operação sem sobrescrever dados.

### Dependências e limites da garantia

Não existe como detectar apenas pelo estado atual do Excel uma exclusão e
recriação invisível entre duas leituras, nem uma troca de equipe seguida de retorno.
É necessário um produtor que capture as transições no momento da mutação e
publique recibos consistentes com Excel/checkpoints. Isso exigirá alterações
autorizadas em CRUD/importação/produtores; **nenhuma foi realizada aqui**.

A âncora externa também não está implementada no ambiente real. Se banco,
manifesto e âncora forem restaurados juntos, a comparação não consegue provar
retrocesso. Alterações legadas de contas não incrementam esta revisão isolada:
uma futura restauração de autenticação deve obrigatoriamente passar pela barreira
externa de continuidade. Não se deve reutilizar uma referência antiga para
contornar uma divergência. Falha entre commit e atualização da âncora deve
bloquear uso e entrar em recuperação administrativa, sem confiança automática
no valor do banco.

Inventário, snapshot 3A, evento e manifesto devem representar observação atual
confiável. Não há persistência completa de revisões/eventos 3A nesta etapa: o
controle de identidade não é comprovação de atualidade de todos os campos de
um evento. Essa proteção e a composição/entrega atômica pertencem às próximas
subetapas. Nenhuma dessas dependências foi simulada como garantia de produção.

## G. Testes executados

```powershell
python -B scripts/testar_persistencia_destinatarios.py
# Ran 163 tests ... OK

python -B scripts/testar_contrato_destinatarios.py
# Ran 116 tests ... OK
```

O executor novo cobre 34 testes da 3A, 39 da 3B, 41 da 3C.1, **47 novos de
persistência** e 2 de isolamento. A segunda execução usa o executor estrito da
3C.1, que proíbe até conexões SQLite em memória. Há sobreposição entre as suítes;
as quantidades não devem ser somadas como casos distintos.

As execuções passaram desde a primeira rodada (156 testes), seguidas por reforços
de revisão que elevaram a cobertura para 162 e finalmente 163. Não houve falha
automatizada a corrigir nesta etapa. Os reforços verificam lacuna de sequência,
bloqueio persistente por perda de continuidade, recuperação explícita, conta
afetada na auditoria, compatibilidade com `sqlite3.Row` e escopos reidratados.

Casos relevantes executados:

- Migração repetível, schema/versão alterados, colisões, base ausente, FKs,
  índices parciais, `CHECK`s, gerações inválidas e rollback de DDL parcial.
- Titular único, alvo ausente/inativo/papel incompatível, aprovador sem autoridade,
  troca transacional bem-sucedida e falha no meio da troca.
- Concessões nos três escopos/módulos, duplicação ativa com campos opcionais,
  revogação, nova aprovação com ID novo, alvos desativados, referências inválidas.
- Auditoria UTC, conta afetada, tentativa de update/delete/replace do histórico,
  payload imutável, falha injetada na auditoria e rollback integral.
- Duas conexões/threads concorrendo pela designação; exatamente um commit.
- Reabertura do SQLite, exclusão/recriação com mesmo código e geração 3A antiga,
  recriação de equipe, mudança e retorno de equipe, sequência omitida, manifesto
  antigo, snapshot de banco sintético restaurado e âncora atual divergente.
- Revalidação com conta bloqueada/inativa, opt-out, e-mail ausente/não verificado,
  alteração de login e proibição de incluir novos destinatários em resolução preparada.

Os schemas legados das fixtures são extraídos como literais por AST dos arquivos
de schema atuais. Não são importados `AuthService`, `ProfileService` ou a aplicação.
Isso testa compatibilidade com as declarações presentes no código, sem abrir
uma cópia ou o banco principal. Todos os usuários, senhas e históricos são fictícios.

O executor cria uma raiz temporária vazia e restringe conexões e escritas a ela.
Bloqueia acesso de leitura a `instance`/`dados`, importações operacionais,
rede/SMTP/subprocessos, `ATTACH` e carregamento de extensões nas conexões que
fornece. Os bloqueios são testados. Ao final, conexões são fechadas e diretórios
temporários removidos; não foram deixados bancos de teste no workspace.
São proteções de execução para código de teste conhecido, não uma sandbox para
Python hostil que possa remover deliberadamente seus próprios authorizers.

O executor geral de `AGENTS.md` e os testes que inicializam Flask não foram
executados, por contrariar a restrição específica desta solicitação. Nenhuma
alteração visual foi feita, portanto não se declara homologação visual.

## H. Evidências de integridade

Antes e depois dos testes foram comparados caminho, tamanho e SHA-256 de todos
os **19 arquivos preexistentes** em `instance` e `dados`, incluindo auxiliares
existentes e backups: inventário e hashes iguais. Nenhum novo WAL/SHM/journal
principal apareceu nessa comparação. Os hashes foram lidos pelo shell, fora
do processo de testes que proíbe acesso a dados reais.

| Arquivo | SHA-256 inalterado |
| --- | --- |
| `instance/auth.sqlite3` | `5F9AFB9698A639EAE26A3F57BA1F6ECD775704FCE64611AE36AFB432B20A7B62` |
| `dados/dados_dashboard.xlsx` | `4E1AD99271C9BD7D77A7FC406E41B9C540867DF531AE0495F454B072F9752EB1` |

No SQLite sintético, a comparação antes/depois inclui definições e linhas de
todas as tabelas legadas: credenciais, sessões, preferências, eventos,
notificações, snapshots, outbox e tentativas SMTP. A migração e as operações
novas preservaram esse estado. Nenhum corpo de mensagem ou dado pessoal real
foi consultado. Não se executou backup/restauração de arquivos de produção.

## I. Procedimento futuro de migração, backup e reversão

**Este procedimento é apenas proposto, não foi aplicado ao ambiente real.**

1. Aprovar separadamente os arquivos/SQL/checksum, janela operacional, produtor
   durável, âncora externa, contas responsáveis, critérios de bloqueio e reversão.
2. Parar/controlar os escritores relevantes e recuperar importações pendentes
   apenas por procedimento operacional previamente autorizado, fora desta etapa.
   Não usar inicialização de serviços como suposta operação de leitura.
3. Obter backup consistente do SQLite via API de backup ou mecanismo equivalente
   homologado, considerando WAL/SHM e escritores. Uma cópia direta de banco ativo
   não comprova consistência. Alinhar backup do Excel, checkpoints, manifesto e
   recibo externo em uma mesma referência lógica. Proteger dados pessoais.
4. Registrar hashes, versão/checksum, contagens e integridade. Restaurar primeiro
   em cópia isolada sem rede; verificar `integrity_check` e `foreign_key_check` e
   comparar schemas/linhas anteriores, sem expor segredos em logs.
5. Na cópia, chamar explicitamente `migrate_recipient_schema` com conexão ociosa e
   FKs habilitadas. Testar reexecução, falhas, concorrência e rollback. Designações
   e concessões reais não devem ser inferidas a partir de papel, nome ou e-mail.
6. Solicitar aprovação específica da execução principal com evidências e backup
   testado. Só então executar a migração, ainda com a integração desativada.
7. Confirmar preservação das tabelas legadas, integridade e checksum. Registrar a
   época inicial em âncora independente, reconciliar identidades por procedimento
   aprovado e conceder responsabilidades somente por operação administrativa
   autorizada e auditada. Não habilitar envio nesta migração.
8. Em falha transacional, fazer rollback. Para interromper uso posterior, parar
   os consumidores novos e preservar estruturas e auditoria. Havendo perda de
   continuidade, usar recuperação explícita com nova época e concessões novas.
   Não excluir tabelas automaticamente e não restaurar backup antigo sobre dados
   posteriores. Restauração integral exige autorização, reconciliação e mudança
   da referência externa antes de qualquer reativação.

Bloquear a migração/uso se faltar backup consistente/restaurável, se houver
schema diferente, FKs/integridade inválidas, transação já aberta, versões/checksum
incompatíveis, conflito concorrente ou se não houver condições de garantir
identidade e continuidade. O código atual não fornece CLI de produção ou
mecanismo automático de aprovação.

## J. Riscos e limites remanescentes

- Nenhuma execução em cópia de dados reais foi necessária; a validação cobre
  o schema declarado e fixtures sintéticas, não particularidades não declaradas
  de uma instalação real.
- A captura durável/ordenada de identidades em Excel/importação e a âncora externa
  são pré-condições de integração, ainda não instaladas. Perdas de transições
  não podem ser corrigidas inferindo continuidade do código atual.
- A referência externa deve acompanhar commits também quando há recusa auditada.
  Falhas de atualização da âncora bloqueiam uso até recuperação autorizada.
- Schema desconhecido é recusado; não há reparo silencioso. Administradores com
  acesso irrestrito ao arquivo continuam fora da proteção dos triggers.
- Composição por registro, atualidade durável dos eventos, retries, entrega e
  coordenação entre SQLite e Excel não foram implementadas. Carregar uma política
  não autoriza reutilizá-la indefinidamente antes de um envio futuro.

## K. Antes da Etapa 3C.2B

É necessária aprovação explícita da próxima subetapa, delimitando como serão
produzidos os tokens de criação, como se capturam transições sem lacunas, onde
ficará a âncora independente e como ocorrerá recuperação após restauração.
A aplicação da migração principal requer aprovação própria após teste em cópia
consistente e backup validado. Designação real e concessões reais também exigem
operações administrativas autorizadas. Não houve avanço automático para 3C.2B.
