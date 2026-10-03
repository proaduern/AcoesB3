-- Fase 1: cadastro de empresas, documentos CVM, contas das demonstrações e cotações B3.

-- Empresa (cadastro CVM). Inclui canceladas: o backtest não pode ter viés de sobrevivência.
CREATE TABLE company (
    cvm_code        integer PRIMARY KEY,
    cnpj            text NOT NULL,
    name            text NOT NULL,
    trade_name      text,
    cvm_sector      text,          -- setor de atividade declarado à CVM (não é a classificação B3)
    status          text,          -- situação do registro na CVM (ATIVO, CANCELADA...)
    status_since    date,
    registered_at   date,
    canceled_at     date,
    cancel_reason   text,
    category        text,          -- Categoria A/B
    source          text NOT NULL, -- 'cvm_cad' ou 'cvm_fca'
    updated_at      timestamptz NOT NULL DEFAULT now()
);

-- Documento entregue à CVM (DFP, ITR, FCA). Uma linha por versão: o índice da CVM
-- traz todas as versões com a data de entrega de cada uma.
CREATE TABLE filing (
    id              serial PRIMARY KEY,
    doc_type        text NOT NULL CHECK (doc_type IN ('DFP', 'ITR', 'FCA')),
    cvm_code        integer NOT NULL,
    cnpj            text NOT NULL,
    reference_date  date NOT NULL,       -- data-base do documento
    version         smallint NOT NULL,
    doc_id          integer NOT NULL,    -- ID_DOC / NumeroSequencialDocumento no RAD/ENET
    received_date   date NOT NULL,       -- data de entrega à CVM (ponto no tempo do backtest)
    link            text,
    source_file_id  integer NOT NULL REFERENCES source_file(id),
    has_lines       boolean NOT NULL DEFAULT false, -- true quando as contas desta versão foram gravadas
    UNIQUE (doc_type, cvm_code, reference_date, version)
);
CREATE INDEX filing_company_idx ON filing (cvm_code, doc_type, reference_date);

-- Contas guardadas (regra da especificação: só as usadas nos cálculos).
-- Editável: incluir uma conta aqui e rodar a carga novamente.
-- Os códigos mudam de sentido conforme o plano de contas (empresa comum, banco,
-- seguradora): por isso a lista cobre os três planos e a descrição diz qual é qual.
CREATE TABLE cvm_account (
    statement        text NOT NULL,   -- BPA, BPP, DRE, DFC_MI, DFC_MD, DVA
    code             text NOT NULL,   -- CD_CONTA
    include_children boolean NOT NULL DEFAULT false,
    description      text NOT NULL,
    purpose          text NOT NULL,   -- para que cálculo a conta é guardada
    PRIMARY KEY (statement, code)
);

INSERT INTO cvm_account (statement, code, include_children, description, purpose) VALUES
 ('BPA', '1',          false, 'Ativo Total', 'ROA, conferência'),
 ('BPA', '1.01',       false, 'Ativo Circulante (comum) / Caixa e Equivalentes (banco)', 'dívida líquida'),
 ('BPA', '1.01.01',    false, 'Caixa e Equivalentes de Caixa (comum, seguradora)', 'dívida líquida'),
 ('BPA', '1.01.02',    false, 'Aplicações Financeiras (comum, seguradora)', 'dívida líquida'),
 ('BPP', '2.01.04',    false, 'Empréstimos e Financiamentos CP (comum)', 'dívida líquida'),
 ('BPP', '2.02.01',    false, 'Empréstimos e Financiamentos LP (comum)', 'dívida líquida'),
 ('BPP', '2.03',       false, 'Patrimônio Líquido Consolidado (comum, seguradora) / Passivos ao custo amortizado (banco)', 'ROE, VPA'),
 ('BPP', '2.03.09',    false, 'Participação dos Não Controladores (comum, seguradora)', 'ROE, VPA'),
 ('BPP', '2.08',       true,  'Patrimônio Líquido Consolidado e subcontas (banco)', 'ROE, VPA'),
 ('DRE', '3.01',       false, 'Receita (comum) / Receitas da Intermediação Financeira (banco)', 'crescimento, margem'),
 ('DRE', '3.05',       false, 'EBIT (comum)', 'dívida líquida/EBITDA'),
 ('DRE', '3.09',       true,  'Lucro Consolidado (banco) e atribuição', 'lucro, ROE, payout'),
 ('DRE', '3.11',       true,  'Lucro Consolidado (comum) e atribuição', 'lucro, ROE, payout'),
 ('DRE', '3.13',       true,  'Lucro Consolidado (seguradora) e atribuição', 'lucro, ROE, payout'),
 ('DRE', '3.99.01',    true,  'Lucro Básico por Ação, por classe (R$/ação)', 'LPA, Graham, múltiplos'),
 ('DFC_MI', '6.01',    false, 'Caixa Líquido das Atividades Operacionais', 'FCFE'),
 ('DFC_MD', '6.01',    false, 'Caixa Líquido das Atividades Operacionais', 'FCFE'),
 ('DVA', '7.04.01',    false, 'Depreciação, Amortização e Exaustão (comum)', 'EBITDA'),
 ('DVA', '7.08.04.01', false, 'Juros sobre o Capital Próprio', 'proventos, payout'),
 ('DVA', '7.08.04.02', false, 'Dividendos', 'proventos, payout');

