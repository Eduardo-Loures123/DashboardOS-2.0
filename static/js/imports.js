/* Preview first; only an explicit confirmation can persist operational records. */
(()=>{
 const opener=document.querySelector('#import-excel');
 let refreshPending=false;
 const refresh=()=>{if(['perfil','administracao','ajuda'].includes(page))return;if(document.hidden){refreshPending=true;return;}loadData();};
 window.addEventListener('storage',event=>{if(event.key==='dashboardos-data-revision')refresh();});
 document.addEventListener('visibilitychange',()=>{if(!document.hidden&&refreshPending){refreshPending=false;refresh();}});
 if(!opener)return;
 opener.addEventListener('click',()=>{
  if(!canWrite())return;
  const body=el('section',{class:'import-layout'}),form=el('form',{class:'import-form'});
  const file=el('input',{type:'file',accept:'.xlsx',required:'',name:'file'}),mode=el('select',{name:'mode','aria-label':'Modo de importação'});
  mode.append(el('option',{value:'new',text:'Adicionar somente novos registros'}),el('option',{value:'upsert',text:'Adicionar e atualizar por código'}));
  const info=el('p',{class:'muted',text:'Nenhum arquivo selecionado. XLSX · até 5 MB e 5.000 registros.'}),status=el('p',{class:'import-status',role:'status','aria-live':'polite',text:'Selecione o Excel exportado pelo DashboardOS para analisar.'}),preview=el('div',{class:'import-preview'});
  const analyze=el('button',{class:'button secondary',type:'submit',text:'Analisar arquivo',icon:'search'}),confirm=el('button',{class:'button primary',type:'button',text:'Confirmar importação',icon:'check'}),cancel=el('button',{class:'button secondary',type:'button',text:'Cancelar'});
  confirm.disabled=true;analyze.disabled=true;
  form.append(el('div',{class:'import-file-group'},[el('label',{text:'Arquivo Excel'},[file]),info]),el('div',{class:'import-mode-group'},[el('label',{text:'Modo de importação'},[mode]),el('p',{class:'muted',text:'Registros ausentes no arquivo serão preservados. Nenhum dado será alterado durante a análise.'})]),analyze);
  body.append(el('div',{class:'import-content'},[form,status,preview]),el('div',{class:'form-actions'},[cancel,confirm]));
  let token=null,busy=false,completed=false;
  async function discard(){const previous=token;token=null;if(previous&&!completed)try{await api('/api/import/cancel',{method:'POST',body:JSON.stringify({token:previous})});}catch{/* Expired previews contain no persisted changes. */}}
  function invalidate(){discard();confirm.disabled=true;preview.replaceChildren();status.classList.remove('form-error');status.textContent='Arquivo ou modo alterado. Analise antes de confirmar.';}
  function processing(value,message){busy=value;modal.dataset.lockClose=String(value);file.disabled=value;mode.disabled=value;analyze.disabled=value||!file.files.length;cancel.disabled=value;document.querySelector('#modal-close').disabled=value;confirm.disabled=value||!token||completed;body.setAttribute('aria-busy',String(value));if(message)status.textContent=message;}
  file.addEventListener('change',()=>{invalidate();const selected=file.files[0];info.textContent=selected?selected.name+' · '+(selected.size/1024).toLocaleString('pt-BR',{maximumFractionDigits:1})+' KB':'Nenhum arquivo selecionado.';analyze.disabled=!selected;});
  mode.addEventListener('change',invalidate);
  function paged(items,render){
   const box=el('div',{class:'import-list'}),content=el('div'),controls=el('div',{class:'import-list-pages'}),previous=el('button',{type:'button',class:'icon-button',icon:'left','aria-label':'Prévia anterior'}),next=el('button',{type:'button',class:'icon-button',icon:'right','aria-label':'Próxima prévia'}),label=el('span');let current=0;
   function draw(){const pages=Math.max(1,Math.ceil(items.length/25));content.replaceChildren(...items.slice(current*25,current*25+25).map(render));label.textContent=(current+1)+' / '+pages+' · '+items.length+' registros';previous.disabled=current===0;next.disabled=current>=pages-1;}
   previous.onclick=()=>{current--;draw();};next.onclick=()=>{current++;draw();};controls.append(previous,label,next);box.append(content,controls);draw();return box;
  }
  function show(result){
   preview.replaceChildren(el('h3',{text:'Prévia de '+result.filename}));
   const grid=el('div',{class:'import-summary'});
   for(const [sheet,counts] of Object.entries(result.sheets))grid.append(el('article',{},[el('strong',{text:sheet}),el('p',{text:counts.found+' encontrados · '+counts.added+' novos · '+counts.updated+' com alterações'}),el('small',{text:counts.unchanged+' sem alterações · '+counts.ignored+' ignorados · '+counts.invalid+' inválidos'})]));
   preview.append(grid);
   if(result.errors.length){preview.append(el('h3',{text:'Corrija os erros antes de importar'}),paged(result.errors,error=>el('p',{class:'form-error',text:error.sheet+' · linha '+error.line+(error.code?' · '+error.code:'')+(error.field?' · '+error.field:'')+': '+error.message})));}
   if(result.changes.length)preview.append(el('h3',{text:'Alterações propostas'}),paged(result.changes,change=>{
    const details=el('details',{class:'import-change'}),list=el('dl');details.append(el('summary',{text:change.sheet+' · '+change.code+' · linha '+change.line+' · '+(change.kind==='added'?'Novo registro':'Atualizar registro')}));
    for(const field of change.fields)list.append(el('dt',{text:field.field}),el('dd',{text:(change.kind==='updated'?(field.before||'Vazio')+' → ':'')+(field.after||'Vazio')}));details.append(list);return details;
   }));
   status.textContent=result.errors.length?'Validação encontrou erros. Nenhum registro será importado.':result.can_confirm?'Validação concluída. Revise as alterações e confirme para importar.':'Análise concluída. Não há alterações para importar neste modo.';
   status.classList.toggle('form-error',result.errors.length>0);
  }
  form.onsubmit=async event=>{
   event.preventDefault();if(busy)return;const selected=file.files[0];if(!selected)return;
   if(!/\.xlsx$/i.test(selected.name)||selected.size>5*1024*1024){status.textContent='Selecione um arquivo .xlsx de até 5 MB.';status.classList.add('form-error');return;}
   processing(true,'Analisando arquivo…');status.classList.remove('form-error');await discard();preview.replaceChildren();
   try{
    const payload=new FormData();payload.append('file',selected);payload.append('mode',mode.value);
    const response=await fetch('/api/import/preview',{method:'POST',headers:{'X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content},body:payload});
    let result;try{result=await response.json();}catch{throw Error('O servidor não conseguiu analisar o arquivo. Tente novamente.');}
    if(!response.ok)throw Error(result.error||'Não foi possível analisar o arquivo.');token=result.token;show(result);processing(false);confirm.disabled=!result.can_confirm;
   }catch(error){processing(false);confirm.disabled=true;status.textContent=error.message||'Falha ao analisar o arquivo.';status.classList.add('form-error');}
  };
  confirm.onclick=async()=>{
   if(busy||!token||confirm.disabled)return;processing(true,'Importação em andamento…');status.classList.remove('form-error');
   try{
    const result=await api('/api/import/confirm',{method:'POST',body:JSON.stringify({token})});completed=true;
    const c=result.totals;status.textContent='Importação concluída: '+c.added+' adicionados, '+c.updated+' atualizados, '+c.unchanged+' sem alterações e '+c.ignored+' ignorados. Nenhum registro rejeitado.';
    preview.replaceChildren();form.hidden=true;cancel.textContent='Concluir';processing(false);confirm.hidden=true;
    try{localStorage.setItem('dashboardos-data-revision',Date.now()+'-'+Math.random());}catch{}
    await loadData();
   }catch(error){processing(false);confirm.disabled=true;token=null;status.textContent=error.message;status.classList.add('form-error');}
  };
  cancel.onclick=()=>{if(!busy)closeModal();};
  const cleanup=()=>{discard();delete modal.dataset.lockClose;document.querySelector('#modal-close').disabled=false;};modal.addEventListener('close',cleanup,{once:true});
  openModal('Importar dados do Excel',body);modal.classList.add('import-modal');
 });
})();
