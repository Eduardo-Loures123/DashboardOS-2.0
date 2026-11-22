const page=document.body.dataset.page;let state={},currentPage=1,pageSize=page==='equipes'?12:10,sortKey='codigo',sortDirection=1,searchTerm='',loadSequence=0,dataReady=false;
let deadlineType='acessos';
const deadlineViews=new Map();
function viewParams(){return page==='vencimentos'&&deadlineType==='os'?{...activeFilters,tipo:'os'}:{...activeFilters};}
async function switchDeadlines(kind){
 if(kind===deadlineType||!['acessos','os'].includes(kind))return;
 deadlineViews.set(deadlineType,{filters:{...activeFilters},search:searchTerm,sortKey,sortDirection,currentPage});
 deadlineType=kind;const saved=deadlineViews.get(kind);
 activeFilters={...(saved?.filters||{})};searchTerm=saved?.search||'';sortKey=saved?.sortKey||'codigo';sortDirection=saved?.sortDirection||1;currentPage=saved?.currentPage||1;
 document.querySelector('#search').value=searchTerm;
 document.querySelectorAll('[data-deadline-type]').forEach(b=>{const active=b.dataset.deadlineType===kind;b.setAttribute('aria-pressed',String(active));});
 setDataReady(false);
 document.querySelector('#table-head').replaceChildren();
 document.querySelector('#table-body').replaceChildren(el('tr',{},[el('td',{class:'empty',text:'Carregando registros…'})]));
 document.querySelector('#expiry-summary').replaceChildren();document.querySelector('#record-count').textContent='';document.querySelector('#page-number').textContent='';
 await loadData();
}
document.querySelectorAll('[data-deadline-type]').forEach(b=>b.addEventListener('click',()=>switchDeadlines(b.dataset.deadlineType)));
searchTerm=new URLSearchParams(location.search).get('q')||'';
if(document.querySelector('#search'))document.querySelector('#search').value=searchTerm;
function canWrite(){return ['admin','superadmin'].includes(document.body.dataset.role);}
function setDataReady(ready){dataReady=ready;for(const id of ['filters-button','export','new','search','page-size','report-download']){const control=document.getElementById(id);if(control){control.disabled=!ready||(id==='new'&&!canWrite());if(id==='new')control.title=canWrite()?'Novo registro':'Disponível apenas para administradores';}}}
setDataReady(false);
DashboardSidebar.attach();
async function api(url,options={}){let response;try{response=await fetch(url,{...options,headers:{'Content-Type':'application/json','X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content,...options.headers}});}catch{throw Error('Não foi possível conectar ao servidor. Verifique se o Flask está em execução.');}let result;try{result=await response.json();}catch{throw Error('O servidor retornou uma resposta inválida (HTTP '+response.status+'). Tente Atualizar.');}if(!response.ok)throw Error(result.error||'Não foi possível concluir a operação.');return result;}
async function loadData(){const sequence=++loadSequence;document.querySelector('main').setAttribute('aria-busy','true');document.querySelector('#refresh').disabled=true;try{const result=await api('/api/data/'+page+'?'+new URLSearchParams(viewParams()));if(sequence!==loadSequence)return;state=result;if(result.user)document.body.dataset.role=result.user.role;document.querySelector('#filter-count').textContent=Object.keys(activeFilters).length||'';
 if(page==='dashboard')renderDashboard();else if(page==='relatorios')renderReports();else{renderTable();document.querySelector('#new').hidden=page==='vencimentos';}
 setDataReady(true);document.querySelector('#updated').textContent='Atualizado às '+new Date().toLocaleTimeString('pt-BR');
 }catch(error){if(sequence!==loadSequence)return;if(page==='vencimentos'&&!dataReady)document.querySelector('#table-body').replaceChildren(el('tr',{},[el('td',{class:'empty',text:'Falha ao carregar. Use Atualizar para tentar novamente.'})]));toast(error.message,true);document.querySelector('#updated').textContent='Falha ao atualizar · tente novamente';}finally{if(sequence===loadSequence){document.querySelector('main').removeAttribute('aria-busy');if(!refreshTask)document.querySelector('#refresh').disabled=false;}}}
let refreshTask=null;
function refreshWithMotion(work){
 if(refreshTask)return refreshTask;
 const button=document.querySelector('#refresh'),started=performance.now();button.disabled=true;button.setAttribute('aria-busy','true');
 refreshTask=(async()=>{try{await work();}finally{button.disabled=true;const elapsed=performance.now()-started,remaining=DashboardPreferences.reduced()?0:650-elapsed%650;if(remaining)await new Promise(resolve=>setTimeout(resolve,remaining));button.removeAttribute('aria-busy');button.disabled=false;refreshTask=null;}})();
 return refreshTask;
}
document.querySelector('#refresh').onclick=()=>refreshWithMotion(loadData);
async function download(){if(!dataReady)return;const params=viewParams();if(searchTerm)params.q=searchTerm;const buttons=[document.querySelector('#export'),document.querySelector('#report-download')].filter(Boolean);buttons.forEach(b=>b.disabled=true);try{const response=await fetch('/api/export/'+page+'?'+new URLSearchParams(params));if(!response.ok){let error;try{error=(await response.json()).error;}catch{}throw Error(error||'Não foi possível exportar o Excel.');}const url=URL.createObjectURL(await response.blob()),link=el('a',{href:url,download:page+'.xlsx'});document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);}catch(error){toast(error.message||'Não foi possível conectar ao servidor.',true);}finally{buttons.forEach(b=>b.disabled=false);}}
document.querySelector('#export').onclick=download;
function displayValue(key,value){if(key==='situacao'&&value)return expiryPresentation(value)[0];if(value===undefined||value===null||value==='')return '—';if(['equipe','funcionario','responsavel','acesso'].includes(key))return optionLabel(key,String(value));if(/^\d{4}-\d{2}-\d{2}$/.test(String(value)))return String(value).split('-').reverse().join('/');return String(value);}
// Keep temporal categories unchanged for filtering, exports and notifications.
function expiryPresentation(category){
 return ({'Vencidos':['Vencido','expired'],'Vencem hoje':['Urgente','urgent'],'Até 30 dias':['Urgente','urgent'],'31 a 45 dias':['Atenção','warn'],'Após 45 dias':['Dentro do prazo','good']})[category]||[category,['Encerrado','Sem prazo v\u00e1lido'].includes(category)?'neutral':'warn'];
}
function renderTable(){
 renderOperationalControls();
 const query=searchTerm.toLocaleLowerCase('pt-BR');let rows=state.rows.filter(r=>!query||Object.entries(r).some(([k,v])=>displayValue(k,v).toLocaleLowerCase('pt-BR').includes(query)));
 rows.sort((a,b)=>String(a[sortKey]??'').localeCompare(String(b[sortKey]??''),'pt-BR',{numeric:true})*sortDirection);
 const pages=Math.max(1,Math.ceil(rows.length/pageSize));currentPage=Math.min(currentPage,pages);
 const head=el('tr');for(const key of state.columns){const button=el('button',{text:state.labels[key]||key,type:'button',class:'table-sort',...(sortKey===key?{icon:sortDirection===1?'arrow-up':'arrow-down'}:{})});button.onclick=()=>{sortDirection=sortKey===key?-sortDirection:1;sortKey=key;renderTable();};head.append(el('th',{'data-column':key,'aria-sort':sortKey===key?(sortDirection===1?'ascending':'descending'):'none'},[button]));}head.append(el('th',{text:'Ações'}));document.querySelector('#table-head').replaceChildren(head);
 const body=document.querySelector('#table-body');body.replaceChildren();for(const row of rows.slice((currentPage-1)*pageSize,currentPage*pageSize)){const tr=el('tr');for(const key of state.columns){const td=el('td',{'data-column':key});if(['status','situacao','prioridade'].includes(key)){let cls=['Concluída','Aprovada','Ativo'].includes(row[key])?'good':['Vencidos','Rejeitada','Revogado','Crítica'].includes(row[key])?'bad':'warn';const visual=key==='situacao'?expiryPresentation(row[key]):[displayValue(key,row[key]),cls];td.append(el('span',{class:'badge '+visual[1],text:visual[0],...(key==='situacao'?{title:row[key]}:{})}));}else td.textContent=displayValue(key,row[key]);tr.append(td);}const actions=el('div',{class:'row-actions'});for(const [label,fn] of [['Ver',()=>viewRecord(row)],['Editar',()=>editRecord(row)],['Excluir',()=>deleteRecord(row)]]){const button=el('button',{type:'button',class:'record-action',icon:{Ver:'eye',Editar:'edit',Excluir:'trash'}[label],title:label+' '+row.codigo,'aria-label':label+' '+row.codigo});if(label!=='Ver'&&!canWrite()){button.disabled=true;button.title='Disponível apenas para administradores';}button.onclick=fn;actions.append(button);}tr.append(el('td',{},[actions]));body.append(tr);}
 if(!rows.length)body.append(el('tr',{},[el('td',{colspan:state.columns.length+1,class:'empty',text:'Nenhum registro encontrado. Experimente limpar os filtros.'})]));
 document.querySelector('#record-count').textContent=rows.length+' registros';document.querySelector('#page-number').textContent=currentPage+' / '+pages;document.querySelector('#prev').disabled=currentPage===1;document.querySelector('#next').disabled=currentPage===pages;
 if(page==='vencimentos'){const target=document.querySelector('#expiry-summary');target.hidden=false;target.replaceChildren();for(const [label,cls] of [['Vencido','expired'],['Urgente','urgent'],['Atenção','warn'],['Dentro do prazo','good']])target.append(el('span',{class:'badge '+cls,text:label+': '+rows.filter(r=>expiryPresentation(r.situacao)[0]===label).length}));const unclassified=rows.filter(r=>['Encerrado','Sem prazo v\u00e1lido'].includes(r.situacao)).length;if(unclassified)target.append(el('small',{class:'muted',text:unclassified+' registros encerrados ou sem prazo v\u00e1lido, fora dos indicadores.'}));}
 if(page==='equipes')renderTeamCards(rows.slice((currentPage-1)*pageSize,currentPage*pageSize));
}
function renderOperationalControls(){
 if(!['ordens-servico','acessos','renovacoes'].includes(page))return;
 if(page==='renovacoes'){
  let summary=document.querySelector('#followup-summary');if(!summary){summary=el('section',{id:'followup-summary',class:'kpis','aria-label':'Indicadores das renovações filtradas'});document.querySelector('.table-panel').before(summary);}summary.replaceChildren();
  for(const [label,status,category,icon] of [['Solicitações',null,'orders','renovacoes'],['Em análise','Em análise','urgent','vencimentos'],['Aprovadas','Aprovada','access','check'],['Rejeitadas','Rejeitada','rejected','close']])summary.append(el('div',{class:'kpi','data-category':category},[el('span',{class:'kpi-label',text:label}),el('strong',{text:DashboardPreferences.formatNumber(status?state.rows.filter(r=>r.status===status).length:state.rows.length)}),el('span',{class:'kpi-icon'},[iconSvg(icon)]),el('small',{text:'Visão filtrada'})]));
 }
 let pills=document.querySelector('#status-pills');if(!pills){pills=el('div',{id:'status-pills',class:'status-pills','aria-label':'Filtrar por status'});document.querySelector('.table-scroll').before(pills);}
 pills.replaceChildren();for(const status of ['',...(state.statuses||[])]){const selected=(activeFilters.status||'')===status,b=el('button',{type:'button',class:'button '+(selected?'primary':'secondary'),text:status||'Todos','aria-pressed':String(selected)});b.onclick=()=>{if(status)activeFilters.status=status;else delete activeFilters.status;currentPage=1;loadData();};pills.append(b);}
}
function renderTeamCards(rows){
 let grid=document.querySelector('#teams-grid');if(!grid){grid=el('div',{id:'teams-grid',class:'teams-grid'});document.querySelector('.table-scroll').before(grid);}grid.replaceChildren();document.querySelector('.table-scroll').hidden=true;
 for(const r of rows){const actions=el('div',{class:'row-actions'});for(const [text,fn] of [['Ver',()=>viewRecord(r)],['Editar',()=>editRecord(r)],['Excluir',()=>deleteRecord(r)]]){const b=el('button',{type:'button',text,'aria-label':text+' '+r.nome});b.disabled=text!=='Ver'&&!canWrite();b.onclick=fn;actions.append(b);}grid.append(el('article',{class:'team-card'},[iconSvg('equipes'),el('h2',{text:r.nome}),el('p',{text:(r.quantidade_acessos||0)+' acessos · '+(r.quantidade_funcionarios||0)+' funcionários'}),el('p',{text:(r.quantidade_os||0)+' ordens de serviço'}),actions]));}
 if(!rows.length)grid.append(el('p',{class:'empty',text:'Nenhuma equipe encontrada.'}));
}
document.querySelector('#search')?.addEventListener('input',e=>{if(!dataReady)return;searchTerm=e.target.value;currentPage=1;renderTable();});
document.querySelector('#page-size')?.addEventListener('change',e=>{pageSize=Number(e.target.value);currentPage=1;renderTable();});
document.querySelector('#prev')?.addEventListener('click',()=>{currentPage--;renderTable();});document.querySelector('#next')?.addEventListener('click',()=>{currentPage++;renderTable();});
document.querySelector('#new').onclick=()=>{if(dataReady)editRecord();};
function viewRecord(row){const dl=el('dl',{class:'details-grid'});if(page==='vencimentos')dl.append(el('a',{class:'button secondary',href:(state.sheet==='OrdensServico'?'/ordens-servico':'/acessos')+'?'+new URLSearchParams({q:row.codigo}),text:'Consultar registro',icon:'external'}));for(const key of state.columns)dl.append(el('div',{},[el('dt',{text:state.labels[key]||key}),el('dd',{text:displayValue(key,row[key])})]));openModal('Detalhes · '+row.codigo,dl);}
function editRecord(row=null){
 if(!canWrite())return;
 const form=el('form');
 const relations={equipe:'Equipes',funcionario:'Funcionarios',responsavel:'Funcionarios',acesso:'Acessos'};
 for(const key of state.fields){if(key==='codigo')continue;let input;const label=el('label',{text:state.labels[key]||key});
 if(relations[key]||key==='status'||key==='prioridade'){input=el('select',{name:key});input.append(el('option',{value:'',text:'Selecione…'}));const values=relations[key]?state.lookups[relations[key]]:(key==='status'?state.statuses:['Baixa','Média','Alta','Crítica']).map(v=>({value:v,label:v}));for(const item of values)input.append(el('option',{value:item.value,text:item.label}));}
 else if(key==='observacoes'||key==='descricao')input=el('textarea',{name:key,maxlength:'1000'});
 else input=el('input',{name:key,type:['admissao','abertura','previsao','conclusao','concessao','vencimento','solicitacao'].includes(key)?'date':key==='email'?'email':'text',maxlength:'250'});
 input.value=row?.[key]||'';if(!['conclusao','observacoes'].includes(key))input.required=true;label.append(input);form.append(label);
 }
 const error=el('p',{class:'form-error',role:'alert'}),actions=el('div',{class:'form-actions'}),cancel=el('button',{type:'button',class:'button secondary',text:'Cancelar'}),save=el('button',{type:'submit',class:'button primary',text:'Salvar registro'});cancel.onclick=closeModal;actions.append(cancel,save);form.append(error,actions);
 form.onsubmit=async e=>{e.preventDefault();save.disabled=true;actionLabel(save,'Salvando…','save');try{const result=await api('/api/records/'+state.sheet+(row?'/'+row.codigo:''),{method:row?'PUT':'POST',body:JSON.stringify(Object.fromEntries(new FormData(form)))});closeModal();toast(result.message);await loadData();}catch(err){error.textContent=err.message;}finally{save.disabled=false;actionLabel(save,'Salvar registro','save');}};
 openModal(row?'Editar · '+row.codigo:'Novo registro',form);
}
function deleteRecord(row){if(!canWrite())return;const body=el('div'),text=el('p',{text:'Excluir '+row.codigo+'? Esta ação será bloqueada se houver registros relacionados. Uma cópia de segurança será preservada.'}),error=el('p',{class:'form-error',role:'alert'}),actions=el('div',{class:'form-actions'}),cancel=el('button',{class:'button secondary',text:'Cancelar'}),confirm=el('button',{class:'button danger',text:'Confirmar exclusão'});cancel.onclick=closeModal;confirm.onclick=async()=>{confirm.disabled=true;try{await api('/api/records/'+state.sheet+'/'+row.codigo,{method:'DELETE'});closeModal();toast('Registro excluído.');await loadData();}catch(err){error.textContent=err.message;}finally{confirm.disabled=false;}};actions.append(cancel,confirm);body.append(text,error,actions);openModal('Confirmar exclusão',body);}
if(!['perfil','administracao','ajuda'].includes(page))loadData();
if(page==='ajuda'){document.querySelector('.toolbar').hidden=true;document.querySelector('#updated').textContent='Central de ajuda';}
document.querySelector('#guest-appearance')?.addEventListener('click',()=>openModal('Aparência',buildPreferencesPanel()));
