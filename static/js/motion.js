/* Shared finite motion. Preferences and keyboard behavior remain authoritative. */
window.DashboardMotion=(()=>{
 const active=new WeakMap();
 function duration(name,fallback=200){if(window.DashboardPreferences?.reduced())return 0;const value=getComputedStyle(document.documentElement).getPropertyValue('--motion-'+name).trim();const number=parseFloat(value);return Number.isFinite(number)?number*(value.endsWith('ms')?1:1000):fallback;}
 function details(group,open){
  const content=group.querySelector('.sidebar-subnav');if(!content)return;active.get(group)?.cancel();
  group.dataset.motionOpen=String(open);
  if(!duration('menu')||typeof content.animate!=='function'){group.open=open;delete group.dataset.motionOpen;return;}
  const start=group.open?content.getBoundingClientRect().height:0;group.open=true;const end=open?content.scrollHeight:0;
  if(!open&&content.contains(document.activeElement))group.querySelector('summary')?.focus();
  const animation=content.animate([{height:start+'px',opacity:open?0:1,overflow:'hidden'},{height:end+'px',opacity:open?1:0,overflow:'hidden'}],{duration:duration('menu'),easing:'cubic-bezier(.22,.68,.2,1)'});active.set(group,animation);
  animation.finished.then(()=>{if(active.get(group)!==animation)return;group.open=open;delete group.dataset.motionOpen;active.delete(group);}).catch(()=>{});
 }
 function cancelDetails(group){active.get(group)?.cancel();active.delete(group);if(group.dataset.motionOpen!==undefined){group.open=group.dataset.motionOpen==='true';delete group.dataset.motionOpen;}}
 return {duration,details,cancelDetails};
})();
