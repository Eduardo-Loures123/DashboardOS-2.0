/* Presentation only: every total is derived from the displayed, filtered series. */
const chartSeriesVisibility=new Map();
const accessTeamPalette=['#50cf01','#00c6f0','#ffbf00','#ae5dff',getComputedStyle(document.documentElement).getPropertyValue('--dos-red').trim()];
function compactMetric(label,value,icon,color,detail=''){
 return el('article',{class:'premium-metric',style:'--metric-color:'+color},[
  el('span',{class:'metric-icon','aria-hidden':'true'},[iconSvg(icon)]),
  el('div',{},[el('span',{class:'metric-label',text:label}),el('strong',{text:String(value)}),...(detail?[el('small',{text:detail})]:[])])]);
}
function renderOrderTeamMetrics(target,spec){
 if(!target)return;const counts=spec.data.map(trace=>(trace.y||[]).reduce((sum,value)=>sum+value,0)),total=counts.reduce((a,b)=>a+b,0);
 const labels={'Concluída':'Concluídas','Pendente':'Pendentes','Em andamento':'Em andamento'},icons={'Concluída':'check','Pendente':'warning','Em andamento':'vencimentos'};
 target.replaceChildren(compactMetric('Total de OS',DashboardPreferences.formatNumber(total),'equipes','#00cfff','Equipes representadas no gráfico'));
 spec.data.forEach((trace,index)=>target.append(compactMetric(labels[trace.name]||trace.name,DashboardPreferences.formatNumber(counts[index]),icons[trace.name]||'relatorios',orderStatusPalette[trace.name]||'#00cfff',(total?counts[index]/total*100:0).toLocaleString('pt-BR',{maximumFractionDigits:1})+'% do total')));
}
function renderOrderTeamLegend(target,spec){
 if(!target)return;target.replaceChildren();const hidden=chartSeriesVisibility.get('teams')||new Set();
 for(const trace of spec.data){const b=el('button',{type:'button',class:'chart-legend-button','aria-pressed':String(!hidden.has(trace.name)),style:'--series-color:'+orderStatusPalette[trace.name]},[el('i',{'aria-hidden':'true'}),el('span',{text:({'Concluída':'Concluídas','Pendente':'Pendentes'})[trace.name]||trace.name})]);
  b.onclick=()=>{hidden.has(trace.name)?hidden.delete(trace.name):hidden.add(trace.name);chartSeriesVisibility.set('teams',hidden);document.querySelectorAll('.premium-legend').forEach(legend=>renderOrderTeamLegend(legend,spec));document.querySelectorAll('.plot').forEach(node=>{const current=chartState.get(node);if(current?.spec.key==='teams')drawChart(node,current.spec,current.large);});};target.append(b);
 }
}
function accessQuery(team){
 const params=new URLSearchParams();for(const [key,value] of Object.entries(activeFilters))if(['equipe','q','funcionario','sistema','situacao'].includes(key)&&value)params.set(key,value);
 if(team)params.set('equipe',team);return '/acessos'+(params.size?'?'+params:'');
}
function renderAccessAnalytics(){
 const target=document.querySelector('#access-teams');if(!target)return;
 target.querySelectorAll('.plot').forEach(releaseChart);target.replaceChildren();
 const overview=state.overview||{},all=overview.access_teams||[],rows=all.slice(0,5),total=rows.reduce((sum,row)=>sum+row.value,0),globalTotal=overview.access_total??all.reduce((sum,row)=>sum+row.value,0),max=Math.max(1,...rows.map(row=>row.value));
 const plot=el('div',{class:'plot access-donut'}),center=el('div',{class:'donut-center access-center'},[iconSvg('equipes'),el('strong',{text:DashboardPreferences.formatNumber(total)}),el('small',{text:'Acessos · Top '+rows.length})]);
 const left=el('div',{class:'access-donut-wrap'},[plot,center]),right=el('section',{class:'access-ranking','aria-label':'Ranking das equipes por acessos'},[el('h3',{text:'Acessos por equipe (Top '+rows.length+')'})]),buttons=[];
 const link=document.querySelector('#access-details');link.href=accessQuery();let selected=null;
 const highlight=index=>buttons.forEach((button,i)=>button.classList.toggle('is-hovered',i===index));
 const choose=index=>{selected=selected===index?null:index;buttons.forEach((button,i)=>button.setAttribute('aria-pressed',String(i===selected)));link.href=accessQuery(selected===null?null:rows[selected].code);emphasizePieSlice(plot,selected);};
 rows.forEach((row,index)=>{const percent=total?row.value/total*100:0,color=accessTeamPalette[index],button=el('button',{type:'button',class:'access-ranking-row','aria-pressed':'false','aria-label':row.name+': '+row.value+' acessos, '+percent.toLocaleString('pt-BR',{maximumFractionDigits:1})+'% do Top '+rows.length,style:'--team-color:'+color},[
  el('span',{class:'ranking-name'},[el('i',{'aria-hidden':'true'}),el('span',{text:row.name})]),
  el('span',{class:'ranking-track','aria-hidden':'true'},[el('span',{style:'width:'+row.value/max*100+'%'})]),el('b',{text:DashboardPreferences.formatNumber(row.value)}),el('span',{class:'ranking-percent',text:percent.toLocaleString('pt-BR',{maximumFractionDigits:1})+'%'})]);
  button.onpointerenter=button.onfocus=()=>{emphasizePieSlice(plot,index);highlight(index);};button.onpointerleave=button.onblur=()=>{emphasizePieSlice(plot,selected);highlight(selected);};button.onclick=()=>choose(index);buttons.push(button);right.append(button);
 });
 if(!rows.length)right.append(el('p',{class:'muted',text:'Nenhuma equipe encontrada nos filtros atuais.'}));
 target.append(left,right);
 if(activeFilters.inicio||activeFilters.fim)target.append(el('p',{class:'access-scope-note',text:'O intervalo de datas do dashboard filtra as OS. Este painel representa os acessos da seleção de equipes.'}));
 const period=overview.access_period||{},dateText=value=>value?new Date(value+'T12:00:00').toLocaleDateString('pt-BR'):'—';
 const periodText=period.start?(period.start===period.end?dateText(period.start):dateText(period.start)+' – '+dateText(period.end)):'Sem registros';
 document.querySelector('#access-summary')?.replaceChildren(
  compactMetric('Total de equipes',DashboardPreferences.formatNumber(all.length),'equipes','#00cfff',rows.length+' representadas no Top 5'),
  compactMetric('Acessos totais',DashboardPreferences.formatNumber(globalTotal),'acessos','#00cfff','Todas as equipes da seleção'),
  compactMetric('Participação Top 5',(globalTotal?total/globalTotal*100:0).toLocaleString('pt-BR',{maximumFractionDigits:1})+'%','relatorios','#50cf01','Sem histórico comparável para variação'),
  compactMetric('Período de concessão',periodText,'calendar','#00cfff','Datas reais dos acessos da seleção'));
 drawChart(plot,{title:'Acessos por equipe · Top '+rows.length,externalLegend:true,premiumPie:true,onHighlight:highlight,onSelect:(_,index)=>choose(index),data:[{type:'pie',hole:.76,sort:false,labels:rows.map(row=>row.name),values:rows.map(row=>row.value),marker:{colors:accessTeamPalette.slice(0,rows.length)},textinfo:'none'}]});
}
function expandTeamOrders(spec){
 const body=el('section',{class:'expanded-team-orders'}),legend=el('div',{class:'premium-legend'}),scroll=el('div',{class:'chart-scroll',tabindex:'0','aria-label':'Equipes representadas no gráfico'}),plot=el('div',{class:'plot'}),metrics=el('div',{class:'premium-metrics'});
 scroll.append(plot);body.append(el('p',{class:'chart-description',text:'Distribuição e status das ordens por equipe. Totais dos filtros ativos.'}),legend,scroll,metrics);renderOrderTeamLegend(legend,spec);renderOrderTeamMetrics(metrics,spec);
 openModal(spec.title,body,true);modal.classList.add('premium-chart-modal');requestAnimationFrame(()=>{if(plot.isConnected&&modal.open)drawChart(plot,spec,true);});
}
