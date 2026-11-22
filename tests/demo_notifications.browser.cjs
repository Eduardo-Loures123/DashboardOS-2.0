// Playwright tool entry point. Run against a NEW standalone P5-A localhost:5095.
// Interacts exclusively with authenticated fictional demo routes, never app.py.
async (page) => {
 const errors=[],failed=[];
 page.on('pageerror',e=>errors.push(e.message));
 page.on('requestfailed',r=>{if(r.failure()?.errorText!=='net::ERR_ABORTED')failed.push(r.url());});
 const assert=(value,message)=>{if(!value)throw Error(message);};
 const password='Demo-Notificacoes-2026!';
 async function login(uid){
  await page.waitForFunction(()=>!document.body.classList.contains('busy'));
  await page.goto('http://127.0.0.1:5095/');
  if(await page.getByRole('button',{name:'Trocar conta'}).count())await page.getByRole('button',{name:'Trocar conta'}).click();
  await page.locator('select[name=uid]').selectOption(uid);
  await page.locator('input[name=password]').fill(password);
  await page.getByRole('button',{name:'Entrar na demonstração'}).click();
  await page.locator('#clock').filter({hasText:/\d{2}:\d{2}/}).waitFor();
 }
 const matrix=[];
 await page.setViewportSize({width:1366,height:900});
 await login('root');
 assert(await page.locator('#events').innerText()==='0','Baseline emitted retroactive event');
 await page.locator('#order-status').selectOption('Em andamento');
 await page.getByRole('button',{name:'Confirmar alteração fictícia'}).click();
 await page.locator('#events').filter({hasText:'1'}).waitFor();
 await page.getByRole('button',{name:'Repetir última operação'}).click();
 await page.locator('#message').filter({hasText:'mesmo recibo'}).waitFor();
 assert(await page.locator('#operations').innerText()==='1','Duplicate operation');
 await page.getByRole('button',{name:'Simular 09:00',exact:true}).click();
 await page.locator('#clock').filter({hasText:'09:00'}).waitFor();
 await page.getByRole('button',{name:'Preparar resumo',exact:true}).click();
 await page.locator('#digests-count').filter({hasText:'3'}).waitFor();
 await page.getByRole('button',{name:'Simular entrega',exact:true}).click();
 await page.locator('#outbox').filter({hasText:'Entrega simulada'}).waitFor();
 await page.getByRole('button',{name:'Simular entrega',exact:true}).click();
 await page.locator('#message').filter({hasText:'0 entrega'}).waitFor();
 for(const [width,height] of [[1920,1080],[1366,768],[390,844]]){
  await page.setViewportSize({width,height});
  const layout=await page.evaluate(()=>({width:innerWidth,overflow:document.documentElement.scrollWidth>innerWidth}));
  assert(!layout.overflow,'Horizontal overflow: '+width);matrix.push(layout);
 }
 await page.setViewportSize({width:1366,height:900});
 await login('alice');assert(await page.locator('#notices .record').count()===1,'Alice did not receive notice');
 await login('somente-email');assert(await page.locator('#notices .record').count()===0,'Email grant leaked internal notice');
 assert(await page.locator('#outbox .record').count()===1,'Email-only account missing simulated digest');
 await login('bob');assert(await page.locator('#notices .record').count()===0,'Wrong team saw notice');
 assert(await page.locator('#outbox .record').count()===0,'Wrong team received digest');
 assert(await page.locator('#order-form').count()===0,'Non-admin saw operation form');
 await login('root');
 await page.getByRole('button',{name:'Próximo dia · 08:55',exact:true}).click();
 await page.locator('#notices').filter({hasText:'7 dias'}).waitFor();
 await page.getByRole('button',{name:'Recuperação · 11:30',exact:true}).click();
 await page.locator('#clock').filter({hasText:'11:30'}).waitFor();
 await page.getByRole('button',{name:'Preparar resumo',exact:true}).click();
 await page.locator('#digests-count').filter({hasText:'6'}).waitFor();
 await page.locator('.user-card').filter({has:page.locator('strong',{hasText:/^alice$/})}).getByRole('button',{name:'Revogar',exact:true}).click();
 await page.locator('#message').filter({hasText:'Restrição aplicada'}).waitFor();
 await page.getByRole('button',{name:'Simular entrega',exact:true}).click();
 await page.locator('#message').filter({hasText:'2 entrega'}).waitFor();
 const state=await page.evaluate(async()=>await (await fetch('/demo/api/state')).json());
 assert(state.legacy.length===5&&state.legacy.every(r=>r.status==='pending'&&r.attempts===0),'Legacy was changed');
 await login('alice');assert(await page.locator('#notices .record').count()===0,'Revoked user retained details');
 assert((await page.locator('#outbox').innerText()).includes('Cancelado na revalidação'),'Revoked digest not cancelled');
 assert(errors.length===0,'Browser exceptions: '+errors.join(','));assert(failed.length===0,'Failed requests: '+failed.join(','));
 return {matrix,errors,failed,confirmedOperations:state.operations,events:state.events,legacy:state.legacy.length,flow:'OS → evento → Central → resumo → entrega simulada → repetição → 7 dias → revogação'};
}
