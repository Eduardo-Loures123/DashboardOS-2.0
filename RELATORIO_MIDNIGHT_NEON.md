# DashboardOS — Midnight Neon Premium

Implementação local em 05/11/2026. Versão declarada preservada: `2.1.2`. Sem deploy, publicação, alteração de infraestrutura ou migração de banco.

## Implementação

- Sistema visual compartilhado com variáveis de cor, superfícies, bordas, gradientes, sombras, brilho, tipografia e responsividade em `static/css/midnight.css`.
- Barra lateral recolhível, navegação móvel, seleção neon, cabeçalho com identidade do usuário e ondas SVG. Os submenus operacionais continuam disponíveis.
- Visão Geral organizada em quatro indicadores, evolução mensal, rosca com total, tabela de urgentes e barras de acessos por equipe. Agenda, análises por equipe, indicadores complementares e ampliação dos gráficos foram preservados abaixo da composição principal.
- Funcionários, OS, Acessos, Vencimentos, Renovações e Relatórios recebem o tema compartilhado. Tabelas mantêm todos os campos, pesquisa, ordenação, paginação, exportação e ações existentes. A rolagem horizontal fica dentro da tabela quando necessária.
- Equipes passa a usar cartões com quantidades reais e as mesmas ações de consulta, edição e exclusão, respeitando permissões.
- OS, Acessos e Renovações apresentam cápsulas que acionam os filtros reais da API. Renovações apresenta indicadores calculados sobre os registros filtrados, sem introduzir estados novos.
- Meu Perfil tem cinco abas. Preferências reúne tema, fonte, densidade, formato dos números e movimento reduzido. A aplicação local é imediata; o botão de salvar na conta usa a persistência já existente, sem alterar opções de e-mail. A seleção de tema duplicada em Notificações foi removida.
- Configurações saiu da barra lateral. `/configuracoes` e `/settings` redirecionam contas autorizadas para `/perfil?tab=preferences`; visitantes continuam bloqueados no perfil.
- Ajuda ganha página com pesquisa funcional sobre orientações locais, sem telefones, links de atendimento ou canais fictícios.
- Modo Visitante mantém leitura e preferências visuais locais. O acesso ao perfil retorna HTTP 403. O comando para sair continua usando o fluxo de logout existente.
- Login e redefinição de senha recebem os estilos compartilhados.
- Tema claro, preferências existentes e chave histórica de armazenamento foram preservados. Escuro é o padrão para preferências novas sem escolha anterior.

## Dados e gráficos

`overview(data)` deriva os painéis do conjunto já filtrado, sem escrever nos registros. Urgentes significa prioridade Alta ou Crítica e status diferente de Concluída, explicitado no indicador. A tabela exibe quatro registros e o painel de acessos exibe as cinco equipes com mais acessos; os módulos completos permanecem acessíveis pelos links.

A evolução mostra a quantidade de OS abertas por mês, sem percentuais de crescimento inventados. A rosca mantém os status reais Concluída, Pendente e Em andamento. Os rótulos ilustrativos das referências não substituem os estados do sistema.

Plotly foi mantido. Linha ciano, área com gradiente, pontos destacados, paleta de status, legendas, total central e tooltips existentes foram adaptados. Ampliação, teclado, estabilidade do domínio no hover e limpeza dos tooltips continuam cobertos pelos testes.

## Arquivos desta implementação

| Área | Arquivos |
| --- | --- |
| Base e marca | `templates/base.html`, `templates/_brand.html` |
| Visão Geral | `templates/dashboard.html`, `static/js/dashboard.js` |
| Sistema visual | `static/css/midnight.css`, `static/brand/midnight-waves.svg` |
| Operação e gráficos | `static/js/app.js`, `static/js/charts.js` |
| Preferências e perfil | `static/js/preferences.js`, `static/js/settings.js`, `static/js/profile.js` |
| Ajuda | `templates/help.html`, `static/js/help.js` |
| Acesso | `templates/login.html`, `templates/reset.html` |
| Agregações e rotas | `services/dashboard_service.py`, `services/enterprise_routes.py`, `app.py` |
| Verificação | `tests/test_midnight.py`, `tests/frontend.test.cjs` |

O repositório já continha alterações locais extensas antes desta tarefa. A lista acima identifica os arquivos trabalhados nesta implementação, sem atribuir as alterações anteriores a este redesign.

## Recursos gráficos e pendências

