# Etapa 3B — Destinatários e permissões em ambiente isolado

Data: 04/11/2026, America/Sao_Paulo. Nenhuma ativação na aplicação, fila ou banco principal.

## Análise anterior às alterações

- Funcionários são cadastrados na coleção Excel `Funcionarios` por `ExcelService.mutate`; contas são cadastradas em `users`/`account` pelo serviço de autenticação e gestão empresarial.
- OS e acessos usam `funcionario` como referência a `Funcionarios.codigo`.
- Renovação usa `responsavel` como referência a funcionário e `acesso` como referência a acesso. O titular desse acesso é outro envolvido direto possível.
- `Funcionarios.equipe` e `Equipes.responsavel` representam equipe/responsável. Não representam uma designação expressa para receber notificações operacionais.
- Não existe vínculo funcionário–conta nem cadastro explícito de gestores de notificações no esquema atual.
- Os papéis existentes são `superadmin`, `admin` e `user`. Somente superadministradores ativos gerenciam contas pelo serviço empresarial; administradores/superadministradores podem editar registros empresariais. Receber um alerta não concede permissão de edição.
- `account` armazena `state`, `email`, `verified`, `internal_alerts` e `email_alerts`. Esses campos foram reutilizados na elegibilidade, sem alteração de esquema.

Antes das inclusões foram preservadas cópias e hashes em `diagnosticos/etapa3b-20261104-202410/`. Não houve descarte de alterações anteriores do usuário.

## Arquivos desta etapa

Criados:

1. `services/notification_recipients.py`: resolução pura, modelos de vínculos e auxiliares de confirmação.
2. `tests/test_notification_recipients.py`: 39 testes novos, com dados fictícios em memória.
3. Este relatório, incluindo proposta de persistência para aprovação.

Modificado:

- `scripts/testar_notificacoes.py`: inclui a nova suíte na seleção padrão, preservando as proteções de isolamento existentes.

Não foram alterados `operational_events.py`, o scanner empresarial antigo, APIs Flask, interfaces, comandos da fila ou transporte SMTP. A resolução nova só funciona quando chamada explicitamente; nenhuma distribuição em produção foi modificada por esta etapa.

## Modelos isolados e limite de confiança

`EmployeeAccountLink` contém `employee_code`, `user_id`, `confirmed`, `confirmed_by` e `active`.

`ManagerDesignation` contém `sheet`, `code`, `generation`, `user_id`, `confirmed`, `confirmed_by` e `active`. Seu escopo é um único registro de uma geração da Etapa 3A; uma designação para um acesso não é herdada automaticamente por uma renovação.

Vínculos e designações não confirmados, sem autor de confirmação ou inativos não autorizam o recebimento. Ambos os modelos são valores em memória, sem persistência automática e sem associação por nome/e-mail.

`confirm_employee_link` e `confirm_manager_designation` verificam que o ator informado no contexto confiável é uma conta `superadmin` ativa. Eles verificam a existência dos alvos e devolvem somente metadados. Não escrevem em tabelas, não alteram perfis e não substituem vínculos existentes. A designação exige evento atual, não superado.

Esses metadados **não são assinaturas nem autorização para aceitar JSON arbitrário de uma requisição**. A futura integração deve carregar contas e vínculos de um repositório confiável e obter o ator da sessão autenticada, nunca do corpo enviado pelo usuário. A identidade do confirmador é evidência histórica: o resolvedor não exige que esse confirmador permaneça ativo para sempre. Revogações serão expressas no estado atual do vínculo/designação.

Em caso de múltiplas contas confirmadas para um funcionário ou múltiplos funcionários ligados à mesma conta, o resolvedor bloqueia a associação ambígua. Isso é uma proteção provisória, não aprovação de uma cardinalidade definitiva. Uma designação independente e válida de gestor continua podendo autorizar seu destinatário.

## Como a resolução funciona

`resolve_recipients(event, raw, accounts, snapshot=..., employee_links=..., manager_designations=...)` aceita um `OperationalEvent` da Etapa 3A e o snapshot atual.

1. Confere o tipo do evento, existência do registro, ausência de superação e correspondência do status/data atuais com o evento.
2. Obtém funcionários pelos códigos exatos dos relacionamentos existentes.
3. Localiza somente associações confirmadas e não ambíguas com contas.
4. Soma gestores expressamente designados para tipo, código e geração do registro.
5. Deduplica por `user_id`, preservando os motivos que autorizaram cada conta.
6. Reavalia conta, endereço, verificação e preferências fornecidos na chamada atual.
7. Devolve listas determinísticas e separadas de IDs para os canais interno e e-mail, decisões e motivos seguros de exclusão.

