# Fase 5 — Tela Next.js, login Google, filtro, ficha da empresa e simulador (roteiro)

**Estado (08/10/2026)**: decisões tomadas com o usuário; etapas 5.0 (esqueleto) e 5.1 (login) feitas no código; o login real ainda não foi conferido na Vercel. Este documento é o roteiro; as regras
ficam na seção 9.1 da especificação. A tela **só lê** resultados prontos do Neon; a única lógica de cálculo em TypeScript
é o simulador, com teste de paridade contra `pipeline/acoesb3/ceiling.py`.

## Decisões do usuário (08/10/2026)

| Tema | Decisão |
|---|---|
| Telas | Lista acompanhada · Filtro da B3 inteira · Backtest · Ficha da empresa com o simulador numa aba. Menu fixo no topo. |
| Ficha | Os 5 métodos do preço teto · critérios do filtro com histórico anual · gráfico de preço com a linha do teto · eventos societários e dados de origem. |
| Simulador | Recalcula **parâmetros e preço**. Não troca insumos (LPA, VPA, dividendo, FCFE) à mão. |
| Aviso de viés | Faixa fixa sem botão de fechar + selo "universo de hoje" ao lado de cada retorno e do gráfico. Texto lido do banco. |
| Escrita | **Somente leitura.** Revisão de outliers/eventos e mudança de configuração seguem por comando e Actions. |
| Login | Auth.js com Google + `ALLOWED_EMAILS`. Segredo novo: `AUTH_SECRET`. |
| Repositório e deploy | `web/` na raiz; projeto da Vercel com Root Directory `web`; produção pela branch padrão, preview por PR. |

## Escopo por tela

Toda tela mostra, em cada dado, **fonte, data-base e data de coleta**; dado ausente aparece como "indisponível", nunca
como zero ou valor antigo (seção 10).

1. **Lista acompanhada** (`watchlist` + `ceiling_class` + `ceiling_result` + `screen_result`): por papel, preço e data do
   fechamento, teto, razão preço ÷ teto, faixa (`strong_buy`, `buy`, `hold`, `expensive`), votos/K, `buy`, papel de carteira ou
   radar e segmento. `insufficient` aparece como "dados insuficientes" (visível, nunca compra). Filtro por segmento e por papel.
2. **Filtro** (`screen_result` + `screen_criterion`, B3 inteira): status do retrato, critério reprovado/indisponível com valor e
   limite, busca e filtro por status (`approved`, `rejected`, `insufficient_history`, `insufficient_data`, `stale`, `not_listed`,
   `excluded`). Botão para ver a ficha só para empresas da lista; para as demais, a linha mostra os critérios e a indicação de
   que ela não está na lista (`acoesb3 watch add`). Lista de pendências (outliers e eventos suspeitos) com o comando a rodar.
3. **Ficha da empresa**, abas:
   - *Preço teto*: os 5 métodos (`ceiling_method`: valor, status, motivo, `inputs` expansível), mediana, K, votos, faixa por papel.
   - *Filtro*: critérios, histórico anual de lucro, ROE, DPS, DY, payout (`indicator_annual`, `dividend_outlier`, `outlier_review`),
     outliers em destaque.
   - *Preço*: fechamento (`quote_daily`) com a linha do teto.
   - *Origem*: eventos societários (`corporate_event`), plano de contas, setor e reclassificação (`company_class_override`),
     proventos lançados à mão (`dividend_override`), fonte de cada ano.
   - *Simulador*: ver abaixo.
4. **Backtest** (`backtest_run`, `backtest_series`, `backtest_freeze`, `backtest_trade`): cenários do ajuste (2012-01 a 2023-12)
   lado a lado; a **validação** (execução única, 2024-01-01 a 2025-12-31) em bloco separado com a nota "medida uma vez em
   08/10/2026, sem reajuste"; gráfico mensal da estratégia líquida e bruta contra Ibovespa, IDIV e CDI; métricas, janelas de
   5 anos perdidas, queda máxima e o estado do critério de morte; ordens por cenário. O aviso de viés cobre todo o bloco:
   faixa fixa no topo (texto de `backtest_run.warnings` / `universe.survivorship_warning`) e selo ao lado de cada retorno e
   do gráfico. As pendências da fase 4 (proventos, fim do período, tarifas) aparecem como notas, sem esconder o limite.

## Simulador (TypeScript) e paridade

