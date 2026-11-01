let activeFilters={};
function filterLabel(key){return ({inicio:'Data inicial',fim:'Data final',situacao:'Situação do vencimento',q:'Pesquisa'})[key]||state.labels[key]||key;}
function optionLabel(key,value){const target=({equipe:'Equipes',funcionario:'Funcionarios',responsavel:'Funcionarios',acesso:'Acessos'})[key];return target?(state.lookups?.[target]?.find(r=>r.value===value)?.label||value):value;}
document.querySelector('#filters-button').addEventListener('click',()=>{
 if(!dataReady||!Array.isArray(state.filterFields))return;
 const form=el('form');
 for(const key of state.filterFields){const label=el('label',{text:filterLabel(key)});let input;
  if(['inicio','fim'].includes(key)){input=el('input',{type:'date',name:key});}
  else{input=el('select',{name:key});input.append(el('option',{value:'',text:'Todos'}));for(const value of state.filters[key]||[])input.append(el('option',{value,text:optionLabel(key,value)}));}
  input.value=activeFilters[key]||'';label.append(input);form.append(label);
 }
 const error=el('p',{class:'form-error',role:'alert'});form.append(error);
 const actions=el('div',{class:'form-actions'}),clear=el('button',{type:'button',class:'button secondary',text:'Limpar filtros'}),apply=el('button',{type:'submit',class:'button primary',text:'Aplicar filtros'});actions.append(clear,apply);form.append(actions);
 clear.onclick=()=>{activeFilters={};currentPage=1;closeModal();loadData();};
 form.onsubmit=e=>{e.preventDefault();const values=Object.fromEntries(new FormData(form));if(values.inicio&&values.fim&&values.inicio>values.fim){error.textContent='A data final deve ser igual ou posterior à data inicial.';return;}activeFilters=Object.fromEntries(Object.entries(values).filter(([,v])=>v));currentPage=1;closeModal();loadData();};
 openModal('Filtrar informações',form);
});