| Tipo de evento | Funcionários envolvidos | Gestores |
|---|---|---|
| OS | `OrdensServico.funcionario` | Somente os designados para essa OS/geração |
| Acesso | `Acessos.funcionario` | Somente os designados para esse acesso/geração |
| Renovação | `Renovacoes.responsavel` e titular de `Renovacoes.acesso` | Somente os designados para essa renovação/geração |

Se responsável e titular forem a mesma pessoa, ou se um funcionário também for gestor, a conta aparece uma única vez por canal. Não há distribuição geral a administradores ou superadministradores. Sem conta vinculada válida e sem gestor designado elegível, a resolução informa ausência de destinatários; não usa fallback por nome, e-mail, equipe ou papel.

Uma conta de gestor não precisa de vínculo com funcionário: a própria designação expressa confirma seu vínculo de autorização com o registro. Ter cargo/papel administrativo, isoladamente, não basta.

Um relacionamento ausente é diagnosticado. Por exemplo, se o acesso de uma renovação estiver ausente, não se adivinha seu titular; o responsável válido ou um gestor explicitamente designado ainda podem ser resolvidos por suas autorizações independentes.

## Elegibilidade e mudanças de autorização

| Condição | Interno | E-mail operacional futuro |
|---|---|---|
| Conta ativa com papel reconhecido e vínculo/designação atual | Obrigatório | Obrigatório |
| `internal_alerts` habilitado | Obrigatório | Não condiciona este canal |
| Endereço cadastrado e sintaticamente válido | Não obrigatório | Obrigatório |
| `verified` habilitado | Não obrigatório | Obrigatório |
| `email_alerts` habilitado | Não condiciona este canal | Obrigatório |

Preferências dos canais são independentes, conforme comportamento já existente. Apenas booleanos reais ou inteiros SQLite 0/1 são interpretados como flags; strings como `"false"`, `"true"` e `"1"` não viram consentimento.

Alterar preferências, desativar/bloquear a conta, revogar designação, mudar vínculo ou trocar o funcionário do registro afeta uma nova resolução imediatamente, quando ela recebe os dados atuais. Um resultado anterior é uma fotografia, não um token de envio permanente; a Etapa 3C deverá revalidar antes de qualquer criação/reserva/transmissão futura.

As decisões contêm IDs e motivos de autorização/exclusão, sem endereço de e-mail, nome, conteúdo de evento, senha ou token. Elas podem ser auditadas pelo chamador autorizado; nenhum registro de auditoria é gravado automaticamente nesta etapa.

O resolvedor rejeita fluxos que não sejam `OperationalEvent`, mantendo confirmações de endereço fora das regras operacionais. Ele não recebe nem altera mensagens da fila e, portanto, não modifica mensagens `sent`, aceitas ou inconclusivas.

## Proposta de persistência — ainda não implementada

A implementação isolada não necessita de SQLite novo. Para uso definitivo, serão necessários vínculos persistidos com controle administrativo e auditoria. A parte dependente dessa estrutura ficou suspensa para aprovação, conforme a instrução de não presumir um esquema novo nem aplicá-lo ao principal.

As seguintes tabelas são **propostas futuras e não existem por efeito desta etapa**:

| Estrutura proposta | Campos propostos | Justificativa |
|---|---|---|
| `notification_employee_accounts` | ID da associação, código de funcionário, `user_id`, confirmador/data de confirmação, revogador/data de revogação | Guardar vínculo explícito e histórico sem acrescentar colunas ao Excel |
| `notification_record_managers` | ID da designação, tipo/código/geração do registro, `user_id`, confirmador/data de confirmação, revogador/data de revogação | Autorizar gestores expressos por registro, sem conceder acesso global por papel |

O estado ativo poderá ser derivado da ausência de revogação; não é necessário armazenar campos redundantes. As datas propostas são metadados de autorização, não novos prazos operacionais. IDs de contas devem referenciar `account.user_id`, com estratégia de atualização compatível com a renomeação existente de contas. Códigos Excel não podem ter foreign key SQLite real: sua existência deve ser validada pelo serviço, com controle de concorrência e revalidação na resolução.

A geração dependerá da persistência dos snapshots da Etapa 3A. Não se deve preencher geração presumida nem herdar automaticamente autorização quando um código de registro for reutilizado. Reutilização de código de funcionário para outra pessoa também precisa de política de identidade/reconfirmação; o código Excel atual, sozinho, não identifica imutavelmente uma pessoa ao longo de exclusões e recriações.

Decisões pendentes de aprovação:

- Cardinalidade definitiva funcionário–conta: recomendação inicial de uma associação ativa por funcionário e por conta; ambiguidades já são bloqueadas no resolvedor isolado.
- Confirmar designação exclusivamente por registro/geração. Não foram introduzidas designações globais, por equipe ou herança acesso → renovação.
- Confirmar gestão dessas associações por superadministrador ativo, alinhada à gestão atual de contas; delegação a administradores exige regra adicional explícita.

