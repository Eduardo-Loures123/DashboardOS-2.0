const iconPaths={
 'panel-left':'M3 4h18v16H3zM9 4v16M5.5 8h1M5.5 12h1M5.5 16h1',
 expand:'M8 3H3v5M16 3h5v5M21 16v5h-5M8 21H3v-5M3 3l6 6M21 3l-6 6M21 21l-6-6M3 21l6-6',
 calendar:'M4 5h16v16H4zM8 2v6M16 2v6M4 10h16M8 14h1M15 14h1M8 18h1M15 18h1',
 camera:'M4 7h4l2-3h4l2 3h4v13H4zM16 13a4 4 0 1 0-8 0 4 4 0 0 0 8 0',
 dashboard:'M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9',
 funcionarios:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M18 8a3 3 0 0 1 0 6M22 21v-2a4 4 0 0 0-3-3.9',
 equipes:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M19 8v6M16 11h6',
 'ordens-servico':'M9 4H5v17h14V4h-4M9 2h6v5H9zM8 12h8M8 16h6',
 acessos:'M12 12 2 22h5v-3h3v-3h3l2-2M22 8a6 6 0 1 0-12 0 6 6 0 0 0 12 0M17 7h.01',
 vencimentos:'M12 8v5l3 2M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18',
 renovacoes:'M14 2v6h6M10 22H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h8l6 6v2M13 16a4 4 0 0 1 6.8-2.8L22 15M22 11v4h-4M21 18a4 4 0 0 1-6.8 2.8L12 19M12 23v-4h4',
 relatorios:'M4 3v18h17M8 16v-5M13 16V7M18 16v-8',
 menu:'M4 6h16M4 12h16M4 18h16',
 refresh:'M3 12a9 9 0 0 1 15.36-6.36L21 8M21 3v5h-5M21 12a9 9 0 0 1-15.36 6.36L3 16M8 16H3v5',
 filter:'M4 7h9M17 7h3M4 17h3M11 17h9M13 4v6M7 14v6',
 upload:'M12 16V4m-5 5 5-5 5 5M5 17v4h14v-4',
 download:'M12 3v12m-5-5 5 5 5-5M5 17v4h14v-4',
 plus:'M12 5v14M5 12h14',close:'M6 6l12 12M18 6 6 18',
 external:'M7 17 17 7M7 7h10v10',left:'m15 6-6 6 6 6',right:'m9 6 6 6-6 6',down:'m6 9 6 6 6-6',
 'arrow-up':'M12 19V5m-6 6 6-6 6 6','arrow-down':'M12 5v14m-6-6 6 6 6-6',
 settings:'M10 2h4l.7 3L17 6.3l3-.8 2 3.5-2.2 2v2l2.2 2-2 3.5-3-.8-2.3 1.3-.7 3h-4l-.7-3L7 17.7l-3 .8L2 15l2.2-2v-2L2 9l2-3.5 3 .8L9.3 5 10 2ZM15.5 12a3.5 3.5 0 1 0-7 0 3.5 3.5 0 0 0 7 0',
 help:'M9.1 9a3 3 0 0 1 5.8 1c0 2-3 2-3 4M12 17h.01M21 12a9 9 0 1 0-18 0 9 9 0 0 0 18 0',
 user:'M19 21v-2a7 7 0 0 0-14 0v2M17 7a5 5 0 1 0-10 0 5 5 0 0 0 10 0',
 guest:'M21 12a9 9 0 1 0-18 0 9 9 0 0 0 18 0M16 12a4 4 0 1 0-8 0 4 4 0 0 0 8 0',
 logout:'M9 3H4v18h5M10 12h11m-5-5 5 5-5 5',login:'M15 3h5v18h-5M3 12h11M9 7l5 5-5 5',
 bell:'M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4',
 search:'M21 21l-5-5M18 10a8 8 0 1 0-16 0 8 8 0 0 0 16 0',check:'m5 12 4 4L20 5',
 trash:'M3 6h18M9 6V3h6v3M5 6l1 15h12l1-15M10 10v7M14 10v7',
 inbox:'M4 4h16l2 12v5H2v-5L4 4M2 16h6l2 3h4l2-3h6',circle:'M21 12a9 9 0 1 0-18 0 9 9 0 0 0 18 0',
 info:'M12 11v6M12 7h.01M21 12a9 9 0 1 0-18 0 9 9 0 0 0 18 0',
 warning:'m12 3 10 18H2L12 3M12 9v5M12 17h.01',
 mail:'M3 5h18v14H3zM3 5l9 7 9-7',lock:'M5 10h14v11H5zM8 10V7a4 4 0 0 1 8 0v3M12 14v3',
 edit:'m15 5 4 4M4 20l1-5L16 4a2.8 2.8 0 0 1 4 4L9 19z',
 save:'m20 7-4-4H4v18h16zM7 3v6h9V3M7 21v-8h10v8',
 eye:'M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12M15 12a3 3 0 1 0-6 0 3 3 0 0 0 6 0',
 broom:'m14 4 6-2M17 3l-6 9M7 11l7 5-5 6-7-5 5-6ZM5 16l5 4M7 14l5 4',
 shield:'M12 3 3 7v6c0 5 9 8 9 8s9-3 9-8V7zM8 12l3 3 5-6'};
function iconSvg(name){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('class','ui-icon');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.8');svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');svg.setAttribute('aria-hidden','true');svg.setAttribute('focusable','false');const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d',iconPaths[name]||iconPaths.info);svg.append(path);return svg;}
function actionLabel(node,text,icon){node.replaceChildren(...(icon?[iconSvg(icon)]:[]),document.createTextNode(text));return node;}
function actionIcon(text){
 const rules=[[/^(Salvar|Atualizar senha)/,'save'],[/^(Cancelar|Fechar)/,'close'],[/^(Excluir|Confirmar exclusão|Limpar central|Limpar minha central|Confirmar limpeza)/,'trash'],[/^Editar/,'edit'],[/^(Ver|Consultar)/,'eye'],[/^(Criar|Novo)/,'plus'],[/^(Enviar código|Solicitar novo código)/,'mail'],[/^(Confirmar e-mail|Marcar)/,'check'],[/^(Atualizar situação|Restaurar)/,'refresh'],[/^Aplicar filtros/,'filter'],[/^Limpar filtros/,'broom']];
 return rules.find(([pattern])=>pattern.test(text))?.[1];
}
document.querySelectorAll('[data-icon]').forEach(node=>node.replaceChildren(iconSvg(node.dataset.icon)));
