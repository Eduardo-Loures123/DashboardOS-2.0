const chartConfig={displayModeBar:false,scrollZoom:false,doubleClick:false,displaylogo:false,responsive:true};
let chartSpecs={};
const dangerColor=getComputedStyle(document.documentElement).getPropertyValue('--dos-red').trim()||'#ff3030';
const orderStatusPalette={'Concluída':'#50cf01','Pendente':dangerColor,'Em andamento':'#ffbf00'};
const chartState=new WeakMap();
let chartIdentity=0;
function chartDimensions(node){const rect=node.getBoundingClientRect();return {width:Math.floor(node.clientWidth||rect.width),height:Math.floor(node.clientHeight||rect.height)};}
function chartError(error){console.error('Falha no gráfico:',error);toast('Não foi possível atualizar um gráfico. Tente Atualizar.',true);}
// Keep real values intact; padding and tick selection belong to the axis.
function lineAxisLayout(traces,width,scale){
 const lines=traces.filter(t=>t.type==='scatter');if(!lines.length)return null;
 const values=[...new Set(lines.flatMap(t=>t.x||[]))];if(!values.length)return null;
 const monthly=values.every(v=>typeof v==='string'&&/^\d{4}-\d{2}(?:-\d{2})?$/.test(v));
 const numeric=values.every(v=>typeof v==='number'&&Number.isFinite(v));
 let sorted=monthly?values.sort((a,b)=>Date.parse(a)-Date.parse(b)):numeric?values.sort((a,b)=>a-b):values;
 const positions=sorted.map((v,i)=>monthly?Date.parse(v):numeric?v:i);
 const first=positions[0],last=positions.at(-1),span=last-first;
 const padding=span?span*.08:monthly?15*86400000:numeric?Math.max(Math.abs(first)*.08,1):.5;
 const capacity=Math.max(2,Math.floor((width-90)/(62*scale)));
 const step=Math.max(1,Math.ceil((sorted.length-1)/(capacity-1)));
 const ticks=sorted.filter((_,i)=>i===0||i===sorted.length-1||i%step===0&&i<sorted.length-1-step/2);
 const sameYear=monthly&&new Set(sorted.map(v=>v.slice(0,4))).size===1;
 const formatter=new Intl.DateTimeFormat('pt-BR',{month:'short',...(sameYear?{}:{year:'numeric'}),timeZone:'UTC'});
 return {type:monthly?'date':numeric?'linear':'category',range:monthly?[new Date(first-padding).toISOString(),new Date(last+padding).toISOString()]:[first-padding,last+padding],autorange:false,
  ...(monthly||numeric?{}:{categoryorder:'array',categoryarray:sorted}),
  tickmode:'array',tickvals:ticks,ticktext:ticks.map(v=>monthly?formatter.format(new Date(v)):String(v)),tickangle:0,ticklabelstandoff:12,automargin:true};
}
function lineValueAxis(traces){
 const values=traces.filter(trace=>trace.type==='scatter').flatMap(trace=>trace.y||[]).filter(Number.isFinite);
 if(!values.length)return null;
 const low=Math.min(0,...values),high=Math.max(0,...values),span=high-low||1;
 // Marker size participates in Plotly autorange. Reserve hover-marker room at
 // draw time, then keep this data-derived domain unchanged during restyle.
 return {autorange:false,range:[low<0?low-span*.1:0,high>0?high+span*.1:span*.1]};
}
async function drawChart(node,spec,large=false){
 if(!node||!spec)return;
 if(!window.Plotly){node.textContent='Biblioteca de gráficos não encontrada. Consulte o README.';return;}
 let state=chartState.get(node);
 if(!state){state={spec,large,busy:false,disposed:false,id:++chartIdentity};chartState.set(node,state);chartResize.observe(node);}
 state.spec=spec;state.large=large;state.dirty=true;
 if(state.busy)return;
 state.busy=true;
 try{
  while(state.dirty&&!state.disposed&&node.isConnected){
   state.dirty=false;state.cleanup?.();state.cleanup=null;
   const {width,height}=chartDimensions(node);if(width<1||height<1)break;
   const pie=state.spec.data[0]?.type==='pie';
   const styles=getComputedStyle(document.documentElement),scale=window.DashboardPreferences?.scale()||1.1;
   const color=name=>styles.getPropertyValue(name).trim();
   const traces=structuredClone(state.spec.data);
   if(document.documentElement.dataset.theme==='dark')for(const trace of traces){
    if(trace.marker?.color==='#12395B')trace.marker.color=color('--chart-navy')||'#82accf';
    if(trace.marker?.colors)trace.marker.colors=trace.marker.colors.map(c=>c==='#12395B'?(color('--chart-navy')||'#82accf'):c==='#DCE5EE'?'#4b647b':c);
    if(trace.line?.color==='#12395B')trace.line.color=color('--chart-navy')||'#82accf';
   }
   traces.forEach(trace=>{
    if(trace.type==='scatter'&&orderStatusPalette[trace.name])trace.line={...trace.line,color:orderStatusPalette[trace.name]};
    if(!trace.name||/^trace\s*\d+$/i.test(trace.name))trace.name=/acessos/i.test(state.spec.title)?'Quantidade de acessos':'Quantidade de registros';
    trace.hoverinfo='none';delete trace.hovertemplate;
    if(trace.type==='pie'){trace.textinfo='none';if(trace.labels?.every(label=>orderStatusPalette[label]))trace.marker={...trace.marker,colors:trace.labels.map(label=>orderStatusPalette[label])};}
    if(trace.type==='bar'&&orderStatusPalette[trace.name])trace.marker={...trace.marker,color:orderStatusPalette[trace.name]};
    if(state.spec.premiumBars){trace.text=(trace.y||[]).map(String);trace.textposition='outside';trace.cliponaxis=false;trace.textfont={size:12,color:color('--dos-text')};trace.visible=chartSeriesVisibility.get('teams')?.has(trace.name)?'legendonly':true;}
    if(trace.type==='scatter'){
     trace.mode='lines+markers';trace.cliponaxis=false;trace.marker={...trace.marker,size:8,color:trace.line?.color,line:{width:2,color:color('--surface')}};
     trace.line={...trace.line,width:3};
     if(trace.fill){trace.fillcolor=chartAlpha(trace.line?.color,.2);trace.fillgradient={type:'vertical',colorscale:[[0,chartAlpha(trace.line?.color,.01)],[1,chartAlpha(trace.line?.color,.45)]]};}
    }
   });
   const layout={autosize:true,width,height,dragmode:false,paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{family:'Segoe UI, sans-serif',size:(state.large?14:12)*scale,color:color('--chart-text')||'#64748B'},margin:pie?{t:12,b:state.large?(width<600?112:64):12,l:12,r:12}:{t:55,b:52,l:52,r:20},barmode:'group',bargap:.4,hovermode:'closest',showlegend:pie?state.large:traces.length>1,legend:{orientation:'h',x:pie?.5:0,xanchor:pie?'center':'left',y:pie?-.05:1.02,yanchor:pie?'top':'bottom',font:{size:11*scale},itemclick:false,itemdoubleclick:false},xaxis:{showspikes:false,fixedrange:true,showgrid:false,zeroline:false,tickfont:{size:11*scale},automargin:true},yaxis:{showspikes:false,fixedrange:true,gridcolor:color('--chart-grid')||'#eef2f6',zeroline:false,rangemode:'tozero',automargin:true},hoverlabel:{bgcolor:color('--chart-tooltip')||'white',bordercolor:color('--chart-grid')||'#e8edf3',font:{size:14*scale,family:'Segoe UI, sans-serif',color:color('--chart-tooltip-text')||'#12395B'}}};
   const lineAxis=lineAxisLayout(traces,width,scale);
   if(lineAxis){Object.assign(layout.xaxis,lineAxis);Object.assign(layout.yaxis,lineValueAxis(traces));layout.yaxis.ticklabelstandoff=10;layout.margin={t:32,b:48,l:50,r:22};}
   if(lineAxis){layout.hovermode='x';layout.hoverdistance=-1;if(traces.length>1)layout.legend.itemclick='toggle';}
   if(state.spec.premiumBars){layout.bargap=.22;layout.bargroupgap=.05;layout.margin={t:38,b:42,l:45,r:16};layout.yaxis.range=[0,Math.max(1,...traces.flatMap(t=>t.y||[]))*1.19];layout.yaxis.autorange=false;}
   if(state.spec.externalLegend){layout.showlegend=false;}
   if(pie)layout.margin={t:24,b:24,l:24,r:24};
   await Plotly.react(node,traces,layout,chartConfig);
   if(!state.disposed&&node.isConnected){state.lastGood={traces:structuredClone(traces),layout:structuredClone(layout),spec:state.spec};delete node.dataset.chartError;finishChartArtwork(node,state);bindChartInteraction(node,state);}
  }
 }catch(error){if(!state.disposed){node.dataset.chartError='true';chartError(error);if(state.lastGood&&node.isConnected){try{await Plotly.react(node,state.lastGood.traces,state.lastGood.layout,chartConfig);finishChartArtwork(node,state);bindChartInteraction(node,state);}catch{console.error('Falha ao restaurar o desenho anterior do gr?fico.');}}}}
 finally{state.busy=false;if(state.disposed&&window.Plotly)Plotly.purge(node);}
}
function releaseChart(node){const state=chartState.get(node);if(state){state.disposed=true;state.cleanup?.();}chartResize.unobserve(node);chartState.delete(node);if(window.Plotly)Plotly.purge(node);}
document.addEventListener('click',event=>{const card=event.target.closest('[data-chart]');if(card)expandChart(card.dataset.chart);});
document.addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)&&event.target.matches('[data-chart]')){event.preventDefault();expandChart(event.target.dataset.chart);}});
function expandChart(key){const spec=chartSpecs[key];if(!spec)return;if(key==='teams'&&spec.premiumBars){expandTeamOrders(spec);return;}if(key==='donut'&&spec.data[0]?.type==='pie'){expandStatusAnalysis(spec);return;}const plot=el('div',{class:'plot'});openModal(spec.title,plot,true);requestAnimationFrame(()=>{if(plot.isConnected&&modal.open)drawChart(plot,spec,true);});}
function orderStatusQuery(status){
 const allowed=['equipe','prioridade','inicio','fim','q'],params=new URLSearchParams();
 for(const [key,value] of Object.entries(typeof activeFilters==='undefined'?{}:activeFilters))if(allowed.includes(key)&&value)params.set(key,value);
 if(status)params.set('status',status);
 return '/ordens-servico'+(params.size?'?'+params:'');
}
function expandStatusAnalysis(spec){
 const trace=spec.data[0],total=trace.values.reduce((sum,value)=>sum+value,0),plot=el('div',{class:'plot'});
 const left=el('div',{class:'donut-analysis-chart'},[plot,el('div',{class:'donut-center'},[el('strong',{text:DashboardPreferences.formatNumber(total)}),el('small',{text:'Total de OS'})])]);
 const right=el('section',{class:'analysis-breakdown','aria-label':'Distribuição das ordens por status'}),buttons=[];
 right.append(el('h2',{text:'Distribuição por status'}),el('p',{class:'analysis-context',text:'Selecione um status para consultar as ordens correspondentes. Os filtros atuais serão mantidos.'}));
 let selected=typeof activeFilters==='undefined'?null:activeFilters.status||null;
 const link=el('a',{class:'button primary',text:'Consultar ordens de serviço',href:orderStatusQuery(selected)});
 const choose=status=>{selected=selected===status?null:status;buttons.forEach(([label,button])=>button.setAttribute('aria-pressed',String(label===selected)));link.href=orderStatusQuery(selected);link.textContent=selected?'Consultar OS · '+selected:'Consultar todas as OS';};
 trace.labels.forEach((label,index)=>{
  const value=trace.values[index],percent=total?value/total*100:0,color=orderStatusPalette[label]||trace.marker?.colors?.[index]||'#007bff';
  const button=el('button',{type:'button',class:'analysis-status','data-status':label,'aria-pressed':String(label===selected),style:'--status-color:'+color},[
   el('span',{class:'analysis-status-heading'},[el('span',{text:label}),el('strong',{text:DashboardPreferences.formatNumber(value)})]),
   el('small',{text:percent.toLocaleString('pt-BR',{maximumFractionDigits:1})+'% do total'}),
   el('span',{class:'bar-track','aria-hidden':'true'},[el('span',{class:'bar-fill',style:'width:'+percent+'%'})])]);
  button.onclick=()=>choose(label);buttons.push([label,button]);right.append(button);
 });
 right.append(el('div',{class:'analysis-actions'},[link]));
 const filters=Object.entries(typeof activeFilters==='undefined'?{}:activeFilters).filter(([,value])=>value);
 if(filters.length)right.append(el('p',{class:'analysis-context',text:'Filtros: '+filters.map(([key,value])=>(typeof filterLabel==='function'?filterLabel(key):key)+': '+value).join(' · ')}));
 const updated=document.querySelector('#updated')?.textContent;if(updated?.startsWith('Atualizado'))right.append(el('p',{class:'analysis-updated',text:updated}));
 openModal(spec.title,el('section',{class:'donut-analytics'},[left,right]),true);modal.classList.add('status-analytics');
 const analyticSpec={...spec,externalLegend:true,onSelect:choose};
 requestAnimationFrame(()=>{if(plot.isConnected&&modal.open)drawChart(plot,analyticSpec,true);});
}
const chartResize=new ResizeObserver(entries=>{
 if(document.documentElement.dataset.sidebarTransition)return;
 for(const {target} of entries){
  const state=chartState.get(target);if(!state||state.disposed||!target.isConnected)continue;
  const size=chartDimensions(target);if(size.width<1||size.height<1)continue;
  // Medidas do contêiner, independentes do SVG gerado pelo Plotly.
  if(target.layout?.width!==size.width||target.layout?.height!==size.height)drawChart(target,state.spec,state.large);
 }
});
window.addEventListener('dashboard:sidebar-settled',()=>document.querySelectorAll('.plot').forEach(node=>{const current=chartState.get(node);if(!current)return;const size=chartDimensions(node);if(size.width&&size.height&&(node.layout?.width!==size.width||node.layout?.height!==size.height))drawChart(node,current.spec,current.large);}));
function observeCharts(){document.querySelectorAll('.plot').forEach(p=>{if(chartState.has(p))chartResize.observe(p);});}

