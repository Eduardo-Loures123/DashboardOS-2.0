# DashboardOS 2.0 — Etapa 3C.2C / P1

## A. Resumo executivo

Implementado um planejador puro e determinístico de transições de identidade.
Ele compara inventários completos anterior/proposto, operação explícita,
histórico de identidades e contexto de continuidade fornecidos pelo chamador.
Retorna um plano imutável ou uma recusa estruturada sem ações parciais.

Criação, exclusão, recriação, geração de vínculo, efeitos indiretos e importações
`new`/`upsert` são analisados exclusivamente em memória. Não há execução de
operações, SQL, alocação aleatória de UUIDs, relógio, persistência, manifesto
enviado ao repositório, integração operacional ou envio de notificações.

## B. Arquivos

Criados nesta P1:

- `services/identity_planner.py` — API, validações e objetos de plano.
- `tests/test_identity_planner.py` — 53 testes com fixtures em memória.
- `scripts/testar_planejador_identidades.py` — executor restrito, com 2 testes de isolamento.
- `PLANEJADOR_IDENTIDADES_3C2C_P1.md` — este relatório.

Nenhum arquivo anterior foi modificado. Em particular, não foram alterados
`app.py`, Excel/importação, repositório/schema 3C.2A, autenticação, observadores,
workers, Central, interface, versão ou configuração. Mudanças preexistentes no
workspace não pertencem a esta etapa.

A inspeção inicial foi estática: contratos 3C.1/3C.2A, política, schema e repositório,
3A, Excel, coordenador/importador e definições reais de `SCHEMA`/relações. Nenhum
serviço foi importado ou instanciado para fazer essa inspeção.

## C. Contrato público

```python
plan = plan_identity_transition(
    before_inventory,
    proposed_inventory,
    ProposedOperation('operation-id', 'update', 'Funcionarios', 'F1'),
    durable_history,
    context=PlanningContext('epoch', 10, 4, 'source-4'),
    allocations=(),
)
```

### Entradas

| Objeto | Contrato |
| --- | --- |
| Inventários | Mapeamentos com exatamente as cinco abas de `SCHEMA`, listas/tuplas de linhas, códigos únicos e valores textuais. Valida as referências necessárias para identidade, não todas as regras de negócio do CRUD. |
| `ProposedOperation` | `operation_id`, `kind` (`create`, `update`, `delete`, `recreate`, `import`), módulo/código em operações individuais; `mode`, `targets` e `continuations` na importação. |
| `DurableIdentity` | `RecordKey(module, code)`, token `incarnation`, geração durável, `present`, equipe/geração da equipe e `operational_generation` para registros operacionais. O histórico inclui gerações encerradas. |
| `PlanningContext` | Época, revisão administrativa, revisão/token da origem e declaração de histórico completo. Deve ser obtido/validado por um coordenador confiável. |
| `TokenAllocation` | Associação opcional entre chave de uma nova existência e token novo fornecido pelo coordenador. Não se aceita dicionário de upload como alocação. |

`Funcionarios` participa da análise de dependências, sem inventar uma tabela de
identidade de funcionário na 3C.2A. Identidades planejadas são de equipes e dos
três módulos operacionais.

### Saída

`IdentityPlan` e todos os seus objetos internos são dataclasses congeladas,
contendo somente valores imutáveis e tuplas. Não retêm linhas/dicionários das
entradas. Campos principais:

- Tipo, módulo e código da operação individual.
- `direct_transitions` e `indirect_transitions` com ação, antes/depois, motivos
  e nomes dos campos alterados.
- `preserved_identities`, `identities_to_end`, `identities_to_create` e `tombstones`.
- `resulting_identities`: inventário completo de identidades presentes após o plano.
- `allocations_needed`: necessidades simbólicas `AllocationNeed(operation_id, key)`.
- `affected_dependencies` e resultados por chave importada em `import_outcomes`.
- `issues`: código, módulo, registro e campo, quando aplicável.
- Fingerprints SHA-256 dos inventários, histórico, contexto e plano completo.

