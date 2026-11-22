# Rolagem e estabilidade dos painéis — 08/11/2026

Correções locais de frontend. Sem alteração de backend, banco, versão, regras de auditoria/notificações, autenticação, permissões ou sessões. Alterações locais anteriores foram preservadas.

## Causas e correções

**Central de notificações.** O modal e seu corpo permitiam rolagem, enquanto a grade interna tinha altura automática, a lista usava `overflow: visible` e impunha uma altura mínima. Assim, o conteúdo podia expandir a grade e deslocar ferramentas e rodapé.

O corpo agora ocupa o espaço restante do modal, com `min-height: 0`. A grade limita a linha central com `minmax(0, 1fr)`; a lista recebe a rolagem vertical. Cabeçalho, filtros, ações e paginação ficam fora da região rolável. Os layouts menores continuam em Grid, evitando que a regra móvel volte a expandir o conteúdo. A altura responsiva e o limite máximo já existentes do modal foram preservados. Mudanças de página/filtro reiniciam a lista no topo.

**Meu perfil → Atividades.** Os registros e a paginação eram inseridos no mesmo elemento, sem restrição da altura do histórico. O crescimento da lista empurrava o rodapé.

A paginação passou a ser irmã da lista. Somente a aba Atividades usa uma cadeia Flexbox com espaço vertical limitado à janela e `min-height: 0` nos ancestrais. As demais abas preservam seu fluxo anterior. Um `ResizeObserver`, combinado com o evento de redimensionamento, ajusta o mínimo necessário quando há mudanças de layout, preservando espaço para um registro completo. Em janelas com até 800 px de altura, reduzem-se apenas os espaços verticais do perfil enquanto Atividades está ativa; fontes, avatar, cores, controles e informações permanecem. Não há medição contínua durante a rolagem.

**Agenda Operacional.** A lista usava `overscroll-behavior: contain`. Esse bloqueio impedia o encadeamento ao atingir seus limites. A regra foi alterada para `auto`. Não foi necessário adicionar listeners de `wheel`, cancelamento de eventos ou uma simulação de transferência por JavaScript. Calendário, eventos, vínculos, status e animações não foram modificados.

## Arquivos modificados

| Arquivo | Ajuste |
|---|---|
| `static/css/midnight.css` | Dimensionamento e distribuição das regiões da Central; eliminação da rolagem concorrente nos ancestrais. |
| `static/css/profile-redesign.css` | Histórico limitado, rodapé separado e adaptação vertical restrita à aba Atividades. |
| `static/css/agenda.css` | Encadeamento nativo da rolagem da agenda. |
| `static/css/scrollbars.css` | Classe compartilhada `record-scroll-region`, com mínimo zero, rolagem vertical e espaço para a barra. |
| `static/js/enterprise.js` | Aplicação da região rolável acessível à lista e retorno ao topo após atualizar os resultados. |
| `static/js/profile.js` | Separação da paginação, atualização dos resultados e observação das dimensões do layout. |
| `tests/frontend.test.cjs` | Regressões de paginação independente, filtros, estados vazio/com registros e troca de abas. |
| `RELATORIO_ROLAGEM_PAINEIS.md` | Este relatório. |

Os logs e manifestos de verificação foram salvos em `tests/scroll-*.log` e `tests/scroll-protected-*.json`.

## Barras e componentes compartilhados

As listas reutilizam a barra fina azul/ciano já definida em `scrollbars.css`: trilho transparente, cantos arredondados, sem setas e sem ocultar o indicador. O navegador confirmou trilho `rgba(0, 0, 0, 0)` e ausência de transbordamento horizontal na lista de notificações. As regiões receberam foco de teclado e nomes acessíveis.

A revisão encontrou tabelas e áreas de gráficos já configuradas para encadeamento natural; não foi necessário alterá-las. O isolamento de rolagem de seletores e de outros modais foi preservado. Nenhuma regra global removeu bloqueios de interação necessários a esses componentes.

## Testes e resultados

