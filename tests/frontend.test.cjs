// Testes de eventos/DOM. jsdom não renderiza CSS, Plotly ou janelas reais.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {JSDOM,VirtualConsole}=require('jsdom');
const root=path.resolve(__dirname,'..');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const scripts=['preferences.js','icons.js','modals.js','charts.js','filters.js','dashboard.js','app.js','settings.js'];

async function setup(t,page,options={}){
 const fixture=page+(options.guest?'-guest':'');
 const html=fs.readFileSync(path.join(__dirname,'fixtures',fixture+'.html'),'utf8');
 const data=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures',fixture+'.json'),'utf8'));
 const errors=[],requests=[],plots=[],purged=[],downloads=[],navigationClicks=[];
 const virtualConsole=new VirtualConsole();virtualConsole.on('jsdomError',error=>errors.push(error.message));
 const dom=new JSDOM(html,{url:'http://localhost/'+page,runScripts:'outside-only',pretendToBeVisual:true,virtualConsole});
 const w=dom.window,doc=w.document,observers=[];
 if(options.userKey)doc.documentElement.dataset.userKey=options.userKey;
 if(options.guest){doc.body.dataset.role='guest';data.user={role:'guest',id:'Visitante'};}
 if(options.preferences)w.localStorage.setItem('DashboardOS_2.0:appearance:v1:'+doc.documentElement.dataset.userKey,JSON.stringify(options.preferences));
 const mediaListeners={};
 const mediaState={dark:Boolean(options.systemDark),motion:!options.animate};
 w.matchMedia=query=>({get matches(){return query.includes('reduced-motion')?mediaState.motion:mediaState.dark;},addEventListener:(name,callback)=>mediaListeners[query]=callback});
 const harness={dom,w,doc,data,errors,requests,plots,purged,downloads,navigationClicks,networkError:false,exportFailure:false,deleteFailure:false};
 harness.mediaListeners=mediaListeners;
 harness.mediaState=mediaState;
 // jsdom não implementa navegação. Os destinos são verificados pela suíte Flask.
 doc.addEventListener('click',event=>{const link=event.target.closest('a');if(link){navigationClicks.push(link.getAttribute('href'));event.preventDefault();}},true);
 t.after(()=>{dom.window.close();assert.deepEqual(errors,[],'Nenhum erro JavaScript deve ficar sem tratamento.');});
 w.structuredClone=structuredClone;
 w.requestAnimationFrame=fn=>w.setTimeout(()=>fn(Date.now()),0);
 w.ResizeObserver=class{constructor(callback){this.callback=callback;this.targets=new Set();observers.push(this);}observe(node){this.targets.add(node);}unobserve(node){this.targets.delete(node);}};
 w.Element.prototype.getBoundingClientRect=function(){return this.__rect||{x:0,y:0,left:0,top:0,right:600,bottom:180,width:600,height:180};};
 w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
 w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');w.setTimeout(()=>this.dispatchEvent(new w.Event('close')),0);};
 w.HTMLAnchorElement.prototype.click=function(){downloads.push({href:this.href,download:this.download});};
 w.URL.createObjectURL=()=> 'blob:dashboardos-test';w.URL.revokeObjectURL=()=>{};
 w.Plotly={react:async(node,traces,layout,config)=>{node.data=traces;node.layout=layout;plots.push({node,traces,layout,config});},purge:node=>{purged.push(node);delete node.data;delete node.layout;}};
 let releaseInitial;const initialGate=options.deferInitial?new Promise(resolve=>releaseInitial=resolve):Promise.resolve();
 harness.releaseInitial=releaseInitial;
 const result=(body,status=200)=>({ok:status>=200&&status<300,status,json:async()=>structuredClone(body),blob:async()=>new w.Blob(['xlsx-test'])});
 w.fetch=async(url,config={})=>{
  requests.push({url:String(url),...config});
  if(harness.networkError)throw Error('offline');
  if(String(url).startsWith('/api/export/'))return harness.exportFailure?result({error:'Falha de exportação'},503):result({});
  if(String(url).startsWith('/api/data/')){await initialGate;return result(data);}
  if(String(url).startsWith('/api/records/')){
   const parts=String(url).split('/'),code=parts[4];
   if(config.method==='DELETE'){
    if(harness.deleteFailure)return result({error:'Registro relacionado'},400);
    data.rows=data.rows.filter(row=>row.codigo!==code);
   }else{
    const row=JSON.parse(config.body);row.codigo=code||'NOVO0001';
    const index=data.rows.findIndex(r=>r.codigo===code);
    if(index<0)data.rows.push(row);else data.rows[index]={...data.rows[index],...row};
   }
   return result({message:'Registro salvo com sucesso.',codigo:code||'NOVO0001'});
  }
  throw Error('Rota inesperada: '+url);
 };
 harness.run=source=>vm.runInContext(source,dom.getInternalVMContext());
 for(const file of scripts)harness.run(fs.readFileSync(path.join(root,'static/js',file),'utf8'));
 harness.flush=()=>sleep(25);
 harness.click=selector=>{const node=doc.querySelector(selector);assert.ok(node,selector);node.click();return node;};
 harness.close=async()=>{harness.click('#modal-close');await harness.flush();assert.equal(doc.querySelector('#modal').open,false);};
 harness.resize=node=>{for(const observer of observers)if(observer.targets.has(node))observer.callback([{target:node}]);};
 if(!options.deferInitial)await harness.flush();
 return harness;
}

