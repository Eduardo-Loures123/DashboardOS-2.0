# DashboardOS Next — configuração, operação e rollback

Esta branch preserva Flask/Excel/SQLite/Plotly e EC2/Gunicorn/Nginx. Não houve deploy, publicação GitHub, migração de contas reais, promoção de conta real nem envio SMTP real.

## Instalação e execução local

Use Python 3.11+ e `python -m pip install -r requirements.txt`. Não há dependências Python novas. Configure `DASHBOARD_EXCEL_PATH` e `DASHBOARD_AUTH_DIRECTORY` para os destinos escolhidos. `python app.py` inicia em 127.0.0.1:5000. Dados ausentes geram erro explícito; a inicialização não gera dados demonstrativos. Não execute o gerador sobre dados reais.

Para testar a atualização antes de ativar, copie a planilha e faça backup SQLite pela API `sqlite3.Connection.backup`, com serviços parados, para uma pasta privada fora do checkout. Aponte ambas as variáveis à cópia. Não copie credenciais para pastas públicas, não use o banco original como ambiente de teste. Contagens, IDs, hashes e `PRAGMA integrity_check` devem ser conferidos.

## Migração e primeira conta principal

**Somente após confirmação do proprietário para o banco configurado**, com Gunicorn/worker parados e backup completo existente:

```text
python -m flask --app app migrar-contas
python -m flask --app app promover-superadmin
```

O primeiro comando pede confirmação e cria `auth.before-next.<aleatório>.sqlite3` por backup consistente antes de uma transação aditiva. Preserva users, IDs e hashes; adiciona tabelas, sem reclassificar administradores existentes. Verifica igualdade dos IDs/hashes antes/depois. Pode ser repetido. O segundo exige identificador e senha atual de um administrador ativo. Nenhuma senha padrão; a senha é solicitada de forma oculta. Não passe senhas como argumentos. Só permite a promoção inicial quando nenhum superadministrador existe. Promoções seguintes exigem a interface autenticada. Alterar/bloquear/desativar o último superadministrador ativo é recusado dentro de transação serializada.

Até migrar, o login/visitante e as operações antigas permanecem compatíveis; APIs empresariais respondem 503. Bancos novos já recebem o esquema aditivo, mas `criar-admin` continua criando administrador comum. Para datas legadas não conhecidas, a interface informa indisponibilidade em vez de inventar histórico.

## Permissões e perfil

| Perfil | Operações |
|---|---|
| Superadministrador | CRUD operacional, contas, permissões, bloqueio/desativação, código de redefinição, comunicados e auditoria |
| Administrador | CRUD operacional existente; perfil próprio; notificações próprias |
| Usuário | Consultas, pesquisa/filtros/exportação e perfil/notificações próprios |
| Visitante | Consultas, filtros, gráficos/exportação; sem gravação operacional, perfil ou central |

O avatar abre `/perfil`; a navegação administrativa aparece somente para superadministrador. A autorização de cada API é feita no backend. Papéis são consultados no banco a cada requisição; alterações administrativas revogam sessões da conta afetada. Não há exclusão física de contas. Nome, login, e-mail, preferências e senha são editáveis no perfil. Login/senha/e-mail exigem a senha atual; alterações sensíveis encerram a sessão. Identificadores únicos são validados. As respostas de perfil/admin não retornam hashes. Formulários/API mantêm CSRF e senhas scrypt.

Preferências do perfil ficam no SQLite; preferências locais continuam disponíveis nas configurações. Em novo navegador, o perfil fornece a aparência inicial. Um ajuste local já salvo prevalece naquele navegador. Usuários comuns consultam os mesmos dados operacionais já disponíveis no modo leitura; não foi introduzida uma política nova de filtragem por equipe.

O superadministrador pode gerar código de redefinição após confirmar sua própria senha. Entregue o código ao titular por canal seguro; ele usa `/redefinir-senha`. Código não aparece no histórico, tem hash no armazenamento de validação, uso único e prazo de 30 minutos. A troca revoga sessões. O fluxo não depende de e-mail nem divulga credenciais existentes.

## E-mail verificado e outbox

