// Playwright tool entry point. Serve the project read-only on localhost:5010.
// Every /api request is fulfilled here; no real authentication/write route is used.
async (page) => {
 const base='http://127.0.0.1:5010',assert=(condition,message)=>{if(!condition)throw Error(message);};
 await page.unrouteAll();
 const profile=(await (await page.request.get(base+'/tests/fixtures/perfil.json')).json()).profile;
 const dashboard=await (await page.request.get(base+'/tests/fixtures/dashboard.json')).json();
 const now=new Date().toISOString(),fixture={deletes:0,activities:60,notifications:80};
 await page.route('**/api/**',async route=>{
  const request=route.request(),url=new URL(request.url());let data={};
  if(url.pathname==='/api/profile')data=profile;
  else if(url.pathname==='/api/profile/activities'){
   const rows=Array.from({length:fixture.activities},(_,i)=>({operation:i%2?'update':'create',summary:'Operação fictícia · Ordens de serviço',record_code:'OS'+String(i+1).padStart(4,'0'),occurred:Date.now()/1000-i*60})).filter(r=>(!url.searchParams.get('q')||r.record_code.includes(url.searchParams.get('q')))&&(!url.searchParams.get('operation')||r.operation===url.searchParams.get('operation')));
   const number=Number(url.searchParams.get('page')||1);data={activities:rows.slice((number-1)*20,number*20),total:rows.length};
  }else if(url.pathname.startsWith('/api/notifications')){
   if(request.method()==='POST'&&request.postDataJSON().action==='delete'){fixture.deletes++;await new Promise(resolve=>setTimeout(resolve,100));fixture.notifications=0;}
   data={notifications:Array.from({length:fixture.notifications},(_,i)=>({id:i+1,title:'Notificação de teste '+(i+1),message:'Notificação fictícia para verificar seleção estável, rolagem e ações preservadas. '.repeat(3),kind:'operational',occurred:now,link:'/acessos?q=AC0001',read_at:i%3===0?now:null})),unread:fixture.notifications};
  }else if(url.pathname==='/api/data/dashboard')data=dashboard;
  await route.fulfill({json:data});
 });
 const matrix=[];
 for(const [width,height] of [[1920,1080],[1366,768],[1280,720]]){
  await page.setViewportSize({width,height});
  for(const theme of ['light','dark']){
   await page.goto(base+'/tests/fixtures/perfil.html');
   await page.locator('#profile-tab-activities').waitFor();await page.evaluate(t=>DashboardPreferences.set({theme:t}),theme);
   await page.locator('#profile-tab-activities').click();await page.locator('.activity-item').first().waitFor();await page.waitForTimeout(300);
   await page.waitForFunction(()=>document.querySelector('#profile-activity-pagination').getBoundingClientRect().bottom<=innerHeight,null,{timeout:3000});
   const activities=await page.evaluate(()=>{
    const list=document.querySelector('#profile-activity-results'),box=list.getBoundingClientRect(),footer=document.querySelector('#profile-activity-pagination');
    const full=[...list.children].filter(item=>{const rect=item.getBoundingClientRect();return rect.top>=box.top&&rect.bottom<=box.bottom;}).length;
    const before=footer.getBoundingClientRect().top;list.scrollTop=list.scrollHeight;
    return {height:list.clientHeight,fullRows:full,footerStable:Math.abs(before-footer.getBoundingClientRect().top)<1,footerBottom:footer.getBoundingClientRect().bottom,viewport:innerHeight};
   });
   assert(activities.footerStable,'Activity footer moved');assert(activities.fullRows>=3,'Activity history is too short');
   await page.locator('#notifications-button').click();await page.locator('.notification-row').first().waitFor();await page.waitForTimeout(250);
   const selection=await page.evaluate(()=>{
    const list=document.querySelector('.notification-results'),cards=[...list.children];list.scrollTop=100;
    cards[0].querySelector('input').click();cards[1].querySelector('input').click();cards[0].querySelector('input').click();
    const all=document.querySelector('.notification-select-all input');all.click();all.click();
    return {sameCards:cards.every((card,i)=>card===list.children[i]),scrollTop:list.scrollTop};
   });
   assert(selection.sameCards&&selection.scrollTop===100,'Selection rebuilt or scrolled cards');
   const footerBefore=await page.locator('.notification-footer').boundingBox();
   for(let repeat=0;repeat<3;repeat++){
    await page.getByRole('button',{name:'Limpar central',exact:true}).click();await page.locator('.confirmation-dialog').waitFor();await page.waitForTimeout(250);
    const confirmation=await page.locator('.confirmation-dialog').evaluate(dialog=>{
     const icon=dialog.querySelector('.confirmation-title svg').getBoundingClientRect(),buttons=[...dialog.querySelectorAll('.form-actions button')].map(b=>b.getBoundingClientRect());
     return {icon:{width:icon.width,height:icon.height},gap:buttons[1].left-buttons[0].right,heights:buttons.map(b=>b.height),width:dialog.getBoundingClientRect().width};
    });
    assert(confirmation.icon.width===24&&confirmation.icon.height===24,'Confirmation icon size');assert(confirmation.gap>=12,'Confirmation button spacing');assert(confirmation.heights[0]===confirmation.heights[1],'Confirmation button heights');
    await page.locator('.confirmation-dialog').getByRole('button',{name:'Cancelar',exact:true}).click();
   }
   const footerAfter=await page.locator('.notification-footer').boundingBox();assert(Math.abs(footerBefore.y-footerAfter.y)<1,'Confirmation moved central footer');
   assert(fixture.deletes===0,'Cancel triggered deletion');
   matrix.push({width,height,theme,activities,selection,confirmationStable:true});
   if(width===1366&&theme==='dark'){
    await page.getByRole('button',{name:'Limpar central',exact:true}).click();await page.waitForTimeout(250);await page.screenshot({path:'interface-confirm-dark.png'});
    await page.locator('.confirmation-dialog').getByRole('button',{name:'Cancelar',exact:true}).click();
   }
   await page.locator('#modal-close').click();await page.locator('#modal').waitFor({state:'hidden'});
   if(width===1366&&theme==='dark')await page.screenshot({path:'interface-activities-dark.png'});
  }
 }
 await page.locator('#notifications-button').click();await page.locator('.notification-row').first().waitFor();
 await page.getByRole('button',{name:'Limpar central',exact:true}).click();
 await page.locator('.confirmation-dialog').getByRole('button',{name:'Confirmar limpeza',exact:true}).evaluate(button=>{button.click();button.click();});
 await page.locator('.confirmation-dialog').waitFor({state:'detached'});assert(fixture.deletes===1,'Duplicate cleanup request');
 assert(await page.locator('.notification-empty').count()===1,'Cleanup result missing');
 return {matrix,mockedCleanupRequests:fixture.deletes,realBackendRequests:0};
}
