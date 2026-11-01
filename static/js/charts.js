const chartConfig={displayModeBar:false,scrollZoom:false,doubleClick:false,displaylogo:false,responsive:true};
let chartSpecs={};
const chartState=new WeakMap();
function chartDimensions(node){const rect=node.getBoundingClientRect();return {width:Math.floor(node.clientWidth||rect.width),height:Math.floor(node.clientHeight||rect.height)};}
function chartError(error){console.error('Falha no gráfico:',error);toast('Não foi possível atualizar um gráfico. Tente Atualizar.',true);}
async function drawChart(node,spec,large=false){
 if(!node||!spec)return;
 if(!window.Plotly){node.textContent='Biblioteca de gráficos não encontrada. Consulte o README.';return;}
 let state=chartState.get(node);
 if(!state){state={spec,large,busy:false,disposed:false};chartState.set(node,state);chartResize.observe(node);}
 state.spec=spec;state.large=large;state.dirty=true;
 if(state.busy)return;
 state.busy=true;
 try{
  while(state.dirty&&!state.disposed&&node.isConnected){
   state.dirty=false;
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
   for(const trace of traces){if(trace.type==='pie'){trace.hovertemplate='%{label}<br><b>%{value}</b> ? %{percent}<extra></extra>';trace.textinfo='none';}else{trace.hovertemplate='<b>%{y}</b><extra>%{fullData.name}</extra>';}}
   const layout={autosize:true,width,height,dragmode:false,paper_bgcolor:'transparent',plot_bgcolor:'transparent',font:{family:'Segoe UI, sans-serif',size:(state.large?14:12)*scale,color:color('--chart-text')||'#64748B'},margin:pie?{t:8,b:62,l:12,r:12}:{t:34,b:40,l:40,r:12},barmode:'group',bargap:.4,hovermode:pie?'closest':'x unified',showlegend:true,legend:{orientation:'h',x:pie?.5:0,xanchor:pie?'center':'left',y:pie?-.05:1.02,yanchor:pie?'top':'bottom',font:{size:11*scale},itemclick:false,itemdoubleclick:false},xaxis:{showspikes:true,spikedash:'solid',spikethickness:1,spikecolor:color('--chart-text'),spikemode:'across',fixedrange:true,showgrid:false,zeroline:false,tickfont:{size:9*scale},automargin:true},yaxis:{fixedrange:true,gridcolor:color('--chart-grid')||'#eef2f6',zeroline:false,rangemode:'tozero',automargin:true},hoverlabel:{bgcolor:color('--chart-tooltip')||'white',bordercolor:color('--chart-grid')||'#e8edf3',font:{size:14*scale,family:'Segoe UI, sans-serif',color:color('--chart-tooltip-text')||'#12395B'}}};
   await Plotly.react(node,traces,layout,chartConfig);
  }
 }catch(error){if(!state.disposed)chartError(error);}
 finally{state.busy=false;if(state.disposed&&window.Plotly)Plotly.purge(node);}
}
function releaseChart(node){const state=chartState.get(node);if(state)state.disposed=true;chartResize.unobserve(node);chartState.delete(node);if(window.Plotly)Plotly.purge(node);}
document.addEventListener('click',event=>{const card=event.target.closest('[data-chart]');if(card)expandChart(card.dataset.chart);});
document.addEventListener('keydown',event=>{if(['Enter',' '].includes(event.key)&&event.target.matches('[data-chart]')){event.preventDefault();expandChart(event.target.dataset.chart);}});
function expandChart(key){const spec=chartSpecs[key];if(!spec)return;const plot=el('div',{class:'plot'});openModal(spec.title,plot,true);requestAnimationFrame(()=>{if(plot.isConnected&&modal.open)drawChart(plot,spec,true);});}
const chartResize=new ResizeObserver(entries=>{
 for(const {target} of entries){
  const state=chartState.get(target);if(!state||state.disposed||!target.isConnected)continue;
  const size=chartDimensions(target);if(size.width<1||size.height<1)continue;
  // Medidas do contêiner, independentes do SVG gerado pelo Plotly.
  if(target.layout?.width!==size.width||target.layout?.height!==size.height)drawChart(target,state.spec,state.large);
 }
});
function observeCharts(){document.querySelectorAll('.plot').forEach(p=>{if(chartState.has(p))chartResize.observe(p);});}
