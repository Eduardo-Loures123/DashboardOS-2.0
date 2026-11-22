# DashboardOS 2.1.2 — lote de três correções visuais

Validação local em 02/11/2026. PATCH compatível, sem alteração de esquema, regras de negócio, autenticação, credenciais, envio de e-mails ou regras de notificações. Fonte de versão: `VERSION`. A aplicação foi reiniciada localmente e confirmou `data-version="2.1.2"`. Não houve deploy, tag, commit ou publicação remota.

## 1. Gráfico de linhas: causa medida e correção

O marcador normal mede 8 px e cresce para 13 px no destaque. O eixo Y estava em autorange. Ao passar o cursor pelo primeiro ponto azul (40), o Plotly recalculava a folga do eixo para acomodar o marcador maior. Isso mudava a projeção de todos os pontos, embora cartão, contêiner, margens e legenda não mudassem de tamanho/posição.

| Medição no gráfico original | Antes do hover | Durante o hover no primeiro ponto azul |
|---|---:|---:|
| Limite superior do eixo Y | 43,1324713345 | 43,8003220612 |
| Coordenada SVG Y do primeiro ponto | 16,05 px | 19,17 px |
| Altura do contêiner | 340 px | 340 px |
| Altura útil de plotagem | 221 px | 221 px |

O deslocamento aparente de aproximadamente 3,12 px era, portanto, uma mudança de escala provocada pelo tamanho do marcador, não uma compressão do cartão pelo tooltip. O tooltip já estava em uma camada HTML flutuante fora do fluxo. Não foi necessário escondê-lo ou desativar o destaque.

`lineValueAxis()` calcula o domínio a partir dos valores reais, incluindo zero e folga de 10% para o marcador destacado, e desativa autorange durante a interação. Para os dados atuais, o domínio é `[0,44]`. Dados novos e redimensionamentos continuam passando por `drawChart()` normalmente: dimensões e domínio não ficam congelados entre carregamentos. Valores não são modificados.

A inspeção também encontrou uma diferença entre os dados do Plotly e o SVG: a opacidade de destaque era escrita nos dados, mas não persistia em `_fullData` nem no grupo renderizado. O destaque agora também aplica opacidade ao grupo SVG correspondente. Uma geração de interação impede que uma promessa antiga sobrescreva o ponto atual; limpeza e saída restauram a apresentação. Isso não altera coordenadas ou layout.

### Resultado Playwright

- Hover real com mouse: primeiro azul, azul central, máximo laranja, últimos pontos azul e laranja.
- Comparação de cartão, plot, legenda, margens, domínio Y e transforms dos 12 pontos: **nenhuma mudança entre antes/durante/depois** nos casos medidos.
- Em 1600×1000, eixo `[0,44]`, plot com altura 340 px e área útil 221 px; nenhum `Plotly.react()` durante a sequência instrumentada de hover.
- Repetido em 1366×768 e 1024×768. Verificado também o primeiro ponto alto no modal ampliado e em tema escuro.
- Opacidades computadas no SVG final: `[1,0.22]` ao destacar azul, `[0.22,1]` ao destacar laranja; ambas voltam a 1 na saída. Marcador destacado continua com 13 px, normal com 8 px, contorno 2 px.
- Cores `#12395B` e `#FF9F0A`, curvas `spline`, preenchimentos `tozeroy`, rótulos mensais, folga horizontal e tooltip arredondado preservados. `showspikes=false` nos dois eixos.

## 2. Menu: causa e correção

O evento antigo alternava apenas `.shell.collapsed`; a próxima resposta HTML começava expandida. Foi reproduzido: recolher no dashboard e abrir Funcionários resultava em `collapsed=false` e `aria-expanded=true`.

Além disso, paddings, alturas e espaços de elementos com rótulos ocultos variavam. Um gutter de scrollbar reservado na própria sidebar deslocava todos os centros 3,2 px à esquerda, mesmo com os grupos flex centralizados.

`sidebar.js` é carregado no `<head>`, identifica a preferência pelo usuário e aplica `data-sidebar` antes do corpo. A chave é `DashboardOS:sidebar:v1:<chave-do-usuário>`, separada da chave histórica de aparência. `DashboardSidebar.attach()` sincroniza a classe existente e ARIA e mantém um único controlador de clique. O estado é salvo somente no navegador, sem API ou alteração no banco. Falhas de acesso ao localStorage não impedem o botão de funcionar durante a página atual.

