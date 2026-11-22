let agendaDate='',agendaMonth=new Date().getMonth(),agendaYear=new Date().getFullYear();
function indicatorLink(key){
 const status={'Concluídas':'Concluída','Pendentes':'Pendente','Em andamento':'Em andamento'}[key];
 return status?'/ordens-servico?'+new URLSearchParams({status}):null;
}
function renderDashboard(){
 const values=state.indicators;
 const primary=['Ordens de serviço','Acessos','Equipes','Urgentes'];const icons=['ordens-servico','acessos','equipes','warning'];
 const target=document.querySelector('#kpis');target.replaceChildren();
 primary.forEach((label,i)=>target.append(el('div',{class:'kpi','data-category':['orders','access','teams','urgent'][i]},[el('span',{class:'kpi-label',text:label}),el('strong',{text:DashboardPreferences.formatNumber(values[label]||0)}),el('span',{class:'kpi-icon','aria-hidden':'true'},[iconSvg(icons[i])]),el('small',{text:label==='Urgentes'?'Alta ou crítica · não concluídas':'Dados reais · visão filtrada'})])));
 chartSpecs={...state.charts,teams:{...state.charts.teams,key:'teams',premiumBars:true,individualBars:true,externalLegend:true}};
 renderOrderTeamLegend(document.querySelector('#teams-legend'),chartSpecs.teams);renderOrderTeamMetrics(document.querySelector('#team-order-summary'),chartSpecs.teams);
 for(const [key,spec] of Object.entries(chartSpecs))drawChart(document.querySelector('#chart-'+key),spec);
 const total=values['Ordens de serviço'];document.querySelector('#completion').textContent=DashboardPreferences.formatNumber(total);
 const list=document.querySelector('#status-list');list.replaceChildren();['Concluídas','Pendentes','Em andamento'].forEach((key,i)=>list.append(el('div',{class:'status-row'},[el('span',{},[el('i',{style:'background:'+orderStatusPalette[['Concluída','Pendente','Em andamento'][i]]}),document.createTextNode(key)]),el('b',{text:(total?(values[key]/total*100).toLocaleString('pt-BR',{maximumFractionDigits:1}):0)+'% ('+DashboardPreferences.formatNumber(values[key])+')'})])));
 renderOverviewPanels();
 renderCalendar();observeCharts();
}
function renderOverviewPanels(){
 const overview=state.overview||{},urgent=document.querySelector('#urgent-orders');
 if(urgent){const table=el('table',{class:'urgent-table'}),head=el('thead',{},[el('tr',{},['OS','Solicitante','Equipe','Prioridade'].map(text=>el('th',{text})))]),body=el('tbody');
 for(const r of (overview.urgent||[]).slice(0,4)){const link=el('a',{href:'/ordens-servico?'+new URLSearchParams({q:r.codigo}),text:r.codigo});body.append(el('tr',{},[el('td',{},[link]),el('td',{text:r.nome_funcionario||'—'}),el('td',{text:optionLabel('equipe',r.equipe)}),el('td',{},[el('span',{class:'badge bad',text:r.prioridade})])]));}
 if(!body.children.length)body.append(el('tr',{},[el('td',{colspan:4,class:'empty',text:'Nenhuma ordem urgente nos filtros atuais.'})]));table.append(head,body);urgent.replaceChildren(table);}
 renderAccessAnalytics();
}
function renderCalendar(){
 const target=document.querySelector('#calendar'),today=new Date(),year=agendaYear,month=agendaMonth;
 const toISO=d=>d.getFullYear()+'-'+String(d.getMonth()+1).padStart(2,'0')+'-'+String(d.getDate()).padStart(2,'0');
 if(!agendaDate)agendaDate=toISO(today);
 const heading=el('div',{class:'calendar-heading'}),previous=el('button',{class:'icon-button',type:'button','data-month-step':'-1','aria-label':'Mês anterior',icon:'left'}),next=el('button',{class:'icon-button',type:'button','data-month-step':'1','aria-label':'Próximo mês',icon:'right'});
 const change=delta=>{const date=new Date(year,month+delta,1);agendaYear=date.getFullYear();agendaMonth=date.getMonth();renderCalendar();target.querySelector('[data-month-step="'+delta+'"]')?.focus();};previous.onclick=()=>change(-1);next.onclick=()=>change(1);
 heading.append(previous,el('h3',{text:new Date(year,month,1).toLocaleDateString('pt-BR',{month:'long',year:'numeric'}).replace(/^./,letter=>letter.toLocaleUpperCase('pt-BR'))}),next);target.replaceChildren(heading);
 const eventsByDate=new Map();for(const event of state.agenda?.events||[]){if(!eventsByDate.has(event.date))eventsByDate.set(event.date,[]);eventsByDate.get(event.date).push(event);}
 const grid=el('div',{class:'calendar-grid'});['D','S','T','Q','Q','S','S'].forEach(d=>grid.append(el('span',{class:'weekday',text:d})));
 const offset=new Date(year,month,1).getDay(),days=new Date(year,month+1,0).getDate();
 for(let i=0;i<offset;i++)grid.append(el('span'));
 for(let day=1;day<=days;day++){
  const iso=toISO(new Date(year,month,day)),count=state.calendar[iso]||0;
  const button=el('button',{type:'button',text:day,class:'calendar-day '+(count?'scheduled ':'')+(iso===toISO(today)?'today ':'')+(iso===agendaDate?'selected':''),'aria-pressed':String(iso===agendaDate),'data-date':iso,'aria-label':day+'/'+(month+1)+'/'+year+' · '+count+' OS previstas',...(iso===toISO(today)?{'aria-current':'date'}:{})});
  const dayEvents=eventsByDate.get(iso)||[],tones=[...new Set(dayEvents.map(agendaEventTone))];
  if(tones.length||count){const markers=el('span',{class:'agenda-day-markers','aria-hidden':'true'});for(const tone of tones.length?tones:['orders'])markers.append(el('i',{class:'agenda-dot tone-'+tone}));button.append(markers);button.setAttribute('aria-label',button.getAttribute('aria-label')+' · '+dayEvents.length+' acompanhamentos');}
  button.onclick=()=>{agendaDate=iso;renderCalendar();document.querySelector('[data-date="'+iso+'"]')?.focus();};grid.append(button);
 }
 const legend=el('div',{class:'calendar-legend'});for(const [cls,text] of [['scheduled','Previsões de OS'],['today','Hoje'],['selected','Data selecionada']])legend.append(el('span',{},[el('i',{class:cls,'aria-hidden':'true'}),document.createTextNode(text)]));
 target.append(grid,legend);renderAgendaDetail();
}
function agendaEventTone(item){
 if(['Revogado','Rejeitada','Cancelada'].includes(item.status))return 'danger';
 if(['Ativo','Concluída','Aprovada'].includes(item.status))return 'success';
 return item.kind==='renovacao'?'warning':'orders';
}
function renderAgendaDetail(){
 const target=document.querySelector('#agenda-detail');if(!target)return;
 const date=new Date(agendaDate+'T12:00:00');
 target.replaceChildren(el('h2',{class:'agenda-section-title',text:'Acompanhamento do dia',icon:'relatorios'}),el('h3',{class:'agenda-selected-date',text:date.toLocaleDateString('pt-BR',{day:'numeric',month:'long',year:'numeric'})}));
 const events=(state.agenda?.events||[]).filter(e=>e.date===agendaDate);
 if(!events.length){target.append(el('div',{class:'agenda-empty'},[el('strong',{text:'Nenhum acompanhamento nesta data'}),el('p',{text:'Selecione um dia para consultar previsões, vencimentos e solicitações reais.'})]));return;}
 const list=el('ul',{class:'agenda-events'});
 const labels={os:'Previsão de OS',acesso:'Vencimento de acesso',renovacao:'Solicitação de renovação'};
 for(const item of events){
  const tone=agendaEventTone(item),status=el('span',{class:'agenda-event-status'},[el('i',{class:'agenda-dot','aria-hidden':'true'}),document.createTextNode(item.status)]);
  const meta=el('span',{class:'agenda-event-meta'},[status,el('span',{class:'agenda-consult',text:'Consultar',icon:'external'})]);
  const copy=el('span',{class:'agenda-event-copy'},[el('small',{text:labels[item.kind]||'Acompanhamento'}),el('strong',{text:item.code+' · '+item.title}),meta]);
  const symbol=el('span',{class:'agenda-event-symbol','aria-hidden':'true'},[iconSvg({acesso:'acessos',os:'ordens-servico',renovacao:'renovacoes'}[item.kind]||'calendar')]);
  const link=el('a',{href:'/'+item.page+'?'+new URLSearchParams({q:item.code}),class:'agenda-event tone-'+tone},[symbol,copy]);
  list.append(el('li',{},[link]));
 }target.append(list);
}
function renderReports(){const select=document.querySelector('#report-type');const old=select.value;select.replaceChildren();Object.keys(state.reports).forEach(k=>select.append(el('option',{value:k,text:k})));if(old)select.value=old;select.onchange=showReport;document.querySelector('#report-download').onclick=download;showReport();}
function showReport(){
 const title=document.querySelector('#report-type').value,rows=state.reports[title]||[];
 document.querySelector('#report-title').textContent=title;
 const grouped=rows.length&&'grupo' in rows[0];
 const columns=rows.length?Object.keys(rows[0]):[];
 document.querySelector('#report-summary').replaceChildren(document.createTextNode(String(grouped?rows.reduce((a,r)=>a+r.quantidade,0):rows.length)),el('small',{text:grouped?'registros na análise':'registros encontrados'}));
 document.querySelector('#report-head').replaceChildren(el('tr',{},columns.map(k=>el('th',{text:state.labels[k]||k}))));
 const body=document.querySelector('#report-body');body.replaceChildren();
 if(!rows.length)body.append(el('tr',{},[el('td',{text:'Nenhum registro para os filtros selecionados.',class:'empty'})]));
 else rows.forEach(r=>body.append(el('tr',{},columns.map(k=>el('td',{text:displayValue(k,r[k])})))));
 let labels,values;
 if(grouped){labels=rows.map(r=>optionLabel(title.includes('equipe')?'equipe':'',r.grupo));values=rows.map(r=>r.quantidade);}
 else{const key=title.startsWith('Vencimentos')?'situacao':'status';const counts={};rows.forEach(r=>counts[r[key]]=(counts[r[key]]||0)+1);labels=Object.keys(counts).map(value=>key==='situacao'?expiryPresentation(value)[0]:value);values=Object.values(counts);}
 const total=values.reduce((sum,value)=>sum+value,0),palette=['#00c6f0','#50cf01','#ae5dff','#ffbf00','#f43ead'];
 const categoryColors={'Concluída':'#50cf01','Pendente':dangerColor,'Em andamento':'#ffbf00','Vencidos':dangerColor,'Vencem hoje':'#ffbf00','Vencido':'#111820','Urgente':dangerColor,'Aten\u00e7\u00e3o':'#ffbf00','Dentro do prazo':'#50cf01','Ativo':'#50cf01','Revogado':dangerColor};
 const period=[activeFilters.inicio,activeFilters.fim].filter(Boolean).map(value=>displayValue('data',value)).join(' a ');
 document.querySelector('#report-context').textContent=DashboardPreferences.formatNumber(total)+' registros representados · '+(period?'Período selecionado: '+period:'Sem restrição de período');
 document.querySelector('#report-record-count').textContent=rows.length+' registros na tabela';
 chartSpecs.report={key:'report',title,premiumBars:true,categoryPercent:true,data:[{type:'bar',name:title.startsWith('Acessos')?'Quantidade de acessos':'Quantidade de registros',x:labels,y:values,marker:{color:labels.map((label,index)=>categoryColors[label]||palette[index%palette.length])}}]};drawChart(document.querySelector('#chart-report'),chartSpecs.report);observeCharts();
}
