function buildPreferencesPanel(saveToAccount=false){
 const panel=el('div',{class:'settings-panel'});
 const current=DashboardPreferences.get();
 panel.append(el('p',{class:'muted',text:'Personalize sua experiência. As preferências visuais são aplicadas neste navegador, separadas por usuário.'}));
 const appearance=el('section',{class:'settings-section'},[el('h3',{text:'Aparência'})]);
 const options=[['theme','Tema',[['light','Claro'],['dark','Escuro'],['auto','Automático — acompanhar o sistema']]],['font','Tamanho da fonte',[['small','Pequena'],['default','Padrão'],['large','Grande'],['xlarge','Muito grande']]],['density','Densidade da interface',[['default','Padrão'],['compact','Compacta']]],['numbers','Exibição dos números',[['standard','Brasileira · 1.250'],['compact','Abreviada · 1,25 mil']]]];
 for(const [key,title,values] of options){const label=el('label',{text:title}),select=el('select',{'data-preference':key});for(const [value,text] of values)select.append(el('option',{value,text}));select.value=current[key];select.onchange=()=>DashboardPreferences.set({[key]:select.value});label.append(select);appearance.append(label);}
 const access=el('section',{class:'settings-section'},[el('h3',{text:'Acessibilidade'})]);
 const motion=el('input',{type:'checkbox','data-preference':'reduceMotion'});motion.checked=current.reduceMotion;motion.onchange=()=>DashboardPreferences.set({reduceMotion:motion.checked});
 access.append(el('label',{class:'switch-row'},[motion,document.createTextNode('Reduzir animações')]),el('small',{class:'muted',text:'A preferência de movimento reduzido do sistema também é respeitada.'}));
 const restore=el('button',{type:'button',class:'button secondary',text:'Restaurar configurações visuais'});
 restore.onclick=()=>{DashboardPreferences.reset();for(const input of panel.querySelectorAll('[data-preference]')){const value=DashboardPreferences.get()[input.dataset.preference];if(input.type==='checkbox')input.checked=value;else input.value=value;}DashboardControls.refresh();toast('Preferências visuais restauradas.');};
 panel.append(appearance,access,el('div',{class:'form-actions'},[restore]));
 if(saveToAccount){const save=el('button',{type:'button',class:'button primary',text:'Salvar preferências na conta'});save.onclick=async()=>{save.disabled=true;try{await api('/api/profile',{method:'PUT',body:JSON.stringify({appearance:DashboardPreferences.get()})});toast('Preferências salvas na conta.');}catch(error){toast(error.message,true);}finally{save.disabled=false;}};panel.querySelector('.form-actions').append(save);panel.prepend(el('p',{class:'muted',text:'As alterações são aplicadas neste navegador. Salve na conta para disponibilizá-las em novos navegadores.'}));}
 return panel;
}
function openSettings(){if(document.body.dataset.role==='guest')return;location.assign('/perfil?tab=preferences');}
let chartAppearanceTimer;
window.addEventListener('dashboard:appearance',()=>{
 if(typeof state==='undefined'||!dataReady)return;
 if(page==='dashboard')renderDashboard();else if(page==='relatorios')showReport();
 else observeCharts();
 clearTimeout(chartAppearanceTimer);chartAppearanceTimer=setTimeout(()=>document.querySelectorAll('.plot').forEach(node=>{const current=chartState.get(node);if(current)drawChart(node,current.spec,current.large);}),window.DashboardMotion?.duration('theme',220)||0);
});