O modo compacto tem largura de 80 px, elementos centralizados, áreas clicáveis uniformes, espaçamentos regulares e foco interno visível. Somente a área de navegação rola quando necessário; o rail não reserva gutter. Foi mantido acesso ao perfil existente no modo compacto. Links, formulários de sessão e seus destinos não foram alterados.

### Resultado Playwright

- Recolhido: Funcionários → Equipes → Ordens de Serviço → Acessos → Vencimentos → Renovações → Relatórios → Configurações → Perfil → recarregar. Estado preservado.
- Expandido manualmente: repetida a navegação pelas páginas operacionais, dashboard, Configurações e reload. Estado preservado.
- Primeiro frame observado após uma navegação já tinha `data-sidebar=collapsed` e largura 80 px, antes mesmo da aplicação da classe pelo script de rodapé. Os 18 frames registrados permaneceram com 80 px: sem expansão visual temporária nessa observação.
- Em desktop: todas as áreas medidas com 60×48 px. Em notebook: 60×44 px. Desvio horizontal de todos os centros SVG em relação ao rail: **0 px**.
- Identificação por `title` e nomes acessíveis, `aria-expanded` e rótulo Expandir/Recolher conferidos. Configurações e navegação não expandem o menu.

## 3. Ícones: auditoria e padronização

O sistema misturava SVGs com caracteres de fonte (`↻`, `☰`, `☷`, setas, engrenagem e outros). O Atualizar usava um caractere Unicode, com desenho e métricas dependentes da fonte, sem viewBox controlado. Havia também implementações separadas para a central e tamanhos/paddings diferentes entre contextos.

Foi ampliado o catálogo SVG local existente, sem instalar bibliotecas ou depender de CDN. `iconSvg()` compartilha viewBox 24×24, traço 1,8, pontas/junções arredondadas, `currentColor`, `aria-hidden` e `focusable=false`. `visual-polish.css` define tamanhos por contexto e alinhamento reutilizável. Textos, nomes acessíveis e eventos permanecem no controle original.

Áreas revistas: menu, ações de sessão, toolbar, Atualizar, filtros, exportação, cadastro, paginação, ordenação, ações de tabela, formulários, modais, calendário, expansão de gráficos, perfil, configuração, central e estados de confirmação. A central reutiliza o mesmo catálogo. A logo DOS e o avatar de identidade foram preservados. O indicador de calendário do campo date continua nativo do navegador.

### Resultado visual

- Atualizar com SVG 18×18 px, centralizado, sem corte em normal/foco. SVG 24×24 contém o caminho e a espessura do traço com margem interna.
- Ampliação de renderização CSS em 75%, 100%, 125% e 150%: ícone contido no botão e desvio vertical de centro 0 px em todos os casos.
- Auditoria temporária de todos os caminhos do catálogo em um diálogo de teste na página: bounds mais metade do traço contidos no viewBox. O diálogo de auditoria não faz parte do produto e foi removido após a captura.
- Ícones verificados visualmente em menu expandido/recolhido, perfil, central vazia real, configurações e formulário aberto/cancelado sem envio. Tema escuro e foco também inspecionados.

## Testes e preservação

- `scripts/testar.py`: **51 testes Python aprovados**.
- `scripts/preparar_testes_frontend.py`: fixtures geradas em cópias temporárias.
- `node --test --test-isolation=none tests/frontend.test.cjs`: **56 testes aprovados** na execução final.
- Sintaxe JavaScript e `git diff --check`: aprovados.
- Novas regressões: restauração do menu por usuário, independência da aparência/API, domínio Y estável e dados preservados no hover, uso consistente de SVG e restauração da opacidade dos grupos.
- O import global da aplicação nos testes Python/gerador de fixtures foi isolado inicialmente em diretório temporário; em seguida a variável de diretório foi retirada para permitir o isolamento próprio de cada caso. Escritas das suítes ocorreram apenas em fixtures temporárias.
- Playwright utilizou a sessão autenticada já disponível. Não foram usadas credenciais antigas, não houve criação de conta real nem login automatizado nesta tarefa. Formulários reais foram apenas abertos e cancelados; nenhuma operação de escrita foi enviada.
- SQLite local aberto para auditoria via `mode=ro`; integridade `ok`, sem violações de chaves estrangeiras.

SHA-256 antes/depois da tarefa, idênticos:

