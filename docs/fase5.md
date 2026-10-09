# Fase 5 — Tela Next.js, login Google, filtro, ficha da empresa e simulador

**Estado (09/10/2026): concluída no código; falta a primeira publicação na Vercel e as conferências com dados reais** (lista
abaixo). 439 testes no `web/` e 338 no `pipeline/`, lint e build limpos, CI verde no GitHub em todas as etapas
(`web-ci` de 5.0 a 5.8, `pipeline-ci` na 5.6). Regras decididas: seção 9.1 da especificação. A tela **só lê** o Neon; a
única lógica de cálculo em TypeScript é o simulador do preço teto, com teste de paridade contra `pipeline/acoesb3/ceiling.py`.

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

## O que existe

| Rota | O que mostra | Lê |
|---|---|---|
| `/login`, `/acesso-negado`, `/api/auth/*` | Login Google; recusa de e-mail fora da lista | Google, `ALLOWED_EMAILS` |
| `/` | Lista acompanhada: papel, preço, teto, razão, faixa, votos, situação, status do filtro; filtros por papel, segmento e "só compra" | `watchlist`, `ceiling_*`, `screen_result` |
| `/filtro` | Filtro da B3: busca por nome ou ticker, status com contagem, critérios com valor e limite, paginação | `screen_result`, `screen_criterion`, `company_security` |
| `/filtro/pendencias` | Proventos suspeitos, eventos suspeitos e DVA zerada, com o comando a rodar | `dividend_outlier`, `corporate_event`, `indicator_annual` |
| `/empresa/[cvm]` | Ficha (só da lista): abas Preço teto, **Simulador**, Filtro, Preço e Origem dos dados | `ceiling_*`, `app_config`, `screen_*`, `quote_daily`, `company_event`... |
| `/backtest` | Aviso de viés, validação, ajuste, gráfico, fluxos, avisos, universo e ordens | `backtest_*` |

- **Leitura do banco**: driver `pg` com `NEON_DATABASE_URL_POOLED`; toda consulta passa por `src/lib/db/queries.ts` (`server-only`), que confere o usuário antes e roda em transação `READ ONLY` (escrita falha, testado). O navegador nunca recebe a URL.
- **Login**: e-mail verificado pelo Google e presente em `ALLOWED_EMAILS` (lista vazia = ninguém entra), conferido no login, no `proxy.ts` e em cada consulta; tirar um e-mail da lista vale na próxima requisição.
- **Procedência**: toda tela mostra fonte, data-base e data de coleta; dado ausente aparece como "indisponível", nunca como zero.

## Diferenças em relação ao roteiro de 08/10/2026

| Roteiro | O que foi feito | Por quê |
|---|---|---|
| Papel do Neon só com `SELECT` (a confirmar) | **Não criado.** O "só lê" é garantido por transação `READ ONLY` | Depende de você criar o papel no console; continua recomendado como segunda camada |
| Driver `@neondatabase/serverless` ou `pg` | `pg` | Funciona no pooler e no Postgres de teste do CI |
| CI regera o fixture de paridade e falha com `git diff` | `test_parity.py` falha se o fixture versionado estiver defasado, e o `pipeline-ci` roda quando `web/tests/parity/**` muda | Mesmo efeito sem instalar o Python no `web-ci` |
| Casos de `ESCALA_MOEDA` (unidade e mil) no fixture de paridade | **Não há**. Os insumos do simulador já são por ação ou em reais | A escala é resolvida no pipeline (`cvm.scale_value`); a tela é testada em `format.test.ts` (reais x mil, `toReais`, escala desconhecida é erro) |
| Gráfico de preço com a linha do teto | Preço **sem ajuste por desdobramentos**; a linha só vale depois do último evento societário | O pipeline não grava série ajustada e refazê-la na tela seria um segundo cálculo (**a confirmar**) |
| Aba do simulador por último | Logo depois de Preço teto | É a segunda coisa que se faz numa ficha |
| Comparar a lista e a ficha com `ceilings list` na entrega | Fica para a primeira publicação | Sem acesso ao Neon real nesta sessão |
| Aviso de viés "fixo" | Acompanha a rolagem só em telas largas | No celular a faixa ocupa ~160 px; ali valem os selos |

## Primeira publicação (passos do usuário)