`applicable=True` significa que o planejamento é estruturalmente consistente.
**Não significa autorização ou aplicação concluída.** Sem tokens fornecidos,
uma criação pode ser aplicável e conter alocações pendentes.
`ready_for_manifest` só é verdadeiro quando o plano é aplicável e não há
alocações pendentes; ainda exige todas as verificações futuras do coordenador.

Recusas retornam `applicable=False`, sem transições executáveis parciais.
Exemplos: `reference_missing`, `identity_missing`, `identity_team_mismatch`,
`identity_generation_gap_or_duplicate`, `incarnation_reused`,
`operation_contradiction`, `import_continuity_unproven`.

## D. Regras de identidade

| Situação | Plano |
| --- | --- |
| Criação sem histórico do código | Nova existência, geração durável 1; geração operacional 1 para registro; token fornecido ou necessidade simbólica. |
| Código com existência anterior encerrada | Token novo; geração durável seguinte; geração operacional seguinte para registro. |
| Edição comum | Preserva existência e geração. Não cria tombstone. |
| Exclusão | Encerra a geração presente, produz tombstone e mantém referência à existência encerrada. Não apaga histórico. |
| `recreate` explícito | Mesmo com dados de negócio idênticos, encerra a existência atual e requer token novo. |
| Equipe efetiva diferente | Preserva token da existência e geração operacional; encerra a geração de vínculo e cria a seguinte. |
| Recriação da equipe com mesmo código | Nova existência/geração da equipe e novas gerações de vínculo de seus registros dependentes. |
| Retorno à equipe anterior | Avança novamente a geração durável; não reapresenta a geração de autorização antiga. |
| Referência alterada dentro da mesma equipe | Registra mudança do caminho de dependência, preservando a geração. |

O token nunca é derivado do código. Alocação ou histórico que use o próprio
código como token é recusado, assim como tokens novos repetidos ou já presentes
no histórico, inclusive tombstones. Registros podem conservar o mesmo token em
gerações sucessivas de vínculo: isso não é nova existência.

Histórico completo exige gerações duráveis contíguas desde 1, sem duplicação,
apenas a última geração possivelmente presente, referências históricas de equipe
existentes e correspondência com o inventário anterior. Tokens não podem voltar
depois de outra existência, nem identificar chaves diferentes.

A geração operacional inicial de uma identidade já existente pode ser maior que
1 quando provém de uma baseline 3A confiável. Dentro do histórico completo, a
mesma existência conserva essa geração; uma nova existência avança a seguinte.
Não se confunde esse contador com a geração durável de vínculo.

## E. Dependências reais

As relações verificadas são:

```text
Funcionarios.equipe -> Equipes.codigo
Equipes.responsavel -> Funcionarios.codigo
OrdensServico.funcionario -> Funcionarios.codigo
Acessos.funcionario -> Funcionarios.codigo
Renovacoes.acesso -> Acessos.codigo
Renovacoes.responsavel -> Funcionarios.codigo
```

A equipe de OS/acesso vem do funcionário titular; a equipe da renovação vem do
titular do acesso vinculado. O responsável da renovação é uma referência válida,
mas sua equipe não amplia nem altera o escopo efetivo da renovação.

O planejador recalcula os registros operacionais completos após a operação:

- Transferência de funcionário: OS, acessos e renovações via seus acessos.
- Transferência de acesso para outro titular: acesso e suas renovações.
- Troca do acesso de uma renovação: a própria renovação.
- Recriação de equipe: todos os registros ligados àquela geração de equipe.

Mudanças de nome, descrição, sistema, observações ou responsável não criam
gerações sem alteração da existência/equipe efetiva. Um campo derivado `equipe`
no registro não substitui a resolução pelas relações reais.

Excluir uma referência ainda utilizada é recusado pela validação do inventário
final. As cinco abas são sempre exigidas, mesmo numa operação individual, para
não assumir que uma dependência ausente deixou de existir.

## F. Importação

O plano recebe os inventários anterior/final e a lista exata de chaves do upload,
sem abrir XLSX e sem modificar o importador existente.

- `new`: chave inexistente é criação; chave existente é `ignored_existing` e
  precisa permanecer inalterada no inventário final.
- `upsert`: chave nova é criação. Para cada chave já existente, `continuations`
  deve declarar explicitamente que a operação atualiza a existência atual.
  O resultado será `updated` ou `unchanged`.
