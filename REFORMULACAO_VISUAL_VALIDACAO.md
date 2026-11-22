# DashboardOS 2.0 — reformulação visual local

Branch: `feature/dashboardos-next`. Checkpoint anterior confirmado: `811fce5`.

## Referências examinadas

Leitura integral de `referencias_visuais/CORRECOES_VISUAIS_CODEX.md` e do documento anexado. As dez imagens foram abertas e analisadas individualmente: `01_trace_0.png`, `02_sobreposicao_visao_geral.png`, `03_foco_filtros.png`, `03_foco_cadastro.png`, `03_foco_configuracoes.png`, `04_filtro_equipes.png`, `05_hover_barras.png`, `06_hover_linhas.png`, `06_referencia_pontos_linhas.png` e `07_tooltip_compacto.png`.

## Causas e correções

| Problema | Causa encontrada | Implementação |
| --- | --- | --- |
| 1. trace 0 | Série de relatório sem `name`; legenda habilitada indiscriminadamente. | Nome explícito no relatório, proteção compartilhada para séries sem nome e supressão de legenda redundante em série única. Tooltip mantém nome e valor. |
| 2. Gráficos comprimidos | Shell com altura de viewport, dashboard flexível dividindo apenas a altura restante e gráficos com mínimo zero. Calendário dividia a largura da evolução; rosca tinha duas legendas concorrentes. | Fluxo natural com rolagem da página, gráficos com altura útil de 320/340px, calendário independente, colunas responsivas, rosca de 280px e legenda permanente externa com quantidade e percentual. `ResizeObserver` existente continua recalculando após mudanças do menu/contêiner. |
| 3. Foco cortado | Outline externo de 3px mais offset de 3px dentro de área de modal com overflow e campos rente às bordas. | Anel interno contínuo e arredondado, borda de foco e cores por tema. Controles de navegação mantêm outline externo visível. |
| 4. Filtro Equipes vazio | Formulários tinham duas colunas fixas e modal de até 860px para qualquer quantidade de campos. | Grade adaptativa reutilizável; formulário com um campo recebe modal de até 480px e coluna inteira. Ações no fluxo, sem espaço reservado artificial. |
| 5. Hover de barras | `hovermode: x unified` e `showspikes: true` aplicados globalmente. | Hover próximo sem spikelines, opacidade por categoria, cores originais preservadas e restauração ao sair. Tooltip HTML compartilhado. |
| 6. Hover de linhas | Mesmo hover unificado, sem marcador ativo e sem suavização das séries. | Marcadores nos dados existentes; ponto ativo maior com contorno contrastante, série selecionada vibrante e outras com opacidade reduzida. Áreas têm preenchimento discreto. Nenhuma data, escala, contagem ou ponto fictício foi acrescentado. |
| 7. Tooltip compacto | Tooltip SVG unificado com fonte proporcional, renderizado dentro da área pequena dos gráficos. | Camada HTML flutuante no body ou no próprio dialog da camada superior, com limites de viewport, inversão junto às bordas, quebra de textos e indicadores coloridos. Limpeza de elementos e eventos ao redesenhar/fechar. |

## Reformulação compartilhada

Novo acabamento azul-marinho/laranja, superfícies neutras, cartões com borda e sombra suave, hierarquia tipográfica maior, botões consistentes, formulários adaptativos e modais proporcionais. Navegação lateral com destaque laranja, rolagem e acesso em janelas baixas. Tabelas, perfil, configurações e notificações herdam os componentes compartilhados. Temas claro/escuro/automático, escalas de fonte e redução de movimento continuam usando o mecanismo existente.

Tokens e regras estão centralizados em `static/css/refinement.css`, carregado após o CSS legado. A separação permite revisar ou reverter a reformulação sem alterar regras de negócio. Não houve substituição de tecnologias ou dependências.

## Arquivos alterados

