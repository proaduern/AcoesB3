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
- Testes: 29, com linhas reais copiadas dos arquivos oficiais.

## Como fazer a primeira carga (depois de corrigir o segredo, ver abaixo)

Actions → `backfill` → Run workflow, nesta ordem: `cad`, `FCA`, `DFP`, `ITR`, `cotahist`
(campos de ano vazios = de 2010 até hoje). Depois disso o `collect-daily` mantém tudo em dia.

## Ficou de fora, e por quê

| Item | Motivo |
|---|---|
| Carga real no Neon | O segredo `NEON_DATABASE_URL` chega **vazio** ao GitHub Actions (verificado: tamanho 0, idem `NEON_DATABASE_URL_POOLED`). A carga completa foi feita num Postgres descartável no Actions para validar e medir. |
| Detecção de entrega via RAD/ENET | A CVM atualiza DFP/ITR/FCA **semanalmente** (passa de 1 dia útil, então a seção 12 manda usar o RAD/ENET). Não implementei porque o endpoint do RAD não foi verificado e a regra exige não inventar endpoint. Precisa de decisão (ver relatório). |
| Cotação intradiária (brapi/Yahoo) | É só para exibição na tela (fase 5); a verificação de limites é item próprio da seção 12. |
| Classificação setorial B3 | Não é CVM nem COTAHIST; entra quando o filtro precisar (fase 2). O cadastro guarda o setor declarado à CVM, que não é a classificação B3. |
| Ajuste por desdobramento/grupamento e proventos | Fase 2. O `DISMES` (número de distribuição) do COTAHIST já é guardado para ajudar a detectar eventos. |
| Ticker ↔ empresa no passado | O FCA só traz ticker a partir de certo ano (em 2010 vem vazio). Ligar papéis antigos à empresa (via ISIN/prefixo) fica para a fase 2. |
| Comparativo (`PENÚLTIMO`) dos documentos | Só o exercício do próprio documento é guardado; o comparativo é o mesmo dado reapresentado no documento seguinte. |
| Contas do DFC de investimento/financiamento | Não são contas fixas da CVM (código e descrição mudam por empresa). O FCFE da fase 3 vai precisar de uma regra para elas. |
| Os 3 testes contra balanços publicados conferidos pelo usuário (seção 10) | Os testes usam valores dos arquivos da CVM. A conferência contra o balanço publicado precisa ser feita pelo usuário (ver relatório). |
