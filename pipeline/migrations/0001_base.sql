-- Base: configuração, controle de arquivos baixados e execuções de coleta.

-- Todo parâmetro numérico do sistema mora aqui (regra: nada fixo no código).
CREATE TABLE app_config (
    key         text PRIMARY KEY,
    value       jsonb NOT NULL,
    description text NOT NULL,
    updated_at  timestamptz NOT NULL DEFAULT now()
);

-- Um registro por arquivo de origem baixado (zip da CVM, COTAHIST...).
-- Permite pular arquivos sem mudança e auditar de onde veio cada número.
CREATE TABLE source_file (
    id             serial PRIMARY KEY,
    source         text NOT NULL,          -- 'cvm_dfp', 'cvm_itr', 'cvm_fca', 'cvm_cad', 'b3_cotahist'
    url            text NOT NULL UNIQUE,
    last_modified  text,                   -- cabeçalho HTTP Last-Modified, como veio
    sha256         text NOT NULL,
    size_bytes     bigint NOT NULL,
    collected_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE collection_run (
    id           serial PRIMARY KEY,
    job          text NOT NULL,
    started_at   timestamptz NOT NULL DEFAULT now(),
    finished_at  timestamptz,
    status       text NOT NULL DEFAULT 'running' CHECK (status IN ('running', 'ok', 'failed')),
    detail       jsonb
);

-- Parâmetros da fase 1 (coleta). Fases seguintes acrescentam os seus.
INSERT INTO app_config (key, value, description) VALUES
 ('cvm.first_year', '2010', 'Primeiro ano de DFP/ITR/FCA coletado (dados estruturados da CVM começam ~2010)'),
 ('cotahist.first_year', '2010', 'Primeiro ano de cotações COTAHIST coletado'),
 ('cotahist.codbdi', '["02"]', 'Códigos BDI guardados (02 = lote padrão de ações)'),
 ('cotahist.market_types', '["010"]', 'Tipos de mercado guardados (010 = à vista)'),
 ('cotahist.isin_types', '["ACN", "UNT", "CDA"]', 'Tipo de ativo no ISIN (posições 7-9): ACN = ação, UNT/CDA = unit. Exclui BDR, que em 2020-2022 veio com CODBDI 02'),
 ('cvm.statement_scope', '"con_else_ind"', 'Demonstração usada: consolidada; individual só se a empresa não entregar consolidada'),
 ('collect.daily_lookback_days', '10', 'Dias úteis para trás que a coleta diária de cotações reprocessa');