- Runner existente `scripts/testar.py`: **204 testes Python passaram**, em 176,261 segundos. A inicialização global da aplicação foi isolada em diretório temporário; os testes de escrita usam seus ambientes de teste.
- `scripts/preparar_testes_frontend.py`: fixtures preparadas com cópia temporária do Excel.
- `node --test --test-isolation=none tests/frontend.test.cjs`: **96 testes passaram**, em 27,049 segundos. Inclui paginação, busca, filtros, seleção/marcação de notificações, abertura/fechamento, troca de abas e regressões das funcionalidades anteriores.
- Verificação de sintaxe JavaScript e `git diff --check` dos arquivos rastreados ajustados: sem erros.
- Navegador Chromium real: HTML/recursos locais, respostas de API simuladas e registros fictícios. Nenhuma ação visual acessou as rotas de escrita da aplicação real. Capturas dos painéis foram inspecionadas.

### Matriz de layout no navegador

Cada linha foi testada nos temas **claro e escuro**, aguardando a conclusão das animações de abertura antes de medir.

| Resolução | Histórico de atividades | Altura total da página de atividades | Paginações durante rolagem |
|---|---:|---:|---|
| 1920 × 1080 | 384 px, rolável | 1080 px | Fixas nos dois painéis |
| 1366 × 768 | 190 px, rolável | 768 px | Fixas nos dois painéis |
| 1280 × 720 | 94 px, rolável | 720 px | Fixas nos dois painéis |

Na Central, a lista ficou rolável com os cartões excedentes; modal e corpo não apresentaram transbordamento vertical concorrente. Pesquisa, ferramentas e rodapé permaneceram no mesmo lugar. Foram verificados 0, 2 e 80 registros, navegação entre páginas, pesquisa sem resultados e reabertura.

Em Atividades, foram verificados 60 registros fictícios, paginação, pesquisa com um resultado, estado vazio, filtros e alternância para Dados da conta e de volta. O crescimento da quantidade de registros não aumentou a altura da página nas resoluções da matriz.

Na agenda, eventos `wheel` enviados pelo Playwright comprovaram:

1. Rolagem da lista enquanto havia conteúdo interno disponível.
2. Continuação para baixo movimentando a página após o fim da lista.
3. Continuação para cima movimentando a página após o início da lista.
4. Lista com apenas um evento permitindo rolar diretamente a página.
5. Navegação entre meses funcionando.

O teste de encadeamento incluiu espaço adicional somente na página de teste, garantindo que o ancestral tivesse conteúdo para rolar em ambas as direções. Não foi adicionado espaçamento à aplicação para produzir esse resultado.

## Preservação e limites

Os **6 arquivos principais monitorados** antes/depois permaneceram idênticos por SHA-256, incluindo Excel operacional, SQLite principal e `VERSION`. Portanto, não houve alteração desses dados locais, da fila histórica contida no SQLite ou da versão. Nenhum comando de commit, push, deploy, envio de e-mail ou processamento da fila principal foi executado. AWS não foi acessada.

A inspeção visual usou fixtures e APIs simuladas; não representa uma nova homologação completa das integrações de backend, que não foram alteradas. Os testes automatizados existentes passaram separadamente.

Não houve teste com um touchpad físico, Safari ou Firefox. O efeito de mola continua a cargo do navegador/sistema operacional; não foi substituído por uma animação nova. Em alturas extremas ou com fontes muito ampliadas, a página pode precisar de rolagem residual para acomodar os controles, mantendo o histórico limitado e evitando sobreposição.

### Roteiro manual complementar

1. Com touchpad físico, abrir uma data com muitos eventos; manter o cursor na lista, chegar aos dois limites e continuar o gesto. A página deve receber a continuação quando houver espaço disponível.
2. Repetir com poucos eventos e confirmar que a página se move imediatamente.
3. Testar fontes ampliadas e janelas mais baixas que 720 px, verificando acesso aos filtros, paginações e botão de fechar.
4. Repetir abertura, filtros e navegação entre páginas em outros navegadores antes de uma futura publicação.
