# Etapa B — correções funcionais do perfil

Concluída em 05/11/2026. Etapas C/D/E não executadas.

## Arquivos alterados nesta etapa
- static/js/profile.js: referência normalizada dos dados da conta; mesma comparação para salvar e avisar sobre alterações; formulários auxiliares rastreiam edições explícitas enquanto visíveis; cancelamento, descarte e salvamento restauram a referência; preferências e confirmação pendente também protegidas. Avatar superior agora é visual, sem botão, câmera ou seletor de arquivos; inferior preservado.
- templates/base.html: atalho de perfil omitido somente na página perfil; notificações e data preservadas.
- tests/frontend.test.cjs: cinco novos testes agrupados de regressão.

## Reversão
Cópias anteriores dos três arquivos em diagnosticos/etapa-b-20261105-005413/before/. Não restaurar outros arquivos nem sobrescrever alterações posteriores sem comparação.

## Validação
- Python: 174 testes aprovados (scripts/testar.py).
- Frontend: 66 testes aprovados, cinco novos (node --test --test-isolation=none tests/frontend.test.cjs).
- Fixtures frontend geradas em ambiente temporário a partir de cópia do Excel.
- Playwright: contexto separado, prévia 127.0.0.1:5099, SQLite e Excel temporários, conta fictícia, saída de rede bloqueada pelo script existente. Confirmados: estado inicial limpo; avatar superior DIV, cursor auto, sem câmera; inferior com câmera; atalho ausente no perfil e presente em Funcionários; edição real protegida; continuar editando mantém rascunho; salvar nome fictício persiste após recarregar e limpa pendência; autofill em senha oculta não aciona aviso; zero erros JavaScript capturados.
- Prévia encerrada após os testes. Não houve envio real, processamento da fila principal, operação AWS, alteração de SMTP ou de versão.

## Preservação e limites da comparação
Conferência SQLite exclusivamente em leitura contra backup histórico: users, tokens, events, notifications, outbox e mail_attempts iguais; cinco mensagens IDs 1 a 5 continuam pending com attempts=0, conteúdo preservado. Excel igual ao hash histórico; VERSION preservado.
A tabela account tem diferenças históricas nos campos display_name e last_login. O backup é anterior a esta etapa, sem fotografia imediatamente anterior para atribuir tais diferenças; portanto não se declara igualdade integral do banco nem se restaura esses dados. Nenhum comando desta etapa atualizou registros do banco principal; operações de edição foram feitas apenas na prévia isolada.

## Pendências
Rolagem lateral, geometria das abas, logo oficial, fundos e acabamento pertencem às etapas C/D. Fidelidade visual final não aprovada nesta etapa. Aguardar autorização para C. Recursos oficiais da logo e ondas ainda necessários para D.
