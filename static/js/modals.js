const modal=document.querySelector('#modal'),modalBody=document.querySelector('#modal-body');
let returnFocus, modalGeneration=0, modalCloseTimer;
function disposeModalPlots(){modalBody.querySelectorAll('.plot').forEach(p=>{
 if(typeof releaseChart==='function')releaseChart(p);
 else if(window.Plotly)Plotly.purge(p);
});}
function closeModal({immediate=false}={}){
 if(modal.dataset.lockClose==='true')return;
 if(!modal.open)return;
 clearTimeout(modalCloseTimer);
 const generation=++modalGeneration;
 const finish=()=>{if(generation!==modalGeneration)return;disposeModalPlots();modal.classList.remove('is-closing');modal.close();};
 if(immediate||window.DashboardPreferences?.reduced()){finish();return;}
 modal.classList.add('is-closing');modalCloseTimer=setTimeout(finish,window.DashboardMotion?.duration('modal-exit',180)??180);
}
function openModal(title,body,chart=false){
 const opener=modal.contains(document.activeElement)?returnFocus:document.activeElement;
 if(modal.open)closeModal({immediate:true});
 returnFocus=opener;const generation=++modalGeneration;
 modal.querySelectorAll('[data-modal-icon]').forEach(node=>node.remove());
 modal.className=chart?'modal-chart':'';
 if(!chart&&body.matches?.('form')&&body.querySelectorAll(':scope > label').length===1)modal.classList.add('modal-single');
 document.querySelector('#modal-title').textContent=title;
 modalBody.replaceChildren(body);
 modal.showModal();
 requestAnimationFrame(()=>{if(!modal.open||generation!==modalGeneration)return;const el=modal.querySelector('input,select,textarea')||document.querySelector('#modal-close');el.focus();});
}
document.querySelector('#modal-close').addEventListener('click',closeModal);
modal.addEventListener('click',e=>{if(e.target===modal){const r=modal.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)closeModal();}});
modal.addEventListener('cancel',event=>{event.preventDefault();closeModal();});
modal.addEventListener('close',()=>{if(modal.open)return;disposeModalPlots();if(returnFocus?.isConnected)returnFocus.focus({preventScroll:true});});
function toast(message,error=false){const el=document.querySelector('#toast');el.textContent=message;el.className='show'+(error?' error':'');clearTimeout(window.toastTimer);window.toastTimer=setTimeout(()=>el.className='',5000);}
function el(tag,props={},children=[]){const node=document.createElement(tag);for(const [k,v] of Object.entries(props)){if(k==='text')node.textContent=v;else if(k==='class')node.className=v;else if(k!=='icon')node.setAttribute(k,v);}const icon=props.icon||(tag==='button'&&props.text?actionIcon(props.text):null);if(icon)node.prepend(iconSvg(icon));for(const child of children)node.append(child);return node;}

let activeConfirmation=null,confirmationSequence=0;
function openConfirmation({title,message,icon='warning',confirmLabel='Confirmar',onConfirm}){
 if(activeConfirmation?.open)return activeConfirmation;
 const opener=document.activeElement,id='confirmation-title-'+(++confirmationSequence),dialog=el('dialog',{class:'confirmation-dialog notification-confirm','aria-labelledby':id});
 const cancel=el('button',{type:'button',class:'button secondary',text:'Cancelar'}),confirm=el('button',{type:'button',class:'button danger',text:confirmLabel,icon}),close=el('button',{type:'button',class:'icon-button','aria-label':'Fechar confirmação',icon:'close'}),error=el('p',{class:'form-error',role:'alert'});
 let busy=false;
 function finish(){if(busy)return;dialog.close();dialog.remove();modal.removeEventListener('close',finish);if(activeConfirmation===dialog)activeConfirmation=null;if(opener?.isConnected&&!opener.disabled)opener.focus({preventScroll:true});else if(modal.open)modal.querySelector('input,button')?.focus({preventScroll:true});}
 cancel.onclick=close.onclick=finish;
 dialog.addEventListener('cancel',event=>{event.preventDefault();finish();});
 dialog.addEventListener('click',event=>{if(event.target!==dialog)return;const rect=dialog.getBoundingClientRect();if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)finish();});
 confirm.onclick=async()=>{if(busy)return;busy=true;cancel.disabled=confirm.disabled=close.disabled=true;dialog.setAttribute('aria-busy','true');error.textContent='';try{await onConfirm();busy=false;finish();}catch(e){error.textContent=e.message||'Não foi possível concluir a ação.';}finally{busy=false;cancel.disabled=confirm.disabled=close.disabled=false;dialog.removeAttribute('aria-busy');}};
 dialog.append(el('div',{class:'modal-heading'},[el('div',{class:'confirmation-title'},[iconSvg(icon),el('h2',{id,text:title})]),close]),el('p',{class:'confirmation-message',text:message}),error,el('div',{class:'form-actions'},[cancel,confirm]));
 document.body.append(dialog);activeConfirmation=dialog;modal.addEventListener('close',finish);dialog.showModal();cancel.focus();return dialog;
}
