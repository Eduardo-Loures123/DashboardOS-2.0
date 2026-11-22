// Testes de eventos/DOM. jsdom não renderiza CSS, Plotly ou janelas reais.
const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const {JSDOM,VirtualConsole}=require('jsdom');
const root=path.resolve(__dirname,'..');
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
const scripts=['preferences.js','sidebar.js','icons.js','motion.js','modals.js','charts.js','premium-charts.js','filters.js','dashboard.js','app.js','settings.js','enterprise.js','controls.js','imports.js','profile.js'];

test('notification selection preserves card identity, focus and scroll without requests',async t=>{
 const notifications=Array.from({length:15},(_,i)=>({id:i+1,title:'Aviso '+i,message:'Teste',kind:'operational',link:'/acessos',occurred:new Date().toISOString(),read_at:null}));
 const h=await setup(t,'dashboard',{notifications}),d=h.doc;h.click('#notifications-button');await h.flush();
 const list=d.querySelector('.notification-results'),cards=[...list.children],inputs=[...list.querySelectorAll('input')],all=d.querySelector('.notification-select-all input'),before=h.requests.length;
 list.scrollTop=170;inputs[0].focus();inputs[0].click();
 assert.equal(d.activeElement,inputs[0]);assert.equal(list.scrollTop,170);assert.equal(all.indeterminate,true);assert.equal(h.requests.length,before);
 inputs[1].click();inputs[0].click();all.click();assert.ok(inputs.every(c=>c.checked));all.click();assert.ok(inputs.every(c=>!c.checked));
 assert.equal(list.scrollTop,170);assert.ok(cards.every((card,i)=>list.children[i]===card));assert.equal(h.requests.length,before);
 h.click('.notification-pagination [aria-label="Próxima página"]');
 const search=d.querySelector('.notification-search input');search.value='Aviso 1';search.dispatchEvent(new h.w.Event('input'));
 const filteredCard=list.firstElementChild;list.querySelector('input').click();assert.equal(list.firstElementChild,filteredCard);
});

test('clear confirmation is separate, cancellable and commits once for repeated clicks',async t=>{
 const h=await setup(t,'dashboard',{notifications:[{id:1,title:'Teste',message:'Somente fixture',kind:'operational',occurred:new Date().toISOString(),read_at:null}]}),d=h.doc;
 h.click('#notifications-button');await h.flush();const list=d.querySelector('.notification-results'),card=list.firstElementChild,footer=d.querySelector('.notification-footer');list.scrollTop=110;
 const clear=()=>[...d.querySelectorAll('.notification-toolbar button')].find(b=>b.textContent==='Limpar central').click();
 for(let i=0;i<3;i++){clear();const confirmation=d.querySelector('dialog.confirmation-dialog');assert.ok(confirmation.open);assert.equal(list.contains(confirmation),false);assert.equal(d.querySelector('#modal').open,true);assert.equal(confirmation.querySelector('.confirmation-title svg').getAttribute('viewBox'),'0 0 24 24');[...confirmation.querySelectorAll('button')].find(b=>b.textContent==='Cancelar').click();assert.equal(list.firstElementChild,card);assert.equal(d.querySelector('.notification-footer'),footer);assert.equal(list.scrollTop,110);}
 assert.equal(h.requests.filter(r=>r.method==='POST').length,0);
 clear();const confirm=[...d.querySelectorAll('.confirmation-dialog button')].find(b=>b.textContent==='Confirmar limpeza');confirm.click();confirm.click();await h.flush();
 assert.equal(h.requests.filter(r=>r.method==='POST'&&r.url==='/api/notifications'&&JSON.parse(r.body).action==='delete').length,1);
 assert.equal(d.querySelector('.confirmation-dialog'),null);assert.equal(h.data.notifications.length,0);assert.ok(d.querySelector('.notification-empty'));
});

test('activities keep pagination outside the scroll region through filtering and tab changes',async t=>{
 const activities=Array.from({length:45},(_,i)=>({operation:i%2?'update':'create',summary:'Operacao de teste',record_code:'OS'+String(i+1).padStart(4,'0'),occurred:Date.now()/1000}));
 const h=await setup(t,'perfil',{activities}),d=h.doc;
 h.click('#profile-tab-activities');await h.flush();
 const list=d.querySelector('#profile-activity-results'),footer=d.querySelector('#profile-activity-pagination');
 assert.equal(list.querySelectorAll('.activity-item').length,20);assert.equal(list.contains(footer),false);assert.equal(footer.parentElement,list.parentElement);
 assert.equal(list.tabIndex,0);assert.match(footer.textContent,/45 atividades/);
 footer.querySelectorAll('button')[1].click();await h.flush();assert.match(footer.textContent,/página 2/);assert.match(list.textContent,/OS0021/);
 const filter=d.querySelector('#profile-activity-filter');filter.value='create';filter.dispatchEvent(new h.w.Event('change'));await h.flush();assert.match(footer.textContent,/23 atividades/);assert.match(footer.textContent,/página 1/);
 const search=d.querySelector('#profile-activity-search');search.value='OS0001';search.dispatchEvent(new h.w.Event('input'));await sleep(300);assert.equal(list.querySelectorAll('.activity-item').length,1);assert.match(footer.textContent,/1 atividades/);
 search.value='inexistente';search.dispatchEvent(new h.w.Event('input'));await sleep(300);assert.ok(list.querySelector('.activity-empty'));assert.ok([...footer.querySelectorAll('button')].every(b=>b.disabled));
 h.click('#profile-tab-account');await h.flush();assert.equal(d.querySelector('#profile-panel-activities').hidden,true);
 h.click('#profile-tab-activities');await h.flush();assert.equal(list.contains(footer),false);
 assert.equal(h.requests.filter(r=>r.method&&r.method!=='GET').length,0);
});

test('notifications retain the scroll region and independent footer for paged and empty results',async t=>{
 const notifications=Array.from({length:15},(_,i)=>({id:i+1,title:'Notificacao '+i,message:'Teste',kind:'operational',link:'/acessos',occurred:new Date().toISOString(),read_at:null}));
 const h=await setup(t,'dashboard',{notifications}),d=h.doc;h.click('#notifications-button');await h.flush();
 const list=d.querySelector('.notification-results'),footer=d.querySelector('.notification-footer');
 assert.equal(list.tabIndex,0);assert.ok(list.classList.contains('record-scroll-region'));assert.equal(list.contains(footer),false);assert.equal(list.querySelectorAll('.notification-row').length,6);
 list.scrollTop=200;footer.querySelector('[aria-label="Próxima página"]').click();await h.flush();assert.match(footer.textContent,/7 a 12/);assert.equal(list.scrollTop,0);
 const search=d.querySelector('.notification-search input');search.value='inexistente';search.dispatchEvent(new h.w.Event('input'));assert.ok(list.querySelector('.notification-empty'));assert.match(footer.textContent,/0 notificações/);
 await h.close();h.click('#notifications-button');await h.flush();assert.equal(d.querySelectorAll('.notification-footer').length,1);
});

test('deadline switch keeps each view filters, search and page independent',async t=>{
 const h=await setup(t,'vencimentos'),d=h.doc;
 h.deadlineOrders=JSON.parse(fs.readFileSync(path.join(root,'tests/fixtures/vencimentos-os.json'),'utf8'));
 h.run("activeFilters={sistema:'Portal'};searchTerm='AC';currentPage=3");
 h.click('[data-deadline-type=os]');await h.flush();
 assert.equal(h.requests.at(-1).url,'/api/data/vencimentos?tipo=os');
 assert.equal(h.run('state.sheet'),'OrdensServico');assert.equal(h.run('searchTerm'),'');assert.equal(h.run('currentPage'),1);
 assert.equal(d.querySelector('[data-deadline-type=os]').getAttribute('aria-pressed'),'true');
 assert.ok(h.run("state.columns.includes('previsao')"));
 assert.equal(d.querySelectorAll('#expiry-summary>.badge').length,4);
 h.run("activeFilters={status:'Pendente'};searchTerm='OS'");
 h.click('[data-deadline-type=acessos]');await h.flush();
 assert.equal(h.run('state.sheet'),'Acessos');assert.equal(h.run('activeFilters.sistema'),'Portal');assert.equal(h.run('searchTerm'),'AC');
 h.click('[data-deadline-type=os]');await h.flush();assert.equal(h.run('activeFilters.status'),'Pendente');assert.equal(h.run('searchTerm'),'OS');
 h.networkError=true;h.click('[data-deadline-type=acessos]');await h.flush();
 assert.match(d.querySelector('#table-body').textContent,/Falha ao carregar/);assert.equal(d.querySelector('#export').disabled,true);
});

test('import requires analysis then explicit confirmation; cancellation never commits',async t=>{
 const h=await setup(t,'acessos'),d=h.doc;
 function attach(){const input=d.querySelector('.import-form input[type=file]');Object.defineProperty(input,'files',{configurable:true,value:[new h.w.File(['xlsx fixture'],'teste.xlsx')]});input.dispatchEvent(new h.w.Event('change'));return input;}
 h.click('#import-excel');attach();
 assert.equal(d.querySelector('.import-layout .primary').disabled,true);
 d.querySelector('.import-form').dispatchEvent(new h.w.Event('submit',{bubbles:true,cancelable:true}));await h.flush();
 assert.equal(h.requests.filter(r=>r.url==='/api/import/confirm').length,0);
 assert.match(d.querySelector('.import-status').textContent,/Revise/);
 assert.equal(d.querySelector('.import-layout .primary').disabled,false);
 h.click('#modal-close');await h.flush();assert.equal(h.requests.filter(r=>r.url==='/api/import/confirm').length,0);
 assert.equal(h.requests.filter(r=>r.url==='/api/import/cancel').length,1);
 h.click('#import-excel');attach();d.querySelector('.import-form').dispatchEvent(new h.w.Event('submit',{bubbles:true,cancelable:true}));await h.flush();
 const confirm=d.querySelector('.import-layout .primary');confirm.click();confirm.click();await h.flush();
 assert.equal(h.requests.filter(r=>r.url==='/api/import/confirm').length,1);
 assert.match(d.querySelector('.import-status').textContent,/concluída/);assert.equal(confirm.hidden,true);
 assert.ok(h.requests.at(-1).url.startsWith('/api/data/acessos'));
});

