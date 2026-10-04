"""Carga no Postgres a partir de zips montados com as fixtures reais."""

import io
import zipfile
from datetime import date
from decimal import Decimal

import pytest

from acoesb3 import http, load
from conftest import FIXTURES, fixture_bytes

STMT_HEADER = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;GRUPO_DFP;MOEDA;ESCALA_MOEDA;ORDEM_EXERC;"
    "DT_INI_EXERC;DT_FIM_EXERC;CD_CONTA;DS_CONTA;VL_CONTA;ST_CONTA_FIXA\n"
)
SHARES_HEADER = (
    "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;QT_ACAO_ORDIN_CAP_INTEGR;QT_ACAO_PREF_CAP_INTEGR;"
    "QT_ACAO_TOTAL_CAP_INTEGR;QT_ACAO_ORDIN_TESOURO;QT_ACAO_PREF_TESOURO;QT_ACAO_TOTAL_TESOURO\n"
)


def make_zip(prefix: str, year: int, with_shares: bool = True) -> bytes:
    """Zip com os arquivos da fixture; demonstrações sem amostra entram só com cabeçalho."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        names = [f"{prefix}{year}.csv"]
        if with_shares:
            names.append(f"{prefix}composicao_capital_{year}.csv")
        names += [
            f"{prefix}{s}_{sc}_{year}.csv" for s in load.cvm.STATEMENTS for sc in ("con", "ind")
        ]
        for name in names:
            path = FIXTURES / name
            if path.exists():
                z.writestr(name, path.read_bytes())
            elif "composicao" in name:
                z.writestr(name, SHARES_HEADER.encode("latin-1"))
            else:
                z.writestr(name, STMT_HEADER.encode("latin-1"))
    return buf.getvalue()


class FakeResponse:
    def __init__(self, content, status=200):
        self.content = content
        self.status_code = status
        self.headers = {"Last-Modified": "Sun, 27 Sep 2026 10:25:02 GMT"}


@pytest.fixture
def served(monkeypatch):
    files: dict[str, bytes] = {}

    def fake_fetch(url, retries=4, timeout=300):
        if url in files:
            return FakeResponse(files[url])
        return FakeResponse(b"", 404)

    monkeypatch.setattr(http, "fetch", fake_fetch)
    return files


def test_dfp_carga_valores_em_reais_e_versoes(conn, served):
    served[load.cvm.doc_url("DFP", 2024)] = make_zip("dfp_cia_aberta_", 2024)
    result = load.load_doc_year(conn, "DFP", 2024)
    assert result["filings"] == 7

    lucro = conn.execute(
        """SELECT l.value, l.source_scale, f.received_date
           FROM financial_line l JOIN filing f ON f.id = l.filing_id
           WHERE f.cvm_code = 5410 AND l.statement = 'DRE' AND l.account_code = '3.11.01'"""
    ).fetchone()
    assert lucro[0] == Decimal("6042593000")
    assert lucro[1] == "MIL"

    lpa = conn.execute(
        """SELECT l.value FROM financial_line l JOIN filing f ON f.id = l.filing_id
           WHERE f.cvm_code = 5410 AND l.account_code = '3.99.01.01'"""
    ).fetchone()[0]
    assert lpa == Decimal("1.44026")

    # Só contas da lista configurada
    codes = {r[0] for r in conn.execute("SELECT DISTINCT account_code FROM financial_line")}
    allowed = conn.execute("SELECT statement, code, include_children FROM cvm_account").fetchall()
    for code in codes:
        # filhos diretos de uma conta 2.NN (o PL, achado por nome) entram além da lista
        parent = code.rsplit(".", 1)[0] if code.startswith("2.") and code.count(".") == 2 else None
        assert any(
            code == c or (ch and code.startswith(c + ".")) or parent == c for _, c, ch in allowed
        ), code

    # BRB: 3 versões no índice com datas de entrega; nenhuma tem contas nesta amostra
    brb = conn.execute(
        "SELECT version, received_date, has_lines FROM filing WHERE cvm_code = 14206 ORDER BY 1"
    ).fetchall()
    assert [v for v, _, _ in brb] == [1, 2, 3]
    assert brb[0][1] == date(2025, 4, 9)

    # Composição do capital ligada por CNPJ + data + versão
    itau = conn.execute(
        """SELECT s.total FROM share_count s JOIN filing f ON f.id = s.filing_id
           WHERE f.cvm_code = 19348"""
    ).fetchone()
    assert itau is not None and itau[0] > 0

    # Fonte, data-base e data de coleta rastreáveis
    src = conn.execute(
        """SELECT sf.url, f.reference_date, sf.collected_at FROM filing f
           JOIN source_file sf ON sf.id = f.source_file_id WHERE f.cvm_code = 5410"""
    ).fetchone()
    assert src[0].endswith("dfp_cia_aberta_2024.zip")
    assert src[1] == date(2024, 12, 31)
    assert src[2] is not None


def test_dfp_carga_idempotente(conn, served):
    served[load.cvm.doc_url("DFP", 2024)] = make_zip("dfp_cia_aberta_", 2024)
    first = load.load_doc_year(conn, "DFP", 2024)
    n1 = conn.execute("SELECT count(*) FROM financial_line").fetchone()[0]
    assert load.load_doc_year(conn, "DFP", 2024) == {"skipped": "sem mudança"}
    again = load.load_doc_year(conn, "DFP", 2024, force=True)
    n2 = conn.execute("SELECT count(*) FROM financial_line").fetchone()[0]
    assert n1 == n2 == first["lines"] == again["lines"]
    assert conn.execute("SELECT count(*) FROM filing").fetchone()[0] == 7


def test_itr_trimestre_e_acumulado(conn, served):
    served[load.cvm.doc_url("ITR", 2025)] = make_zip("itr_cia_aberta_", 2025)
    load.load_doc_year(conn, "ITR", 2025)
    rows = conn.execute(
        """SELECT l.period_start, l.value FROM financial_line l JOIN filing f ON f.id = l.filing_id
           WHERE f.reference_date = '2025-06-30' AND l.account_code = '3.11.01'
           ORDER BY 1"""
    ).fetchall()
    assert [r[0] for r in rows] == [date(2025, 1, 1), date(2025, 4, 1)]
    assert rows[0][1] > rows[1][1]  # acumulado do semestre > trimestre (lucro positivo)


def test_fca_tickers(conn, served):
    served[load.cvm.doc_url("FCA", 2026)] = make_fca_zip()
    load.load_doc_year(conn, "FCA", 2026)
    row = conn.execute(
        "SELECT cvm_code, unit_composition FROM company_security WHERE ticker = 'TAEE11'"
    ).fetchone()
    assert row == (20257, "1 ON / 2 PN")


def make_fca_zip() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name in ("fca_cia_aberta_2026.csv", "fca_cia_aberta_valor_mobiliario_2026.csv"):
            z.writestr(name, fixture_bytes(name))
    return buf.getvalue()


def test_arquivo_inexistente_nao_falha(conn, served):
    assert load.load_doc_year(conn, "DFP", 2031) == {"skipped": "arquivo inexistente"}


def test_cad(conn, served):
    served[load.cvm.CAD_URL] = fixture_bytes("cad_cia_aberta.csv")
    load.load_cad(conn)
    canceled = conn.execute(
        "SELECT status, canceled_at FROM company WHERE cvm_code = 21954"
    ).fetchone()
    assert canceled == ("CANCELADA", date(2015, 12, 18))


def test_cotahist_fatcot_e_filtro(conn, served):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("COTAHIST_A2010.TXT", fixture_bytes("COTAHIST_A2010_sample.TXT"))
    url = load.cotahist_year_url(2010)
    served[url] = buf.getvalue()
    result = load.load_cotahist(conn, url)
    assert result["quotes"] == 5  # 3 com FATCOT 1000 + PETR4 + WEGE3; fracionário fora

    petr = conn.execute(
        """SELECT q.close, q.volume FROM quote_daily q JOIN security s ON s.id = q.security_id
           WHERE s.ticker = 'PETR4'"""
    ).fetchone()
    assert petr[0] == Decimal("37.32")

    raw_close = next(
        load.cotahist.parse_line(ln)
        for ln in load.cotahist.iter_lines(fixture_bytes("COTAHIST_A2010_sample.TXT"))
        if ln[12:24].strip() == "CBEE3"
    ).close
    cbee = conn.execute(
        """SELECT q.close FROM quote_daily q JOIN security s ON s.id = q.security_id
           WHERE s.ticker = 'CBEE3'"""
    ).fetchone()[0]
    assert cbee == raw_close / 1000

    # Reprocessar não duplica
    load.load_cotahist(conn, url, force=True)
    assert conn.execute("SELECT count(*) FROM quote_daily").fetchone()[0] == 5


def test_documento_fora_do_indice_e_ignorado_e_registrado(conn, served):
    idx = fixture_bytes("fca_cia_aberta_2026.csv").decode("latin-1").splitlines()
    vm = fixture_bytes("fca_cia_aberta_valor_mobiliario_2026.csv").decode("latin-1")
    # remove do índice o documento da Taesa: as linhas dela em valor_mobiliario ficam órfãs
    taesa_doc = next(ln.split(";")[6] for ln in idx[1:] if ln.split(";")[4] == "020257")
    idx = [ln for ln in idx if ln.split(";")[6] != taesa_doc]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("fca_cia_aberta_2026.csv", ("\n".join(idx) + "\n").encode("latin-1"))
        z.writestr("fca_cia_aberta_valor_mobiliario_2026.csv", vm.encode("latin-1"))
    served[load.cvm.doc_url("FCA", 2026)] = buf.getvalue()
    result = load.load_doc_year(conn, "FCA", 2026)
    assert result["orphan_doc_ids"] == [int(taesa_doc)]
    tickers = {r[0] for r in conn.execute("SELECT ticker FROM company_security")}
    assert "TAEE11" not in tickers and "BBAS3" in tickers


def test_zip_antigo_sem_composicao_capital(conn, served):
    # DFP 2010 real não tem composicao_capital: carrega o resto e registra a ausência
    served[load.cvm.doc_url("DFP", 2024)] = make_zip("dfp_cia_aberta_", 2024, with_shares=False)
    result = load.load_doc_year(conn, "DFP", 2024)
    assert result["share_counts"] == "arquivo ausente no zip"
    assert result["lines"] > 0
    assert conn.execute("SELECT count(*) FROM share_count").fetchone()[0] == 0


def test_carga_historica_segue_apos_ano_com_erro(conn, served, monkeypatch):
    from acoesb3 import cli

    served[load.cvm.doc_url("DFP", 2024)] = make_zip("dfp_cia_aberta_", 2024)
    served[load.cvm.doc_url("DFP", 2023)] = b"isto nao e um zip"
    monkeypatch.setattr(cli, "connect", lambda: _NoClose(conn))
    with pytest.raises(SystemExit, match="cvm_dfp_2023"):
        cli.main(["cvm", "--doc", "DFP", "--from-year", "2023", "--to-year", "2024"])
    runs = dict(conn.execute("SELECT job, status FROM collection_run").fetchall())
    assert runs == {"cvm_dfp_2023": "failed", "cvm_dfp_2024": "ok"}


class _NoClose:
    """Usa a conexão do teste dentro do `with connect()` da CLI sem fechá-la."""

    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self.conn

    def __exit__(self, *exc):
        return False


def test_backtest_usa_data_da_versao_guardada(conn, served):
    # BRB tem 3 versões no índice; simula que a versão 3 é a que tem números
    served[load.cvm.doc_url("DFP", 2024)] = make_zip("dfp_cia_aberta_", 2024)
    load.load_doc_year(conn, "DFP", 2024)
    conn.execute("UPDATE filing SET has_lines = true WHERE cvm_code = 14206 AND version = 3")
    row = conn.execute(
        "SELECT version, available_from, first_received_date FROM filing_available"
        " WHERE cvm_code = 14206"
    ).fetchall()
    assert len(row) == 1
    version, available_from, first = row[0]
    v3 = conn.execute(
        "SELECT received_date FROM filing WHERE cvm_code = 14206 AND version = 3"
    ).fetchone()[0]
    assert version == 3
    assert available_from == v3  # data da versão guardada, não a da 1ª entrega
    assert first == date(2025, 4, 9) and available_from > first
