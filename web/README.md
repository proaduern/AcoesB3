# web

Tela do AcoesB3: Next.js (App Router), React 19, TypeScript estrito. Só **lê** resultados prontos do Neon; a única lógica de
cálculo é o simulador do preço teto, com teste de paridade contra `pipeline/acoesb3/ceiling.py`. Decisões e registro por
etapa: `docs/fase5.md`; regras: seção 9.1 de `docs/ESPECIFICACAO.md`.

## Rotas

| Rota | O que mostra |
|---|---|
| `/` | Lista acompanhada (preço, teto, faixa, votos, situação) |
| `/filtro`, `/filtro/pendencias` | Filtro da B3 inteira; pendências de revisão com o comando a rodar |
| `/empresa/[cvm]` | Ficha (só da lista): preço teto, simulador, filtro, preço, origem dos dados |
| `/backtest` | Aviso de viés, validação, ajuste, gráfico, fluxos e ordens |
| `/login`, `/acesso-negado` | Entrada com Google e recusa |

## Rodar

```bash
cd web
npm ci
npm run lint && npm run typecheck && npm test && npm run build
npm run dev   # precisa das variáveis abaixo e de um banco com as migrações do pipeline
```

Os testes de banco precisam de um Postgres vazio em `TEST_DATABASE_URL`; eles **apagam o schema `public`** e aplicam as
migrações de `pipeline/migrations/`. Sem a variável são pulados.

```bash
export TEST_DATABASE_URL=postgresql://usuario:senha@localhost:5432/acoes_web_test
```

## Segredos (só na Vercel; nunca no código nem no chat)

`NEON_DATABASE_URL_POOLED`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ALLOWED_EMAILS` (separados por vírgula) e
`AUTH_SECRET`. Os nomes estão em `.env.example`. Projeto da Vercel com Root Directory `web`; URI de redirecionamento do
Google: `https://<dominio>/api/auth/callback/google`. Passo a passo e conferências: `docs/fase5.md`.

## Estrutura

- `src/app/` rotas; `src/proxy.ts` leva quem não tem sessão ao login.
- `src/lib/db/` leitura do banco: `queries.ts` é a **única porta** (confere o usuário e roda em transação somente leitura).
- `src/lib/ceiling/` simulador (`methods`, `consolidate`, `simulate`, `params`, `form`, `view`).
- `src/lib/` regras puras testáveis (`format`, `screen`, `company`, `backtest`, `watchlist`, `chart`); `src/components/` telas e gráficos em SVG.
- `tests/parity/cases.json` fixture de paridade, **gerado pelo Python**; `tests/helpers/` dados de teste.

## Simulador do preço teto

`src/lib/ceiling/` refaz o preço teto com outros parâmetros e preços a partir dos insumos gravados em `ceiling_method.inputs`
(taxas, multiplicador, k, limites de g, DCF, tabela de K, faixas). Janelas de exercícios e alíquotas não mudam aqui: exigem os
dados brutos. A paridade com `ceiling.py` é testada contra `tests/parity/cases.json`.

**Mudou uma regra em `ceiling.py`**: ajuste o simulador e regere o fixture no mesmo commit
(`acoesb3 ceilings parity-export`, dentro de `pipeline/`); `pipeline/tests/test_parity.py` falha se o fixture estiver defasado.