test('invalid import preview and changed mode keep confirmation disabled',async t=>{
 const h=await setup(t,'acessos'),d=h.doc;h.click('#import-excel');
 h.importPreview={token:'bad',filename:'teste.xlsx',sheets:{},totals:{},changes:[],errors:[{sheet:'Acessos',line:2,code:'AC1',field:'status',message:'Status inválido.'}],can_confirm:false};
 const input=d.querySelector('input[type=file]');Object.defineProperty(input,'files',{configurable:true,value:[new h.w.File(['fixture'],'teste.xlsx')]});input.dispatchEvent(new h.w.Event('change'));
 d.querySelector('.import-form').dispatchEvent(new h.w.Event('submit',{bubbles:true,cancelable:true}));await h.flush();
 assert.equal(d.querySelector('.import-layout .primary').disabled,true);assert.match(d.querySelector('.import-preview').textContent,/linha 2/);
 const mode=d.querySelector('select[name=mode]');mode.value='upsert';mode.dispatchEvent(new h.w.Event('change'));await h.flush();
 assert.equal(d.querySelector('.import-preview').textContent,'');assert.equal(d.querySelector('.import-layout .primary').disabled,true);
});

test('select opening keeps selection separate from keyboard focus across search modes',async t=>{
 const h=await setup(t,'equipes'),d=h.doc;
 for(const count of [3,8]){
  const select=d.createElement('select');
  for(let i=0;i<count;i++)select.append(new h.w.Option('Option '+i,String(i)));
  select.value='2';d.body.append(select);h.w.DashboardControls.refresh();
  const input=select.parentElement.querySelector('.select-input');input.click();
  let popup=d.querySelector('.select-popup:not([hidden])');
  assert.equal(popup.querySelectorAll('[aria-selected=true]').length,1);
  assert.equal(popup.querySelector('[aria-selected=true]').textContent,'Option 2');
  assert.equal(popup.querySelectorAll('.is-active').length,0);
  assert.equal(popup.querySelectorAll('.ui-icon').length,1);
  input.dispatchEvent(new h.w.KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true}));
  assert.equal(popup.querySelectorAll('.is-active').length,1);
  assert.ok(input.getAttribute('aria-activedescendant'));
  input.dispatchEvent(new h.w.KeyboardEvent('keydown',{key:'Escape',bubbles:true}));
  input.click();assert.equal(popup.querySelectorAll('.is-active').length,0);
  h.w.DashboardControls.closeAll();
 }
});

test('access deadlines share expiry presentation while operational status stays independent',async t=>{
 const h=await setup(t,'acessos');
 h.run("state.rows=['Vencidos','Vencem hoje','At\\u00e9 30 dias','31 a 45 dias','Ap\\u00f3s 45 dias'].map((situacao,i)=>({...state.rows[0],codigo:String(i),situacao,status:'Ativo'}));renderTable()");
 assert.deepEqual([...h.doc.querySelectorAll('td[data-column=situacao] .badge')].map(n=>n.className),['badge expired','badge urgent','badge urgent','badge warn','badge good']);
 assert.ok([...h.doc.querySelectorAll('td[data-column=status] .badge')].every(n=>n.textContent==='Ativo'));
 assert.equal(h.run("optionLabel('situacao','Vencidos')"),'Vencido');
});

test('correções finais: equipes pagina 12/24/48 e ajusta pesquisa e redução de dados',async t=>{
 const h=await setup(t,'equipes'),d=h.doc;
 assert.deepEqual([...d.querySelector('#page-size').options].map(o=>o.value),['12','24','48']);
 h.run("state.rows=Array.from({length:61},(_,i)=>({...state.rows[0],codigo:'EQ'+String(i).padStart(3,'0'),nome:'Equipe '+i}));renderTable()");
 assert.equal(d.querySelectorAll('.team-card').length,12);
 for(const size of [24,48,12]){h.run('pageSize='+size+';currentPage=1;renderTable()');assert.equal(d.querySelectorAll('.team-card').length,size);assert.equal(d.querySelector('#page-number').textContent,'1 / '+Math.ceil(61/size));}
 h.run('currentPage=6;state.rows=state.rows.slice(0,3);renderTable()');assert.equal(d.querySelectorAll('.team-card').length,3);assert.equal(d.querySelector('#page-number').textContent,'1 / 1');
 h.run("searchTerm='inexistente';renderTable()");assert.equal(d.querySelectorAll('.team-card').length,0);assert.equal(d.querySelector('#record-count').textContent,'0 registros');
 const other=await setup(t,'funcionarios');assert.deepEqual([...other.doc.querySelector('#page-size').options].map(o=>o.value),['10','20','50']);
});

test('correções finais: vencimentos conserva categorias internas e agrupa hoje com urgência',async t=>{
 const h=await setup(t,'vencimentos'),d=h.doc;
 h.run("state.rows=['Vencidos','Vencem hoje','Até 30 dias','31 a 45 dias','Após 45 dias'].map((situacao,i)=>({...state.rows[0],codigo:String(i),situacao}));renderTable()");
 assert.deepEqual([...d.querySelectorAll('td[data-column=situacao] .badge')].map(n=>n.textContent),['Vencido','Urgente','Urgente','Atenção','Dentro do prazo']);
 assert.deepEqual(h.run('state.rows.map(r=>r.situacao)').join('|'),'Vencidos|Vencem hoje|Até 30 dias|31 a 45 dias|Após 45 dias');
 assert.match(d.querySelector('#expiry-summary').textContent,/Urgente: 2/);assert.equal(d.querySelector('#today'),null);
});

test('correções finais: tooltip acompanha X/Y, limita bordas e não redesenha séries',async t=>{
 const h=await setup(t,'dashboard'),d=h.doc,n=d.querySelector('#chart-trend'),draws=h.plots.length;
 const point={curveNumber:0,pointNumber:1,x:n.data[0].x[1],data:n.data[0]};
 n.__events.plotly_hover({points:[point],event:{clientX:200,clientY:300}});
 const tip=d.querySelector('body>.chart-tooltip:not([hidden])');
 n.closest('.chart-card').__rect={left:20,top:20,right:900,bottom:700,width:880,height:680};
 tip.__rect={left:0,top:0,right:180,bottom:160,width:180,height:160};
 n.__events.plotly_hover({points:[point],event:{clientX:200,clientY:300}});
 assert.equal(tip.style.left,'218px');assert.equal(tip.style.top,'220px');
 n.__events.plotly_hover({points:[point],event:{clientX:300,clientY:400}});
 assert.equal(tip.style.left,'318px');assert.equal(tip.style.top,'320px');
 n.__events.plotly_hover({points:[point],event:{clientX:890,clientY:690}});
 assert.ok(parseFloat(tip.style.left)+180<=900);assert.ok(parseFloat(tip.style.top)+160<=700);
 assert.equal(tip.querySelectorAll('.chart-tooltip-row').length,n.data.length);assert.equal(h.plots.length,draws);
});

test('premium: Top 5 conserva universo, percentuais e consulta da equipe selecionada',async t=>{
 const h=await setup(t,'dashboard'),before=JSON.stringify(h.data),rows=h.data.overview.access_teams.slice(0,5),total=rows.reduce((sum,r)=>sum+r.value,0);
 assert.equal(h.doc.querySelector('.access-center strong').textContent,h.w.DashboardPreferences.formatNumber(total));assert.match(h.doc.querySelector('.access-center small').textContent,/Top 5/);
 assert.equal(h.doc.querySelectorAll('.access-ranking-row').length,rows.length);assert.equal(h.doc.querySelectorAll('#access-summary .premium-metric').length,4);
 h.doc.querySelectorAll('.access-ranking-row')[1].click();assert.equal(new URL(h.doc.querySelector('#access-details').href).searchParams.get('equipe'),rows[1].code);
 assert.equal(JSON.stringify(h.data),before);assert.doesNotMatch(h.doc.querySelector('#access-summary').textContent,/vs\. período anterior/);
});

test('premium: legenda de OS oculta série sem alterar métricas ou dados',async t=>{
 const h=await setup(t,'dashboard'),before=JSON.stringify(h.data),metrics=h.doc.querySelector('#team-order-summary').textContent;
 h.click('#teams-legend button');await h.flush();assert.equal(h.doc.querySelector('#chart-teams').data[0].visible,'legendonly');assert.equal(h.doc.querySelector('#teams-legend button').getAttribute('aria-pressed'),'false');
 assert.equal(h.doc.querySelector('#team-order-summary').textContent,metrics);assert.equal(JSON.stringify(h.data),before);
 h.click('[data-chart="teams"]');await h.flush();assert.equal(h.doc.querySelector('.expanded-team-orders .plot').data[0].visible,'legendonly');
});

test('motion: movimento reduzido desativa durações sem impedir menus e modais',async t=>{
 const h=await setup(t,'dashboard',{animate:true});h.w.DashboardPreferences.set({reduceMotion:true});assert.equal(h.w.DashboardMotion.duration('menu'),0);
 const group=h.doc.querySelector('.sidebar-group');h.w.DashboardMotion.details(group,true);assert.equal(group.open,true);h.w.DashboardMotion.details(group,false);assert.equal(group.open,false);
 h.click('[data-chart="teams"]');await h.flush();h.click('#modal-close');await h.flush();assert.equal(h.doc.querySelector('#modal').open,false);
});