1. Criar o projeto na Vercel apontando para este repositório, **Root Directory `web`**, produção na branch padrão do repositório (hoje `ccr-d11b7b9a-o4jy33`; confira o nome na Vercel).
2. Cadastrar na Vercel: `NEON_DATABASE_URL_POOLED`, `GOOGLE_CLIENT_ID`, `GOOGLE_CLIENT_SECRET`, `ALLOWED_EMAILS` (separados por vírgula) e `AUTH_SECRET` (gere um valor aleatório, por exemplo `openssl rand -base64 32`). Nenhum valor passa pelo chat nem pelo código.
3. No cliente OAuth do Google, autorizar `https://<dominio-de-producao>/api/auth/callback/google`; o app precisa estar publicado (não em modo de teste). Previews por PR têm URL própria e **não fazem login**, a menos que a URI delas também seja cadastrada.
4. (Recomendado) Criar no console do Neon um papel só com `SELECT` e montar a URL do pooler com ele.
5. Rodar o workflow `compute` com `step=ceilings`: o DCF passou a gravar o divisor por ação (`shares`, `shares_factor`) e, sem isso, o simulador mostra o DCF com o valor gravado.

## Conferências na primeira publicação

Nada abaixo foi conferido com dados reais; é o que falta para fechar a fase de verdade.

1. **Login**: o e-mail da lista entra; outro e-mail cai em `/acesso-negado`; sem sessão, qualquer rota vai para `/login`.
2. **Lista** (`/`) igual a `acoesb3 ceilings list`: preço, teto, razão, faixa, votos e compra de cada papel.
3. **Ficha** de 2 empresas (uma comum, uma financeira) igual a `ceilings list --dcf`: valor e motivo de cada método.
4. **Simulador**: sem alterar nada, cada empresa da lista abre "idêntico ao gravado" (depois do passo 5 acima). Se alguma divergir, é falha de paridade ou insumo faltando: anotar a empresa e o método.
5. **Filtro**: contagem por status igual à do `compute`; pendências iguais a `review list`.
6. **Backtest**: a validação de 08/10/2026 (`dy_5`) igual a `docs/fase4.md`: estratégia líquida 33,2% no período, 15,4% ao ano, queda máxima 14,7%; IDIV 26,6%, 12,5% e 10,6%; 2 de 24 janelas perdidas; queda 4,1 p.p. pior; critério de morte não acionado. Ajuste `dy_5`: 14,2% ao ano, queda 33,1%, 6 de 83 janelas.
7. **Celular**: a lista, a ficha, o simulador e o backtest sem rolagem horizontal da página.

## O que fica de fora, e por quê

| Item | Motivo |
|---|---|
| Revisão de outliers/eventos pela tela | Decisão de 08/10/2026: tela somente leitura; vira fase própria com credencial de escrita |
| Disparo de recálculo pela tela (workflow `compute`) | Idem: exige token do GitHub na Vercel |
| Simulador com troca de insumos (LPA, VPA, dividendo, FCFE) e das janelas/alíquotas | Decisão de 08/10/2026; exigiria os dados brutos e mais regras espelhadas |
| Preço ajustado por desdobramentos no gráfico | Sem série ajustada no pipeline (ver diferenças) |
| Cotação intradiária | Decisão da fase 3 (preço = último fechamento); brapi/Yahoo seguem sem uso |
| Carteira, lançamentos, extrato B3, alocação e alertas | Fases 6 e 7 |
| Releases em PDF e escopo `drive.file` | Fase 8 |
| Novo backtest ou nova validação pela tela | O backtest é do pipeline; a validação só pode ser medida uma vez |
| Tema escuro | O app inteiro é claro; os gráficos têm só a paleta clara |
| Pendências de revisão das fases 2 e 3 (`docs/fase3.md`) | Dependem do usuário; a tela só as expõe |

## Limites conhecidos

