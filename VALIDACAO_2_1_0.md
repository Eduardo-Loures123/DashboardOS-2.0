# DashboardOS 2.1.0 — versão local preparada

Data: 02/11/2026. Branch preservada: `feature/dashboardos-next`.

A implementação incorpora as onze melhorias do documento anexado e preserva as alterações locais da reformulação anterior. Esta versão está preparada para homologação; não foi publicada e não recebeu aprovação visual no navegador.

## Implementação e causas

| Item | Causa ou necessidade | Solução |
| --- | --- | --- |
| 01. Gerenciamento | O fluxo natural da Visão Geral também era usado nas tabelas, somando cabeçalhos, espaços e mínimos de altura ao viewport. | Layout delimitado por `.management-page`: cabeçalho compacto, painel ocupa espaço restante e tabela tem rolagem interna. Em janelas estreitas/baixas, volta ao fluxo de página para preservar legibilidade. |
| 02. Situação das OS | Coluna direita tinha menos conteúdo que os dois gráficos adjacentes. | Resumo de atenção com OS abertas de previsão vencida e previstas entre hoje e sete dias, calculado apenas sobre dados já filtrados. Não duplica o indicador de renovações nem muda a rosca. |
| 03. Agenda | Calendário não aproveitava a largura e não tinha seleção ou registros associados. | Calendário à esquerda, acompanhamento à direita, seleção independente de hoje, navegação de meses/anos e estado vazio. Mostra OS abertas pela previsão, acessos ativos pelo vencimento e renovações em acompanhamento pela solicitação. Não atribui vencimento fictício às renovações. |
| 04. Indicadores | Distribuição automática poderia deixar um cartão isolado. | Cartões proporcionais em composição de sete colunas ou linhas equilibradas 4+3/2+2+3, conforme espaço. Todos os valores preservados; os três status de OS abrem a página com filtro real. Indicadores agregados sem filtro equivalente permanecem informativos. |
| 05. Barras | Hover do Plotly só reconhecia o caminho de cada barra. | Detecção no contêiner, com retângulos lógicos derivados da geometria SVG de cada categoria, até a altura da maior barra. Mantém destaque no espaço acima da barra central menor. Sem camada que intercepte cliques e sem séries/pontos artificiais. |
| 06. Seleções | Select nativo tinha apresentação diferente e não oferecia pesquisa consistente. | Componente compartilhado pesquisável com input imediato, opções selecionadas, estado vazio, mouse, setas, Enter, Esc, fechamento externo e portal no body/dialog. O select original permanece como fonte de FormData, required, disabled, change/input e múltiplos valores. |
| 07. Datas | Acabamento não acompanhava os demais campos. | Estilo compartilhado por tema, tipografia numérica, foco contínuo e indicador nativo de calendário. Preserva teclado, seletor nativo, validação e ISO no backend. `lang=pt-BR` e descrição acessível; a aparência/localização final do popup nativo depende do navegador/SO e precisa de inspeção. |
| 08. Sidebar | Identificação inferior duplicada e Trocar usuário repetia logout. | Removidos somente esses elementos; sair, visitante, perfil, administração, configurações e recolhimento permanecem. Botões/setas de scrollbar ocultados sem trocar a paleta. |
| 09. Marcadores | Clipping do traçado também cortava os marcadores nas extremidades; contorno só era aplicado durante hover. | `cliponaxis=false` nas séries temporais, pontos de 8px e ativo de 13px, contorno de 2px na cor da superfície desde a primeira renderização. O contorno preserva a separação visual entre linha e ponto. Valores, escala e períodos não mudaram. |
| 10. Marca | Cabeçalho global de modal era texto genérico em caixa alta. | Macro compartilhada `_brand.html` reutiliza D/OS, peso, espaçamento e cores do logo existente, adaptando D ao fundo. Versão somente no logo principal; título do modal permanece abaixo da marca. |
| 11. Versão | Número era repetido manualmente na sidebar, login e rodapé. | `VERSION` é fonte única, lida pelo Flask e disponibilizada aos templates e API. Preparada `2.1.0` por adicionar funcionalidades compatíveis. Changelog e instruções para futuras releases em `AGENTS.md`. Nenhuma tag foi criada/publicada. |

O calendário mantém previsões azuis e hoje laranja. A data selecionada recebe anel distinto. A legenda usa indicadores visuais, sem o antigo texto com quadrado literal. Os atalhos de registros usam a pesquisa real por código; os atalhos de status usam o filtro `status` existente, que agora também é inicializado da URL.

## Arquivos principais

