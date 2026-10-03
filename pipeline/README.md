# pipeline

Coleta e cálculos em Python. Roda no GitHub Actions e grava no Postgres (Neon).

## Rodar os testes

```bash
cd pipeline
pip install -e ".[dev]"
# precisa de um Postgres vazio; o teste apaga e recria o schema public
export TEST_DATABASE_URL=postgresql://usuario:senha@localhost:5432/acoes_test
ruff check . && ruff format --check . && python -m pytest -q
```

Sem `TEST_DATABASE_URL`, os testes de carga no banco são pulados.

## Comandos

```bash
export NEON_DATABASE_URL=...   # conexão direta (sem -pooler)
acoesb3 migrate                # só aplica migrações (todo comando já faz isso)
acoesb3 cad                    # cadastro de companhias da CVM
acoesb3 cvm --doc FCA|DFP|ITR [--from-year 2010] [--to-year 2026] [--force]
acoesb3 cotahist [--from-year 2010] [--to-year 2026] [--force]
acoesb3 daily                  # coleta diária (o que o workflow agendado roda)
acoesb3 size                   # tamanho do banco por tabela
```

Arquivo sem mudança desde a última coleta (mesmo sha256) é pulado; `--force` reprocessa.
Reprocessar é seguro: a carga substitui o que veio do mesmo documento/arquivo.

## Estrutura

- `migrations/` — SQL aplicado em ordem, registrado em `schema_migration`.
- `acoesb3/cvm.py`, `acoesb3/cotahist.py` — parsers (sem banco).
- `acoesb3/load.py` — download + carga.
- `acoesb3/cli.py` — linha de comando.
- `tests/fixtures/` — linhas reais dos arquivos oficiais (ver o README de lá).
