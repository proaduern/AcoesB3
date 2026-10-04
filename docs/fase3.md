# Fase 3 — Preço teto (roteiro para a próxima sessão)

Escopo da especificação: seção 5 (5 métodos, mediana, regra de "Compra" com K métodos, faixas). **Vale só para a lista
acompanhada** (`watchlist`: carteira + radar), decisão de 04/10/2026. Leia, nesta ordem: `CLAUDE.md`,
`docs/ESPECIFICACAO.md` (seções 3, 4.1, 5, 12), `docs/fase2.md`, este arquivo. Não releia logs nem a conversa anterior.

## O que já existe (fase 2)

- **Banco** (Neon, ~397 MB de ~512 MB se o plano for o gratuito): `indicator_annual` (lucro, PL, JCP, dividendos DVA e FRE,
  LPA ON/PN, ações da DFP), `company_event` (desdobramentos/bonificações por empresa), `fre_capital` (ações por data via
  `shares.shares_at`), `quote_daily` (COTAHIST não ajustado), `screen_result`/`screen_criterion` (filtro por data-base),
  `dividend_outlier`/`outlier_review`/`dividend_override` (revisão), `watchlist`, `app_config` (todos os parâmetros).
- **Código** (`pipeline/acoesb3/`): `indicators.py` (fatos anuais, `choose_dividends`), `screen.py` (critérios), `shares.py`,
  `corporate.py` (eventos), `compute.py` (etapas annual/outliers/events/screens), `watch.py`, `review.py`, `cli.py`.
- **Decisões que a fase 3 herda**: proventos = DVA primeiro, FRE só se a DVA faltar ou for zero; DPS = total ÷ ações do FRE
  ajustadas por eventos; valor de mercado = fechamento × ações por classe (papel mais negociado com preço na data); ano de
  outlier sem decisão fica fora das médias; dado ausente = indisponível; números só da CVM.
- **Lista acompanhada** (cvm_code): carteira BB 1023, Itaú 19348, BB Seguridade 23159, Caixa Seguridade 23795, Porto Seguro
  16659, Alupar 21490, Engie 17329, ISA 18376, Sanepar 18627, Copasa 19445, Vivo 17671. Radar: Bradesco 906, Santander 20532,
  Cemig 2453, CPFL 18660, Taesa 20257, Sabesp 14443, TIM 24929.

## Como operar sem acesso direto ao Neon

Tudo roda no Actions: workflow `compute` (disparar pela branch ou pela padrão). Entradas úteis: `skip_compute` (só
imprimir), `step` (annual/outliers/events/screens; `events` leva ~40 min), `sql` (consultas somente leitura separadas por
`###`), `watch_explain` (critérios, fatos e eventos por empresa), `watch_find`, `watch_add`, `watch_candidates`,
`priority_only`. Logs: ler com `mcp__github__get_job_logs` com `return_content`; resultado grande vem como arquivo, extrair
com Python. Testes locais: Postgres em `/var/tmp/pgdata` porta 5433 (reiniciar com `pg_ctl` se cair),
`TEST_DATABASE_URL=postgresql://postgres@localhost:5433/acoes_test`, `pytest` e `ruff` dentro de `pipeline/`.

## Perguntas a fazer ao usuário ANTES de codar (a especificação não cobre)

1. **VPA**: PL do controlador ÷ ações em qual data? (sugestão: fim do último exercício, levado à base de ações de hoje pelos eventos).
2. **Preço atual**: último fechamento do COTAHIST (defasagem de dias) ou cotação intradiária? Qual data-base do preço teto?
3. **Classes**: o preço teto é por classe (ON/PN/unit). O valor por ação é o mesmo para as classes da empresa ou usa os
   proventos por classe do FRE? Como tratar units (TAEE11 = 1 ON + 2 PN)?
4. **Gordon**: o "crescimento histórico de 5 anos" é do dividendo total, do DPS ou do lucro? E o "dividendo médio líquido"
   usa os 5 últimos exercícios fechados (ano de outlier fora)?
5. **P/L e P/VP mediano de 10 anos**: preço de fim de exercício ÷ LPA (lucro ÷ ações do FRE) ou o LPA da DRE? Ano com
   prejuízo sai do P/L (já na especificação); empresa com menos de 10 anos usa o que existe ou fica indisponível?
6. **DCF (FCFE)**: para quais empresas da lista? Exige contas do fluxo de caixa (DFC) que **não** estão em `cvm_account`:
   verificar a fonte real e os códigos antes de carregar (regra: não inventar formato).
7. **Alíquotas** do dividendo médio líquido: JCP 15%, dividendo 0% (já em `app_config`, `tax.*`).
8. **Banco e seguradora**: sem Graham e sem DCF (especificação); ficam 3 métodos (Bazin, Gordon, P/VP) e K = 2.

## Entrega esperada da fase 3

Migração com tabela de resultado (por empresa, data-base e método: valor, entradas em JSON, status/motivo de
indisponível, fonte, data-base e data de coleta), parâmetros novos em `app_config` (6% do Bazin, k=12%, g em [0%, 5%], 22,5
do Graham, janelas, K por nº de métodos, faixas 80/100/120%), módulo `pipeline/acoesb3/ceiling.py` (funções puras +
`compute --step ceilings`), testes com números conferidos à mão (Bazin e Graham fáceis de conferir), comando de leitura
(`acoesb3 ceilings list`), entrada no workflow `compute`, especificação e `CLAUDE.md` atualizados, nota do que ficou de fora.

## Pendências da fase 2 que afetam a fase 3 (do usuário)

- Revisar os outliers que mudam resultado (`review list --priority`): 18 em 04/10/2026 (Itaú 2019, Bradesco 2018, CPFL 2021 entre
  as aprovadas) e os eventos suspeitos (633) só das empresas da lista.
- Decidir o método do critério de queda do DPS (ano contra ano, hoje, ou média de 3 anos).
- Caixa Seguridade (abriu capital em 2021) e BB Seguridade (proventos de todos os anos indisponível) ficam com dado insuficiente.