- `midnight-waves.svg` é um recurso vetorial decorativo novo, com curvas, gradientes e iluminação. Não representa uma reconstrução da marca.
- A logo nova mostrada nas referências não foi fornecida como recurso gráfico separado nos arquivos inspecionados.
- O arquivo chamado `dashboardos-official-original.png` contém a marca antiga em D, RGB, 1254 × 1254, sem transparência; o SVG existente incorpora esses mesmos pixels.
- A marca antiga deixou de ser exibida pelo componente compartilhado. Foi mantido apenas o nome DashboardOS enquanto o original aprovado não estiver disponível. Os arquivos antigos foram preservados, sem recortes ou alterações.
- Favicon, ícone de instalação e símbolo definitivo dependem da nova marca. O manifesto antigo não é anunciado pelos templates enquanto aponta para a identidade retirada.
- Não foi criada pesquisa global: as pesquisas por módulo e a busca de orientações são funcionais. A pesquisa global da referência exigiria implementação própria.

## Validação executada

1. `.venv/Scripts/python.exe scripts/testar.py`: **179 testes passaram**. Inclui autenticação, permissões, integridade dos registros, CRUD, perfil, atividades, rotas, notificações e transportes de e-mail simulados.
2. `.venv/Scripts/python.exe scripts/preparar_testes_frontend.py`: fixtures geradas a partir de cópia temporária do Excel.
3. `node --test --test-isolation=none tests/frontend.test.cjs`: **72 testes passaram**, sem falhas. As expectativas de configuração no menu foram atualizadas para Preferências no perfil. Testes de múltiplas séries continuam usando séries de teste explícitas, embora o gráfico principal agora mostre o total mensal.
4. Novos testes verificam agregações sem mutação, redirecionamentos, bloqueio do visitante, cartões de equipes, filtros reais de status e salvamento de aparência sem mudar preferências de e-mail.
5. Inspeção real no navegador com Flask em loopback e dados fictícios temporários, usando `scripts/preview_profile_redesign.py`. Esse script bloqueia rede de saída e acesso a bancos fora do diretório temporário, com e-mail desativado.
6. Capturas inspecionadas da Visão Geral, Funcionários, Equipes, OS, Acessos, Renovações, Perfil, Ajuda, modo visitante e modais. Relatórios e Vencimentos também foram abertos e capturados.
7. Verificações de layout em 1672, 1366, 768 e 390 pixels. Foram corrigidos conflitos de dimensões da barra lateral, posição do centro da rosca, sobreposição do rodapé e excesso de largura do cabeçalho no tablet. A verificação final dos cenários afetados não apresentou rolagem horizontal global.
8. Tema claro e escuro verificados no navegador. Nenhum erro JavaScript foi observado na varredura de páginas. HTTP 403 ao consultar o perfil como visitante é esperado e foi confirmado.

Logs: `../artifacts/midnight-python-tests.log` e `../artifacts/midnight-node-tests.log`.

## Capturas reais

Os arquivos estão em `../artifacts/`:

- `midnight-dashboard-final.png`
- `midnight-funcionarios-final.png`
- `midnight-equipes-final.png`
- `midnight-ordens-servico-final.png`
- `midnight-acessos-final.png`
- `midnight-renovacoes-final.png`
- `midnight-perfil-final.png`
- `midnight-ajuda-final.png`
- `midnight-guest-final.png`
- `midnight-light.png`
- `midnight-form-modal.png`
- `midnight-chart-modal.png`
- `midnight-*-mobile-final.png`

As capturas usam registros fictícios criados exclusivamente no ambiente temporário, sem substituir os dados reais do aplicativo.

## Diferenças e limites

Não se declara equivalência pixel a pixel. O símbolo aprovado permanece pendente; curvas decorativas, ícones e tipografia não são os arquivos originais da composição de referência. Dados, quantidades, status e campos reais produzem diferenças legítimas no conteúdo e nas dimensões das tabelas.

A agenda e outros recursos existentes foram mantidos abaixo da composição principal, ampliando a altura da Visão Geral. Tabelas completas podem exigir rolagem interna horizontal para preservar todos os campos e ações. A ajuda apresenta os recursos locais reais, sem simular tutoriais em vídeo ou abertura de chamados inexistentes.

Os estilos legados continuam presentes para preservar contratos de componentes existentes. O novo sistema de tokens e sua integração estão centralizados em `midnight.css`; não houve reescrita integral do frontend ou do backend.

## Preservação do ambiente

Nenhuma chamada à AWS, alteração em `deployment/aws`, deploy, push, tag, agendador, worker ou envio de e-mail real foi realizado. As cinco mensagens pendentes não foram processadas. Nenhuma migração, recriação de banco ou limpeza de atividades reais foi executada. Testes de escrita e prévias usaram ambientes temporários. As permissões administrativas não foram alteradas.