test('refinamento: painel analítico seleciona status, preserva filtros e não escreve dados',async t=>{
 const h=await setup(t,'dashboard');h.run("activeFilters={equipe:'EQ0001',prioridade:'Alta',inicio:'2026-01-01',fim:'2026-12-31'}");
 const before=h.requests.length;h.click('[data-chart="donut"]');await h.flush();
 const d=h.doc,rows=d.querySelectorAll('.analysis-status');assert.equal(rows.length,h.data.charts.donut.data[0].labels.length);
 rows[1].click();let url=new URL(d.querySelector('.analysis-actions a').href);
 assert.equal(url.pathname,'/ordens-servico');assert.equal(url.searchParams.get('status'),'Pendente');assert.equal(url.searchParams.get('equipe'),'EQ0001');assert.equal(url.searchParams.get('prioridade'),'Alta');assert.equal(url.searchParams.get('inicio'),'2026-01-01');assert.equal(url.searchParams.get('fim'),'2026-12-31');
 const plot=d.querySelector('.donut-analysis-chart .plot');plot.__events.plotly_click({points:[{label:'Concluída',curveNumber:0,pointNumber:0}]});
 assert.equal(new URL(d.querySelector('.analysis-actions a').href).searchParams.get('status'),'Concluída');
 assert.equal(d.querySelector('.analysis-status[aria-pressed=true]').dataset.status,'Concluída');assert.equal(h.requests.length,before);
 await h.close();assert.equal(d.querySelectorAll('dialog>.chart-tooltip').length,0);
});

test('refinamento: painel de status vazio mantém totais e percentuais finitos',async t=>{
 const h=await setup(t,'dashboard');h.run("chartSpecs.donut.data[0].values=[0,0,0]");h.click('[data-chart="donut"]');await h.flush();
 assert.equal(h.doc.querySelector('.donut-analysis-chart .donut-center strong').textContent,'0');
 assert.equal(h.doc.querySelectorAll('.analysis-status').length,3);assert.doesNotMatch(h.doc.querySelector('.donut-analytics').textContent,/NaN|Infinity/);
});

test('refinamento: visitante só é oferecido no login; indicadores removidos preservam dados',async t=>{
 const h=await setup(t,'dashboard');assert.equal(h.doc.querySelector('.sidebar form[action="/auth/guest"]'),null);
 const login=fs.readFileSync(path.join(__dirname,'fixtures/login.html'),'utf8');assert.match(login,/action="\/auth\/guest"/);
 assert.equal(h.doc.querySelectorAll('#kpis .kpi').length,4);assert.equal(h.doc.querySelector('#secondary-kpis'),null);assert.equal(h.doc.querySelector('#attention-panel'),null);
 assert.ok(Object.hasOwn(h.data.indicators,'Vencidos'));assert.ok(h.data.agenda.attention.length);
 assert.ok(h.doc.querySelector('.page-chrome .header-operations .toolbar'));assert.equal(h.doc.querySelector('.header-right #today'),null);
});

test('midnight: preferências na conta não alteram opções de e-mail',async t=>{
 const h=await setup(t,'perfil');await h.w.DashboardProfile.selectTab('preferences');
 const select=h.doc.querySelector('[data-preference="theme"]');select.value='light';select.dispatchEvent(new h.w.Event('change'));
 h.click('#profile-panel-preferences .button.primary');await h.flush();
 const request=h.requests.find(r=>r.url==='/api/profile'&&r.method==='PUT');
 assert.equal(JSON.parse(request.body).appearance.theme,'light');assert.equal(Object.hasOwn(JSON.parse(request.body),'email_alerts'),false);
 assert.equal(h.doc.querySelector('#settings-button'),null);
});

test('midnight: cartões de equipes preservam consulta e restrições do visitante',async t=>{
 for(const guest of [false,true]){const h=await setup(t,'equipes',{guest});
  assert.equal(h.doc.querySelectorAll('.team-card').length,Math.min(12,h.data.rows.length));
  const actions=h.doc.querySelectorAll('.team-card .row-actions button');assert.equal(actions[0].disabled,false);assert.equal(actions[1].disabled,guest);assert.equal(actions[2].disabled,guest);
  actions[0].click();assert.equal(h.doc.querySelector('#modal').open,true);await h.close();
 }
});

test('midnight: cápsulas usam o filtro real de status',async t=>{
 const h=await setup(t,'ordens-servico'),status=h.data.statuses[0];
 [...h.doc.querySelectorAll('#status-pills button')].find(b=>b.textContent===status).click();await h.flush();
 assert.ok(h.requests.some(r=>r.url==='/api/data/ordens-servico?'+new URLSearchParams({status})));
 assert.equal(h.doc.querySelector('#status-pills [aria-pressed=true]').textContent,status);
});

test('perfil: cartões independentes, preferências persistidas, confirmação e central',async t=>{
 const h=await setup(t,'perfil'),doc=h.doc;
 assert.equal(doc.querySelectorAll('[role="tab"]').length,5);
 assert.equal(doc.querySelectorAll('.profile-card').length,5);
 const info=doc.querySelector('#profile-info-form');info.elements.display_name.value='Nome atualizado';
 doc.querySelector('[data-edit-account]').click();info.elements.display_name.dispatchEvent(new h.w.Event('input',{bubbles:true}));
 info.dispatchEvent(new h.w.Event('submit',{bubbles:true,cancelable:true}));await h.flush();
 const request=h.requests.find(r=>r.url==='/api/profile'&&r.method==='PUT');assert.equal(JSON.parse(request.body).display_name,'Nome atualizado');
 const theme=doc.querySelector('[data-preference="theme"]');theme.value='light';theme.dispatchEvent(new h.w.Event('change'));assert.equal(doc.documentElement.dataset.theme,'light');
 const secure=doc.querySelector('#profile-security-form');secure.elements.password.value='nova-senha-longa';secure.dispatchEvent(new h.w.Event('submit',{bubbles:true,cancelable:true}));await h.flush();assert.match(secure.querySelector('.form-error').textContent,/não coincidem/);
 h.click('#notifications-button');await h.flush();assert.equal(doc.querySelector('#modal').open,true);assert.ok(doc.querySelector('.notifications-modal'));assert.match(doc.querySelector('#modal-body').textContent,/Você está em dia/);
});

test('administração: criar conta e exigir prévia antes de publicar comunicado',async t=>{
 const h=await setup(t,'administracao'),doc=h.doc;
 doc.querySelector('#account-content button').click();await h.flush();
 assert.ok(doc.querySelector('#modal [name="role"]'));
 await h.close();
 const form=doc.querySelector('#announcement-content form');form.elements.title.value='Aviso';form.elements.message.value='<script>texto</script>';
 form.dispatchEvent(new h.w.Event('submit',{cancelable:true,bubbles:true}));await h.flush();
 assert.equal(h.requests.filter(r=>r.url==='/api/admin/announcements'&&r.method==='POST').length,0);
 assert.equal(doc.querySelector('#modal-body script'),null);
 assert.match(doc.querySelector('#modal-body').textContent,/<script>texto/);
 doc.querySelector('#modal-body button').click();await h.flush();
 const request=h.requests.find(r=>r.url==='/api/admin/announcements'&&r.method==='POST');assert.equal(JSON.parse(request.body).confirmed,true);
});

