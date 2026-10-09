# AcoesB3 — Especificação v1

Documento de decisões consolidado a partir de 32 perguntas respondidas pelo usuário (03/10/2026).

**Status: aprovada pelo usuário em 03/10/2026, incluindo as suposições da seção 13.** Segredo `NEON_DATABASE_URL` já cadastrado no GitHub Actions.
Todo parâmetro numérico abaixo é **configurável** no sistema; os valores são os padrões iniciais.

## 1. Objetivo

Sistema pessoal para ações da B3 que:
- **(a)** indica se uma ação está para compra ou não (preço teto);
- **(b)** sugere a alocação do aporte mensal;
- **(c)** alerta venda/rebalanceamento.

## 2. Fontes de dados

| Dado | Fonte | Observação |
|---|---|---|
| Demonstrações financeiras | CVM Dados Abertos (DFP/ITR/FCA) | Fonte única dos números. Sem leitura de PDF para números. |
| Release de resultados | CVM (comunicados) → Google Drive | Só para leitura. Empresas que não entregarem à CVM: link manual para o RI. |
| Cotações históricas | B3 COTAHIST (oficial) | Base para cálculos e backtest. |
| Cotação intradiária | brapi / Yahoo (atraso de ~15 min) | Só exibição. Se falhar: fechamento anterior + aviso. |
| Classificação setorial | B3 (setor/subsetor/segmento) | Com reclassificação manual por empresa. |
| Operações do usuário | Lançamento manual + extrato da Área do Investidor B3 (upload) | Reconciliação entre os dois. Sem histórico inicial. |

Duas séries de preço:
- ajustada só por desdobramentos/grupamentos (para múltiplos);
- ajustada também por proventos, de retorno total (para backtest e rentabilidade).

## 3. Universo

- **Filtro**: calculado para a B3 inteira (o backtest precisa de empresas canceladas, sem viés de sobrevivência). Decidido em 04/10/2026: o universo de trabalho é só a **lista acompanhada** (`watchlist`): a **carteira** do usuário e o **radar** (2 a 3 candidatas por segmento da carteira, escolhidas a partir do filtro). Revisão manual, preço teto, DCF, alertas e releases valem só para a lista. `screen.excluded_sectors` perdeu o sentido e fica vazio.
- **Carteira inicial** (04/10/2026): Banco do Brasil, Itaú Unibanco (ITUB4/ITUB3), BB Seguridade, Caixa Seguridade, Porto Seguro, Alupar, Engie, ISA Energia, Sanepar, Copasa, Vivo (Telefônica Brasil). **Segmentos do radar**: bancos, seguradoras, energia (geração e transmissão), saneamento e telecom (`watch.segments`).
- **Acompanhamento detalhado** (DCF, release, alertas): a lista acompanhada; o DCF vale para todas as empresas da lista, exceto bancos e seguradoras (decisão de 05/10/2026, antes: só as que o usuário indicasse).
- **Classes**: uma linha por empresa no filtro e preço teto por classe. Units calculadas pela composição (ex.: TAEE11 = 1 ON + 2 PN).
- **Liquidez**: volume médio diário ≥ R$ 1 mi e presença em ≥ 90% dos pregões (últimos 3 meses).

## 4. Filtro

**Lucratividade**
- lucro líquido positivo em ≥ 8 dos últimos 10 anos;
- ROE médio de 5 anos > 10%.

**Proventos** (dividendos + JCP)
- pagos em 10 de 10 anos;
- DY médio líquido de 5 anos > 5%;
- payout entre 25% e 100%;
- dividendo por ação caiu em no máximo 4 dos últimos 10 anos, medido pela **média móvel de 3 anos** (a média do DPS dos 3 anos até k contra a média móvel do ano anterior; até 7 comparações na janela, mínimo de 3 para avaliar). Decidido em 04/10/2026; antes: ano contra ano, no máximo 3 (`screen.dps_method`, `screen.dps_max_drop_years`).

**DY líquido**: alíquotas configuráveis (JCP 15%, dividendo 0%).

**Outliers**: provento > 2× a mediana de 5 anos é marcado como suspeito.
- Fica fora do histórico por padrão.
- Aparece em destaque na tela.
- O usuário revisa e decide incluir ou não.

**Limitação de histórico**: os dados estruturados da CVM começam por volta de 2010.

### 4.1 Definições operacionais do filtro (fase 2, 03/10/2026)