test('carregamento protege os controles; falha de rede permite tentar Atualizar',async t=>{
 const h=await setup(t,'funcionarios',{deferInitial:true});
 for(const id of ['filters-button','export','new','search','page-size'])assert.equal(h.doc.getElementById(id).disabled,true,id);
 h.click('#filters-button');assert.equal(h.doc.querySelector('#modal').open,false);
 h.releaseInitial();await h.flush();assert.equal(h.doc.querySelector('#filters-button').disabled,false);
 h.networkError=true;h.click('#refresh');await h.flush();
 assert.match(h.doc.querySelector('#toast').textContent,/conectar/);assert.equal(h.doc.querySelector('#refresh').disabled,false);
 h.networkError=false;h.click('#refresh');await h.flush();assert.match(h.doc.querySelector('#updated').textContent,/Atualizado/);
});

for(const page of ['dashboard','funcionarios','equipes','ordens-servico','acessos','vencimentos','renovacoes','relatorios']){
 test(page+': menu, atualizar, filtros, aplicar, limpar, cancelar, exportar',async t=>{
  const h=await setup(t,page),doc=h.doc;
  assert.equal(h.requests[0].url,'/api/data/'+page+'?');
  assert.ok(doc.querySelector('#sidebar #menu-toggle'));assert.equal(doc.querySelector('main #menu-toggle'),null);
  assert.equal(doc.querySelectorAll('nav a').length,8);
  assert.equal(doc.querySelectorAll('a button,a form,a [data-chart],a main,a dialog').length,0,'Links do menu precisam terminar antes do conteúdo.');
  for(const a of doc.querySelectorAll('nav a'))assert.match(a.getAttribute('href'),/^\/[a-z-]+$/);
  h.click('#menu-toggle');assert.equal(doc.querySelector('.shell').classList.contains('collapsed'),true);
  assert.equal(doc.querySelector('#menu-toggle').getAttribute('aria-expanded'),'false');h.click('#menu-toggle');
  const before=h.requests.length;h.click('#refresh');await h.flush();assert.equal(h.requests.length,before+1);
  h.click('#filters-button');assert.equal(doc.querySelector('#modal').open,true);
  const select=doc.querySelector('#modal-body select');if(select?.options.length>1)select.selectedIndex=1;
  const field=select?.name,value=select?.value;
  doc.querySelector('#modal form button:not([type="button"])').click();await h.flush();
  assert.equal(doc.querySelector('#modal').open,false);
  if(value)assert.equal(new URL(h.requests.at(-1).url,'http://localhost').searchParams.get(field),value);
  h.click('#filters-button');h.click('#modal .secondary');await h.flush();
  assert.equal(h.requests.at(-1).url,'/api/data/'+page+'?');assert.equal(doc.querySelector('#filter-count').textContent,'');
  h.click('#filters-button');const requests=h.requests.length;await h.close();assert.equal(h.requests.length,requests);
  h.click('#export');await h.flush();assert.equal(h.downloads.at(-1).download,page+'.xlsx');
  h.exportFailure=true;h.click('#export');await h.flush();assert.match(doc.querySelector('#toast').textContent,/Falha de exportação/);
  assert.equal(doc.querySelector('#export').disabled,false);
 });
}

