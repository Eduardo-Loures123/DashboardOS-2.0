# Etapa 3A — Regras operacionais isoladas

Implementação local em 04/11/2026, sem ativação na aplicação. Esta etapa termina na análise de inventários em memória: não cria linhas em `events`, `notifications` ou `outbox`.

## Arquitetura e arquivos

Foram examinados os serviços empresariais, faixas do dashboard, esquema das planilhas, validações Excel, consulta de renovações e executor isolado da Etapa 2.

Arquivos criados:

- `services/operational_events.py`: funções puras de classificação, transição consolidada, identidade e superação de eventos.
- `tests/test_operational_events.py`: 34 testes novos com registros fictícios em memória.
- Este relatório.

Arquivo modificado:

- `scripts/testar_notificacoes.py`: inclui a nova suíte na seleção padrão. As proteções contra rede e bancos fora da pasta temporária foram preservadas.

O novo módulo reutiliza `dashboard_service.categoria` e os estados de `schema.STATUS`. Não foi conectado ao scanner antigo, observador Excel, rotas Flask, comandos de processamento ou transporte SMTP. O comportamento atualmente ativo da aplicação continua o anterior; os eventos consolidados só são devolvidos quando a nova função é chamada explicitamente.

## Contrato reutilizável

`analyze_operational_events(raw, previous=None, now=None)` recebe as três coleções completas (`OrdensServico`, `Acessos`, `Renovacoes`) e devolve `OperationalAnalysis(events, snapshot)`.

- `previous=None` significa primeira ativação e estabelece apenas referências.
- O próximo processamento deve receber o `snapshot` devolvido pelo anterior.
- O snapshot é serializável em JSON e pertence ao chamador. O módulo não salva arquivo nem abre SQLite.
- `equivalent_events` compara identidades lógicas; `is_superseded` identifica eventos substituídos ou cujo registro foi removido.
- O retorno contém eventos neutros, sem destinatários, filas ou canais. Uma projeção interna e outra para resumos por e-mail poderão consumir os mesmos fatos separadamente na etapa futura.
- `SNAPSHOT_FORMAT` identifica somente o contrato em memória; não é versão do sistema nem migração do banco.

Inventário incompleto, código duplicado, estado desconhecido ou data inválida interrompem a análise sem alterar os dados de entrada. Não se interpreta uma coleção ausente como exclusão de todos os seus registros.

## Regras implementadas

### OS e acessos

OS acompanhadas: `Pendente` e `Em andamento`. Acessos acompanhados: `Ativo`.

| Dias restantes | Classificação | Alerta de prazo |
|---|---|---|
| Mais de 45 | Após 45 dias | Nenhum |
| 31 a 45 | 31 a 45 dias | Preventivo |
| 1 a 30 | Até 30 dias | Urgência |
| 0 | Vencem hoje | Específico de hoje |
| Menos de 0 | Vencidos | Específico de vencido |

A primeira ativação não gera evento para registros preexistentes, mesmo urgentes ou vencidos. Depois dessa referência, entradas em faixas de atenção geram um evento da situação atual; saltos não reconstruem faixas intermediárias. Reexecutar a análise sobre o snapshot atualizado não repete o evento. Permanecer na mesma faixa apenas com o passar do tempo não cria novo alerta.

Mudanças simultâneas de status, data e faixa formam um único `OperationalEvent`, com vários motivos. Alterar o vencimento incrementa `date_revision`, inclusive quando a nova data continua na mesma faixa. Mudanças de data ou status podem produzir evento informativo fora da faixa de atenção, mas não um alerta de proximidade.

OS concluída e acesso revogado encerram o acompanhamento de prazo. Alterações posteriores nesses registros podem produzir informação de mudança, sempre sem alerta de prazo. Reabertura/reativação gera um acontecimento consolidado com a situação atual, sem reproduzir notificações antigas.