- Previews por PR não fazem login (URI do Google por domínio).
- No celular, os parâmetros do simulador ficam acima do resultado; não há como salvar ou compartilhar uma simulação.
- O gráfico de preço é semanal e sem ajuste; a dica ao passar o mouse é a nativa do navegador (sem cursor com linha vertical).
- A paridade compara valores a 1e-9 relativo (não distingue 28 de 15 dígitos de precisão) e só cobre o que está em `ceiling_method.inputs`.
- `npm audit`: 0 vulnerabilidades nas dependências de produção; restam avisos `braces`/`micromatch` só no ferramental do ESLint (dev).
- Auth.js v5 ainda é beta (`next-auth@5.0.0-beta.32`, versão fixa).
- O ticker mostrado no filtro é o do FCA e pode incluir papel antigo.

## Para a próxima fase

A fase 6 (carteira) vai precisar de **escrita** pela tela (lançamentos e upload do extrato): isso exige decidir a credencial de escrita
do banco na Vercel (papel próprio com `INSERT/UPDATE` só nas tabelas da carteira) e abre exceção controlada à regra de só ler. A
revisão de outliers e o disparo do `compute` pela tela podem entrar na mesma decisão.

---

# Notas por etapa (registro)

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

## Notas da etapa 5.7

- **Aba Simulador** na ficha (`?aba=simulador`, depois de Preço teto). Componente cliente (`Simulator.tsx`) que recebe do servidor só o gravado (insumos, papéis com multiplicador e os parâmetros de `app_config` que o pipeline usou) e recalcula no navegador com o mesmo `simulate()` da paridade; nada vai ao servidor nem ao banco. Sem preço teto calculado, a aba avisa em vez de abrir vazia.
- **Campos**: Bazin, Graham, Gordon, DCF (inclui ligar/desligar e o **crescimento do FCFE informado**), faixas, tabela de votos (K) e o **preço de cada papel** (editado na própria tabela de resultados). Percentuais são digitados como "6" ou "6,5" (vírgula ou ponto); milhar, letras e vazio são recusados com a mensagem do campo, nunca trocados por um padrão. Os campos usam os mesmos nomes de `ceiling.*`, e a conversão passa por `paramsFromConfig`, o caminho já coberto pela paridade.
- **Gravado ao lado do simulado**: teto consolidado, cada método, e cada papel (preço, teto, preço ÷ teto, faixa, votos, situação). O que difere do gravado leva a marca "alterado" em texto (não só cor); diferença de até 2e-8 não conta, pois o banco guarda 8 casas. Sem alterar nada o resultado é idêntico ao gravado e o botão "Voltar aos valores gravados" fica desabilitado. DCF desligado aparece como "desligado na simulação", não some.
- **Honestidade do valor**: método que não dá para refazer (excluído pelo plano de contas, indisponível por falta de dado, DCF gravado antes da 5.6) aparece com o valor gravado e a nota "faltam insumos para refazer" (no DCF, "rode compute --step ceilings"). Aviso fixo no topo: nada é gravado, não é o preço teto oficial, janelas e alíquotas são as do pipeline.
- **Erro encontrado e corrigido**: o preço inicial tirava zeros com uma expressão que transformava "100" em "1"; agora só tira zeros depois da vírgula (teste dedicado).
- **Limites**: no celular os parâmetros aparecem acima do resultado (o resultado exige rolar); a conta roda a cada tecla, sem atraso; não há link para compartilhar uma simulação nem como salvá-la.
- **Verificação**: 408 testes no web (19 arquivos). Nos testes: o modelo de visão sobre 5 empresas do fixture de paridade (idêntico ao gravado, inclusive com o gravado arredondado em 8 casas; Bazin, DCF desligado, K, DCF sem crescimento informado, preço alto, campo e preço inválidos), a renderização do componente, a aba na ficha e o carregamento do banco (com as migrações, todos os parâmetros do simulador existem em `app_config`; parâmetro ausente é erro explícito). Injetei 3 erros no modelo de visão (tolerância, detecção de mudança, preço inválido): todos pegos, o terceiro só depois de eu reforçar o teste para checar a mensagem. Conferi em navegador real (Chromium, desktop e 390 px) numa página temporária, já removida: digitar altera e marca, valor inválido mostra o erro sem resultado e "Voltar" restaura campos e preços; sem erros de página.
- `next.config.ts` ganhou `agentRules: false`: o `next dev` gerava um `AGENTS.md` na raiz do `web/` que o repositório não versiona.
- **Não conferido**: a aba contra o Neon real e com login (precisa da publicação na Vercel).

## Notas da etapa 5.8

