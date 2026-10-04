# Fase 2 — Indicadores, filtro e outliers

**Estado (04/10/2026)**: código e testes prontos (147 testes, lint limpo); PR #3 já mergeado com a primeira
versão. Esta segunda leva corrige o que a primeira medição com dados reais mostrou e adota o FRE. A medição
roda num Postgres descartável do Actions (workflow temporário `phase2-trial`); **ainda não rodou no Neon**.

## O que a primeira medição com dados reais mostrou

Rodada de 03-04/10/2026: carga completa (cadastro, FCA, DFP, COTAHIST) + `compute` num Postgres descartável.

| Achado | Causa | O que mudou |
|---|---|---|
| 42% das DFP sem plano de contas (lucro indisponível) | 962 de 986 eram DFP **individuais**, sem as contas "atribuído aos controladores" | Contas resolvidas por presença e por escopo (`indicators.py`) |
| Banco do Brasil 2020+ lido como empresa comum, sem PL nem proventos | DRE no padrão comum, balanço e DVA no padrão de banco | Mesma mudança: cada conceito olha o que existe no documento |
| Ambev aprovada com DY de 4.570% | Ações da DFP em **milhares** para Ambev, Vale e Itaú (sem coluna de escala) | Ações vêm do FRE; DFP não é mais usada para isso |
| `3.99.01.01/.02` nem sempre ON/PN | 8 empresas com PN em `.01`, 18 com ON em `.02` (2024) | Payout × LPA removido; dividendo por ação = total ÷ ações |
| Vale, Gerdau e outras com proventos zero em todos os anos | DVA zerada | FRE passa a ser a fonte preferida dos proventos |
| B3SA3, BPAC11, CSNA3... sem empresa | Raiz com dígito (B3SA); FCA sem ticker para as demais | Raiz com dígito aceita; os demais exigem `review ticker` |
| Empresas canceladas há anos no retrato de hoje | Nenhuma regra de atualidade | Regra de 2 anos (`stale`) |
| 433 outliers, todos pendentes | Regra da especificação (2× a mediana dos 5 anos anteriores) | Sem mudança: precisa de revisão (Itaú, Petrobras e WEG ficam indisponíveis por isso) |

## Entregue

- `migrations/0004_indicators_screen.sql` e `0005_fre.sql`: parâmetros, contas de DVA de banco e seguradora,
  tabelas de revisão e de resultado, tabelas do FRE, eventos por empresa e status `stale`.
- `indicators.py`: lucro, PL e proventos conta a conta (escopo consolidado/individual, planos misturados).
- `fre.py` + `load.load_fre_year` (`acoesb3 cvm --doc FRE`): índice, capital social, desdobramentos e proventos
  por classe, com os formatos verificados (`docs/fontes.md`). Layout novo (2025+) sem dividendos/desdobramentos é
  registrado como "arquivo ausente", não como erro.
- `shares.py`: ações em uma data a partir dos retratos do FRE, ajustadas por eventos, comparando a contagem do
  retrato com o antes/depois do evento.
- `corporate.py`: detecção de eventos no COTAHIST e fusão com o FRE (fator oficial + data de efeito).
- `screen.py`: critérios, outliers, status (inclui `stale`).
- `compute.py`: fatos anuais, outliers, eventos (por papel e por empresa) e retratos por data.
- `review.py` / `acoesb3 review`: revisão manual (outliers, eventos, proventos, setor, plano, ticker).
- Workflows: `compute` (manual), `phase2-trial` e `fre-probe` (temporários).
- Testes: parsers com linhas reais, extração com as linhas reais de WEG, Itaú e BB Seguridade, lógica pura,
  e integração no Postgres (ponto no tempo, outliers, eventos, FRE × DVA, liquidez, setor, `stale`).
  Mutações em precedência do FRE, ajuste de retrato e regra de 2 anos derrubam testes.

## Como rodar no Neon

1. Merge na branch padrão.
2. Actions → `compute` com `reload_dfp` e `load_fre` marcados na primeira vez (recarga das DFP grava as contas
   de DVA de banco/seguradora; o FRE traz ações, eventos e proventos). Ou, antes disso, o job `neon` do
   `phase2-trial` (commit com o marcador de execução no Neon), que faz o mesmo e imprime o relatório.
3. Revisar: `acoesb3 review list`; decidir com `review outlier` e `review event`; rodar `compute` de novo.
4. Informar `screen.excluded_sectors` e, se preciso, `review class`/`review ticker`.

## Ficou de fora, e por quê

| Item | Motivo |
|---|---|
| Validação no Neon | Aguarda a revisão do resultado da medição no Postgres descartável |
| Lista de segmentos excluídos | O usuário ainda não informou; `screen.excluded_sectors` está vazio |
| Proventos dos exercícios mais recentes pelo FRE | O layout 2025+ não traz o arquivo; ficam com a DVA ou o valor manual |
| Tesouraria nas ações | O FRE não traz; diferença estimada de ~1% |
| Retratos antes de 2020 | A janela de 10 anos só fecha em 2020 (`screen.snapshot_first_year`); a fase 4 precisa de janelas menores configuradas |
| Mapeamento de tickers sem FCA (CSNA3, BPAC11, KROT3...) | Sem fonte oficial verificada; `review ticker` por enquanto |
| Classificação setorial B3 | Setor da CVM + reclassificação manual (decisão do usuário) |
| Encadear `compute` no `collect-daily` | Evita alerta diário enquanto o cálculo não foi validado |

## Limitações conhecidas

- "Pago" é "declarado no exercício" (DVA) ou a soma do FRE por exercício de origem; a data de pagamento do FRE
  ainda não entra em nenhum critério.
- Bonificações e desdobramentos dependem do FRE (até o layout antigo) e do COTAHIST depois dele; um evento
  recente só do COTAHIST pode ficar suspeito até alguém confirmar.
- A data de efeito do evento vem do salto de preço; sem salto correspondente vale a data de aprovação, que pode
  ser meses antes da efetiva.
- Se a empresa mudar a data de encerramento do exercício, dois exercícios no mesmo ano civil colidem e vale o
  mais recente.
