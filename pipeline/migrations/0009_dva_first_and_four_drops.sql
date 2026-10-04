-- Decisões do usuário (04/10/2026):
-- 1) Proventos: a DVA vale em todos os anos e o FRE só cobre DVA ausente ou zerada. Evidência: dos 2.583
--    exercícios com as duas fontes, divergem 35%; nas divergências o payout pela DVA é plausível (40%-64%)
--    e pelo FRE não (173% quando é maior, 31% quando é menor); FRE até 2021 + DVA depois criava quedas falsas.
-- 2) Queda do dividendo por ação: no máximo 4 quedas em 10 anos (antes 3).
UPDATE app_config SET value = '"dva"' WHERE key = 'dividends.preferred_source';
UPDATE app_config SET value = '4' WHERE key = 'screen.dps_max_drop_years';