- Registros fora de `targets` precisam permanecer iguais no inventário final.
- Ausência no upload não autoriza exclusão. Não existe modo de substituição total.
- Alteração de funcionário/equipe importada gera os efeitos indiretos normais.
- Várias abas podem introduzir referências entre si, desde que o inventário
  final completo seja consistente.

`continuations` é uma declaração de intenção do **coordenador confiável**, não
prova de linhagem fornecida pelo navegador. Sem ela, um upsert de registro
existente é recusado. O coordenador futuro ainda precisará comprovar continuidade
externa antes de construir essa declaração. Recriação deve ser descrita como tal,
em vez de ser escondida num upsert.

UUIDs e campos derivados vindos de linhas não são lidos como identidade. Campos
textuais extras participam do fingerprint, mas não autorizam alocações ou vínculos.

## G. Compatibilidade com a 3C.2A

O módulo novo não importa o repositório, schema SQLite, serviços operacionais ou
3A. Importa somente constantes de `services.schema` e biblioteca padrão.

### Informações já produzidas

- Chaves, tokens fornecidos/pendentes e gerações duráveis das identidades finais.
- Equipe efetiva e geração da equipe.
- `operational_generation` independente da geração de vínculo.
- Tombstones e invalidações planejadas de gerações anteriores.
- Dependências, motivos e precondições representadas por fingerprints/contexto.

### Conversão futura, não implementada

Após resolver todas as alocações, verificar que o estado atual ainda corresponde
ao analisado e autorizar a operação, o coordenador poderá mapear:

- Equipes finais para `TeamIncarnation(code, incarnation)`.
- Registros finais para `RecordIncarnation(module, code, incarnation, team_code,
  operational_generation)`.
- O conjunto completo para `IdentityManifest`, com época e **próxima** revisão
  de origem e token/recibo novos atribuídos pelo coordenador.

As gerações duráveis são previsões que deverão ser confrontadas com o histórico
persistido; não são campos adicionais inventados para o DTO `RecordIncarnation`.
O `sync_identities` atual calcula essas gerações a partir do manifesto completo.
Ausências no manifesto final representam exclusões, enquanto o plano mantém
explicitamente os tombstones que deverão resultar delas.

Os testes conferem estaticamente os campos dos DTOs reais por AST, sem importar
ou chamar o repositório. Não foi executado `sync_identities` ou qualquer SQL.
Esta é compatibilidade conceitual/de formato, não homologação de aplicação
transacional do plano na 3C.2A.

### Prevenção de aplicação sobre estado diferente

O coordenador futuro deve, sob lock/controle de concorrência:

1. Validar a âncora e o contexto atual, incluindo época/revisões/token.
2. Reobter inventário e histórico confiáveis e conferir seus fingerprints.
3. Conferir a operação, o inventário proposto e as alocações correspondentes.
4. Replanejar e comparar `plan_fingerprint` se qualquer entrada tiver mudado.
5. Só confirmar com recibo idempotente e verificação condicional do estado anterior.

Os hashes usam ordenação canônica de módulos, códigos, histórico e chaves da
operação. Não dependem da ordem de linhas recebidas. Não são assinatura, prova
de autorização, lock ou proteção contra um chamador que forneça todo um estado
antigo falsamente apresentado como confiável.

## H. Testes executados

```powershell
python -B scripts/testar_planejador_identidades.py
# Ran 55 tests ... OK

python -B scripts/testar_contrato_destinatarios.py
# Ran 116 tests ... OK
```

O executor P1 contém **53 testes do planejador + 2 de isolamento**. A primeira
rodada tinha 48 testes aprovados; a revisão acrescentou sete casos adversariais,
todos aprovados na rodada final. Não houve falha automatizada a corrigir.

Cobertura: quatro tipos de criação, edição/no-op, exclusões, tombstones,
recriações, retorno à equipe, efeitos indiretos, caminhos distintos dentro da
mesma equipe, importações nos dois modos, continuidade ambígua, upload ausente,
referências inválidas, duplicações, histórico incompleto/incompatível, gerações
inválidas, tokens atuais/históricos/repetidos, código como token, determinismo,
entradas não modificadas e resultado profundamente imutável.

