# Vencimentos e importação Excel — implementação local

Data: 08/11/2026. Sem alteração de versão, commit, push ou deploy.

## Auditoria e adaptação aprovada

Os registros operacionais são persistidos por `ExcelService` em `dados_dashboard.xlsx`. O SQLite guarda contas, preferências, snapshots, eventos, notificações e fila de e-mails. O Excel já era a fonte principal dos registros; esta entrega não migra operações para SQLite nem substitui o banco de contas.

Foi solicitada e recebida aprovação explícita para manter essa arquitetura, usar gravação atômica com backup e revalidar a prévia sob bloqueio exclusivo, atualizando apenas os snapshots dos registros importados para suprimir eventos em massa. Não houve criação de tabelas, migração ou mudança das regras SMTP.

As faixas já existem em `categoria()`: negativo; hoje; até 30 dias; 31–45 dias; acima de 45 dias. `operational_events.FOLLOW_UP` já acompanha OS Pendentes e Em andamento e encerra o acompanhamento de Concluídas. Não existe status Cancelada no esquema atual; a importação não inventa nem aceita esse status.

## Arquivos de implementação

| Arquivo | Alteração |
|---|---|
| `app.py` | Consulta/exportação de vencimentos por tipo; filtros específicos de OS; registro das rotas de importação; limite de upload exclusivo dessa rota. |
| `services/deadline_service.py` | Consulta de prazos das OS com regras existentes, sem modificar registros. |
| `services/dashboard_service.py` | Tratamento de acesso legado sem data válida e pesquisa pelos rótulos visíveis de vencimento, inclusive na exportação. |
| `services/excel_service.py` | Escritor compartilhado; opção de preservar campos adicionais já existentes; validação de linha reutilizável; recuperação sob o bloqueio existente. |
| `services/excel_import_service.py` | Verificação do XLSX, normalização explícita, validação, comparação por código e composição da prévia. |
| `services/import_coordinator.py` | Prévia vinculada à sessão, confirmação idempotente, concorrência, backup, diário de recuperação, transação de snapshots e auditoria. |
| `services/import_routes.py` | Rotas de análise, confirmação e cancelamento protegidas por autorização e CSRF. |
| `static/js/app.js` | Alternância dinâmica Acessos/OS, estado independente de pesquisa/filtros/paginação/ordenação e exportação do tipo selecionado. |
| `static/js/imports.js` | Modal, upload, análise, prévia paginada, confirmação, cancelamento, erros e atualização das telas. |
| `static/js/modals.js` | Proteção do fechamento durante análise/confirmação para evitar operações duplicadas ou perda do resultado. |
| `static/js/icons.js` | Ícone de upload no catálogo SVG existente. |
| `static/css/data-tools.css` | Seletor segmentado, modal, rolagem da prévia, rodapé de confirmação e ajustes responsivos restritos aos novos controles. |
| `templates/base.html` | Botão Importar Excel ao lado da exportação, somente para administradores; inclusão dos recursos. |
| `templates/table.html` | Botões Acessos/OS junto ao título de Vencimentos. |
| `scripts/preparar_testes_frontend.py` | Fixture adicional da consulta de vencimentos de OS. |
| `tests/test_excel_import.py` | Testes sintéticos de prazos, arquivos, permissões, integridade, rollback e concorrência. |
| `tests/frontend.test.cjs` | Testes da alternância, isolamento de filtros, falha de carregamento e fluxo explícito de importação. |
| `tests/preview_data_tools.py` | Prévia visual local que usa somente registros e contas fictícios. |

Também foram produzidos logs de validação e um manifesto de hashes dos arquivos principais, sem publicar seus conteúdos neste relatório. As alterações locais anteriores foram preservadas.

## Como funciona Vencimentos

- Acessos continua como seleção inicial. OS usa uma consulta independente, sem recarregar a página inteira.
- Cada tipo preserva seu próprio filtro, pesquisa, ordenação e página. A quantidade por página é mantida. Ao trocar, registros antigos saem da área de resultados enquanto os novos carregam.
- OS apresenta os campos reais, incluindo previsão, funcionário, equipe, dias restantes, situação do prazo e status operacional.
- Os quatro indicadores são calculados sobre os mesmos registros filtrados e pesquisados da tabela, abrangendo todas as páginas.
- OS concluídas exibem **Encerrado**, com aparência neutra, sem entrar nos quatro indicadores. Os dias continuam sendo a diferença real para a previsão; uma diferença negativa não transforma uma OS concluída em vencida.
- Datas legadas ausentes/inválidas exibem **Sem prazo válido**, sem inventar uma classificação. Há indicação separada de registros fora dos quatro indicadores. Essas datas continuam sendo rejeitadas em novas importações.
- Detalhes oferecem acesso ao registro correspondente. Filtros, paginação, edição autorizada, ordenação, rolagem interna e exportação continuam disponíveis.

