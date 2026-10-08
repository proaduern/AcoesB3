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
- Filtro do pipeline (configurável): `CODBDI = 02` (lote padrão), `TPMERC = 010` (à vista) e
  tipo de ativo do ISIN (posições 7–9 do ISIN) em `ACN` (ação), `UNT`/`CDA` (unit).
  Em 2024: 85.739 registros com CODBDI 02, de 2,6 milhões no arquivo.
- **Em 2020–2022 a B3 marcou BDRs com `CODBDI = 02`** (ESPECI `DRN`/`DR3`, ISIN tipo `BDR`,
  ex.: `A1AP34`). Em 2021 eram 718 dos 1.309 papéis com CODBDI 02. Daí o filtro pelo ISIN.
- `DT_REFER`/datas: AAAAMMDD. Arquivo de 1986 tem ISIN no formato antigo (sem `BR`).

## CVM — RAD/ENET (consulta externa de documentos)

Verificado em 03/10/2026:
- `https://www.rad.cvm.gov.br/ENET/frmConsultaExternaCVM.aspx` foi **descontinuada em 06/07/2026**
  e redireciona para `https://www.rad.cvm.gov.br/ENETWeb/frmConsultaExternaCVM.aspx`.
- A listagem (`frmConsultaExternaCVM.aspx/ListarDocumentos`, POST JSON com `dataDe`, `dataAte`,
  `empresa`, `categoria`...) envia um token do **Google reCAPTCHA v3** e, se o servidor pedir
  (`SolicitarCaptcha = 'S'`), um desafio reCAPTCHA v2. Não é usada pelo pipeline: automatizar
  exigiria contornar o CAPTCHA.
- O conjunto de dados IPE (documentos eventuais) da CVM Dados Abertos também é semanal, então
  não serve para detectar entrega no mesmo dia.

## CVM — FRE (Formulário de Referência)

Verificado em 04/10/2026 baixando os arquivos reais pelo GitHub Actions (sonda temporária, já removida; os fixtures de `pipeline/tests/fixtures` guardam as linhas reais).

- URL: `https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS/fre_cia_aberta_{ano}.zip`, de 2010 a 2026
  (44 arquivos por zip). Os zips de 2010 a 2024 têm o mesmo conjunto de arquivos; **os de 2025 e 2026 (layout
  novo, `CATEG_DOC = 'FRE WEB'`) não trazem** `capital_social_desdobramento`, `capital_social_aumento`,
  `capital_social_reducao`, `distribuicao_dividendos`, `distribuicao_dividendos_classe_acao`,
  `plano_recompra`, `informacao_financeira`, entre outros. O `capital_social` continua.
- Índice `fre_cia_aberta_{ano}.csv`: mesmas colunas do DFP (`CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;CATEG_DOC;
  ID_DOC;DT_RECEB;LINK_DOC`). `CATEG_DOC` = `FRE` (até 2019), `FRE NOVO` (2020), `FRE WEB` (2025+).
  `DT_REFER` é só um marcador do ano (1º de janeiro até 2024; 31 de dezembro depois). Uma linha por versão
  (até 8 ou mais); `DT_RECEB` de um zip "2015" vai de 2014 a 2018 (reapresentações).
- Os arquivos de dados trazem **só a última versão** de cada documento (`(CNPJ, Versão)` do capital = 650 contra
  2.782 no índice), ligada ao índice por `ID_Documento` = `ID_DOC`.
- `capital_social`: `Tipo_Capital` = Capital Emitido, Subscrito, Integralizado ou Autorizado;
  `Data_Autorizacao_Aprovacao`; `Quantidade_Acoes_Ordinarias/Preferenciais/Total`. Em unidades de ações
  (Ambev 15,76 bilhões; Vale 4,44 bilhões; Itaú 5,6 + 5,4 bilhões). Mais de uma linha "Capital Integralizado" por
  documento quando há histórico de aprovações. Não traz tesouraria.
- `capital_social_desdobramento`: `Tipo_Evento` = Desdobramento, Grupamento ou Bonificação; `Data_Aprovacao` (de
  **aprovação**, com valores inválidos como 2077-03-08); quantidades antes e depois, por total, ON e PN.
  Casos conferidos: WEG (bonificações 2014 e 2018, desdobramentos 2015 e 2021 — os dois desdobramentos batem com
  o COTAHIST), Itaú (bonificações 2013-2015; desdobramento 1,5x aprovado em 27/07/2018 e visto no preço em
  21/11/2018).
