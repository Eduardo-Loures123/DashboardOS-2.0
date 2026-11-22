/* Loaded in <head>: independent, per-user browser preference; no HTTP writes. */
window.DashboardSidebar=(()=>{
 const root=document.documentElement,key='DashboardOS:sidebar:v1:'+(root.dataset.userKey||'login');
 let collapsed=false;
 const mobile=window.matchMedia?.('(max-width: 600px)');let mobileOpen=false;
 let transitionTimer;
 try{collapsed=localStorage.getItem(key)==='collapsed';}catch{}
 root.dataset.sidebar=collapsed?'collapsed':'expanded';
 root.dataset.sidebarBooting='true';
 function sync(){
  root.dataset.sidebar=collapsed?'collapsed':'expanded';
  if(mobile?.matches)root.dataset.mobileMenu=mobileOpen?'open':'closed';else delete root.dataset.mobileMenu;
  document.querySelector('.shell')?.classList.toggle('collapsed',collapsed);
  const button=document.querySelector('#menu-toggle');
  document.querySelectorAll('.sidebar-group').forEach(group=>{window.DashboardMotion?.cancelDetails(group);if(collapsed){if(!group.dataset.wasOpen)group.dataset.wasOpen=String(group.open);group.open=true;}else if(group.dataset.wasOpen){group.open=group.dataset.wasOpen==='true';delete group.dataset.wasOpen;}});
  if(button){const expanded=mobile?.matches?mobileOpen:!collapsed;button.setAttribute('aria-expanded',String(expanded));button.setAttribute('aria-label',expanded?'Recolher menu':'Expandir menu');button.title=expanded?'Recolher menu':'Expandir menu';}
 }
 function set(value){const duration=window.DashboardMotion?.duration('layout',280)||0;clearTimeout(transitionTimer);if(duration){root.dataset.sidebarTransition='true';transitionTimer=setTimeout(()=>{delete root.dataset.sidebarTransition;window.dispatchEvent(new Event('dashboard:sidebar-settled'));},duration+20);}else delete root.dataset.sidebarTransition;collapsed=Boolean(value);try{localStorage.setItem(key,collapsed?'collapsed':'expanded');}catch{}sync();}
 function attach(){sync();const button=document.querySelector('#menu-toggle');if(button)button.onclick=()=>{if(mobile?.matches){mobileOpen=!mobileOpen;sync();}else set(!collapsed);};document.querySelectorAll('.sidebar-group').forEach(group=>{const summary=group.querySelector('summary');summary.onclick=event=>{if(!window.DashboardMotion)return;event.preventDefault();DashboardMotion.details(group,!(group.dataset.motionOpen===undefined?group.open:group.dataset.motionOpen==='true'));};});requestAnimationFrame(()=>requestAnimationFrame(()=>delete root.dataset.sidebarBooting));}
 mobile?.addEventListener?.('change',()=>{mobileOpen=false;sync();});
 return {key,get:()=>collapsed,set,attach};
})();