async function setup(t,page,options={}){
 const fixture=page+(options.guest?'-guest':'');
 const html=fs.readFileSync(path.join(__dirname,'fixtures',fixture+'.html'),'utf8');
 const data=JSON.parse(fs.readFileSync(path.join(__dirname,'fixtures',fixture+'.json'),'utf8'));
 if(options.multiLine){const second=structuredClone(data.charts.trend.data[0]);second.name='Pendente';second.line.color='#ffc247';second.y=second.y.map(v=>Math.floor(v/2));data.charts.trend.data.push(second);}
 if(options.profileState&&data.profile)Object.assign(data.profile,options.profileState);
 const errors=[],requests=[],plots=[],purged=[],downloads=[],navigationClicks=[];
 const virtualConsole=new VirtualConsole();virtualConsole.on('jsdomError',error=>errors.push(error.message));
 const dom=new JSDOM(html,{url:'http://localhost/'+page,runScripts:'outside-only',pretendToBeVisual:true,virtualConsole});
 const w=dom.window,doc=w.document,observers=[];
 if(options.userKey)doc.documentElement.dataset.userKey=options.userKey;
 if(options.guest){doc.body.dataset.role='guest';data.user={role:'guest',id:'Visitante'};}
 if(options.sidebar)w.localStorage.setItem('DashboardOS:sidebar:v1:'+doc.documentElement.dataset.userKey,options.sidebar);
 if(options.preferences)w.localStorage.setItem('DashboardOS_2.0:appearance:v1:'+doc.documentElement.dataset.userKey,JSON.stringify(options.preferences));
 const mediaListeners={};
 const mediaState={dark:Boolean(options.systemDark),motion:!options.animate,mobile:Boolean(options.mobile)};
 w.matchMedia=query=>({get matches(){return query.includes('reduced-motion')?mediaState.motion:query.includes('max-width: 600px')?mediaState.mobile:mediaState.dark;},addEventListener:(name,callback)=>mediaListeners[query]=callback});
 const harness={dom,w,doc,data,errors,requests,plots,purged,downloads,navigationClicks,networkError:false,exportFailure:false,deleteFailure:false};
 harness.mediaListeners=mediaListeners;
 harness.mediaState=mediaState;
 // jsdom não implementa navegação. Os destinos são verificados pela suíte Flask.
 doc.addEventListener('click',event=>{const link=event.target.closest('a');if(link){navigationClicks.push(link.getAttribute('href'));event.preventDefault();}},true);
 t.after(()=>{harness.run("DashboardControls.destroy();document.querySelectorAll('.plot').forEach(releaseChart)");dom.window.close();assert.deepEqual(errors,[],'Nenhum erro JavaScript deve ficar sem tratamento.');});
 w.structuredClone=structuredClone;
 w.requestAnimationFrame=fn=>w.setTimeout(()=>fn(Date.now()),0);
 w.ResizeObserver=class{constructor(callback){this.callback=callback;this.targets=new Set();observers.push(this);}observe(node){this.targets.add(node);}unobserve(node){this.targets.delete(node);}};
 w.Element.prototype.getBoundingClientRect=function(){return this.__rect||{x:0,y:0,left:0,top:0,right:600,bottom:180,width:600,height:180};};
 w.HTMLDialogElement.prototype.showModal=function(){this.setAttribute('open','');};
 w.HTMLDialogElement.prototype.close=function(){this.removeAttribute('open');w.setTimeout(()=>this.dispatchEvent(new w.Event('close')),0);};
 w.HTMLAnchorElement.prototype.click=function(){downloads.push({href:this.href,download:this.download});};
 w.URL.createObjectURL=()=> 'blob:dashboardos-test';w.URL.revokeObjectURL=()=>{};
 w.Plotly={react:async(node,traces,layout,config)=>{node.data=traces;node.layout=layout;if(!node.on){node.__events={};node.on=(name,fn)=>node.__events[name]=fn;node.removeListener=(name)=>delete node.__events[name];}plots.push({node,traces,layout,config});},restyle:(node,patch,indexes)=>{node.__restyles??=[];node.__restyles.push({patch,indexes});return Promise.resolve();},purge:node=>{purged.push(node);delete node.data;delete node.layout;}};
 let releaseInitial;const initialGate=options.deferInitial?new Promise(resolve=>releaseInitial=resolve):Promise.resolve();
 harness.releaseInitial=releaseInitial;
 const result=(body,status=200)=>({ok:status>=200&&status<300,status,json:async()=>structuredClone(body),blob:async()=>new w.Blob(['xlsx-test'])});
 w.fetch=async(url,config={})=>{
  requests.push({url:String(url),...config});
  if(harness.networkError)throw Error('offline');
  if(String(url)==='/api/import/preview')return result(harness.importPreview||{token:'preview-only',filename:'teste.xlsx',sheets:{Acessos:{found:1,added:1,updated:0,unchanged:0,ignored:0,invalid:0}},totals:{found:1,added:1,updated:0,unchanged:0,ignored:0,invalid:0},errors:[],changes:[{sheet:'Acessos',code:'AC9999',line:2,kind:'added',fields:[{field:'sistema',before:'',after:'Recurso de teste'}]}],can_confirm:true});
  if(String(url)==='/api/import/cancel')return result({message:'Cancelado.'});
  if(String(url)==='/api/import/confirm')return result({totals:{added:1,updated:0,unchanged:0,ignored:0},message:'Importado.'});
  if(String(url).startsWith('/api/notifications')){
   data.notifications??=structuredClone(options.notifications||[]);
   if(config.method==='POST'){
    const id=Number(String(url).split('/')[3]),action=JSON.parse(config.body).action;
    if(action==='read')for(const item of data.notifications)if(!id||item.id===id)item.read_at=new Date().toISOString();
    if(action==='delete')data.notifications=data.notifications.filter(item=>id&&item.id!==id);
   }
   return result({notifications:data.notifications,unread:data.notifications.filter(n=>!n.read_at).length,message:'Central atualizada.'});
  }
  if(String(url)==='/api/profile/verification')return result({state:'unverified',can_confirm:false,delivery_available:false});
  if(String(url).startsWith('/api/profile/login-availability'))return result({available:!String(url).includes('duplicate')});
  if(String(url).startsWith('/api/profile/activities')){
   const params=new URL(String(url),'http://localhost').searchParams,n=Number(params.get('page')||1);
   const rows=(options.activities||[]).filter(item=>(!params.get('operation')||item.operation===params.get('operation'))&&(!params.get('q')||item.record_code.includes(params.get('q'))));
   return result({activities:rows.slice((n-1)*20,n*20),total:rows.length,page:n,page_size:20});
  }
  if(String(url)==='/api/profile/email-change'){
   if(config.method==='DELETE')data.profile.pending_email=null;
   else data.profile.pending_email={address:JSON.parse(config.body).email,expires:Date.now()/1000+1800};
   return result({message:'Solicitação preparada. A entrega ainda não está habilitada.',delivery_available:false,profile:data.profile});
  }
  if(String(url)==='/api/profile'){
   if(config.method==='PUT'){Object.assign(data.profile,JSON.parse(config.body));return result({message:'Perfil atualizado.'});}
   return result(data.profile);
  }
  if(String(url).startsWith('/api/admin/users'))return result({users:data.users||[],message:'Conta atualizada.'});
  if(String(url)==='/api/admin/audit')return result({audit:[]});
  if(String(url)==='/api/admin/announcements')return result({announcements:[],message:'Comunicado publicado.'});
  if(String(url).startsWith('/api/export/'))return harness.exportFailure?result({error:'Falha de exportação'},503):result({});
  if(String(url).startsWith('/api/data/')){await initialGate;return result(new URL(String(url),'http://localhost').searchParams.get('tipo')==='os'&&harness.deadlineOrders?harness.deadlineOrders:data);}
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
  if(h.data.rows.length>(page==='equipes'?12:10)){h.click('#next');assert.match(doc.querySelector('#page-number').textContent,/^2 \/ /);h.click('#prev');}
  else assert.equal(doc.querySelector('#next').disabled,true);
  const size=doc.querySelector('#page-size');size.value=page==='equipes'?'24':'20';size.dispatchEvent(new h.w.Event('change'));assert.equal(doc.querySelectorAll('#table-body tr').length,Math.min(page==='equipes'?24:20,h.data.rows.length));
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
  const spec=h.data.charts[key],rendered=h.plots.at(-1);
  assert.deepEqual(rendered.traces.map(trace=>({x:trace.x,y:trace.y,values:trace.values,labels:trace.labels})),spec.data.map(trace=>({x:trace.x,y:trace.y,values:trace.values,labels:trace.labels})));
  assert.equal(rendered.layout.showlegend,key==='trend'&&spec.data.length>1);
  if(key==='donut'){assert.ok(doc.querySelector('.analysis-breakdown'));assert.equal(doc.querySelector('.donut-analysis-chart .donut-center strong').textContent,String(spec.data[0].values.reduce((a,b)=>a+b,0)));}
  assert.equal(rendered.layout.xaxis.showspikes,false);assert.equal(rendered.layout.yaxis.showspikes,false);assert.equal(rendered.layout.hovermode,key==='trend'?'x':'closest');
  assert.ok(rendered.layout.hoverlabel.font.size>=14);
  assert.ok(rendered.traces.every(trace=>trace.hoverinfo==='none'&&trace.name&&!/^trace\s*\d/i.test(trace.name)));
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
 const h=await setup(t,'perfil'),doc=h.doc,prefs=h.w.DashboardPreferences,raw=JSON.stringify(h.data);
 assert.equal(doc.documentElement.dataset.theme,'dark');assert.equal(prefs.scale(),1.1);
 assert.equal(doc.querySelector('#settings-button'),null);
 await h.w.DashboardProfile.selectTab('preferences');assert.equal(doc.querySelector('#profile-panel-preferences').hidden,false);
 function choose(key,value){const control=doc.querySelector('[data-preference="'+key+'"]');control.value=value;control.dispatchEvent(new h.w.Event('change'));}
 choose('theme','dark');await h.flush();assert.equal(doc.documentElement.dataset.theme,'dark');
 assert.equal(doc.querySelector('#profile-preferences-form [name=theme]'),null);
 choose('theme','auto');h.mediaState.dark=true;h.mediaListeners['(prefers-color-scheme: dark)']();await h.flush();assert.equal(doc.documentElement.dataset.theme,'dark');
 h.mediaState.dark=false;h.mediaListeners['(prefers-color-scheme: dark)']();assert.equal(doc.documentElement.dataset.theme,'light');
 for(const [value,scale] of [['small',1],['default',1.1],['large',1.22],['xlarge',1.35]]){choose('font',value);assert.equal(prefs.scale(),scale);assert.equal(doc.documentElement.style.getPropertyValue('--font-scale'),String(scale));}
 choose('density','compact');assert.equal(doc.documentElement.dataset.density,'compact');
 choose('numbers','compact');assert.match(prefs.formatNumber(1250),/1,25.*mil/);
 choose('numbers','standard');assert.equal(prefs.formatNumber(1250),'1.250');
 assert.equal(JSON.stringify(h.data),raw);
});

