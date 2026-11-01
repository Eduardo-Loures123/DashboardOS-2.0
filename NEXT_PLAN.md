# Atualização empresarial — plano e arquitetura

Data: 01/11/2026. Branch: feature/dashboardos-next. Nenhuma publicação ou alteração na AWS autorizada.

## Arquitetura encontrada

`app.py` cria Flask, valida host/CSRF/sessão e expõe oito páginas, CRUD e exportação. `services/excel_service.py` mantém cinco abas, códigos e referências, com lock entre processos, backup antes de escrita e substituição atômica. Funcionários vinculam equipes; equipes apontam responsáveis; OS/acessos apontam funcionários; renovações apontam acesso/responsável. Os serviços de consulta reutilizam filtros e indicadores. Excel não contém credenciais. SQLite contém users, sessions e attempts; sessões revogáveis duram oito horas e senhas usam scrypt. Todas as contas existentes são administradoras. Preferências visuais ficam no navegador, separadas por identificador. Plotly local mantém ampliação e eixos fixos. CSS em camadas já inclui premium/responsividade. AWS usa EC2, Nginx, Gunicorn, dados externos ao checkout e backup separado.

## Etapas, riscos e validação

1. Baseline: suíte Python (scripts/testar.py contorna instalação local incompleta de unittest) e Node/jsdom; verificar Git limpo e hashes dos dados.
2. Persistência/segurança: auth_service e novo serviço empresarial; esquema aditivo explícito com backup SQLite consistente; manter IDs/hashes e role admin de contas legadas. Promoção inicial exige senha atual no CLI. Não executar migração no banco real nesta tarefa. Testar cópias, revogação, CSRF, último superadministrador e isolamento.
3. Perfil/admin/notificações: blueprint, templates e JS compartilhados. Tokens de uso único com validade e hash; preferências, auditoria e outbox persistente. Eventos detectados por snapshots duráveis, nunca por GET do dashboard. Testar transições, reinício, duplicidade e e-mail simulado.
4. UI: tokens compartilhados, sidebar, formulários e Plotly. Preservar oito páginas, controles, temas/fontes e exportação. Testar Node e navegação Flask; verificar layout no navegador quando disponível.
5. Operação: worker externo executado por timer systemd (nenhum scheduler Gunicorn), envio desativado por padrão, documentação de atualização/rollback, README e changelog. Sem deploy.

Migrações e promoção da conta real aguardam confirmação do proprietário. Configuração SMTP e autorização de testes reais também. Rollback restaura código anterior e backup com serviços parados; não aplicar downgrade destrutivo automático. Mudanças posteriores ao backup precisam ser preservadas antes de restaurar.