## Formato suportado

Aceita `.xlsx` com uma ou mais destas abas, usando nomes e cabeçalhos exatos:

| Aba | Colunas persistidas |
|---|---|
| Funcionarios | codigo, nome, equipe, cargo, email, admissao, status |
| Equipes | codigo, nome, responsavel |
| OrdensServico | codigo, descricao, funcionario, abertura, previsao, conclusao, prioridade, status |
| Acessos | codigo, funcionario, sistema, concessao, vencimento, status |
| Renovacoes | codigo, acesso, solicitacao, status, responsavel, observacoes |

O arquivo exportado por Visão Geral e as exportações das telas desses registros são suportados, inclusive Vencimentos por tipo. Colunas calculadas oficiais, como equipe derivada, nome do funcionário, dias, situação e contagens de equipe, são reconhecidas e recalculadas a partir dos dados persistidos. Não são campos editáveis da importação.

Relatórios agregados não são arquivos de cadastro: abas de totais/grupos são recusadas com orientação para usar o formato oficial. Cabeçalhos ausentes, duplicados ou desconhecidos são informados; não há associação automática de nomes externos nem preenchimento inventado. Campos opcionais podem ter células vazias; seus cabeçalhos continuam necessários no formato suportado.

## Fluxo e validação

1. Selecionar o arquivo e um dos modos: **somente novos** ou **adicionar e atualizar por código**.
2. Analisar no servidor, sem gravação de registros, snapshots, eventos ou mensagens.
3. Conferir abas, quantidades, erros com linha/campo/código e alterações propostas com valores antes/depois. As listas de prévia têm paginação para evitar milhares de elementos na interface.
4. Confirmar explicitamente. Havendo qualquer erro impeditivo, o lote inteiro é bloqueado; não há importação parcial de linhas válidas.
5. Receber o resumo real e atualizar a tela a partir dos dados persistidos. Outras abas abertas no mesmo navegador recebem aviso de atualização; novas navegações sempre consultam o servidor sem cache de dados.

Identificação usa `codigo` dentro de cada aba. Nomes e descrições não identificam registros. Códigos não são renumerados nem alterados automaticamente. O modo somente novos ignora os existentes; o outro atualiza apenas colunas do esquema operacional. Registros ausentes no upload, campos adicionais já existentes no armazenamento e todos os registros de outras abas são preservados.

A validação reutiliza `ExcelService.validate`: obrigatoriedade existente, e-mail, status e prioridades conhecidos, referências, previsão após abertura, coerência entre conclusão e status e vencimento após concessão. Relacionamentos são resolvidos após combinar todas as abas; equipes e funcionários novos podem referenciar-se no mesmo lote. Duplicações no arquivo bloqueiam a confirmação.

Datas aceitas: célula nativa do Excel, serial numérico do Excel, `AAAA-MM-DD` e data/hora ISO, preservando o dia informado. `DD/MM/AAAA` é aceito quando o dia acima de 12 torna o formato inequívoco. Datas ambíguas são recusadas com orientação, sem inverter mês e dia. Horários são removidos porque os campos atuais armazenam dias, não instantes.

## Segurança, transação e concorrência

- Backend limita a análise a administradores/superadministradores, inclusive em acesso direto às rotas. Reutiliza autenticação e CSRF existentes; não altera credenciais ou permissões.
- Limites: 5 MB enviados, 32 MB expandidos, 150 entradas ZIP, 5.000 registros, 150.000 células e 32 colunas. Arquivos inválidos, corrompidos, estruturas excessivas, caminhos indevidos, macros, referências externas e declarações XML perigosas são recusados.
- Fórmulas reais e erros de célula são rejeitados. Nenhum código, fórmula ou macro é executado. Texto escapado pela exportação oficial é restaurado como texto inerte e o escritor define explicitamente o tipo textual das células.
- A prévia é mantida no servidor, vinculada à sessão, por dez minutos. A confirmação aceita somente o token; alterações de dados enviadas junto dele são recusadas. Há no máximo oito prévias em memória, uma por sessão proprietária, com descarte das anteriores.
- A confirmação retoma o mesmo bloqueio exclusivo utilizado pelo CRUD, compara o hash do Excel com o da análise e repete a validação. Dados alterados por outra operação exigem nova análise.
- Um backup é criado antes de substituir o Excel. O novo arquivo é preparado separadamente e substituído atomicamente. Snapshots e recibo administrativo são gravados em uma transação SQLite.
- Como dois arquivos distintos não formam uma única transação nativa, um diário durável associa os hashes, o backup e o recibo. Se o commit SQLite falhar, o Excel original é restaurado. Se houver interrupção entre as gravações, a recuperação consulta o recibo antes de permitir novas leituras/escritas/varreduras.
- O bloqueio de arquivo existente pode permanecer após encerramento abrupto do processo. Nesse caso, confirmar que o servidor está parado antes de remover um lock abandonado; na próxima abertura, o diário permite a recuperação. Não remover backups ou diário manualmente durante esse procedimento.
- Confirmação repetida na mesma instância devolve o resultado já concluído, sem nova importação. Duas importações conflitantes são serializadas e a segunda prévia desatualizada é recusada.
- Histórico administrativo utiliza a tabela `audit` existente: ator, data/hora, nome base do arquivo, totais e identificação da operação. Não registra valores de células ou credenciais.

