# Estabilidade, bugs e refinamento visual

Rodada local iniciada em 05/11 e concluída em 06/11/2026. Versão preservada: 2.1.2. Backup anterior às alterações: `../_restauracao/stability-20261105/`. Trabalho anterior do repositório preservado; sem commit ou publicação.

## Diagnóstico comprovado

O problema crítico foi reproduzido no navegador, com a base fictícia do preview isolado. Quarenta e oito movimentos entre os seis meses do gráfico produziram **2.574 chamadas de `Plotly.restyle`, com pico de 374 chamadas simultâneas**, além da mensagem “Não foi possível atualizar um gráfico. Tente Atualizar.”

O hover personalizado alterava marcadores por `restyle`. Esses desenhos provocavam eventos nativos de hover/unhover, que voltavam a alterar os marcadores. Havia também detecção personalizada por posição do cursor atuando junto dos eventos nativos. A combinação criava realimentação e concorrência de desenhos. A guarda de geração das promises descartava callbacks antigos, mas não cancelava os desenhos já iniciados no Plotly.

Outras causas identificadas:

- Relatórios: `flex:none` no contêiner e altura mínima do plot definida por seletor mais específico impediam a limitação da área central. Centenas de linhas aumentavam tanto o gráfico quanto a tabela. Medir somente a altura do documento não detectava o problema porque o ancestral já limitava a área visível.
- Barras pequenas: a função que construía regiões de interação rejeitava gráficos com uma única série, justamente o formato dos relatórios.
- Cabeçalho: data e operações compartilhavam células sobrepostas; o sino estava agrupado separadamente dos demais botões.
- Seleções: o componente central ativava pesquisa para qualquer quantidade de opções.
- Notificações: amarelo decorativo era definido diretamente no CSS das categorias e dos contadores.

## Correções implementadas

| Componente | Resultado |
|---|---|
| Evolução de OS | Hover altera somente classes e iluminação dos marcadores SVG; não chama `react` ou `restyle`. Uma única detecção por posição atende a área real de plotagem no navegador. O tooltip conserva as quatro séries, valores do período e cores. |
| Ciclo dos gráficos | A interação anterior é limpa antes de redesenhar. Listeners, tooltip, cópias de geometria e callbacks de animation frame são descartados. Sair da área, cancelar o ponteiro, rolar ou perder foco oculta o tooltip. Alterações nativas da legenda renovam a leitura das séries visíveis. |
| Falha de desenho | O último desenho válido é guardado para recuperação. Em falha, a tentativa de restauração é tratada e o estado de desenho sempre é liberado, permitindo nova tentativa. O teste de regressão força uma falha e verifica restauração e retry. |
| Relatórios | Barras com gradientes, arredondamento, iluminação, cores por categoria, valores e percentuais no tooltip. Total representado e contexto de período vêm da seleção existente. Classificação e quantidades originais permanecem intactas. |
| Resultados extensos | Grid/flex com altura disponível definida, gráfico proporcional, cabeçalho da tabela sticky, registros com rolagem própria e rodapé separado. Todos os sete relatórios mantiveram 615px na área de resultados em 1366×768, inclusive os de 99 e 386 linhas. |
| Barras pequenas | Região transparente calculada a partir do desenho real, com altura mínima de interação de 24px e limites horizontais entre categorias. Não aumenta a barra nem altera seu valor ou escala. |
| Barra lateral | Espaçamento compartilhado mais compacto, botões de 36px no desktop e rodapé agrupado. Acompanhamento com os três subitens coube sem rolagem em 1366×768 e 1366×600 no perfil de preview. Rolagem acessível permanece disponível caso uma configuração menor necessite. |
| Cabeçalho | Áreas distintas para identificação/metadados, ações com sino e identidade do usuário. Data dentro da área de identificação. Botões na mesma referência vertical no desktop. Sino fica fora da toolbar que é ocultada em Meu perfil, preservando o acesso à central. |
| Atualizar | Rotação do ícone durante a requisição, conclusão de volta completa, liberação em sucesso/erro e deduplicação enquanto o trabalho está em andamento. Movimento reduzido desativa a rotação. |
| Avatar | Contorno circular ciano e iluminação em hover/foco, cursor de link e nenhuma mudança de posição. Navegação existente preservada; Meu perfil continua sem avatar redundante para a própria página. |
| Acessos Top 5 | Padding horizontal uniforme e destaque por sombra interna, sem alterar dimensões ou encostar no ponto colorido e percentual. Altura e composição do painel preservadas. |
| Seleções | Até sete opções disponíveis: modo simples, não editável. A partir de oito: pesquisa. “Todos” é contado; opções ocultas/desabilitadas não entram no limiar. Mudanças dinâmicas preservam o valor e o select nativo continua sendo a fonte de FormData/validação. |
| Filtros | Aplicar conserva sliders; Limpar utiliza vassoura SVG do catálogo compartilhado. Ações e parâmetros preservados. |
| Paginação | Divisória fixa de aproximadamente 1px pertence ao rodapé compartilhado, incluindo relatórios. Não acompanha a última linha dos registros. |
| Notificações | Contadores e destaque decorativo em azul/ciano. Classes que representam avisos operacionais reais continuam com suas cores semânticas. Contagem, seleção, filtros e gerenciamento não foram alterados. |

