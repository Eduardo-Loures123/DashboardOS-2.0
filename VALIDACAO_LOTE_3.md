# Validacao local - lote de tres correcoes

Data: 02/11/2026. Pronto para teste local; sem publicacao ou alteracao de versao.

## Arquivos alterados neste lote

- static/css/refinement.css: no Chromium, scrollbar customizada em vez do estilo nativo thin que pode reintroduzir setas. Mantidos 7px, cores e overflow existentes. Firefox conserva o estilo fino padrao.
- static/js/charts.js: layout compartilhado de linhas com range horizontal acolchoado, ticks explicitos incluindo primeiro e ultimo mes, densidade responsiva e afastamento dos rotulos dos eixos. Dados originais, cores, hover e marcadores preservados em cartoes e ampliacoes.
- static/js/controls.js: foco nao abre listas; clique, digitacao e setas abrem. Selecao fecha inclusive multisselecao, sem perder os valores nativos. Digitacao inicial preservada ao abrir a pesquisa.
- tests/frontend.test.cjs: regressao de foco automatico, pesquisa, selecao, multisselecao, clique externo, Esc, filtros/criacao/edicao em seis areas e margens/meses extremos dos graficos.
- CHANGELOG.md e este relatorio.

## Testes automatizados

- .venv/Scripts/python.exe scripts/testar.py: 44 testes aprovados, 205,919 segundos.
- .venv/Scripts/python.exe scripts/preparar_testes_frontend.py: fixtures geradas com copia temporaria do Excel.
- node --test --test-isolation=none tests/frontend.test.cjs: 51 testes aprovados, zero falhas, incluindo a verificacao adicional de edicao na execucao final.
- O runner Python informou a limitacao preexistente de unittest/main.py vazio e executou a suite com seu contorno existente.

## Navegador real via servidor MCP playwright

- Inspecao visual de dashboard, filtros, cadastro e edicao de OS, grafico no cartao e ampliado.
- Resolucos inspecionadas: 1440x900, 1024x600 e 390x844. Maio e outubro de 2026 visiveis; em telas estreitas, a densidade dos meses intermediarios diminui sem ocultar os extremos.
- Scroll lateral testado em 1024x600: scrollTop 216,8px de um maximo de 217px; thumb rgb(99,134,164), botao computado display:none; captura visual sem setas.
- Hover real no primeiro marcador: tooltip apresentado e intervalo do eixo conferido, sem alterar as datas das series.
- Varredura Playwright de 17 formularios em funcionarios, equipes, ordens-servico, acessos, vencimentos e renovacoes: listas inicialmente fechadas, foco sem expansao, clique abre e Esc fecha. Vencimentos nao possui criacao, conforme comportamento existente.
- Cadastro/edicao inspecionados em servidor temporario na porta 5001 com Excel e autenticacao em diretorio temporario; nenhum formulario foi salvo. Servidor temporario encerrado apos a validacao.
- A sessao principal foi devolvida ao dashboard local da porta 5000.

## Limites e preservacao

Firefox e Safari nao foram executados; sua renderizacao visual permanece pendente. A validacao visual realizada foi no Chromium disponibilizado pelo MCP. Nao foram alterados os arquivos de dados, regras de negocio, autenticacao, permissoes, notificacoes ou hospedagem; testes de escrita usam copias temporarias. Mudancas anteriores ja presentes no repositorio foram preservadas. Nenhum deploy, commit ou publicacao foi feito.