for(const page of ['funcionarios','equipes','ordens-servico','acessos','vencimentos','renovacoes']){
 test(page+': detalhes, pesquisa, ordenação, paginação, edição e exclusão',async t=>{
  const h=await setup(t,page),doc=h.doc,row=h.data.rows[0];
  assert.equal(doc.querySelector('#prev').disabled,true);
  if(h.data.rows.length>10){h.click('#next');assert.match(doc.querySelector('#page-number').textContent,/^2 \/ /);h.click('#prev');}
  else assert.equal(doc.querySelector('#next').disabled,true);
  const size=doc.querySelector('#page-size');size.value='20';size.dispatchEvent(new h.w.Event('change'));assert.equal(doc.querySelectorAll('#table-body tr').length,Math.min(20,h.data.rows.length));
  h.click('#table-head button');assert.equal(doc.querySelector('#table-head th').getAttribute('aria-sort'),'descending');h.click('#table-head button');
  const search=doc.querySelector('#search');search.value=row.codigo;search.dispatchEvent(new h.w.Event('input'));assert.equal(doc.querySelectorAll('#table-body tr').length,1);
  h.click('#table-body .row-actions button');assert.equal(doc.querySelector('#modal-title').textContent,'Detalhes · '+row.codigo);await h.close();
  h.click('#table-body .row-actions button:nth-child(2)');
  const input=doc.querySelector('#modal-body [name="observacoes"],#modal-body [name="nome"],#modal-body [name="descricao"],#modal-body [name="sistema"]');
  input.value='Alterado apenas no DOM de teste';h.click('#modal-body button[type="submit"]');await h.flush();
  const put=h.requests.find(r=>r.method==='PUT');assert.ok(put);assert.ok(put.headers['X-CSRF-Token']);assert.match(put.body,/Alterado apenas no DOM/);
  h.click('#table-body .row-actions button:nth-child(3)');const count=h.requests.length;h.click('#modal .secondary');await h.flush();assert.equal(h.requests.length,count);
  h.deleteFailure=true;h.click('#table-body .row-actions button:nth-child(3)');h.click('#modal .danger');await h.flush();
  assert.match(doc.querySelector('.form-error').textContent,/relacionado/);assert.equal(doc.querySelector('#modal').open,true);
  h.deleteFailure=false;h.click('#modal .danger');await h.flush();assert.equal(doc.querySelector('#modal').open,false);
  assert.ok(h.requests.some(r=>r.method==='DELETE'));assert.match(doc.querySelector('#table-body').textContent,/Nenhum registro/);
 });
 if(page!=='vencimentos')test(page+': cadastrar e cancelar cadastro',async t=>{
  const h=await setup(t,page),doc=h.doc,row=h.data.rows[0];
  h.click('#new');h.click('#modal .secondary');await h.flush();assert.equal(h.requests.some(r=>r.method==='POST'),false);
  h.click('#new');for(const input of doc.querySelectorAll('#modal-body [name]'))input.value=row[input.name]||'';
  h.click('#modal-body button[type="submit"]');await h.flush();
  const post=h.requests.find(r=>r.method==='POST');assert.ok(post);assert.equal(post.url,'/api/records/'+h.data.sheet);assert.equal(doc.querySelector('#modal').open,false);
 });
}

test('gráficos: cartão vazio, teclado, dimensões, reabertura, Escape e clique externo',async t=>{
 const h=await setup(t,'dashboard'),doc=h.doc;
 for(const plot of h.plots){assert.equal(plot.layout.width,600);assert.equal(plot.layout.height,180);assert.equal(plot.layout.dragmode,false);assert.equal(plot.layout.xaxis.fixedrange,true);assert.equal(plot.config.scrollZoom,false);assert.equal(plot.config.displayModeBar,false);assert.equal(plot.config.doubleClick,false);}
 for(const key of ['teams','trend','donut']){
  const card=doc.querySelector('[data-chart="'+key+'"]');card.focus();card.click();await h.flush();
  assert.equal(doc.querySelector('#modal').open,true);
  const spec=h.data.charts[key];assert.deepEqual(h.plots.at(-1).traces,spec.data);
  doc.querySelector('#modal').dispatchEvent(new h.w.Event('cancel',{cancelable:true}));await h.flush();
  assert.equal(doc.querySelector('#modal').open,false);assert.equal(doc.activeElement,card);
  card.dispatchEvent(new h.w.KeyboardEvent('keydown',{key:'Enter',bubbles:true}));await h.flush();await h.close();
 }
 const chart=doc.querySelector('#chart-teams');chart.__rect={width:380,height:220};h.resize(chart);await h.flush();
 assert.equal(chart.layout.width,380);assert.equal(chart.layout.height,220);
 Object.defineProperty(chart,'clientWidth',{value:400,configurable:true});Object.defineProperty(chart,'clientHeight',{value:240,configurable:true});
 h.resize(chart);await h.flush();assert.equal(chart.layout.width,400);assert.equal(chart.layout.height,240,'A animação não deve alterar as medidas finais do gráfico.');
 h.click('[data-chart="teams"]');await h.flush();
 const old=doc.querySelector('#modal .plot');h.click('#modal-close');
 h.click('[data-chart="trend"]');await h.flush();
 const current=doc.querySelector('#modal .plot');assert.ok(current.data);assert.ok(h.purged.includes(old));assert.equal(h.purged.includes(current),false);
 doc.querySelector('#modal').dispatchEvent(new h.w.MouseEvent('click',{clientX:-10,clientY:-10,bubbles:true}));await h.flush();assert.equal(doc.querySelector('#modal').open,false);
 assert.deepEqual(h.navigationClicks,[],'Cartões e botões de fechar não devem navegar.');
});

