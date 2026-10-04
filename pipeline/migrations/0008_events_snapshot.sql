-- Engie (EGIE3): bonificação de 40% em 27/11/2025 (preço caiu para 1/1,4, ações 815,9 mi -> 1.142,3 mi)
-- não era detectada: 1,3 / 1,4 / 1,6 não estavam entre os fatores simples, e o FRE de 2025 em diante não traz
-- o arquivo de desdobramentos. Um salto de preço suspeito vira automático quando a contagem de ações
-- de dois retratos consecutivos do FRE cresce pelo mesmo fator.
UPDATE app_config SET value = '[1.1, 1.2, 1.25, 1.3, 1.4, 1.5, 1.6, 2, 3, 4, 5, 6, 8, 10, 15, 20, 25, 30, 40, 50, 100]'
WHERE key = 'split.simple_factors';

INSERT INTO app_config (key, value, description) VALUES
 ('events.snapshot_tolerance', '0.01', 'Salto de preço suspeito vira automático se a contagem de ações do FRE (retratos consecutivos) cresceu pelo mesmo fator, com esta diferença relativa máxima')
ON CONFLICT DO NOTHING;

-- Fonte preferida dos proventos quando FRE e DVA existem: 'fre' (regra aprovada em 04/10/2026) ou 'dva'
-- (a DVA vale em todos os anos; o FRE só entra se a DVA faltar ou for zero).
INSERT INTO app_config (key, value, description) VALUES
 ('dividends.preferred_source', '"fre"', 'Fonte preferida dos proventos quando FRE e DVA existem: "fre" ou "dva" (o FRE entra se a DVA faltar ou for zero)')
ON CONFLICT DO NOTHING;