Decididas pelo usuário:
- **Proventos**, por exercício, nesta ordem (ver a decisão de 04/10/2026 mais abaixo: DVA passou à frente do FRE): valor informado à mão ou por outra fonte (`dividend_override`) > **FRE** (distribuição de dividendos por classe de ação: valor e data de pagamento; soma de todas as classes, JCP à parte) > DVA da DFP (total declarado no exercício, sem data de pagamento). Cada ano guarda a fonte. O FRE de 2025 em diante não traz mais esse arquivo (layout novo), então os exercícios mais recentes dependem da DVA ou do valor manual. Aprovado pelo usuário em 04/10/2026. **Decidido em 04/10/2026 (substitui a ordem acima): DVA > FRE.** A DVA vale em todos os anos e o FRE só cobre DVA ausente ou zerada (`dividends.preferred_source = dva`; `fre` restaura a ordem anterior). Medição de 04/10/2026 (2.583 exercícios com as duas fontes): concordam em 65%; quando divergem, o payout médio pela DVA é plausível (40%–64%) e pelo FRE não (173% quando o FRE é maior, 31% quando é menor). Trocar de fonte no meio da janela (FRE até 2021, DVA depois) cria altas e quedas falsas no dividendo por ação.
- **Menos de 10 anos de DFP**: não reprova; fica como **histórico insuficiente**, separado de quem reprovou num critério.
- **Setor**: setor declarado à CVM, com reclassificação manual por empresa (`company_class_override`). `screen.excluded_sectors` não é mais usado (ver seção 3).
- **Retratos**: o cálculo recebe uma data-base e só usa DFP já entregues nela (`filing_available`). Grava o retrato de hoje e um por fim de ano a partir de `screen.snapshot_first_year` (2020: antes disso a janela de 10 anos não fecha, pois a DFP estruturada começa em 2010).
- **Queda do dividendo por ação**: por ação de verdade, com ajuste por desdobramento/grupamento/bonificação (ver eventos abaixo).
- **Payout**: média de 5 anos dentro da faixa (não ano a ano).
- **Outlier**: mediana dos 5 anos **anteriores**, sem o próprio ano, e só se for **pico isolado**: o ano seguinte fica abaixo de 70% do valor (`outlier.persistence`); o último exercício nunca é marcado (aprovado pelo usuário em 04/10/2026).
- **Universo e tickers**: empresa sem papel mapeado fica `not_listed`. Tickers sem FCA são mapeados pelo nome do papel quando o casamento é inequívoco (`mapping.auto_*`); ambíguo não mapeia.
- **DVA zerada**: depois do último exercício em que o FRE mostra pagamento, anos de DVA zerada (sem nenhum ano positivo) ficam **indisponíveis** e vão para a lista de lançamento manual (`review list`), não contam como "não pagou". FRE e DVA que diferem ~1000× deixam o ano indisponível (escala incerta).
- **PL**: a conta do PL é achada pelo **nome** (nível 2 do passivo, "Patrimônio Líquido..."), não pelo código, e os não controladores pelo filho com esse nome; sem nomes valem 2.08/2.03. Exige recarga das DFP (migração 0006).
- **Dividendo por ação** = total de proventos do exercício ÷ ações no fim do exercício, levado à base de ações da data-base. Ações vêm do capital social do FRE (retrato mais próximo do fim do exercício, ajustado por eventos), não da DFP: a quantidade da DFP vem em unidades ou em milhares conforme a empresa, sem indicação de escala (Ambev, Vale e Itaú em milhares). Sem payout × LPA: as contas `3.99.01.01/.02` nem sempre são ON/PN.
- **DY**: dividendo total do ano ÷ valor de mercado (fechamento do último pregão do exercício × ações do FRE por classe). Com o FRE, o DY existe desde 2010 (antes de adotar o FRE era indisponível antes de 2020).
- **Eventos societários**: fator oficial do FRE (ações depois ÷ antes; desdobramento, grupamento, bonificação), com data de efeito dada pelo salto de preço do COTAHIST que casa com o evento (até 200 dias depois da aprovação, fator dentro de 8%); sem salto, vale a data de aprovação. Eventos só do COTAHIST valem depois do que o FRE cobre (se automáticos ou confirmados) ou se informados à mão; os suspeitos esperam revisão. Um salto de preço suspeito (fora do FRE) vira automático se a contagem de ações de dois retratos consecutivos do FRE cresceu pelo mesmo fator (`events.snapshot_tolerance`): cobre os anos do FRE sem arquivo de desdobramentos (caso Engie, bonificação de 40% em 27/11/2025). Retrato de FRE entregue perto do evento: compara-se a contagem do retrato com o antes/depois do evento para saber se já a inclui.
- **Valor de mercado e troca de ticker**: cada classe usa o papel mais negociado que tiver preço na data (a ISA trocou TRPL por ISAE em 11/2024).
- **Queda do DPS**: método `avg` (média móvel de `screen.dps_alt_avg_years` = 3 anos) decide o status; o ano contra ano (`yearly`) fica no detalhe do critério, só informativo. `screen.dps_method = yearly` restaura o método anterior. Em 04/10/2026, com `avg` e limite 4, Engie e Taesa têm 3 quedas cada e passam.
- **Dados desatualizados**: empresa cuja última DFP tem mais de 730 dias em relação à data-base (`screen.max_data_age_days`) fica `stale` e não é avaliada. Aprovado pelo usuário em 04/10/2026.