## Notificações: comportamento atual e integração futura

A importação não chama `store.observer`, `scan`, `emit` ou `process_outbox`. Atualiza apenas os snapshots dos acessos/OS efetivamente importados, na transação de confirmação, para que uma varredura posterior não interprete o lote como alterações pendentes de notificação. Eventos históricos, leituras, mensagens e fila existente não são atualizados nem excluídos.

O analisador puro de eventos operacionais continua desconectado da entrega. Em etapa futura, será necessário decidir como registrar um lote, resolver destinatários, tratar eventos superados por novas datas e estabelecer uma baseline de ativação antes de habilitar mensagens. Isso não está ativado nesta entrega. Rotinas de CRUD e regras SMTP existentes foram preservadas.

## Verificação e limites

Os resultados finais dos comandos estão nos logs `tests/import-python.log` e `tests/import-frontend.log`. A suíte Python é executada pelo runner existente `scripts/testar.py`, com a aplicação global inicializada em diretório temporário. A preparação de fixtures usa `scripts/preparar_testes_frontend.py`; Node usa `--test-isolation=none`, conforme `AGENTS.md`, devido ao bloqueio de criação de subprocessos no sandbox.

Cobertura específica: arquivos válidos/ilegíveis/vazios/corrompidos/disfarçados; cabeçalhos; duplicações; fórmulas; referências externas; limites; datas; referências entre abas; dois modos; prévia sem escrita; permissões/CSRF; adulteração do payload; cancelamento/expiração; revalidação; repetição; concorrência entre coordenadores; falha ao preparar/substituir/gravar SQLite; rollback após substituição; recuperação com/sem recibo; preservação de campos legados, contas, histórico e e-mails pendentes fictícios; faixas de vencimento, OS concluídas, datas inválidas e exportação da pesquisa por rótulo visível.

Inspeção real no navegador, usando apenas `tests/preview_data_tools.py`: Vencimentos Acessos/OS; encerramento separado dos indicadores; modal escuro de análise; confirmação de 1 registro novo e 1 atualizado; tabela atualizada com 6 acessos; arquivo inválido bloqueado no tema claro; modal a 390 px com confirmação visível; paginação a 390 px; seletor e barra superior a 1366 px com sidebar recolhida; modo automático. Capturas foram inspecionadas. Não houve rolagem horizontal da página nos tamanhos amostrados; a tabela mantém sua própria rolagem.

Limites conhecidos: homologação visual amostral, sem testar todos os navegadores/resoluções; prévias em memória desaparecem ao reiniciar e exigem que análise/confirmação cheguem ao mesmo processo. Um deployment futuro com múltiplos workers deverá adotar afinidade ou armazenamento compartilhado de prévias antes da publicação. Não foram alteradas configurações Gunicorn/Nginx para resolver isso nesta etapa local. O escritor preserva dados e campos legados, mas, como no CRUD existente, reconstitui o arquivo operacional; não promete conservar formatação manual arbitrária do Excel.

Os hashes dos arquivos principais locais foram registrados antes dos testes para comparação final. Nenhuma chamada AWS, deploy, migração real, envio de e-mail ou processamento da fila principal faz parte do procedimento. A AWS não foi acessada nem auditada remotamente; a confirmação de preservação dos dados locais depende da comparação final de hashes registrada abaixo.

### Resultado final

- Suíte Python completa: **204 testes passaram**, em 165,542 segundos.
- Frontend Node: **94 testes passaram**, sem falhas, em 24,932 segundos.
- Preparação de fixtures concluída; verificações de sintaxe JavaScript e `git diff --check` dos arquivos ajustados sem erros. Avisos de normalização LF/CRLF não são falhas de validação.
- Comparação antes/depois: **5 de 5 arquivos principais idênticos por SHA-256**, incluindo o Excel operacional e o SQLite principal com sua fila histórica. Resultado em `tests/import-protected-after.json`.
- Nenhuma migração necessária ou executada no ambiente principal. Nenhuma alteração em usuários reais, preferências, SMTP, fila histórica, Nginx ou Gunicorn. Nenhum acesso ou deploy AWS; não houve auditoria remota desse ambiente.
- Testes e confirmação visual de importação executados apenas em diretórios isolados, com registros fictícios. A prévia visual foi encerrada após a verificação.
