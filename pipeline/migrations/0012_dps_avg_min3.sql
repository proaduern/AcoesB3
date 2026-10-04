-- Decisão do usuário (04/10/2026): mínimo de 3 comparações da média móvel (antes 4). Um ano de outlier sem
-- decisão derruba até 4 das 7 comparações; com 4 como mínimo, Itaú e CPFL ficavam com dado insuficiente.
UPDATE app_config SET value = '3' WHERE key = 'screen.dps_avg_min_comparisons';