test('filtros recusam período invertido sem enviar pedido',async t=>{
 const h=await setup(t,'ordens-servico'),doc=h.doc;h.click('#filters-button');
 doc.querySelector('[name="inicio"]').value='2026-10-30';doc.querySelector('[name="fim"]').value='2026-10-01';
 const before=h.requests.length;doc.querySelector('#modal form button:not([type="button"])').click();await h.flush();
 assert.equal(h.requests.length,before);assert.match(doc.querySelector('.form-error').textContent,/data final/);
});

test('relatórios: sete opções, gráfico ampliado e exportação do painel',async t=>{
 const h=await setup(t,'relatorios'),doc=h.doc,select=doc.querySelector('#report-type');assert.equal(select.options.length,7);
 for(const option of select.options){select.value=option.value;select.dispatchEvent(new h.w.Event('change'));await h.flush();assert.equal(doc.querySelector('#report-title').textContent,option.value);}
 h.click('#report-chart-card');await h.flush();assert.equal(doc.querySelector('#modal').open,true);await h.close();
 h.click('#report-download');await h.flush();assert.equal(h.downloads.at(-1).download,'relatorios.xlsx');
});

test('configurações: claro, escuro, automático, fontes, densidade e números sem alterar dados',async t=>{
 const h=await setup(t,'dashboard'),doc=h.doc,prefs=h.w.DashboardPreferences,raw=JSON.stringify(h.data);
 assert.equal(doc.documentElement.dataset.theme,'light');assert.equal(prefs.scale(),1.1);
 assert.ok(doc.querySelector('.sidebar-bottom #settings-button'));
 h.click('#settings-button');assert.equal(doc.querySelector('#modal-title').textContent,'Configurações');
 function choose(key,value){const control=doc.querySelector('[data-preference="'+key+'"]');control.value=value;control.dispatchEvent(new h.w.Event('change'));}
 choose('theme','dark');await h.flush();assert.equal(doc.documentElement.dataset.theme,'dark');
 assert.equal(doc.querySelector('#chart-teams').data[0].marker.color,'#82accf');
 choose('theme','auto');h.mediaState.dark=true;h.mediaListeners['(prefers-color-scheme: dark)']();await h.flush();assert.equal(doc.documentElement.dataset.theme,'dark');
 h.mediaState.dark=false;h.mediaListeners['(prefers-color-scheme: dark)']();assert.equal(doc.documentElement.dataset.theme,'light');
 for(const [value,scale] of [['small',1],['default',1.1],['large',1.22],['xlarge',1.35]]){choose('font',value);assert.equal(prefs.scale(),scale);assert.equal(doc.documentElement.style.getPropertyValue('--font-scale'),String(scale));}
 choose('density','compact');assert.equal(doc.documentElement.dataset.density,'compact');
 choose('numbers','compact');assert.match(prefs.formatNumber(1250),/1,25.*mil/);
 choose('numbers','standard');assert.equal(prefs.formatNumber(1250),'1.250');
 assert.equal(JSON.stringify(h.data),raw);
});

test('preferências persistem por usuário e restaurar não toca outras chaves nem faz escrita HTTP',async t=>{
 const h=await setup(t,'funcionarios'),prefs=h.w.DashboardPreferences;
 prefs.set({theme:'dark',font:'large',density:'compact',numbers:'compact',reduceMotion:true});
 const saved=JSON.parse(h.w.localStorage.getItem(prefs.key));assert.equal(saved.theme,'dark');
 assert.deepEqual(Object.keys(saved).sort(),['density','font','numbers','reduceMotion','theme']);
 const reload=await setup(t,'acessos',{preferences:saved});assert.equal(reload.doc.documentElement.dataset.theme,'dark');assert.equal(reload.w.DashboardPreferences.scale(),1.22);
 const other=await setup(t,'funcionarios',{userKey:'outro-usuario'});assert.notEqual(other.w.DashboardPreferences.key,prefs.key);assert.equal(other.doc.documentElement.dataset.theme,'light');
 h.w.localStorage.setItem('outra-aplicacao','preservar');const before=h.requests.length;
 h.click('#settings-button');h.click('.settings-panel .form-actions button');
 assert.equal(prefs.get().theme,'light');assert.equal(prefs.scale(),1.1);assert.equal(h.w.localStorage.getItem(prefs.key),null);
 assert.equal(h.w.localStorage.getItem('outra-aplicacao'),'preservar');assert.equal(h.requests.length,before);
});

