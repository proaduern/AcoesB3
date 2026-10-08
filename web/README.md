# web

Tela Next.js (App Router, TypeScript estrito). Só lê resultados prontos do Neon; a única lógica de cálculo é o simulador
(etapa 5.6), com teste de paridade contra `pipeline/acoesb3/ceiling.py`. Roteiro: `docs/fase5.md`.

```bash
cd web
npm ci
# testes de banco: Postgres vazio; as migrações do pipeline são aplicadas (apaga o schema public)
export TEST_DATABASE_URL=postgresql://usuario:senha@localhost:5432/acoes_test
npm run lint && npm run typecheck && npm test && npm run build
npm run dev
```

Segredos só na Vercel (nunca no código): `NEON_DATABASE_URL_POOLED`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`,
`ALLOWED_EMAILS`, `AUTH_SECRET`. Projeto da Vercel com Root Directory `web`.
