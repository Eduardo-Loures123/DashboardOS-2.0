# Notificações e Atividades — correções locais de interface

Data: 08/11/2026. Sem alteração de versão, backend, autenticação, permissões, dados operacionais ou regras de notificações/auditoria. As alterações locais anteriores foram preservadas.

## Causas identificadas

1. **Lixeira gigante:** a confirmação era inserida diretamente na lista de notificações. O SVG não recebia um tamanho específico e a regra compartilhada usava `var(--icon-size)` sem valor padrão; quando a variável não existia, o SVG podia usar dimensões intrínsecas inadequadas.
2. **Botões próximos:** a confirmação não tinha rodapé próprio. Além disso, uma regra compartilhada de formulários tinha especificidade suficiente para impor seu espaçamento às ações. A confirmação precisava delimitar sua área de botões e seu intervalo de 14 px.
3. **Piscada na seleção:** tanto o checkbox individual quanto Selecionar todas chamavam `render()`. Isso removia e recriava os cartões e reiniciava a rolagem, mesmo sem mudança nos dados.
4. **Histórico curto:** o dimensionamento anterior reservava espaço mínimo para apenas um registro. A soma dos cabeçalhos e controles consumia grande parte da janela e deixava pouco espaço para a lista.

## Correções

### Confirmação compacta

Foi criado um componente reutilizável de confirmação em `modals.js`, aproveitando `dialog`, cabeçalhos, ícones, botões e rodapés compartilhados. Ele abre sobre a Central, sem substituir a lista, filtros ou paginação.

- Ícone explícito de **24 × 24 px**; fallback compartilhado dos demais SVGs para 20 px quando não houver tamanho definido.
- Modal centralizado, com largura máxima de 480 px e adaptação à janela.
- Rodapé horizontal com **14 px** entre os botões, altura comum de 42 px e alinhamento dos ícones.
- Cancelar, X e Escape fecham somente a confirmação, sem limpar ou renderizar novamente a lista.
- A confirmação mantém os controles desabilitados enquanto a ação está em andamento e impede execução repetida pelo mesmo diálogo.
- Ação original preservada: a confirmação chama a limpeza já existente da central do usuário. Não foram alterados endpoint, escopo ou regras de exclusão/histórico.
- Erros deixam a confirmação aberta com mensagem e possibilidade de nova tentativa. A restauração do foco usa `preventScroll`, evitando deslocamentos não solicitados.

### Seleção estável

Os checkboxes visíveis são associados aos identificadores das notificações. A seleção atualiza apenas propriedades dos checkboxes, o estado marcado/indeterminado de Selecionar todas e os controles coletivos dependentes.

Não há renderização, remoção de cartões, reinício de animação ou requisição de API para selecionar/desmarcar. Pesquisa, filtros, atualização real de dados e mudança de página continuam usando a renderização apropriada. A posição de rolagem é preservada ao selecionar.

### Histórico ampliado

O cálculo considera a altura real dos registros, os controles do painel, a barra superior e a navegação entre abas. Reserva espaço para até cinco registros quando a janela comporta isso, reduzindo a quantidade em telas menores. Não reduz fonte, padding ou altura dos cartões.

A dimensão não depende do total de registros: páginas de histórico continuam limitadas e a lista mantém rolagem interna. Quando necessário, a navegação normal da página permite percorrer a identidade acima do painel. Ao entrar em Atividades, o painel é trazido para a área visível **após** concluir o carregamento e o dimensionamento, deixando a paginação acessível. Cabeçalho, pesquisa, filtro e paginação ficam fora da lista rolável.

As demais abas mantêm seu fluxo e seus campos. O `ResizeObserver` existente continua respondendo a alterações do layout. Não foram adicionados listeners de roda do mouse, nem alterada a Agenda Operacional.

## Arquivos modificados

