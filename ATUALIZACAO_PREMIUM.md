# Atualização de aparência e autenticação

Foram acrescentadas exclusivamente as preferências, a posição e transição do menu, animações, tipografia e autenticação solicitadas. As oito páginas, indicadores, gráficos, filtros, regras de negócio e a integração Excel continuam no projeto existente.

## Restaurar a versão anterior

Antes da edição, foi criado `../_restauracao/DashboardOS_2.0_antes_premium_20261028_221026.zip`. O manifesto está em `../_restauracao/manifesto_premium.json`. Extraia para outra pasta para consultar ou recuperar a versão anterior, preservando dados alterados legitimamente depois do backup.

O hash SHA-256 registrado para o Excel desta atualização é:

```text
275a1627a92cad444e64d254639bd317d1e7862170a3c94d587856bcb72c805d
```

Esse é o arquivo existente no início desta atualização, incluindo uma equipe cadastrada após a primeira entrega. Ele não foi substituído pelo conjunto fictício original. Testes de escrita usam cópias temporárias, e os testes de indicadores consideram os registros atuais.

## Acesso e primeiro administrador

Na pasta `DashboardOS_2.0`, com as dependências Python instaladas:

```powershell
python -m flask --app app criar-admin
python app.py
```

O primeiro comando solicita ID, senha de pelo menos 12 caracteres e confirmação. A senha não é exibida, não deve ser passada como argumento e não possui valor padrão. A mesma ferramenta permite adicionar outros administradores com IDs distintos. Nenhum administrador foi criado automaticamente no banco real pelos testes.

Abra **http://127.0.0.1:5000/login**. O endereço raiz redireciona usuários sem sessão para essa tela. O login usa formulário POST com CSRF e funciona sem depender de uma validação JavaScript. O botão **Mostrar/Ocultar** controla apenas a visibilidade do campo; o navegador pode usar seu próprio gerenciador de senhas.

**Modo visitante** inicia uma sessão de leitura sem senha. Indicadores, páginas, filtros, pesquisa, detalhes, gráficos e exportações continuam acessíveis. Todos os botões existentes de cadastro, edição e exclusão ficam visíveis, pálidos e desabilitados, com a indicação “Disponível apenas para administradores”. Os formulários de alteração não abrem nesse modo. O Flask rejeita POST, PUT e DELETE nas rotas de registros com HTTP 403 para visitantes ou usuários sem autorização, mesmo com um CSRF válido ou uma alegação de papel administrativo enviada pelo cliente.

Na parte inferior do menu:

- Administrador: **Configurações**, identificação, **Trocar usuário**, **Entrar no modo visitante** e **Sair**.
- Visitante: **Configurações**, identificação, **Fazer login** e **Voltar à tela inicial**.

As trocas e o logout são POST com CSRF. A sessão anterior é revogada no SQLite antes de iniciar a seguinte. Reutilizar um cookie antigo não recupera privilégios administrativos. Sessões duram até oito horas e continuam válidas após reiniciar o Flask se não tiverem sido encerradas ou expirado.

## Personalizar

Abra **Configurações** na parte inferior da barra lateral. Quando recolhida, a faixa lateral preserva a engrenagem com tooltip e o botão de expansão à esquerda. O botão antigo da direita foi removido; não há controles duplicados.

- **Tema:** Claro preserva a paleta atual; Escuro adapta superfícies, campos, tabelas, pop-ups e gráficos; Automático acompanha mudanças da preferência do sistema.
- **Fonte:** Pequena usa a escala anterior; Padrão aumenta aproximadamente 10% os textos menores; Grande e Muito grande oferecem ampliações adicionais. Títulos principais permanecem com seu tamanho anterior. O aumento usa variáveis CSS e não escala a aplicação inteira. Quando necessário nas maiores fontes, o conteúdo tem rolagem interna para manter as informações acessíveis.
- **Densidade:** Padrão mantém a distribuição; Compacta reduz espaçamentos internos de tabelas e componentes.
- **Números:** Brasileira mostra, por exemplo, `1.250`; Abreviada mostra `1,25 mil`. A preferência afeta os indicadores apresentados, sem modificar valores nem exportações.
- **Reduzir animações:** simplifica transições. A preferência `prefers-reduced-motion` do sistema também é respeitada, mesmo se o controle local estiver desligado.
- **Restaurar configurações visuais:** restaura somente as preferências de aparência. Não altera cadastros, Excel, senha, conta ou sessão.

