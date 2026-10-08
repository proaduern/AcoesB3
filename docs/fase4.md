# Fase 4 — Backtest (concluída: ajuste, congelamento do dy_5 e validação medida uma vez)

**Estado (08/10/2026)**: estratégia mensal, custos, impostos, índices de comparação, métricas, critério de morte e o fluxo
ajuste → congelamento → validação única. 328 testes (com Postgres), lint limpo. Ajuste rodado no Neon (6 cenários, 2012-01 a 2023-12).
**O usuário escolheu o `dy_5` (Bazin a 5%) e autorizou a medida da validação, feita uma única vez em 08/10/2026 (execução 7).**
O banco não aceita outra: nenhum parâmetro pode mais ser reajustado com base nela.
Regras e decisões: seção 8.1 da especificação. Formatos das fontes: `docs/fontes.md`.

## Como operar

- Comandos (`acoesb3 backtest ...`) e workflow `backtest.yml` (Actions → backtest; passos `benchmarks`, `run`, `report`, `freeze`, `validate`).
  O GitHub só aceita `workflow_dispatch` de workflows que existem na branch padrão: **depois do merge** o `backtest.yml` fica disponível.
  Nesta sessão rodei os mesmos comandos por um workflow temporário na branch (já removido).
- `benchmarks`: Ibovespa e IDIV (B3) e CDI (BCB) para `benchmark_daily` (11.784 linhas em 08/10/2026). Idempotente.
- `run`: ajuste dos cenários de `backtest.scenarios` até `backtest.validation_start - 1`. Grava `backtest_run` (kind `fit`), séries mensais
  (`backtest_series`), ordens (`backtest_trade`) e avisos. Rodar de novo substitui a execução do mesmo cenário e dos mesmos parâmetros.
- `report [--warnings]`: imprime o que está gravado.
- `freeze --scenario NOME [--note ...]`: grava a escolha (e o hash dos parâmetros). Exige ajuste feito com os mesmos parâmetros.
- `validate` (workflow exige digitar SIM): roda o cenário congelado até `backtest.end_date` e mede a validação. Recusa se os parâmetros
  mudaram depois do congelamento. O banco só aceita **uma** validação (índice único `backtest_one_validation`); depois dela, `freeze` também recusa.
- Parâmetros: tudo em `app_config` (`backtest.*`, `benchmark.*`, `tax.*`, `ceiling.*`); cenários em `backtest.scenarios`.
- Código: `backtest.py` (alocação, impostos, simulação, proventos; puro), `performance.py` (cota, janelas, queda máxima, critério de morte; puro),
  `benchmarks.py` (parsers B3/BCB; puro), `backtest_run.py` (banco, sinais no ponto no tempo, execução, gravação), migração 0015.

## Resultado do ajuste (2012-01 a 2023-12, retorno ponderado no tempo, líquido de custos e impostos)

| Cenário | Retorno a.a. | Bruto a.a. | Queda máx. | Janelas perdidas p/ IDIV | Morte |
|---|---|---|---|---|---|
| aporte_1000 / 1250 / 1500 | 14,4% | 15,0% | 46,6% | 3 de 83 (3,6%) | não |
| dy_5 (Bazin a 5%) | 14,2% | 14,6% | **33,1%** | 6 de 83 (7,2%) | não |
| dy_7 (Bazin a 7%) | 12,2% | 13,0% | 45,1% | 30 de 83 (36,1%) | não |
| k_estrito (K+1) | 11,4% | 12,1% | 44,7% | 36 de 83 (43,4%) | não |
| Referências | IDIV 9,9% (queda 57,3%) · Ibovespa 7,4% (46,8%) · CDI 9,1% | | | | |

Leituras e cuidados (não são recomendação):
- **O tamanho do aporte não muda o retorno ponderado no tempo** (14,4% nos três); ele só muda valores em reais e o imposto (aporte_1500: aportes de
  R$ 214,5 mil viraram R$ 636,7 mil líquidos, com R$ 13,3 mil de imposto e R$ 105 mil de proventos recebidos).
- **O resultado é favorecido pelo universo**: a lista acompanhada é a de hoje (carteira e radar escolhidos com o que se sabe agora). O aviso de viés de sobrevivência
  que o usuário pediu está em `backtest_run.warnings` e `universe.survivorship_warning`, para a tela da fase 5. Não dá para separar quanto dos +4,5 p.p. sobre o IDIV é método e quanto é seleção.
- **Os primeiros 3 anos e meio são caixa**: a 1ª compra é em 2015-03/04 (56 meses sem compra no cenário base). Antes, o preço teto não tinha 3 métodos válidos
  (Bazin e Gordon pedem 5 exercícios e a DFP estruturada começa em 2010). O caixa rende CDI, mas a janela de 2012–2015 puxa o retorno anual para baixo e deixa as primeiras janelas de 5 anos pouco representativas.