O teste de bootstrap usa somente inventário vazio e uma importação completa
fictícia em memória. Não cria baseline real nem dispensa histórico para um
inventário anterior já existente.

O executor reutiliza o audit guard do runner puro anterior e acrescenta bloqueios
de importação. Proíbe **todas** as escritas e mutações de arquivo, uma restrição
mais forte que permitir somente temporários. Bloqueia conexões SQLite inclusive
em memória, rede/SMTP/processos, leitura de `dados`/`instance`, Flask, aplicação,
autenticação, Excel/importação, enterprise, repositório/schema 3C.2A e mail.
Os bloqueios são exercitados em testes; tentativas são recusadas antes do acesso.

Não foram executados os testes de persistência 3C.2A, o executor geral ou o
bootstrap frontend de `AGENTS.md`, pois esta fase proíbe SQL e inicialização
operacional. A suíte pura anterior 3A/3B/3C.1 foi reexecutada separadamente e
passou nos 116 testes. Não houve modificação visual nem validação visual.

## I. Integridade e isolamento

O shell leu hashes, fora dos processos de teste, antes e depois da implementação/
validação: os **19 arquivos preexistentes** em `dados` e `instance` conservaram
caminhos, tamanhos e SHA-256. Não surgiram auxiliares SQLite nesse inventário.
Isso não envolveu abrir conexões SQLite, ler células ou consultar dados pessoais.

| Arquivo | SHA-256 inalterado |
| --- | --- |
| `instance/auth.sqlite3` | `5F9AFB9698A639EAE26A3F57BA1F6ECD775704FCE64611AE36AFB432B20A7B62` |
| `dados/dados_dashboard.xlsx` | `4E1AD99271C9BD7D77A7FC406E41B9C540867DF531AE0495F454B072F9752EB1` |

Durante os testes nenhum dado real foi lido: as tentativas explícitas de leitura
nos testes de isolamento foram bloqueadas pelo guard. Não foram criados bancos,
planilhas ou diretórios temporários. Bytecode está desativado. O arquivo de
tentativa de escrita `tests/never-created-p1.txt` não foi criado.

A busca de referências ao planejador encontrou somente seus testes/runner;
nenhum produtor real o importa. Central, notificações históricas, outbox,
autenticação e configurações permaneceram intactas. Nenhum e-mail, SMTP, worker,
agendamento, AWS, deploy ou push foi executado.

## J. Limitações

- O chamador ainda precisa comprovar confiança, atualidade e completude do
  inventário/histórico/contexto. Dataclasses tipadas não constituem autenticação.
- O planejador não detecta sozinho alterações externas que ocorreram e foram
  desfeitas entre observações; precisa receber cada operação confiável em ordem.
- Sem alocação externa de tokens novos, um plano de criação fica pendente.
- A validação cobre identidade/referências, não substitui datas, status, campos
  obrigatórios de negócio, limites de upload ou permissões do CRUD.
- Histórico completo é exigido. Prefixos ausentes, saltos de geração e estados
  incompatíveis são recusados em vez de tratados como nova baseline.
- O contrato é conservador: não permite recriação de funcionário como identidade
  durável, porque tal entidade não existe no registro 3C.2A. Operações normais
  de funcionário são tratadas como fontes de dependências.
- Não há diário, recibo, âncora externa, controle transacional, persistência de
  eventos completos, integração Excel/SQLite ou entrega. Nenhuma garantia de
  produção dessas fases foi declarada como concluída.

## K. Próxima etapa

A futura P2 depende de autorização explícita. Ela deverá tratar unidade de
trabalho SQLite, recibos idempotentes, verificação dos fingerprints/contexto,
separação entre produtor técnico e aprovador administrativo e comparação entre
gerações planejadas/persistidas, inicialmente apenas em bancos sintéticos.

Qualquer alteração de schema/repositório requer revisão da migração e seus testes.
Não basta aplicar o plano diretamente no fluxo existente: as limitações
transacionais e de recuperação identificadas na auditoria 3C.2B permanecem.
Não houve avanço para P2, P3, P4, P5, P6 ou P7.
