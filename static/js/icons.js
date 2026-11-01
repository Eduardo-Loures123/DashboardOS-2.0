const iconPaths={
 dashboard:'M3 10 12 3l9 7M5 9v12h5v-7h4v7h5V9',
 funcionarios:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M18 8a3 3 0 0 1 0 6M22 21v-2a4 4 0 0 0-3-3.9',
 equipes:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8M20 8v6M17 11h6',
 'ordens-servico':'M9 4H5v17h14V4h-4M9 2h6v5H9zM8 12h8M8 16h6',
 acessos:'M15 7a5 5 0 1 0-3 4.6L5 19H2v3h5v-3h3l4-4M16 7h.01',
 vencimentos:'M12 8v5l3 2M12 3a9 9 0 1 0 0 18 9 9 0 0 0 0-18',
 renovacoes:'M20 7v5h-5M4 17v-5h5M5.3 7A8 8 0 0 1 19 6l1 6M4 12l1 6a8 8 0 0 0 13.7-1',
 relatorios:'M4 3v18h17M8 16v-5M13 16V7M18 16v-8'};
function iconSvg(name){const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('fill','none');svg.setAttribute('stroke','currentColor');svg.setAttribute('stroke-width','1.8');svg.setAttribute('stroke-linecap','round');svg.setAttribute('stroke-linejoin','round');svg.setAttribute('aria-hidden','true');const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d',iconPaths[name]||iconPaths.dashboard);svg.append(path);return svg;}
document.querySelectorAll('.nav-icon').forEach(node=>node.append(iconSvg(node.dataset.icon)));
