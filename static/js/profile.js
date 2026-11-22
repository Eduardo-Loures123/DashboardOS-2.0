/* Account data enters the DOM as text. No mail delivery or queue processing. */
(()=>{
 const content=document.querySelector('#account-content'),onProfile=document.body.dataset.page==='perfil';
 const roles={superadmin:'Superadministrador',admin:'Administrador',user:'Usuário'};
 let data,editing=false,tab=new URLSearchParams(location.search).get('tab')==='preferences'?'preferences':'account',acceptedNavigation=false,accountForm,securityForm,emailForm;
 const initials=name=>String(name||'').trim().split(/\s+/).filter(Boolean).slice(0,2).map(x=>x[0]).join('').toLocaleUpperCase('pt-BR')||'D';
 const btn=(label,handler,style='secondary',icon)=>{const b=el('button',{type:'button',class:'button '+style,text:label,...(icon?{icon}:{})});b.onclick=handler;return b;};
 function input(parent,label,name,value='',type='text'){
  const wrap=el('label',{class:'profile-field'}),caption=el('span',{text:label}),i=el('input',{name,type,autocomplete:type==='password'?'new-password':'off'});i.value=value??'';wrap.append(caption);
  if(type==='password'){const control=el('div',{class:'password-control'}),toggle=btn('Mostrar',()=>{i.type=i.type==='password'?'text':'password';toggle.textContent=i.type==='password'?'Mostrar':'Ocultar';toggle.setAttribute('aria-pressed',String(i.type==='text'));});toggle.setAttribute('aria-label','Mostrar ou ocultar '+label.toLowerCase());toggle.setAttribute('aria-pressed','false');control.append(i,toggle);wrap.append(control);}else wrap.append(i);
  parent.append(wrap);return i;
 }
 function section(title,subtitle,icon){const s=el('section',{class:'profile-card'});s.append(el('div',{class:'profile-card-heading'},[el('span',{class:'profile-symbol'},[iconSvg(icon)]),el('div',{},[el('h2',{text:title}),el('p',{class:'muted',text:subtitle})])]));return s;}
 function avatar(node,size=''){node.replaceChildren();node.classList.add('account-avatar');if(size)node.classList.add(size);if(data?.avatar_url){const img=el('img',{src:data.avatar_url,alt:'Foto de perfil'});img.onerror=()=>node.replaceChildren(document.createTextNode(initials(data.display_name||data.user_id)));node.append(img);}else node.textContent=initials(data?.display_name||data?.user_id);if(node.tagName==='BUTTON')node.append(el('span',{class:'camera-badge','aria-hidden':'true'},[iconSvg('camera')]));}
 function syncIdentity(){
  if(!data)return;
  document.querySelectorAll('[data-account-avatar]').forEach(n=>avatar(n));
  document.querySelectorAll('[data-profile-name]').forEach(n=>n.textContent=data.display_name||data.user_id);
  document.querySelectorAll('[data-profile-login]').forEach(n=>n.textContent='ID: '+data.user_id);
  document.querySelectorAll('[data-remove-photo]').forEach(n=>n.disabled=!data.avatar_url);
 }
 // Compare account values with a stable, normalized server snapshot. Other forms
 // track explicit edits only while visible, ignoring hidden password-manager fills.
 let accountOriginal,trackedForms=new Map();
 const accountValues=()=>({display_name:accountForm.elements.display_name.value.trim(),user_id:accountForm.elements.user_id.value.toLowerCase()});
 function rememberAccount(){accountOriginal={display_name:String(data.display_name||'').trim(),user_id:String(data.user_id).toLowerCase()};}
 function accountChanged(){if(!editing||!accountForm||!accountOriginal)return false;const current=accountValues();return Object.keys(current).some(key=>current[key]!==accountOriginal[key]);}
 const fieldValue=i=>i.type==='checkbox'?i.checked:i.value;
 function rememberForm(form){
  const values=new Map(Array.from(form.querySelectorAll('input,select')).map(i=>[i,fieldValue(i)]));
  trackedForms.set(form,{values,touched:new Set()});
 }
 function trackForm(form){
  rememberForm(form);
  const edited=event=>{if(form.hidden||form.closest('[hidden]'))return;const state=trackedForms.get(form);if(state?.values.has(event.target))state.touched.add(event.target);};
  form.addEventListener('input',edited);form.addEventListener('change',edited);
 }
 function changed(){return accountChanged()||Array.from(trackedForms.values()).some(state=>Array.from(state.touched).some(i=>fieldValue(i)!==state.values.get(i)));}
 function askDiscard(){return new Promise(resolve=>{const box=el('div',{class:'discard-confirmation'}),actions=el('div',{class:'form-actions'});box.append(el('p',{text:'Você possui alterações não salvas. Deseja descartá-las?'}));let done=false;const finish=value=>{if(done)return;done=true;resolve(value);};actions.append(btn('Continuar editando',()=>{finish(false);closeModal();}),btn('Descartar alterações',()=>{finish(true);closeModal();},'primary'));box.append(actions);openModal('Alterações não salvas',box);modal.addEventListener('close',()=>finish(false),{once:true});});}
 function discard(){if(accountForm){accountForm.elements.display_name.value=data.display_name;accountForm.elements.user_id.value=data.user_id;accountForm.elements.current_password.value='';setEditing(false);}for(const [form,state] of trackedForms){for(const [i,value] of state.values){if(i.type==='checkbox')i.checked=value;else i.value=value;}form.dispatchEvent(new Event('input',{bubbles:true}));state.touched.clear();}}
 async function switchTab(next){if(next===tab)return;if(changed()){if(!await askDiscard())return;discard();}tab=next;document.querySelectorAll('[data-profile-tab]').forEach(b=>{const selected=b.dataset.profileTab===next;b.setAttribute('aria-selected',String(selected));b.tabIndex=selected?0:-1;});document.querySelectorAll('[data-profile-panel]').forEach(p=>p.hidden=p.dataset.profilePanel!==next);if(next==='activities'){revealActivities=true;await loadActivities();}}
 function setEditing(value){editing=value;if(!accountForm)return;for(const key of ['display_name','user_id'])accountForm.elements[key].readOnly=!value;accountForm.querySelector('[data-edit-account]').hidden=value;accountForm.querySelector('[data-save-account]').hidden=!value;accountForm.querySelector('[data-cancel-account]').hidden=!value;validateAccount();}
 let availability=true,lookupTimer,lookupSequence=0;
 function validateAccount(){
  if(!accountForm)return;const login=accountForm.elements.user_id.value.toLowerCase(),loginChanged=login!==data.user_id.toLowerCase();
  const pwd=accountForm.elements.current_password;pwd.closest('label').hidden=!editing||!loginChanged;pwd.required=editing&&loginChanged;
  const valid=accountForm.elements.display_name.value.trim().length>0&&accountForm.elements.display_name.value.length<=120&&/^[a-z0-9_.-]{3,64}$/.test(login)&&(!loginChanged||availability===true&&pwd.value.length>0);
  const dirty=accountChanged();
  accountForm.querySelector('[data-save-account]').disabled=!editing||!dirty||!valid;
 }
 function accountPanel(){
  const card=section('Dados da conta','Suas informações e sua identidade no DashboardOS.','user');
  const photo=el('div',{class:'profile-photo-row'}),a=el('button',{type:'button',class:'profile-photo-button','aria-label':'Alterar foto de perfil','data-account-avatar':''});a.onclick=choosePhoto;avatar(a,'avatar-large');
  const controls=el('div',{class:'photo-actions'},[btn('Trocar foto',choosePhoto,'primary','edit')]);const remove=btn('Remover foto',async()=>{try{const r=await api('/api/profile/avatar',{method:'DELETE'});data.avatar_url=r.profile.avatar_url;syncIdentity();remove.disabled=true;toast(r.message);}catch(e){toast(e.message,true);}},'secondary','trash');remove.disabled=!data.avatar_url;controls.append(remove,el('small',{class:'muted',text:'JPG, PNG ou WebP. Até 5 MB.'}));
  remove.dataset.removePhoto='';photo.append(a,controls,el('aside',{class:'profile-data-notice'},[iconSvg('info'),el('div',{},[el('strong',{text:'Sobre seus dados'}),el('p',{text:'Nome e identificador podem ser atualizados. Sua função e suas permissões são gerenciadas pelo administrador.'})])]));card.append(photo);
  accountForm=el('form',{id:'profile-info-form',class:'account-form'});const grid=el('div',{class:'profile-fields'});
  input(grid,'Nome de exibição','display_name',data.display_name).maxLength=120;
  const email=input(grid,'E-mail atual','email_info',data.email||'Não cadastrado');email.readOnly=true;
  const login=input(grid,'ID de login','user_id',data.user_id);login.maxLength=64;
  const role=input(grid,'Função','role_info',roles[data.role]||data.role);role.disabled=true;
  const pwd=input(grid,'Senha atual para confirmar o novo ID','current_password','','password');pwd.autocomplete='current-password';
  const status=el('p',{class:'login-availability',role:'status'}),error=el('p',{class:'form-error',role:'alert'}),actions=el('div',{class:'form-actions'});
  const edit=btn('Editar informações',()=>{availability=true;setEditing(true);accountForm.elements.display_name.focus();},'primary','edit');edit.dataset.editAccount='';
  const cancel=btn('Cancelar',()=>{accountForm.elements.display_name.value=data.display_name;login.value=data.user_id;pwd.value='';status.textContent='';error.textContent='';setEditing(false);});cancel.dataset.cancelAccount='';
  const save=el('button',{type:'submit',class:'button primary',text:'Salvar informações','data-save-account':''});actions.append(edit,cancel,save);
  accountForm.append(grid,status,el('p',{class:'profile-footnote',text:'O ID é único, sem espaços, com 3 a 64 letras, números, ponto, hífen ou sublinhado. Alterá-lo exige sua senha e um novo login.'}),error,actions);
  accountForm.addEventListener('input',event=>{error.textContent='';if(event.target===login){clearTimeout(lookupTimer);const seq=++lookupSequence;availability=null;const value=login.value.toLowerCase();if(value===data.user_id.toLowerCase()){availability=true;status.textContent='';}else if(/^[a-z0-9_.-]{3,64}$/.test(value)){status.textContent='Verificando disponibilidade…';lookupTimer=setTimeout(async()=>{try{const r=await api('/api/profile/login-availability?login='+encodeURIComponent(value));if(seq!==lookupSequence)return;availability=r.available;status.textContent=r.available?'Identificador disponível':'Identificador indisponível';validateAccount();}catch(e){if(seq===lookupSequence){availability=false;status.textContent=e.message;validateAccount();}}},300);}else status.textContent='Identificador inválido.';}validateAccount();});
  accountForm.onsubmit=async event=>{event.preventDefault();if(save.disabled)return;save.disabled=true;try{const r=await api('/api/profile',{method:'PUT',body:JSON.stringify({display_name:accountForm.elements.display_name.value,user_id:login.value,current_password:pwd.value})});acceptedNavigation=Boolean(r.redirect);if(r.redirect){editing=false;location.assign(r.redirect);return;}data=r.profile||await api('/api/profile');rememberAccount();accountForm.elements.display_name.value=data.display_name;login.value=data.user_id;pwd.value='';syncIdentity();setEditing(false);toast(r.message);}catch(e){error.textContent=e.message;validateAccount();}};
  card.append(accountForm);setEditing(false);return card;
 }
 function securityPanel(){
  const card=section('Senha e autenticação','Proteja sua conta com uma senha exclusiva.','shield'),open=btn('Alterar senha',()=>{securityForm.hidden=false;open.hidden=true;securityForm.elements.current_password.focus();},'primary','lock');
  securityForm=el('form',{id:'profile-security-form',class:'account-form'});securityForm.hidden=true;
  const current=input(securityForm,'Senha atual','current_password','','password');current.required=true;current.autocomplete='current-password';
  const password=input(securityForm,'Nova senha','password','','password');password.required=true;password.minLength=12;password.maxLength=256;
  const confirm=input(securityForm,'Confirmar nova senha','password_confirmation','','password');confirm.required=true;confirm.maxLength=256;
  const error=el('p',{class:'form-error',role:'alert'}),save=el('button',{type:'submit',class:'button primary',text:'Salvar nova senha'});save.disabled=true;
  securityForm.addEventListener('input',()=>{error.textContent=confirm.value&&password.value!==confirm.value?'As senhas não coincidem.':'';save.disabled=!current.value||password.value.length<12||password.value.length>256||password.value!==confirm.value;});
  securityForm.append(el('p',{class:'profile-footnote',text:'Use de 12 a 256 caracteres. As sessões serão encerradas após a alteração.'}),error,el('div',{class:'form-actions'},[btn('Cancelar',()=>{securityForm.reset();rememberForm(securityForm);securityForm.hidden=true;open.hidden=false;save.disabled=true;error.textContent='';}),save]));
  securityForm.onsubmit=async event=>{event.preventDefault();if(password.value!==confirm.value){error.textContent='As senhas não coincidem.';return;}save.disabled=true;try{const r=await api('/api/profile',{method:'PUT',body:JSON.stringify(Object.fromEntries(new FormData(securityForm)))});securityForm.reset();rememberForm(securityForm);acceptedNavigation=true;toast(r.message);if(r.redirect)location.assign(r.redirect);}catch(e){error.textContent=e.message;save.disabled=false;}};
  card.append(open,securityForm);return card;
 }
 function emailPanel(){
  const wrapper=el('div',{class:'profile-email-layout'}),card=section('E-mail e verificação','Seu endereço atual só muda depois da confirmação do novo.','mail');
  card.append(el('strong',{text:data.email||'Nenhum endereço cadastrado'}),el('span',{class:'verification-badge '+(data.verified?'verified':''),text:data.verified?'Verificado':'Não verificado'}));
  emailForm=el('form',{id:'profile-email-form',class:'account-form'});const email=input(emailForm,'Novo endereço de e-mail','email','','email');email.required=true;email.maxLength=254;const password=input(emailForm,'Senha atual','current_password','','password');password.required=true;password.autocomplete='current-password';
  const error=el('p',{class:'form-error',role:'alert'}),save=el('button',{type:'submit',class:'button primary',text:'Preparar confirmação'});
  emailForm.append(error,el('div',{class:'form-actions'},[btn('Cancelar edição',()=>{emailForm.reset();rememberForm(emailForm);}),save]));
  emailForm.onsubmit=async event=>{event.preventDefault();save.disabled=true;try{const r=await api('/api/profile/email-change',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(emailForm)))});emailForm.reset();data=r.profile;toast(r.message);render();}catch(e){error.textContent=e.message;}finally{save.disabled=false;}};card.append(emailForm);
  card.append(el('p',{class:'mail-notice',text:'Entrega de códigos ainda não habilitada. Nenhum e-mail é enviado nesta etapa. O endereço atual é preservado.'}));
  if(data.pending_email){const pending=el('div',{class:'pending-email'},[el('strong',{text:'Confirmação pendente'}),el('p',{text:data.pending_email.address}),el('small',{text:'Válida até '+new Date(data.pending_email.expires*1000).toLocaleString('pt-BR')})]);
   const f=el('form',{class:'account-form'});input(f,'Código recebido','token').required=true;const err=el('p',{class:'form-error',role:'alert'});f.append(err,el('button',{type:'submit',class:'button primary',text:'Confirmar novo endereço'}));f.onsubmit=async e=>{e.preventDefault();try{const r=await api('/api/profile/email-change/confirm',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(f)))});data=r.profile;render();toast(r.message);}catch(x){err.textContent=x.message;}};
   pending.append(f,btn('Cancelar solicitação',async()=>{try{const r=await api('/api/profile/email-change',{method:'DELETE'});data=r.profile;render();toast(r.message);}catch(e){toast(e.message,true);}}));card.append(pending);}
  const prefs=section('Preferências de notificações','Você mantém o controle dos alertas por e-mail.','bell'),form=el('form',{id:'profile-preferences-form',class:'account-form'});
  prefs.append(el('div',{class:'always-on'},[iconSvg('check'),el('div',{},[el('strong',{text:'Notificações internas — Sempre ativas'}),el('p',{class:'muted',text:'Avisos operacionais gerais para contas ativas. Informações restritas continuam protegidas.'})])]));
  const label=el('label',{class:'switch-row'}),toggle=el('input',{type:'checkbox',name:'email_alerts'});toggle.checked=Boolean(data.email_alerts);toggle.disabled=!data.verified&&!data.email_alerts;label.append(toggle,document.createTextNode('Receber notificações por e-mail'));form.append(label);
  const error2=el('p',{class:'form-error',role:'alert'});form.append(el('p',{class:'muted',text:'Resumo diário previsto para 09:00 · America/Sao_Paulo. O envio operacional ainda não está ativo.'}),error2,el('button',{type:'submit',class:'button primary',text:'Salvar preferências'}));
  form.onsubmit=async e=>{e.preventDefault();try{const values={appearance:DashboardPreferences.get()};if(toggle.checked!==Boolean(data.email_alerts))values.email_alerts=toggle.checked;await api('/api/profile',{method:'PUT',body:JSON.stringify(values)});data.email_alerts=toggle.checked;toggle.disabled=!data.verified&&!data.email_alerts;rememberForm(form);toast('Preferências salvas.');}catch(x){error2.textContent=x.message;}};
  if(!data.verified)form.append(el('small',{class:'muted',text:'Confirme o endereço para habilitar essa opção. A confirmação não ativa e-mails automaticamente.'}));prefs.append(form);wrapper.append(card,prefs);return wrapper;
 }
 let activitySequence=0,activityPage=1,activityTimer;
 let activityLayoutObserver,activityLayoutFrame,revealActivities=false;
 function fitActivities(){
  cancelAnimationFrame(activityLayoutFrame);
  activityLayoutFrame=requestAnimationFrame(()=>{
   if(tab!=='activities')return;
   const main=document.querySelector('main'),list=document.querySelector('#profile-activity-results');if(!main||!list)return;
   const items=Array.from(list.querySelectorAll('.activity-item')),style=getComputedStyle(list),card=list.closest('.activity-card'),mainStyle=getComputedStyle(main);
   const rowHeight=Math.max(0,...items.slice(0,5).map(row=>row.getBoundingClientRect().height))||parseFloat(style.lineHeight)||1;
   const controls=card.getBoundingClientRect().height-list.getBoundingClientRect().height;
   const reserved=(document.querySelector('.page-chrome')?.getBoundingClientRect().height||0)+(document.querySelector('.profile-tabs')?.getBoundingClientRect().height||0)+(parseFloat(mainStyle.rowGap)||0)*2+(parseFloat(mainStyle.paddingBottom)||0);
   const rows=Math.min(items.length,5,Math.max(1,Math.floor((innerHeight-controls-reserved)/rowHeight)));
   const minimum=Math.ceil(Math.max(innerHeight,main.getBoundingClientRect().height-list.getBoundingClientRect().height+rowHeight*rows+parseFloat(style.paddingTop)+parseFloat(style.paddingBottom)));
   const value=minimum+'px',resized=main.style.getPropertyValue('--activities-min-height')!==value;
   if(resized)main.style.setProperty('--activities-min-height',value);
   if(revealActivities&&list.getAttribute('aria-busy')!=='true'){if(resized)fitActivities();else{revealActivities=false;card.scrollIntoView?.({block:'end'});}}
  });
 }
 window.addEventListener('resize',fitActivities);
 async function loadActivities(){
  const target=document.querySelector('#profile-activity-results'),footer=document.querySelector('#profile-activity-pagination');if(!target||!footer)return;const sequence=++activitySequence;
  const query=document.querySelector('#profile-activity-search').value,operation=document.querySelector('#profile-activity-filter').value;
  target.setAttribute('aria-busy','true');try{const r=await api('/api/profile/activities?'+new URLSearchParams({q:query,operation,page:activityPage}));if(sequence!==activitySequence)return;target.replaceChildren();
   if(!r.activities.length)target.append(el('div',{class:'activity-empty'},[iconSvg('vencimentos'),el('h3',{text:'Nenhuma atividade por aqui'}),el('p',{class:'muted',text:'As operações concluídas da sua conta aparecerão aqui por 30 dias.'})]));
   for(const item of r.activities){const icon={create:'plus',update:'edit',delete:'trash'}[item.operation];target.append(el('article',{class:'activity-item'},[el('span',{class:'profile-symbol'},[iconSvg(icon)]),el('div',{},[el('strong',{text:item.summary}),el('span',{class:'muted',text:item.record_code})]),el('time',{datetime:new Date(item.occurred*1000).toISOString(),text:new Date(item.occurred*1000).toLocaleString('pt-BR')})]));}
   const prev=btn('Anterior',()=>{activityPage--;loadActivities();}),next=btn('Próxima',()=>{activityPage++;loadActivities();});prev.disabled=activityPage<=1;next.disabled=activityPage*20>=r.total;footer.replaceChildren(el('span',{text:r.total+' atividades · página '+activityPage}),prev,next);target.scrollTop=0;
  }catch(e){if(sequence===activitySequence){target.replaceChildren(el('p',{class:'form-error',text:e.message}));footer.replaceChildren();}}finally{if(sequence===activitySequence){target.removeAttribute('aria-busy');fitActivities();}}
 }
 function activitiesPanel(){const s=section('Suas atividades','Operações concluídas pela sua conta nos últimos 30 dias.','vencimentos'),filters=el('div',{class:'activity-filters'}),search=el('input',{type:'search',id:'profile-activity-search',placeholder:'Pesquisar por código ou descrição','aria-label':'Pesquisar atividades'}),select=el('select',{id:'profile-activity-filter','aria-label':'Tipo de atividade'});for(const [v,t] of [['','Todas'],['create','Cadastros'],['update','Edições'],['delete','Exclusões']])select.append(el('option',{value:v,text:t}));search.oninput=()=>{clearTimeout(activityTimer);activityPage=1;activityTimer=setTimeout(loadActivities,250);};select.onchange=()=>{activityPage=1;loadActivities();};filters.append(search,select);s.classList.add('activity-card');s.append(filters,el('div',{id:'profile-activity-results',class:'record-scroll-region',tabindex:'0',role:'region','aria-label':'Histórico de atividades','aria-live':'polite'}),el('div',{id:'profile-activity-pagination',class:'activity-pagination','aria-label':'Paginação de atividades'}));return s;}
 function choosePhoto(){const file=el('input',{type:'file',accept:'image/jpeg,image/png,image/webp'});file.onchange=()=>{const photo=file.files[0];if(!photo)return;if(photo.size>5*1024*1024){toast('A foto deve ter no máximo 5 MB.',true);return;}const url=URL.createObjectURL(photo),box=el('div',{class:'photo-preview'}),preview=el('img',{src:url,alt:'Prévia da nova foto'}),error=el('p',{class:'form-error',role:'alert'}),confirm=btn('Confirmar foto',async()=>{confirm.disabled=true;try{const form=new FormData();form.append('photo',photo);const response=await fetch('/api/profile/avatar',{method:'POST',headers:{'X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content},body:form});const result=await response.json();if(!response.ok)throw Error(result.error||'Não foi possível salvar a foto.');data.avatar_url=result.profile.avatar_url;syncIdentity();closeModal();toast(result.message);}catch(e){error.textContent=e.message;}finally{confirm.disabled=false;}},'primary');box.append(preview,error,el('div',{class:'form-actions'},[btn('Cancelar',closeModal),confirm]));openModal('Prévia da foto de perfil',box);modal.addEventListener('close',()=>URL.revokeObjectURL(url),{once:true});};file.click();}
 function render(){
  content.className='premium-profile';content.replaceChildren();editing=false;accountForm=securityForm=emailForm=null;trackedForms=new Map();rememberAccount();
  const hero=el('section',{class:'profile-hero'}),photo=el('div',{'data-account-avatar':'','aria-label':'Foto de perfil'});avatar(photo,'avatar-hero');
  const identity=el('div',{class:'profile-hero-identity'},[el('h2',{'data-profile-name':'',text:data.display_name||data.user_id}),el('div',{class:'identity-badges'},[el('span',{'data-profile-login':'',text:'ID: '+data.user_id}),el('span',{text:roles[data.role]||data.role},[iconSvg('shield')])])]);
  if(data.created){const date=new Date(data.created);if(!isNaN(date))identity.append(el('p',{text:'Membro do DashboardOS desde '+date.toLocaleDateString('pt-BR')}));}
  hero.append(photo,identity);content.append(hero);
  if(data.profile_ready===false){content.append(el('p',{class:'mail-notice',text:'Atualização do perfil pendente. Consulte o procedimento migrar-perfil antes de editar.'}));syncIdentity();return;}
  const tabs=el('div',{class:'profile-tabs',role:'tablist','aria-label':'Seções do perfil'}),panels=el('div',{class:'profile-panels'});
  for(const [key,label,icon,build] of [['account','Dados da conta','user',accountPanel],['security','Segurança','shield',securityPanel],['email','E-mail e notificações','mail',emailPanel],['preferences','Preferências','settings',()=>buildPreferencesPanel(true)],['activities','Atividades','vencimentos',activitiesPanel]]){
   const b=btn(label,()=>switchTab(key),'secondary',icon);b.id='profile-tab-'+key;b.dataset.profileTab=key;b.setAttribute('role','tab');b.setAttribute('aria-controls','profile-panel-'+key);b.setAttribute('aria-selected',String(tab===key));b.tabIndex=tab===key?0:-1;
   b.onkeydown=e=>{const keys=['account','security','email','preferences','activities'];let i=keys.indexOf(key);if(['ArrowRight','ArrowLeft','Home','End'].includes(e.key)){e.preventDefault();i=e.key==='Home'?0:e.key==='End'?keys.length-1:(i+(e.key==='ArrowRight'?1:keys.length-1))%keys.length;switchTab(keys[i]).then(()=>document.querySelector('#profile-tab-'+tab)?.focus());}};
   tabs.append(b);const p=el('div',{id:'profile-panel-'+key,role:'tabpanel','aria-labelledby':b.id,'data-profile-panel':key});p.hidden=tab!==key;p.append(build());panels.append(p);
  }
  content.append(tabs,panels);for(const form of panels.querySelectorAll('form'))if(form!==accountForm)trackForm(form);syncIdentity();if(tab==='activities')loadActivities();
  activityLayoutObserver?.disconnect();
  if(typeof ResizeObserver==='function'){
   activityLayoutObserver=new ResizeObserver(fitActivities);
   for(const node of [document.querySelector('main'),hero,tabs,panels.querySelector('.activity-filters'),panels.querySelector('.activity-card .profile-card-heading'),panels.querySelector('#profile-activity-pagination')])if(node)activityLayoutObserver.observe(node);
  }
 }
 document.querySelector('#help-button')?.addEventListener('click',()=>{const box=el('div',{class:'help-content'});box.append(el('p',{text:'Explore os módulos pelo menu. Administradores podem cadastrar e editar registros; o modo visitante permite somente leitura.'}),el('p',{text:'Para ajuda com acesso, permissões ou dados, entre em contato com o administrador responsável pelo seu DashboardOS.'}),el('p',{class:'muted',text:'DashboardOS '+document.body.dataset.version+' · Nenhum canal externo é acionado.'}));openModal('Ajuda e suporte',box);});
 if(document.body.dataset.role==='guest')return;
 window.addEventListener('beforeunload',event=>{if(!acceptedNavigation&&changed()){event.preventDefault();event.returnValue='';}});
 document.addEventListener('click',async event=>{const a=event.target.closest('a[href]');if(!onProfile||!a||acceptedNavigation||!changed()||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey||a.target==='_blank')return;event.preventDefault();if(await askDiscard()){discard();acceptedNavigation=true;location.assign(a.href);}},true);
 document.addEventListener('submit',async event=>{if(!onProfile||acceptedNavigation||!event.target.closest('.session-actions')||!changed())return;event.preventDefault();if(await askDiscard()){discard();acceptedNavigation=true;event.target.requestSubmit();}},true);
 api('/api/profile').then(value=>{if(!value)return;data=value;if(onProfile)render();else syncIdentity();}).catch(error=>{if(onProfile)content.replaceChildren(el('p',{class:'form-error',text:error.message}));});
 window.DashboardProfile={hasUnsavedChanges:changed,selectTab:switchTab};
})();