- **Tela do backtest** (`/backtest`), toda lida de `backtest_run`, `backtest_series`, `backtest_trade` e `backtest_freeze`; nenhum cálculo na tela (retornos, queda máxima, janelas e critério de morte são os gravados pelo pipeline). Seções: faixa do viés, **Validação**, **Ajuste**, gráfico da execução escolhida, fluxos, avisos do cálculo, universo e ordens. `?execucao=` escolhe a validação ou um cenário; sem escolha, abre a validação (ou o cenário congelado, ou o primeiro).
- **Aviso de viés de sobrevivência** (decisão do usuário): faixa sem botão de fechar, acima de qualquer número, que **acompanha a rolagem em telas largas** (no celular sai da tela, pois ocupa ~160 px; ali valem os selos); texto lido de `universe.survivorship_warning` da execução. **Selo "universo de hoje"** ao lado de cada retorno da estratégia (líquida e bruta, em cada cenário) e do título do gráfico; os índices e o CDI não levam selo. Se a execução não trouxer o texto, a faixa usa um **texto padrão** (`FALLBACK_SURVIVORSHIP`): ela nunca some, nem sem backtest calculado nem com o banco fora do ar. A lista de avisos do cálculo não repete o texto da faixa.
- **Validação**: marcada como **medida uma única vez** (data e hora, cenário congelado e a nota do congelamento; "o banco recusa uma segunda medição"), com as medidas das cinco séries, o critério de morte (veredito, e cada regra com o valor da estratégia, o limite configurado da própria execução e o resultado) e a nota de **período curto** quando passa de menos de 3,5 anos (hoje 2,0 anos, não os 3 da especificação, e as janelas de 5 anos que terminam nele se sobrepõem quase por inteiro). Sem janelas ou sem queda para comparar, o veredito é "Indisponível", nunca "não acionado". Sem validação medida, a tela diz isso.
- **Ajuste**: os cenários lado a lado (aporte, líquido e bruto ao ano, queda máxima, janelas perdidas para o IDIV, critério de morte), o congelado marcado e IDIV, Ibovespa e CDI como referência do mesmo período.
- **Gráfico**: níveis reescalados (início = 100) de estratégia líquida, IDIV, Ibovespa e CDI (as séries mensais gravadas), com legenda e valor final de cada série, marcador do início da validação e tabela equivalente com o fim de cada ano. Cores: azul, laranja e verde-água passaram no `validate_palette` (o verde-água tem contraste 2,74:1, aviso que o guia resolve com legenda e tabela, ambas presentes); o CDI é cinza neutro. Dica nativa por mês com todas as séries.
- **Ordens**: as 50 mais recentes (todas até 2.000 com `?ordens=todas`), com a contagem total; data inválida aparece como "indisponível".
- **Estrutura**: `BacktestView` (visual) separada da página (carrega e trata falhas); `lib/backtest.ts` com as regras puras; `db/backtest.ts` com os carregadores (último ajuste de cada cenário, validação, congelamento; configuração de cada execução lida do JSON, inválida = nula).
- **Testes** (440 no web): regras puras (texto padrão do aviso, escolha da execução, níveis reescalados, regras do critério de morte), carregadores contra Postgres com as migrações (versões de um cenário, JSON de configuração em número e em texto, séries desconhecidas ignoradas, ordens), a página com dados simulados (faixa, selos por seção, texto padrão, banco fora do ar, validação acionada e indisponível, sem validação, escolha por URL) e a tela renderizada com o que o carregador devolve do banco. Removi o aviso de 4 formas (texto padrão vazio, selo da tabela de cenários, faixa na falha do banco, botão de fechar): os 4 testes pegaram. Conferi em navegador real (Chromium, desktop e 390 px) numa página temporária, já removida: faixa visível ao rolar no desktop, sem rolagem horizontal da página e sem erros; achei e corrigi o gráfico pequeno no desktop e os cabeçalhos longos da tabela por ano no celular.
- **Não conferido**: a tela contra o Neon real (a validação de 08/10/2026 e os 6 cenários) e logada; fica para a publicação na Vercel. As decisões pendentes da fase 4 (proventos, fim do período, tarifas) aparecem pelos avisos que o próprio pipeline grava em cada execução, sem texto fixo na tela.
