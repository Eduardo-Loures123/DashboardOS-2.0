# DashboardOS — correções finais de interface

Data: 6 de novembro de 2026. Alterações locais sobre a versão existente 2.1.2; nenhuma release ou implantação preparada. As alterações locais anteriores foram preservadas.

## Arquivos modificados nesta rodada

| Arquivo | Finalidade |
|---|---|
| `templates/base.html` | Remover o elemento da data do cabeçalho compartilhado. |
| `templates/table.html` | Oferecer 12/24/48 somente em Equipes; manter 10/20/50 nas outras tabelas. |
| `static/js/app.js` | Padrão 12 em Equipes, remover a escrita da data, separar status visual de categoria temporal e agrupar os indicadores de vencimento. |
| `static/js/charts.js` | Paleta vermelha compartilhada, aplicação às séries de status, posicionamento do tooltip em X/Y e cache das posições dos meses. |
| `static/js/dashboard.js` | Reutilizar o vermelho nos gráficos dos relatórios e nas categorias críticas. |
| `static/css/midnight.css` | Tokens de perigo, badges, exclusão, erros e estados inválidos, incluindo login e recuperação de senha. |
| `static/css/sprint-layout.css` | Recorte da grade, divisória e alinhamento da paginação de Equipes; ocultação localizada da marca; badges sem quebra; tooltip sem captura de eventos. |
| `tests/frontend.test.cjs` | Atualizar expectativas antigas e acrescentar regressões de paginação, vencimentos e posicionamento do tooltip. |
| Este relatório | Registrar implementação, evidências e limites da validação. |

## Correções e causas

1. **Separação dos registros de Equipes.** A grade tinha margens externas e permitia que a pintura dos cartões e seus efeitos alcançasse o limite da paginação. A grade agora usa espaçamento interno, isolamento e contenção de pintura, mantendo o próprio scroll. A paginação permanece como um irmão fora da área rolável, com fundo transparente, sem sombra ou pseudoelementos e com uma única borda superior. O limite inferior da grade coincide com o limite superior da barra.
2. **Centralização da paginação.** O estilo compacto compartilhado aplicava padding somente acima. Em Equipes, o padding passa a ser simétrico e os grupos, o label e o seletor alinham pelo centro via Flexbox. Mantidos os controles de 32 px e a barra de aproximadamente 43 px.
3. **12/24/48.** O seletor compartilhado e o estado JavaScript começavam em 10. Ambos agora dependem da página: somente Equipes começa em 12. O cálculo de páginas e o ajuste da página atual continuam usando o universo filtrado, sem modificar dados. As outras tabelas mantêm 10/20/50.
4. **Data do cabeçalho.** A data era criada pelo template e preenchida por `app.js`. As duas operações foram removidas. A grade do título ficou com uma única coluna; os controles do cabeçalho preservam suas células existentes. Datas dos registros e o horário de atualização no rodapé permanecem.
5. **Vencimentos.** A tabela reutilizava diretamente as categorias temporais e o classificador genérico de badges. Foi adicionada uma função de apresentação, sem alterar as categorias recebidas, datas, dias restantes, filtros, exports ou serviços:

   | Categoria interna existente | Apresentação |
   |---|---|
   | Vencidos, dias < 0 | Vencido, fundo muito escuro e texto branco |
   | Vencem hoje, dias = 0 | Urgente, vermelho |
   | Até 30 dias, dias de 1 a 30 | Urgente, vermelho |
   | 31 a 45 dias | Atenção, amarelo existente |
   | Após 45 dias | Dentro do prazo, verde existente |

   O resumo agrega as duas categorias urgentes. O atributo `title` do badge preserva a categoria temporal para consulta. Hoje continua prioritário, sem virar vencido por comparação de horário. Os filtros continuam apresentando suas faixas temporais originais.
6. **Logo recolhida.** Um estilo posterior voltava a exibir a marca na segunda linha do topo. A marca agora usa `visibility:hidden` e não recebe cliques nesse estado, preservando sua caixa e a posição da navegação. Expandida, continua visível; a abertura do menu móvel também preserva a marca.
7. **Tooltip de evolução.** O posicionamento acima do cursor, limitado pela margem interna superior do plot, prendia o tooltip no eixo Y em grande parte do card. Agora ele acompanha Y pelo seu centro e mantém 18 px de afastamento horizontal, limitado continuamente ao card e à viewport. Isso evita a troca brusca entre acima/abaixo junto às bordas. O agrupamento por mês e as quatro séries permanecem; apenas a posição é atualizada quando o mês não muda. As coordenadas dos meses são calculadas por desenho, sem converter novamente todos os meses a cada movimento. Mantidos o portal no diálogo, `pointer-events:none`, a limpeza dos listeners, os efeitos e os marcadores. Não há chamada a `Plotly.react` no movimento do cursor.
8. **Vermelhos.** O token `--dos-red` era `#ee6575`, e a paleta JS usava `#ff5269`. Agora os gráficos leem o token CSS compartilhado. Linhas, barras e segmentos de OS usam a mesma paleta de status, incluindo tooltips, legendas e relatórios. Os tokens são:

   | Token | Valor |
   |---|---|
   | `--dos-red` | `#ff3030` |
   | `--dos-red-hover` | `#ff4545` |
   | `--dos-red-strong` | `#ff2020` |
   | `--dos-red-dark` | `#b91c1c` |

   Fundos com texto branco usam o vermelho escuro para contraste; ícones no tema escuro usam o vermelho de hover. Badges críticos têm gradiente vermelho escuro; erros, exclusão e bordas de campos inválidos usam os tokens. Os filtros SVG e sombras neon continuam derivados da cor da série, com a intensidade anterior. As categorias legitimamente magenta, como a quinta equipe do ranking, foram preservadas. Não houve substituição indiscriminada de cores nem alteração do backend para apresentação.

