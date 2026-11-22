# Perfil, e-mail e notificações — validação local

Data: 02/11/2026. Versão preparada: **2.1.1 (PATCH)**, compatível com o esquema empresarial existente. Nenhuma nova migração foi necessária. Não houve deploy, push, tag, acesso à AWS ou envio SMTP real.

## Resultado

- Perfil reorganizado em quatro cartões: informações, segurança, preferências e verificação. Cada formulário envia somente os dados correspondentes. A regra existente permite editar o identificador mediante senha atual; essa regra foi preservada. Alterações sensíveis continuam revogando a sessão e exigindo novo login.
- Central segue a composição da referência: cabeçalho azul-marinho com logo DOS e sino, detalhe laranja, menu interno, pesquisa, período, seleção, cartões, indicadores de leitura e rodapé. A adaptação mantém os dados disponíveis e suas ações reais. A decoração é uma curva sutil, não uma reprodução exata das ondas da imagem.
- Situações disponíveis: todas, não lidas e lidas. Arquivamento foi omitido porque não existe no modelo atual; não foi criada uma categoria fictícia nem alterado o banco para suportá-la.
- Busca e filtros atuam sobre até 200 notificações recentes retornadas pelo contrato existente. Quando esse limite é atingido, o rodapé informa a limitação. Paginação de seis itens por página aparece somente quando necessária. “Selecionar todas” seleciona a página visível; “Marcar todas como lidas”, sem seleção, afeta toda a central do usuário, conforme o backend existente.
- Limpeza exige confirmação, preserva eventos, auditoria e notificações de terceiros. A exclusão continua lógica por `deleted`.

## Diagnóstico de e-mail, antes da ativação

1. `EnterpriseService.token()` já usava `secrets.token_urlsafe(32)` e armazenava o digest na tabela `tokens`, vinculado à conta, finalidade e endereço, com validade de 30 minutos. O código em texto integra o corpo da mensagem na outbox privada para entrega; banco e backups são material privado.
2. A solicitação HTTP apenas insere a mensagem em `outbox`. Enfileiramento não é aceitação pelo provedor nem entrega na caixa de entrada.
3. `process_outbox()` é o processador existente. Antes desta atualização, a CLI `processar-alertas` também processava a fila, após observar o Excel. A nova CLI `processar-emails` permite processar somente e-mails.
4. A integração existente usa `smtplib.SMTP`, STARTTLS obrigatório e contexto TLS com validação de certificado. Login SMTP é usado quando o provedor exige usuário. Não há integração dependente de Gmail nem evidência de credenciais Gmail incorretas.
5. O envio real depende de `DASHBOARD_MAIL_ENABLED=true`. Foi mantido explicitamente `false` na aplicação local reiniciada. Não foram fornecidos/configurados host, remetente ou credenciais de provedor nesta tarefa.
6. A leitura final do banco real encontrou cinco mensagens `pending`, zero tentativas em `mail_attempts` e nenhum código de verificação ainda válido. Não foram processadas, reenviadas ou removidas mensagens reais. Isso explica por que pedidos anteriores ficaram na fila; não demonstra falha de autenticação de um provedor.
7. Falhas são registradas apenas pelo nome da classe em `last_error` e `mail_attempts.error_type`, sem texto do provedor, endereço, código ou senha nos logs de erro.
8. Estados existentes: `pending`, `sending`, `sent`, `failed`, `uncertain` e `cancelled`. Falhas transitórias têm retentativas com espera e limite de três; autenticação/configuração inválida termina em falha. Timeouts e desconexões ambíguas não são reenviados automaticamente. Aceitação SMTP não comprova entrega final.

## Correções do fluxo

- `GET /api/profile/verification` retorna somente estado público, possibilidade de confirmação e disponibilidade de envio, sem código, detalhes SMTP ou credenciais.
- Interface diferencia endereço ausente, não confirmado, enfileirado, processando, aceito pelo provedor, nova tentativa, falha, envio incerto e endereço verificado. O usuário pode atualizar a situação. Sem configuração disponível, solicitar novos códigos fica desabilitado na interface.
- Reenvio exige intervalo mínimo de 60 segundos e no máximo cinco solicitações por hora, por conta. Auditoria existente mantém os limites após reinício.
- Código anterior é invalidado; mensagens antigas ainda pendentes são canceladas. O worker confere se o código da mensagem continua válido e vinculado ao e-mail atual antes de enviar, evitando entregar códigos expirados/obsoletos.
- Após cinco confirmações inválidas em dez minutos, novas confirmações ficam temporariamente bloqueadas. Tentativas rejeitadas são persistidas sem armazenar o código digitado.
- Confirmação exige sessão autenticada e CSRF, conta ativa, endereço correspondente e código válido de uso único. Senhas e papéis mantêm suas proteções existentes.
- Alertas operacionais preservam a geração anterior. O worker continua exigindo endereço verificado, preferência de e-mail ativa e destinatário atual para mensagens operacionais.

## Testes automatizados

**51 testes Python e 52 testes JavaScript aprovados.** Os testes Python usam bancos e cópias Excel temporários; o import global de `app` também foi direcionado inicialmente a um diretório temporário, retirando depois a variável para preservar o isolamento por caso de teste. O gerador de fixtures foi executado em cópias temporárias e a suíte Node usou `--test-isolation=none`.

