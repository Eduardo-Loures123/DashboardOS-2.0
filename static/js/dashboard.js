function renderDashboard(){
 const values=state.indicators;
 const primary=['Funcionários','Equipes','Ordens de serviço','Acessos'];const icons=['funcionarios','equipes','ordens-servico','acessos'];
 const target=document.querySelector('#kpis');target.replaceChildren();
 primary.forEach((label,i)=>target.append(el('div',{class:'kpi'},[el('span',{class:'kpi-label',text:label}),el('strong',{text:DashboardPreferences.formatNumber(values[label])}),el('span',{class:'kpi-icon','aria-hidden':'true'},[iconSvg(icons[i])]),el('small',{text:'Base operacional · visão filtrada'})])));
 const secondary=document.querySelector('#secondary-kpis');secondary.replaceChildren();for(const [key,value] of Object.entries(values)){if(!primary.includes(key))secondary.append(el('div',{class:'mini-kpi'},[el('span',{text:key}),el('strong',{text:DashboardPreferences.formatNumber(value),title:String(value)})]));}
 chartSpecs=state.charts;
 for(const [key,spec] of Object.entries(chartSpecs))drawChart(document.querySelector('#chart-'+key),spec);
 const total=values['Ordens de serviço'];document.querySelector('#completion').textContent=(total?Math.round(values['Concluídas']/total*100):0)+'%';
 const list=document.querySelector('#status-list');list.replaceChildren();['Concluídas','Pendentes','Em andamento'].forEach((key,i)=>list.append(el('div',{class:'status-row'},[el('span',{},[el('i',{style:'background:'+['#12395B','#FF9F0A','#DCE5EE'][i]}),document.createTextNode(key)]),el('b',{text:DashboardPreferences.formatNumber(values[key])})])));
 renderCalendar();observeCharts();
}
function renderCalendar(){
 const target=document.querySelector('#calendar'),today=new Date(),year=today.getFullYear(),month=today.getMonth();
 target.replaceChildren(el('h3',{text:today.toLocaleDateString('pt-BR',{month:'long',year:'numeric'})}));
 const grid=el('div',{class:'calendar-grid'});['D','S','T','Q','Q','S','S'].forEach(d=>grid.append(el('span',{class:'weekday',text:d})));
 const offset=new Date(year,month,1).getDay(),days=new Date(year,month+1,0).getDate();
 for(let i=0;i<offset;i++)grid.append(el('span'));
 for(let day=1;day<=days;day++){const iso=year+'-'+String(month+1).padStart(2,'0')+'-'+String(day).padStart(2,'0'),count=state.calendar[iso]||0;grid.append(el('span',{text:day,class:(count?'scheduled ':'')+(day===today.getDate()?'today':''),title:count+' OS com conclusão prevista em '+day+'/'+(month+1)}));}
 target.append(grid,el('small',{text:'■ Previsões de OS · laranja: hoje'}));
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
 else{const key=title.startsWith('Vencimentos')?'situacao':'status';const counts={};rows.forEach(r=>counts[r[key]]=(counts[r[key]]||0)+1);labels=Object.keys(counts);values=Object.values(counts);}
 chartSpecs.report={title,data:[{type:'bar',x:labels,y:values,marker:{color:'#12395B'}}]};drawChart(document.querySelector('#chart-report'),chartSpecs.report);observeCharts();
}
