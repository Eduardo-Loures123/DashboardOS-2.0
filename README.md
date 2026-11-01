# DashboardOS 2.0

> **Atualização Next disponível nesta branch, ainda não publicada.** Inclui perfis de acesso, administração de contas, perfil funcional, notificações persistentes, comunicados, worker de vencimentos, outbox de e-mail desativada por padrão e componentes visuais compartilhados. Leia [plano e arquitetura](NEXT_PLAN.md), [configuração, migração, testes e rollback](NEXT_OPERATIONS.md) e [changelog](CHANGELOG.md). Contas reais não foram migradas/promovidas. A ativação exige migração com backup e confirmação; SMTP real e homologação visual/Linux permanecem pendentes.

Validação desta entrega: **41 testes Python e 36 testes DOM aprovados**. Consulte [resultados e pendências de homologação](NEXT_VALIDATION.md).

**Sistema web para gerenciamento de ordens de serviço, funcionários, equipes, acessos e renovações.**

O DashboardOS 2.0 é um projeto desenvolvido para facilitar o acompanhamento de informações operacionais por meio de uma interface organizada, com indicadores, gráficos, tabelas e ferramentas de consulta.

O sistema reúne dados que normalmente seriam acompanhados em diferentes planilhas, permitindo visualizar prazos, identificar pendências, consultar registros e acompanhar situações que exigem atenção.

Esta versão representa uma etapa importante da evolução do projeto, com melhorias na interface, autenticação de usuários, gerenciamento de registros e preparação para utilização em ambiente de produção.

## 1. Sobre o projeto

O DashboardOS nasceu da necessidade de tornar o controle de informações operacionais mais simples e eficiente.

Em atividades que envolvem funcionários, equipes, ordens de serviço e permissões de acesso, acompanhar datas de vencimento e solicitações de renovação é fundamental para evitar atrasos e manter os registros organizados.

O sistema foi desenvolvido para centralizar essas informações e apresentá-las de forma visual, facilitando a identificação de prioridades.

Entre seus principais objetivos estão:

- Organizar informações de funcionários e equipes.
- Acompanhar ordens de serviço e seus respectivos prazos.
- Controlar a validade de acessos.
- Identificar vencimentos e situações urgentes.
- Registrar e acompanhar renovações.
- Disponibilizar indicadores, gráficos e relatórios.
- Facilitar consultas e atualizações dos dados.

O projeto também tem finalidade de aprendizado e aprimoramento profissional, envolvendo desenvolvimento web, manipulação de dados, organização de código, testes e implantação em servidor.

## 2. Tecnologias utilizadas

O DashboardOS 2.0 utiliza diferentes tecnologias, cada uma com uma função no desenvolvimento e funcionamento do sistema.

| Tecnologia | Utilização |
|---|---|
| Python | Regras de negócio e processamento dos dados |
| Flask | Aplicação web e comunicação entre interface e servidor |
| HTML | Estrutura das páginas |
| CSS | Estilização, responsividade e aparência visual |
| JavaScript | Interatividade, filtros e atualização da interface |
| Excel | Armazenamento e organização dos dados operacionais |
| SQLite | Persistência de informações relacionadas à autenticação |
| Git | Controle de versões do código |
| GitHub | Hospedagem e compartilhamento do repositório |
| AWS EC2 | Hospedagem da aplicação |
| Gunicorn | Execução da aplicação Python em produção |
| Nginx | Servidor web e encaminhamento das requisições |

A arquitetura separa as páginas, os arquivos visuais e as regras de negócio, facilitando a manutenção e a implementação de novas funcionalidades.

## 3. Funcionalidades da versão 2.0

### Dashboard principal

A página inicial apresenta uma visão geral das informações cadastradas, utilizando indicadores e gráficos para facilitar o acompanhamento.

Por meio dela, é possível consultar dados consolidados, identificar situações que merecem atenção e navegar para as áreas específicas do sistema.

### Gerenciamento de funcionários

Permite consultar e administrar registros de funcionários.

Os usuários autorizados podem cadastrar, visualizar, editar e excluir informações, respeitando as validações e dependências existentes.