-- Valores das contas, já convertidos para reais (ESCALA_MOEDA aplicada).
CREATE TABLE financial_line (
    filing_id      integer NOT NULL REFERENCES filing(id) ON DELETE CASCADE,
    statement      text NOT NULL,
    consolidated   boolean NOT NULL,
    account_code   text NOT NULL,
    period_start   date,            -- nulo em balanço patrimonial (posição na data)
    period_end     date NOT NULL,
    value          numeric(24, 6) NOT NULL,
    source_scale   text NOT NULL    -- ESCALA_MOEDA original ('MIL' ou 'UNIDADE')
);
CREATE UNIQUE INDEX financial_line_uq ON financial_line
    (filing_id, statement, account_code, period_end, coalesce(period_start, '0001-01-01'::date));

-- Ações por empresa (FCA, seção valor mobiliário). Mapeia ticker -> empresa.
CREATE TABLE company_security (
    id              serial PRIMARY KEY,
    cvm_code        integer NOT NULL,
    ticker          text,            -- vazio nos FCA antigos (ex.: 2010)
    security_type   text NOT NULL,   -- 'Ações Ordinárias', 'Units'...
    preferred_class text,
    unit_composition text,
    market          text,
    segment         text,            -- segmento de listagem (Novo Mercado, N1...)
    trading_start   date,
    trading_end     date,
    filing_id       integer NOT NULL REFERENCES filing(id) ON DELETE CASCADE
);
CREATE INDEX company_security_filing_idx ON company_security (filing_id);
CREATE INDEX company_security_ticker_idx ON company_security (ticker);

-- Quantidade de ações (composicao_capital do DFP/ITR), para VPA e LPA.
CREATE TABLE share_count (
    filing_id           integer PRIMARY KEY REFERENCES filing(id) ON DELETE CASCADE,
    common              bigint NOT NULL,
    preferred           bigint NOT NULL,
    total               bigint NOT NULL,
    treasury_common     bigint NOT NULL,
    treasury_preferred  bigint NOT NULL,
    treasury_total      bigint NOT NULL
);

-- Papel negociado conforme o COTAHIST. Ticker pode ser reaproveitado, por isso (ticker, isin).
CREATE TABLE security (
    id          serial PRIMARY KEY,
    ticker      text NOT NULL,
    isin        text NOT NULL,
    especi      text NOT NULL,   -- especificação mais recente: 'ON NM', 'PN N1', 'UNT N2'...
    short_name  text NOT NULL,
    first_date  date NOT NULL,
    last_date   date NOT NULL,
    UNIQUE (ticker, isin)
);

-- Cotação diária sem ajuste (COTAHIST). Preços por ação (FATCOT já aplicado).
-- Ajustes por desdobramento e proventos ficam para a fase 2.
CREATE TABLE quote_daily (
    security_id     integer NOT NULL REFERENCES security(id),
    trade_date      date NOT NULL,
    open            numeric(18, 6) NOT NULL,
    high            numeric(18, 6) NOT NULL,
    low             numeric(18, 6) NOT NULL,
    avg             numeric(18, 6) NOT NULL,
    close           numeric(18, 6) NOT NULL,
    trades          integer NOT NULL,
    quantity        bigint NOT NULL,
    volume          numeric(20, 2) NOT NULL,
    distribution    smallint NOT NULL,  -- DISMES: muda a cada evento societário/provento
    source_file_id  integer NOT NULL REFERENCES source_file(id),
    PRIMARY KEY (security_id, trade_date)
);

INSERT INTO app_config (key, value, description) VALUES
 ('cvm.per_share_prefixes', '["3.99"]', 'Contas de valor por ação: não recebem ESCALA_MOEDA (já vêm em R$/ação)');
