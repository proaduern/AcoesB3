# Fixtures

Linhas copiadas **sem edição** dos arquivos oficiais, baixados pelo GitHub Actions em 03/10/2026
(scripts `scripts/probe_*.py`, já removidos do repositório; ver `docs/fontes.md`).
Arquivos CVM gravados em latin-1, como na origem.

- `dfp_cia_aberta_*_2024.csv`: DFP 2024, empresas WEG (5410), Itaú Unibanco (19348),
  BB Seguridade (23159), CEL Participações (16675, única em `ESCALA_MOEDA = UNIDADE`);
  no índice também BRB (14206), que tem 3 versões.
- `itr_cia_aberta_*_2025.csv`: ITR 2025 da WEG (DRE, contas 3.01, 3.11*, 3.99*).
- `fca_cia_aberta_*_2026.csv`: FCA 2026 de Taesa (20257) e Banco do Brasil (1023).
- `cad_cia_aberta.csv`: cadastro CVM (inclui uma cancelada e CD_CVM duplicados).
- `COTAHIST_A2010_sample.TXT`: COTAHIST 2010 com header, 3 linhas com FATCOT = 1000,
  PETR4, WEGE3, uma do fracionário e trailer.
- `COTAHIST_A2024_A2010_A1986_sample.txt`: linhas iniciais/finais e amostras de 2024, 2010 e 1986.

Header (00) e trailer (99) do COTAHIST: o log do Actions corta espaços no fim da linha;
foram completados com espaços até 245 posições, que é o conteúdo original desses campos (FILLER).

## FRE (verificado em 04/10/2026)

- `fre_cia_aberta_capital_social_2010.csv`, `..._capital_social_desdobramento_2018.csv`,
  `..._distribuicao_dividendos_classe_acao_2018.csv`: cabeçalho e primeiras linhas dos arquivos
  reais (BB, Telebras, Fictor), reconstruídos a partir da saída da sonda do Actions, sem edição
  dos valores.
- `fre_cia_aberta_2010.csv`: as duas primeiras linhas do índice do FRE 2010 (BB, versões 1 e 2).
  A linha da versão 11 (ID 9670), que liga o `capital_social` ao documento, **não** foi impressa
  pela sonda; os testes de carga acrescentam essa linha de índice sintética.