Adotadas por padrão (corrigir se discordar; todas configuráveis):
- **Lucro e PL**: lucro atribuído aos controladores; PL dos controladores (consolidado menos não controladores). Cada conta é resolvida por presença, não por "plano": lucro em `3.09.01`, `3.11.01` ou `3.13.01`; PL em `2.08` (se existir) ou `2.03`; proventos na DVA em `7.09.04`, `7.11.04` ou `7.08.04`. No escopo individual (empresas que só entregam individual) usa-se o lucro total (`3.11` comum, `3.09` banco, `3.13` seguradora) e o PL sem subtrair não controladores.
- **ROE** = lucro ÷ média do PL do início e do fim do exercício. PL médio ≤ 0: indisponível.
- **"Últimos N anos"**: os N exercícios que terminam no último exercício disponível na data-base. Falta um exercício no meio da janela: indisponível.
- **Payout** = (JCP + dividendos) ÷ lucro do controlador (bruto); faixa inclusiva; anos de prejuízo e de outlier ficam fora da média (mínimo de 3 anos restantes, `outlier.min_valid_years`).
- **Proventos em 10 de 10 anos**: total declarado > 0 em todos os anos. Ano de outlier excluído conta como pago.
- **Queda do dividendo por ação**: queda = DPS menor que o do ano anterior (tolerância `screen.dps_drop_tolerance`, padrão 0), com cada ano levado à base de ações da data-base pelos eventos societários. Pares de anos com métodos diferentes (exato x estimado), ano de outlier ou, no método estimado, ano de prejuízo são pulados; exige 6 comparações (`screen.dps_min_pairs`), senão indisponível.
- **Outlier**: total anual > 2 × mediana dos 5 anos anteriores, sem o próprio ano (mínimo de 3 anos com dado; mediana zero não conclui). Sem decisão do usuário, o ano fica fora das médias de DY e payout; decisão `include` o devolve. A revisão é por comando até a tela existir (fase 5).
- **Liquidez**: janela de 3 meses até a data-base; volume = soma de todas as classes ÷ pregões da janela; presença = pregões com negócio em alguma classe ÷ pregões da janela. Entra como critério do filtro, com motivo visível.
- **Status do retrato**: `approved`, `rejected` (algum critério falhou), `insufficient_history` (menos anos de DFP que a janela), `insufficient_data` (falta conta, ano no meio ou preço) ou `excluded` (setor fora do universo) ou `stale` (dados desatualizados) ou `not_listed` (sem papel mapeado). Falha de um critério vence critério indisponível.

## 5. Preço teto

| Método | Aplicação | Parâmetros | Exclusões |
|---|---|---|---|
| Bazin | Todas | dividendo médio líquido de 5 anos (sem outliers) ÷ 6% | — |
| Graham | Todas | √(22,5 × LPA médio de 3 anos × VPA) | LPA ≤ 0, VPA ≤ 0, bancos e seguradoras |
| Gordon | Todas | D1 ÷ (k − g); k = 12% nominal; g = crescimento histórico de 5 anos limitado a [0%, 5%]; D1 = dividendo médio líquido de 5 anos × (1+g) | k − g < 3 p.p. |
| Múltiplos | Todas | P/L mediano de 10 anos × LPA médio de 3 anos (não financeiras); P/VP mediano de 10 anos × VPA (bancos e seguradoras). Conta como 1 método. | Anos de lucro negativo fora do P/L |
| DCF (FCFE) | Só lista acompanhada (todas, exceto bancos e seguradoras) | Desconto a 12%; 5 anos projetados (crescimento histórico, sobrescrevível por empresa) + perpetuidade de 4% | Bancos e seguradoras |

**Consolidação**: preço teto = **mediana** dos métodos aplicáveis.