As preferências usam a chave `DashboardOS_2.0:appearance:v1:<identificador>` no localStorage, separada por usuário. Visitantes compartilham uma preferência de visitante no mesmo navegador. A tela de login tem seu próprio contexto de aparência. Não há senhas, cookies de sessão ou tokens CSRF no localStorage. As preferências são aplicadas antes da pintura inicial para reduzir flashes de tema.

## Implementação e segurança

`premium.css`, `preferences.js` e `settings.js` acrescentam a personalização sem substituir os estilos base. O menu ajusta sua coluna em 300 ms. Pop-ups entram com opacidade e escala discretas; saem em 180 ms antes de restaurar o foco. A limpeza dos gráficos mantém a proteção contra reabertura rápida. Os gráficos recebem medidas do conteúdo, sem depender da escala visual durante a animação.

`services/auth_service.py` usa SQLite separado (`instance/auth.sqlite3`), consultas parametrizadas e hashes scrypt do Werkzeug. O cookie Flask é assinado, HttpOnly e SameSite=Strict, e contém um identificador aleatório de sessão; o SQLite mantém sua autorização e expiração e permite revogá-lo. O segredo de assinatura é gerado localmente uma vez em `instance/session.key`. Dez tentativas inválidas por origem em dez minutos resultam em bloqueio temporário de novas tentativas. A aplicação não serve o Excel, o SQLite ou o segredo por URLs de arquivos.

O cookie não usa Secure neste ambiente HTTP local, e o servidor permanece vinculado a `127.0.0.1`. Para uso futuro com HTTPS, esse atributo deve ser habilitado. Não foi implementada hospedagem. Preserve a pasta `instance` como material privado; apagá-la remove contas e sessões, sem apagar o Excel. Não é preciso apagá-la para restaurar preferências visuais.

Referências de implementação: [segurança do Flask](https://flask.palletsprojects.com/en/stable/web-security/) e [hashes do Werkzeug](https://werkzeug.palletsprojects.com/en/stable/utils/).

## Testes e limites

Foram executados **28 testes Python** e **34 testes JavaScript**, todos aprovados, além da checagem de sintaxe dos scripts próprios. A suíte anterior foi mantida e adaptada para autenticar um administrador de teste em bancos temporários.

Python verifica login válido/inválido, CLI de criação, hashes, CSRF, cookies, limite de tentativas, logout, expiração, troca de administrador, administrador → visitante, revogação de cookies anteriores, bloqueio das cinco entidades por visitantes e preservação da planilha, além dos testes de regressão dos cálculos, CRUD, filtros e exportação.

JavaScript/jsdom verifica controles anteriores, permissões visuais dos visitantes, temas claro/escuro/automático, mudanças de sistema, quatro fontes, densidade, números, persistência e separação por usuário, restauração, redução de movimento, posição do botão à esquerda, abertura/fechamento e reabertura dos pop-ups, gráficos e mostrar/ocultar senha. Rede e Plotly são simulados nessa suíte; a persistência real nas cópias Excel é validada separadamente pela suíte Flask.

Para repetir:

```powershell
python scripts/testar.py
python scripts/preparar_testes_frontend.py
npm.cmd ci --ignore-scripts --no-audit --no-fund
npm.cmd test
```

A ferramenta de navegador não conseguiu iniciar o runtime nesta sessão. Portanto **não foram certificados visualmente** o contraste final, a suavidade das animações ou a ausência de sobreposição nas resoluções 1920×1080, 1600×900, 1366×768, 1280×720 e 390×844, principalmente com fontes Grande/Muito grande. O jsdom não mede renderização CSS. Essa revisão no navegador permanece pendente e não é apresentada como teste realizado.

Ao atualizar uma instância em uso, pare o Flask com `Ctrl+C`, execute `python app.py` novamente e atualize a página com `Ctrl+F5`.