## Arquivos modificados

- `static/js/charts.js`: estabilidade do hover, limpeza, recuperação de desenho, acabamento das barras e regiões de interação.
- `static/js/app.js`: execução deduplicada da atualização e ciclo da animação.
- `static/js/dashboard.js`: apresentação dos relatórios, cores, totais e contexto sem reclassificar dados.
- `static/js/controls.js`: limiar global de pesquisa e atualização dinâmica do modo de seleção.
- `static/js/icons.js`: vassoura vetorial e associação da ação Limpar filtros.
- `static/css/sprint-layout.css`: layout compartilhado, tabelas/relatórios, navegação, estados visuais e animação de atualização.
- `templates/base.html`: grupos do cabeçalho e posição da data/sino.
- `templates/relatorios.html`: contexto do gráfico, área acessível dos registros e rodapé fixo.
- `tests/frontend.test.cjs`: sete novos testes de regressão e atualização das expectativas anteriores de pesquisa/hover.
- Este relatório.

Não foram instaladas bibliotecas. Não houve alteração em serviços Python, classificação dos relatórios, schemas ou infraestrutura nesta rodada.

## Testes automatizados

A verificação inicial passou em **181 testes de backend e 79 de frontend**. Durante a implementação, seis expectativas de frontend ainda pressupunham pesquisa em seleções pequenas; foram atualizadas para a nova regra, mantendo validação, teclado e FormData testados.

Validação final:

| Comando | Resultado |
|---|---|
| `.venv/Scripts/python.exe scripts/testar.py` | **181 passaram**, 260,122s — [log](../artifacts/stability-final-python.log) |
| `.venv/Scripts/python.exe scripts/preparar_testes_frontend.py` | Fixtures de oito páginas geradas a partir de cópia temporária |
| `node --test --test-isolation=none tests/frontend.test.cjs` | **86 passaram**, 39,448s — [log](../artifacts/stability-final-node.log) |
| `git diff --check` nos arquivos desta rodada | Sem problemas de whitespace |

Novas regressões cobertas: falha/restauração/retry de gráfico; limiar 7/8 com opções dinâmicas; deduplicação e erro da atualização; ícones diferentes dos filtros; sino acessível em Meu perfil; hitbox de barra pequena em uma série; totais e dados dos sete relatórios.

## Validação efetiva no navegador

