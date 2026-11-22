# Sprint: dez correções visuais e funcionais

Implementação local em 05/11/2026. Versão mantida em 2.1.2. Backup antes das alterações: `../_restauracao/sprint10-20261105/`. Alterações anteriores do projeto foram preservadas.

## Auditoria e execução

Foram inspecionados o template base, a macro da marca, as camadas compartilhadas de CSS, os assets, o ciclo de desenho/redimensionamento do Plotly e os eventos de hover. A execução seguiu: layout compartilhado; pesquisa/scrollbars/tabelas; gráficos; testes e inspeção no preview isolado.

| Correção | Causa identificada e solução |
|---|---|
| 1. Cabeçalho compacto | Duas faixas com padding e altura mínima elevados. O contêiner compartilhado agora organiza título/descrição, operações e identidade em grid horizontal; quebra em faixas menores conforme a largura. Altura medida: 74px em 1672px e cerca de 85px em 1366px. Informações e ações permanecem disponíveis. |
| 2. Gráficos expandidos | Alturas fixas do plot, métricas e cabeçalho excediam o modal. O modal e seu corpo agora usam flex, área central elástica e ResizeObserver existente. Barras, linhas e status couberam sem rolagem interna em 1366×768, 1280×600 e 1024×768. Fechar e indicadores permaneceram visíveis. |
| 3. Tooltip por período | Hover `closest` selecionava uma série; datas nativas do Plotly também podiam diferir na representação do mesmo mês. Hover nativo por X, normalização das datas e detecção do período mais próximo dentro da área de plotagem alimentam o tooltip compartilhado. Todas as séries visíveis aparecem com seus valores reais e cores. Sem linha vertical adicional. |
| 4. Hover circular estável | A detecção dependia do caminho visual transformado. Agora cópias SVG invisíveis e imóveis fazem o hit test; uma tolerância radial de 8–9px preserva as divisões angulares. Somente a superfície visível recebe transform. Aplicado aos dois donuts e ao status expandido. |
| 5. Neon sem cortes | Margens de 10–12px eram insuficientes para deslocamento e brilho, e o SVG limitava sua área visível. Os donuts reservam 24px internos e o SVG permite a dissipação nessa margem. O deslocamento continua dentro do espaço do card. Capturas normais e ampliadas foram inspecionadas. |
| 6. Painéis por equipe compactos | Paddings, donut de 380px, plot de 340px e indicadores altos se acumulavam. Cabeçalhos, gráficos e métricas foram compactados; os painéis passaram de aproximadamente 650–710px para 530–540px na configuração desktop conferida. Títulos, descrições, ondas, cores e informações foram preservados. |
| 7. Scrollbars unificadas | Regras concorrentes definiam larguras de 6/7px e bordas distintas. Essas definições foram removidas e concentradas em `scrollbars.css`: 4px no Chromium/WebKit, indicador ciano arredondado, mínimo de 40px quando suportado, sem botões e trilho/canto transparentes. Mantida a mecânica nativa. |
| 8. Botão lateral | A estrutura em coluna centralizava o botão nos dois estados. O cabeçalho usa grid e o controle fica à direita da marca quando expandido; no trilho, fica centralizado acima do símbolo. O deslocamento horizontal acompanha a transição de largura. |
| 9. Marca restaurada | A macro compartilhada havia sido reduzida ao nome. O símbolo original encontrado em `dashboardos-symbol.svg` foi reutilizado. Uma máscara SVG separa o fundo opaco da imagem; as cores do desenho vêm do asset original. Não foi criada outra logo. A macro é compartilhada por navegação, login e demais usos existentes. |
| 10. Gestão e pesquisa | Padding excessivo na gestão/paginação e foco aplicado no input interno. Cabeçalho e paginação foram compactados; o seletor não quebra “Por página”. `:focus-within` aplica uma única borda iluminada ao componente inteiro; input interno sem outline/borda próprios, com lupa dentro do contorno. Registros continuam sendo a região que rola. |

## Arquivos e componentes

Novos: `static/css/sprint-layout.css`, `static/css/scrollbars.css`, `static/brand/dashboardos-transparent.svg` e este relatório.

Atualizados: `templates/base.html`, `templates/_brand.html`, `templates/login.html`, `templates/reset.html`; `static/js/charts.js`; `static/css/midnight.css`, `static/css/refinement.css`, `static/css/profile-redesign.css`, `static/css/enterprise.css`; `tests/frontend.test.cjs`.

Componentes centrais ajustados: cabeçalho compartilhado, marca, cabeçalho da navegação, pesquisa, paginação, scrollbar nativa, layout de modal de gráfico, tooltip compartilhado, geometria fixa dos donuts e dimensionamento dos painéis premium. Nenhuma biblioteca foi substituída.

O hit test usa geometria preparada por desenho e não reconstrói o gráfico ao mover um segmento. Listeners e cópias invisíveis são descartados na limpeza do gráfico. O tooltip reutiliza o mesmo período enquanto o cursor permanece nele. Movimento reduzido permanece respeitado.

## Evidências de validação