- `static/css/refinement.css`: design system, layout, responsividade, foco e tooltip.
- `static/js/charts.js`: apresentação, nomes, hover, pontos, posicionamento e limpeza.
- `static/js/dashboard.js`: nomes dos relatórios e quantidades/percentuais do status.
- `static/js/modals.js`: detecção reutilizável de formulário com campo único.
- `templates/base.html`: carregamento da folha compartilhada.
- `templates/dashboard.html`: calendário independente e estrutura legível.
- `tests/frontend.test.cjs`: regressões e adaptação das expectativas ao novo hover.
- `REFORMULACAO_VISUAL_VALIDACAO.md`: este relatório.

## Testes

- Fixtures regeneradas pelo script existente, usando cópia temporária do Excel.
- Interface: **38 testes aprovados**, zero falhas e sem atividade assíncrona não tratada na execução final. Inclui fluxos existentes de filtros, pesquisa, ordenação, paginação, cadastros, edição, exclusão, exportação simulada, permissões, configurações e notificações; novas regressões verificam névoa, ponto real, restauração, limpeza do tooltip e modal de um campo.
- Python: **41 testes aprovados**, zero falhas, por `scripts/testar.py`, com cópias temporárias; cobertura de autenticação, permissões, notificações, persistência, Excel, indicadores, filtros e exportações.
- `git diff --check`: sem erros de whitespace; aviso normal de conversão LF/CRLF do Git no Windows.

Comandos usados a partir de `DashboardOS_2.0`:

```powershell
.venv\Scripts\python.exe scripts\preparar_testes_frontend.py
node --test --test-isolation=none tests/frontend.test.cjs
.venv\Scripts\python.exe scripts\testar.py
git diff --check
```

O `npm test` padrão encontrou `spawn EPERM` no sandbox; executar o runner sem isolamento de subprocesso funcionou. A CLI `python -m unittest` encontrou `unittest/main.py` incompleto no Python instalado; o runner alternativo já existente no projeto funcionou sem modificar a instalação.

## Limitação da validação visual

**Não houve inspeção da aplicação renderizada nem novas screenshots.** A descoberta do navegador retornou `The browser access host is unavailable`. A tentativa de selecionar o Chrome pela automação nativa retornou `Computer Use app approval timed out`. As imagens de referência foram visualizadas normalmente; o bloqueio afeta a homologação do resultado implementado.

Os testes DOM usam jsdom e Plotly simulado: comprovam eventos, valores e configurações, mas não comprovam renderização, ausência de clipping, contraste ou desempenho do hover no Plotly real.

Permanece pendente validar manualmente:

- 1920×1080, 1366×768, 1280×720 e janela reduzida.
- Zoom 100%, 125% e 150%; menu expandido/recolhido.
- Temas claro, escuro e automático; fontes pequena, padrão, grande e muito grande.
- Barras e linhas compactas/ampliadas: névoa, pontos, saída do cursor e fluidez.
- Tooltips nas quatro bordas, legendas sem sobreposição e gráfico de rosca.
- Foco via teclado em filtros, cadastro e configurações; modal Equipes proporcional.
- Fluxos reais de cadastro/edição/exportação e notificações exclusivamente em cópia de homologação.
- Console do navegador sem novos erros.

## Executar localmente

Na pasta `DashboardOS_2.0`, com a instalação existente:

```powershell
.venv\Scripts\python.exe app.py
```

Abrir `http://127.0.0.1:5000`. Se já houver um servidor antigo em execução, reiniciá-lo e atualizar o navegador com Ctrl+F5 para carregar os arquivos alterados. Para homologar ações que gravam, apontar `DASHBOARD_EXCEL_PATH` e `DASHBOARD_AUTH_DIRECTORY` para cópias locais de teste existentes antes de iniciar.

Nenhum push, deploy AWS, envio real de email ou migração real foi executado. Nenhuma regra de negócio ou arquivo de dados foi modificado como parte da implementação. Os testes de escrita/migração da suíte existente operam em arquivos temporários.

