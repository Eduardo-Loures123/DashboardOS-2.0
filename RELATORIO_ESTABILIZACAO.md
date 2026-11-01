# Correções e validação — 28/10/2026

O projeto existente foi corrigido no mesmo diretório. Os arquivos originais de cores, fontes, sombras, cartões e ícones foram preservados. Não houve regeneração nem escrita no Excel original. Os cálculos de indicadores e a classificação de vencimentos foram mantidos.

## Ponto de restauração

Antes da primeira alteração, foi criado o arquivo `../_restauracao/DashboardOS_2.0_antes_correcao_20261028_200454.zip`, incluindo o código e o Excel. A integridade do ZIP foi verificada com `ZipFile.testzip()`. O manifesto está em `../_restauracao/manifesto_correcao.json`.

SHA-256 da planilha antes e depois, idêntico:

```text
269c2be4db91bb2e2c176df6960610e30457f0412d5325a8e6791857f82cb5e9
```

Para consultar ou recuperar a versão anterior, extraia o ZIP para uma pasta nova. Pare o Flask antes de substituir qualquer arquivo do projeto. Preserve a planilha atual se houver alterações legítimas posteriores. O diretório não possuía repositório Git; por isso foi usada uma cópia ZIP completa.

## Diagnóstico e correções

| Problema | Causa e correção |
| --- | --- |
| Cliques indevidos em Relatórios e HTML desorganizado | O laço de navegação em `base.html` abria `<a>` sem `</a>`. O parser HTML mantinha o último link ativo em elementos posteriores, inclusive conteúdo dos pop-ups. Os testes reproduziram navegações inesperadas para `/relatorios` e cancelamento dos envios de formulários. As tags foram fechadas corretamente; a regressão verifica que botões, formulários, gráficos, main e dialog não são descendentes de links. |
| Conteúdo dos gráficos ultrapassando sua área | A dimensão interna do Plotly podia participar do dimensionamento do Grid/Flex. `stability.css` define mínimos adequados e separa o conteúdo gerado do tamanho do contêiner. O JavaScript usa largura/altura medidas do próprio contêiner para renderizar novamente quando ele muda. |
| Legendas sem espaço reservado | As margens do gráfico foram ajustadas para acomodar a legenda dentro da área. As escalas continuam fixas, com zoom, pan, seleção e barra de ferramentas desativados. |
| Reabertura rápida de pop-up | O evento assíncrono `close` podia limpar o gráfico da abertura seguinte. A limpeza agora é síncrona antes do fechamento; eventos atrasados respeitam uma nova abertura. Observadores dos gráficos fechados são liberados. |
| Controles durante a inicialização | Filtros e outros controles dependentes dos dados ficavam utilizáveis antes da API responder. Agora começam desabilitados no HTML e só são habilitados após o carregamento. Atualizar permanece disponível após falha. |
| Erros de rede e exportação | Respostas inválidas e falhas de conexão agora geram mensagens. A exportação baixa o arquivo após verificar o HTTP; erros não substituem o dashboard por uma página JSON. |
| Pesquisa diferente da exportação | A tabela pesquisava os nomes exibidos, mas o backend considerava apenas códigos brutos. O filtro de pesquisa agora usa a mesma representação de relações e datas apresentada na tabela. |
| Período inválido pela API | A validação existente no formulário foi complementada no Flask para rejeitar datas inválidas ou invertidas enviadas diretamente. |
| Excel com esquema incompleto | A leitura verifica abas e colunas obrigatórias e informa o problema explicitamente. Todas as abas são lidas por uma única abertura do workbook, reduzindo trabalho repetido. |

`stability.css` é carregado após os estilos existentes. Suas regras tratam distribuição, limites e rolagem interna; não substituem a identidade visual. Os arquivos `style.css`, `components.css`, `responsive.css`, `reference.css` e `icons.js` ficaram byte a byte iguais à cópia de restauração.

## Testes executados

- **Python: 20 testes aprovados**, zero falhas. Última execução: 53,213 segundos. Cobrem as oito páginas, recursos estáticos, links, API, filtros, períodos, indicadores, limites de vencimento, CRUD nas cinco entidades, relações, backups, concorrência, persistência, estados vazios, relatórios e arquivos Excel exportados.
- **JavaScript: 23 testes aprovados**, zero falhas. Última execução: 7,762 segundos. Executam os scripts reais em jsdom com HTML e JSON produzidos pelo Flask. Cobrem menu, atualizar, filtros, aplicar/limpar, cancelamento, pesquisa, ordenação, paginação, detalhes, cadastro, edição, confirmação de exclusão, erro por vínculo, exportação, seletor de relatórios, abertura de cartões, teclado, fechamento, foco e reabertura dos pop-ups.
- **Sintaxe JavaScript:** `node --check` em todos os scripts próprios, sem erros.
- **Preservação:** hash SHA-256 do Excel confirmado idêntico; integridade do ZIP e preservação dos ícones confirmadas.

Os testes de escrita utilizam **cópias temporárias do Excel existente**. O teste específico do gerador cria arquivos separados apenas no diretório temporário e verifica que ele recusa sobrescrever um arquivo existente. Nenhum teste chama o gerador sobre a planilha do projeto.

Os testes DOM simulam rede, diálogo nativo e Plotly; verificam eventos, dados enviados, dimensões encaminhadas e tratamento das respostas. A suíte Flask verifica separadamente os efeitos reais nas cópias Excel. Isso **não equivale a um teste completo de renderização e cliques em um navegador real**.

## Limites e validação visual pendente

A ferramenta de navegador retornou `The browser access host is unavailable`, sem navegadores conectados. Não foram obtidas capturas, inspeção de console real ou medições visuais de sobreposição. A ausência de sobreposição não está certificada nas resoluções abaixo:

| Resolução | Validação visual |
| --- | --- |
| 1920×1080 | Pendente |
| 1600×900 | Pendente |
| 1366×768 | Pendente |
| 1280×720 | Pendente |
| 390×844 | Pendente |

Para concluir a aceitação visual, abrir as oito páginas nessas resoluções e conferir limites dos gráficos/legendas, ausência de rolagem do documento no desktop, rolagem interna de tabelas, pop-ups longos, clique no espaço vazio dos cartões, tooltips, Escape, foco e bloqueio da página de fundo. O comportamento geométrico e a acessibilidade nativa dos diálogos dependem dessa verificação real. Não há falhas conhecidas nas suítes executadas; possíveis problemas visuais restantes não puderam ser investigados nesta sessão.

## Reproduzir

Na pasta do projeto:

```powershell
python scripts/testar.py
python scripts/preparar_testes_frontend.py
npm.cmd ci --ignore-scripts --no-audit --no-fund
npm.cmd test
```

O Node/jsdom é necessário apenas para testes, não para iniciar a aplicação. O executor Python mantém o contorno já existente para o `unittest/main.py` vazio nesta instalação, sem alterar arquivos do Python.

Para utilizar as correções, pare a instância antiga com `Ctrl+C`, execute `python app.py` e atualize a página com `Ctrl+F5` em `http://127.0.0.1:5000`.