// A floating HTML layer shares one presentation in cards and top-layer dialogs.
function chartAlpha(color,alpha){
 const match=/^#([a-f0-9]{6})$/i.exec(color||'');
 return match?`rgba(${parseInt(match[1].slice(0,2),16)},${parseInt(match[1].slice(2,4),16)},${parseInt(match[1].slice(4,6),16)},${alpha})`:color;
}
function finishChartArtwork(node,state){
 const ns='http://www.w3.org/2000/svg';
 const scatter=(node.data||[]).filter(trace=>trace.type==='scatter');node.querySelectorAll('.scatterlayer .trace').forEach((group,i)=>{const color=scatter[i]?.line?.color||'#00cfff';group.querySelectorAll('.js-line').forEach(path=>path.style.color=color);group.querySelectorAll('.point').forEach(path=>path.style.setProperty('--point-color',color));});
 if(state.spec.premiumBars){const svg=node.querySelector('.main-svg');if(!svg)return;let defs=svg.querySelector('defs');if(!defs){defs=document.createElementNS(ns,'defs');svg.prepend(defs);}defs.querySelectorAll('[data-premium-bar]').forEach(n=>n.remove());const traces=(node.data||[]).filter(t=>t.type==='bar'&&t.visible!=='legendonly'&&t.visible!==false);
  node.querySelectorAll('.barlayer .trace').forEach((group,i)=>{
   group.querySelectorAll('.point path').forEach((path,j)=>{const source=traces[i]?.marker?.color,color=(Array.isArray(source)?source[j]:source)||'#00cfff',id='dos-bar-'+state.id+'-'+i+'-'+j,gradient=document.createElementNS(ns,'linearGradient');gradient.id=id;gradient.setAttribute('data-premium-bar','');gradient.setAttribute('x1','0');gradient.setAttribute('y1','0');gradient.setAttribute('x2','0');gradient.setAttribute('y2','1');for(const [offset,opacity] of [['0','1'],['.22','.94'],['1','.48']]){const stop=document.createElementNS(ns,'stop');stop.setAttribute('offset',offset);stop.setAttribute('stop-color',color);stop.setAttribute('stop-opacity',opacity);gradient.append(stop);}defs.append(gradient);
    if(typeof path.getBBox==='function'){const b=path.getBBox(),r=Math.min(7,b.width*.25,b.height);if(b.height>0&&b.width>0)path.setAttribute('d',`M${b.x},${b.y+b.height}V${b.y+r}Q${b.x},${b.y} ${b.x+r},${b.y}H${b.x+b.width-r}Q${b.x+b.width},${b.y} ${b.x+b.width},${b.y+r}V${b.y+b.height}Z`);}path.style.fill='url(#'+id+')';path.style.stroke=color;path.style.setProperty('--bar-color',color);
   });
   group.querySelectorAll('text.bartext').forEach(text=>{if(typeof text.getBBox!=='function')return;text.parentNode.querySelector('.bar-value-chip')?.remove();const b=text.getBBox(),rect=document.createElementNS(ns,'rect');rect.setAttribute('class','bar-value-chip');rect.setAttribute('x',b.x-5);rect.setAttribute('y',b.y-2);rect.setAttribute('width',b.width+10);rect.setAttribute('height',b.height+4);rect.setAttribute('rx','9');if(text.hasAttribute('transform'))rect.setAttribute('transform',text.getAttribute('transform'));text.before(rect);});
  });
 }
 const paths=[...node.querySelectorAll('.pielayer .slice path.surface')];
 const pie=(node.data||[]).find(trace=>trace.type==='pie');paths.forEach((path,index)=>path.style.setProperty('--slice-color',pie?.marker?.colors?.[index]||'#00cfff'));
 state.pieDirections=paths.map(path=>{const p=path.getBoundingClientRect(),box=node.getBoundingClientRect(),dx=p.left+p.width/2-box.left-box.width/2,dy=p.top+p.height/2-box.top-box.height/2,length=Math.hypot(dx,dy)||1;return [dx/length,dy/length];});
}
function emphasizePieSlice(node,index){
 const current=chartState.get(node),paths=[...node.querySelectorAll('.pielayer .slice path.surface')];
 paths.forEach((path,i)=>{const direction=current?.pieDirections?.[i]||[0,0],distance=window.DashboardPreferences?.reduced()?0:7;path.style.transform=i===index?'translate('+direction[0]*distance+'px,'+direction[1]*distance+'px)':'';path.classList.toggle('is-slice-highlighted',i===index);});
}
// Invisible, stationary copies own hit testing; CSS transforms affect artwork only.
// Radial tolerance is clamped to the original ring, retaining angular boundaries.
function stationaryPieHit(node,base){
 const paths=[...node.querySelectorAll('.pielayer .slice path.surface')];
 if(!paths.length||typeof paths[0].isPointInFill!=='function')return null;
 const copies=paths.map((path,index)=>{const copy=document.createElementNS('http://www.w3.org/2000/svg','path');copy.setAttribute('d',path.getAttribute('d'));copy.setAttribute('class','pie-hit-geometry');copy.style.cssText='visibility:hidden;pointer-events:none;transform:none;filter:none';path.parentNode.append(copy);const datum=path.parentNode.__data__,j=base[0].labels.indexOf(datum?.label);return {copy,index:j>=0?j:index};});
 const boxes=copies.map(({copy})=>copy.getBBox()),left=Math.min(...boxes.map(b=>b.x)),right=Math.max(...boxes.map(b=>b.x+b.width)),top=Math.min(...boxes.map(b=>b.y)),bottom=Math.max(...boxes.map(b=>b.y+b.height));
 const cx=(left+right)/2,cy=(top+bottom)/2,outer=Math.max(right-left,bottom-top)/2,inner=outer*(base[0].hole||0);
 return {hit(event){const matrix=copies[0].copy.getScreenCTM();if(!matrix)return null;const p=new DOMPoint(event.clientX,event.clientY).matrixTransform(matrix.inverse()),dx=p.x-cx,dy=p.y-cy,r=Math.hypot(dx,dy);if(r<Math.max(0,inner-8)||r>outer+9||!r)return null;const radius=Math.max(inner+.5,Math.min(outer-.5,r)),q=new DOMPoint(cx+dx/r*radius,cy+dy/r*radius);return copies.find(({copy})=>copy.isPointInFill(q))?.index??null;},remove(){copies.forEach(({copy})=>copy.remove());}};
}
function chartXKey(value){return /^\d{4}-\d{2}/.test(String(value))?Date.parse(value):String(value);}
function bindChartInteraction(node,state){
 state.cleanup?.();if(typeof node.on!=='function')return;
 const tip=el('div',{class:'chart-tooltip',role:'tooltip'});tip.hidden=true;
 (node.closest('dialog')||document.body).append(tip);
 const base=structuredClone(node.data),shared=base.some(t=>t.type==='scatter'),pieHit=base[0]?.type==='pie'?stationaryPieHit(node,base):null;let active='',lastEvent,restyleFrame;
 const place=event=>{
  if(event)lastEvent=event;if(tip.hidden)return;
  const bounds=node.getBoundingClientRect(),p=lastEvent||{};
  const x=p.clientX??bounds.left+bounds.width/2,y=p.clientY??bounds.top+bounds.height/2;
  const r=tip.getBoundingClientRect(),gap=18,pad=12;
  let left=x+gap,top=shared?y-r.height/2:y+gap;
  if(!shared&&left+r.width>innerWidth-pad)left=x-r.width-gap;
  if(!shared&&top+r.height>innerHeight-pad)top=y-r.height-gap;
  if(shared){
   const card=node.closest('.chart-card,dialog')||node,box=card.getBoundingClientRect();
   const minX=Math.max(pad,box.left+8),maxX=Math.min(innerWidth-pad,box.right-8),minY=Math.max(pad,box.top+8),maxY=Math.min(innerHeight-pad,box.bottom-8);
   tip.style.maxWidth=Math.max(0,maxX-minX)+'px';tip.style.maxHeight=Math.max(0,maxY-minY)+'px';
   left=Math.max(minX,Math.min(left,maxX-r.width));top=Math.max(minY,Math.min(top,maxY-r.height));
  }
  tip.style.left=Math.max(pad,Math.min(left,innerWidth-r.width-pad))+'px';
  tip.style.top=Math.max(pad,Math.min(top,innerHeight-r.height-pad))+'px';
 };
 const update=point=>{
  const groups=node.querySelectorAll('.scatterlayer .trace');let visibleLine=0,visibleBar=0;
  base.forEach((trace,i)=>{
   if(trace.type==='pie'){emphasizePieSlice(node,point?.pointNumber??null);state.spec.onHighlight?.(point?.pointNumber??null);return;}
   if(trace.visible==='legendonly'||trace.visible===false)return;
   if(trace.type==='scatter'){
    const group=groups[visibleLine++];group?.style.removeProperty('opacity');
    group?.querySelectorAll('.point').forEach((path,j)=>{path.style.setProperty('--point-color',trace.line?.color||'#00cfff');path.classList.toggle('is-point-highlighted',!!point&&chartXKey(trace.x[j])===chartXKey(point.x));});
   }
   if(trace.type==='bar'){
    const group=node.querySelectorAll('.barlayer .trace')[visibleBar++];group?.querySelectorAll('.point path').forEach((path,j)=>{const same=!!point&&chartXKey(trace.x[j])===chartXKey(point.x);path.classList.toggle('is-bar-highlighted',same&&(!state.spec.individualBars||i===point.curveNumber));});
   }
  });
 };
 const hover=event=>{
  const point=event.points?.[0];if(!point)return;
  const key=shared?'period:'+chartXKey(point.x):point.curveNumber+':'+point.pointNumber;
  if(active===key&&!tip.hidden){place(event.event);return;}
  if(active!==key){active=key;update(point);}
  let title=state.spec.individualBars&&typeof optionLabel==='function'?optionLabel('equipe',String(point.x)):String(point.label??point.x??state.spec.title);
  if(shared&&/^\d{4}-\d{2}/.test(String(point.x)))title=new Date(String(point.x).slice(0,7)+'-01T12:00:00Z').toLocaleDateString('pt-BR',{month:'long',year:'numeric',timeZone:'UTC'});
  tip.replaceChildren(el('strong',{class:'chart-tooltip-title',text:point.data.type==='pie'?state.spec.title:title}));
  const indexes=shared?base.map((_,i)=>i).filter(i=>base[i].type==='scatter'&&base[i].visible!=='legendonly'&&base[i].visible!==false):point.data.type==='bar'&&!state.spec.individualBars?base.map((_,i)=>i):[point.curveNumber];
  indexes.forEach(i=>{
   const trace=base[i],j=trace.type==='bar'||shared?trace.x.findIndex(x=>chartXKey(x)===chartXKey(point.x)):point.pointNumber;
   if(j<0)return;
   const value=trace.type==='pie'?trace.values[j]:trace.y[j];
   const color=trace.marker?.colors?.[j]||trace.line?.color||(Array.isArray(trace.marker?.color)?trace.marker.color[j]:trace.marker?.color)||'#12395B';
   const total=trace.type==='pie'?trace.values.reduce((sum,v)=>sum+v,0):state.spec.categoryPercent?trace.y.reduce((sum,v)=>sum+v,0):0;
   const percent=total?value/total*100:0;
   const row=el('div',{class:'chart-tooltip-row'},[el('i'),el('span',{text:trace.type==='pie'?String(point.label):trace.name}),el('b',{text:DashboardPreferences.formatNumber(value)+(total?' · '+percent.toLocaleString('pt-BR',{maximumFractionDigits:1})+'%':'')})]);
   row.firstChild.style.backgroundColor=color;tip.append(row);
  });
  tip.hidden=false;place(event.event);
 };
 const reset=()=>{tip.hidden=true;if(active){active='';update(null);}};
 // Read rendered SVG geometry once per draw. Detection never adds an input-blocking overlay.
 const regions=state.spec.individualBars?[]:chartBarRegions(node,base);
 const hit=event=>{
  if(!event)return null;const bounds=node.getBoundingClientRect(),x=event.clientX-bounds.left,y=event.clientY-bounds.top;
  return regions.find(r=>x>=r.left&&x<=r.right&&y>=r.top&&y<=r.bottom);
 };
 const groupHover=(region,event)=>hover({event,points:[{curveNumber:0,pointNumber:region.index,x:base[0].x[region.index],y:base[0].y[region.index],data:base[0]}]});
 const piePoint=(index,event)=>({event,points:[{curveNumber:0,pointNumber:index,label:base[0].labels[index],data:base[0]}]});
 const periodTrace=base.find(t=>t.type==='scatter'&&t.visible!=='legendonly'&&t.visible!==false);
 const periodPixels=periodTrace?.x.map(v=>node._fullLayout?.xaxis?.d2p(v))||[];
 const move=event=>{lastEvent=event;if(pieHit){const index=pieHit.hit(event);if(index!==null)hover(piePoint(index,event));else reset();return;}if(shared&&node._fullLayout?._size){const size=node._fullLayout._size,b=node.getBoundingClientRect(),x=event.clientX-b.left-size.l,y=event.clientY-b.top-size.t,trace=periodTrace;if(trace&&x>=0&&x<=size.w&&y>=0&&y<=size.h){const j=trace.x.reduce((best,v,i)=>Math.abs(periodPixels[i]-x)<Math.abs(periodPixels[best]-x)?i:best,0);hover({event,points:[{curveNumber:base.indexOf(trace),pointNumber:j,x:trace.x[j],data:trace}]});}else reset();return;}if(regions.length){const region=hit(event);if(region)groupHover(region,event);else reset();}else place(event);};
 const unhover=()=>{if(shared&&lastEvent&&node._fullLayout?._size){move(lastEvent);return;}const region=hit(lastEvent);if(region)groupHover(region,lastEvent);else reset();};
 const select=event=>{const point=event.points?.[0];if(point&&typeof state.spec.onSelect==='function')state.spec.onSelect(point.label??base[point.curveNumber]?.labels?.[point.pointNumber],point.pointNumber);};
 if(!pieHit&&!(shared&&node._fullLayout?._size)){node.on('plotly_hover',hover);node.on('plotly_unhover',unhover);node.on('plotly_click',select);}
 const pieSelect=event=>{const index=pieHit?.hit(event);if(index!==null&&index!==undefined)state.spec.onSelect?.(base[0].labels[index],index);};
 if(pieHit)node.addEventListener('click',pieSelect);
 const afterRestyle=()=>{reset();cancelAnimationFrame(restyleFrame);restyleFrame=requestAnimationFrame(()=>{if(!state.disposed&&!state.busy&&node.isConnected){finishChartArtwork(node,state);bindChartInteraction(node,state);}});};
 if(shared)node.on('plotly_restyle',afterRestyle);
 node.addEventListener('pointermove',move);node.addEventListener('pointerleave',reset);
 node.addEventListener('pointercancel',reset);window.addEventListener('blur',reset);
 window.addEventListener('scroll',reset,true);window.addEventListener('resize',reset);
 state.cleanup=()=>{cancelAnimationFrame(restyleFrame);pieHit?.remove();node.removeEventListener('click',pieSelect);node.querySelectorAll('.scatterlayer .trace').forEach(group=>group.style.removeProperty('opacity'));tip.remove();node.removeListener?.('plotly_hover',hover);node.removeListener?.('plotly_unhover',unhover);node.removeListener?.('plotly_click',select);node.removeListener?.('plotly_restyle',afterRestyle);node.removeEventListener('pointermove',move);node.removeEventListener('pointerleave',reset);node.removeEventListener('pointercancel',reset);window.removeEventListener('blur',reset);window.removeEventListener('scroll',reset,true);window.removeEventListener('resize',reset);};
}
function chartBarRegions(node,traces){
 if(!traces.length||!traces.every(trace=>trace.type==='bar'&&trace.orientation!=='h'))return [];
 const origin=node.getBoundingClientRect(),groups=new Map();
 node.querySelectorAll('.barlayer .trace').forEach((trace,i)=>trace.querySelectorAll('.point path').forEach((path,j)=>{
  const rect=path.getBoundingClientRect(),category=traces[i]?.x[j];if(category===undefined||!rect.width)return;
  const previous=groups.get(category),box={left:rect.left-origin.left,right:rect.right-origin.left,top:Math.min(rect.top-origin.top,rect.bottom-origin.top-24),bottom:rect.bottom-origin.top+4,index:traces[0].x.indexOf(category)};
  if(previous){previous.left=Math.min(previous.left,box.left);previous.right=Math.max(previous.right,box.right);previous.top=Math.min(previous.top,box.top);previous.bottom=Math.max(previous.bottom,box.bottom);}else groups.set(category,box);
 }));
 const result=[...groups.values()].filter(r=>r.index>=0).sort((a,b)=>a.left-b.left);
 const centers=result.map(r=>(r.left+r.right)/2);
 return result.map((r,i)=>({...r,left:i?(centers[i-1]+centers[i])/2:r.left-(result[1]?((centers[1]-centers[0])-(r.right-r.left))/2:0),right:i<result.length-1?(centers[i]+centers[i+1])/2:r.right+(result[i-1]?((centers[i]-centers[i-1])-(r.right-r.left))/2:0)}));
}
