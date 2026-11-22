/* Standalone P5-A UI: no operational endpoints, external scripts or timers. */
(()=>{
 if(!document.body.dataset.user)return;
 const csrf=document.querySelector('meta[name="csrf-token"]').content;
 const text=(tag,value,cls)=>{const n=document.createElement(tag);n.textContent=value;if(cls)n.className=cls;return n;};
 const message=document.querySelector('#message');let lastOperation,lastStatus,busy=false;
 const labels={status_changed:'Status alterado',band_changed:'Faixa de prazo alterada',date_changed:'Prazo alterado',seven_day_reminder:'Lembrete de renovação · 7 dias',monitoring_ended:'Acompanhamento encerrado',reactivated:'Acompanhamento retomado'};
 const modules={OrdensServico:'Ordens de serviço',Acessos:'Acessos',Renovacoes:'Renovações'};
 const readableBody=value=>Object.entries({...labels,...modules}).reduce((body,[key,label])=>body.replaceAll(key,label),value);
 async function api(path,data){const r=await fetch('/demo/api/'+path,{method:data===undefined?'GET':'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':csrf},...(data===undefined?{}:{body:JSON.stringify(data)})});const value=await r.json();if(!r.ok)throw Error(value.error||'Não foi possível concluir.');return value;}
 function empty(node,label){node.replaceChildren(text('div',label,'empty'));}
 function fillRecords(node,items,render,label){node.replaceChildren();if(!items.length)empty(node,label);else for(const item of items)node.append(render(item));}
 async function refresh(){
  const s=await api('state');document.querySelector('#clock').textContent=new Date(s.clock).toLocaleString('pt-BR',{timeZone:'America/Sao_Paulo'});
  document.querySelector('#notices-count').textContent=s.notices.length+' aviso(s)';
  fillRecords(document.querySelector('#notices'),s.notices,item=>{const n=text('article','','record');n.append(text('strong',(modules[item.module]||item.module)+' · '+item.code),text('p',item.reasons.map(r=>labels[r]||r).join(' · ')),text('small',item.status+' · '+new Date(item.occurred).toLocaleString('pt-BR',{timeZone:'America/Sao_Paulo'})));return n;},'Nenhum aviso autorizado e vigente para esta conta.');
  fillRecords(document.querySelector('#outbox'),s.outbox,item=>{const n=text('article','','record');n.append(text('strong',item.day+' · '+({prepared:'Preparado',simulated:'Entrega simulada',cancelled:'Cancelado na revalidação'}[item.status]||item.status)),text('pre',readableBody(item.body||'Aguardando simulação; permissões serão revalidadas.')));return n;},'Nenhum resumo preparado para esta conta.');
  if(!s.order)return;
  document.querySelector('#operations').textContent=s.operations;document.querySelector('#events').textContent=s.events;document.querySelector('#digests-count').textContent=s.digests.length;
  if(!lastOperation)document.querySelector('#order-status').value=s.order.status==='Pendente'?'Em andamento':s.order.status==='Em andamento'?'Concluída':'Pendente';
  document.querySelector('#receipt').textContent=s.last_operation?'Último recibo: '+s.last_operation+' · '+(s.recovery?.status||'confirmado'):'Primeiro snapshot estabelecido sem eventos retroativos.';
  const users=document.querySelector('#users');users.replaceChildren();for(const u of s.users){const n=text('article','','user-card');n.append(text('strong',u.user_id),text('p',(u.revoked?'Acesso revogado':u.user_id==='bob'?'Outra equipe':u.user_id==='somente-email'?'Autorização só para e-mail':'Conta fictícia')+' · '+(u.verified?'E-mail verificado':'Não verificado')+' · '+(u.email_alerts?'Com consentimento':'Sem consentimento')));if(u.user_id!=='root'){const row=text('div','','actions wrap');for(const [action,label] of [['revoke','Revogar'],['optout','Retirar consentimento'],['unverify','Invalidar verificação']]){const b=text('button',label);b.disabled=action==='revoke'?Boolean(u.revoked):action==='optout'?!u.email_alerts:!u.verified;b.onclick=()=>act('restrict',{uid:u.user_id,action});row.append(b);}n.append(row);}users.append(n);}
  const evidence=document.querySelector('#evidence');evidence.replaceChildren(text('p','Mensagens legadas: '+s.legacy.length+' · todas pendentes, sem tentativas. O fluxo novo não lê essa fila.'));const pre=text('pre',JSON.stringify({recovery:s.recovery,legacy:s.legacy,digests:s.digests},null,2));evidence.append(pre);
 }
 async function act(path,data={}){if(busy)return;busy=true;document.body.classList.add('busy');try{const r=await api(path,data);message.textContent=r.message|| (r.replayed?'Operação repetida: mesmo recibo, sem duplicação.':'Operação coordenada concluída; Central atualizada com os eventos aplicáveis.');message.className='success';await refresh();return r;}catch(e){message.textContent=e.message;message.className='error';}finally{busy=false;document.body.classList.remove('busy');}}
 document.querySelector('#refresh').onclick=()=>refresh().catch(e=>{message.textContent=e.message;message.className='error';});
 const form=document.querySelector('#order-form');if(form){form.onsubmit=async event=>{event.preventDefault();if(busy)return;lastOperation=crypto.randomUUID();lastStatus=document.querySelector('#order-status').value;document.querySelector('#replay').disabled=false;await act('order',{operation_id:lastOperation,status:lastStatus});};document.querySelector('#replay').onclick=()=>act('order',{operation_id:lastOperation,status:lastStatus});for(const b of document.querySelectorAll('[data-clock]'))b.onclick=()=>act('clock',{command:b.dataset.clock});for(const key of ['recover','compose','deliver'])document.querySelector('#'+key).onclick=()=>act(key);}
 refresh().catch(e=>{message.textContent=e.message+' Use Retomar para continuar uma operação interrompida.';message.className='error';});
})();
