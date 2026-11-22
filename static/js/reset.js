document.querySelector('#reset-form').onsubmit=async event=>{
 event.preventDefault();const form=event.target,button=form.querySelector('button'),result=document.querySelector('#result');
 const data=Object.fromEntries(new FormData(form));if(data.password!==data.confirmation){result.textContent='As senhas não coincidem.';return;}
 button.disabled=true;
 try{const response=await fetch('/api/auth/reset',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':document.querySelector('meta[name="csrf-token"]').content},body:JSON.stringify(data)});const body=await response.json();result.textContent=body.error||body.message;if(response.ok)form.reset();}catch{result.textContent='Não foi possível conectar ao servidor.';}finally{button.disabled=false;}
};