**"Compra"** exige preço < mediana **e** preço < teto em pelo menos K métodos:
- 5 métodos → K = 3
- 4 métodos → K = 3
- 3 métodos → K = 2
- menos de 3 → "dados insuficientes": visível, mas fora do aporte automático.

**Faixas** (preço ÷ teto):

| Faixa | Situação |
|---|---|
| < 80% | Compra forte |
| 80–100% | Compra |
| 100–120% | Manter |
| > 120% | Cara, avaliar venda |

### 5.1 Definições operacionais do preço teto (fase 3, 05/10/2026)

O preço teto é calculado **só para a lista acompanhada** (`watchlist`), por `compute --step ceilings` (tabelas `ceiling_method`, `ceiling_result`, `ceiling_class`; parâmetros `ceiling.*` em `app_config`).

Decididas pelo usuário:
- **VPA** = PL do controlador ÷ ações no fim do último exercício, levado à base de ações da data-base pelos eventos societários.
- **Preço atual** = último fechamento do COTAHIST (não a cotação intradiária).
- **Classes**: o teto vale por papel (ON, PN, unit); a unit é tratada pela composição do FCA (TAEE11 = 1 ON + 2 PN = 3 ações).
- **Gordon**: o crescimento histórico de 5 anos é o do **dividendo total** (não por ação, não o lucro); o dividendo médio líquido usa os 5 últimos exercícios fechados, com o ano de outlier fora.
- **P/L e P/VP medianos de 10 anos**: preço de fim de exercício ÷ LPA (lucro ÷ ações do FRE). Ano de prejuízo sai do P/L; empresa com menos de 10 anos usa o que existe.
- **DCF (FCFE)** para todas as empresas da lista (exceto bancos e seguradoras); exige as contas do fluxo de caixa (DFC), cujos códigos foram verificados na fonte real (ver abaixo e `docs/fontes.md`).
- **Alíquotas** do dividendo médio líquido: as de `tax.*` (JCP 15%, dividendo 0%).
- **Bancos e seguradoras**: sem Graham e sem DCF; ficam 3 métodos (Bazin, Gordon, P/VP) e K = 2.

Adotadas por padrão (corrigir se discordar; todas configuráveis):
- **Data-base**: a data do cálculo (`--as-of`, padrão hoje). Só valem DFP entregues até a data (mesma regra de ponto no tempo do filtro) e o último fechamento até ela; fechamento com mais de `ceiling.price_max_age_days` (10) de defasagem não vale e o papel fica sem teto. Cada resultado guarda a data-base (último exercício), a data de coleta e a data do preço. A fase 4 reutiliza a mesma função com datas de fim de ano.
- **Valor por ação igual em todas as classes**: o teto por ação é um só para a empresa (proventos totais ÷ ações totais, como no DPS do filtro); não usa os proventos por classe do FRE, que não existem no layout de 2025+. A unit vale a soma das ações da composição. Composição ilegível (só `1 ON / 2 PN` foi verificado no FCA) deixa a unit sem teto, com o motivo.
- **Por ação, na base de ações da data-base**: dividendo, LPA e VPA de cada exercício = total ÷ ações do fim do exercício (FRE) ÷ eventos posteriores (`shares_factor`).
- **Bazin**: média do dividendo líquido por ação nos `ceiling.dividend_years` (5) últimos exercícios ÷ 6%. Ano de outlier sai da média (mínimo `outlier.min_valid_years` = 3 anos restantes); exercício faltando no meio ou sem proventos/ações = indisponível; média ≤ 0 = indisponível.
- **Gordon**: crescimento composto do dividendo total bruto entre a primeira e a última ponta dos 5 exercícios (4 intervalos), limitado a [0%, 5%]; pontas ausentes, ≤ 0 ou de outlier = indisponível. D1 = dividendo médio líquido por ação × (1 + g); k − g < 3 p.p. exclui o método.
- **Graham**: LPA médio dos 3 últimos exercícios (com anos de prejuízo dentro da média); LPA médio ≤ 0 ou VPA ≤ 0 exclui o método.
- **Múltiplos**: P/L de cada exercício = valor de mercado do fim do exercício (fechamento × ações do FRE por classe, o mesmo do DY) ÷ lucro, equivalente a preço ÷ LPA; mediana dos exercícios válidos da janela de 10 anos, **mínimo de 3** (`ceiling.multiple_min_years`, número escolhido por falta de regra); bancos e seguradoras: P/VP mediano × VPA.
- **Plano de contas não identificado**: Graham e múltiplos ficam indisponíveis (não dá para saber se é financeira).
- **Consolidação**: mediana dos métodos `ok`; método excluído por regra ou indisponível não conta. K por quantidade de métodos em `ceiling.k_by_methods` (5 → 3, 4 → 3, 3 → 2). Menos de 3 métodos: `insufficient` (o teto aparece, mas nunca é compra). Observação: com a regra "preço abaixo da mediana", K só pode reprovar com 4 métodos (com 3 e K = 2 ou com 5 e K = 3 a mediana já garante os votos).
- **Compra**: preço < teto (mediana) **e** preço abaixo do teto de pelo menos K métodos. A faixa (`strong_buy`, `buy`, `hold`, `expensive`) usa só preço ÷ teto: < 80%, 80% a < 100%, 100% a 120% (inclusive), > 120%. Preço abaixo do teto sem os K votos fica na faixa de compra mas com `buy = false`.

