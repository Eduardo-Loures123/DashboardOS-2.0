# Padronização final da interface — 08/11/2026

## Escopo e arquivos

Alterações pontuais locais, preservando as alterações que já existiam no projeto.

| Arquivo | Correção |
|---|---|
| `static/js/app.js` | Apresentação compartilhada de vencimentos em tabelas e detalhes, sem alterar status operacional. |
| `static/js/filters.js` | Rótulos modernos nos filtros de vencimento, preservando seus valores internos. |
| `static/js/dashboard.js` | Rótulos e cores de vencimento nos relatórios; remoção dos dois ícones nos títulos da agenda. |
| `static/js/icons.js` | Símbolo de documento com renovação no catálogo compartilhado. |
| `static/js/controls.js` | Separação entre seleção e foco de teclado em todos os seletores aprimorados; navegação ignora opções indisponíveis. |
| `static/js/premium-charts.js` | Quinta posição do ranking usa `--dos-red`, compartilhado pelo gráfico, barra, indicador e efeitos. |
| `static/css/refinement.css` | Foco de teclado tracejado, independente do fundo de seleção e do hover. |
| `static/css/midnight.css` | Remoção da faixa lateral; contadores centralizados e expansíveis; fechamento herda o estilo de `.icon-button`. |
| `static/css/sprint-layout.css` | Indicador Urgente usa o vermelho oficial intenso. |
| `tests/frontend.test.cjs` | Regressões para seleção/foco nas listas curtas e pesquisáveis e classificação de acessos. |

## Causas e regras preservadas

- Acessos e Vencimentos já usam `categoria()` no serviço: negativo = Vencido; zero até 30 = Urgente; 31 a 45 = Atenção; acima de 45 = Dentro do prazo. O adaptador visual existente era usado apenas na tabela de Vencimentos. Agora a apresentação é compartilhada. Não foi encontrada divergência de limites que exigisse mudar regras de negócio.
- Os valores históricos de categoria permanecem nas APIs, filtros e exportações. Esta alteração trata a interface; não reescreve registros nem formatos de integração.
- O seletor marcava a primeira opção como ativa ao abrir e aplicava o mesmo fundo de seleção ao estado ativo. Agora apenas a navegação por teclado ativa seu indicador próprio. O símbolo de confirmação continua vinculado exclusivamente a `option.selected`.
- Mantida a pesquisa a partir de oito opções disponíveis e a seleção direta até sete, inclusive em controles inseridos dinamicamente.
- O rosa vinha da quinta entrada fixa da paleta por posição. Somente essa entrada foi substituída pela variável oficial de vermelho.
- Os dois títulos da agenda adicionavam o ícone pelo atributo `icon`. Outros ícones de calendário foram preservados.
- A faixa vinha de `::before`; os contadores não tinham alinhamento flexível nem altura comum; o fechamento tinha um fundo específico que sobrepunha o componente compartilhado.
- O projeto usa um catálogo SVG próprio, sem biblioteca Lucide instalada. Foi adaptado nele o símbolo de documento com setas de renovação, sem dependências novas. Não se afirma que o path adaptado seja uma cópia literal do SVG oficial FileSync.

## Validação

- `scripts/preparar_testes_frontend.py`: fixtures geradas com cópia temporária do Excel.
- `node --test --test-isolation=none tests/frontend.test.cjs`: **91 testes passaram**. A execução padrão estava bloqueada por `spawn EPERM`; aplicada a alternativa prevista em `AGENTS.md`.
- Primeira execução de `scripts/testar.py` no Python global: 162 testes passaram e dois módulos falharam na importação por ausência de Pillow. Reexecução com `.venv/Scripts/python.exe scripts/testar.py`, que já contém Pillow: **181 testes passaram**, em 147,773 segundos. Resultado registrado em `tests/final-ui-python.log`; nenhuma dependência foi instalada.
- `git diff --check` dos arquivos de implementação ajustados e do teste: sem erros. A verificação global aponta linhas em branco finais preexistentes em outros arquivos CSS.

Prévia via `tests/preview_account_premium.py`, com Excel copiado, autenticação em diretório exclusivo, notificações ilustrativas e envio de e-mail desativado:

- Acessos: rótulos padronizados nos temas claro, escuro e automático; abertura de filtro com uma seleção e nenhum foco automático em outra opção.
- Dashboard: paleta verde/ciano/amarelo/roxo/vermelho confirmada por posição; ambos os títulos da agenda sem SVG; captura do dashboard claro inspecionada.
- Central de Notificações: captura escura inspecionada; três categorias sem pseudoelemento lateral; contadores centralizados; botão de fechamento usa estilo compartilhado e reage ao hover.
- Renovações: navegação e presença do SVG na barra lateral verificadas.
- Relatórios: seleção de “Vencimentos futuros” e apresentação dos rótulos modernos na tabela verificadas no navegador.
- Largura de 640 px: Central sem transbordamento horizontal.

## Limites e preservação

A inspeção visual foi amostral. Não foi feita homologação manual de cada formulário, de todas as combinações de filtros, de rankings alternados e de todas as resoluções ou estados da barra lateral. Os testes automatizados cobrem as demais telas, pesquisa, validação, teclado, paginação, filtros e agenda; não substituem inspeção visual completa.

Nenhum comando de deploy, AWS, migração, fila ou envio real foi executado. As alterações desta tarefa são de frontend, testes e documentação. Os testes e a prévia usam cópias temporárias/isoladas. Não houve auditoria remota de AWS nem comparação por hash dos bancos principais antes/depois; portanto, não se declara verificação forense desses ambientes.
