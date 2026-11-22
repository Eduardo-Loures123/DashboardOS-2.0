# 2.1.3 — preparada localmente, não publicada

- Suíte Python executada por módulo em processos separados, com dados fictícios e raiz temporária de execução fora da cópia do código; testes legados de e-mail habilitam explicitamente apenas adaptadores simulados, preservando a suspensão padrão da release e suas verificações.
- Nome do usuário abre o perfil, preservando o estilo e a navegação pelo avatar.
- Suspensão explícita e por padrão do envio de e-mails e do processador legado; fila histórica preservada.
- Pacote operacional sem demonstração experimental, dados ou tarefas de e-mail; roteiro de atualização da infraestrutura existente.

## 2.1.2 — Estabilidade dos gráficos, menu persistente e SVGs (local)

- Corrigido o deslocamento dos pontos no hover: o domínio Y das linhas é calculado a partir dos dados, com espaço para o marcador destacado, sem autorange durante o destaque.
- Menu recolhido redesenhado com áreas uniformes e ícones centralizados. Estado persistido por usuário no navegador e carregado no head, antes do corpo da página, sem interferir nas preferências de aparência.
- Catálogo SVG existente ampliado e compartilhado por navegação, ações, filtros, tabelas, formulários, modais, perfil e notificações; removida a dependência de caracteres de fonte nos símbolos de interface revisados. Logo DOS preservada.
- Validação: 51 testes Python e 56 JavaScript, inspeção Playwright com medidas de geometria, navegação nos dois estados e temas claro/escuro. Evidências em `VALIDACAO_REFINAMENTO_2_1_2.md`.
- PATCH preparado somente localmente. Sem alteração do SQLite real, migração, mudanças de e-mail, deploy, push ou tag.

## 2.1.1 — Perfil, verificação de e-mail e central premium (local)

- Perfil organizado em quatro cartões com formulários independentes, preservando validação de senha e preferências por conta.
- Central com cabeçalho azul, navegação por leitura, busca, período, seleção, paginação e limpeza confirmada por usuário. Arquivamento omitido por ausência de suporte no esquema.
- Verificação com estados reais de fila/envio/falha, intervalo de reenvio, limite horário e bloqueio temporário de tentativas inválidas. Códigos antigos ou expirados não são enviados pelo worker.
- SMTP existente preservado com STARTTLS; comando `processar-emails` separa processamento de e-mail da observação operacional do Excel. Envio real permanece desativado.
- Sem nova migração, deploy ou publicação remota. Validação e limites em `REFINAMENTO_PERFIL_NOTIFICACOES.md`.

# Changelog

## Correcoes locais pendentes de homologacao - 02/11/2026

- Barra lateral usa scrollbar customizada no Chromium para remover as setas nativas, preservando cor, largura e rolagem; Firefox conserva o estilo padrao fino.
- Graficos de linhas usam margens no eixo, rotulos inicial/final explicitos e densidade adaptada a largura; dados, hover e marcadores preservados nos cartoes e ampliacoes.
- Selecoes pesquisaveis nao expandem ao receber foco automatico; clique, pesquisa e setas abrem a lista, selecao/Esc/clique externo fecham preservando valores e FormData.
- Regressao de filtros, criacao e edicao nos componentes compartilhados e dos meses extremos nos graficos.

## 2.1.0 — preparada localmente, 02/11/2026

### Funcionalidades compatíveis

- Agenda operacional com calendário navegável, seleção de data, registros reais de OS/acessos/solicitações de renovação e links de consulta.
- Resumo de OS abertas vencidas/próximas, derivado dos dados já filtrados, sem persistência adicional.
- Seleção pesquisável compartilhada, navegação por teclado, estados vazios e suporte a múltiplos valores; selects nativos preservam FormData, validação e eventos.
- Fonte única de versão em `VERSION`, marca DOS compartilhada e versão consistente na sidebar, login, rodapé e API.

### Correções e apresentação

- Gerenciamento ocupa a altura disponível com rolagem interna da tabela; Visão Geral mantém fluxo natural.
- Indicadores inferiores em cartões responsivos, preservando todos os valores e atalhos de status reais.
- Área de hover dos grupos de barras cobre os espaços vazios até o topo da maior barra, sem bloquear cliques.
- Marcadores maiores com contorno contrastante e extremos sem clipping, preservando eixos e valores.
- Datas nativas com acabamento por tema e valores ISO preservados.
- Removidas identificação inferior duplicada e ação Trocar usuário; preservados sair, visitante, perfil e permissões.
- Scrollbars de menu e seleções sem botões/setas; mantidas cores e espessura.

Validação visual em navegador pendente: host de navegador indisponível nesta sessão. Esta entrada descreve uma versão local preparada, ainda não homologada/publicada. Sem push, tag remota, migração real ou deploy.

## Next — não publicado, 01/11/2026

- Esquema empresarial aditivo com backup explícito e promoção inicial autenticada, sem modificar contas reais na implementação.
- Superadministrador, administrador, usuário e visitante; bloqueio/desativação, revogação de sessões e proteção do último superadministrador ativo.
- Perfil funcional, alteração de login/senha/e-mail com confirmação, preferências, verificação de e-mail e redefinição de senha com códigos de uso único.
- Central por destinatário, contagem de não lidas, leitura/exclusão/limpeza, links operacionais, comunicados com prévia e auditoria persistente.
- Eventos de OS/acessos com snapshots/versões, integração com CRUD e worker externo idempotente; outbox SMTP opt-in, tentativas limitadas e tratamento de entrega ambígua.
- Tokens visuais compartilhados, sidebar/scrollbar, formulários em duas colunas, temas, foco acessível, legendas Plotly permanentes, tooltips maiores e linhas contínuas.
- Inicialização local não gera dados demonstrativos automaticamente.
- Testes de regressão/segurança/transições/SMTP simulado e documentação AWS/backup/rollback.

Sem deploy ou push. Envio real desativado; ativação/migração de contas reais, validação visual de navegador e homologação Linux continuam pendentes. Consulte NEXT_OPERATIONS.md.
