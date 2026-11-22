# Correções de divisórias e paginação — 06/11/2026

## Arquivos

- `static/css/sprint-layout.css`: único arquivo de implementação alterado nesta tarefa.
- Este relatório. Fixtures locais de teste também foram regeneradas pelo script existente.
- Alterações anteriores no projeto foram preservadas. Sem alteração de versão, regras de negócio ou JavaScript.

## Causas e soluções

**Equipes:** a regra final de `.teams-grid` definia margem, padding, rolagem e contenção de pintura, mas não uma borda superior. Somente o rodapé tinha `border-top`. Foi acrescentada a mesma borda à grade: mesma expressão de cor, espessura e limites laterais. A borda pertence ao contêiner de rolagem, portanto não acompanha o conteúdo. Foram preservados `overflow:auto`, `contain:paint`, isolamento, dimensões e estilos dos cartões.

**Paginação:** o rodapé compartilhado tinha padding apenas acima (`7px 0 0`), enquanto o painel acrescentava 12px abaixo (10px no móvel). Equipes tinha uma exceção de 5px acima/abaixo, ainda somada ao padding inferior do painel. Relatórios repetia o desequilíbrio com padding superior de 8px e 16px abaixo no painel pai. `align-items:center` sozinho centralizava apenas dentro da caixa errada.

O espaço inferior do painel foi incorporado ao rodapé, com padding simétrico, alinhamento de linhas e filhos e remoção de margens dos grupos. O espaço mínimo total existente foi preservado: 54px nas tabelas desktop, 52px no móvel e 46px em relatórios. O seletor mantém sua altura e tem uma caixa sem espaço de linha excedente. Foi removida a exceção de geometria de Equipes para usar o mesmo ajuste compartilhado. Não foram alterados botões, cores existentes, fontes, ícones ou lógica de paginação.

## Verificação no navegador

Servidor HTTP estático restrito a `127.0.0.1:8765`, com HTML/JSON produzidos pelo preparador de fixtures em cópia temporária do Excel. Requisições de API interceptadas no navegador: dados servidos pelas fixtures e respostas neutras para chamadas auxiliares. Nenhum backend real foi iniciado para esta inspeção.

- Funcionários, Equipes, Ordens de Serviço, Acessos, Vencimentos, Renovações e Relatórios: geometria verificada em 1440×900, 1024×768 e 390×844, incluindo estados expandido/recolhido da barra lateral.
- Medição final das sete telas nos três tamanhos: diferença de espaçamento exterior superior/inferior igual a zero, diferença entre os centros dos controles igual a zero e sem overflow horizontal da página.
- Em telas estreitas, o contador pode ficar em outra linha conforme a quebra responsiva existente; o conjunto continua com espaço simétrico e os controles de navegação compartilham o eixo.
- Equipes: bordas superior e inferior com estilos calculados iguais. Após rolar 234,4px, posições da borda superior, cabeçalho e rodapé permaneceram iguais. Conteúdo contido pela região de pintura.
- Capturas de Equipes inspecionadas visualmente no desktop e no móvel, incluindo conteúdo rolado. As demais telas foram verificadas por geometria renderizada; não houve comparação visual exaustiva de todos os componentes do sistema.
- Equipes com 61 registros sintéticos apenas na memória do navegador: selecionar 24, 48 e 12 exibiu respectivamente 24, 48 e 12 cartões; próxima página mudou de `1 / 6` para `2 / 6`, e anterior retornou a `1 / 6`.
- Paginação adicional de atividades de perfil e notificações foi localizada e inspecionada no CSS: já usa alinhamento central sem a combinação de painel/rodapé responsável pelo defeito. Não recebeu alterações; sua aparência não foi validada nesta inspeção.

## Testes

- `python scripts/preparar_testes_frontend.py`: aprovado, usando cópia temporária.
- `node --test --test-isolation=none tests/frontend.test.cjs`: 89 aprovados, zero falhas; inclui navegação, quantidade por página e opções exclusivas de Equipes.
- `python scripts/testar.py`: 164 entradas executadas, 162 aprovadas e dois erros de importação. `tests.test_profile_redesign` e `tests.test_visual_identity` não carregaram porque `PIL` (Pillow) não está instalado no Python utilizado. Esses módulos permanecem pendentes de execução em ambiente com a dependência disponível.
- `npm test` foi bloqueado pela política de execução de `npm.ps1`; o comando Node acima executou a suíte sem alterar a política do sistema.

Não houve deploy, acesso à AWS ou envio real de e-mails. A validação usou os scripts de teste existentes, dados temporários e mocks; não foram acionados trabalhadores operacionais de notificação. Não foi feita homologação em produção.