test('preferências persistem por usuário e restaurar não toca outras chaves nem faz escrita HTTP',async t=>{
 const h=await setup(t,'perfil'),prefs=h.w.DashboardPreferences;
 prefs.set({theme:'dark',font:'large',density:'compact',numbers:'compact',reduceMotion:true});
 const saved=JSON.parse(h.w.localStorage.getItem(prefs.key));assert.equal(saved.theme,'dark');
 assert.deepEqual(Object.keys(saved).sort(),['density','font','numbers','reduceMotion','theme']);
 const reload=await setup(t,'acessos',{preferences:saved});assert.equal(reload.doc.documentElement.dataset.theme,'dark');assert.equal(reload.w.DashboardPreferences.scale(),1.22);
 const other=await setup(t,'funcionarios',{userKey:'outro-usuario'});assert.notEqual(other.w.DashboardPreferences.key,prefs.key);assert.equal(other.doc.documentElement.dataset.theme,'dark');
 h.w.localStorage.setItem('outra-aplicacao','preservar');const before=h.requests.length;
 await h.w.DashboardProfile.selectTab('preferences');h.click('.settings-panel .form-actions button');
 assert.equal(prefs.get().theme,'dark');assert.equal(prefs.scale(),1.1);assert.equal(h.w.localStorage.getItem(prefs.key),null);
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
 assert.equal(doc.body.dataset.role,'guest');assert.match(doc.querySelector('.session-actions').textContent,/Sair do modo visitante/);
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
 assert.equal(h.doc.querySelector('#settings-button'),null);assert.equal(h.doc.querySelector('a[href="/perfil"]'),null);
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


test('hover premium: nevoa por categoria, ponto real, restauracao e limpeza do portal',async t=>{
 const h=await setup(t,'dashboard',{multiLine:true}),doc=h.doc;
 const bar=doc.querySelector('#chart-teams'),line=doc.querySelector('#chart-trend');
 const point=(node,i,j)=>({points:[{curveNumber:i,pointNumber:j,x:node.data[i].x[j],y:node.data[i].y[j],data:node.data[i]}],event:{clientX:590,clientY:20}});
 bar.__events.plotly_hover(point(bar,0,0));
 const tip=doc.querySelector('body>.chart-tooltip:not([hidden])');assert.ok(tip);assert.match(tip.textContent,/Conclu.da/);
 assert.equal(bar.__restyles?.length||0,0,'Hover individual não redesenha ou desloca as demais barras.');
 assert.equal(tip.querySelectorAll('.chart-tooltip-row').length,1);
 bar.__events.plotly_unhover();assert.equal(tip.hidden,true);
 const pending=line.data.findIndex(trace=>trace.name==='Pendente');line.__events.plotly_hover(point(line,pending,1));
 assert.equal(line.__restyles?.length||0,0);
 assert.match(doc.querySelector('body>.chart-tooltip:not([hidden])').textContent,/Pendente/);
 line.__events.plotly_unhover();assert.equal(line.__restyles?.length||0,0);
 h.click('[data-chart="trend"]');await h.flush();assert.equal(doc.querySelectorAll('dialog>.chart-tooltip').length,1);
 await h.close();assert.equal(doc.querySelectorAll('dialog>.chart-tooltip').length,0);
 assert.equal(doc.querySelector('#chart-donut').layout.showlegend,false);
 assert.ok(doc.querySelector('.calendar-panel #calendar'));
});

test('filtro unico ocupa modal proporcional sem mudar os filtros',async t=>{
 const h=await setup(t,'equipes');h.click('#filters-button');
 assert.ok(h.doc.querySelector('dialog.modal-single form>label select[name="responsavel"]'));
 assert.equal(h.doc.querySelectorAll('#modal form>label').length,1);
});

test('seleção pesquisável: pesquisa imediata, estado vazio, teclado, Esc e FormData',async t=>{
 const h=await setup(t,'equipes'),doc=h.doc;h.click('#filters-button');await h.flush();
 const native=doc.querySelector('select[name="responsavel"]'),input=native.parentElement.querySelector('.select-input');
 const option=native.options[1];assert.ok(option);
 input.focus();assert.equal(input.getAttribute('aria-expanded'),'false');input.click();assert.equal(input.value,'');assert.equal(input.getAttribute('aria-expanded'),'true');
 input.value='__sem_resultados__';input.dispatchEvent(new h.w.Event('input',{bubbles:true}));
 assert.match(doc.querySelector('.select-popup:not([hidden])').textContent,/Nenhuma/);
 input.value=option.textContent;input.dispatchEvent(new h.w.Event('input',{bubbles:true}));
 input.dispatchEvent(new h.w.KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
 assert.equal(native.value,option.value);assert.equal(new h.w.FormData(native.form).get('responsavel'),option.value);
 assert.equal(input.value,option.textContent);assert.equal(input.getAttribute('aria-expanded'),'false');
 input.dispatchEvent(new h.w.KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true,cancelable:true}));
 input.dispatchEvent(new h.w.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
 assert.equal(input.getAttribute('aria-expanded'),'false');assert.equal(doc.querySelector('dialog').open,true);
 await h.close();h.click('#new');await h.flush();
 assert.ok([...doc.querySelectorAll('select')].every(s=>s.classList.contains('native-select')));
});

test('seleção múltipla preserva todos os valores, opções desabilitadas e eventos',async t=>{
 const h=await setup(t,'equipes'),doc=h.doc;
 const form=doc.createElement('form');form.innerHTML='<label>Destinatários<select name="recipients" multiple><option value="a">Ana</option><option value="b">Bruno</option><option value="c" disabled>Carla</option></select></label>';doc.body.append(form);h.w.DashboardControls.refresh();
 const select=form.querySelector('select'),input=form.querySelector('.select-input');let changes=0;select.addEventListener('change',()=>changes++);input.focus();input.click();
 const choose=index=>doc.querySelector('.select-popup:not([hidden]) [role="listbox"]').children[index].dispatchEvent(new h.w.MouseEvent('pointerdown',{bubbles:true,cancelable:true}));
 choose(0);input.click();choose(1);input.click();choose(2);
 assert.deepEqual([...new h.w.FormData(form).getAll('recipients')],['a','b']);assert.equal(changes,2);
 input.dispatchEvent(new h.w.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));assert.match(input.value,/Ana, Bruno/);
 input.focus();input.click();select.disabled=true;await h.flush();assert.equal(input.disabled,true);assert.equal(input.getAttribute('aria-expanded'),'false');
});

test('seleção: limiar global 7/8 acompanha opções disponíveis sem perder o valor',async t=>{
 const h=await setup(t,'equipes'),d=h.doc,form=d.createElement('form');d.body.append(form);
 for(const count of [2,5,7,8,10]){const select=d.createElement('select');select.name='list'+count;for(let i=0;i<count;i++)select.append(new h.w.Option(i===0?'Todos':'Opção '+i,String(i)));select.value='1';form.append(select);h.w.DashboardControls.refresh();const input=select.parentElement.querySelector('.select-input');assert.equal(input.readOnly,count<=7);assert.equal(select.value,'1');}
 const select=form.querySelector('select[name=list7]'),input=select.parentElement.querySelector('.select-input');select.append(new h.w.Option('Mais uma','8'));await h.flush();assert.equal(input.readOnly,false);assert.equal(select.value,'1');select.lastElementChild.disabled=true;await h.flush();assert.equal(input.readOnly,true);assert.equal(new h.w.FormData(form).get('list7'),'1');select.lastElementChild.disabled=false;select.lastElementChild.hidden=true;await h.flush();assert.equal(input.readOnly,true);
 input.click();input.dispatchEvent(new h.w.KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true,cancelable:true}));input.dispatchEvent(new h.w.KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));assert.equal(select.value,'1');
});

test('atualização: chamadas repetidas compartilham trabalho e liberam estado após erro',async t=>{
 const h=await setup(t,'dashboard'),b=h.doc.querySelector('#refresh');let release,calls=0;h.w.qaWork=()=>{calls++;return new Promise(resolve=>release=resolve);};
 const first=h.run('refreshWithMotion(window.qaWork)'),second=h.run('refreshWithMotion(window.qaWork)');assert.equal(first,second);assert.equal(calls,1);assert.equal(b.getAttribute('aria-busy'),'true');assert.equal(b.disabled,true);release();await first;assert.equal(b.hasAttribute('aria-busy'),false);assert.equal(b.disabled,false);
 h.w.qaWork=async()=>{throw new Error('falha simulada')};await assert.rejects(h.run('refreshWithMotion(window.qaWork)'));assert.equal(b.hasAttribute('aria-busy'),false);assert.equal(b.disabled,false);
});

test('filtros: aplicar e limpar preservam ações e usam vetores diferentes',async t=>{
 const h=await setup(t,'acessos');h.click('#filters-button');await h.flush();const apply=h.doc.querySelector('.form-actions .primary svg path'),clear=h.doc.querySelector('.form-actions .secondary svg path');assert.ok(apply);assert.ok(clear);assert.notEqual(apply.getAttribute('d'),clear.getAttribute('d'));
});

test('perfil: sino permanece fora das operações ocultas e abre a central',async t=>{
 const h=await setup(t,'perfil');assert.equal(h.doc.querySelector('.toolbar').hidden,true);const bell=h.doc.querySelector('#notifications-button');assert.equal(bell.closest('.toolbar'),null);bell.click();await h.flush();assert.equal(h.doc.querySelector('#modal').open,true);assert.ok(h.doc.querySelector('.notifications-modal'));
});

test('relatórios: uma série e barra mínima recebem região confortável sem alterar os dados',async t=>{
 const h=await setup(t,'relatorios'),node=h.doc.querySelector('#chart-report'),before=JSON.stringify(node.data),layer=h.doc.createElement('div');layer.className='barlayer';
 const group=h.doc.createElement('div');group.className='trace';layer.append(group);node.append(layer);
 for(let i=0;i<2;i++){const point=h.doc.createElement('div');point.className='point';const path=h.doc.createElementNS('http://www.w3.org/2000/svg','path');path.getBoundingClientRect=()=>({left:10+i*50,right:30+i*50,top:99,bottom:100,width:20,height:1});point.append(path);group.append(point);}
 node.getBoundingClientRect=()=>({left:0,top:0,width:200,height:120});h.w.qaBars=[{type:'bar',x:['Pequena','Controle'],y:[1,100]}];const regions=h.run("chartBarRegions(document.querySelector('#chart-report'),window.qaBars)");
 assert.equal(regions.length,2);assert.ok(regions[0].bottom-regions[0].top>=24);assert.equal(regions[0].right,regions[1].left);assert.equal(JSON.stringify(node.data),before);
});

test('relatórios: acabamento e totais usam a seleção original sem reclassificar registros',async t=>{
 const h=await setup(t,'relatorios'),d=h.doc,select=d.querySelector('#report-type');
 for(const title of Object.keys(h.data.reports)){select.value=title;select.dispatchEvent(new h.w.Event('change'));await h.flush();const source=h.data.reports[title],grouped=source.length&&'grupo' in source[0],total=grouped?source.reduce((sum,row)=>sum+row.quantidade,0):source.length,n=d.querySelector('#chart-report');assert.equal(n.data[0].y.reduce((sum,n)=>sum+n,0),total);assert.equal(n.data[0].marker.color.length,n.data[0].x.length);assert.match(d.querySelector('#report-record-count').textContent,new RegExp('^'+source.length+' registros'));}
});

test('agenda seleciona data, navega meses, mostra dados reais e preserva indicadores',async t=>{
 const h=await setup(t,'dashboard'),doc=h.doc,event=h.data.agenda.events[0];assert.ok(event);
 const [year,month]=event.date.split('-').map(Number);h.run(`agendaYear=${year};agendaMonth=${month-1};renderCalendar();`);
 h.click('[data-date="'+event.date+'"]');
 assert.equal(doc.querySelector('[data-date="'+event.date+'"]').getAttribute('aria-pressed'),'true');
 assert.match(doc.querySelector('#agenda-detail').textContent,new RegExp(event.code));
 assert.ok(doc.querySelector('#agenda-detail a[href="/'+event.page+'?q='+event.code+'"]'));
 assert.equal(doc.querySelectorAll('.calendar-legend i').length,3);
 assert.equal(doc.querySelector('#secondary-kpis'),null);assert.equal(doc.querySelector('#attention-panel'),null);
 assert.ok(Object.hasOwn(h.data.indicators,'Pendentes'));assert.ok(h.data.agenda.attention.length);
 const previousHeading=doc.querySelector('.calendar-heading h3').textContent;h.click('[data-month-step="1"]');
 assert.notEqual(doc.querySelector('.calendar-heading h3').textContent,previousHeading);assert.equal(doc.activeElement.dataset.monthStep,'1');
 h.run("agendaDate='1900-01-01';renderAgendaDetail();");assert.match(doc.querySelector('#agenda-detail').textContent,/Nenhum acompanhamento/);
});