- `scripts/testar.py`: **181 testes passaram**, 108,218s. [Log](../artifacts/sprint10-python.log).
- `scripts/preparar_testes_frontend.py`: fixtures de oito páginas a partir de cópia temporária do Excel.
- `node --test --test-isolation=none tests/frontend.test.cjs`: **79 testes passaram**, incluindo novo teste de valores compartilhados no cartão e no modal. [Log](../artifacts/sprint10-node.log).
- Testes existentes de pesquisa, paginação, ordenação, filtros, formulários, navegação, permissões, modais e operações CRUD continuaram passando em ambiente de teste. Nenhuma exclusão real foi executada.
- Dez páginas abertas e medidas nos temas claro/escuro em 1672×941, 1366×768 e 390×844: dashboard, funcionários, equipes, ordens, acessos, vencimentos, renovações, relatórios, perfil e ajuda. Sessenta combinações sem transbordamento horizontal do documento. Outras vinte combinações com barra recolhida em 1366×768 também sem transbordamento.
- Conferência adicional de cabeçalho de gestão em 1024 e 768px detectou sobreposição de data/ações; a organização foi corrigida, e a nova medição mostrou data terminando antes do início dos botões.
- Doze combinações de gráficos ampliados (três gráficos em quatro resoluções, incluindo 390×844) mantiveram botão de fechar visível e modal/corpo sem transbordamento. No celular há rolagem horizontal própria das barras e organização em duas colunas das métricas; o conteúdo não é recortado nem removido.
- Hover circular testado com cursor parado próximo da borda interna: cinco amostras sucessivas estáveis e exatamente um segmento destacado em ambos os donuts. Status expandido também permaneceu estável. Não depende do caminho visual deslocado.
- Tooltip real em agosto: total 97, concluídas 30, pendentes 34, em andamento 33, obtidos da base fictícia de preview. Posicionamento ajustado para ficar abaixo da legenda/título.
- Scrollbars do documento, tabela, modal, filtros e resultados de notificações: estilo computado de 4px e trilho `rgba(0, 0, 0, 0)`. Captura da tabela inspecionada sem faixa atrás do indicador.
- Rolagem de 400px por wheel na tabela manteve a paginação na mesma coordenada. PageDown também moveu os registros. Pesquisa com foco mostrou outline/borda internos de 0px e destaque no contêiner da lupa e texto.
- Console do navegador: nenhum erro ou warning registrado durante a sessão de inspeção.

## Capturas e inspeção visual

Capturas inspecionadas no navegador/localmente: visão geral, tooltip de evolução, barras normais e ampliadas, acessos, status ampliado, funcionários, navegação recolhida, ajuda no celular, gestão no celular e central de notificações. Abertura e medição das demais páginas não equivalem a inspeção pixel a pixel de todo seu conteúdo.

- [Evolução com tooltip compartilhado](../artifacts/sprint10-shared-tooltip-final.png)
- [Ordens por equipe — escuro](../artifacts/sprint10-orders-dark.png)
- [Ordens por equipe — claro](../artifacts/sprint10-orders-light.png)
- [Acessos por equipe — escuro](../artifacts/sprint10-access-dark.png)
- [Acessos por equipe — claro](../artifacts/sprint10-access-light.png)
- [Barras ampliadas em notebook](../artifacts/sprint10-expanded-notebook.png)
- [Status ampliado com segmento desprendido](../artifacts/sprint10-status-expanded-dark.png)
- [Pesquisa com foco e navegação recolhida](../artifacts/sprint10-search-final.png)
- [Central de notificações](../artifacts/sprint10-notifications-light.png)
- [Gestão no celular](../artifacts/sprint10-management-mobile-final.png)

## Limitações e preservação

A mola não foi simulada. O indicador nativo não oferece compressão animada controlável de forma confiável; substituí-lo exigiria uma representação personalizada com riscos desnecessários para arraste, teclado e acessibilidade. A alternativa adotada é a scrollbar nativa unificada, permitida pela condição expressa da solicitação.

Firefox recebeu `scrollbar-width:thin` e cores com trilho transparente; sua espessura exata e mínimo do indicador são definidos pelo navegador/plataforma. A inspeção efetiva foi feita no Chromium, não em Firefox/Safari nem em touchpad físico. Wheel e teclado foram exercitados por automação. Não há benchmark de todos os dispositivos.

No celular, dez grupos com três valores exigem navegação horizontal no gráfico de barras para manter os rótulos legíveis. Essa é uma adaptação explícita; no desktop conferido não existe rolagem interna dos gráficos expandidos. O painel de acessos existente continua oferecendo seleção e consulta por equipe; não havia modal ampliado desse painel para substituir.

A marca utiliza a imagem raster original incorporada ao SVG, não um novo desenho vetorial. A máscara atua sobre a transparência do fundo; os arquivos originais foram preservados. A qualidade é limitada pela resolução do original, suficiente para os tamanhos de interface conferidos.

Preview e testes usaram arquivos temporários e dados fictícios. Banco real, Excel real, autenticação, permissões, perfis, SMTP, notificações pendentes, agendadores e ambiente AWS permaneceram intactos. Nenhum e-mail foi enviado, nenhuma mensagem pendente foi processada, nenhuma migração ou tarefa agendada foi executada. Não houve deploy, push ou alteração de versão. O preview isolado foi encerrado ao concluir a inspeção.
