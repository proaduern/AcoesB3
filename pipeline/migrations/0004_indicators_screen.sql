-- Fase 2: indicadores anuais, filtro, outliers de proventos e eventos societários.

-- Contas de proventos na DVA de banco (7.09.04.*) e seguradora (7.11.04.*). A fase 1 só
-- guardava as de empresa comum (7.08.04.*). Conferido nas linhas reais de DFP 2024 (Itaú, BB
-- Seguridade). Para valer nos dados já carregados: acoesb3 cvm --doc DFP --force.
INSERT INTO cvm_account (statement, code, include_children, description, purpose) VALUES
 ('DVA', '7.09.04.01', false, 'Juros sobre o Capital Próprio (banco)', 'proventos, payout'),
 ('DVA', '7.09.04.02', false, 'Dividendos (banco)', 'proventos, payout'),
 ('DVA', '7.11.04.01', false, 'Juros sobre o Capital Próprio (seguradora)', 'proventos, payout'),
 ('DVA', '7.11.04.02', false, 'Dividendos (seguradora)', 'proventos, payout')
ON CONFLICT DO NOTHING;

INSERT INTO app_config (key, value, description) VALUES
 ('screen.snapshot_first_year', '2020', 'Primeiro fim de ano com retrato do filtro (com janela de 10 anos e DFP desde 2010, o critério completo só é avaliável a partir de 2020)'),
 ('screen.excluded_sectors', '[]', 'Setores CVM (ou reclassificados em company_class_override) fora do universo do filtro'),
 ('screen.profit_window_years', '10', 'Janela do critério de lucro positivo (anos)'),
 ('screen.profit_min_positive_years', '8', 'Mínimo de anos com lucro líquido positivo na janela'),
 ('screen.roe_years', '5', 'Anos do ROE médio'),
 ('screen.roe_min', '0.10', 'ROE médio mínimo (exclusivo: precisa ser maior)'),
 ('screen.dividend_window_years', '10', 'Janela do critério de proventos em todos os anos'),
 ('screen.dy_years', '5', 'Anos do DY médio líquido'),
 ('screen.dy_min', '0.05', 'DY médio líquido mínimo (exclusivo)'),
 ('screen.payout_years', '5', 'Anos do payout médio'),
 ('screen.payout_min', '0.25', 'Payout médio mínimo (inclusivo)'),
 ('screen.payout_max', '1.00', 'Payout médio máximo (inclusivo)'),
 ('screen.dps_window_years', '10', 'Janela do critério de queda do dividendo por ação'),
 ('screen.dps_max_drop_years', '3', 'Máximo de quedas do dividendo por ação na janela'),
 ('screen.dps_drop_tolerance', '0', 'Queda só conta se o dividendo por ação cair mais que esta fração (0 = qualquer queda)'),
 ('screen.dps_min_pairs', '6', 'Mínimo de comparações ano a ano disponíveis para avaliar a queda do dividendo por ação'),
 ('tax.jcp', '0.15', 'Alíquota sobre JCP no DY líquido'),
 ('tax.dividend', '0', 'Alíquota sobre dividendos no DY líquido'),
 ('outlier.multiple', '2', 'Provento anual acima de N vezes a mediana é marcado como suspeito'),
 ('outlier.median_years', '5', 'Anos anteriores usados na mediana do outlier'),
 ('outlier.min_history_years', '3', 'Mínimo de anos anteriores com dados para marcar outlier'),
 ('outlier.min_valid_years', '3', 'Mínimo de anos sem outlier para calcular médias de DY e payout'),
 ('liquidity.min_avg_volume', '1000000', 'Volume médio diário mínimo (R$), soma de todas as classes'),
 ('liquidity.min_presence', '0.90', 'Presença mínima nos pregões da janela'),
 ('liquidity.months', '3', 'Janela de liquidez (meses até a data-base)'),
 ('split.candidate_low', '0.85', 'Razão fechamento/fechamento anterior abaixo da qual há candidato a desdobramento'),
 ('split.candidate_high', '1.18', 'Razão acima da qual há candidato a grupamento'),
 ('split.ratio_tolerance', '0.03', 'Distância máxima entre a razão observada e um fator simples'),
 ('split.auto_min_factor', '1.5', 'Fator mínimo (ou inverso) para confirmar evento automaticamente'),
 ('split.max_gap_days', '10', 'Pregões separados por mais dias que isto não são comparados'),
 ('split.simple_factors', '[1.1, 1.2, 1.25, 1.5, 2, 3, 4, 5, 6, 8, 10, 15, 20, 25, 30, 40, 50, 100]', 'Fatores simples de desdobramento/bonificação; o inverso vale para grupamento'),
 ('market.price_lookback_days', '10', 'Dias para trás para achar o último fechamento do exercício')
ON CONFLICT DO NOTHING;

