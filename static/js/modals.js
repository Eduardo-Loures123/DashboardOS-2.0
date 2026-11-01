const modal=document.querySelector('#modal'),modalBody=document.querySelector('#modal-body');
let returnFocus, modalGeneration=0, modalCloseTimer;
function disposeModalPlots(){modalBody.querySelectorAll('.plot').forEach(p=>{
 if(typeof releaseChart==='function')releaseChart(p);
 else if(window.Plotly)Plotly.purge(p);
});}
function closeModal({immediate=false}={}){
 if(!modal.open)return;
 clearTimeout(modalCloseTimer);
 const generation=++modalGeneration;
 const finish=()=>{if(generation!==modalGeneration)return;disposeModalPlots();modal.classList.remove('is-closing');modal.close();};
 if(immediate||window.DashboardPreferences?.reduced()){finish();return;}
 modal.classList.add('is-closing');modalCloseTimer=setTimeout(finish,180);
}
function openModal(title,body,chart=false){
 const opener=modal.contains(document.activeElement)?returnFocus:document.activeElement;
 if(modal.open)closeModal({immediate:true});
 returnFocus=opener;const generation=++modalGeneration;
 modal.className=chart?'modal-chart':'';
 document.querySelector('#modal-title').textContent=title;
 modalBody.replaceChildren(body);
 modal.showModal();
 requestAnimationFrame(()=>{if(!modal.open||generation!==modalGeneration)return;const el=modal.querySelector('input,select,textarea')||document.querySelector('#modal-close');el.focus();});
}
document.querySelector('#modal-close').addEventListener('click',closeModal);
modal.addEventListener('click',e=>{if(e.target===modal){const r=modal.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)closeModal();}});
modal.addEventListener('cancel',event=>{event.preventDefault();closeModal();});
modal.addEventListener('close',()=>{if(modal.open)return;disposeModalPlots();if(returnFocus?.isConnected)returnFocus.focus();});
function toast(message,error=false){const el=document.querySelector('#toast');el.textContent=message;el.className='show'+(error?' error':'');clearTimeout(window.toastTimer);window.toastTimer=setTimeout(()=>el.className='',5000);}
function el(tag,props={},children=[]){const node=document.createElement(tag);for(const [k,v] of Object.entries(props)){if(k==='text')node.textContent=v;else if(k==='class')node.className=v;else node.setAttribute(k,v);}for(const child of children)node.append(child);return node;}
