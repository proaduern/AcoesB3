-- Lista de empresas acompanhadas (decisão de 04/10/2026): carteira do usuário e radar.
-- O cálculo do filtro continua em toda a B3 (o backtest precisa de empresas canceladas);
-- revisão manual, preço teto, DCF, alertas e releases valem só para esta lista.
CREATE TABLE watchlist (
    cvm_code integer PRIMARY KEY REFERENCES company(cvm_code),
    role     text NOT NULL CHECK (role IN ('carteira', 'radar')),
    segment  text NOT NULL,
    note     text,
    added_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO app_config (key, value, description) VALUES
 ('watch.segments', '{"bancos": ["banc"], "seguradoras": ["segur"], "energia": ["energia"], "saneamento": ["saneamento"], "telecom": ["telecom"]}', 'Segmentos do radar: trechos do setor CVM (sem acento, minúsculas) que classificam a empresa no segmento')
ON CONFLICT DO NOTHING;
