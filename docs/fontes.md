# Fontes de dados — formatos verificados

Verificados em 03/10/2026 baixando os arquivos reais pelo GitHub Actions
(o ambiente de desenvolvimento não alcança `dados.cvm.gov.br` nem `bvmf.bmfbovespa.com.br`).
As linhas usadas nos testes (`pipeline/tests/fixtures/`) foram copiadas desses arquivos, sem edição.

## CVM Dados Abertos — DFP, ITR, FCA

- URL: `https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/{DFP|ITR|FCA}/DADOS/{dfp|itr|fca}_cia_aberta_{ano}.zip`
- Histórico: DFP e FCA desde 2010, ITR desde 2011.
- Periodicidade oficial (página do conjunto de dados): **semanal**, "com as eventuais reapresentações".
  Na verificação, todos os zips de 2022–2026 tinham data de 27/09/2026 (domingo), e a página
  dizia "Última atualização: 28/09/2026". Os de anos antigos ficam congelados
  ("arquivos não sujeitos à política de atualização").
- CSV separado por `;`, codificação **latin-1**, sem aspas. Nenhuma linha com número de campos
  diferente do cabeçalho nas amostras.
- Dentro do zip:
  - `*_cia_aberta_{ano}.csv` — índice. Uma linha **por versão** entregue:
    `CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;CATEG_DOC;ID_DOC;DT_RECEB;LINK_DOC`.
  - Demonstrações (DFP/ITR): `BPA`, `BPP`, `DRE`, `DRA`, `DFC_MD`, `DFC_MI`, `DMPL`, `DVA`,
    cada uma em `_con` (consolidada) e `_ind` (individual), mais `composicao_capital` e `parecer` (DFP).
    Colunas: `CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;ORDEM_EXERC;
    [DT_INI_EXERC;]DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA` (balanços não têm `DT_INI_EXERC`).
  - **As demonstrações trazem só a versão mais recente de cada documento** (DFP 2024: 467 de 467
    documentos com a maior versão do índice; nenhum com duas versões). O histórico de versões
    só existe no índice. Consequência: versões antigas só ficam guardadas se coletadas na época.
  - `ORDEM_EXERC`: `ÚLTIMO` (exercício do documento) e `PENÚLTIMO` (comparativo). Com acento.
  - `ESCALA_MOEDA`: `MIL` ou `UNIDADE`. `MOEDA`: sempre `REAL` nas amostras.
  - **LPA (contas `3.99.*`) vem com `ESCALA_MOEDA = MIL` mas já está em R$/ação**
    (ex.: WEG 2024, `3.99.01.01` = 1,44026). Não pode ser multiplicado por 1000.
  - ITR: a DRE traz dois períodos no `ÚLTIMO` a partir do 2º trimestre — o trimestre
    (ex.: 01/04–30/06) e o acumulado do ano (01/01–30/06). DFC só o acumulado.
  - `DT_REFER` nem sempre é 31/12 (há exercícios encerrados em outras datas).
  - Plano de contas varia: empresa comum, banco e seguradora usam os mesmos códigos com sentidos
    diferentes (ex.: `2.03` = PL na comum, passivos ao custo amortizado no banco; PL do banco é `2.08`;
    lucro consolidado: `3.11` comum, `3.09` banco, `3.13` seguradora).
  - DFP 2024: 467 empresas com DRE consolidada, 704 com individual (242 só individual).
  - `composicao_capital` não tem `CD_CVM`: liga-se ao documento por CNPJ + data + versão.
- FCA: arquivos `geral`, `valor_mobiliario`, `auditor`, `dri`, `endereco`, `escriturador`,
  `canal_divulgacao`, `pais_estrangeiro_negociacao`, `departamento_acionistas`. Colunas em
  `Nome_Com_Maiusculas` (diferente do DFP/ITR). `valor_mobiliario` liga-se ao índice por `ID_Documento`.
  **No FCA 2010 o `Codigo_Negociacao` (ticker) vem vazio**; em 2026 vem preenchido (ex.: TAEE11
  com `Composicao_BDR_Unit` = "1 ON / 2 PN").
- Metadados: `.../{DFP|ITR|FCA}/META/` tem um zip com o dicionário (o `.txt` solto não existe: 404).

## CVM — cadastro de companhias

- URL: `https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv` (latin-1, `;`).
- Periodicidade oficial: **diária**.
- Inclui canceladas (1914 canceladas, 756 ativas, 8 suspensas na verificação), com `DT_CANCEL`.
- O mesmo `CD_CVM` pode aparecer em mais de uma linha (107 casos): o pipeline fica com a ativa,
  senão a de registro mais recente.

## B3 — COTAHIST

- Anual: `https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A{ano}.ZIP`
- Mensal: `COTAHIST_M{mm}{aaaa}.ZIP`; diário: `COTAHIST_D{dd}{mm}{aaaa}.ZIP`
  (o de 30/09/2026 tinha data 01/10/2026 00:44 UTC, ou seja, ~21h44 de Brasília do mesmo dia).
- Texto de largura fixa, **245 posições**, latin-1. Registros `00` (header), `01` (cotação), `99` (trailer).
- Preços e volume com 2 casas implícitas. `FATCOT` (posições 211–217) = 1 ou 1000:
  com 1000 o preço é por lote de mil ações (2010: 7.015 registros; 2024: 539).
- Conferência: PETR4 em 02/01/2024 — fechamento 37,78; preço médio 37,66 × 24.043.800 ações
  = volume 905.513.838,00 (bate com o campo VOLTOT).
- Filtro do pipeline (configurável): `CODBDI = 02` (lote padrão) e `TPMERC = 010` (à vista).
  Em 2024: 85.739 registros com CODBDI 02, de 2,6 milhões no arquivo.