Cobertura nova e regressões: solicitação; digest e prazo; envio simulado; ausência de configuração; STARTTLS/login SMTP simulados; conexão recusada; autenticação rejeitada; falha sanitizada; código inválido/expirado/uso único; reenvio/limites; preferência de e-mail; isolamento entre contas; formulários independentes; filtros; seleção; paginação; confirmação de limpeza; texto não interpretado como HTML e destino inválido não oferecido como link. Suítes existentes de CRUD, autenticação, indicadores, exportação e interface também passaram.

## Playwright MCP e inspeção visual

Inspeção realizada antes, durante e depois. Capturas foram abertas e examinadas visualmente, não apenas geradas. Resoluções verificadas: 1600×1000, 1366×768 e 390×844, incluindo temas claro e escuro. Header e rodapé da central permanecem acessíveis, com rolagem interna na lista. Movimento reduzido respeita sistema e preferência da aplicação.

Banco real na porta 5000: consultas autenticadas, sem salvar perfil ou alterar notificações. Após reiniciar, `/perfil`, `/api/profile`, `/api/profile/verification` e `/api/notifications` retornaram 200, com quatro cartões e versão 2.1.1. Nenhum erro no console final. Não houve migração nesta atualização. A impressão digital dos registros SQLite e o SHA-256 do Excel permaneceram iguais antes/depois do reinício e das consultas finais. Integridade `ok`, sem violações de chaves estrangeiras.

Instância isolada na porta 5001: login normal pelo formulário, com senha aleatória exclusiva de teste; nove notificações na conta de teste e nove na segunda conta. Foram testados pesquisa, resultado vazio, período, categorias, paginação, leitura selecionada (contador 7 → 6), leitura em lote, cancelamento e confirmação de limpeza, persistência após recarregar e fechamento com Esc. O filtro por período também foi validado pelo combobox visível; fechamento por clique externo foi confirmado na aplicação local. As nove notificações da outra conta continuaram não lidas e não excluídas. E-mail foi aceito por um sender simulado, e o código foi confirmado pela interface. Nome e tema foram salvos somente nessa conta de teste e persistiram após recarregar.

### Capturas

Os arquivos estão em `../artifacts/`:

- [Perfil antes](../artifacts/perfil-antes.png)
- [Central antes](../artifacts/notificacoes-antes.png)
- [Perfil final local](../artifacts/perfil-depois-desktop.png)
- [Central final vazia, banco real](../artifacts/notificacoes-depois-vazia.png)
- [Central com dados exclusivamente de teste](../artifacts/notificacoes-teste-desktop.png)
- [Central escura, teste](../artifacts/notificacoes-teste-escuro.png)
- [Central notebook, teste](../artifacts/notificacoes-teste-notebook.png)
- [Central estreita, teste](../artifacts/notificacoes-teste-mobile.png)
- [Perfil escuro, teste](../artifacts/perfil-teste-escuro.png)
- [Perfil estreito, teste](../artifacts/perfil-teste-mobile.png)

Algumas capturas intermediárias do ambiente isolado exibem 2.1.0, pois antecedem o reinício final. As capturas finais locais mostram 2.1.1. A referência contém dados ilustrativos e arquivamento; a implementação mantém dados reais disponíveis e omite arquivamento por ausência de suporte. O estado vazio tem a mesma estrutura visual, sem itens fictícios no banco real.

## Ativação futura — pendente de participação do proprietário

O envio está **testado por simulação e aguardando configuração externa**. Para um envio real controlado, é necessário escolher um provedor compatível com SMTP/STARTTLS e informar, em ambiente privado: host, porta STARTTLS (padrão 587), remetente autorizado/verificado e, quando exigidos, usuário e senha SMTP. Segredos devem ser definidos em variáveis de ambiente, não em arquivos versionados ou no chat. A configuração `.env.example` é ilustrativa; `python app.py` não carrega esse exemplo automaticamente.

Depois da configuração e de autorização explícita para envio real: revisar a fila antiga e a validade dos códigos sem reenviar itens indiscriminadamente; autorizar um único destinatário e uma solicitação de teste; validar `processar-emails` no ambiente correto e a aceitação pelo provedor; confirmar recebimento e código; somente então aprovar agendamento e alertas operacionais. Nenhum desses passos externos foi ativado nesta entrega.

A instância de prévia na porta 5001 foi encerrada após os testes. A aplicação principal permanece em `http://127.0.0.1:5000`.

## Arquivos desta tarefa

- `.env.example`: nomes de configuração, sem segredos e envio desativado.
- `.gitignore`: diretório privado de diagnóstico/prévia excluído do versionamento.
- `VERSION`, `CHANGELOG.md`: PATCH local 2.1.1 e escopo.
- `services/enterprise_routes.py`: consulta de estado e CLI de e-mails.
- `services/enterprise_service.py`: estados, limites e confirmação; tipo real de evento retornado nas notificações.
- `services/mail_service.py`: configuração e falhas, validação de código antes do envio.
- `static/js/enterprise.js`: quatro cartões e nova central funcional.
- `static/css/account-premium.css`: estilos restritos ao perfil e central.
- `templates/account.html`, `templates/base.html`: classes do perfil e inclusão do CSS.
- `tests/test_account_premium.py`, `tests/frontend.test.cjs`: regressões e novos fluxos.
- `tests/preview_account_premium.py`: prévia isolada; nunca abre o SQLite real.
- Este relatório.

O checkout já continha outras alterações antes desta tarefa. Elas foram preservadas; a lista acima descreve os arquivos alterados por este refinamento, não todo o `git diff` do usuário.