test('animação fecha sem bloquear a reabertura; preferência e sistema reduzem movimento',async t=>{
 const h=await setup(t,'dashboard',{animate:true}),doc=h.doc,prefs=h.w.DashboardPreferences;
 h.click('[data-chart="teams"]');await h.flush();h.click('#modal-close');
 assert.equal(doc.querySelector('#modal').open,true);assert.ok(doc.querySelector('#modal').classList.contains('is-closing'));
 h.click('[data-chart="trend"]');await sleep(210);assert.equal(doc.querySelector('#modal').open,true);assert.ok(doc.querySelector('#modal .plot').data);
 prefs.set({reduceMotion:true});h.click('#modal-close');await h.flush();assert.equal(doc.querySelector('#modal').open,false);
 prefs.set({reduceMotion:false});h.mediaState.motion=true;h.mediaListeners['(prefers-reduced-motion: reduce)']();assert.equal(prefs.reduced(),true);
});

for(const page of ['funcionarios','equipes','ordens-servico','acessos','vencimentos','renovacoes'])test(page+': visitante vê ações desabilitadas e não abre formulário',async t=>{
 const h=await setup(t,page,{guest:true}),doc=h.doc;
 assert.equal(doc.body.dataset.role,'guest');assert.match(doc.querySelector('.session-actions').textContent,/Fazer login/);
 if(page!=='vencimentos'){assert.equal(doc.querySelector('#new').hidden,false);assert.equal(doc.querySelector('#new').disabled,true);assert.equal(doc.querySelector('#new').title,'Disponível apenas para administradores');h.click('#new');assert.equal(doc.querySelector('#modal').open,false);}
 for(const selector of ['#table-body .row-actions button:nth-child(2)','#table-body .row-actions button:nth-child(3)']){const button=doc.querySelector(selector);assert.equal(button.disabled,true);assert.equal(button.title,'Disponível apenas para administradores');button.click();assert.equal(doc.querySelector('#modal').open,false);}
 h.run('editRecord(state.rows[0]);deleteRecord(state.rows[0]);');assert.equal(doc.querySelector('#modal').open,false);
 h.click('#table-body .row-actions button');assert.equal(doc.querySelector('#modal').open,true);await h.close();
 h.click('#filters-button');assert.equal(doc.querySelector('#modal').open,true);await h.close();
 assert.equal(h.requests.some(r=>['POST','PUT','DELETE'].includes(r.method)),false);
});

test('visitante mantém gráficos e configurações; sessão oferece somente login e tela inicial',async t=>{
 const h=await setup(t,'dashboard',{guest:true});
 h.click('[data-chart="teams"]');await h.flush();assert.ok(h.doc.querySelector('#modal .plot').data);await h.close();
 h.click('#settings-button');assert.equal(h.doc.querySelector('#modal-title').textContent,'Configurações');
 assert.equal(h.doc.querySelectorAll('.session-actions form').length,2);
 assert.equal(h.doc.querySelectorAll('.session-actions [action="/auth/guest"]').length,0);
});

test('login: mostrar/ocultar senha e estado de carregamento sem salvar credenciais',t=>{
 const dom=new JSDOM(fs.readFileSync(path.join(__dirname,'fixtures/login.html'),'utf8'),{url:'http://localhost/login',runScripts:'outside-only'});
 t.after(()=>dom.window.close());const w=dom.window,doc=w.document;
 vm.runInContext(fs.readFileSync(path.join(root,'static/js/preferences.js'),'utf8'),dom.getInternalVMContext());
 vm.runInContext(fs.readFileSync(path.join(root,'static/js/login.js'),'utf8'),dom.getInternalVMContext());
 doc.querySelector('#toggle-password').click();assert.equal(doc.querySelector('#password').type,'text');
 doc.querySelector('#toggle-password').click();assert.equal(doc.querySelector('#password').type,'password');
 doc.querySelector('#login-form').dispatchEvent(new w.Event('submit',{cancelable:true}));
 assert.match(doc.querySelector('#login-form [type="submit"]').textContent,/Entrando/);
 assert.equal(doc.querySelector('#guest-form [type="submit"]').disabled,true);assert.equal(w.localStorage.length,0);
});