Alterar e-mail remove a verificação. No perfil, solicite código: ele é enfileirado somente para o endereço informado, nunca retornado ao solicitante. Copie o código recebido para a confirmação no perfil. Sem provedor habilitado, permanece pendente. Alertas operacionais por e-mail exigem endereço verificado **e** preferência de recebimento. A confirmação de endereço é a única mensagem que precisa chegar a endereço ainda não verificado.

Configure no ambiente privado (exemplo sem segredos em `deployment/aws/dashboardos.env.example`):

```text
DASHBOARD_MAIL_ENABLED=false
DASHBOARD_SMTP_HOST=<provedor>
DASHBOARD_SMTP_PORT=587
DASHBOARD_SMTP_USER=<usuário se necessário>
DASHBOARD_SMTP_PASSWORD=<segredo externo>
DASHBOARD_MAIL_FROM=<remetente autorizado>
```

STARTTLS obrigatório com validação de certificado. Credenciais fora do Git. Configurar, verificar remetente e autorizar testes reais antes de definir `DASHBOARD_MAIL_ENABLED=true`. SMTP autenticado de provedor compatível, incluindo endpoint SMTP do SES, pode ser usado; provisionamento SES/limites/permissões não é feito por esta atualização.

O comando `processar-alertas` processa até 25 mensagens por execução fora do servidor web. Estados persistentes: pending/sending/sent/failed/cancelled/uncertain. Falhas conhecidas têm até três tentativas, com espera exponencial. Cada tentativa guarda horário, resultado e classe de erro, sem mensagem do provedor. Estado inativo, endereço alterado ou preferência revogada impedem entrega de alerta pendente. Comunicados nunca enfileiram e-mail automaticamente.

SMTP não oferece entrega exatamente uma vez em caso de queda após aceitação. Timeouts/desconexões ficam `uncertain`; queda abrupta pode deixar `sending`. Ambos exigem revisão administrativa dos logs do provedor antes de qualquer reenvio manual; não há reenvio automático desses estados. Não altere filas sem backup. Mensagens de verificação contêm código na outbox privada para entrega: proteja banco, backups e permissões de arquivo como credenciais.

## Eventos e notificações

O worker compara snapshots persistentes de OS/acessos. A primeira leitura estabelece baseline sem inventar transições anteriores. Depois registra mudanças reais de status, data e faixa: Após 45 dias, 31 a 45 dias, Até 30 dias, Vencem hoje e Vencidos; concluídas/revogadas saem do acompanhamento de prazo. Mantém regras de classificação existentes. A primeira execução deve ocorrer antes de ativar acompanhamento; alertas antigos não são retroativos.

O CRUD também observa estado anterior e posterior com lock da planilha. Ao salvar o mesmo conteúdo não gera evento. Se a escrita Excel já concluiu e o registro de alerta falhar, a gravação operacional continua válida e o worker reconcilia o snapshot pendente. Alterações externas ao Excel entre verificações são observadas pelo estado final disponível; não há histórico de edições externas intermediárias. Uma falha entre gravação Excel e SQLite também pode impedir observar um estado intermediário que tenha sido sobrescrito antes da reconciliação. A persistência principal continua Excel; não se promete transação distribuída Excel/SQLite.

Snapshots, versões por registro e chaves únicas de evento impedem duplicidade entre processos/reinícios. Tombstones preservam versões quando códigos são removidos/reutilizados. Exclusão na central é lógica e restrita ao destinatário; não remove evento, comunicado nem registro operacional. A central lista os 200 itens recentes e conta todos os não lidos; marcar tudo/limpar afeta toda a conta. Links abrem a página operacional com pesquisa do código. Comunicados exigem prévia/confirmação, destinatários ativos e superadministrador; conteúdo é texto, sem execução HTML. Histórico administrativo permanece mesmo com exclusão da notificação.

## Agendamento independente de Gunicorn

`python -m flask --app app processar-alertas` faz uma execução. Para Windows/local, execute por Agendador de Tarefas com o Python/variáveis corretos. Para AWS, os novos exemplos `dashboardos-alerts.service` e `.timer` executam oneshot a cada minuto, sem scheduler nos workers web. Lock Excel serializa scanners/CRUD; `BEGIN IMMEDIATE` e chaves únicas serializam SQLite. Nenhum agendador foi instalado/ativado nesta tarefa.

