# Fase 1 — Banco + coleta CVM e cotações

## Entregue

- `pipeline/` (Python 3.11+): migrações SQL, parsers e carga idempotente.
  - **CVM**: cadastro (diário), DFP, ITR e FCA (zips anuais). Todas as versões de cada
    documento ficam em `filing` com a data de entrega (`received_date`); as contas ficam em
    `financial_line`, já em reais, ligadas à versão de onde vieram.
  - **COTAHIST**: anual (carga histórica) e diário (coleta). Cotação sem ajuste, por ação
    (FATCOT aplicado), em `quote_daily`.
  - Origem de cada número: `source_file` (URL, sha256, `Last-Modified`, data de coleta);
    data-base: `filing.reference_date` / `quote_daily.trade_date`.
  - Toda execução fica em `collection_run` (status, duração, contagens, documentos órfãos).
  - Parâmetros em `app_config`; contas guardadas em `cvm_account` (editáveis).
- Workflows:
  - `pipeline-ci`: lint + testes contra Postgres em contêiner.
  - `collect-daily`: terça a sábado, 02:50 UTC (23h50 de Brasília). Etapa com erro não
    interrompe as outras; no fim o job falha e o GitHub manda e-mail.
  - `backfill`: carga histórica manual por fonte e intervalo de anos.
- `docs/fontes.md`: formatos verificados nos arquivos reais.
- Testes: 33, com linhas reais copiadas dos arquivos oficiais.

## Carga completa medida (03/10/2026)

Primeiro medida no GitHub Actions contra um Postgres 16 descartável (~19 min); depois repetida no Neon (ver acima).

| Tabela | Linhas | Tamanho |
|---|---:|---:|
| `quote_daily` (COTAHIST 2010–2026, só ações/units) | 1.256.975 | 165,0 MB |
| `financial_line` (DFP 2010–2026, ITR 2011–2026) | 950.941 | 113,5 MB |
| `filing` (todas as versões de DFP/ITR/FCA) | 75.503 | 28,0 MB |
| demais | | ~5 MB |
| **Total** | | **319,6 MB** (32% de 1 GB) |

Crescimento estimado: ~20 MB/ano (≈90 mil cotações + ≈60 mil contas).

Conferências na carga: PETR4 fechou 37,78 em 02/01/2024 e 49,12 em 30/09/2026; TAEE11 38,13 e 41,81;
WEGE3 36,57 e 49,46.

Problemas reais encontrados nas fontes e como ficaram:

| Problema | Tratamento |
|---|---|
| `composicao_capital` não existe nos zips DFP/ITR até 2019 | Quantidade de ações fica indisponível nesses anos (registrado na execução). |
| A partir de 2021, linhas duplicadas byte a byte em DFP/ITR (ex.: CPX Distribuidora; 1.005 no ITR 2024) | Fica uma. |
| Mesma conta/período com valores diferentes no mesmo documento (poucos casos: DFP 2022–2024, ITR 2021) | Nenhum dos valores é gravado (indisponível); chaves registradas em `collection_run.detail`. |
| FCA 2021: 1 documento em `valor_mobiliario` fora do índice | Ignorado (sem data de entrega) e registrado. |
| COTAHIST 2020–2022: BDRs com `CODBDI = 02` | Filtro pelo tipo de ativo do ISIN. |

Prazos de entrega observados (versão 1, dias entre data-base e entrega à CVM):
ITR mediana 43, p90 47; DFP mediana 82, p90 94.

## Carga no Neon (03/10/2026)

Feita por um workflow temporário na branch de desenvolvimento (já removido): 68 etapas, todas `ok`,
~35 min. Banco no Neon: **317,9 MB** (32% de 1 GB). Conferido no próprio Neon: lucro do controlador 2024
WEG R$ 6.042.593 mil (LPA ON 1,44026), Itaú R$ 41.085.000 mil, BB Seguridade R$ 8.703.353 mil;
fechamentos de 30/09/2026 PETR4 49,12, TAEE11 41,81, WEGE3 49,46.

O `collect-daily` só começa a rodar quando os workflows estiverem na branch padrão (agendamentos
do GitHub Actions só valem lá). Recarga manual: Actions → `backfill` (também só na branch padrão).

## Ficou de fora, e por quê

| Item | Motivo |
|---|---|
| Detecção de entrega via RAD/ENET | A CVM atualiza DFP/ITR/FCA **semanalmente** (passa de 1 dia útil, então a seção 12 manda usar o RAD/ENET). Não implementei porque o endpoint do RAD não foi verificado e a regra exige não inventar endpoint. Precisa de decisão (ver relatório). |
| Cotação intradiária (brapi/Yahoo) | É só para exibição na tela (fase 5); a verificação de limites é item próprio da seção 12. |
| Classificação setorial B3 | Não é CVM nem COTAHIST; entra quando o filtro precisar (fase 2). O cadastro guarda o setor declarado à CVM, que não é a classificação B3. |
| Ajuste por desdobramento/grupamento e proventos | Fase 2. O `DISMES` (número de distribuição) do COTAHIST já é guardado para ajudar a detectar eventos. |
| Ticker ↔ empresa no passado | O FCA só traz ticker a partir de certo ano (em 2010 vem vazio). Ligar papéis antigos à empresa (via ISIN/prefixo) fica para a fase 2. |
| Comparativo (`PENÚLTIMO`) dos documentos | Só o exercício do próprio documento é guardado; o comparativo é o mesmo dado reapresentado no documento seguinte. |
| Contas do DFC de investimento/financiamento | Não são contas fixas da CVM (código e descrição mudam por empresa). O FCFE da fase 3 vai precisar de uma regra para elas. |
| Os 3 testes contra balanços publicados conferidos pelo usuário (seção 10) | Os testes usam valores dos arquivos da CVM. A conferência contra o balanço publicado precisa ser feita pelo usuário (ver relatório). |
