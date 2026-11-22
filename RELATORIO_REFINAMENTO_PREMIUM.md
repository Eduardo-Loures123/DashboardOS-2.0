# DashboardOS — Correções estruturais e refinamento premium

Implementação exclusivamente local em 05/11/2026. Versão declarada preservada: `2.1.2`.

## Ponto de restauração

Antes das alterações, foram copiados `templates`, `static`, `tests`, `AGENTS.md` e `VERSION` para:

`../_restauracao/premium-refinement-20261105-174035/`

Os dados operacionais e os bancos reais não foram usados para testes de escrita.

## Diagnóstico

Os problemas principais vinham de conflitos entre as folhas de estilo históricas e o tema Midnight: dimensões de sidebar e modais definidas em vários arquivos, controles absolutos no cabeçalho, ícones absolutos nos indicadores, largura mínima global aplicada à tabela compacta, rodapés com fundo sólido no tema escuro e rolagem aninhada em painéis comuns.

`midnight.css` foi reorganizado por componente e ponto de quebra. As regras antigas da central de notificações foram retiradas de `account-premium.css` e reunidas no sistema visual compartilhado. Não foi adicionada biblioteca nem alterado o backend.

## Correções, item por item

| Item | Correção |
| --- | --- |
| 1. Rodapés dos pop-ups | Ações com fundo transparente nos dois temas, sem faixa sólida, borda divisória ou posicionamento sticky. Mantidos alinhamento, contraste, foco e rolagem dos modais extensos. |
| 2. Cabeçalho | Nova estrutura `.page-chrome`: identificação e usuário na primeira região; data e ações em uma linha operacional própria. Grid/Flexbox substituem o posicionamento absoluto dos controles. Cabeçalho sticky no fluxo; em janelas baixas fica no fluxo normal para preservar espaço útil. |
| 3. Ordens urgentes | Tabela de largura integral, `table-layout: fixed`, proporções explícitas para quatro colunas, quebra de textos longos e remoção da largura mínima herdada. A prioridade permanece visível. Não foi escondida uma barra para mascarar conteúdo excedente. |
| 4. Indicadores | Grade com áreas próprias para título, ícone, valor e descrição. Nenhum ícone absoluto. Valores de 1, 3 e 8 dígitos foram verificados em desktop, tablet e celular, nos dois temas. |
| 5. Largura lateral | Expandida em 260 px e recolhida em 76 px, verificadas no navegador. |
| 6. Navegação | Removido o formulário de entrada no modo visitante da barra autenticada. A opção continua no login. Perfil, ajuda, logout, permissões e submenus foram preservados. Navegação sem rolagem interna permanente nas alturas comuns verificadas; a sidebar inteira pode rolar quando a janela é baixa ou a fonte ampliada exige espaço. |
| 7. Roda do mouse | Painéis comuns e tabelas usam altura natural, sem scrollers verticais aninhados. Testes reais com a roda sobre indicadores, gráficos, barras e tabela moveram a página principal. Mantida rolagem justificada em modais e listas extensas. |
| 8. Mostradores secundários | Removida da Visão Geral a seção de oito mostradores, além do painel Atenção operacional. Os indicadores, cálculos e dados continuam na resposta da API. Agenda e gráfico por equipe foram preservados e compactados. |
| 9. Geometria lateral | Cantos externos retos, integração à estrutura, separação vertical discreta e ondas inferiores preservadas. |
| 10. Status das ordens | Rosca compacta centralizada, total central e paleta turquesa/azul/âmbar consistente. Modal analítico proporcional, com total, quantidades, percentuais, barras, contexto e atualização disponível. Seleção por botão ou segmento do gráfico e consulta real das OS com preservação de filtros. |
| 11. Notificações | Cabeçalho compacto com sino linear e descrição real; navegação Todas/Não lidas/Lidas; pesquisa, período, seleção, ações, contadores, paginação e estados vazios preservados. Regras de geração, distribuição e envio não foram modificadas. |
| 12. Barras de rolagem | Padrão centralizado com trilho transparente e indicador azul discreto. Chromium usa barras personalizadas de 6 px sem botões nas extremidades; outros mecanismos recebem o padrão compatível de barra fina. Rolagens necessárias permanecem acessíveis. |
| 13. Ícones | Catálogo SVG compartilhado preservado; engrenagem linear revisada, tamanhos por contexto, traços consistentes, remoção de glow forte e substituição de setas textuais do dashboard por SVG. Ações das tabelas usam ícones com `aria-label` e `title`, mantendo consulta, edição e exclusão. A marca não foi alterada. |

As tabelas operacionais também passaram a identificar suas colunas na apresentação, permitindo preservar códigos, status e datas em uma linha e quebrar nomes e textos onde apropriado. A tabela Funcionários coube no desktop de 1440 px sem rolagem horizontal, sem retirar campos ou ações.

## Arquivos modificados nesta etapa

- `templates/base.html`: cabeçalho, regiões operacionais, navegação autenticada e seta SVG do submenu.
- `templates/dashboard.html`: retirada dos componentes solicitados e links com ícones SVG.
- `static/css/midnight.css`: sistema visual reorganizado, layout, temas, componentes, responsividade, modais, análise de status e scrollbars.
- `static/css/account-premium.css`: remoção dos estilos antigos da central; regras de perfil preservadas.
- `static/js/app.js`: metadados visuais de coluna e botões de ação compactos com nomes acessíveis.
- `static/js/dashboard.js`: retirada da renderização dos mostradores e painel de atenção; legenda de status padronizada.
- `static/js/charts.js`: painel analítico, filtros de consulta, seleção de segmentos, paleta e tooltip com quantidade e percentual.
- `static/js/enterprise.js`: descrição acessível e ícone do cabeçalho da central, sem alterar operações de notificações.
- `static/js/icons.js`: engrenagem linear e catálogo SVG.
- `tests/frontend.test.cjs`: expectativas atualizadas para as remoções autorizadas e três novos testes funcionais.