**O que recalcula**: dado o papel, o usuário altera o preço e os parâmetros `ceiling.*` (taxa Bazin, multiplicador de Graham,
k, g mínimo/máximo e spread do Gordon, taxa, anos, crescimento e perpetuidade do DCF, K por quantidade de métodos, faixas). O
TS refaz os métodos, a mediana, os votos, a faixa e `buy`, usando como entrada os insumos anuais já gravados em
`ceiling_method.inputs` (`dps_net`, `growth.first/last`, `lpa_mean`, `vpa`, `ratios`, `fcfe`, `base`) e `ceiling_class.multiplier`.
Defaults vêm de `app_config`. Nada de DFP, FRE ou COTAHIST é lido nem recalculado.

**Regra**: uma só implementação, em `web/src/lib/ceiling/`, espelhando `ceiling.py` função a função (`bazin`, `gordon`,
`graham`, `multiples`, `dcf`, `consolidate`, `k_for`, `band_for`, `value_class`). Aritmética com `decimal.js` (precisão 28,
como o `Decimal` do Python), nunca `number`, para a paridade valer inclusive em `sqrt` e potência fracionária.

**Teste de paridade**:
- `acoesb3 ceilings parity-export` gera `web/tests/parity/cases.json` a partir de `ceiling.py`: parâmetros, insumos, resultado
  esperado de cada método e do consolidado. Cobre os casos com borda: método excluído e indisponível, `k − g` abaixo do mínimo,
  LPA/VPA ≤ 0, banco/seguradora, menos de 3 métodos, K = 3 com 4 métodos, preço exatamente em 80%, 100% e 120%, unit com
  multiplicador 3, ano de outlier fora da média e `ESCALA_MOEDA` (insumos em unidade e em mil, com a escala explícita).
- O Vitest roda os mesmos casos no TS e compara com tolerância relativa de 1e-9 (e igualdade exata de status, faixa e `buy`).
- No CI, o export é regerado e `git diff --exit-code web/tests/parity` falha se o Python mudou e o fixture não: as duas
  implementações não divergem em silêncio.
- Mudou uma regra em `ceiling.py`: mudar o TS e regerar o fixture no mesmo commit.

## Login e acesso

- Auth.js (NextAuth v5) com provedor Google, escopos `openid email profile`. O escopo `drive.file` fica para a fase 8.
- `ALLOWED_EMAILS` (lista separada por vírgula, comparada em minúsculas) conferida no callback `signIn` **e** em todo acesso ao
  banco no servidor (middleware não basta). E-mail fora da lista cai numa tela de recusa, sem dados.