- `VERSION`, `AGENTS.md`, `CHANGELOG.md`: versão, processo de release e histórico.
- `app.py`, `services/agenda_service.py`: versão no contexto/API e apresentação operacional somente de leitura.
- `templates/_brand.html`, `templates/base.html`, `templates/login.html`, `templates/dashboard.html`: marca, versão, sidebar, controles e composição da Visão Geral.
- `static/js/controls.js`: seleção universal e atributos acessíveis dos campos de data.
- `static/js/dashboard.js`, `static/js/filters.js`: agenda, resumo, cartões e filtros de URL.
- `static/js/charts.js`: área de grupos, marcadores e ciclo de vida dos tooltips.
- `static/js/settings.js`, `static/js/enterprise.js`: sincronização dos controles e instrução de múltipla seleção.
- `static/css/refinement.css`: componentes compartilhados e regras específicas de gerenciamento.
- `tests/frontend.test.cjs`, `tests/test_premium_21.py`: regressões novas e existentes.

## Validação executada

- **44 testes Python aprovados**, zero falhas, com `scripts/testar.py`.
- **44 testes de interface aprovados**, zero falhas, com jsdom e Plotly simulado.
- Novas verificações: seleção única/múltipla, opções desabilitadas, estado vazio, pesquisa imediata, Enter/setas/Esc, FormData, required, limpeza de erro, agenda, links, seleção de data, dados reais e imutáveis, limite de sete dias, marca/versão, área vazia dos grupos e atributos dos marcadores/datas.
- Regressões existentes continuam cobrindo filtros, CRUD em cópias, exportações, autenticação, perfis/permissões, notificações, preferências e persistência.
- Fixtures regeneradas a partir de cópia temporária do Excel. Nenhum registro de produção foi substituído ou criado para a interface.
- `git diff --check` sem erros; avisos LF/CRLF são do checkout Windows.

Comandos, executados dentro de `DashboardOS_2.0`:

```powershell
.venv\Scripts\python.exe scripts\preparar_testes_frontend.py
node --test --test-isolation=none tests/frontend.test.cjs
.venv\Scripts\python.exe scripts\testar.py
git diff --check
```

O runner Python existente contorna `unittest/main.py` incompleto no host. O runner Node sem isolamento evita a restrição de subprocessos do sandbox. Não foram modificadas configurações de segurança do Windows.

## Homologação visual pendente

A nova descoberta de navegador retornou `The browser access host is unavailable`, com lista de navegadores vazia. Não houve inspeção da aplicação renderizada nem novas screenshots nesta etapa. A automação nativa havia expirado na tentativa anterior. Não é possível inferir aprovação visual a partir dos testes DOM.

Validar em navegador local:

1. Visão Geral, Funcionários, Equipes, OS, Acessos, Vencimentos, Renovações e Relatórios em 1920×1080, 1366×768, 1280×720 e janela reduzida.
2. Zoom 100/125/150%, fontes pequena/padrão/grande/muito grande e sidebar aberta/recolhida.
3. Temas claro, escuro e automático; contraste, foco e movimento reduzido.
4. Tabelas ocupando altura útil sem cortar pesquisa/paginação e sem rolagem principal desnecessária em desktop.
5. Grade dos indicadores, proporções da coluna de situação/atenção e agenda em duas regiões/empilhada.
6. Seleções de filtros/cadastro/edição/configurações/perfil/administração: lista junto às bordas, pesquisa, teclado, múltiplos valores, fechamento e leitor de tela.
7. Calendário nativo de datas no Chrome/Windows, formato brasileiro, teclado e abertura em modais.
8. Plotly real em cartões/modais: geometria da área de grupo, névoa, ausência de flicker, marcadores inteiros e contornados, tooltips e clique para ampliar.
9. Console do navegador sem novos erros; fluxos de escrita/notificações somente em cópia de homologação.

## Execução local

```powershell
.venv\Scripts\python.exe app.py
```

Abrir `http://127.0.0.1:5000`. Reiniciar servidor antigo e usar Ctrl+F5 para carregar os assets atualizados. Para testar gravações, definir `DASHBOARD_EXCEL_PATH` e `DASHBOARD_AUTH_DIRECTORY` para cópias locais existentes antes de iniciar. Nenhuma migração nova é necessária para esta atualização.

## Publicação futura e rollback

Não houve push, tag, deploy AWS, alteração de produção/credenciais, migração real ou envio real de e-mails/notificações. A suíte existente pode executar migrações e envio simulado exclusivamente em diretórios temporários.

Após homologação e aprovação: revisar o diff, preservar as alterações anteriores do checkout, registrar o commit aprovado e então preparar a tag `v2.1.0`. Publicação remota e AWS dependem de autorização específica. Incluir `VERSION`, novos templates, módulo da agenda e assets no mesmo pacote do código; não copiar bancos, Excel, credenciais ou fixtures para o repositório/pacote.

Usar o procedimento existente de backup/implantação do projeto. Esta versão não exige mudança de esquema. O rollback deve restaurar o pacote de código anterior sem restaurar ou sobrescrever dados reais; não usar um restore indiscriminado do checkout, pois já havia alterações locais antes deste trabalho. O número mostrado em cada ambiente corresponde ao `VERSION` do pacote efetivamente instalado; a AWS não muda por haver uma nova versão local.

A chave histórica `DashboardOS_2.0:appearance:v1:` foi preservada intencionalmente para manter preferências existentes; ela não é a fonte da versão exibida.