Novos registros observados após a referência inicial geram evento inicial quando estão em faixa de atenção. Registros novos acima de 45 dias ou já encerrados apenas estabelecem referência, sem alerta inicial de prazo.

### Renovações

Mantidos os seis estados existentes: `Pendente`, `Solicitada`, `Em análise`, `Aprovada`, `Concluída` e `Rejeitada`. A criação após a referência inicial e mudanças de estado são classificadas. Não existe criação retroativa para registros da primeira ativação.

O uso atual do campo `solicitacao` como data da solicitação foi conferido em `schema.py`, `renovacoes_service.py`, filtros do aplicativo, validação Excel e gerador de dados. Não há data imutável de abertura nem histórico de entrada em status; o cálculo usa a data existente, sem inventar prazo de atendimento.

- Um lembrete quando completar sete dias de calendário desde `solicitacao`, se ainda estiver `Pendente`, `Solicitada`, `Em análise` ou `Aprovada`.
- Se a primeira análise posterior ao marco ocorrer depois do sétimo dia, gera um único lembrete da condição atual.
- Solicitações já com sete dias na primeira ativação ficam marcadas como tratadas para esse lembrete, sem disparo retroativo em leitura posterior.
- `Concluída` e `Rejeitada` não recebem lembrete.
- Lembrete e mudança simultânea de estado são consolidados no mesmo evento.
- Após tratado, alterar a data, reabrir ou remover/reinserir o mesmo código não autoriza repetir o lembrete.
- Aprovação não altera o acesso nem presume que seu vencimento foi prorrogado.

### Identidade, superação e relógio

A identidade inclui contrato, planilha, código, geração, revisão e conteúdo relevante da transição. Não inclui o horário de execução. Reanalisar a mesma transição gera identidade equivalente; mudanças diferentes a partir do mesmo checkpoint não colidem. Voltar ao mesmo status depois de outras transições tem uma revisão nova.

Registros removidos conservam tombstones no snapshot. Seu reaparecimento ganha nova geração; eventos antigos ficam superados. O indicador de lembrete já tratado de uma renovação é preservado por código, evitando repetição por exclusão/reinserção.

Datas explícitas são dias de negócio. Datetimes precisam ter fuso e são convertidos para `America/Sao_Paulo`. Não se aceita retroceder o dia de análise em relação ao snapshot, evitando recriar transições por regressão do relógio. Datas/horas sem fuso são rejeitadas. O lembrete conta dias de calendário, não intervalos de 168 horas.

## Testes e execução

Os 34 testes novos cobrem: limites 45/31/30/1/0 e vencidos; passagem do relógio; salto de faixas; status e data simultâneos; revisão da data; encerramento/reabertura/reativação; criação posterior à ativação; todos os estados de renovação; lembrete único e consolidação; aprovação sem prorrogação; replay, serialização JSON, colisões entre transições, tombstones e eventos superados; ausência de mutações/I/O; meia-noite de São Paulo em relação ao UTC; mudança de mês e entradas inválidas.

Uma primeira execução com 66 testes de regras, pipeline e SMTP simulado passou antes dos dois cenários adicionais de identidade e lembrete após reinserção. A execução final completa inclui esses dois cenários adicionais.

No PowerShell, em `DashboardOS_2.0`:

```powershell
.\.venv\Scripts\python.exe -B scripts\testar_notificacoes.py
.\.venv\Scripts\python.exe -B scripts\testar_notificacoes.py --completo
.\.venv\Scripts\python.exe -B scripts\testar_notificacoes.py --frontend-fixtures
node --require ./diagnosticos/etapa3a-20261104-201052/node-no-network.cjs --test --test-isolation=none tests/frontend.test.cjs
```

