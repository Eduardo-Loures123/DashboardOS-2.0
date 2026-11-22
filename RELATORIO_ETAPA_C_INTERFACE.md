# Etapa C — lateral, rolagem e geometria das abas

Concluída localmente em 05/11/2026. Etapas D e E não iniciadas.

## Correções
- Removido o pseudoelemento decorativo lateral com 180% de largura, causador do transbordamento. A lateral mantém seu gradiente existente; a arte definitiva depende da Etapa D.
- Estilos específicos da lateral consolidados em static/css/profile-redesign.css; removidas regras legadas conflitantes das folhas anteriores, preservando seus estilos dos demais componentes.
- Lateral organizada em três regiões por CSS Grid: cabeçalho, navegação central rolável e ações inferiores estáveis. Navegação com scrollbar discreto e acessível. A correção não depende de esconder overflow horizontal: lateral com overflow visible; navegação com overflow auto, e largura do conteúdo validada no navegador.
- Larguras internas, ícones e textos dimensionados para não transbordar. Rotas, ações, proteção CSRF, preferência de recolhimento e módulos preservados.
- Em telas baixas, ações inferiores ocupam duas colunas; na lateral recolhida, a largura se adapta para preservar os alvos de clique. Em dispositivos móveis, apenas o menu aberto ocupa uma altura limitada à janela, com rolagem central e rodapé acessível.
- Abas com raio interno calculado: raio externo menos borda e padding. Desktop: 19 - 1 - 3 = 15 px. Controle compacto: 15 - 1 - 3 = 11 px. Alturas e colunas uniformes, ícones alinhados, texto com quebra quando necessário, transições e preferência de movimento reduzido preservadas.
- Adaptação por largura disponível do perfil (container query), incluindo duas colunas nas abas e reorganização da região da foto/campos quando a lateral deixa pouco espaço ao conteúdo.
- Correções funcionais da Etapa B preservadas. Sem alteração de JavaScript da aplicação, backend, permissões, SMTP, versão ou agendamentos.

## Arquivos alterados
- static\css\enterprise.css
- static\css\premium.css
- static\css\profile-redesign.css
- static\css\reference.css
- static\css\refinement.css
- static\css\responsive.css
- static\css\stability.css
- static\css\style.css
- static\css\visual-polish.css
- tests\frontend.test.cjs

Relatório adicional: RELATORIO_ETAPA_C_INTERFACE.md.

## Reversão
Cópias anteriores em diagnosticos/etapa-c-20261105-010253/before/. Restaurar somente arquivos correspondentes após verificar alterações posteriores; não restaurar outros trabalhos existentes.

## Testes executados
- Python: 174 aprovados. scripts/testar_notificacoes.py --completo executa scripts/testar.py sob isolamento: bancos temporários, Excel fictício, SMTP e conexões externas bloqueados.
- Frontend: 69 aprovados, três cenários agrupados novos: restauração dos submenus, menu móvel sem alterar preferência desktop/rotas/CSRF, teclado e acessibilidade das quatro abas. Fixtures geradas com scripts/testar_notificacoes.py --frontend-fixtures.
- Playwright: prévia existente em 127.0.0.1:5099, dados fictícios e SQLite temporário, contexto de navegador separado. Prévia encerrada ao concluir.
- 44 combinações do perfil: temas claro/escuro, lateral expandida/recolhida e onze tamanhos solicitados, incluindo 320 px de largura e 320 px de altura. Nenhum transbordamento horizontal na página, lateral ou navegação; nenhuma rolagem vertical da lateral inteira; rodapé dentro dos limites; textos das abas sem corte; raios calculados corretamente. Verificado que a rolagem central não desloca cabeçalho/rodapé. Navegação por teclado funcional.
- 32 verificações adicionais: oito páginas operacionais, dois temas, dois estados da lateral. Sem transbordamento da página/lateral e com rodapé acessível.
- Zero erros JavaScript capturados nas verificações.
- Capturas reais inspecionadas: perfil-expandido.png, perfil-recolhido.png, perfil-mobile-escuro.png e perfil-desktop-escuro.png, no diretório de diagnóstico.
- A validação final usa a largura útil documentElement.clientWidth, descontando a barra de rolagem da janela. Em escala de tela fracionária, bordas podem ser arredondadas pelo navegador; a relação dos raios é verificada pelos tokens CSS declarados.

## Preservação
Baseline registrado ANTES das alterações desta etapa e comparação final exclusivamente em leitura: todas as 17 tabelas do banco principal inalteradas, incluindo account, users, outbox, mail_attempts e profile_activities; Excel também inalterado. As cinco mensagens antigas permanecem pending com attempts=0 e conteúdo inalterado. Evidência: preservation.json. Nenhum e-mail real, processamento da fila principal, operação AWS ou deploy.

## Evidências
- diagnosticos/etapa-c-20261105-010253/python.log
- diagnosticos/etapa-c-20261105-010253/frontend.log
- diagnosticos/etapa-c-20261105-010253/browser-validation-final.json
- diagnosticos/etapa-c-20261105-010253/browser-routes.json
- diagnosticos/etapa-c-20261105-010253/playwright-check.js
- diagnosticos/etapa-c-20261105-010253/preservation.json

## Limitações e próxima etapa
Não se declara fidelidade gráfica final aprovada. Logo oficial, ondas, fundos e acabamento final dos temas pertencem à Etapa D e dependem dos recursos gráficos oficiais identificados no diagnóstico. Aguardar autorização antes de prosseguir.