| Arquivo | Alteração |
|---|---|
| `static/js/modals.js` | Confirmação reutilizável, controle de execução e foco sem deslocar a rolagem. |
| `static/js/enterprise.js` | Uso do modal de confirmação e atualização pontual da seleção. |
| `static/js/profile.js` | Dimensionamento para múltiplos registros e espera do carregamento antes de posicionar o painel. |
| `static/css/visual-polish.css` | Tamanho padrão seguro para SVGs sem variável de dimensão. |
| `static/css/midnight.css` | Modal compacto, ícone limitado, rodapé e botões responsivos. |
| `tests/frontend.test.cjs` | Regressões de identidade dos cartões, foco, rolagem, cancelamento e confirmação única. |
| `tests/interface_visual.cjs` | Cenários de navegador com APIs inteiramente simuladas e dados fictícios. |
| `RELATORIO_AJUSTES_NOTIFICACOES_ATIVIDADES.md` | Este relatório. |

Logs e manifestos de preservação foram produzidos em `tests/interface-*.log` e `tests/interface-protected-*.json`.

## Validação

- `scripts/testar.py`: **204 testes Python passaram**. A inicialização global foi isolada em diretório temporário; nenhum teste de escrita apontou à base principal.
- `scripts/preparar_testes_frontend.py`: fixtures geradas com cópia temporária do Excel.
- `node --test --test-isolation=none tests/frontend.test.cjs`: **98 testes passaram**. A alternativa sem isolamento segue a instrução existente em `AGENTS.md` para este sandbox.
- Verificação de sintaxe JavaScript e `git diff --check` dos arquivos rastreados ajustados: sem erros.

Os testes DOM verificam seleção individual, desmarcação, seleção múltipla e coletiva, estado indeterminado, identidade dos cartões, foco, posição da rolagem, ausência de requisições de seleção, pesquisa, paginação, cancelamento repetido e confirmação única. Permanecem os testes anteriores de filtros, ações individuais/coletivas, perfil, preferências e demais módulos.

### Navegador real

`tests/interface_visual.cjs` foi executado com Playwright contra arquivos locais servidos em `127.0.0.1:5010`. Todas as requisições `/api/**` foram interceptadas e respondidas em memória. Nenhuma confirmação visual atingiu uma rota real de exclusão.

| Resolução | Tema | Altura útil do histórico | Registros completos |
|---|---|---:|---:|
| 1920 × 1080 | Claro e escuro | 393 px | 5 |
| 1366 × 768 | Claro e escuro | 317 px | 4 |
| 1280 × 720 | Claro e escuro | 240 px | 3 |

Em todas as combinações, a paginação permaneceu estável durante a rolagem e acessível após a entrada na aba. A lista de notificações conservou os mesmos elementos DOM e a posição de 100 px após selecionar/desmarcar individualmente e em conjunto.

A confirmação foi aberta/cancelada repetidamente: ícone de 24 px, botões com alturas iguais, intervalo mínimo de 12 px (configurado em 14 px), Central e rodapé sem deslocamento. Dois cliques consecutivos na confirmação produziram **uma única limpeza simulada**. Cancelar não produziu nenhuma limpeza.

Em **390 × 844**, a confirmação mediu aproximadamente 358 px de largura, sem transbordamento horizontal, com ícone de 24 px e gap de 14 px. Escape fechou a confirmação e manteve a Central aberta. Capturas do modal e do histórico ampliado foram inspecionadas.

## Preservação e limites

Os **6 arquivos principais monitorados** permaneceram idênticos por SHA-256 antes/depois, incluindo Excel operacional, SQLite principal com notificações/fila histórica e `VERSION`. Nenhum commit, push, deploy, envio real de e-mail, processamento da fila principal ou acesso AWS foi realizado.

As regras de barras finas, ciano, sem setas e com trilho transparente foram preservadas. O arquivo de estilos da agenda e seu `overscroll-behavior: auto` não foram modificados nesta tarefa. A Central continua com cabeçalho, ferramentas e paginação fora da lista rolável.

A inspeção visual usou Chromium, fixtures e APIs simuladas; não constitui uma nova homologação integral do backend, que não foi alterado. Outros navegadores, touchpad físico e fontes extremamente ampliadas continuam como validação manual complementar. Em janelas baixas, o número visível é reduzido conforme o espaço real; não há promessa de cinco registros em qualquer resolução.
