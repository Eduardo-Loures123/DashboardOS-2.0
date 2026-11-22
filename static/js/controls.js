/* Native controls remain the source of truth for FormData and validation. */
window.DashboardControls=(()=>{
 const instances=new Map();let sequence=0,destroyed=false;
 const normalize=text=>text.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('pt-BR');
 function enhance(select){
  if(instances.has(select))return;
  const wrapper=document.createElement('span');wrapper.className='select-control';
  const input=document.createElement('input');input.type='text';input.className='select-input';input.autocomplete='off';input.spellcheck=false;input.placeholder='Selecionar opções…';
  const label=select.closest('label'),id='select-options-'+(++sequence);
  if(label){input.setAttribute('aria-label',Array.from(label.childNodes).filter(n=>n.nodeType===3).map(n=>n.textContent).join(' ').trim()||select.name||'Selecionar opção');}
  else input.setAttribute('aria-label',select.getAttribute('aria-label')||'Selecionar opção');
  input.setAttribute('role','combobox');input.setAttribute('aria-autocomplete','list');input.setAttribute('aria-expanded','false');input.setAttribute('aria-controls',id);
  const popup=document.createElement('div');popup.className='select-popup';popup.hidden=true;
  const list=document.createElement('div');list.id=id;list.setAttribute('role','listbox');if(select.multiple)list.setAttribute('aria-multiselectable','true');popup.append(list);
  select.before(wrapper);wrapper.append(select,input);select.classList.add('native-select');select.tabIndex=-1;select.setAttribute('aria-hidden','true');
  const arrow=document.createElement('span');arrow.className='select-chevron';arrow.append(iconSvg('down'));arrow.setAttribute('aria-hidden','true');wrapper.append(arrow);
  let opened=false,filtered=[],index=-1,keyboardActive=false,searchable=null;
  const selectedText=()=>Array.from(select.selectedOptions,o=>o.textContent).join(', ');
  const available=option=>!option.hidden&&!option.disabled&&!option.closest('optgroup[disabled]');
  const sync=()=>{const mode=Array.from(select.options).filter(available).length>=8,changed=mode!==searchable;searchable=mode;input.readOnly=!mode;input.setAttribute('aria-autocomplete',mode?'list':'none');wrapper.dataset.searchable=String(mode);input.disabled=select.disabled;input.setAttribute('aria-required',String(select.required));if(select.disabled&&opened){close();return;}if(!opened){input.value=selectedText();input.title=input.value;}else{if(changed)input.value=mode?'':selectedText();render();position();}};
  function position(){
   const r=input.getBoundingClientRect(),height=Math.min(280,Math.max(100,innerHeight-24));
   popup.style.width=Math.min(Math.max(r.width,220),innerWidth-24)+'px';
   const actual=popup.getBoundingClientRect();
   const below=innerHeight-r.bottom-12,above=r.top-12;
   popup.style.maxHeight=Math.min(height,Math.max(below,above))+'px';
   popup.style.left=Math.max(12,Math.min(r.left,innerWidth-actual.width-12))+'px';
   popup.style.top=(below>=Math.min(actual.height,height)||below>=above?r.bottom+6:Math.max(12,r.top-Math.min(actual.height,height,above)-6))+'px';
  }
  function close(){opened=false;popup.hidden=true;input.placeholder='Selecionar opções…';input.setAttribute('aria-expanded','false');input.removeAttribute('aria-activedescendant');sync();}
  function choose(option){
   if(!option||!available(option))return;
   input.setCustomValidity('');input.removeAttribute('aria-invalid');
   if(select.multiple)option.selected=!option.selected;else select.value=option.value;
   select.dispatchEvent(new Event('input',{bubbles:true}));select.dispatchEvent(new Event('change',{bubbles:true}));
   close();input.focus();
  }
  function render(){
   const query=searchable?normalize(input.value):'';filtered=Array.from(select.options).filter(o=>!o.hidden&&normalize(o.textContent).includes(query));
   list.replaceChildren();index=Math.min(index,filtered.length-1);
   filtered.forEach((option,i)=>{
    const row=document.createElement('div');row.id=id+'-'+i;row.className='select-option';row.setAttribute('role','option');row.setAttribute('aria-selected',String(option.selected));row.setAttribute('aria-disabled',String(option.disabled));
    row.textContent=option.textContent;if(option.selected)row.append(iconSvg('check'));row.classList.toggle('is-active',keyboardActive&&i===index);row.addEventListener('pointerdown',e=>{e.preventDefault();e.stopPropagation();choose(option);});list.append(row);
   });
   if(!filtered.length){const empty=document.createElement('p');empty.className='select-empty';empty.textContent='Nenhuma opção encontrada.';empty.setAttribute('role','status');list.append(empty);input.removeAttribute('aria-activedescendant');}
   else if(keyboardActive&&index>=0)input.setAttribute('aria-activedescendant',id+'-'+index);else input.removeAttribute('aria-activedescendant');
  }
  function open(query=''){if(select.disabled||opened)return;opened=true;input.value=searchable?query:selectedText();input.placeholder=searchable?'Pesquisar opções…':'Selecionar opção';keyboardActive=false;index=0;(select.closest('dialog')||document.body).append(popup);popup.hidden=false;input.setAttribute('aria-expanded','true');render();position();}
  // Modal autofocus and Tab focus must not expand the list.
  input.addEventListener('click',()=>open());
  input.addEventListener('input',()=>{if(!searchable){input.value=selectedText();return;}if(!opened)open(input.value);keyboardActive=false;index=0;render();position();});
  input.addEventListener('keydown',event=>{
   if(event.key==='Escape'&&opened){event.preventDefault();event.stopPropagation();close();}
   else if(event.key==='Tab')close();
   else if(['ArrowDown','ArrowUp'].includes(event.key)){
    event.preventDefault();if(!opened)open();{keyboardActive=true;const step=event.key==='ArrowDown'?1:-1;let candidate=index<0?(step===1?-1:0):index;index=-1;for(let tries=0;tries<filtered.length;tries++){candidate=(candidate+step+filtered.length)%filtered.length;if(available(filtered[candidate])){index=candidate;break;}}render();list.children[index]?.scrollIntoView?.({block:'nearest'});}
   }else if(event.key==='Enter'&&opened){event.preventDefault();choose(filtered[index]||filtered.find(option=>option.selected));}
   else if((event.key==='Enter'||event.key===' ')&&!opened){event.preventDefault();open();}
  });
  input.addEventListener('blur',()=>close());
  select.addEventListener('change',sync);
  select.addEventListener('focus',()=>input.focus());
  select.addEventListener('invalid',event=>{event.preventDefault();input.focus();input.setAttribute('aria-invalid','true');input.setCustomValidity(select.validationMessage);input.reportValidity?.();});
  input.addEventListener('input',()=>{input.setCustomValidity('');input.removeAttribute('aria-invalid');});
  const outside=event=>{if(!wrapper.contains(event.target)&&!popup.contains(event.target))close();};
  document.addEventListener('pointerdown',outside);
  const scroll=event=>{if(opened&&!popup.contains(event.target))close();};window.addEventListener('scroll',scroll,true);window.addEventListener('resize',close);
  const observer=new MutationObserver(sync);observer.observe(select,{attributes:true,childList:true,subtree:true,characterData:true});
  instances.set(select,{sync,close,destroy(){close();observer.disconnect();popup.remove();document.removeEventListener('pointerdown',outside);window.removeEventListener('scroll',scroll,true);window.removeEventListener('resize',close);instances.delete(select);}});sync();
 }
 function refresh(){
  for(const [select,item] of instances)if(!select.isConnected)item.destroy();
  document.querySelectorAll('select').forEach(enhance);for(const item of instances.values())item.sync();
  document.querySelectorAll('input[type="date"]').forEach(input=>{input.lang='pt-BR';input.setAttribute('aria-description','Data no formato dia, mês e ano.');});
 }
 let queued=false;
 const observer=new MutationObserver(records=>{
  if(!records.some(r=>[...r.addedNodes,...r.removedNodes].some(n=>n.nodeType===1&&(n.matches?.('select,input[type="date"]')||n.querySelector?.('select,input[type="date"]')))))return;
  if(!queued){queued=true;queueMicrotask(()=>{queued=false;if(!destroyed)refresh();});}
 });
 observer.observe(document.body,{childList:true,subtree:true});
 document.addEventListener('reset',()=>queueMicrotask(refresh));
 document.querySelector('#modal')?.addEventListener('close',()=>{for(const item of instances.values())item.close();});
 refresh();return {refresh,closeAll(){for(const item of instances.values())item.close();},destroy(){destroyed=true;observer.disconnect();for(const item of [...instances.values()])item.destroy();}};
})();
