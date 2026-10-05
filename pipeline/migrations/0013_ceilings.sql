-- Fase 3: preço teto (seção 5 da especificação), só para a lista acompanhada.

-- Um método de preço teto por empresa e data-base. value = R$ por ação na base de ações de as_of
-- (o mesmo valor vale para todas as classes; a unit soma as ações da composição).
CREATE TABLE ceiling_method (
    as_of        date NOT NULL,           -- data do cálculo: só vale o que se conhecia nela
    cvm_code     integer NOT NULL,
    method       text NOT NULL CHECK (method IN ('bazin', 'graham', 'gordon', 'multiples', 'dcf')),
    status       text NOT NULL CHECK (status IN ('ok', 'excluded', 'unavailable')),
    value        numeric(24, 8),          -- nulo quando não é 'ok'
    reason       text,                    -- motivo de excluded/unavailable
    inputs       jsonb NOT NULL DEFAULT '{}'::jsonb,
    source       text NOT NULL,           -- de onde vêm os números
    data_base    date,                    -- último exercício usado
    collected_at timestamptz,             -- coleta mais recente entre os arquivos de origem
    computed_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (as_of, cvm_code, method)
);

-- Consolidação por empresa: mediana dos métodos aplicáveis e votos exigidos (K).
CREATE TABLE ceiling_result (
    as_of        date NOT NULL,
    cvm_code     integer NOT NULL,
    status       text NOT NULL CHECK (status IN ('ok', 'insufficient')),  -- insufficient: menos métodos que o mínimo
    methods_ok   smallint NOT NULL,
    k_required   smallint,
    ceiling      numeric(24, 8),          -- mediana por ação; nulo se nenhum método aplicável
    plan         text,
    data_base    date,
    collected_at timestamptz,
    computed_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (as_of, cvm_code)
);

-- Situação por papel (ON, PN, unit): preço de fechamento, teto, faixa e votação.
CREATE TABLE ceiling_class (
    as_of        date NOT NULL,
    cvm_code     integer NOT NULL,
    ticker       text NOT NULL,
    kind         text NOT NULL CHECK (kind IN ('on', 'pn', 'unit')),
    multiplier   smallint,                -- ações por papel (unit: soma da composição)
    price        numeric(18, 6) NOT NULL,
    price_date   date NOT NULL,           -- fechamento COTAHIST usado
    ceiling      numeric(24, 8),
    ratio        numeric(18, 8),          -- preço / teto
    band         text CHECK (band IN ('strong_buy', 'buy', 'hold', 'expensive')),
    votes        smallint,                -- métodos com teto acima do preço
    k_required   smallint,
    buy          boolean NOT NULL DEFAULT false,
    reason       text,                    -- por que não há teto para este papel (unit sem composição...)
    computed_at  timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (as_of, cvm_code, ticker)
);

INSERT INTO app_config (key, value, description) VALUES
 ('ceiling.bazin_rate', '0.06', 'Bazin: taxa que divide o dividendo médio líquido por ação'),
 ('ceiling.dividend_years', '5', 'Exercícios do dividendo médio líquido (Bazin e Gordon); ano de outlier fica fora da média'),
 ('ceiling.graham_multiplier', '22.5', 'Graham: constante dentro da raiz (22,5 x LPA x VPA)'),
 ('ceiling.lpa_years', '3', 'Exercícios do LPA médio (Graham e múltiplos)'),
 ('ceiling.gordon_k', '0.12', 'Gordon: retorno exigido k (nominal)'),
 ('ceiling.gordon_growth_years', '5', 'Gordon: exercícios da janela do crescimento histórico do dividendo total (crescimento composto entre a primeira e a última ponta)'),
 ('ceiling.gordon_g_min', '0', 'Gordon: crescimento g mínimo'),
 ('ceiling.gordon_g_max', '0.05', 'Gordon: crescimento g máximo'),
 ('ceiling.gordon_min_spread', '0.03', 'Gordon: k - g abaixo disto exclui o método'),
 ('ceiling.multiple_years', '10', 'Múltiplos: janela do P/L e do P/VP mediano (exercícios)'),
 ('ceiling.multiple_min_years', '3', 'Múltiplos: mínimo de exercícios válidos na janela (empresa com menos de 10 anos usa o que existe)'),
 ('ceiling.k_by_methods', '{"3": 2, "4": 3, "5": 3}', 'Votos K exigidos para "Compra", por quantidade de métodos aplicáveis; menos que o menor valor = dados insuficientes'),
 ('ceiling.band_strong', '0.8', 'Faixas (preço / teto): abaixo disto = compra forte'),
 ('ceiling.band_buy', '1.0', 'Faixas: abaixo disto (e a partir do anterior) = compra'),
 ('ceiling.band_hold', '1.2', 'Faixas: até aqui (inclusive) = manter; acima = cara, avaliar venda'),
 ('ceiling.price_max_age_days', '10', 'Fechamento do COTAHIST mais velho que isto (em relação a as_of) não vale como preço atual'),
 ('ceiling.financial_plans', '["banco", "seguradora"]', 'Planos sem Graham e sem DCF; múltiplos usam P/VP')
ON CONFLICT DO NOTHING;