- **DCF (FCFE)** (contas verificadas em 05/10/2026, `docs/fontes.md`): FCFE do exercício = caixa operacional (6.01) + investimento em ativos (contas 6.02.xx de imobilizado, intangível e ativo de contrato/concessão, incluindo venda de imobilizado) + dividendos e JCP recebidos de investidas + fluxo de dívida (contas 6.03.xx que não são de acionistas: captações, amortizações, juros, arrendamentos, derivativos, custos de captação). Ficam fora: aplicações financeiras, compra e venda de participações, dividendos e JCP pagos, aumentos e reduções de capital, tesouraria. A classificação é pela descrição da conta (listas de expressões em `fcfe.*`), pois só 6.01, 6.02 e 6.03 são padronizadas. **Base** = média do FCFE dos 3 últimos exercícios (`ceiling.dcf_base_years`); **crescimento** = o informado para a empresa (`review dcf-growth`) ou o crescimento composto do FCFE entre as pontas dos 5 exercícios, limitado a [0%, 5%] (`ceiling.dcf_g_min/max`, limites escolhidos por analogia com o Gordon); ponta de FCFE ausente ou ≤ 0 sem crescimento informado = indisponível; projeta 5 anos a 12% com perpetuidade de 4%; valor total ÷ ações do último exercício na base de ações da data-base. FCFE médio ≤ 0 = indisponível. Exercício sem DFC detalhado = indisponível. Limitações: o valor é o do fim do último exercício (não é levado até a data-base); companhias de transmissão e concessionárias podem registrar o investimento em ativo de contrato dentro do caixa operacional, que então já o desconta.
- **Conferência do DCF**: `acoesb3 ceilings list --dcf` imprime, por exercício, o FCFE e cada conta do DFC no grupo em que foi classificada; `ceiling.dcf_enabled = false` tira o método sem apagar nada.

## 6. Alocação do aporte

- **Elegíveis**: ações com peso abaixo do alvo e na faixa de compra. O desconto define o quanto cada uma recebe.
- **Peso-alvo**: igual para todas, ajustável por ação.
- **Limites**: máximo de 10% por ação e 30% por setor; no máximo 3 ações por aporte.
- **Lote**: mercado fracionário (ações inteiras).

## 7. Venda e rebalanceamento

- **Alertas**: preço > 120% do teto; ação deixou de passar no filtro (sempre "avaliar venda"); concentração acima do limite; dívida líquida/EBITDA > 3× (não se aplica a financeiras); 2 trimestres seguidos de queda de lucro.
- **Rebalanceamento** só via aportes. O sistema não sugere venda por concentração.

## 8. Backtest

- **Ponto no tempo**: um balanço só entra a partir da data de entrega à CVM **da versão cujos números estão guardados** (decisão de 03/10/2026; view `filing_available`). Documento reapresentado só entra na data da reapresentação, mesmo que a 1ª versão seja anterior. Empresas canceladas incluídas (sem viés de sobrevivência).
- **Período**: 2012 em diante. Ajuste até 3 anos atrás; os **3 últimos anos ficam reservados para validação**.
- **Comparação**: Ibovespa, IDIV e CDI, mais variações de parâmetros (DY desejado, K etc.).
- **Critério de morte**: aviso se o retorno total perder do IDIV em mais de 50% das janelas móveis de 5 anos, **ou** se a queda máxima for mais de 10 p.p. pior que a do IDIV.

### 8.1 Definições operacionais do backtest (fase 4, 08/10/2026)