test('barras premium destacam somente a barra apontada sem modificar as vizinhas',async t=>{
 const h=await setup(t,'dashboard'),node=h.doc.querySelector('#chart-teams');
 const layer=h.doc.createElement('div');layer.className='barlayer';node.append(layer);
 for(let series=0;series<3;series++){
  const trace=h.doc.createElement('div');trace.className='trace';layer.append(trace);
  for(let j=0;j<2;j++){const point=h.doc.createElement('div');point.className='point';const path=h.doc.createElement('path');
   path.__rect={left:10+series*20+j*100,right:25+series*20+j*100,top:series===1?80:40,bottom:160,width:15,height:series===1?80:120};point.append(path);trace.append(point);}
 }
 h.run("bindChartInteraction(document.querySelector('#chart-teams'),chartState.get(document.querySelector('#chart-teams')))");
 const original=JSON.stringify(node.data);node.__events.plotly_hover({points:[{curveNumber:1,pointNumber:0,x:node.data[1].x[0],y:node.data[1].y[0],data:node.data[1]}],event:{clientX:35,clientY:100}});
 assert.equal(node.querySelectorAll('.is-bar-highlighted').length,1);assert.ok(node.querySelectorAll('.trace')[1].querySelector('path').classList.contains('is-bar-highlighted'));
 assert.equal(h.doc.querySelector('.chart-tooltip:not([hidden])').querySelectorAll('.chart-tooltip-row').length,1);
 node.__events.plotly_unhover();assert.equal(node.querySelectorAll('.is-bar-highlighted').length,0);assert.equal(JSON.stringify(node.data),original);
 assert.ok(node.data.every(trace=>trace.type==='bar'));
});

test('marcadores mantêm contorno e extremos sem clipping; datas preservam ISO',async t=>{
 const h=await setup(t,'dashboard');
 assert.ok(h.doc.querySelector('#chart-trend').data.every(trace=>trace.cliponaxis===false&&trace.marker.size===8&&trace.marker.line.width===2));
 h.click('#filters-button');await h.flush();const input=h.doc.querySelector('input[type=date]');assert.equal(input.lang,'pt-BR');
 input.value='2026-11-02';assert.equal(new h.w.FormData(input.form).get(input.name),'2026-11-02');assert.ok(input.getAttribute('aria-description'));
});

test('combobox obrigatório preserva validação nativa e limpa erro após seleção',async t=>{
 const h=await setup(t,'equipes'),doc=h.doc,form=doc.createElement('form');
 form.innerHTML='<label>Equipe<select name="team" required><option value="">Selecione</option><option value="EQ1">Tecnologia</option></select></label>';doc.body.append(form);h.w.DashboardControls.refresh();
 const select=form.querySelector('select'),input=form.querySelector('.select-input');
 assert.equal(select.checkValidity(),false);assert.equal(input.getAttribute('aria-invalid'),'true');
 input.click();input.dispatchEvent(new h.w.KeyboardEvent('keydown',{key:'ArrowDown',bubbles:true,cancelable:true}));input.dispatchEvent(new h.w.KeyboardEvent('keydown',{key:'Enter',bubbles:true,cancelable:true}));
 assert.equal(select.value,'EQ1');assert.equal(form.checkValidity(),true);assert.equal(new h.w.FormData(form).get('team'),'EQ1');
});

for(const page of ['funcionarios','equipes','ordens-servico','acessos','vencimentos','renovacoes']){
 test('listas fechadas ao abrir filtros e cadastro: '+page,async t=>{
  const h=await setup(t,page),doc=h.doc;
  for(const button of ['#filters-button','#new','edit']){
   if(button==='edit')h.run('editRecord(state.rows[0])');else h.click(button);await h.flush();
   for(const input of doc.querySelectorAll('#modal .select-input')){
    const selected=input.value;input.focus();assert.equal(input.getAttribute('aria-expanded'),'false');
    input.click();assert.equal(input.getAttribute('aria-expanded'),'true');
    doc.querySelector('#modal-title').dispatchEvent(new h.w.MouseEvent('pointerdown',{bubbles:true}));
    assert.equal(input.getAttribute('aria-expanded'),'false');assert.equal(input.value,selected);
    input.value='__pesquisa__';input.dispatchEvent(new h.w.Event('input',{bubbles:true}));
    if(input.readOnly){assert.equal(input.value,selected);assert.equal(input.getAttribute('aria-expanded'),'false');}else{assert.equal(input.value,'__pesquisa__');assert.match(doc.querySelector('.select-popup:not([hidden])').textContent,/Nenhuma/);}
    input.dispatchEvent(new h.w.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true}));
    assert.equal(input.value,selected);assert.equal(doc.querySelector('#modal').open,true);
   }
   await h.close();
  }
 });
}
test('linhas: margens, meses extremos, resolucoes e dados preservados',async t=>{
 const h=await setup(t,'dashboard');
 for(const width of [320,600,1200]){
  const result=h.run(`lineAxisLayout([{type:'scatter',x:['2026-05','2026-06','2026-07','2026-08','2026-09','2026-10']}],${width},1.1)`);
  assert.ok(Date.parse(result.range[0])<Date.parse('2026-05'));
  assert.ok(Date.parse(result.range[1])>Date.parse('2026-10'));
  assert.equal(result.tickvals[0],'2026-05');assert.equal(result.tickvals.at(-1),'2026-10');
  assert.match(result.ticktext.at(-1),/out/);assert.equal(result.tickvals.at(-1),'2026-10');
 }
 const node=h.doc.querySelector('#chart-trend');const before=JSON.stringify(node.data.map(t=>({x:t.x,y:t.y})));
 h.click('[data-chart="trend"]');await h.flush();
 const expanded=h.doc.querySelector('#modal .plot');
 assert.equal(JSON.stringify(expanded.data.map(t=>({x:t.x,y:t.y}))),before);
 assert.equal(expanded.layout.xaxis.ticklabelstandoff,12);
});


test('central: pesquisa, período, categorias, paginação, seleção e confirmação de limpeza',async t=>{
 const notifications=Array.from({length:9},(_,i)=>({id:i+1,title:i===0?'<script>texto</script>':'Aviso '+i,message:'Mensagem '+i,kind:'operational',link:i===0?'javascript:alert(1)':'/acessos',occurred:new Date(Date.now()-i*86400000).toISOString(),read_at:i>6?new Date().toISOString():null}));
 const h=await setup(t,'perfil',{notifications}),d=h.doc;
 h.click('#notifications-button');await h.flush();assert.equal(d.querySelectorAll('.notification-row').length,6);assert.equal(d.querySelector('.notification-copy script'),null);assert.equal(d.querySelector('.notification-row').querySelector('a'),null);
 const search=d.querySelector('.notification-search [type=search]');search.value='Mensagem 1';search.dispatchEvent(new h.w.Event('input'));assert.equal(d.querySelectorAll('.notification-row').length,1);
 search.value='';search.dispatchEvent(new h.w.Event('input'));const period=d.querySelector('select[aria-label="Período das notificações"]');period.value='1';period.dispatchEvent(new h.w.Event('change'));assert.equal(d.querySelectorAll('.notification-row').length,1);
 period.value='0';period.dispatchEvent(new h.w.Event('change'));d.querySelectorAll('.notification-category')[2].click();assert.equal(d.querySelectorAll('.notification-row').length,2);
 d.querySelectorAll('.notification-category')[0].click();h.click('[aria-label="Próxima página"]');assert.equal(d.querySelectorAll('.notification-row').length,3);h.click('[aria-label="Página anterior"]');
 d.querySelector('.notification-row input').click();[...d.querySelectorAll('.notification-toolbar button')].find(b=>b.textContent.includes('seleção')).click();await h.flush();assert.equal(d.querySelector('#notifications-count').textContent,'6');assert.equal(h.requests.filter(r=>r.method==='POST'&&r.url==='/api/notifications/1').length,1);
 d.querySelectorAll('.notification-toolbar button')[1].click();assert.match(d.querySelector('.notification-confirm').textContent,/Limpar sua central/);[...d.querySelectorAll('.notification-confirm button')].find(b=>b.textContent==='Cancelar').click();assert.equal(h.data.notifications.length,9);
 d.querySelectorAll('.notification-toolbar button')[1].click();[...d.querySelectorAll('.notification-confirm button')].find(b=>b.textContent==='Confirmar limpeza').click();await h.flush();assert.equal(h.data.notifications.length,0);assert.match(d.querySelector('.notification-empty').textContent,/Você está em dia/);
});


test('sidebar: estado por usuário restaura antes de attach e não altera aparência nem APIs',async t=>{
 const h=await setup(t,'funcionarios',{sidebar:'collapsed',preferences:{theme:'dark'}}),d=h.doc;
 assert.equal(d.documentElement.dataset.sidebar,'collapsed');assert.ok(d.querySelector('.shell').classList.contains('collapsed'));assert.equal(d.querySelector('#menu-toggle').getAttribute('aria-expanded'),'false');
 const count=h.requests.length;h.click('#menu-toggle');assert.equal(d.documentElement.dataset.sidebar,'expanded');assert.equal(h.w.localStorage.getItem(h.w.DashboardSidebar.key),'expanded');assert.equal(d.documentElement.dataset.theme,'dark');assert.equal(h.requests.length,count);
 h.run("DashboardSidebar.set(true)");assert.equal(h.w.localStorage.getItem(h.w.DashboardSidebar.key),'collapsed');
 const next=await setup(t,'equipes',{sidebar:h.w.localStorage.getItem(h.w.DashboardSidebar.key)});assert.equal(next.doc.querySelector('#menu-toggle').getAttribute('aria-expanded'),'false');next.click('#menu-toggle');
 const expanded=await setup(t,'acessos',{sidebar:next.w.localStorage.getItem(next.w.DashboardSidebar.key)});assert.equal(expanded.doc.querySelector('#menu-toggle').getAttribute('aria-expanded'),'true');assert.equal(h.w.DashboardPreferences.key.includes('appearance:v1:'),true);
});