O repositório já continha alterações locais anteriores. A lista acima distingue o trabalho desta etapa; o diff total em relação ao Git inclui trabalho anterior.

## Testes automatizados

| Execução | Resultado |
| --- | --- |
| `.venv/Scripts/python.exe scripts/testar.py` | 179 testes aprovados |
| `.venv/Scripts/python.exe scripts/preparar_testes_frontend.py` | Fixtures geradas com cópia temporária do Excel |
| `node --test --test-isolation=none tests/frontend.test.cjs` | 75 testes aprovados |
| `git diff --check` nos arquivos trabalhados e rastreados | Sem erro de whitespace |

Total: **254 testes aprovados**. As suítes cobrem autenticação, permissões, dados, CRUD, exportações, perfil, preferências, notificações, pesquisa, filtros, gráficos, modais e navegação. Testes de e-mail usam transportes simulados.

Os novos testes de interface verificam seleção de status com preservação de equipe, prioridade e datas; atualização pela interação com o gráfico; painel com valores zerados; manutenção dos dados dos indicadores retirados; e disponibilidade do modo visitante somente no login.

Logs:

- `../artifacts/refinement-python-tests.log`
- `../artifacts/refinement-node-tests.log`

## Verificação real no navegador

Foi usada a prévia isolada de `scripts/preview_profile_redesign.py`, em loopback, com registros fictícios temporários, bloqueio de rede de saída e e-mail desativado.

- Temas claro e escuro: Visão Geral, Funcionários, Equipes, OS, Acessos, Renovações, Relatórios, Perfil e Ajuda.
- Resoluções representativas: 1672 × 941, 1366 × 768, 1024 × 768, 768 × 1024, 390 × 844 e janela baixa de 1280 × 600.
- Sidebar expandida/recolhida, submenus, menu móvel e fonte ampliada. A alternativa de rolagem da sidebar foi confirmada com fonte extra grande em janela baixa.
- Sem overflow horizontal global nos cenários verificados; tabela urgente sem overflow próprio, inclusive no celular.
- Sem scrollers verticais ativos em painéis, gráficos ou tabelas comuns na varredura das páginas principais.
- Roda sobre KPI, gráfico de linha, tabela urgente, barras e tabela de funcionários: a página principal rolou em todos os casos.
- Cabeçalho sticky confirmado no topo após rolar a página.
- Rodapé de filtro com `background-color: rgba(0, 0, 0, 0)` nos dois temas.
- Botões de consulta do painel analítico abriram `/ordens-servico?equipe=EQ0001&prioridade=Alta&status=Pendente`; os quatro registros da prévia retornados correspondiam aos filtros.
- Hover e clique reais em segmento da rosca exibiram tooltip e selecionaram o status correspondente.
- Central vazia e central preenchida com respostas fictícias interceptadas apenas na prévia: pesquisa, lista, contadores e rolagem confirmados. Nenhuma limpeza de notificação real foi feita.
- Scrollbar no Chromium: largura computada de 6 px, trilho transparente, thumb azul e botões das extremidades com `display: none`.
- Login, logout, entrada como visitante pelo login, bloqueio de cadastro no visitante e retorno à conta foram confirmados no navegador com a conta temporária.

Não foram observados erros JavaScript na varredura de resoluções. Falhas de sincronização da automação durante navegação foram corrigidas na própria verificação, sem serem tratadas como aprovação visual.

## Capturas

As capturas reais estão em `../artifacts/`, com prefixo `refinement-`:

- `refinement-dashboard-dark.png` e `refinement-dashboard-light.png`
- `refinement-status-dark.png`, `refinement-status-light.png` e `refinement-status-mobile.png`
- `refinement-notifications-dark.png`, `refinement-notifications-light.png`, `refinement-notifications-populated.png` e `refinement-notifications-mobile.png`
- `refinement-filters-dark.png` e `refinement-filters-light.png`
- `refinement-perfil-dark.png` e `refinement-perfil-light.png`
- `refinement-funcionarios-light.png`
- `refinement-navigation-collapsed.png` e `refinement-navigation-mobile.png`
- Demais capturas das páginas operacionais nos dois temas.

As imagens foram inspecionadas e comparadas às referências fornecidas. Elas mostram dados fictícios da prévia, sem substituir os dados do sistema.

## Limitações

Não se declara equivalência pixel a pixel. As referências são imagens e não fornecem arquivos originais de tipografia ou biblioteca vetorial; o refinamento usa o catálogo SVG já existente e a identidade atual. A marca permaneceu inalterada nesta etapa, inclusive por comparação de hash do componente compartilhado com o ponto de restauração.

A inspeção real foi feita no Chromium. Firefox e outros sistemas podem controlar parcialmente as barras de rolagem; foi implementada a alternativa CSS compatível, mas não houve homologação visual nesses ambientes. Em telas estreitas ou janelas baixas, listas/modais extensos e tabelas com muitos campos mantêm rolagem necessária para preservar o conteúdo e a legibilidade.

## Preservação

Nenhum arquivo de backend foi modificado nesta etapa. Nenhuma chamada à AWS, alteração em `deployment/aws`, deploy, push, tag, ativação de worker/agendador ou envio de e-mail real foi realizado. As cinco mensagens antigas pendentes não foram processadas. Nenhum banco real foi recriado, apagado ou migrado, nenhuma credencial ou permissão existente foi alterada e nenhum registro operacional foi modificado para acomodar o design.
