/* Executado no head, antes da pintura. Somente preferências visuais. */
window.DashboardPreferences=(()=>{
 const root=document.documentElement;
 const key='DashboardOS_2.0:appearance:v1:'+(root.dataset.userKey||'login');
 const defaults={theme:'light',font:'default',reduceMotion:false,density:'default',numbers:'standard'};
 const allowed={theme:['light','dark','auto'],font:['small','default','large','xlarge'],density:['compact','default'],numbers:['standard','compact']};
 const scales={small:1,default:1.1,large:1.22,xlarge:1.35};
 const systemTheme=window.matchMedia?.('(prefers-color-scheme: dark)');
 const systemMotion=window.matchMedia?.('(prefers-reduced-motion: reduce)');
 let values={...defaults};
 function validate(data){const clean={...defaults};for(const field of Object.keys(allowed))if(allowed[field].includes(data?.[field]))clean[field]=data[field];if(typeof data?.reduceMotion==='boolean')clean.reduceMotion=data.reduceMotion;return clean;}
 try{values=validate(JSON.parse(localStorage.getItem(key)||root.dataset.accountAppearance||'null'));}catch{}
 function apply(notify=true){
  root.dataset.theme=values.theme==='auto'?(systemTheme?.matches?'dark':'light'):values.theme;
  root.dataset.font=values.font;root.dataset.density=values.density;
  root.dataset.reduceMotion=String(values.reduceMotion||Boolean(systemMotion?.matches));
  root.style.setProperty('--font-scale',scales[values.font]);
  root.style.colorScheme=root.dataset.theme;
  if(notify)window.dispatchEvent(new CustomEvent('dashboard:appearance',{detail:{...values}}));
 }
 function set(patch){values=validate({...values,...patch});try{localStorage.setItem(key,JSON.stringify(values));}catch{}apply();}
 function reset(){values={...defaults};try{localStorage.removeItem(key);}catch{}apply();}
 function formatNumber(value){return new Intl.NumberFormat('pt-BR',values.numbers==='compact'?{notation:'compact',maximumFractionDigits:2}:{}).format(value);}
 systemTheme?.addEventListener?.('change',()=>apply());systemMotion?.addEventListener?.('change',()=>apply());
 window.addEventListener('storage',event=>{if(event.key===key){try{values=validate(JSON.parse(event.newValue||'null'));apply();}catch{}}});
 apply(false);
 return {get:()=>({...values}),set,reset,formatNumber,key,reduced:()=>root.dataset.reduceMotion==='true',scale:()=>scales[values.font]};
})();