- Segredos só na Vercel: `NEON_DATABASE_URL_POOLED`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ALLOWED_EMAILS` e o novo
  `AUTH_SECRET`. `GOOGLE_REFRESH_TOKEN` não é usado nesta fase. Nada de credencial no código nem no chat.
- O app do Google Cloud precisa estar publicado (não em modo teste), como na seção 9. Para só login, os escopos são básicos
  e não pedem verificação.

## Banco de leitura

- Driver `@neondatabase/serverless` (ou `pg`) com `NEON_DATABASE_URL_POOLED`. Consultas só em componentes de servidor e em
  `web/src/lib/db/queries.ts`; o navegador nunca recebe a URL.
- **A confirmar com o usuário**: usar um papel do Neon só com `SELECT` para montar a URL do pooler. Assim "a tela só lê" fica
  garantido pelo banco, não só pelo código. O papel é criado no console do Neon (senha não passa pelo chat) e a URL entra
  na Vercel. Sem ele, a conexão usa o papel do pipeline.
- Cada consulta devolve também `data_base`, `collected_at` e `computed_at`, para a tela mostrar a procedência.

## Etapas

| Etapa | Entrega | Teste / verificação |
|---|---|---|
| 5.0 (feita) | Esqueleto `web/` (Next.js App Router, TypeScript estrito, ESLint, Vitest), `web-ci.yml` (lint, tipos, testes) em `web/**` | CI verde com página vazia |
| 5.1 (código feito) | Login Google + `ALLOWED_EMAILS`, tela de recusa, layout com menu | Testes da função de autorização (lista, caixa, vazio); login real conferido pelo usuário na Vercel |
| 5.2 (feita) | Camada de leitura do Neon, formatadores (R$, %, datas, "indisponível") e componente de procedência | Testes de formatação: nulo nunca vira 0; unidade vs mil explícita |
| 5.3 (feita) | Lista acompanhada | Testes de consulta com banco de teste; conferência com `acoesb3 ceilings list` |
| 5.4 (feita) | Filtro da B3 | Idem; contagem por status bate com o banco |
| 5.5 (feita) | Ficha: preço teto, filtro, preço, origem | Valores da ficha conferidos contra `ceilings list --dcf` em 2 empresas |
| 5.6 (feita) | Simulador TS + `parity-export` + CI de paridade | Paridade com tolerância 1e-9; diff do fixture no CI |
| 5.7 | Aba do simulador na ficha | Com os parâmetros padrão, o resultado é idêntico ao gravado (`ceiling_class`) |
| 5.8 | Tela do backtest com o aviso de viés | Teste que falha se a faixa ou o selo não renderizarem com `warnings` vazio ou não vazio; validação marcada como medida única |
| 5.9 | Docs: `docs/fase5.md` atualizado, seção 9.1 da especificação, README do `web/`, "Fase atual" do CLAUDE.md | Revisão do usuário |

## Passos do usuário (fora do código)

1. Criar o projeto na Vercel apontando para este repositório, Root Directory `web`.
2. Cadastrar na Vercel: `NEON_DATABASE_URL_POOLED`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ALLOWED_EMAILS`, `AUTH_SECRET`
   (gerado por você; eu não peço valores). URI de redirecionamento autorizada no cliente OAuth do Google:
   `https://<dominio>/api/auth/callback/google`.
3. (Opcional) Criar o papel de leitura no Neon.

## O que fica de fora, e por quê

| Item | Motivo |
|---|---|
| Revisão de outliers/eventos pela tela | Decisão de 08/10/2026: tela somente leitura; vira fase própria com credencial de escrita |
| Disparo de recálculo pela tela (workflow `compute`) | Idem: exige token do GitHub na Vercel |
| Simulador com troca de insumos (LPA, VPA, dividendo, FCFE) | Decisão de 08/10/2026; exigiria espelhar mais regras e testes |
| Cotação intradiária | Decisão da fase 3 (preço = último fechamento); brapi/Yahoo seguem sem uso |
| Carteira, lançamentos, extrato B3, alocação e alertas | Fases 6 e 7 |
| Releases em PDF e escopo `drive.file` | Fase 8 |
| Simular um novo backtest na tela | O backtest é feito no pipeline; a validação só pode ser medida uma vez |
| Pendências de revisão das fases 2 e 3 (`docs/fase3.md`) | Dependem do usuário; a tela só as expõe como "pendente" |

## Riscos que a fase precisa fechar

- **Paridade só vale para o que está no `inputs`**: se algum insumo necessário não estiver gravado, a etapa 5.6 pode exigir uma
  migração nova em `ceiling_method.inputs`. Verificar primeiro (casos de Gordon com ponta de outlier e DCF com crescimento informado).
- **Procedência na tela**: `ceiling_class` tem `computed_at` e `price_date`, mas a data de coleta vem de `ceiling_method`/`ceiling_result`;
  a consulta deve juntar as três.
- **Viés de sobrevivência**: o texto vem do banco; se `warnings` e `universe` vierem vazios, a tela deve mostrar um aviso padrão
  e não ocultar a faixa (teste da etapa 5.8).

## Notas da etapa 5.0

- Next.js 16, React 19, TypeScript 5 estrito (`noUncheckedIndexedAccess`), ESLint 9, Vitest 5; Node 22 no CI. `web-ci.yml` roda lint, tipos, testes e build em `web/**`.
- `npm audit`: 0 vulnerabilidades nas dependências de produção. Restam avisos `braces/micromatch` só no ferramental do ESLint (dev); o conserto sugerido (`eslint-config-next@14`) seria um retrocesso, então fica registrado.
- A página inicial é só um marcador; login, menu e telas entram nas etapas 5.1 em diante.

## Notas da etapa 5.1

- Auth.js v5 (`next-auth@5.0.0-beta.32`, versão fixa: ainda é beta, mas é a que suporta Next 16). Sessão JWT de 7 dias.
- `signIn` só aceita e-mail **verificado** pelo Google e presente em `ALLOWED_EMAILS` (falha fechada: lista vazia = ninguém entra). Recusa cai em `/acesso-negado`.
- Duas barreiras: `src/proxy.ts` (Next 16 chama o antigo middleware de proxy) manda quem não tem sessão para `/login`; `requireUser()` confere a lista **de novo** a cada página (grupo `(app)`) e vale para toda consulta ao banco a partir da 5.2. Tirar um e-mail de `ALLOWED_EMAILS` vale na próxima requisição, sem esperar a sessão expirar.
- Conferido localmente com servidor de produção e variáveis falsas: `/`, `/filtro` e `/backtest` redirecionam (307) para `/login`; `/login`, `/acesso-negado` e `/api/auth/providers` respondem 200. O fluxo completo com o Google só pode ser conferido na Vercel.
- Testes: `parseAllowedEmails` e `isAllowedEmail` (caixa, espaços, separadores, sufixo/prefixo, lista vazia).
- Menu: Lista, Filtro, Backtest e Sair; páginas ainda são marcadores.

## Quando publicar na Vercel

Já agora, com a 5.1: o login só se prova numa URL real (redirecionamento OAuth), e é mais barato achar um erro de
configuração do Google com a tela vazia do que com as telas prontas. `NEON_DATABASE_URL_POOLED` só é necessária a partir da 5.2.
A partir daí, cada PR gera preview; produção sai da branch padrão. Lembrete: a URI de redirecionamento do cliente OAuth
vale por domínio; previews com URL própria não fazem login, só o domínio de produção (ou um domínio fixo de preview).

## Notas da etapa 5.2

- **Leitura**: driver `pg` (funciona no pooler da Neon e no Postgres de teste). `src/lib/db/pool.ts` usa só `NEON_DATABASE_URL_POOLED`; datas saem como texto `AAAA-MM-DD` (sem deslocamento de fuso) e `numeric` como texto (sem perder precisão).
- **Somente leitura garantida pelo banco**: `readOnly()` abre `BEGIN READ ONLY`; INSERT/UPDATE/DROP falham com "read-only transaction" (testado). Não usa opções de sessão, que o pooler não aceita. O papel `SELECT` do Neon continua sendo uma camada extra opcional.
- **Uma porta só**: `src/lib/db/queries.ts` (`server-only`) chama `requireUser()` antes de cada consulta; a lógica de SQL fica em `core.ts`, que recebe o pool e por isso é testável sem login.
- **Formatadores** (`src/lib/format.ts`, `decimal.js`): nulo, vazio e não numérico viram "indisponível", nunca 0; reais, percentual, data e data/hora (Brasília) em pt-BR. **ESCALA_MOEDA**: o banco já guarda reais (o pipeline converte em `cvm.scale_value`), então a tela não reescala; `toReais(valor, escala)` existe só para dado cru e recusa escala desconhecida (como o Python). Testes: R$ 41,085 bi lido em reais x em mil.
- **Procedência**: componente `Provenance` (fonte, data-base, coletado em) e `DataFooter` em toda tela do grupo `(app)`: data do cálculo do teto, último fechamento e retrato do filtro. Com o banco fora do ar mostra aviso em vez de erro.
- **Testes de banco** (`src/lib/db/db.test.ts`): aplicam as migrações do pipeline num Postgres de teste (`TEST_DATABASE_URL`); sem a variável são pulados. O `web-ci.yml` agora sobe um Postgres e roda isso; os gatilhos incluem `pipeline/migrations/**`.
- 32 testes, lint, tipos e build passando.

## Notas da etapa 5.3

- **Lista acompanhada** (`/`): parte da tabela `watchlist` (não do teto), então empresa sem cálculo continua na lista como "Sem preço teto calculado". Uma linha por papel (ON, PN, unit), carteira antes do radar. Colunas: papel e empresa, segmento, preço e data do fechamento, teto, preço ÷ teto, faixa, votos/K, situação, status do filtro (retrato mais recente) e exercício (data-base).
- **Situação sempre em texto**, nunca só cor: `COMPRA` só quando o banco diz `buy`; `insufficient` vira "Dados insuficientes" mesmo que `buy` venha verdadeiro; abaixo do teto sem os K votos aparece como "Abaixo do teto, sem os votos exigidos"; papel sem teto mostra o motivo gravado (`reason`, ex.: unit sem composição legível).
- **Filtros por URL** (`?papel=`, `?segmento=`, `?compra=1`), sem estado no cliente; valor desconhecido é ignorado. "Só compra" mantém apenas os papéis em compra.
- **Rodapé e procedência** como na 5.2; a página mostra a data-base mais recente e a coleta mais recente da lista.
- Os nomes ainda não são links: a ficha (`/empresa/[cvm]`) é a etapa 5.5.
- Testes: regras puras (situação, filtros, URL), consulta contra Postgres com as migrações do pipeline (cálculos de duas datas, só vale o último; retrato do filtro mais recente; empresa sem cálculo; precisão em texto) e renderização da página com dados simulados (nenhum "R$ 0,00" nem "0/0" para dado ausente). 48 testes no total.
- **Não conferido**: a lista contra o Neon real (não há acesso a ele nesta sessão) nem o visual no navegador; isso fica para a primeira publicação na Vercel, comparando com `acoesb3 ceilings list`.

## Notas da etapa 5.4

- **Filtro da B3** (`/filtro`): retrato mais recente de `screen_result` para a B3 inteira, 50 empresas por página, lista acompanhada primeiro. Busca por nome, nome fantasia ou ticker do FCA (sem diferenciar caixa; `%` e `_` valem como texto), filtro por status com a contagem de cada um (as contagens respeitam a busca e "só a lista", não o status escolhido) e "só a lista acompanhada". Página além do fim é ajustada para a última.
- **Critérios**: cada empresa mostra o que reprovou e o que ficou indisponível, e um bloco expansível com valor, limite e resultado de todos os critérios. Valor no formato do critério (contagem de anos/quedas, percentual, volume em reais); critério sem valor = "indisponível"; motivo (`data`, `history`, `no_security`, `outliers`) em português.
- **Pendências** (`/filtro/pendencias`): proventos suspeitos da lista sem decisão (e quantos há na B3 inteira), eventos societários suspeitos (30 mais recentes) e anos de DVA zerada a lançar, cada um com o comando a rodar. A tela só lê; a decisão continua por comando ou workflow.
- **Limites conhecidos**: o ticker mostrado é o do FCA (`company_security`), que pode listar papel antigo; o limite de cada critério é o texto gravado pelo pipeline (só troca o ponto decimal por vírgula); empresas fora da lista não têm link para ficha (a ficha é só da lista).
- Testes: regras puras, consultas contra Postgres com as migrações (retrato mais recente, status, busca com curingas, ticker, paginação sem repetir empresa, pendências com decisão e só da lista) e renderização das duas páginas. 67 testes no total.
- **Não conferido**: contra o Neon real (contagens por status e pendências devem bater com `compute` e `review list`) nem o visual no navegador; fica para a primeira publicação.

## Notas da etapa 5.5

- **Ficha** (`/empresa/[cvm]`): só existe para empresa da lista acompanhada (fora dela, 404). Abas por `?aba=` (teto, filtro, preco, origem); a aba do simulador entra na 5.7. Os nomes na lista (`/`) e no filtro (só quem está na lista) agora levam à ficha.
- **Preço teto**: consolidado (mediana, K, votos), tabela de papéis com situação em texto e a tabela dos 5 métodos com situação, motivo, teto por ação e, expansível, os **insumos gravados** (`ceiling_method.inputs`) em português e no formato de cada um (`describeInputs`; chave desconhecida aparece como veio, o detalhe longo do DCF fica no comando `ceilings list --dcf`). Cada método mostra fonte, data-base e coleta.
- **Filtro**: critérios do retrato mais recente, 5 gráficos de colunas (lucro, ROE, dividendo por ação, DY, payout) e a tabela com os mesmos valores, tudo lido do detalhe de `screen_criterion` (nenhum cálculo na tela); ano sem dado fica sem barra e "indisponível" na tabela; ano de outlier pendente ou excluído fica em cinza; fonte do provento por ano e proventos suspeitos com a decisão.
- **Preço**: fechamento semanal (último pregão da semana) do COTAHIST por papel e período (1, 3, 5, 10 anos), com os eventos societários como linhas verticais. **Decisão adotada por padrão (a confirmar)**: o preço é mostrado **sem ajuste por desdobramentos** (o pipeline não grava série ajustada e duplicar a regra na tela seria um segundo cálculo); como o teto está na base de ações de hoje, a linha do teto só é desenhada **depois do último evento societário** do período, com o aviso na tela.
- **Origem**: cadastro (CNPJ, setor CVM, plano de contas, reclassificação manual), eventos aplicados (origem, base da data, conhecido desde), saltos de preço suspeitos ou rejeitados e proventos por exercício na última versão da DFP, marcando o que foi lançado à mão.
- **Gráficos** (SVG no servidor, sem biblioteca): seguem o guia de dataviz (marcas finas, ponta arredondada, grade em fio, só o último valor rotulado, legenda quando há 2 séries, tabela equivalente). Cores 1 (azul) e 2 (laranja) passaram no `validate_palette` (CVD ΔE 24,7). Verificado em captura no Chromium (desktop e 390 px): corrigi rótulo cortado na borda, texto minúsculo do gráfico de preço no celular e quebra do rótulo de outlier. **Limite**: o app ainda não tem tema escuro, então os gráficos têm só a paleta clara; a dica ao passar o mouse é a nativa do navegador (`<title>`), sem cursor com linha vertical.
- Testes: 109 no total (gráficos, descrição dos insumos, parâmetros da URL, as 5 consultas contra Postgres com as migrações, e a página com as 4 abas, empresa fora da lista e banco fora do ar).
- **Não conferido**: contra o Neon real (valores da ficha de 2 empresas contra `ceilings list --dcf`, como no roteiro) nem o fluxo logado no navegador; fica para a primeira publicação na Vercel.

## Notas da etapa 5.6

- **Simulador** em `web/src/lib/ceiling/` (`methods.ts`, `consolidate.ts`, `simulate.ts`, `params.ts`), espelhando `ceiling.py` função a função, com `decimal.js` (28 dígitos, arredondamento par, cópia própria que não mexe na formatação). `simulate(empresa, parâmetros, preços)` refaz os métodos, a mediana, o K, as faixas e a votação de cada papel a partir de `ceiling_method.inputs`; sem alterar nada, devolve o que o pipeline gravou.
- **O que a tela pode alterar** (`ceiling.*` de `app_config`, mesmos nomes): taxa do Bazin, multiplicador de Graham, k, g mínimo e máximo e spread do Gordon, DCF (ligado, taxa, anos, perpetuidade, g mínimo e máximo, **crescimento informado**), tabela de K, faixas e o preço de cada papel. **Não altera** janelas de exercícios, alíquotas nem mínimos de anos (`dividend_years`, `lpa_years`, `multiple_years`, `tax.*`...): mudam *quais* exercícios entram nas médias e exigiriam os dados brutos (decisão de 08/10/2026: parâmetros e preço, sem trocar insumos).
- **Nunca inventa valor**: quando faltam insumos (método excluído pelo plano de contas, indisponível por falta de dado, DCF gravado antes desta etapa), o método sai como gravado e marcado `recomputed: false`. O simulador pode destravar o que o parâmetro destrava: Gordon excluído por spread volta com outro k; **DCF indisponível por crescimento histórico (Sanepar, Cemig, TIM) passa a ter valor ao informar o crescimento**.
- **Mudança no pipeline**: `dcf()` passou a gravar `shares` e `shares_factor` em `inputs` (o divisor por ação). **Os DCF já gravados no Neon não têm isso**: rode `compute --step ceilings` para o simulador poder refazê-los; até lá o DCF aparece com o valor gravado.
- **Paridade**: `acoesb3 ceilings parity-export` (sem banco) gera `web/tests/parity/cases.json` a partir de `pipeline/acoesb3/parity.py`: 11 empresas sintéticas (comum, banco, prejuízo, outlier, dividendo faltando, DCF sem crescimento, sem demonstrações, plano não identificado...) × 20 variações de parâmetros, mais 7 casos de métodos prontos com preços **exatamente em 80%, 100% e 120% do teto** (227 casos). O snapshot é o que o Python grava com os parâmetros padrão; o esperado é o que o Python calcula com os parâmetros novos a partir dos dados brutos; o TS parte só do snapshot. Compara status, motivo, K, votos, faixa e compra por igualdade e valores a 1e-9 relativo.
- **Sincronia**: `test_parity.py` falha se o fixture versionado estiver defasado em relação a `ceiling.py`/`parity.py` e se `BASE_CONFIG` divergir de `app_config` (migrações); o `pipeline-ci` agora também roda quando `web/tests/parity/**` muda. Mudou uma regra: mudar o TS e regerar o fixture no mesmo commit.
- **Teste do teste**: injetei 7 erros no simulador (taxa do Bazin +1e-7, DCF com um ano a menos, Gordon sem limite superior, faixa `<` em vez de `<=`, voto `<=` em vez de `<`, mediana par errada, precisão de 15 dígitos). Os 6 primeiros derrubam o teste; o da precisão não (a tolerância é 1e-9, então a paridade não distingue 28 de 15 dígitos).
- Testes: pipeline 338 (10 novos), web 368 (259 em `lib/ceiling`: 231 de paridade e 28 com números conferidos à mão, entre eles os mesmos de `test_ceiling.py`). O teste de unidade achou um defeito: parâmetro inválido lançava o erro cru do `decimal.js` sem citar a chave.
