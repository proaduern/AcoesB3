# Fase 4 — Backtest (roteiro para a próxima sessão)

Escopo: seção 8 da especificação (ponto no tempo, 2012 em diante, 3 últimos anos de validação, comparação com Ibovespa/IDIV/CDI,
critério de morte). Leia, nesta ordem: `CLAUDE.md`, `docs/ESPECIFICACAO.md` (seções 2, 3, 5, 8, 12), `docs/fase3.md`, este arquivo.

## O que já existe

- `ceiling.py`/`compute.build_ceilings(conn, cfg, as_of)`: preço teto numa data, só com DFP entregues até ela e fechamento até ela.
- `compute._load_years_context` e `_years_at`: exercícios de qualquer empresa em qualquer data (ponto no tempo), ações e eventos incluídos.
- `quote_daily` (COTAHIST **não ajustado**), `company_event` (desdobramentos), `filing_available` (data de entrega da versão guardada).
- Não existe: série ajustada por eventos, série de retorno total (proventos), Ibovespa, IDIV, CDI.

## Perguntas a fazer ao usuário ANTES de codar

1. **Universo do backtest**: a especificação pede empresas canceladas (sem viés de sobrevivência), mas o preço teto só vale para a lista
   acompanhada (decisão de 04/10) e o DFC detalhado só está guardado para ela. Backtest só na lista atual tem viés de sobrevivência.
   Aceitar? Ou ampliar o cálculo (e o DFC) à B3 inteira para o backtest (custo: espaço no Neon, hoje 431 MB)?
2. **Regra da estratégia**: comprar quando `buy` (preço < teto e K métodos)? Vender na faixa "cara" (> 120%)? Periodicidade da decisão
   (mensal?), pesos, aporte mensal fixo, custos de transação e impostos?
3. **Fontes de Ibovespa, IDIV e CDI**: verificar a fonte real e o formato antes de codar (regra: não inventar endpoint); CDI provavelmente
   pela API do Banco Central, índices pela B3. Sem acesso direto daqui: sondar pelo Actions.
4. **Retorno total**: proventos reinvestidos a partir de `indicator_annual`/FRE (com datas de pagamento) ou da série do COTAHIST
   (campo de ajuste)? O FRE 2025+ não traz pagamentos por data.
5. **DCF e histórico**: o DFC detalhado só começa na carga de 2010 para a lista; em datas antigas os métodos ficam indisponíveis — aceitar
   K menor ou exigir os 5 métodos?
6. **Critério de morte** (seção 8): janelas móveis de 5 anos contra o IDIV — janela de início mensal ou anual?
7. Os 3 últimos anos reservados à validação: congelar parâmetros no ajuste (2012–2023) e medir uma única vez.
