# Etapa 3C.1 — Contrato isolado de destinatários de e-mail

Implementação local validada em 08/11/2026. Não instala integração operacional,
persistência, agendamento ou entrega. As estruturas abaixo existem em memória.

## Arquivos desta etapa

| Arquivo | Alteração |
| --- | --- |
| `services/email_recipient_policy.py` | Novo contrato, aprovação simulada, resolução e revalidação puras. |
| `services/notification_recipients.py` | Acrescentado somente o helper público `email_eligibility_denials`, que reutiliza a avaliação existente sem modificar seus consumidores. |
| `tests/test_email_recipient_policy.py` | 41 testes novos, exclusivamente com objetos fictícios em memória. |
| `scripts/testar_contrato_destinatarios.py` | Executor restrito a 3A/3B/3C.1, com dois testes dos bloqueios de isolamento. |
| `CONTRATO_DESTINATARIOS_3C1.md` | Contrato, evidências, limitações e proposta futura; nenhum SQL é executado. |

As demais alterações preexistentes no workspace não fazem parte desta etapa.
Não houve incremento de versão nem preparação de release.

## Identidades e aprovação

`EmailAccount.account_id` representa a identidade persistente `users.id` /
`account.user_id`. O login editável fica em `profile_logins.login` e não pode
ser usado como chave. Atenção ao adaptador futuro: `ProfileService.account`
expõe um campo de apresentação chamado `user_id` que contém o login; esse
campo não serve para construir a identidade deste contrato. Nome e e-mail
também não identificam a conta.

`approve_primary_designation` valida uma proposta, sem gravar nem substituir
qualquer designação. O ator deve ser um superadministrador ativo, conforme
a política administrativa existente. O alvo deve existir, estar ativo e ter
papel `admin` ou `superadmin`. Não ocorre promoção automática.

`identify_primary_admin` exige exatamente uma designação ativa, explícita e
confiável. Zero designações, duas designações (inclusive repetição da mesma),
alvo removido, desativado ou com papel incompatível produzem `account_id=None`
e códigos técnicos. Nunca escolhe o primeiro superadministrador. Mudanças
de login, nome ou e-mail preservam a designação pelo identificador interno.

A designação concede prioridade na ordenação, sem conceder escopo. O principal
também precisa de autorização explícita sobre o conteúdo e de elegibilidade
para e-mail. Se ele falhar, não ocorre substituição automática. Contas com
autorizações próprias válidas continuam elegíveis; isso não as designa como
administrador principal. Designação ausente/ambígua é reportada mesmo quando
existem destinatários secundários expressamente autorizados.

## Escopos e origem confiável

Uma `EmailAuthorization` tem ID único, conta alvo, módulo, escopo, aprovador,
estado e, conforme o escopo, equipe, registro e geração. São aceitos somente
`OrdensServico`, `Acessos` e `Renovacoes`, sem curingas.

| Escopo | Condição completa para autorizar um evento |
| --- | --- |
| `module` | Mesmo módulo explicitamente aprovado. Abrange os registros desse único módulo; não aceita limites adicionais disfarçados ou os ignora. |
| `team` | Mesmo módulo **e** mesma equipe atual. Para limitar um módulo por equipe, use este escopo. |
| `record` | Mesmo módulo **e** mesmo código **e** mesma geração **e** mesma equipe vinculada na aprovação. |

Todos os limites dentro de uma autorização são cumulativos (AND). Entre
autorizações explícitas completas, basta uma aplicável (OR). O resolver não
combina o módulo de uma autorização inadequada com a equipe de outra. Uma
autorização revogada não concede acesso e não revoga outra autorização válida.
IDs de autorizações repetidos no inventário são rejeitados, para impedir estados
contraditórios. Várias autorizações válidas geram somente um destinatário, com
os IDs das fontes válidas ordenados.

A equipe de OS e acesso vem de `funcionario -> Funcionarios.equipe -> Equipes`.
A equipe de renovação vem de `acesso -> Acessos.funcionario -> Funcionarios.equipe`.
A equipe do responsável da renovação não amplia esse escopo. O campo derivado
`equipe` que possa acompanhar o registro, assim como filtros visuais, não é
considerado prova de autorização. Referências ausentes e identidades duplicadas
impedem autorização.

O escopo de registro é conservador: troca de equipe ou exclusão/recriação do
código invalida a autorização anterior. É necessária uma nova aprovação.
Não foram introduzidas permissões sobre telas ou APIs. Vínculos de funcionário,
responsáveis por equipe e gestores da 3B não se tornam autorizações desta política.

As funções de aprovação validam propostas e devolvem objetos imutáveis com um
marcador privado válido nesta execução. Dicionários do navegador, objetos
construídos diretamente, `dataclasses.replace`, cópias profundas e reconstruções
de JSON não viram autorizações confiáveis. Revogação usa helper próprio.
Esse marcador não é assinatura, credencial, autenticação ou proteção contra
código Python hostil. O chamador do servidor é uma fronteira de confiança:
contas, inventários e snapshots devem ser atuais e obtidos de fontes autorizadas.
Não se deve fornecer um endpoint que transforme o JSON do navegador diretamente
em chamadas de aprovação. Um adaptador persistente autenticado/auditável ainda
precisa ser desenvolvido e aprovado separadamente.

