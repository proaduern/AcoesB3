-- Teste da média móvel para a queda do dividendo por ação (04/10/2026): o critério continua ano contra
-- ano; o detalhe do critério passa a trazer também as quedas pelo método alternativo, só para comparação.
INSERT INTO app_config (key, value, description) VALUES
 ('screen.dps_alt_avg_years', '3', 'Método alternativo (informativo) da queda do DPS: média dos N últimos anos contra a dos N anteriores')
ON CONFLICT DO NOTHING;