### Gerenciamento de equipes

Organiza os funcionários em equipes e permite acompanhar os vínculos entre os registros.

Essa estrutura ajuda a relacionar informações operacionais aos respectivos responsáveis.

### Ordens de serviço

Permite acompanhar as ordens de serviço cadastradas, incluindo informações relacionadas a prazos, situação e prioridade.

O sistema oferece recursos de consulta, pesquisa, filtragem e gerenciamento dos registros.

### Controle de acessos

Reúne informações sobre acessos e suas datas de validade.

Essa funcionalidade auxilia no acompanhamento de permissões e na identificação de acessos próximos do vencimento.

### Vencimentos

Apresenta os registros classificados conforme seus prazos.

As categorias utilizadas pelo sistema permitem distinguir situações vencidas, vencimentos próximos e registros com maior prazo disponível.

### Renovações

Permite acompanhar informações relacionadas às solicitações de renovação, facilitando a consulta de pendências e a organização do processo.

### Relatórios

Disponibiliza visualizações e recursos de exportação para auxiliar na análise dos dados.

Os relatórios respeitam os filtros e critérios disponíveis na aplicação.

## 4. Interface e experiência de utilização

Uma das prioridades desta versão foi melhorar a organização visual do sistema.

A interface utiliza um menu lateral para navegação entre as páginas, além de componentes com bordas arredondadas, gráficos interativos e tabelas com ferramentas de consulta.

Entre os recursos disponíveis estão:

- Alternância entre temas claro, escuro e automático.
- Ajustes de tamanho das fontes.
- Configurações de densidade e apresentação dos dados.
- Menu lateral recolhível.
- Pesquisa, filtros e ordenação nas tabelas.
- Ampliação de gráficos para análise.
- Preferências visuais individuais.

As preferências de aparência são mantidas separadamente dos dados operacionais e das credenciais de acesso.

## 5. Acesso ao sistema

O DashboardOS 2.0 possui uma tela de autenticação e diferentes possibilidades de utilização.

### Acesso administrativo

Na atualização Next, superadministradores gerenciam contas/comunicados/auditoria; administradores mantêm o CRUD operacional; usuários têm leitura e perfil próprio; visitantes continuam restritos à consulta. A permissão é validada no servidor. Consulte os comandos de migração/promoção no guia Next antes de ativar o gerenciamento de contas.

Destinado aos usuários autorizados a gerenciar as informações.

Após a autenticação, o administrador pode utilizar os recursos de cadastro, edição e exclusão, conforme as regras de cada área.

### Modo visitante

Permite conhecer e consultar as informações disponibilizadas pelo sistema sem realizar alterações nos registros.

Nesse modo, é possível navegar pelas páginas, pesquisar informações, utilizar filtros, visualizar gráficos e consultar relatórios.

As operações de criação, edição e exclusão permanecem bloqueadas.

**Importante:** o sistema não deve ser publicado com credenciais administrativas de exemplo ou senhas compartilhadas.

## 6. Tutorial de utilização

Esta seção apresenta um roteiro básico para conhecer as principais funcionalidades do DashboardOS 2.0.

### Passo 1 — Entrar na aplicação

Abra o endereço da aplicação no navegador.

Na tela inicial, escolha entre realizar a autenticação com uma conta autorizada ou acessar o modo visitante, quando disponível.

### Passo 2 — Conhecer o dashboard

Após entrar, utilize a página principal para observar os indicadores e gráficos.

Essa visão permite compreender a situação geral dos registros e identificar quais informações precisam de uma análise mais detalhada.

### Passo 3 — Navegar pelo menu lateral

Utilize o menu lateral para acessar as diferentes áreas do sistema.

O menu pode ser recolhido para disponibilizar mais espaço para tabelas e gráficos.

### Passo 4 — Consultar funcionários e equipes

Acesse as páginas correspondentes para visualizar os registros cadastrados.

Utilize a pesquisa e os recursos de ordenação para encontrar informações específicas.

Se estiver autenticado com permissão administrativa, também poderá realizar operações de gerenciamento.

### Passo 5 — Acompanhar ordens de serviço