## Elegibilidade, eventos e revalidação

`evaluate_email_eligibility` reutiliza a 3B: conta ativa, papel reconhecido,
endereço presente com validação sintática existente, e-mail verificado e opção
de recebimento habilitada. Somente `True` ou inteiro `1` habilitam os indicadores;
strings e floats não são aceitos como consentimento. Validação sintática não
prova existência da caixa postal; a verificação da conta continua obrigatória.

`EmailDecision` separa `authorization_sources`, `authorization_denials`,
`eligibility_denials` e `event_denials`. Exemplos de recusas:
`authorization_missing`, `authorization_revoked`, `module_mismatch`,
`team_mismatch`, `record_generation_mismatch`, `account_not_active`,
`email_unverified`, `email_opt_out` e `event_superseded`.

O evento deve ser um `OperationalEvent` da 3A ainda vigente no snapshot.
Presença, geração, revisão, última identidade de evento, status e data são
conferidos. Registro alterado desde o snapshot ou evento não vigente bloqueia
a entrega. As funções não modificam o evento ou o snapshot recebido.

`resolve_email_recipients` retorna IDs de contas deduplicados (principal elegível
primeiro), decisões por conta e problemas estruturados. Não retorna endereços
como identidade, objetos de fila ou destinatários internos. A preferência de
e-mail não interfere na Central; os 39 testes existentes da 3B continuam passando,
incluindo a independência entre canais.

`revalidate_email_recipients` exige a mesma identidade de evento da resolução
preparada e recalcula tudo com contas, escopos, designação, inventário e snapshot
atuais. A lista final é a interseção entre a seleção preparada e a seleção atual.
Novos usuários ou um novo principal não entram automaticamente em conteúdo já
composto. A operação só pode reduzir a seleção preparada.

Na integração futura, revalidar **cada registro** do corpo imediatamente antes
da entrega, recompor conteúdo quando necessário e buscar o endereço atual da
conta. Uma permissão sobre um evento não autoriza todos os registros de um
resumo. Este módulo não implementa transação de entrega, bloqueio concorrente,
composição, política de retries ou supressão de mensagens vazias.

## Uso isolado

Interface pública principal:

```python
designation = approve_primary_designation(
    'proposal-primary', 'fictional-admin', actor_id='fictional-root', accounts=accounts)
grant = approve_email_authorization(
    'proposal-grant', 'fictional-admin', 'OrdensServico', 'team',
    actor_id='fictional-root', accounts=accounts,
    raw=inventory, snapshot=checkpoint, team_code='fictional-team')
prepared = resolve_email_recipients(
    event, inventory, accounts, snapshot=checkpoint,
    primary_designations=[designation], authorizations=[grant])
# Todos os argumentos abaixo devem representar o estado atual confiável.
current = revalidate_email_recipients(
    prepared, event, current_inventory, current_accounts, snapshot=current_checkpoint,
    primary_designations=current_designations, authorizations=current_grants)
```

O exemplo apenas representa dados em memória; não designa contas nem altera
permissões reais. Não existe conexão desta interface a rotas, produtores,
outbox, worker, comando Flask ou SMTP.

## Proposta de persistência futura — não executada

Criar estruturas aditivas somente após aprovação específica de migração:

1. `email_primary_designations`: ID imutável, `account_id`, `approved_by`,
   `approved_at`, `active`, `revoked_by`, `revoked_at` e motivo. FKs de conta
   e atores para identidades persistentes; `CHECK(active IN (0,1))`; índice
   único parcial para uma única designação ativa global. Preservar histórico.
   A ausência de designação continua um estado explícito de configuração,
   sem preenchimento automático por papel. Trocas devem ser atômicas e auditadas.
2. `email_recipient_authorizations`: `grant_id` imutável, `account_id`, módulo,
   escopo, equipe, registro, geração, aprovador/data e dados de revogação.
   `CHECK`s enumeram módulos/escopos e exigem a forma exata de cada escopo:
   módulo sem equipe/registro/geração; equipe sem registro/geração; registro
   com equipe/registro/geração positiva. FKs para contas e atores. IDs únicos,
   índices de busca por conta/módulo/estado e unicidade ativa por escopo por
   índices parciais separados (evitar a semântica de `NULL` em unicidade composta).
3. Histórico de aprovação/revogação com ator, alvo, operação, valores e instante
   UTC. Mudanças só por operação administrativa autenticada; o estado atual do
   ator deve ser conferido na mesma transação. Nenhuma cópia de senha ou papel
   para as novas estruturas, nenhum preenchimento baseado em e-mail ou nome.

