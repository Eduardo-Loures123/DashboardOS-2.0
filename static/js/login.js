const password=document.querySelector('#password'),toggle=document.querySelector('#toggle-password');
toggle.onclick=()=>{const show=password.type==='password';password.type=show?'text':'password';toggle.textContent=show?'Ocultar':'Mostrar';toggle.setAttribute('aria-pressed',String(show));};
for(const form of document.querySelectorAll('.login-card form'))form.addEventListener('submit',()=>{
 for(const button of document.querySelectorAll('.login-card button[type="submit"]'))button.disabled=true;
 const button=form.querySelector('[type="submit"]');button.textContent=form.id==='login-form'?'Entrando…':'Abrindo…';form.setAttribute('aria-busy','true');
});
