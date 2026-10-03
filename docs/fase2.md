# Fase 2 — Indicadores, filtro e outliers

**Estado**: código e testes prontos (98 testes, lint limpo). **Ainda não rodou no Neon**: o ambiente
de desenvolvimento não alcança o Neon nem a CVM. Os números reais só aparecem depois da execução
do workflow `compute` (ver "Como rodar"). Nada abaixo sobre dados reais foi observado, exceto o
que veio das fixtures (linhas copiadas dos arquivos oficiais da DFP 2024).

## Entregue

- `pipeline/migrations/0004_indicators_screen.sql`: parâmetros em `app_config`, contas de DVA de
  banco e seguradora em `cvm_account`, tabelas de revisão e de resultado.
- `acoesb3/indicators.py`: fatos de cada DFP por plano de contas (comum, banco, seguradora).
- `acoesb3/screen.py`: critérios do filtro, outliers e status (funções puras).
- `acoesb3/corporate.py`: detecção de desdobramento/grupamento/bonificação no COTAHIST.
- `acoesb3/mapping.py`: ticker -> empresa (raiz de 4 letras + FCA) e classe ON/PN.
- `acoesb3/compute.py`: lê o banco, calcula e grava (`indicator_annual`, `dividend_outlier`,
  `corporate_event`, `screen_result`, `screen_criterion`).
- `acoesb3/review.py` + `acoesb3 review ...`: decisão sobre outliers e eventos, proventos por
  outra fonte ou à mão, reclassificação de setor/plano, correção de ticker.
- Workflow `compute` (manual).
- Testes: `test_phase2_pure.py` (lógica; extração com as linhas reais de WEG, Itaú e BB Seguridade)
  e `test_compute.py` (Postgres: ponto no tempo, outlier, evento societário, liquidez, setor,
  idempotência). Mutações em fator de evento e exclusão de outlier derrubam testes.

## Achados que mudaram o desenho

- **A fase 1 não guardava os proventos de bancos e seguradoras.** Na DVA, JCP/dividendos são
  `7.08.04.*` (comum), `7.09.04.*` (banco) e `7.11.04.*` (seguradora). A migração 0004 inclui os
  dois últimos; **é preciso recarregar as DFP** (`reload_dfp` no workflow) para valerem.
- Lucro/PL do controlador: comum `3.11.01` e `2.03 − 2.03.09`; banco `3.09.01` e `2.08 − 2.08.09`
  (`2.08.01` é capital social, não PL do controlador); seguradora `3.13.01` e `2.03 − 2.03.09`.
- A CVM só dá ações de 2020 em diante, e LPA/dividendo por ação publicados não são reajustados por
  desdobramentos posteriores (o comparativo `PENÚLTIMO` não é guardado). Por isso o dividendo por
  ação sai de payout × LPA ajustado por eventos detectados, e o DY de valor de mercado (2020+).

## Como rodar

1. Merge na branch padrão (workflows `workflow_dispatch` só aparecem lá).
2. Actions → `compute` → marcar `reload_dfp` (primeira vez). Roda: recarga das DFP, fatos anuais,
   outliers, eventos, retratos, lista de pendências.
3. Revisar: `acoesb3 review list` (também impresso no fim do workflow). Decidir com
   `review outlier` e `review event`; depois rodar `compute` de novo.
4. Informar `screen.excluded_sectors` (valores de `company.cvm_sector`) e, se preciso,
   `review class` por empresa.

## Ficou de fora, e por quê

| Item | Motivo |
|---|---|
| Validação com dados reais | Sem acesso ao Neon/CVM aqui. Cobertura da DVA, ON/PN das contas `3.99.01.0x`, comportamento do DISMES e resultado do filtro precisam ser conferidos na primeira execução (lista em `ESPECIFICACAO.md` seção 12). |
| Lista de segmentos excluídos | O usuário ainda não informou; `screen.excluded_sectors` está vazio (nada excluído). |
| Fonte de ações antes de 2020 (FRE, capital social) | Não verificada. Sem ela o DY é indisponível nos retratos até 2024, que ficam em "dados insuficientes". Candidata a sonda na primeira execução. |
| Retratos antes de 2020 | Com DFP desde 2010 e janela de 10 anos, o critério completo só fecha em 2020 (`screen.snapshot_first_year`). **O backtest (fase 4, desde 2012) precisará de janelas menores configuradas ou de começar em 2021**: decisão para a fase 4. |
| Classificação setorial B3 | Usa o setor declarado à CVM + reclassificação manual (decisão do usuário). |
| Encadear `compute` no `collect-daily` | Evita alerta diário enquanto o cálculo não foi validado em dados reais. |
| Bonificações pequenas (< ~15%) | Fora da faixa de detecção por preço; cadastre com `review event-add`. Sem isso, geram queda falsa de dividendo por ação naquele ano. |
| Valor de mercado sem ON/PN negociadas separadamente | Empresas cujas ações só negociam em units ficam com DY indisponível. |
| Ajuste do preço por proventos (retorno total) | Fase 4. |

## Limitações conhecidas (honestas)

- "Pago" é "declarado no exercício" (DVA): a CVM não traz data de pagamento.
- DPS = payout × LPA é exato para uma classe de ação; com ON e PN é aproximação (os dividendos
  por classe diferem).
- A data de coleta de cada retrato é a do arquivo de origem do primeiro carregamento da versão
  (`filing.source_file_id` não é atualizado em recargas).
- Se a empresa mudar a data de encerramento do exercício, dois exercícios no mesmo ano civil
  colidem e vale o mais recente.