test('linhas: domínio Y estável no hover sem novos desenhos ou alteração dos dados',async t=>{
 const h=await setup(t,'dashboard',{multiLine:true}),node=h.doc.querySelector('#chart-trend'),before=structuredClone(node.layout),values=structuredClone(node.data.map(t=>({x:t.x,y:t.y}))),draws=h.plots.length;
 assert.equal(node.layout.yaxis.autorange,false);const finite=values.flatMap(t=>t.y).filter(Number.isFinite);assert.ok(node.layout.yaxis.range[0]<=Math.min(...finite));assert.ok(node.layout.yaxis.range[1]>Math.max(...finite));
 assert.deepEqual(Array.from(h.run("lineValueAxis([{type:'scatter',y:[40,30,0]}]).range")),[0,44]);
 for(const [i,j] of [[0,0],[0,2],[1,3],[0,5],[1,5]]){
  node.__events.plotly_hover({points:[{curveNumber:i,pointNumber:j,x:node.data[i].x[j],y:node.data[i].y[j],data:node.data[i]}],event:{clientX:500,clientY:200}});
  assert.deepEqual(structuredClone(node.layout),before);node.__events.plotly_unhover();
 }
 assert.equal(h.plots.length,draws);assert.deepEqual(structuredClone(node.data.map(t=>({x:t.x,y:t.y}))),values);
 assert.equal(node.__restyles?.length||0,0,'Hover deve permanecer fora da fila de desenho do Plotly.');
 assert.deepEqual(Array.from(h.run("lineValueAxis([{type:'scatter',y:[-5,10,null]}]).range")),[-6.5,11.5]);assert.ok(h.run("lineValueAxis([{type:'scatter',y:[0]}]).range[1]>0"));
});

test('gráfico: falha de desenho restaura último estado válido e permite nova tentativa',async t=>{
 const h=await setup(t,'dashboard'),n=h.doc.querySelector('#chart-trend'),valid=JSON.stringify(n.data),react=h.w.Plotly.react;
 let fail=true;h.w.Plotly.react=async(...args)=>{if(fail){fail=false;throw new Error('falha simulada de desenho');}return react(...args);};
 await h.run("drawChart(document.querySelector('#chart-trend'),chartSpecs.trend)");
 assert.equal(JSON.stringify(n.data),valid);assert.equal(n.dataset.chartError,'true');assert.equal(h.run("chartState.get(document.querySelector('#chart-trend')).busy"),false);
 await h.run("drawChart(document.querySelector('#chart-trend'),chartSpecs.trend)");assert.equal(n.dataset.chartError,undefined);assert.equal(JSON.stringify(n.data),valid);
});

test('ícones: catálogo SVG único em ações, modal, tabela, perfil e notificações',async t=>{
 const h=await setup(t,'funcionarios'),d=h.doc;
 for(const selector of ['#refresh','#filters-button','#export','#new','#menu-toggle','#modal-close','#prev','#next','.row-actions button']){
  const svg=d.querySelector(selector+' svg.ui-icon');assert.ok(svg,selector);assert.equal(svg.getAttribute('viewBox'),'0 0 24 24');assert.equal(svg.getAttribute('stroke-width'),'1.8');assert.equal(svg.getAttribute('aria-hidden'),'true');assert.equal(svg.getAttribute('focusable'),'false');
 }
 h.click('#new');await h.flush();assert.ok(d.querySelector('.form-actions button svg.ui-icon'));await h.close();
 const p=await setup(t,'perfil');assert.equal(p.doc.querySelectorAll('.profile-symbol svg.ui-icon').length,5);p.click('#notifications-button');await p.flush();assert.ok(p.doc.querySelector('.notification-header-icon svg.ui-icon'));assert.equal(p.doc.querySelectorAll('.notification-header-icon').length,1);await p.close();await p.w.DashboardProfile.selectTab('preferences');assert.equal(p.doc.querySelector('#profile-panel-preferences .notification-header-icon'),null);assert.equal(p.doc.querySelector('#profile-panel-preferences').hidden,false);
});


test('linhas: período compartilhado mantém séries visíveis sem alterar domínio',async t=>{
 const h=await setup(t,'dashboard',{multiLine:true}),n=h.doc.querySelector('#chart-trend'),range=Array.from(n.layout.yaxis.range),layer=h.doc.createElement('div');layer.className='scatterlayer';
 for(let i=0;i<2;i++){const group=h.doc.createElementNS('http://www.w3.org/2000/svg','g');group.setAttribute('class','trace');layer.append(group);}n.append(layer);
 const point=i=>({points:[{curveNumber:i,pointNumber:0,x:n.data[i].x[0],y:n.data[i].y[0],data:n.data[i]}],event:{clientX:200,clientY:100}});
 n.__events.plotly_hover(point(0));await h.flush();assert.equal(layer.children[0].style.opacity,'');assert.equal(layer.children[1].style.opacity,'');
 n.__events.plotly_hover(point(1));n.__events.plotly_unhover();await h.flush();assert.equal(layer.children[0].style.opacity,'');assert.equal(layer.children[1].style.opacity,'');assert.deepEqual(Array.from(n.layout.yaxis.range),range);
});

test('hover por período agrega os valores reais de todas as séries no cartão e modal',async t=>{
 const h=await setup(t,'dashboard'),d=h.doc,node=d.querySelector('#chart-trend'),original=JSON.stringify(node.data);
 const verify=n=>{assert.equal(n.layout.hovermode,'x');const j=1,trace=n.data[0];n.__events.plotly_hover({points:[{curveNumber:0,pointNumber:j,x:trace.x[j],data:trace}],event:{clientX:400,clientY:250}});const tip=[...d.querySelectorAll('.chart-tooltip')].find(t=>!t.hidden),rows=tip.querySelectorAll('.chart-tooltip-row');assert.equal(rows.length,n.data.length);n.data.forEach((t,i)=>assert.ok(rows[i].textContent.includes(String(t.y[j]))));n.__events.plotly_unhover();};
 verify(node);assert.equal(JSON.stringify(node.data),original);h.click('[data-chart="trend"]');await h.flush();verify(d.querySelector('#modal-body .plot'));await h.close();
});

test('perfil: edição começa bloqueada, detecta alterações e cancelar restaura os dados',async t=>{
 const h=await setup(t,'perfil'),d=h.doc,f=d.querySelector('#profile-info-form'),original=f.elements.display_name.value;
 assert.equal(f.elements.display_name.readOnly,true);assert.equal(d.querySelector('[data-save-account]').hidden,true);
 d.querySelector('[data-edit-account]').click();assert.equal(f.elements.display_name.readOnly,false);assert.equal(d.querySelector('[data-save-account]').disabled,true);
 f.elements.display_name.value='Novo nome';f.elements.display_name.dispatchEvent(new h.w.Event('input',{bubbles:true}));assert.equal(d.querySelector('[data-save-account]').disabled,false);
 f.elements.display_name.value=original;f.elements.display_name.dispatchEvent(new h.w.Event('input',{bubbles:true}));assert.equal(d.querySelector('[data-save-account]').disabled,true);
 f.elements.display_name.value='Rascunho';f.elements.display_name.dispatchEvent(new h.w.Event('input',{bubbles:true}));d.querySelector('[data-cancel-account]').click();assert.equal(f.elements.display_name.value,original);assert.equal(f.elements.display_name.readOnly,true);assert.equal(d.querySelector('[data-cancel-account]').hidden,true);
});

test('perfil: troca de aba pede confirmação e preserva rascunho ao continuar',async t=>{
 const h=await setup(t,'perfil'),d=h.doc,f=d.querySelector('#profile-info-form');d.querySelector('[data-edit-account]').click();f.elements.display_name.value='Rascunho';f.elements.display_name.dispatchEvent(new h.w.Event('input',{bubbles:true}));
 d.querySelector('#profile-tab-security').click();await h.flush();assert.match(d.querySelector('.discard-confirmation').textContent,/alterações não salvas/);
 [...d.querySelectorAll('.discard-confirmation button')].find(b=>b.textContent==='Continuar editando').click();await h.flush();assert.equal(f.elements.display_name.value,'Rascunho');assert.equal(d.querySelector('#profile-tab-account').getAttribute('aria-selected'),'true');
 d.querySelector('#profile-tab-security').click();await h.flush();[...d.querySelectorAll('.discard-confirmation button')].find(b=>b.textContent==='Descartar alterações').click();await h.flush();assert.equal(d.querySelector('#profile-tab-security').getAttribute('aria-selected'),'true');assert.equal(h.w.DashboardProfile.hasUnsavedChanges(),false);
});

test('perfil: falha de salvamento mantém a edição e os dados digitados',async t=>{
 const h=await setup(t,'perfil'),d=h.doc,f=d.querySelector('#profile-info-form');d.querySelector('[data-edit-account]').click();f.elements.display_name.value='Preservar rascunho';f.elements.display_name.dispatchEvent(new h.w.Event('input',{bubbles:true}));h.networkError=true;
 f.dispatchEvent(new h.w.Event('submit',{cancelable:true,bubbles:true}));await h.flush();assert.equal(f.elements.display_name.value,'Preservar rascunho');assert.equal(f.elements.display_name.readOnly,false);assert.match(f.querySelector('.form-error').textContent,/conectar/);assert.equal(h.w.DashboardProfile.hasUnsavedChanges(),true);
});