- `distribuicao_dividendos_classe_acao`: `Data_Inicio/Fim_Exercicio_Social`, `Especie_Acao` (Ordinária,
  Preferencial ou vazio), `Classe_Acao`, `Dividendo_Distribuido` (Dividendo Obrigatório, Juros Sobre Capital
  Próprio, Outros, Dividendo Prioritário Mínimo/Fixo ou vazio), `Montante` (R$) e `Data_Pagamento_Dividendo`
  (vazia em ~13% das linhas). Cada documento lista os 2-3 últimos exercícios (FRE 2018: 2015 a 2017), então
  documentos de anos seguidos se sobrepõem. Vale e Gerdau, com DVA zerada, têm pagamentos aqui.
- Encoding e aspas não verificados no byte: o parser tenta UTF-8, depois latin-1, e aceita aspas se o número de
  campos não bater.

### Quantidade de ações na DFP (`composicao_capital`)

Sem coluna de escala. Em 2024: Ambev 15.757.657, Vale 4.539.008 e Itaú 4.958.290 ON (**em milhares**); BB
5.730.834.040, Petrobras 7.442.454.142 e WEG 4.197.317.998 (em unidades). Por isso a fase 2 usa as ações do FRE.

## CVM — DFC (fluxo de caixa) para o FCFE

Verificado em 05/10/2026 pelo GitHub Actions (sonda temporária, já removida) nas DFP de 2021 e 2024 das empresas da lista
(Alupar, Engie, ISA, Sanepar, Copasa, Vivo, Cemig, CPFL, Taesa, Sabesp, TIM).

- O zip da DFP traz `dfp_cia_aberta_DFC_MI_con`, `DFC_MI_ind`, `DFC_MD_con` e `DFC_MD_ind` (método indireto e direto, consolidado e individual); `ESCALA_MOEDA = MIL`.
- **Só os totais são padronizados**: `6.01` caixa líquido operacional, `6.02` investimento, `6.03` financiamento, `6.04` variação cambial, `6.05` aumento (redução) de caixa, `6.05.01` e `6.05.02` saldos inicial e final.
  As contas filhas mudam de código **e de nome** por empresa: imobilizado é `6.02.08` na Alupar, `6.02.03` na Cemig, `6.02.01` na Sanepar e na Vivo; dividendos e JCP pagos são `6.03.06` (Alupar), `6.03.07` (Engie), `6.03.04` (Vivo), `6.03.03` (Cemig, TIM) e `6.03.07` (Sanepar). Por isso o FCFE classifica as filhas pela descrição (`fcfe.*` em `app_config`, ver `acoesb3/fcfe.py`) e guarda o detalhe para conferência (`acoesb3 ceilings list --dcf`).
- Sanepar, Sabesp e TIM só têm DFC individual em 2021 (sem arquivo consolidado); vale a regra de escopo da seção 9.
- Observado, não verificado nas notas: ISA tem `6.01.02` (variações de ativos e passivos) de −R$ 3,0 bi em 2021 contra −R$ 15 mi de imobilizado e intangível em `6.02`; é compatível com concessionárias que registram o investimento em ativo de contrato dentro do caixa operacional (nesse caso o `6.01` já o desconta).
- A carga guarda `6.01` de todas as empresas e `6.02.*`/`6.03.*` só da lista acompanhada (`cvm.dfc_only_watchlist`); empresa nova na lista exige recarregar as DFP (`compute` com `reload_dfp`).

## B3 — Ibovespa e IDIV (série diária de fechamento)

Verificado em 08/10/2026 pelo GitHub Actions (sonda temporária, já removida). A página "Estatísticas históricas" de cada índice
(`.../indice-ibovespa-ibovespa-estatisticas-historicas.htm`, `.../indice-dividendos-idiv-estatisticas-historicas.htm`) é um iframe de
`https://sistemaswebb3-listados.b3.com.br/indexStatisticsPage/daily-evolution/{IBOVESPA|IDIV}`, cujo código chama:

- `GET https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetPortfolioDay/{base64}`, com `base64` do JSON
  `{"index":"IBOVESPA","language":"pt-br","year":"2024"}` (sem espaços). `IBOV` também funciona; para o IDIV, `IDIV`.