## Procedimento futuro AWS — exige revisão e autorização

1. Registre release anterior e caminhos reais. Pare gravações, timer e Gunicorn durante a janela. Não substitua a infraestrutura existente.
2. Execute `deployment/aws/backup.py` com o usuário de serviço; aceite somente diretório COMPLETE. Preserve também configuração privada e release anterior. Verifique cópia Excel, contagens/códigos e integridade SQLite. O backup completo deve anteceder a migração.
3. Prepare novo diretório de release; instale requirements em venv Linux, confira versões. `build_package.py` inclui os novos serviços/templates/assets e arquivos do timer, excluindo dados, credenciais, node_modules e Git. O tarball antigo não foi substituído nesta tarefa; reconstrução é uma ação posterior.
4. Configure variáveis de dados/hosts/SECRET_KEY existentes e as de e-mail, com envio desativado. Proteja env para o usuário do serviço. Mantenha dados em `/var/lib/dashboardos`, fora do código, e backup privado.
5. Com serviços parados, execute migração no ambiente correto e confira contas, hashes e `PRAGMA integrity_check`. Promova a conta escolhida mediante senha atual, após confirmação do proprietário.
6. Atualize symlink/release pelo procedimento existente, reinicie Gunicorn controladamente. Teste login/logout, visitante, permissões, perfil, consultas, CRUD em registro de teste autorizado, filtros e exportação.
7. Instale/revise as duas unidades do worker, execute `systemctl daemon-reload` e uma execução manual do service; valide journal e snapshots. Só então habilite o timer com `systemctl enable --now dashboardos-alerts.timer`. Configure fuso consistente (`TZ=America/Sao_Paulo`). Confirme a execução sem navegador aberto e após reinicialização.
8. Configure provedor e autorize teste de e-mail separadamente. Valide endereço, opt-in, falhas e ausência de duplicidade antes de ativar env real. Logs em journalctl das unidades; não habilite debug em produção.

Não executamos comandos systemd/Nginx/EC2 nesta sessão Windows. Os arquivos são preparação para homologação Linux, não comprovação de implantação. O script deploy.sh foi protegido para não retornar automaticamente a uma release legada após falha na verificação da Next; nesse caso ele mantém o serviço parado para restauração/revisão administrativa. A sintaxe passou em `bash -n`.

## Rollback

Pare timer e Gunicorn. Faça backup adicional dos dados atuais antes de restaurar qualquer coisa. Retorne release anterior. Como o esquema é aditivo e users/sessions/attempts foram preservados, o código anterior consegue ler o banco estendido, mas trata todas as contas autenticadas como administradoras e ignora bloqueios: **não reabra o serviço antigo com contas de menor privilégio existentes**. Para rollback integral, restaure o backup pré-migração com serviços parados, incluindo Excel do mesmo ponto consistente, ou faça revisão administrativa explícita das contas antes de qualquer reabertura. Restauração perde mudanças posteriores: reconcilie/preserve essas mudanças antes de decidir. Nunca automatize remoção de tabelas/contas. Restaure env/symlink, valide integridade/contagens e só então reinicie. Reverter código sozinho não mantém a política de acesso nova.

## Testes e limites

```text
python scripts/testar.py
python scripts/preparar_testes_frontend.py
node --test --test-isolation=none tests/frontend.test.cjs
```

O runner Python contorna `unittest/main.py` vazio no host. No Windows, `npm.cmd test` evita bloqueio de npm.ps1; neste sandbox o runner Node precisa `--test-isolation=none` para não gerar EPERM ao criar subprocesso. Fixtures usam cópias temporárias do Excel e contas aleatórias. Nenhum teste envia e-mail real. jsdom valida eventos/DOM e configuração Plotly, não renderiza pixels, CSS ou SVG real.

Pendências de homologação: inspeção visual em navegador real (host de acesso ao navegador indisponível nesta sessão), contraste/recortes em resoluções móveis, SMTP autorizado, systemd/Gunicorn Linux e teste de rollback operacional no ambiente de homologação. Migração/promoção reais dependem de autorização. Não declarar versão integralmente homologada antes dessas verificações.
