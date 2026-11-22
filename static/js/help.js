document.querySelector('#help-search')?.addEventListener('input',event=>{
 const normalize=value=>value.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLocaleLowerCase('pt-BR');
 const query=normalize(event.target.value);let found=0;
 document.querySelectorAll('[data-help]').forEach(card=>{card.hidden=!normalize(card.textContent).includes(query);if(!card.hidden)found++;});
 document.querySelector('#help-empty').hidden=found>0;
});
