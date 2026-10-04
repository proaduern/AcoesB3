-- Decisão do usuário (04/10/2026): a queda do dividendo por ação passa a ser medida pela média móvel de 3 anos
-- (média do DPS dos 3 anos até k contra a média móvel do ano anterior) em vez de ano contra ano. O ano contra ano
-- fica no detalhe do critério, só informativo. Numa janela de 10 anos há até 7 comparações (2019 a 2025).
INSERT INTO app_config (key, value, description) VALUES
 ('screen.dps_method', '"avg"', 'Método da queda do DPS: "avg" (média móvel de screen.dps_alt_avg_years anos) ou "yearly" (ano contra ano)'),
 ('screen.dps_avg_min_comparisons', '4', 'Mínimo de comparações da média móvel disponíveis para avaliar a queda do DPS')
ON CONFLICT DO NOTHING;