```text
SQLite: 3c6a01537edf83edabd4a7e24067cb023fc4aaa61f1cbd172662c9b5d6666b36
Excel:  b0d1abc83a86de6df36b50f90c2009acbb03bf95fd0d61de089460a1151b554b
```

Os hashes comprovam preservação integral dos arquivos reais, incluindo credenciais, preferências e registros SQLite. Nenhuma migração, alteração de e-mail ou regra de notificação foi aplicada. AWS não foi acessada. Não houve publicação GitHub.

## Capturas e medições

- [Menu antes](../artifacts/lote3-menu-antes.png)
- [Gráfico antes](../artifacts/lote3-linhas-antes.png)
- [Menu expandido final](../artifacts/lote3-menu-expandido.png)
- [Menu recolhido final](../artifacts/lote3-menu-recolhido.png)
- [Menu notebook](../artifacts/lote3-menu-notebook-final.png)
- [Hover final com destaque SVG](../artifacts/lote3-linhas-hover-final.png)
- [Hover notebook](../artifacts/lote3-hover-notebook.png)
- [Gráfico ampliado](../artifacts/lote3-grafico-modal.png)
- [Hover escuro](../artifacts/lote3-hover-escuro.png)
- [Atualizar](../artifacts/lote3-atualizar.png) e [foco](../artifacts/lote3-atualizar-foco.png)
- [Catálogo SVG](../artifacts/lote3-catalogo-svg.png)
- [Perfil](../artifacts/lote3-perfil-icones.png)
- [Notificações](../artifacts/lote3-notificacoes-icones.png)
- [Formulário](../artifacts/lote3-formulario-icones.png)
- [Configurações](../artifacts/lote3-configuracoes-icones.png)
- [Medições estruturadas](../artifacts/lote3-medicoes.json)

Capturas foram abertas e examinadas, além das verificações DOM. Algumas capturas de investigação antecedem o ajuste final de ícones e o PATCH; as duas capturas finais do menu mostram a versão preparada. As medições estruturadas distinguem diagnóstico anterior e resultado corrigido.

## Arquivos desta tarefa

| Arquivo | Alteração |
|---|---|
| `static/js/charts.js` | Domínio Y independente do hover, destaque SVG e limpeza |
| `static/js/sidebar.js` | Preferência de menu antes da pintura e controlador único |
| `static/js/app.js` | Integração do controlador e ícones de ordenação/estado de salvar |
| `static/js/icons.js` | Catálogo e helpers SVG compartilhados |
| `static/js/modals.js` | Ícones dinâmicos e limpeza do ícone decorativo da central |
| `static/js/dashboard.js` | SVGs no calendário e links de consulta |
| `static/js/enterprise.js` | Ícones compartilhados em perfil e central, sem mudar ações/APIs |
| `static/js/controls.js` | Chevron e seleção em SVG, mantendo os controles nativos |
| `static/css/visual-polish.css` | Regras compartilhadas de ícones e modo compacto |
| `templates/base.html` | Scripts/estilos, placeholders SVG, nomes acessíveis e perfil compacto |
| `templates/table.html` | Busca e paginação SVG |
| `templates/dashboard.html` | Ícones de ampliação e consulta |
| `templates/relatorios.html` | Ícones de exportação e ampliação |
| `tests/frontend.test.cjs` | Regressões e carregamento do controlador |
| `VERSION`, `CHANGELOG.md` | PATCH local 2.1.2 e histórico |
| Este relatório | Diagnóstico, resultados e evidências |

O checkout já tinha alterações anteriores; elas foram preservadas. Esta lista não atribui a esta tarefa todo o diff existente do usuário.

## Limites da validação

- O atalho de zoom nativo não alterou o zoom do navegador automatizado; a verificação de ampliação usou zoom CSS de renderização, explicitamente registrado. Não é certificação do zoom nativo em todas as versões de navegador.
- Inspeção real no Chromium do Playwright; não foi feita homologação em Safari/Firefox ou em todas as combinações de sistema e escala de tela.
- A administração autenticada não foi aberta com a conta local, que não tem esse papel. Sua estrutura e ações continuam cobertas pelas fixtures administrativas e testes DOM/Flask, sem promover contas reais.
- Não há pendência funcional identificada nas três melhorias dentro dos ambientes e resoluções testados. A aplicação permanece em `http://127.0.0.1:5000`, com o menu recolhido ao término da validação.