- Resposta JSON: `min` e `max` (por mês) e `results`: 31 linhas, `day` de 1 a 31, com `rateValue1` a `rateValue12` (o mês).
  Valor = fechamento em pontos, texto brasileiro (`"128.481,02"`), ou `null` (sem pregão; também dias que não existem no mês).
  Conferido: IBOVESPA com 246–249 pregões por ano de 2005 a 2013, 2023, 2026 (192 em 2026 até 07/10); IDIV 2011 em diante com a série
  completa (2005 só tem 1 valor: o índice nasce no fim de 2005).
- O mesmo endpoint com `GetDownloadPortfolioDay` devolve o CSV (`Dia;Jan;Fev;...`) em base64; o JSON é mais simples.
- Os chamados `GetMonthlyEvolution` e `GetYearlyVariation` voltaram vazios para 2024 (não usados).
- Tipo: a B3 descreve o **IDIV B3 como índice de retorno total** (há também o IDIV Price Return); a página do Ibovespa não trouxe a
  expressão "retorno total" no texto verificado, então a conferência do tratamento de proventos do Ibovespa fica a cargo do usuário.
- `GetPortfolioDay` do `indexProxy` (outro serviço) devolve só a carteira teórica do dia; não serve para histórico.

## Banco Central — CDI (SGS)

Verificado em 08/10/2026 (Actions): `https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json&dataInicial=dd/mm/aaaa&dataFinal=dd/mm/aaaa`.

- Série 12 = CDI diário, **% ao dia** (ex.: 02/01/2012 = `"0.041028"`; 02/01/2024 = `0,043739` no CSV). JSON: `[{"data":"02/01/2012","valor":"0.041028"}, ...]`.
- Séries diárias aceitam no máximo **10 anos** por consulta (HTTP 406 acima disso, com mensagem em JSON): o pipeline consulta em janelas de 9 anos.
- A série 4389 (CDI anualizado base 252) responde `13.65` em outubro/2026; a 4391 é o CDI mensal; a 11 (Selic) rejeitou a chamada sem datas
  ("Requisição inválida"). A série 7 (Ibovespa no SGS) parou em 30/09/2019, por isso o Ibovespa vem da B3.
- Houve um 502 transitório na primeira chamada (a repetição respondeu); `http.fetch` já repete com espera.

## B3 — tarifas do mercado à vista (custos do backtest)

Verificado em 08/10/2026 no documento oficial "Tarifação de Produtos de Renda Variável" (v3.0, 42 páginas) e na página de tarifas da B3:
operações regulares (não day trade) no mercado à vista de ações, por investidor, pelo ADTV mensal: **até R$ 3 milhões de ADTV** — negociação
0,00500% + CCP 0,02240% + transferência de ativos (TTA) 0,0026% = **0,0300%** sobre o valor de cada ordem (comprador e vendedor);
acima de R$ 3 milhões, 0,0225%. Operações em leilão: negociação 0,0070%. O documento traz só a tabela vigente; o histórico de 2012 a 2025
(emolumentos eram outros) **não foi verificado**: o backtest usa 0,03% em todo o período (`backtest.b3_fee_schedule` aceita datas de
vigência para refinar). Corretagem zero, pela decisão do usuário.

## Tributação de ações (fontes secundárias; conferir na Receita)

Não foi possível abrir o site da Receita Federal desta sessão; as regras abaixo vêm de portais que citam a Lei 11.033/2004 e são as usadas
no backtest, como parâmetros: swing trade em ações paga **15%** sobre o ganho líquido do mês; vendas totais do mês **até R$ 20 mil**
(todas as corretoras) ficam isentas, de forma "tudo ou nada"; prejuízos compensam ganhos futuros do mesmo tipo (sem prazo), mas não
reduzem ganho que já seria isento; DARF até o último dia útil do mês seguinte. Dividendos: isentos (alíquota 0, `tax.dividend`); JCP: 15%
retidos na fonte (`tax.jcp`). Não modelado: IRRF "dedo-duro" de 0,005% sobre as vendas (compensável) e a retenção de 10% sobre dividendos
acima de R$ 50 mil por mês por pagador, que não se aplica a uma carteira deste tamanho.