Decididas pelo usuário:
- **Universo**: o viés de sobrevivência é aceito e **avisado na tela**. O backtest roda na lista acompanhada de hoje (`watchlist`: carteira e radar), a única com preço teto e DFC detalhado; empresas canceladas ficam de fora. O aviso fica em `backtest_run.warnings` e `universe.survivorship_warning`, para a tela da fase 5. Isto **substitui** o trecho "empresas canceladas incluídas" do ponto no tempo acima (sem viés), que continua valendo para o filtro de toda a B3.
- **Estratégia**: compra quando `buy` é verdadeiro (preço abaixo da mediana e do teto em K métodos); vende a **posição inteira** quando preço ÷ teto passa de 120% (`backtest.sell_above_ratio`); decisão **mensal** no último pregão do mês; aporte mensal testado em R$ 1.000, 1.250 e 1.500 (cenários `aporte_*`); pesos pela seção 6 (peso-alvo igual, desconto define a parte, até 3 empresas por aporte), com os limites de 10% por ação e 30% por setor **só quando há posições suficientes** para cumpri-los (1 ÷ limite: 10 empresas, 4 setores); custos e impostos como parâmetros (corretagem 0; taxas da B3; 15% de ganho de capital com isenção de R$ 20 mil de vendas por mês e compensação de prejuízo).
- **Índices**: Ibovespa e IDIV pela B3, CDI pelo Banco Central (SGS 12). Formatos em `docs/fontes.md`.
- **Anos sem DFC detalhado**: K menor, como já vale (o DCF fica indisponível e o preço teto usa os outros métodos).
- **Critério de morte**: janelas móveis de 5 anos com início todo mês (`backtest.window_years`); aciona se a estratégia perde do IDIV em mais de 50% das janelas ou se a queda máxima é mais de 10 p.p. pior que a do IDIV.
- **Ajuste e validação**: os parâmetros são ajustados e congelados com os dados de 2012 a 2023; o período de `backtest.validation_start` (2024-01-01) em diante é medido **uma única vez**, sem reajuste depois. O banco impede a segunda medição (índice único em `backtest_run`) e recusa a validação se algum parâmetro mudou depois do congelamento (`cfg_hash`).

**Retorno total (correção do que foi pedido)**: o usuário pediu proventos reinvestidos "por ajuste do próprio COTAHIST". Verificado: o COTAHIST não traz fator de ajuste por proventos (o parser guarda `FATCOT`, o fator de cotação por lote de mil, e `DISMES`, o número da distribuição, que só marca que houve evento). Adotado por padrão, a confirmar: os proventos vêm do que o filtro já usa (DVA/FRE por exercício, `indicator_annual`), por ação, e entram em caixa na **data de pagamento do FRE** quando existe (exercícios até 2021) e, senão, na **data de entrega da DFP** (ponto no tempo; subestima o reinvestimento de dividendos pagos antes). Repartição do total do exercício pelas datas na proporção dos valores do FRE. O caixa rende CDI até a compra seguinte, e os proventos recebidos são reinvestidos pelo mesmo processo de alocação do aporte mensal (entram no caixa). JCP com 15% retidos (`tax.jcp`), dividendo isento (`tax.dividend`). `backtest.dividend_timing`: `fre_dates_else_filing` (padrão), `filing` ou `none` (só preço).

Adotadas por padrão (corrigir se discordar; todas configuráveis):
- **Execução**: o sinal usa o fechamento do último pregão do mês e a ordem é executada no fechamento do pregão seguinte (`backtest.exec_lag_days`). Ações inteiras (mercado fracionário). O imposto do mês é pago no mesmo dia da venda (a DARF vence só no mês seguinte, o que torna o cálculo conservador).
- **Uma classe por empresa**: em cada aporte compra-se o papel (ON, PN ou unit) de menor preço ÷ teto entre os de compra; a venda olha cada papel pela própria razão. Ticker que mudou (TRPL4 → ISAE4) entra como uma série só da classe.
- **Peso-alvo**: igual entre as empresas da carteira e as escolhidas no mês (1 ÷ N); elegível = peso abaixo de 1 ÷ (carteira + candidatas) e na faixa de compra; escolhem-se as 3 de maior desconto (1 − razão); a parte de cada uma é proporcional ao desconto, limitada ao que falta para o alvo (e aos limites, se ativos), e a sobra se redistribui. O que não couber fica em caixa. Setor = segmento da lista acompanhada.
- **Caixa** rende CDI (`backtest.cash_earns_cdi`) para a comparação com CDI, Ibovespa e IDIV (investidos 100%) não penalizar a estratégia pelo caixa parado.
- **Retorno ponderado no tempo** (cota): o aporte entra ao valor da cota do dia, de modo que aportes não distorcem o retorno; as janelas de 5 anos e a queda máxima usam a cota. O critério de morte usa a estratégia **líquida** (custos e impostos); a bruta é mostrada ao lado.
- **Período**: início em 2012-01 (`backtest.start_date`), fim em 2025-12-31 (`backtest.end_date`): o FRE de 2025 em diante não traz pagamentos e a DVA de 2026 ainda não existe, então os proventos de 2026 não são conhecidos e medir 2026 dobraria um viés contra a estratégia. Os primeiros anos têm poucos métodos válidos (5 exercícios de dividendos só existem a partir de 2015), então o aporte fica em caixa até aparecer papel elegível.
- **Validação**: as janelas de 5 anos que terminam depois de `validation_start` e a queda máxima do período de validação (a carteira continua a mesma, a simulação é uma só desde 2012).
- **Custos da B3**: 0,03% por ordem (tabela vigente para ADTV até R$ 3 mi; histórico não verificado); sem IRRF "dedo-duro".

