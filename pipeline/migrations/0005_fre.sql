-- Fase 2 (continuação): FRE como fonte de ações, desdobramentos e proventos; regra de dados
-- desatualizados; eventos societários por empresa.

-- O FRE entra em `filing` como doc_type 'FRE' (CATEG_DOC do índice: FRE, FRE NOVO, FRE WEB).
ALTER TABLE filing DROP CONSTRAINT filing_doc_type_check;
ALTER TABLE filing ADD CONSTRAINT filing_doc_type_check
    CHECK (doc_type IN ('DFP', 'ITR', 'FCA', 'FRE'));

-- Capital social (fre_cia_aberta_capital_social_AAAA.csv). Uma linha por tipo de capital e
-- data de aprovação; o zip traz só a última versão de cada documento.
CREATE TABLE fre_capital (
    filing_id      integer NOT NULL REFERENCES filing(id) ON DELETE CASCADE,
    capital_type   text NOT NULL,   -- Capital Integralizado, Emitido, Subscrito, Autorizado
    approved_on    date,            -- Data_Autorizacao_Aprovacao
    shares_common  bigint,
    shares_pref    bigint,
    shares_total   bigint
);
CREATE INDEX fre_capital_filing_idx ON fre_capital (filing_id);

-- Desdobramento, grupamento e bonificação (fre_cia_aberta_capital_social_desdobramento_AAAA.csv).
-- A data é a de APROVAÇÃO, não a de efeito na negociação. Os FRE de 2025 em diante não trazem
-- este arquivo (layout novo).
CREATE TABLE fre_split (
    filing_id     integer NOT NULL REFERENCES filing(id) ON DELETE CASCADE,
    event_type    text NOT NULL CHECK (event_type IN ('Desdobramento', 'Grupamento', 'Bonificação')),
    approved_on   date,
    total_before  bigint,
    total_after   bigint,
    common_before bigint,
    common_after  bigint,
    pref_before   bigint,
    pref_after    bigint
);
CREATE INDEX fre_split_filing_idx ON fre_split (filing_id);

-- Proventos por exercício, classe e espécie, com data de pagamento
-- (fre_cia_aberta_distribuicao_dividendos_classe_acao_AAAA.csv). Também ausente do layout de 2025+.
CREATE TABLE fre_dividend (
    filing_id      integer NOT NULL REFERENCES filing(id) ON DELETE CASCADE,
    exercise_start date,
    exercise_end   date NOT NULL,
    share_type     text NOT NULL,   -- Ordinária, Preferencial ou vazio
    share_class    text NOT NULL,
    kind           text NOT NULL,   -- Dividendo Obrigatório, Juros Sobre Capital Próprio, Outros...
    amount         numeric(24, 2) NOT NULL,   -- R$ (Montante)
    paid_on        date
);
CREATE INDEX fre_dividend_filing_idx ON fre_dividend (filing_id);

-- Proventos do FRE somados por exercício (rebuilt a cada compute) e usados no lugar da DVA
-- quando existem. Os valores da DVA continuam em jcp/dividends.
ALTER TABLE indicator_annual
    ADD COLUMN fre_jcp            numeric(24, 6),
    ADD COLUMN fre_dividends      numeric(24, 6),
    ADD COLUMN fre_available_from date;   -- data de entrega do documento FRE de onde veio

-- Eventos societários por empresa (FRE + COTAHIST), na data de efeito quando conhecida.
CREATE TABLE company_event (
    cvm_code    integer NOT NULL,
    event_date  date NOT NULL,
    factor      numeric(18, 8) NOT NULL,   -- ações novas / ações antigas
    source      text NOT NULL CHECK (source IN ('fre', 'cotahist', 'manual')),
    date_basis  text NOT NULL,             -- 'cotahist' (salto de preço), 'approval' (data de aprovação)
    known_from  date NOT NULL,             -- a partir de quando o evento é conhecido (ponto no tempo)
    event_type  text,
    note        text,
    shares_before bigint,                  -- contagem de ações antes/depois (só eventos do FRE)
    shares_after  bigint,
    PRIMARY KEY (cvm_code, event_date, source)
);

-- Status novo: dados desatualizados.
ALTER TABLE screen_result DROP CONSTRAINT screen_result_status_check;
ALTER TABLE screen_result ADD CONSTRAINT screen_result_status_check CHECK (status IN
    ('approved', 'rejected', 'insufficient_history', 'insufficient_data', 'excluded', 'stale'));

INSERT INTO app_config (key, value, description) VALUES
 ('screen.max_data_age_days', '730', 'Empresa cuja última DFP tem mais que isto em relação à data-base fica "stale" (dados desatualizados)'),
 ('fre.min_year', '1990', 'Datas do FRE anteriores a este ano são descartadas como inválidas'),
 ('fre.max_future_days', '30', 'Data do FRE posterior à entrega do documento + estes dias é descartada como inválida'),
 ('fre.jcp_kinds', '["Juros Sobre Capital Próprio"]', 'Espécies de provento do FRE somadas como JCP; as demais (inclusive "Outros" e vazio) contam como dividendos'),
 ('shares.max_snapshot_gap_days', '550', 'Distância máxima entre o fim do exercício e a entrega do FRE usado para contar as ações'),
 ('events.match_window_days', '200', 'Evento do FRE (data de aprovação) casa com um salto do COTAHIST até esta quantidade de dias depois'),
 ('events.match_tolerance', '0.08', 'Diferença relativa máxima entre o fator do FRE e o do salto de preço para casarem')
ON CONFLICT DO NOTHING;
