# DashboardOS 2.0

Atualização de aparência e autenticação: consulte [ATUALIZACAO_PREMIUM.md](ATUALIZACAO_PREMIUM.md). O acesso agora começa em `/login`. Os dados atuais foram preservados; não execute o gerador para atualizar a aplicação.

Correções de estabilização: consulte [RELATORIO_ESTABILIZACAO.md](RELATORIO_ESTABILIZACAO.md) para diagnóstico, cópia de restauração, resultados dos testes e validação visual pendente. Reinicie o Flask e atualize o navegador com `Ctrl+F5` para carregar as correções.

Aplicação empresarial local em Flask, com oito páginas, dados fictícios e Excel como fonte principal. Criada em uma pasta independente; não altera projetos anteriores. A composição segue a imagem fornecida: painel central, menu azul-marinho com avatar, quatro indicadores, gráficos amplos à esquerda e cartão vertical com rosca à direita. Bordas e componentes têm acabamento arredondado.

## Executar no Windows / VS Code

Abra esta pasta no VS Code (`Arquivo > Abrir Pasta > DashboardOS_2.0`). No terminal PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m flask --app app criar-admin
python app.py
```

Abra **http://127.0.0.1:5000** no navegador. O servidor escuta somente no computador local, sem debug. Para parar, pressione `Ctrl+C`. Se a ativação for bloqueada, utilize diretamente `.\.venv\Scripts\python.exe` em lugar de `python`; não é necessário alterar a política do Windows.

O comando `criar-admin` solicita ID e senha (com confirmação, sem exibir a senha). Use ID de 3 a 64 caracteres, com letras, números, ponto, hífen ou sublinhado, e senha com pelo menos 12 caracteres. Não há credenciais padrão. Execute o comando novamente com outro ID para cadastrar outro administrador. Não passe a senha como argumento no terminal.

Em **http://127.0.0.1:5000/login**, informe o ID e a senha ou clique em **Modo visitante**. O visitante pode consultar, filtrar, pesquisar, ampliar gráficos e exportar relatórios; cadastro, edição e exclusão continuam visíveis e bloqueados, inclusive no servidor. Para trocar de conta ou sair, use as opções na parte inferior da barra lateral. **Trocar usuário** encerra a sessão e volta ao login; **Entrar no modo visitante** revoga a sessão administrativa. No modo visitante, **Fazer login** e **Voltar à tela inicial** encerram a sessão de leitura e abrem o login.

Em **Configurações**, no rodapé da barra lateral, selecione tema **Claro**, **Escuro** ou **Automático**, fonte **Pequena**, **Padrão**, **Grande** ou **Muito grande**, densidade, formato numérico e redução de animações. O padrão aumenta discretamente as fontes menores em aproximadamente 10%. **Restaurar configurações visuais** restaura somente a aparência. Preferências ficam no localStorage, separadas por usuário; não contêm credenciais. Com o menu recolhido, a engrenagem permanece acessível na faixa lateral, assim como o único botão para expandir o menu.

A planilha `dados/dados_dashboard.xlsx` já acompanha o projeto. Se ela não existir, a primeira execução por `python app.py` a cria. Também é possível gerá-la manualmente:

```powershell
python scripts/gerar_dados.py
```

O gerador usa semente 42 e datas relativas ao dia da geração. Ele **recusa sobrescrever uma planilha existente**. Não há regeneração em inicializações posteriores. Para um novo conjunto demonstrativo, pare o servidor e mova a planilha atual para um local de segurança antes de executar o gerador.

## Utilização

- Navegue pelas oito páginas no menu lateral. O botão de menu recolhe ou exibe a barra lateral.
- Em Funcionários, Equipes, Ordens de Serviço, Acessos e Renovações, use **Novo registro** para cadastrar. Os códigos são gerados pelo servidor. Utilize **Ver**, **Editar** ou **Excluir** na linha desejada. Exclusões pedem confirmação e são bloqueadas quando há dependências.
- Equipes precisam de um funcionário existente como responsável; novos funcionários precisam de uma equipe existente. O conjunto inicial fornece ambos. OS concluídas exigem data de conclusão válida; outras OS não podem ter conclusão preenchida.
- Use **Filtros** para abrir os campos da página. **Aplicar filtros** atualiza os dados e **Limpar filtros** restaura a visão completa. Os filtros não são compartilhados entre páginas. Na visão geral, status, prioridade e período filtram as OS; equipe filtra as entidades relacionadas. Os vencimentos permanecem classificados mesmo quando o acesso está revogado; os alertas da visão geral contam somente acessos ativos.
- Pesquise nas tabelas e clique nos cabeçalhos para ordenar. A paginação e a rolagem interna preservam todos os registros e colunas.
- Clique em qualquer parte de um cartão de gráfico ou use Enter/Espaço para ampliar. Feche com ×, Escape ou clique fora. Gráficos mantêm tooltips, com zoom, pan e ferramentas desativados.
- **Excel** exporta a página respeitando os filtros e a pesquisa. Em Relatórios, a exportação reúne os sete relatórios em abas. O seletor exibe uma análise de cada vez.
- **Atualizar** relê o Excel e recalcula os valores. Os dados também são atualizados após alterações. Se editar a planilha externamente, preserve nomes das abas, colunas, códigos e relações; feche o Excel antes de salvar pela aplicação.

## Dados e regras

As abas são `Funcionarios` (100), `Equipes` (10), `OrdensServico` (500), `Acessos` (500) e `Renovacoes` (150) no conjunto inicial. Nomes e e-mails são fictícios; o domínio example.com é reservado para exemplos. Equipes das OS e dos acessos são derivadas do funcionário para evitar vínculos divergentes.

Vencimentos usam `date.today()` do Windows: negativo = vencido; zero = hoje; 1–30 = até 30 dias; 31–45; maior que 45. As categorias são exclusivas. No indicador compacto “Até 30 dias”, hoje está incluído. Renovações pendentes são todas que ainda não estão concluídas ou rejeitadas. Aprovar ou concluir uma renovação não altera automaticamente a validade do acesso; a nova validade deve ser registrada explicitamente em Acessos.

Cada gravação bloqueia leitura e escrita por arquivo `.lock`, valida todo o conjunto, cria backup e escreve um Excel temporário antes da substituição atômica. Há espera de até dez segundos para outro processo terminar. Nenhuma relação é removida em cascata. Se o processo for encerrado à força e restar um `.lock`, pare todas as instâncias antes de removê-lo. O bloqueio protege processos da aplicação nesta máquina; não coordena o Microsoft Excel ou alterações do OneDrive. Evite executar várias máquinas sobre uma pasta sincronizada.

Backups ficam em `dados/backups/`, sem exclusão automática. Para restaurar, pare o servidor, preserve a planilha atual e copie o backup desejado para `dados/dados_dashboard.xlsx`. Os dados são locais e não são enviados a serviços externos. O Plotly.js está incluído em `static/js/plotly.min.js` com seu cabeçalho de licença MIT; os gráficos funcionam offline.

## Arquitetura

`app.py` concentra rotas HTML, API JSON, autenticação e exportação. `services/schema.py` define campos; `excel_service.py` implementa transações e validações; `dashboard_service.py` realiza enriquecimento, filtros e indicadores. `auth_service.py` guarda hashes de senha e sessões revogáveis em `instance/auth.sqlite3`, com segredo local em `instance/session.key`, separados do Excel e fora da pasta pública. Serviços específicos oferecem consultas reutilizáveis. Templates compartilham o layout e os componentes JavaScript/CSS. Uma implantação futura precisará de HTTPS, cookie Secure, servidor WSGI e armazenamento apropriado à concorrência; nesta etapa o servidor continua somente em 127.0.0.1.

`static/css/reference.css` contém os ajustes de proporção realizados após o recebimento da imagem. `icons.js` fornece ícones SVG locais consistentes. O calendário ao lado do gráfico de área destaca as previsões de conclusão das OS em aberto, respeitando os filtros; o dia atual fica laranja. Ele não representa valores demonstrativos fixos.

## Verificação

```powershell
python -m unittest discover -s tests -t . -v
```

Nesta máquina foi detectado `Lib/unittest/main.py` vazio na instalação do Python. Para executar a mesma suíte sem alterar a instalação, use `python scripts/testar.py`. O executor utiliza os componentes padrão de carregamento, asserções e execução do unittest e contorna apenas sua entrada de linha de comando quando esse arquivo está vazio.

Os testes usam cópias temporárias da planilha existente: não alteram os dados entregues. Cobrem geração isolada e relações, limites de vencimento, indicadores, filtros, CRUD nas cinco tabelas, concorrência, backups, persistência, navegação HTTP, relatórios, exportação e proteção CSRF. Há também testes de eventos JavaScript em jsdom; instruções e limites estão no relatório de estabilização. Isto não substitui testes visuais no navegador.

Revisão manual necessária: abrir cada página em 1920×1080, 1600×900, 1366×768 e 1280×720; verificar altura sem rolagem do documento, rolagem interna das tabelas, tooltips, abertura pelo espaço vazio dos cartões, fechar por Escape/clique externo, foco do teclado e adaptação no celular. O controle de navegador estava indisponível na sessão de desenvolvimento, portanto esses resultados não são apresentados como validados.

## Preparação para AWS

Consulte [deployment/aws/DEPLOY_AWS.md](deployment/aws/DEPLOY_AWS.md) para diagnóstico, configuração de produção, comandos Windows/Linux, HTTPS, backups e atualização. Nenhuma implantação AWS foi executada.