Plano da futura migração, após aprovação:

1. Preparar migração aditiva com tabelas/índices novos e nenhum preenchimento automático de vínculos.
2. Testar em SQLite temporário: aplicação, repetição idempotente, restrições de unicidade aprovadas, renomeação de contas e preservação de todas as tabelas/linhas existentes.
3. Validar permissões e registro atômico da confirmação/revogação com auditoria.
4. Ensaiar reversão em cópia: se não houver novos registros, remoção apenas das estruturas novas pode ser avaliada; com dados de autorização, preferir desativar a funcionalidade e preservar o histórico.
5. Apresentar evidências e solicitar autorização específica antes de qualquer aplicação ao banco principal, com backup consistente.

**Nenhuma migração executável ou alteração de esquema foi criada/aplicada nesta etapa**, pois o resolvedor funciona sem persistência e as decisões acima ainda precisam de aprovação. Não foram criados vínculos, gestores ou notificações em dados existentes.

## Testes e resultados

Os 39 testes novos cobrem funcionário vinculado/não vinculado, confirmação pendente, autor ausente, gestor único/múltiplo/ausente, funcionário-gestor, deduplicação, conta inativa/bloqueada/ausente, canais independentes, endereço inválido/não verificado, opt-outs, revogação, mudança de vínculo, ambiguidades, ausência de destinatário, nomes/e-mails semelhantes, responsável de equipe sem autorização, permissões para confirmar, escopo de geração, integração OS/acesso/renovação, evento superado, determinismo e ausência de I/O.

Uma primeira rodada passou com **107 testes** de destinatários, regras operacionais, pipeline e SMTP simulado. A suíte completa e a regressão frontend são executadas com rede bloqueada, dados fictícios e bancos/Excel temporários.

Resultados finais: **158 testes Python aprovados**, incluindo os **39 novos**, e **56 testes frontend aprovados**, sem falhas. `git diff --check` não encontrou erros de whitespace.

Comandos executados em `DashboardOS_2.0`:

```powershell
.\.venv\Scripts\python.exe -B scripts\testar_notificacoes.py
.\.venv\Scripts\python.exe -B scripts\testar_notificacoes.py --completo
.\.venv\Scripts\python.exe -B scripts\testar_notificacoes.py --frontend-fixtures
node --require ./diagnosticos/etapa3b-20261104-202410/node-no-network.cjs --test --test-isolation=none tests/frontend.test.cjs
```

O executor completo chama `scripts/testar.py`; a preparação DOM chama `scripts/preparar_testes_frontend.py`, redirecionando a origem do Excel dos testes antigos para uma planilha sintética. Nenhuma mensagem do SQLite principal é importada. Resultados finais em `python-tests.txt` e `frontend-tests.txt` na pasta de evidências. Não houve homologação visual nem mudança de interface.

## Preservação, reversão e pendências da Etapa 3C

Evidências: `diagnosticos/etapa3b-20261104-202410/` contém `baseline.json`, cópias `before/`, logs de testes, manifesto de arquivos alterados e conferência final `preservation.json`.

A comparação final confirmou hashes idênticos do SQLite principal, Excel real, `VERSION`, transporte SMTP, módulo de regras 3A e demais fontes/testes protegidos. A integridade do principal continua `ok`. As cinco mensagens antigas continuam `pending`, todas com zero tentativas. No executor foi confirmada somente a inclusão da seleção de testes autorizada.

Reversão desta etapa: restaurar somente `scripts/testar_notificacoes.py` de `before/scripts/testar_notificacoes.py` e remover os três arquivos novos listados neste relatório. Não restaurar bancos/Excel nem desfazer mudanças de etapas anteriores.

Para a Etapa 3C ainda serão necessários aprovação da persistência, gestão autenticada das associações, identidade durável/geração, revalidação de destinatários em cada fronteira, integração dos canais e seleção que exclua as cinco mensagens antigas antes de qualquer reserva/validação mutável. A distribuição antiga da aplicação não foi substituída; não ativar o processador supondo que este resolvedor já esteja integrado.

Esta etapa não altera as permissões de leitura das páginas existentes nem implementa uma política geral de acesso por registro. A autorização do destinatário de um alerta é distinta dessas permissões; gestão e consumo futuros devem respeitar ambas.

O resumo único diário às 09h em `America/Sao_Paulo` permanece uma decisão para etapa futura. Não houve agendamento, worker, envio real, acesso AWS, alteração de credenciais/SMTP, interface, versão, esquema principal, dados reais ou migração. A Etapa 3C não foi iniciada.
