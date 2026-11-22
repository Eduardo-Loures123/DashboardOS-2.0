/* Text from accounts/events always enters DOM through textContent. */
(()=>{
 const accountPage=['perfil','administracao'].includes(page),content=document.querySelector('#account-content');
 const button=(label,handler,style='secondary')=>{const b=el('button',{type:'button',class:'button '+style,text:label});b.onclick=async()=>{b.disabled=true;try{await handler();}catch(error){toast(error.message,true);}finally{b.disabled=false;}};return b;};
 const field=(form,label,name,value='',type='text',values=null)=>{
  const wrap=el('label',{text:label});let input;
  if(values){input=el('select',{name});for(const [v,t] of values)input.append(el('option',{value:v,text:t}));input.value=value;}
  else if(type==='textarea'){input=el('textarea',{name,maxlength:'5000'});input.value=value;}
  else{input=el('input',{name,type,maxlength:type==='password'?'256':'254'});if(type==='checkbox')input.checked=Boolean(value);else input.value=value;if(type==='password')input.autocomplete='new-password';}
  if(type==='checkbox')wrap.className='switch-row';wrap.append(input);form.append(wrap);return input;
 };
 function submit(form,label,handler){const error=el('p',{class:'form-error',role:'alert'}),b=el('button',{type:'submit',class:'button primary',text:label});form.append(error,el('div',{class:'form-actions'},[b]));form.onsubmit=async event=>{event.preventDefault();b.disabled=true;error.textContent='';try{await handler();}catch(e){error.textContent=e.message;}finally{b.disabled=false;}};}
 const roles=[['user','Usuário'],['admin','Administrador'],['superadmin','Superadministrador']];
 function userForm(user=null){
  const form=el('form',{class:'account-form'});
  if(!user){field(form,'Identificador','user_id').required=true;const pwd=field(form,'Senha inicial (mínimo 12 caracteres)','password','','password');pwd.required=true;pwd.minLength=12;}
  field(form,'Nome de exibição','display_name',user?.display_name||'').required=true;
  field(form,'Permissão','role',user?.role||'user','text',roles);
  if(user)field(form,'Estado da conta','state',user.state,'text',[['active','Ativa'],['blocked','Bloqueada'],['inactive','Desativada']]);
  submit(form,user?'Salvar conta':'Criar conta',async()=>{const values=Object.fromEntries(new FormData(form));const result=await api('/api/admin/users'+(user?'/'+encodeURIComponent(user.user_id):''),{method:user?'PUT':'POST',body:JSON.stringify(values)});closeModal();toast(result.message);await admin();});
  openModal(user?'Editar conta · '+(user.login||user.user_id):'Nova conta',form);
 }
 async function admin(){
  const {users}=await api('/api/admin/users');content.replaceChildren(button('Criar conta',()=>userForm(), 'primary'));
  for(const user of users){const card=el('article',{class:'account-user'});card.append(el('h3',{text:user.display_name||user.user_id}),el('p',{class:'muted',text:user.user_id+' · '+roles.find(r=>r[0]===user.role)?.[1]+' · '+user.state}));
   card.querySelector('p').textContent=(user.login||user.user_id)+' · '+roles.find(r=>r[0]===user.role)?.[1]+' · '+user.state;
   card.append(button('Editar permissões',()=>userForm(user)),button('Redefinir credenciais',()=>{
    const form=el('form');field(form,'Confirme sua senha atual','current_password','','password').required=true;
    submit(form,'Gerar código seguro',async()=>{const result=await api('/api/admin/users/'+encodeURIComponent(user.user_id)+'/reset',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(form)))});const box=el('div');box.append(el('p',{text:result.message}),el('code',{text:result.token}),el('p',{text:'O titular deve abrir /redefinir-senha e inserir o código. Ele não será exibido novamente.'}));openModal('Redefinição de credenciais',box);});openModal('Confirmar identidade',form);
   }));content.append(card);
  }
  const form=el('form',{class:'account-form'});field(form,'Título','title').required=true;field(form,'Mensagem','message','','textarea').required=true;
  const recipients=field(form,'Destinatários (selecione um ou mais)','recipients','*','text',[['*','Todos os usuários ativos'],...users.filter(u=>u.state==='active').map(u=>[u.user_id,u.display_name||u.user_id])]);recipients.multiple=true;
  const send=async()=>{const data=Object.fromEntries(new FormData(form)),selected=Array.from(recipients.selectedOptions,o=>o.value);data.recipients=selected.includes('*')?null:selected;return data;};
  submit(form,'Revisar comunicado',async()=>{const data=await send(),box=el('div');box.append(el('h3',{text:data.title}),el('p',{class:'message-text',text:data.message}),el('p',{text:'Destinatários: '+(data.recipients?.join(', ')||'Todos os usuários ativos')}),button('Confirmar publicação',async()=>{const result=await api('/api/admin/announcements',{method:'POST',body:JSON.stringify({...data,confirmed:true})});closeModal();toast(result.message);await admin();},'primary'));openModal('Prévia do comunicado',box);});
  document.querySelector('#announcement-content').replaceChildren(form);
  const [audit,announcements]=await Promise.all([api('/api/admin/audit'),api('/api/admin/announcements')]);const history=document.querySelector('#admin-history');history.replaceChildren();
  for(const item of announcements.announcements)history.append(el('article',{class:'notification-item'},[el('strong',{text:item.title}),el('p',{class:'message-text',text:item.message}),el('small',{text:item.actor+' · '+new Date(item.occurred).toLocaleString('pt-BR')})]));
  for(const item of audit.audit)history.append(el('p',{class:'audit-row',text:new Date(item.occurred).toLocaleString('pt-BR')+' · '+item.actor+' · '+item.action+' · '+item.target}));
 }
 const bell=document.querySelector('#notifications-button');
 async function updateBell(){if(!bell)return;const data=await api('/api/notifications');document.querySelector('#notifications-count').textContent=String(data.unread);bell.classList.toggle('has-unread',data.unread>0);bell.setAttribute('aria-label',data.unread+' notificações não lidas');return data;}
 async function notifications(){
  let data=await updateBell(),category='all',pageNumber=1,visible=[];const selected=new Set(),size=6,checkboxes=new Map();
  const shell=el('div',{class:'notification-center'}),nav=el('nav',{class:'notification-nav','aria-label':'Situação das notificações'}),main=el('div',{class:'notification-main'}),filters=el('div',{class:'notification-filters'});
  const search=el('input',{type:'search',placeholder:'Buscar notificações…','aria-label':'Buscar notificações'}),period=el('select',{'aria-label':'Período das notificações'});
  for(const [value,label] of [['0','Todo o período'],['1','Hoje'],['7','Últimos 7 dias'],['30','Últimos 30 dias']])period.append(el('option',{value,text:label}));
  const searchWrap=el('label',{class:'notification-search'},[notificationIcon('search'),search]);filters.append(searchWrap,period);
  const toolbar=el('div',{class:'notification-toolbar'}),count=el('strong',{'aria-live':'polite'}),all=el('input',{type:'checkbox','aria-label':'Selecionar todas as notificações desta página'}),allLabel=el('label',{class:'notification-select-all'},[all,document.createTextNode('Selecionar todas')]);
  const list=el('div',{class:'notification-results record-scroll-region',tabindex:'0',role:'region','aria-label':'Lista de notificações','aria-live':'polite'}),footer=el('div',{class:'notification-footer'}),error=el('p',{class:'form-error',role:'alert'});
  const refresh=async()=>{data=await updateBell();selected.clear();render();};
  const run=async(action,ids=null)=>{try{if(ids){for(const id of ids)await api('/api/notifications/'+id,{method:'POST',body:JSON.stringify({action})});}else await api('/api/notifications',{method:'POST',body:JSON.stringify({action})});await refresh();return true;}catch(e){error.textContent=e.message;return false;}};
  const read=button('Marcar como lidas',async()=>{await run('read',selected.size?[...selected]:null);});
  const clear=el('button',{type:'button',class:'button secondary',text:'Limpar central'});
  clear.onclick=()=>openConfirmation({title:'Limpar sua central?',icon:'trash',message:'As notificações sairão da sua central. O histórico e as notificações de outras pessoas serão preservados.',confirmLabel:'Confirmar limpeza',onConfirm:async()=>{if(!await run('delete'))throw Error(error.textContent);}});
  toolbar.append(count,allLabel,read,clear);main.append(filters,toolbar,error,list,footer);shell.append(nav,main);
  const navButtons=[];
  for(const [value,label,icon] of [['all','Todas as notificações','inbox'],['unread','Não lidas','circle'],['read','Lidas','check']]){const b=el('button',{type:'button',class:'notification-category'},[notificationIcon(icon),el('span',{text:label}),el('b')]);b.onclick=()=>{category=value;pageNumber=1;selected.clear();render();};navButtons.push([value,b]);nav.append(b);}
  function filtered(){const query=search.value.trim().toLocaleLowerCase('pt-BR'),days=Number(period.value),today=new Date();today.setHours(0,0,0,0);const since=days===1?today.getTime():Date.now()-days*86400000;return data.notifications.filter(n=>(category==='all'||(category==='read'?!!n.read_at:!n.read_at))&&(!query||(n.title+' '+n.message).toLocaleLowerCase('pt-BR').includes(query))&&(!days||new Date(n.occurred).getTime()>=since));}
  function syncSelection(){
   all.disabled=!visible.length;all.checked=visible.length>0&&visible.every(n=>selected.has(n.id));all.indeterminate=!all.checked&&visible.some(n=>selected.has(n.id));
   const label=selected.size?'Marcar seleção como lida':'Marcar todas como lidas';if(read.textContent!==label)actionLabel(read,label,'check');read.disabled=!data.unread&&!selected.size;
   for(const [id,checkbox] of checkboxes)checkbox.checked=selected.has(id);
  }
  all.onchange=()=>{for(const n of visible)all.checked?selected.add(n.id):selected.delete(n.id);syncSelection();};
  function render(){
   for(const [value,b] of navButtons){b.classList.toggle('active',category===value);b.setAttribute('aria-pressed',String(category===value));const total=data.notifications.filter(n=>value==='all'||(value==='read'?!!n.read_at:!n.read_at)).length;b.querySelector('b').textContent=String(total);}
   const rows=filtered(),pages=Math.max(1,Math.ceil(rows.length/size));pageNumber=Math.min(pageNumber,pages);visible=rows.slice((pageNumber-1)*size,pageNumber*size);
   count.textContent=rows.length+' '+(rows.length===1?'notificação':'notificações');clear.disabled=!data.notifications.length;list.replaceChildren();checkboxes.clear();
   if(!rows.length)list.append(el('div',{class:'notification-empty'},[el('span',{class:'notification-empty-icon'},[notificationIcon('bell')]),el('h3',{text:data.notifications.length?'Nenhum resultado encontrado':'Você está em dia!'}),el('p',{text:data.notifications.length?'Tente outra pesquisa ou ajuste os filtros.':'Nenhuma notificação disponível no momento.'})]));
   for(const n of visible){
    const checkbox=el('input',{type:'checkbox','aria-label':'Selecionar '+n.title});checkbox.checked=selected.has(n.id);checkboxes.set(n.id,checkbox);checkbox.onchange=()=>{checkbox.checked?selected.add(n.id):selected.delete(n.id);syncSelection();};
    const body=el('div',{class:'notification-copy'},[el('strong',{text:n.title}),el('p',{text:n.message})]);
    const actions=el('div',{class:'notification-row-actions'});if(n.link?.startsWith('/')&&!n.link.startsWith('//')&&!n.link.includes('\\'))actions.append(el('a',{href:n.link,text:'Consultar registro'}));
    if(!n.read_at)actions.append(button('Marcar como lida',()=>run('read',[n.id])));body.append(actions);
    const time=el('time',{datetime:n.occurred,text:new Intl.DateTimeFormat('pt-BR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'}).format(new Date(n.occurred))});
    const item=el('article',{class:'notification-row '+(!n.read_at?'unread':'')},[checkbox,el('span',{class:'notification-kind '+(n.kind==='operational'?'operational':'information')},[notificationIcon(n.kind==='operational'?'warning':'info')]),body,time]);if(!n.read_at)item.append(el('span',{class:'notification-unread','aria-label':'Não lida'}));list.append(item);
   }
   footer.replaceChildren(el('span',{text:rows.length?'Exibindo '+((pageNumber-1)*size+1)+' a '+Math.min(pageNumber*size,rows.length)+' de '+rows.length+' notificações':'0 notificações'}));
   if(data.notifications.length===200)footer.append(el('small',{text:'Exibindo até 200 notificações recentes.'}));
   if(pages>1){const pagination=el('div',{class:'notification-pagination'}),previous=button('',()=>{pageNumber--;render();}),next=button('',()=>{pageNumber++;render();});actionLabel(previous,'','left');actionLabel(next,'','right');previous.setAttribute('aria-label','Página anterior');next.setAttribute('aria-label','Próxima página');previous.disabled=pageNumber===1;next.disabled=pageNumber===pages;pagination.append(previous,el('span',{text:pageNumber+' / '+pages}),next);footer.append(pagination);}
   syncSelection();list.scrollTop=0;
  }
  search.oninput=period.onchange=()=>{pageNumber=1;selected.clear();render();};render();openModal('Central de notificações',shell);modal.classList.add('notifications-modal');modal.querySelector('.modal-heading>div').append(el('span',{class:'notification-header-icon','data-modal-icon':'','aria-hidden':'true'},[iconSvg('bell')]),el('p',{class:'notification-description','data-modal-icon':'',text:'Acompanhe avisos, atualizações e atividades do sistema.'}));
 }
 function notificationIcon(name){return iconSvg(name);}
 if(bell){bell.onclick=()=>notifications().catch(error=>toast(error.message,true));updateBell().catch(()=>{document.querySelector('#notifications-count').textContent='—';});document.addEventListener('visibilitychange',()=>{if(!document.hidden)updateBell().catch(()=>{});});setInterval(()=>{if(!document.hidden)updateBell().catch(()=>{});},60000);}
 if(accountPage){document.querySelector('.toolbar').hidden=true;document.querySelector('#updated').textContent='Conta e segurança';if(page==='administracao')admin().catch(error=>content.replaceChildren(el('p',{class:'form-error',text:error.message})));}
})();