## 9. Infraestrutura

- **Banco**: Neon (Postgres, plano grátis: 1 GB por projeto, verificado em 03/10/2026). Guardar só as contas usadas nos cálculos: lista editável na tabela `cvm_account` (cobre os planos de contas de empresa comum, banco e seguradora).
- **Demonstração usada**: consolidada; individual só quando a empresa não entrega consolidada.
- **Processamento**: Python em lotes no GitHub Actions (coleta diária, cálculos, recálculo disparado pela tela ao mudar configuração, 2–5 min).
- **Tela**: Next.js na Vercel. Lê resultados prontos do banco.
- **Simulador**: recalcula uma ação na hora (TypeScript), com teste automático de paridade contra o Python.
- **Login**: Google, lista de e-mails permitidos (inicialmente só o do usuário). Banco preparado para vários usuários.
- **PDFs**: Google Drive do usuário, uma pasta por empresa. Acesso só aos arquivos criados pelo app. App no Google Cloud publicado (não em modo teste).
- **Alertas**: só dentro do sistema por enquanto. Falha de coleta também gera e-mail automático do GitHub Actions. Toda tela mostra a data-base e a data de coleta de cada dado.

### 9.1 Definições operacionais da tela (fase 5, 08/10/2026)

Decididas pelo usuário (roteiro em `docs/fase5.md`):
- **Telas**: lista acompanhada, filtro da B3 inteira, backtest e ficha da empresa (com o simulador numa aba), menu fixo no topo.
- **Ficha**: os 5 métodos do preço teto, critérios do filtro com histórico anual, gráfico de preço com a linha do teto, eventos societários e dados de origem.
- **Simulador**: recalcula parâmetros (`ceiling.*`) e preço a partir dos insumos anuais já gravados em `ceiling_method.inputs`; não troca insumos à mão. Implementação única em TypeScript com `decimal.js`, teste de paridade contra `ceiling.py` e fixture versionado em `web/tests/parity/cases.json`, gerado por `acoesb3 ceilings parity-export` e conferido pelo CI. Só altera o que age sobre os insumos gravados (taxas, multiplicador, k, limites de g, parâmetros do DCF, crescimento informado do DCF, K, faixas e preço); janelas de exercícios, alíquotas e mínimos de anos exigem os dados brutos e ficam no pipeline. Sem os insumos para refazer um método, mostra o valor gravado, marcado como tal. O DCF grava o divisor por ação (`shares`, `shares_factor`) em `inputs`.
- **Aviso de viés de sobrevivência**: faixa fixa, sem botão de fechar, no topo da tela do backtest, mais selo "universo de hoje" ao lado de cada retorno e do gráfico; o texto vem de `backtest_run.warnings` / `universe.survivorship_warning`. Em telas largas a faixa acompanha a rolagem; se a execução não trouxer o texto, a tela usa um texto padrão (a faixa nunca some). A validação aparece marcada como medida uma única vez, com o critério de morte e seus limites, e com a nota de período curto quando passa de menos de 3,5 anos.
- **Somente leitura**: revisão de outliers/eventos e mudança de configuração continuam por comando e Actions (a frase "revisão por comando até a tela existir" da seção 4.1 vale até uma fase própria de escrita).
- **Login**: Auth.js com Google e `ALLOWED_EMAILS`, conferida no login e em todo acesso ao banco no servidor; segredo novo `AUTH_SECRET`.
- **Repositório e deploy**: `web/` na raiz, projeto da Vercel com Root Directory `web`, produção pela branch padrão e preview por PR.

