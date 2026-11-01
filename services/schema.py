SCHEMA = {
 'Funcionarios': ['codigo','nome','equipe','cargo','email','admissao','status'],
 'Equipes': ['codigo','nome','responsavel'],
 'OrdensServico': ['codigo','descricao','funcionario','abertura','previsao','conclusao','prioridade','status'],
 'Acessos': ['codigo','funcionario','sistema','concessao','vencimento','status'],
 'Renovacoes': ['codigo','acesso','solicitacao','status','responsavel','observacoes'],
}
PREFIX = dict(zip(SCHEMA, ['FUNC','EQ','OS','AC','REN']))
STATUS = {'Funcionarios':['Ativo','Inativo'], 'OrdensServico':['Pendente','Em andamento','Concluída'], 'Acessos':['Ativo','Revogado'], 'Renovacoes':['Pendente','Solicitada','Em análise','Aprovada','Concluída','Rejeitada']}
LABELS = {'codigo':'Código','nome':'Nome','equipe':'Equipe','cargo':'Cargo','email':'E-mail','admissao':'Admissão','status':'Status','responsavel':'Responsável','descricao':'Descrição','funcionario':'Funcionário','abertura':'Abertura','previsao':'Previsão','conclusao':'Conclusão','prioridade':'Prioridade','sistema':'Sistema / recurso','concessao':'Concessão','vencimento':'Vencimento','acesso':'Acesso','solicitacao':'Solicitação','observacoes':'Observações','dias':'Dias restantes','situacao':'Situação','quantidade_funcionarios':'Funcionários','quantidade_os':'OS','quantidade_acessos':'Acessos'}