Abra a página de ordens de serviço e utilize os filtros disponíveis para analisar os registros.

Verifique principalmente os prazos, a situação das ordens e as informações de prioridade.

### Passo 6 — Verificar acessos e vencimentos

Acesse as páginas de acessos e vencimentos para identificar registros próximos do prazo final ou que já estejam vencidos.

Essa consulta ajuda a organizar o acompanhamento e a definir quais situações devem ser verificadas primeiro.

### Passo 7 — Consultar renovações

Na página de renovações, acompanhe os registros relacionados às solicitações e seus respectivos estados.

### Passo 8 — Utilizar gráficos e relatórios

Interaja com os gráficos para ampliar as visualizações quando necessário.

Utilize os filtros, as pesquisas e os recursos de exportação para obter informações mais específicas.

### Passo 9 — Personalizar a aparência

Abra as configurações disponíveis na interface para ajustar o tema, o tamanho das fontes e outras preferências visuais.

### Passo 10 — Encerrar o acesso

Ao terminar, utilize a opção de sair ou trocar de usuário, especialmente quando estiver utilizando um computador compartilhado.

## 7. Instalação local para desenvolvedores

As instruções a seguir apresentam uma forma básica de executar o projeto em um computador Windows utilizando o VS Code e o PowerShell.

### Requisitos

Antes de começar, instale:

- Python compatível com as dependências do projeto.
- Git.
- Visual Studio Code ou outro editor de sua preferência.

### 7.1. Clonar o repositório

Abra um terminal e execute:

```bash
git clone https://github.com/Eduardo-Loures123/DashboardOS-2.0.git
```

Entre na pasta:

```bash
cd DashboardOS-2.0
```

### 7.2. Criar o ambiente virtual

No PowerShell:

```powershell
python -m venv .venv
```

Ative o ambiente:

```powershell
.\.venv\Scripts\Activate.ps1
```

### 7.3. Instalar as dependências

```powershell
python -m pip install -r requirements.txt
```

### 7.4. Preparar os dados

O projeto utiliza uma planilha Excel como fonte de dados operacionais.

Por motivos de segurança e privacidade, os arquivos de dados locais não são incluídos no repositório público.

Para preparar um conjunto demonstrativo, utilize o script disponível no projeto:

```powershell
python scripts/gerar_dados.py
```

O gerador foi desenvolvido para criar dados fictícios e evitar a substituição de uma planilha existente.

Antes de executá-lo, confirme que não há informações importantes no destino utilizado pelo script.

### 7.5. Criar uma conta administrativa

O projeto disponibiliza um comando para criação de administradores:

```powershell
python -m flask --app app criar-admin
```

Siga as instruções exibidas no terminal para cadastrar as credenciais.

Não utilize senhas simples ou compartilhadas.

### 7.6. Iniciar a aplicação

Execute:

```powershell
python app.py
```

Depois, abra no navegador:

```text
http://127.0.0.1:5000
```

O endereço acima é destinado à execução local.

**Observação:** as configurações necessárias para executar a aplicação podem variar conforme o ambiente. Para implantação em produção, consulte também a documentação disponível em `deployment/aws/`.

## 8. Dados utilizados

O DashboardOS trabalha com informações relacionadas a:

- Funcionários.
- Equipes.
- Ordens de serviço.
- Acessos.
- Renovações.

O projeto inclui um gerador de dados fictícios para demonstrações e testes.

Os conjuntos demonstrativos permitem conhecer a aplicação sem depender de informações reais de uma organização.

Os dados de produção, bancos locais, arquivos de configuração privados e credenciais não fazem parte do repositório público.

## 9. Organização do projeto

A estrutura principal do repositório está organizada da seguinte forma:

```text
DashboardOS-2.0/
│
├── app.py
├── requirements.txt
├── package.json
├── README.md
│
├── services/
│   └── Regras de negócio e serviços da aplicação
│
├── templates/
│   └── Páginas HTML
│
├── static/
│   ├── css/
│   └── js/
│
├── scripts/
│   └── Scripts auxiliares e geração de dados
│
├── tests/
│   └── Testes automatizados
│
└── deployment/
    └── aws/
        └── Configurações e documentação de implantação
```

