# Atualizações e releases do DashboardOS

- Preserve dados reais, autenticação, permissões e preferências. Testes de escrita devem usar cópias temporárias. Não execute migrações reais, envio de e-mails/notificações, push ou deploy sem autorização explícita.
- A única fonte da versão atual é `VERSION`. O backend a expõe aos templates e à API; não replique o número manualmente no frontend. Preserve a chave histórica de armazenamento das preferências, que não representa a versão do aplicativo.
- Em uma atualização aprovada para nova versão, avalie e proponha MAJOR para incompatibilidades, MINOR para funcionalidades compatíveis ou PATCH para correções compatíveis. Atualize `VERSION` e `CHANGELOG.md` e informe a versão preparada. Não incremente ao executar, reiniciar ou testar.
- Versão preparada localmente não significa versão publicada. Após homologação e aprovação da release, a tag deve seguir `vMAJOR.MINOR.PATCH`, apontando ao commit efetivamente aprovado. Não crie/publice tags remotas nem commits remotos sem autorização.
- Valide com `scripts/testar.py` e `scripts/preparar_testes_frontend.py`, seguidos pelos testes Node. Se subprocessos forem bloqueados no sandbox, use `node --test --test-isolation=none tests/frontend.test.cjs`.
- Testes jsdom não comprovam renderização. Registre separadamente validação visual realizada e pendente; não declare aprovação visual sem inspeção real no navegador.