## Testes automatizados

- `.venv\Scripts\python.exe scripts/testar.py`: **181 testes aprovados**. Dados temporários/cópias e transportes de e-mail simulados da suíte; nenhum envio real.
- `.venv\Scripts\python.exe scripts/preparar_testes_frontend.py`: fixtures de páginas e APIs geradas com cópia temporária do Excel.
- `node --test --test-isolation=none tests/frontend.test.cjs`: **89 testes aprovados** na execução final, incluindo três regressões novas. A execução convencional foi recusada por `spawn EPERM`; utilizada a alternativa prevista em `AGENTS.md`.
- Regressões novas: 61 equipes artificiais em memória, 12/24/48, redução para três registros, busca vazia, preservação de 10/20/50 em Funcionários; mapeamento das cinco categorias temporais, hoje urgente e categorias internas intactas; tooltip seguindo X/Y, limitado às bordas, com séries agrupadas e sem novos desenhos.
- `git diff --check`: identificou linhas vazias finais já presentes em arquivos fora desta rodada (`premium.css`, `reference.css`, `responsive.css`, `stability.css`, `style.css`); não foram alterados para limpeza fora do escopo.

## Validação real no navegador

Servidor de prévia restrito a `127.0.0.1:5099`, usando o script existente `scripts/preview_profile_redesign.py`: Excel e SQLite fictícios em diretório temporário, e-mail desabilitado e bloqueio de conexões externas. A prévia foi encerrada após a validação.

- Equipes nos temas claro/escuro, larguras 390/1024/1440 e alturas 800/900: sem overflow horizontal da página e sem interseção entre grade e paginação. Controles centralizados no espaço interno da barra; diferença geométrica de 0,4 px em relação ao centro da caixa externa decorre da borda superior de um pixel CSS.
- 61 equipes inseridas somente no estado JavaScript da prévia: 12 cartões e 6 páginas; 24 cartões e 3 páginas; 48 cartões e 2 páginas. A grade manteve 627 px nas três seleções. Pesquisa reduziu para uma equipe e página 1/1. Dez equipes fictícias reais da prévia também foram verificadas, abaixo do mínimo de 12.
- Sidebar recolhida: ocultar/revelar visualmente a marca no mesmo estado manteve a navegação em Y=96 px. Estado expandido inspecionado na Visão Geral. Nenhum arquivo de logo removido.
- Vencimentos: exemplos reais da prévia com 0, 8, 42, 100 e -52 dias; conferidos rótulos, cores, dias e categorias. Resumo fictício: 100 vencidos, 200 urgentes, 100 em atenção, 100 dentro do prazo. Temas claro e escuro, com captura e inspeção visual; corrigida também a quebra de “Dentro do prazo”.
- Evolução: tooltip verificado em meses diferentes, no centro e nas seis posições próximas às bordas do plot, em card e modal. Todas as posições permaneceram dentro do container e exibiram quatro séries. Movimento Y no card produziu posições sucessivas 313/338/363/393/428 px, sem mudar X. No modal, X e Y variaram juntos.
- Evolução nos temas claro/escuro e larguras 1440/390: tooltip visível, quatro linhas, dentro do card. Capturas desktop e móvel inspecionadas. Instrumentação após estabilizar o desenho: 50 movimentos no card e 50 no modal sem novas chamadas a `Plotly.react`.
- Vermelho da evolução confirmado em `#ff3030`, mantendo ciano, verde e amarelo; donut de status com vermelho e neon inspecionado. Badges de prioridade, ícones de exclusão, legenda e indicadores de vencimentos verificados nas capturas.

As evidências ficam em `../artifacts/final-*.png` e `../artifacts/final-interface-node.log`. Destaques: `final-dashboard-tooltip.png`, `final-teams-light.png`, `final-teams-dark.png`, `final-expiry-light.png`, `final-expiry-dark.png`, `final-trend-dark-390.png` e as demais variantes de tema/largura de `final-trend-*`.

## Limites e pendências

- Validação visual executada no navegador automatizado disponível; não foi realizada uma matriz adicional em Firefox/Safari, aparelhos físicos ou todas as combinações de escala de fonte e preferência do sistema operacional.
- Não se afirma inspeção visual de cada gráfico e relatório possível. A paleta de status é compartilhada; foram inspecionados visualmente evolução, donut e indicadores, com testes automatizados para os demais caminhos existentes.
- Capturas de prévia contêm dados fictícios. Nenhuma alteração de dados reais, esquema, autenticação, permissões, notificações, AWS, Nginx, Gunicorn, DNS ou HTTPS foi necessária.
- Não houve incremento de versão, commit, tag, push ou deploy. A solicitação foi tratada como correção local, preservando a versão existente.