Os registros e equipes estão no Excel: não criar FKs SQLite fictícias para esses
códigos. Validar referências a partir do inventário confiável. Antes de persistir
autorizações, garantir identidade durável de equipes (sem reutilização de código,
ou com geração própria), e de registros inclusive após reinícios/restaurações.
A geração da 3A exige checkpoints duráveis com tombstones; perder/reinicializar
o snapshot não pode revalidar permissões antigas. Uma restauração exige reconciliar
ou invalidar concessões antes da reativação. Essa garantia ainda não é instalada
pela 3C.1. Não migrar dados operacionais para SQLite por suposição.

Plano de migração e reversão, a ser aprovado separadamente:

1. Backup consistente do banco, Excel e checkpoints; registrar hashes e versão
   de schema, verificar restauração. Preparar e testar primeiro em cópia isolada.
2. Capturar contagens/hashes das contas, senhas, papéis, preferências, sessões,
   eventos, notificações e outbox na cópia. Executar apenas DDL aditiva em transação,
   com verificação de integridade/FKs, unicidade e rollback em falha.
3. Confirmar que todas as estruturas/dados anteriores permanecem equivalentes.
   Testar ausência de designação, conflitos, referências inválidas, troca atômica,
   concessão/revogação auditada, concorrência e reexecução controlada da migração.
4. Submeter o SQL, evidências, backup e plano de janela operacional à aprovação
   específica antes de qualquer execução no principal. Não escolher um titular
   nem importar concessões da política antiga automatic
   amente.
5. Em reversão, desabilitar somente a integração nova e preservar novas tabelas
   e auditoria. Falha da transação deve desfazer seu DDL. Restauração de backup
   exige operação autorizada e reconciliação para não sobrescrever dados posteriores.

## Validação executada

Comando: `python -B scripts/testar_contrato_destinatarios.py`.

Resultado final: **116 testes executados, todos aprovados**:
34 da 3A, 39 da 3B, 41 da 3C.1 e 2 dos bloqueios do executor.
A primeira execução teve uma fixture com ID de concessão repetido; ela foi
corrigida sem relaxar a validação de unicidade.

Cobertura inclui designação válida/ausente/duplicada, alvo inexistente/inativo/
bloqueado/papel inválido, identidade após alteração de login/e-mail, três módulos
nos três escopos, equipe adversa, registro adverso, referências ausentes,
revogação, opt-out, metadados não confiáveis, deduplicação, eventos alterados/
superados, reaproveitamento de código, mudança de equipe e revalidação.

O executor instala audit hooks antes de importar os módulos testados, bloqueia
conexões SQLite (até `:memory:`), conexões de rede/SMTP, subprocessos, escritas/
mutações no filesystem e leitura das pastas reais `dados` e `instance`. Desabilita
bytecode e recusa importação de `app`, autenticação, rotas enterprise e serviço
de e-mail. Os bloqueios de escrita, conexão, leitura real e importação são
testados explicitamente. A suite não inicializa Flask, workers ou schema.

Não foi usado o executor geral recomendado em `AGENTS.md`: seu bootstrap e
suítes mais amplas não atendem à restrição explícita desta etapa de não inicializar
a aplicação nem estruturas persistentes. Não houve alteração visual e não se
declara homologação visual ou validação de integração completa.

Hashes SHA-256 lidos externamente ao executor, antes e depois da execução:

| Arquivo | SHA-256 inalterado |
| --- | --- |
| `dados/dados_dashboard.xlsx` | `4E1AD99271C9BD7D77A7FC406E41B9C540867DF531AE0495F454B072F9752EB1` |
| `instance/auth.sqlite3` | `5F9AFB9698A639EAE26A3F57BA1F6ECD775704FCE64611AE36AFB432B20A7B62` |

Nenhum dado real, outbox ou histórico foi gravado; nenhum e-mail foi enviado,
SMTP ativado, migração executada, permissão real alterada ou titular real
designado. Nenhuma mudança de AWS, deploy, push ou configuração de produção.
A única dependência nova da 3B é a leitura de seu helper de elegibilidade;
nenhum consumidor operacional importa a política 3C.1.

## Autorizações futuras

Permanecem pendentes de autorização separada: adaptadores de persistência,
migrações e seus SQLs, designação real do principal, concessões reais, integração
com produtores/compositor/fila e envio. Qualquer relaxamento da vinculação de
registro à equipe/geração ou combinação mais ampla de escopos exige decisão
explícita. A 3C.1 foi concluída sem depender dessas autorizações.

O resumo de pendências atuais e mudanças importantes, 09h em
`America/Sao_Paulo`, recuperação até 12h do mesmo dia e ausência de e-mail vazio
continuam decisões de negócio documentadas; não foram implementados aqui.
Renovações rejeitadas continuam encerradas sem lembrete de sete dias na 3A,
cujos testes foram reexecutados. As etapas 3C.2 a 3C.7 não foram implementadas.