Essa organização facilita a localização dos arquivos e permite desenvolver novas funcionalidades sem concentrar todo o código em um único lugar.

## 10. Testes e qualidade

O projeto possui testes voltados para diferentes partes da aplicação, incluindo autenticação, indicadores, regras de negócio, rotas e componentes da interface.

Os testes ajudam a identificar problemas após alterações no código e reduzem o risco de comprometer funcionalidades já existentes.

Para executar os testes Python, com as dependências de desenvolvimento necessárias instaladas:

```powershell
python -m pytest
```

Nesta branch, o comando validado para a suíte Python é `python scripts/testar.py`. Para a interface: `python scripts/preparar_testes_frontend.py` e `node --test --test-isolation=none tests/frontend.test.cjs`. Os testes usam cópias dos dados e envio simulado, sem SMTP real. A validação DOM não substitui homologação visual em navegador.

A presença dos testes não significa que o sistema esteja livre de falhas. A validação contínua faz parte do processo de evolução do projeto.

## 11. Hospedagem e implantação

O DashboardOS 2.0 também foi preparado para execução em um servidor AWS EC2.

A configuração de produção utiliza Gunicorn para executar a aplicação Flask e Nginx para receber e encaminhar as requisições.

O ambiente de hospedagem conta com acesso HTTPS e separação entre o código da aplicação e os arquivos privados utilizados pelo sistema.

A documentação técnica da implantação está disponível na pasta:

```text
deployment/aws/
```

**Importante:** publicar uma nova versão no GitHub não atualiza automaticamente a aplicação hospedada na AWS. As alterações devem ser testadas e implantadas no servidor por meio de um processo separado.

## 12. Evolução do projeto

O DashboardOS 2.0 não é considerado um produto encerrado. O repositório será utilizado para registrar novas versões, melhorias e correções ao longo do desenvolvimento.

A versão atual estabelece uma base para continuar evoluindo o sistema.

### Possibilidades para próximas versões

Os alertas, a outbox de e-mail, a administração e o perfil descritos no guia Next já têm implementação nesta branch; configuração/ativação reais e homologação permanecem separadas. A lista histórica abaixo descreve oportunidades da versão 2.0 base.

As seguintes ideias representam oportunidades de desenvolvimento e ainda não devem ser consideradas funcionalidades implementadas:

- Aperfeiçoamento dos alertas de vencimento.
- Notificações automáticas por e-mail.
- Novas opções de personalização da interface.
- Indicadores e relatórios adicionais.
- Melhorias na experiência de uso em dispositivos móveis.
- Novas formas de integração e atualização dos dados.
- Aprimoramento dos mecanismos de segurança.
- Automatização de testes e implantação.
- Melhorias de desempenho e manutenção.

As próximas versões poderão incluir outras funcionalidades conforme as necessidades identificadas durante o desenvolvimento e os testes.

### Histórico de versões

**Versão 2.0 — Base atual publicada**

- Organização do sistema web em diferentes módulos.
- Gerenciamento de informações operacionais.
- Dashboard com indicadores e gráficos.
- Autenticação e modo visitante.
- Configurações de aparência.
- Recursos de pesquisa, filtros e relatórios.
- Preparação para implantação em produção.
- Publicação do código no GitHub.

As alterações futuras serão documentadas por meio dos commits e das versões do repositório.

## 13. Sobre o desenvolvimento

O DashboardOS 2.0 é um projeto de desenvolvimento de software criado como parte do aprendizado e da prática de tecnologias utilizadas no mercado de TI.

Seu desenvolvimento envolve não apenas programação, mas também organização de dados, experiência do usuário, testes, versionamento, segurança e hospedagem de aplicações web.

O objetivo é continuar aprimorando o sistema, aplicando novos conhecimentos e desenvolvendo soluções cada vez mais completas.

**Desenvolvedor:** Eduardo Loures

**Repositório:** https://github.com/Eduardo-Loures123/DashboardOS-2.0

---

*Projeto em evolução. Novas versões, correções e funcionalidades poderão ser adicionadas futuramente.*