- 11 exercícios ficaram sem proventos utilizáveis (sem dado ou sem ações do FRE): o retorno total é um pouco subestimado.
- O Ibovespa e o IDIV são séries de pontos da B3; só o IDIV está confirmado como índice de retorno total (ver `fontes.md`).
- Nenhum cenário aciona o critério de morte no ajuste. A regra de queda máxima está folgada porque a estratégia (46,6%) cai menos que o IDIV (57,3%).

## Resultado da validação (2024-01-01 a 2025-12-31, `dy_5` congelado, medida única)

| Série | Retorno no período | a.a. | Queda máx. |
|---|---|---|---|
| Estratégia líquida | 33,2% | 15,4% | 14,7% |
| Estratégia bruta (sem custos e impostos) | 34,8% | 16,0% | 14,7% |
| IDIV | 26,6% | 12,5% | 10,6% |
| CDI | 26,8% | 12,5% | 0% |
| Ibovespa | 20,1% | 9,5% | 13,7% |

- **Critério de morte: não acionado.** A estratégia perde do IDIV em 2 de 24 janelas de 5 anos que terminam no período (8,3%, limite 50%) e a queda máxima é 4,1 p.p. pior que a do IDIV (limite 10 p.p.).
- Cuidados na leitura: são só 2 anos e as 24 janelas se sobrepõem quase por inteiro; o ajuste tinha mostrado 14,2% a.a. e queda de 33,1%, e a validação manteve o retorno acima do IDIV e do CDI, mas com a queda máxima maior que a do IDIV (no ajuste era menor). O viés de sobrevivência continua valendo (lista acompanhada de hoje), os proventos de 2026 estão fora (período termina em 2025-12-31) e a carteira recebeu R$ 131,5 mil de proventos em todo o período.
- Em todo o período (2012–2025) foram R$ 167 mil de aportes, valor final líquido de R$ 589,7 mil, R$ 10,7 mil de imposto e R$ 389 de taxas da B3.
- Para reproduzir: `acoesb3 backtest report --warnings` (execução 7, tipo `validation`).

## O que o usuário ainda precisa decidir

1. ~~Cenário a congelar~~ e ~~medida da validação~~: feitos em 08/10/2026 (`dy_5`).
2. **Período de validação**: cobre 2024-01-01 a 2025-12-31 (cerca de 2 anos, não 3), pela decisão 4 abaixo.
3. **Retorno total (resposta 4)**: o COTAHIST não traz ajuste por proventos, então adotei a DVA/FRE com datas do FRE (até o exercício 2021) e a data de entrega da DFP
   nos demais (`backtest.dividend_timing`). Confirmar ou pedir outra regra (por exemplo, repartir o total do exercício ao longo do ano seguinte).
4. **Fim do período**: `backtest.end_date = 2025-12-31`, porque o FRE de 2025 em diante não traz pagamentos e a DVA de 2026 ainda não existe; medir 2026 penalizaria a estratégia
   (índices recebem os proventos, a carteira não). Se preferir os 3 anos inteiros, é preciso lançar à mão os proventos de 2026 (`review dividend`) ou aceitar o viés.
5. **Taxas da B3 antes de 2025**: usei 0,03% (tabela vigente, v3.0 do documento oficial) em todo o período. Se tiver a tabela histórica, ela entra em `backtest.b3_fee_schedule`
   por data de vigência; o efeito esperado é pequeno (as taxas pagas no cenário base somaram R$ 365 em 12 anos).
6. **Imposto**: as regras (15%, isenção de R$ 20 mil/mês, compensação) vêm de portais que citam a Lei 11.033/2004; o site da Receita não abriu desta sessão. Conferir.

## O que ficou de fora, e por quê

| Item | Motivo |
|---|---|
| Empresas canceladas no backtest | Decisão do usuário (viés aceito): preço teto e DFC detalhado só existem para a lista acompanhada |
| Aviso de viés na tela | A tela é a fase 5; o aviso está gravado em `backtest_run` (warnings e universe) |
| Gráfico e tela do backtest | Fase 5; as séries mensais de estratégia, índices e CDI já estão em `backtest_series` |
| Taxas da B3 anteriores a 2025 | O documento oficial traz só a tabela vigente |
| IRRF "dedo-duro" (0,005% sobre vendas) e retenção de 10% sobre dividendos acima de R$ 50 mil/mês | Efeito desprezível neste porte; o dedo-duro é compensável |
| Composição das units no passado | Usa a do FCA mais recente (as units da lista não mudaram de composição nos dados verificados) |
| Proventos de 2026 | Sem fonte estruturada ainda (ver decisão 4) |
| Teste de paridade com o simulador em TypeScript | O simulador é da fase 5; a lógica de preço teto continua em `ceiling.py` |
| Variações de DY/K além de 5%/7% e K+1 | Os cenários são configuráveis (`backtest.scenarios`); só rodei os pedidos pelo usuário e essas três variações da especificação |
