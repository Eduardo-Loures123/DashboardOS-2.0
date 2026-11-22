# Agenda Operacional — visual baseado na referência

06/11/2026. Alterações exclusivamente locais.

## Resultado

Calendário à esquerda e acompanhamento do dia à direita, com títulos, ícones e divisórias. Navegação mensal com botões de borda azul, células arredondadas, hoje em amarelo `#FFBF00`, seleção com contorno e marcadores derivados dos eventos reais. Cartões com ícone, faixa lateral, tipo de registro, código/título, status, ação Consultar e curvas decorativas produzidas em CSS. O verde principal é `#50CF01`, conforme pedido.

A lista tem rolagem interna; títulos e data permanecem fora da região rolável. Em telas de até 900px o acompanhamento passa para baixo do calendário. Temas claro/escuro e preferência por movimento reduzido são respeitados.

## Arquivos

- `templates/dashboard.html`: estrutura dos dois lados da Agenda.
- `templates/base.html`: carrega `agenda.css` exclusivamente no dashboard.
- `static/css/agenda.css`: estilos isolados em `.calendar-panel`.
- `static/js/dashboard.js`: apresentação de cartões, ícones, marcadores e títulos; mantém os eventos, filtros e destinos de consulta existentes.
- Este relatório.

Nenhuma alteração no backend, regras de negócio, permissões, notificações, dados, AWS ou publicação. Alterações anteriores de cores, divisórias e paginação preservadas.

## Validação

- Fixtures regeneradas com o script existente em cópia temporária dos dados.
- Inspeção visual em navegador real: Agenda completa no desktop escuro, móvel escuro e desktop claro.
- Geometria conferida nas larguras 1600, 1440, 1024, 768, 390 e 320px; estados expandido/recolhido da barra lateral também conferidos em 1440, 1024 e 320px. Sem overflow horizontal da página ou do painel.
- Testados mês anterior/próximo, seleção de dia, preservação do foco e link ao registro correspondente.
- Conteúdo dos cartões comparado aos eventos da data selecionada: mesma quantidade, códigos e status. Estado sem eventos confirmado.
- Lista rolada 99,2px sem mover o cabeçalho de acompanhamento.
- Os marcadores usam eventos existentes, sem criar registros ou datas artificiais. Datas da imagem não foram fixadas no aplicativo.
- Testes Node: 89 aprovados, zero falhas. A suíte foi repetida após o ajuste final do texto do mês.
- `python scripts/testar.py`: 164 entradas, 162 aprovadas e dois erros de importação por falta de Pillow (`PIL`), em `tests.test_profile_redesign` e `tests.test_visual_identity`. Mesma limitação de ambiente registrada nas etapas anteriores.

Não houve homologação em produção ou comparação visual exaustiva de todas as outras telas. Os estilos novos são restritos à Agenda do dashboard.