- Depois da correção, **60 movimentos entre meses no cartão e outros 60 no modal** produziram zero `react` e zero `restyle` durante o hover. Um tooltip completo atualizou o período e desapareceu ao sair; nenhuma mensagem de falha foi exibida.
- Cinco ciclos de abertura/fechamento do modal terminaram sem modal aberto, tooltip órfão ou tooltip visível preso.
- Filtro real de equipe no preview foi aplicado pelo componente pesquisável e retornou a seleção esperada. Trocas de tema e atualização foram exercitadas.
- Três cliques consecutivos em Atualizar geraram uma única requisição de dados. A animação foi observada ativa durante a operação e inativa após sua conclusão.
- Uma resposta HTTP 503 foi simulada somente no preview: dados anteriores permaneceram, botão e `aria-busy` foram liberados, erro apareceu e uma nova tentativa concluiu. O erro HTTP esperado foi registrado pelo navegador; não foi tratado como falha espontânea da aplicação.
- Sete tipos de relatório alternados, incluindo 99 e 386 registros. A área externa permaneceu constante; a tabela rolou internamente e seu rodapé permaneceu na mesma coordenada ao rolar 500px.
- Exportação real do preview concluída como `relatorios.xlsx`.
- Gráfico temporário de teste com valores 1 e 100: cursor 10px acima da barra mínima apresentou “1 · 1%”, mantendo a geometria da barra inalterada. Esse gráfico não substituiu dados da aplicação.
- Avatar conferido antes/depois do hover: mesmas coordenadas e dimensões, com contorno/iluminação ativos.
- Seleções reais conferidas: equipe com 11 e funcionário com 101 opções pesquisáveis; sistema e situação, ambos com seis opções, simples. Testes automatizados também cobrem 2, 5, 7, 8 e 10 opções.
- **Sessenta combinações** de dez páginas, dois temas e três resoluções (1672×941, 1366×768, 390×844), aguardando o carregamento dos dados: sem transbordamento horizontal do documento, sino oculto ou desalinhamento dos botões no desktop.
- Páginas abertas/medidas: Visão Geral, Funcionários, Equipes, Ordens de Serviço, Acessos, Vencimentos, Renovações, Relatórios, Meu perfil e Ajuda.
- Console pós-correção nos fluxos normais conferidos: sem erros. Os erros da reprodução inicial e o HTTP 503 provocado pertencem aos testes controlados descritos acima.

## Inspeção visual e capturas

Foram efetivamente vistas capturas de Visão Geral com tooltip, navegação completa, relatórios extensos nos dois temas, central de notificações, hover do ranking, gestão no celular e modal de filtros. A medição das demais páginas não é uma afirmação de inspeção pixel a pixel de todo o seu conteúdo.

- [Visão Geral — escuro](../artifacts/stability-dashboard-dark-final.png)
- [Visão Geral — claro](../artifacts/stability-dashboard-light-final.png)
- [Relatório com 386 registros — escuro](../artifacts/stability-report-dark-final.png)
- [Relatório com 386 registros — claro](../artifacts/stability-report-light-final.png)
- [Contorno do ranking de acessos](../artifacts/stability-access-hover-dark.png)
- [Notificações sem amarelo decorativo](../artifacts/stability-notifications-light-final.png)
- [Filtros e ícones distintos](../artifacts/stability-filter-icons-final.png)
- [Gestão no celular](../artifacts/stability-management-mobile-final.png)

## Preservação, limites e pendências

Nenhum problema funcional permaneceu observado nos cenários finais descritos; todos os testes finais passaram. Isso não constitui garantia para todos os dispositivos ou bases de produção. A inspeção ocorreu no Chromium local, sem teste físico de touchpad, Firefox/Safari ou carga de produção. Relatórios móveis mantêm tabela com rolagem própria e layout empilhado; telas muito pequenas podem precisar rolar a página ou o menu para conservar acesso às informações.

Todos os testes de escrita e a navegação usaram dados fictícios e arquivos temporários no preview isolado. Banco real, Excel real, registros, autenticação, permissões, credenciais, SMTP, mensagens pendentes, notificações operacionais e agendadores permaneceram intactos. Nenhum e-mail real foi enviado ou fila antiga processada. AWS, Nginx, Gunicorn e produção não foram alterados. Não houve migração, deploy, commit, push ou alteração de versão. O preview foi encerrado ao concluir a validação.