O executor completo chama `scripts/testar.py` sob isolamento; a preparação frontend chama `scripts/preparar_testes_frontend.py`. As regressões antigas usam uma origem Excel sintética e bancos temporários, sem importar mensagens do banco principal. Há bloqueio de conexões de rede e de SQLite fora da pasta temporária. Os testes novos ainda bloqueiam explicitamente arquivos, SQLite e SMTP em um cenário para verificar que a análise não faz I/O.

Os resultados finais ficam em `diagnosticos/etapa3a-20261104-201052/python-tests.txt` e `frontend-tests.txt`. Testes DOM não constituem homologação visual; nenhuma interface foi alterada nesta etapa.

Resultado final: **119 testes Python aprovados**, incluindo os **34 novos**, e **56 testes frontend aprovados**, sem falhas. `git diff --check` não encontrou erros de whitespace.

## Preservação e reversão

Evidências iniciais: `diagnosticos/etapa3a-20261104-201052/baseline.json`. Cópias anteriores: `before/` nessa mesma pasta, incluindo a versão anterior do executor modificado.

A verificação final compara hashes do SQLite principal, Excel, VERSION, transporte SMTP, serviços e testes existentes. As cinco pendências são verificadas somente por ID, estado e tentativas, sem expor destinatários, códigos, tokens ou conteúdo. Não houve backup/copiação das mensagens para os testes, reserva, cancelamento ou processamento dessas linhas.

Conferência final aprovada: hashes dos arquivos protegidos idênticos aos iniciais; SQLite principal com integridade `ok`; cinco mensagens originais ainda `pending`, com zero tentativas. Em `scripts/testar_notificacoes.py`, foi confirmada somente a inclusão autorizada da suíte nova. Evidências em `preservation.json` na pasta desta etapa.

Para reverter somente esta etapa: restaurar `scripts/testar_notificacoes.py` da cópia `before/scripts/testar_notificacoes.py` e remover os três arquivos novos descritos acima. Não restaurar nem modificar bancos, planilhas ou alterações anteriores do usuário.

## Limitações e Etapa 3B

1. A lógica está isolada: não altera notificações internas existentes e não alimenta fila/resumos reais. Sua integração futura exige autorização.
2. A ausência de persistência definitiva é intencional. Deduplicação após reinicialização depende de o chamador guardar/restaurar o snapshot; a recuperação também deverá confirmar eventos e snapshots atomicamente. Sem checkpoint recuperável, não há garantia de continuidade.
3. O snapshot novo não é compatível diretamente com os snapshots legados do scanner empresarial. A transição de formato, corte de ativação e armazenamento precisam de desenho e testes na próxima etapa, sem reinicialização silenciosa que gere replay.
4. Não há identificador imutável de solicitação nem histórico de abertura. O lembrete usa a data atual de `solicitacao`. Reutilizar um código antigo para uma solicitação diferente é ambíguo; por segurança o indicador de lembrete tratado é mantido. Solicitação genuinamente nova deve usar código novo até haver identidade definitiva aprovada.
5. Regressão do relógio para dia anterior exige correção/decisão do chamador, não é processada silenciosamente.
6. Vínculos entre funcionário e conta, gestores designados, autorização por destinatário e projeções separadas dos canais permanecem para etapa posterior. Nenhuma inferência de nomes/e-mails foi introduzida.
7. A decisão aprovada é **um único resumo por destinatário/dia às 09h00, America/Sao_Paulo**. Não foram implementados agrupamento diário, envio, agendamento ou worker persistente nesta etapa.
8. Integração futura deve excluir as cinco mensagens antigas antes de qualquer reserva/validação mutável, além de preservar os estados incertos e mensagens já aceitas. Nada disso foi aplicado à fila principal nesta etapa.

Nenhum e-mail real foi enviado, nenhuma automação foi ativada e nenhum acesso à AWS foi realizado. Não foram alterados SMTP, credenciais, configurações de produção, interface, versão, banco principal ou Excel real. Não houve migração nem criação de eventos/mensagens reais. Etapa 3B depende de autorização explícita.