test('perfil: e-mail pendente preserva o anterior, internas não têm opt-out e atividades têm estado vazio',async t=>{
 const h=await setup(t,'perfil'),d=h.doc,old=h.data.profile.email;d.querySelector('#profile-tab-email').click();await h.flush();assert.equal(d.querySelector('[name=internal_alerts]'),null);assert.match(d.querySelector('.always-on').textContent,/Sempre ativas/);
 const f=d.querySelector('#profile-email-form');f.elements.email.value='pending@example.test';f.elements.current_password.value='fictional-password';f.dispatchEvent(new h.w.Event('submit',{bubbles:true,cancelable:true}));await h.flush();assert.equal(h.data.profile.email,old);assert.match(d.querySelector('.pending-email').textContent,/pending@example.test/);assert.match(d.querySelector('.mail-notice').textContent,/Nenhum e-mail/);
 d.querySelector('#profile-tab-activities').click();await h.flush();assert.match(d.querySelector('.activity-empty').textContent,/Nenhuma atividade/);assert.ok(h.requests.some(r=>r.url.startsWith('/api/profile/activities?')));
});

test('perfil: preferência legada de e-mail pode ser desativada sem verificação e não impede salvar aparência',async t=>{
 const h=await setup(t,'perfil',{profileState:{verified:0,email_alerts:1}}),d=h.doc,f=d.querySelector('#profile-preferences-form');
 assert.equal(f.elements.email_alerts.checked,true);assert.equal(f.elements.email_alerts.disabled,false);
 h.w.DashboardPreferences.set({theme:'dark'});f.dispatchEvent(new h.w.Event('submit',{bubbles:true,cancelable:true}));await h.flush();
 const first=h.requests.find(r=>r.url==='/api/profile'&&r.method==='PUT');assert.equal(Object.hasOwn(JSON.parse(first.body),'email_alerts'),false);
 f.elements.email_alerts.checked=false;f.dispatchEvent(new h.w.Event('submit',{bubbles:true,cancelable:true}));await h.flush();
 assert.equal(h.data.profile.email_alerts,false);assert.equal(f.elements.email_alerts.disabled,true);
});


test('etapa B: carregar, editar, focar e trocar abas sem mudanças não cria pendências',async t=>{
 const h=await setup(t,'perfil'),d=h.doc,dirty=()=>h.w.DashboardProfile.hasUnsavedChanges();
 assert.equal(dirty(),false);d.querySelector('[data-edit-account]').click();assert.equal(dirty(),false);
 d.querySelector('#profile-info-form').elements.display_name.focus();assert.equal(dirty(),false);
 for(const tab of ['security','email','activities','account']){await h.w.DashboardProfile.selectTab(tab);assert.equal(dirty(),false);assert.equal(d.querySelector('.discard-confirmation'),null);}
 const event=new h.w.Event('beforeunload',{cancelable:true});h.w.dispatchEvent(event);assert.equal(event.defaultPrevented,false);
});

test('etapa B: autofill oculto não cria pendência; edição de senha visível e reversão funcionam',async t=>{
 const h=await setup(t,'perfil'),d=h.doc,f=d.querySelector('#profile-security-form'),dirty=()=>h.w.DashboardProfile.hasUnsavedChanges();
 f.elements.current_password.value='fictional-autofill';f.elements.current_password.dispatchEvent(new h.w.Event('input',{bubbles:true}));assert.equal(dirty(),false);
 await h.w.DashboardProfile.selectTab('security');assert.equal(dirty(),false);
 [...d.querySelectorAll('#profile-panel-security button')].find(b=>b.textContent.includes('Alterar senha')).click();assert.equal(dirty(),false);
 f.elements.password.value='fictional-new-password';f.elements.password.dispatchEvent(new h.w.Event('input',{bubbles:true}));assert.equal(dirty(),true);
 f.elements.password.value='';f.elements.password.dispatchEvent(new h.w.Event('input',{bubbles:true}));assert.equal(dirty(),false);
 f.elements.password.value='fictional-new-password';f.elements.password.dispatchEvent(new h.w.Event('input',{bubbles:true}));[...f.querySelectorAll('button')].find(b=>b.textContent==='Cancelar').click();assert.equal(dirty(),false);
});

test('etapa B: salvar atualiza referência, revertendo desabilita salvar e navegação protege edição real',async t=>{
 const h=await setup(t,'perfil'),d=h.doc,f=d.querySelector('#profile-info-form'),dirty=()=>h.w.DashboardProfile.hasUnsavedChanges();
 d.querySelector('[data-edit-account]').click();const original=f.elements.display_name.value;
 const name=value=>{f.elements.display_name.value=value;f.elements.display_name.dispatchEvent(new h.w.Event('input',{bubbles:true}));};
 name('Nome da etapa B');assert.equal(dirty(),true);assert.equal(d.querySelector('[data-save-account]').disabled,false);
 const event=new h.w.Event('beforeunload',{cancelable:true});h.w.dispatchEvent(event);assert.equal(event.defaultPrevented,true);
 name(original);assert.equal(dirty(),false);assert.equal(d.querySelector('[data-save-account]').disabled,true);
 name('Nome da etapa B');f.dispatchEvent(new h.w.Event('submit',{bubbles:true,cancelable:true}));await h.flush();assert.equal(dirty(),false);assert.equal(f.elements.display_name.readOnly,true);
 d.querySelector('[data-edit-account]').click();assert.equal(dirty(),false);assert.equal(d.querySelector('[data-save-account]').disabled,true);
});

test('etapa B: avatar superior visual, inferior editável e atalho só fora do perfil',async t=>{
 const h=await setup(t,'perfil'),d=h.doc,hero=d.querySelector('.profile-hero [data-account-avatar]'),lower=d.querySelector('.profile-photo-row [data-account-avatar]');
 assert.equal(hero.tagName,'DIV');assert.equal(hero.onclick,null);assert.equal(hero.querySelector('.camera-badge'),null);assert.equal(hero.classList.contains('profile-photo-button'),false);
 assert.equal(lower.tagName,'BUTTON');assert.ok(lower.querySelector('.camera-badge'));assert.equal(typeof lower.onclick,'function');assert.equal(d.querySelector('.header-right [data-account-avatar]'),null);assert.ok(d.querySelector('#notifications-button'));assert.equal(d.querySelector('#today'),null);
 const other=await setup(t,'funcionarios');assert.ok(other.doc.querySelector('.header-right a[data-account-avatar][href="/perfil"]'));
});

test('etapa B: e-mail e preferências comparam edição explícita, restauração e cancelamento',async t=>{
 const h=await setup(t,'perfil'),d=h.doc,dirty=()=>h.w.DashboardProfile.hasUnsavedChanges(),f=d.querySelector('#profile-email-form');
 f.elements.current_password.value='fictional-autofill';assert.equal(dirty(),false);await h.w.DashboardProfile.selectTab('email');assert.equal(dirty(),false);
 f.elements.email.value='fictional@example.test';f.elements.email.dispatchEvent(new h.w.Event('input',{bubbles:true}));assert.equal(dirty(),true);
 [...f.querySelectorAll('button')].find(b=>b.textContent==='Cancelar edição').click();assert.equal(dirty(),false);
 const prefs=d.querySelector('#profile-preferences-form'),toggle=prefs.elements.email_alerts,original=toggle.checked;toggle.checked=!original;toggle.dispatchEvent(new h.w.Event('change',{bubbles:true}));assert.equal(dirty(),true);
 toggle.checked=original;toggle.dispatchEvent(new h.w.Event('change',{bubbles:true}));assert.equal(dirty(),false);
});


test('etapa C: recolher revela submenus e expandir restaura a escolha do usuário',async t=>{
 const h=await setup(t,'perfil'),d=h.doc,group=d.querySelector('.sidebar-group');group.open=false;
 const links=[...d.querySelectorAll('.sidebar a')].map(a=>a.getAttribute('href')),requests=h.requests.length;
 h.w.DashboardSidebar.set(true);assert.equal(group.open,true);assert.equal(d.querySelector('#menu-toggle').getAttribute('aria-expanded'),'false');
 h.w.DashboardSidebar.set(false);assert.equal(group.open,false);assert.deepEqual([...d.querySelectorAll('.sidebar a')].map(a=>a.getAttribute('href')),links);assert.equal(h.requests.length,requests);
});

test('etapa C: menu móvel preserva preferência desktop, rotas e ações',async t=>{
 const h=await setup(t,'perfil',{mobile:true,sidebar:'collapsed'}),d=h.doc,root=d.documentElement,key=h.w.DashboardSidebar.key;
 assert.equal(root.dataset.mobileMenu,'closed');const requests=h.requests.length;
 h.click('#menu-toggle');assert.equal(root.dataset.mobileMenu,'open');assert.equal(d.querySelector('#menu-toggle').getAttribute('aria-expanded'),'true');assert.equal(h.w.localStorage.getItem(key),'collapsed');
 for(const route of ['/dashboard','/funcionarios','/equipes','/ordens-servico','/acessos','/vencimentos','/renovacoes','/relatorios','/perfil'])assert.ok(d.querySelector('.sidebar a[href="'+route+'"]'),route);
 assert.equal(d.querySelector('.sidebar form[action="/auth/guest"]'),null);assert.ok(d.querySelector('.sidebar form[action="/auth/logout"] input[name=csrf_token]'));
 h.click('#menu-toggle');assert.equal(root.dataset.mobileMenu,'closed');h.mediaState.mobile=false;h.mediaListeners['(max-width: 600px)']();assert.equal(root.dataset.mobileMenu,undefined);assert.equal(root.dataset.sidebar,'collapsed');assert.equal(h.requests.length,requests);
});

test('etapa C: teclado das quatro abas mantém seleção, foco e painel acessível',async t=>{
 const h=await setup(t,'perfil'),d=h.doc;
 for(const [from,key,to] of [['account','ArrowRight','security'],['security','End','activities'],['activities','Home','account'],['account','ArrowLeft','activities']]){
  d.querySelector('#profile-tab-'+from).dispatchEvent(new h.w.KeyboardEvent('keydown',{key,bubbles:true,cancelable:true}));await h.flush();
  const selected=d.querySelector('#profile-tab-'+to);assert.equal(selected.getAttribute('aria-selected'),'true');assert.equal(selected.tabIndex,0);assert.equal(d.activeElement,selected);assert.equal(d.querySelector('#profile-panel-'+to).hidden,false);assert.equal(d.querySelectorAll('[role=tab][aria-selected=true]').length,1);assert.equal(h.w.DashboardProfile.hasUnsavedChanges(),false);
 }
});
