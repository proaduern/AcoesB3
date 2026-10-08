-- Fase 4: backtest (seção 8 da especificação).

-- Índices de comparação: Ibovespa e IDIV (B3, fechamento em pontos) e CDI (Banco Central, série 12,
-- taxa diária em % ao dia). Cada linha guarda o arquivo de origem (data de coleta em source_file).
CREATE TABLE benchmark_daily (
    code            text NOT NULL CHECK (code IN ('ibov', 'idiv', 'cdi')),
    ref_date        date NOT NULL,
    value           numeric(24, 8) NOT NULL,
    source_file_id  integer NOT NULL REFERENCES source_file(id),
    PRIMARY KEY (code, ref_date)
);

-- Escolha do cenário a validar: feita pelo usuário com os dados de ajuste, antes de olhar a validação.
CREATE TABLE backtest_freeze (
    id         serial PRIMARY KEY,
    scenario   text NOT NULL,
    cfg_hash   text NOT NULL,          -- parâmetros no momento do congelamento
    config     jsonb NOT NULL,
    note       text,
    frozen_at  timestamptz NOT NULL DEFAULT now()
);

-- Uma execução do backtest. kind 'fit' = período de ajuste (até validation_start - 1);
-- 'validation' = medida única dos últimos anos, com os parâmetros congelados.
CREATE TABLE backtest_run (
    id          serial PRIMARY KEY,
    kind        text NOT NULL CHECK (kind IN ('fit', 'validation')),
    scenario    text NOT NULL,
    freeze_id   integer REFERENCES backtest_freeze(id),
    cfg_hash    text NOT NULL,
    config      jsonb NOT NULL,        -- parâmetros do cenário (backtest.*, ceiling.*, tax.*...)
    start_date  date NOT NULL,
    end_date    date NOT NULL,
    universe    jsonb NOT NULL,        -- empresas do backtest e o aviso de viés de sobrevivência
    metrics     jsonb NOT NULL,
    warnings    jsonb NOT NULL DEFAULT '[]'::jsonb,
    created_at  timestamptz NOT NULL DEFAULT now()
);
-- A validação é medida uma única vez, sem reajuste depois.
CREATE UNIQUE INDEX backtest_one_validation ON backtest_run (kind) WHERE kind = 'validation';
CREATE INDEX backtest_run_scenario_idx ON backtest_run (scenario, created_at);

-- Séries mensais (último pregão do mês) para gráficos: estratégia líquida e bruta, Ibovespa,
-- IDIV e CDI, todos em nível. Os cálculos de métricas usam as séries diárias, na memória.
CREATE TABLE backtest_series (
    run_id    integer NOT NULL REFERENCES backtest_run(id) ON DELETE CASCADE,
    ref_date  date NOT NULL,
    series    text NOT NULL,
    value     numeric(24, 8) NOT NULL,
    PRIMARY KEY (run_id, series, ref_date)
);

CREATE TABLE backtest_trade (
    run_id      integer NOT NULL REFERENCES backtest_run(id) ON DELETE CASCADE,
    seq         integer NOT NULL,
    trade_date  date NOT NULL,
    ticker      text NOT NULL,
    side        text NOT NULL CHECK (side IN ('buy', 'sell')),
    quantity    numeric(24, 6) NOT NULL,
    price       numeric(18, 6) NOT NULL,
    fee         numeric(18, 6) NOT NULL,
    tax         numeric(18, 6) NOT NULL DEFAULT 0,
    note        text,
    PRIMARY KEY (run_id, seq)
);

INSERT INTO app_config (key, value, description) VALUES
 ('benchmark.first_year', '2011', 'Primeiro ano coletado de Ibovespa, IDIV e CDI (um ano antes do início do backtest, para ter nível-base)'),
 ('benchmark.b3_indices', '{"ibov": "IBOVESPA", "idiv": "IDIV"}', 'Nome de cada índice na API de estatísticas da B3'),
 ('benchmark.bcb_cdi_series', '12', 'Série do SGS do Banco Central com o CDI diário (% ao dia)'),
 ('backtest.start_date', '"2012-01-01"', 'Início do backtest (especificação, seção 8)'),
 ('backtest.validation_start', '"2024-01-01"', 'Os dados daqui em diante ficam reservados para a validação (medida uma única vez)'),
 ('backtest.end_date', '"2025-12-31"', 'Fim do backtest: último fim de ano com proventos conhecidos (o FRE 2025+ não traz pagamentos e a DVA de 2026 ainda não existe)'),
 ('backtest.contribution', '1000', 'Aporte mensal padrão (R$); os cenários testam 1000, 1250 e 1500'),
 ('backtest.sell_above_ratio', '1.2', 'Vende a posição inteira quando preço / teto passa disto'),
 ('backtest.max_stocks_per_contribution', '3', 'No máximo N empresas recebem o aporte do mês'),
 ('backtest.stock_cap', '0.10', 'Máximo por empresa (fração da carteira), só vale com posições suficientes (1 / limite)'),
 ('backtest.sector_cap', '0.30', 'Máximo por setor (segmento da lista), só vale com setores suficientes (1 / limite)'),
 ('backtest.brokerage', '0', 'Corretagem (fração do valor da ordem)'),
 ('backtest.b3_fee_schedule', '[["2012-01-01", "0.0003"]]', 'Taxas da B3 sobre o valor de cada ordem, por data de vigência: 0,03% = negociação 0,005% + CCP 0,0224% + TTA 0,0026% (tabela vigente da B3 para ADTV até R$ 3 mi; a tabela de anos anteriores não foi verificada)'),
 ('backtest.cgt_rate', '0.15', 'Imposto sobre o ganho de capital em ações (swing trade)'),
 ('backtest.cgt_monthly_exemption', '20000', 'Vendas de ações no mês até este valor: ganho isento'),
 ('backtest.cgt_offset_losses', 'true', 'Prejuízos acumulados compensam ganhos tributáveis de meses seguintes'),
 ('backtest.cash_earns_cdi', 'true', 'Caixa não investido rende CDI'),
 ('backtest.exec_lag_days', '1', 'Pregões entre o sinal (fechamento do último pregão do mês) e a ordem'),
 ('backtest.dividend_timing', '"fre_dates_else_filing"', 'Data de crédito dos proventos: datas de pagamento do FRE quando existem, senão a data de entrega da DFP; "filing" = sempre a da DFP; "none" = retorno só de preço'),
 ('backtest.price_max_age_days', '10', 'Papel sem pregão há mais que isto não recebe ordem'),
 ('backtest.window_years', '5', 'Janelas móveis do critério de morte (anos), com início todo mês'),
 ('backtest.death_lost_share', '0.5', 'Critério de morte: perder do IDIV em mais que esta fração das janelas...'),
 ('backtest.death_drawdown_pp', '0.10', '...ou ter queda máxima mais que isto (fração) pior que a do IDIV'),
 ('backtest.scenarios', '[{"name": "aporte_1000", "contribution": "1000"}, {"name": "aporte_1250", "contribution": "1250"}, {"name": "aporte_1500", "contribution": "1500"}, {"name": "dy_5", "contribution": "1000", "overrides": {"ceiling.bazin_rate": "0.05"}}, {"name": "dy_7", "contribution": "1000", "overrides": {"ceiling.bazin_rate": "0.07"}}, {"name": "k_estrito", "contribution": "1000", "overrides": {"ceiling.k_by_methods": {"3": 3, "4": 4, "5": 4}}}]', 'Cenários do ajuste: aportes pedidos pelo usuário e variações de DY desejado (Bazin) e de K')
ON CONFLICT DO NOTHING;
