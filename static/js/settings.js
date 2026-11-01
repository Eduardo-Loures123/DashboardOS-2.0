function openSettings(){
 const panel=el('div',{class:'settings-panel'});
 const current=DashboardPreferences.get();
 panel.append(el('p',{class:'muted',text:'Personalize sua experiência. Estas opções são salvas somente neste navegador, separadas por usuário.'}));
 const appearance=el('section',{class:'settings-section'},[el('h3',{text:'Aparência'})]);
 const options=[['theme','Tema',[['light','Claro'],['dark','Escuro'],['auto','Automático — acompanhar o sistema']]],['font','Tamanho da fonte',[['small','Pequena'],['default','Padrão'],['large','Grande'],['xlarge','Muito grande']]],['density','Densidade da interface',[['default','Padrão'],['compact','Compacta']]],['numbers','Exibição dos números',[['standard','Brasileira · 1.250'],['compact','Abreviada · 1,25 mil']]]];
 for(const [key,title,values] of options){const label=el('label',{text:title}),select=el('select',{'data-preference':key});for(const [value,text] of values)select.append(el('option',{value,text}));select.value=current[key];select.onchange=()=>DashboardPreferences.set({[key]:select.value});label.append(select);appearance.append(label);}
 const access=el('section',{class:'settings-section'},[el('h3',{text:'Acessibilidade'})]);
 const motion=el('input',{type:'checkbox','data-preference':'reduceMotion'});motion.checked=current.reduceMotion;motion.onchange=()=>DashboardPreferences.set({reduceMotion:motion.checked});
 access.append(el('label',{class:'switch-row'},[motion,document.createTextNode('Reduzir animações')]),el('small',{class:'muted',text:'A preferência de movimento reduzido do sistema também é respeitada.'}));
 const restore=el('button',{type:'button',class:'button secondary',text:'Restaurar configurações visuais'});
 restore.onclick=()=>{DashboardPreferences.reset();for(const input of panel.querySelectorAll('[data-preference]')){const value=DashboardPreferences.get()[input.dataset.preference];if(input.type==='checkbox')input.checked=value;else input.value=value;}toast('Preferências visuais restauradas.');};
 panel.append(appearance,access,el('div',{class:'form-actions'},[restore]));
 openModal('Configurações',panel);modal.classList.add('settings-modal');
}
document.querySelector('#settings-button')?.addEventListener('click',openSettings);
window.addEventListener('dashboard:appearance',()=>{
 if(typeof state==='undefined'||!dataReady)return;
 if(page==='dashboard')renderDashboard();else if(page==='relatorios')showReport();
 else observeCharts();
});