-- Reclassificação manual de setor e do plano de contas (comum/banco/seguradora) por empresa.
CREATE TABLE company_class_override (
    cvm_code integer PRIMARY KEY,
    sector   text,
    plan     text CHECK (plan IN ('comum', 'banco', 'seguradora')),
    note     text,
    set_at   timestamptz NOT NULL DEFAULT now()
);

-- Raiz do ticker (4 letras) -> empresa, para os casos em que o FCA não resolve.
CREATE TABLE ticker_company_override (
    ticker_root text PRIMARY KEY,
    cvm_code    integer NOT NULL,
    note        text,
    set_at      timestamptz NOT NULL DEFAULT now()
);

-- Proventos de um exercício informados à mão ou por outra fonte: substituem a DVA nesse ano.
CREATE TABLE dividend_override (
    cvm_code       integer NOT NULL,
    reference_date date NOT NULL,
    jcp            numeric(24, 6) NOT NULL,
    dividends      numeric(24, 6) NOT NULL,
    source         text NOT NULL,        -- 'manual' ou o nome da outra fonte
    note           text,
    set_at         timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (cvm_code, reference_date)
);

-- Decisão do usuário sobre um provento suspeito. Sem linha = pendente (fica fora do histórico).
CREATE TABLE outlier_review (
    cvm_code       integer NOT NULL,
    reference_date date NOT NULL,
    decision       text NOT NULL CHECK (decision IN ('include', 'exclude')),
    note           text,
    decided_at     timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (cvm_code, reference_date)
);

-- Eventos societários que mudam a base de ações (desdobramento, grupamento, bonificação).
-- factor > 1: mais ações (preço cai); factor < 1: grupamento.
-- status: auto (razão limpa + mudança de DISMES), suspected (precisa de revisão),
--         confirmed / rejected (decisão do usuário). Só auto e confirmed são aplicados.
CREATE TABLE corporate_event (
    id             serial PRIMARY KEY,
    security_id    integer NOT NULL REFERENCES security(id),
    event_date     date NOT NULL,
    factor         numeric(18, 8) NOT NULL,
    observed_ratio numeric(18, 8),          -- fechamento / fechamento anterior
    dismes_changed boolean,
    status         text NOT NULL CHECK (status IN ('auto', 'suspected', 'confirmed', 'rejected')),
    source         text NOT NULL,           -- 'detected' ou 'manual'
    note           text,
    detected_at    timestamptz NOT NULL DEFAULT now(),
    UNIQUE (security_id, event_date)
);

-- Fatos de cada exercício (um por versão de DFP com contas). Nulo = indisponível.
CREATE TABLE indicator_annual (
    filing_id        integer PRIMARY KEY REFERENCES filing(id) ON DELETE CASCADE,
    cvm_code         integer NOT NULL,
    reference_date   date NOT NULL,
    plan             text,                   -- comum, banco, seguradora; nulo = não identificado
    profit           numeric(24, 6),         -- lucro atribuído aos controladores
    equity           numeric(24, 6),         -- PL dos controladores
    jcp              numeric(24, 6),
    dividends        numeric(24, 6),
    dividends_source text,                   -- 'dva' ou a fonte do dividend_override
    lpa_on           numeric(24, 6),         -- R$/ação, como publicado
    lpa_pn           numeric(24, 6),
    shares_on        bigint,                 -- em circulação (sem tesouraria)
    shares_pn        bigint,
    notes            jsonb NOT NULL DEFAULT '{}'::jsonb,
    computed_at      timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX indicator_annual_company_idx ON indicator_annual (cvm_code, reference_date);

-- Proventos anuais suspeitos (> N x mediana). A decisão fica em outlier_review.
CREATE TABLE dividend_outlier (
    cvm_code       integer NOT NULL,
    reference_date date NOT NULL,
    total          numeric(24, 6) NOT NULL,
    median         numeric(24, 6) NOT NULL,
    ratio          numeric(18, 6) NOT NULL,
    years_used     smallint NOT NULL,
    computed_at    timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (cvm_code, reference_date)
);

-- Resultado do filtro por empresa e data-base.
CREATE TABLE screen_result (
    as_of       date NOT NULL,
    cvm_code    integer NOT NULL,
    status      text NOT NULL CHECK (status IN
        ('approved', 'rejected', 'insufficient_history', 'insufficient_data', 'excluded')),
    data_base   date,                -- último exercício usado
    collected_at timestamptz,        -- coleta mais recente entre os arquivos de origem
    computed_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (as_of, cvm_code)
);

CREATE TABLE screen_criterion (
    as_of     date NOT NULL,
    cvm_code  integer NOT NULL,
    criterion text NOT NULL,
    status    text NOT NULL CHECK (status IN ('pass', 'fail', 'unavailable')),
    value     numeric(24, 8),
    threshold text,
    detail    jsonb NOT NULL DEFAULT '{}'::jsonb,
    PRIMARY KEY (as_of, cvm_code, criterion)
);
