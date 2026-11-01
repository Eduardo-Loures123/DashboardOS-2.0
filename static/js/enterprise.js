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
 async function profile(){
  const data=await api('/api/profile');content.replaceChildren();
  content.append(el('p',{class:'badge',text:roles.find(r=>r[0]===data.role)?.[1]+' · '+data.state}));
  const form=el('form',{class:'account-form'});
  field(form,'Nome de exibição','display_name',data.display_name).required=true;
  field(form,'Identificador de login','user_id',data.user_id).required=true;
  field(form,'E-mail '+(data.verified?'(verificado)':'(não verificado)'),'email',data.email,'email');
  field(form,'Senha atual (para alterações sensíveis)','current_password','','password').autocomplete='current-password';
  field(form,'Nova senha (opcional, mínimo 12 caracteres)','password','','password');
  field(form,'Confirmar nova senha','password_confirmation','','password');
  field(form,'Receber alertas internos','internal_alerts',data.internal_alerts,'checkbox');
  field(form,'Receber alertas por e-mail verificado','email_alerts',data.email_alerts,'checkbox');
  const prefs={...window.DashboardPreferences.get(),...data.appearance};
  field(form,'Tema','theme',prefs.theme,'text',[['light','Claro'],['dark','Escuro'],['auto','Sistema']]);
  field(form,'Tamanho da fonte','font',prefs.font,'text',[['small','Pequena'],['default','Padrão'],['large','Grande'],['xlarge','Extra grande']]);
  submit(form,'Salvar perfil',async()=>{
   const values=Object.fromEntries(new FormData(form));if(values.password!==values.password_confirmation)throw Error('As senhas não coincidem.');
   const appearance={...window.DashboardPreferences.get(),theme:values.theme,font:values.font};
   const result=await api('/api/profile',{method:'PUT',body:JSON.stringify({...values,internal_alerts:form.elements.internal_alerts.checked,email_alerts:form.elements.email_alerts.checked,appearance})});
   window.DashboardPreferences.set(appearance);toast(result.message);if(result.redirect)location.assign(result.redirect);else await profile();
  });content.append(form);
  const verifyForm=el('form',{class:'account-form'});field(verifyForm,'Código recebido por e-mail','token').required=true;
  submit(verifyForm,'Confirmar e-mail',async()=>{const result=await api('/api/profile/verify',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(verifyForm)))});toast(result.message);await profile();});
  content.append(el('h3',{text:'Verificação de e-mail'}),button('Enviar código de confirmação',async()=>toast((await api('/api/profile/verification',{method:'POST',body:'{}'})).message)),verifyForm);
  content.append(el('p',{class:'muted',text:'Criada: '+(data.created?new Date(data.created).toLocaleString('pt-BR'):'Data indisponível na versão anterior')+' · Último acesso: '+(data.last_login?new Date(data.last_login).toLocaleString('pt-BR'):'Não registrado')}));
 }
 function userForm(user=null){
  const form=el('form',{class:'account-form'});
  if(!user){field(form,'Identificador','user_id').required=true;const pwd=field(form,'Senha inicial (mínimo 12 caracteres)','password','','password');pwd.required=true;pwd.minLength=12;}
  field(form,'Nome de exibição','display_name',user?.display_name||'').required=true;
  field(form,'Permissão','role',user?.role||'user','text',roles);
  if(user)field(form,'Estado da conta','state',user.state,'text',[['active','Ativa'],['blocked','Bloqueada'],['inactive','Desativada']]);
  submit(form,user?'Salvar conta':'Criar conta',async()=>{const values=Object.fromEntries(new FormData(form));const result=await api('/api/admin/users'+(user?'/'+encodeURIComponent(user.user_id):''),{method:user?'PUT':'POST',body:JSON.stringify(values)});closeModal();toast(result.message);await admin();});
  openModal(user?'Editar conta · '+user.user_id:'Nova conta',form);
 }
 async function admin(){
  const {users}=await api('/api/admin/users');content.replaceChildren(button('Criar conta',()=>userForm(), 'primary'));
  for(const user of users){const card=el('article',{class:'account-user'});card.append(el('h3',{text:user.display_name||user.user_id}),el('p',{class:'muted',text:user.user_id+' · '+roles.find(r=>r[0]===user.role)?.[1]+' · '+user.state}));
   card.append(button('Editar permissões',()=>userForm(user)),button('Redefinir credenciais',()=>{
    const form=el('form');field(form,'Confirme sua senha atual','current_password','','password').required=true;
    submit(form,'Gerar código seguro',async()=>{const result=await api('/api/admin/users/'+encodeURIComponent(user.user_id)+'/reset',{method:'POST',body:JSON.stringify(Object.fromEntries(new FormData(form)))});const box=el('div');box.append(el('p',{text:result.message}),el('code',{text:result.token}),el('p',{text:'O titular deve abrir /redefinir-senha e inserir o código. Ele não será exibido novamente.'}));openModal('Redefinição de credenciais',box);});openModal('Confirmar identidade',form);
   }));content.append(card);
  }
  const form=el('form',{class:'account-form'});field(form,'Título','title').required=true;field(form,'Mensagem','message','','textarea').required=true;
  const recipients=field(form,'Destinatários (Ctrl/Cmd para selecionar vários)','recipients','*','text',[['*','Todos os usuários ativos'],...users.filter(u=>u.state==='active').map(u=>[u.user_id,u.display_name||u.user_id])]);recipients.multiple=true;
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
  const data=await updateBell(),box=el('div',{class:'notification-list'}),actions=el('div',{class:'notification-actions'});
  const act=async(action,id)=>{await api('/api/notifications'+(id?'/'+id:''),{method:'POST',body:JSON.stringify({action})});await notifications();};
  actions.append(button('Marcar todas como lidas',()=>act('read')),button('Limpar minha central',()=>{const confirm=el('div',{},[el('p',{text:'Limpar as notificações da sua conta? O histórico e os registros originais serão preservados.'}),button('Confirmar limpeza',()=>act('delete'),'danger')]);openModal('Limpar notificações',confirm);}));box.append(actions);
  if(!data.notifications.length)box.append(el('p',{class:'muted',text:'Nenhuma notificação por aqui.'}));
  for(const item of data.notifications){const card=el('article',{class:'notification-item'+(!item.read_at?' unread':'')});card.append(el('strong',{text:item.title}),el('p',{class:'message-text',text:item.message}),el('small',{text:new Date(item.occurred).toLocaleString('pt-BR')}));
   if(item.link?.startsWith('/')&&!item.link.startsWith('//'))card.append(el('a',{href:item.link,class:'button secondary',text:'Consultar registro'}));
   card.append(button('Marcar como lida',()=>act('read',item.id)),button('Excluir',()=>act('delete',item.id)));box.append(card);
  }openModal('Central de notificações',box);
 }
 if(bell){bell.onclick=()=>notifications().catch(error=>toast(error.message,true));updateBell().catch(()=>{document.querySelector('#notifications-count').textContent='—';});document.addEventListener('visibilitychange',()=>{if(!document.hidden)updateBell().catch(()=>{});});setInterval(()=>{if(!document.hidden)updateBell().catch(()=>{});},60000);}
 if(accountPage){document.querySelector('.toolbar').hidden=true;document.querySelector('#updated').textContent='Conta e segurança';const load=page==='perfil'?profile:admin;load().catch(error=>content.replaceChildren(el('p',{class:'form-error',text:error.message})));}
})();