## 10. Regras de qualidade de dados

- Todo indicador exibe fonte, data-base e data de coleta.
- Escala da CVM (`ESCALA_MOEDA`: unidade vs mil) tratada e testada explicitamente.
- Dado ausente aparece como "indisponível", nunca como zero ou valor antigo sem aviso.
- Pelo menos 3 testes comparam valores contra números de balanços publicados, conferidos manualmente pelo usuário. **Feito (03/10/2026)**: lucro atribuído aos controladores em 2024 de WEG (R$ 6.042.593 mil), Itaú (R$ 41.085.000 mil) e BB Seguridade (R$ 8.703.353 mil), conferidos pelo usuário contra os balanços publicados (`pipeline/tests/test_cvm.py::test_lucro_controlador_por_plano_de_contas`).

## 11. Fases

1. Banco (Neon) + coleta CVM e cotações (GitHub Actions)
2. Indicadores, filtro, outliers
3. Preço teto (5 métodos), mediana, votação K, faixas
4. Backtest + critério de morte + validação
5. Tela Next.js + login + filtro + ficha da empresa + simulador
6. Carteira: lançamentos, extrato B3, preço médio, proventos
7. Alocação do aporte + alertas
8. Release em PDF no Google Drive

## 12. A verificar na implementação (não assumir)

- ~~Limite atual de armazenamento do Neon grátis.~~ **Verificado (03/10/2026)**: 1 GB por projeto (até 20 GB somando 100 projetos), 100 CU-hora/projeto, 5 GB de tráfego de saída/projeto. Carga completa 2010–2026 medida: **320 MB** (32% do limite), crescimento ~20 MB/ano; ver `docs/fase1.md`.
- ~~Atraso real entre a entrega à CVM e a disponibilidade nos Dados Abertos~~ **Verificado (03/10/2026)**: DFP/ITR/FCA são atualizados **semanalmente** (página oficial do conjunto de dados; arquivos regerados no domingo 27/09). Atraso de até ~7 dias corridos, mais que 1 dia útil. O cadastro de companhias é diário. **Detecção via RAD/ENET inviável**: desde 06/07/2026 a consulta externa mudou para `/ENETWeb/` e a listagem de documentos exige Google reCAPTCHA; automatizá-la exigiria contornar o CAPTCHA. **Decidido (03/10/2026)**: o usuário aceita o atraso semanal; não há detecção de entrega além dos Dados Abertos.
- Os arquivos de demonstrações trazem só a versão mais recente de cada documento; o índice traz todas as versões com a data de entrega. Versões antigas só existem no banco se coletadas na época. **Decidido**: o backtest usa a data de entrega da versão guardada (seção 8).
- **Fase 2, verificado nos dados reais (Actions, 03-04/10/2026)**: (a) 42% das DFP eram individuais, sem as contas "atribuído aos controladores"; (b) o Banco do Brasil de 2020 em diante mistura DRE comum, balanço e DVA de banco; (c) a quantidade de ações da DFP vem em milhares para parte das empresas; (d) `3.99.01.01/.02` não são sempre ON/PN; (e) a DVA vem zerada para empresas que distribuem (Vale, Gerdau); (f) o FRE existe de 2010 a 2026, mas o layout de 2025+ não traz desdobramentos nem dividendos; (g) o FRE traz a data de APROVAÇÃO do desdobramento, não a de efeito (Itaú: aprovação 27/07/2018, salto de preço 21/11/2018). Detalhes e formatos em `docs/fontes.md` e `docs/fase2.md`.
- **Fase 2, ainda a conferir**: se as ações do FRE incluem tesouraria (o FRE não traz tesouraria; diferença estimada de ~1%); concordância entre FRE e DVA nos exercícios em que ambos existem (relatório do trial); quantos outliers pendentes (433 na primeira medição) e quantos são crescimento legítimo; empresas ativas sem ticker no FCA (CSNA3, BPAC11, KROT3, CMIN3...).
- Cobertura dos releases entregues à CVM para as empresas da lista.
- Regras vigentes de tributação de dividendos (informativo; o sistema usa alíquotas configuráveis).
- Disponibilidade e limites da brapi/Yahoo no plano grátis.

## 13. Suposições feitas sem pergunta explícita (corrigir se discordar)

- Dívida/EBITDA não se aplica a bancos e seguradoras.
- Queda máxima de dividendo por ação: no máximo 3 de 10 anos.
- Gatilho do critério de morte conforme a seção 8.
- Python para coleta e cálculos; TypeScript só na tela e no simulador.
