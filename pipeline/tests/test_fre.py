"""FRE: parsers (linhas reais, ver tests/fixtures/README.md) e carga no Postgres."""

import io
import zipfile
from datetime import date
from decimal import Decimal

import pytest
from test_load import FakeResponse

from acoesb3 import fre, http, load
from conftest import fixture_bytes

D = Decimal


def test_indice_do_fre_vira_doc_type_fre():
    idx = fre.parse_index(fixture_bytes("fre_cia_aberta_2010.csv"))
    assert [(r.doc_type, r.cvm_code, r.version, r.doc_id) for r in idx] == [
        ("FRE", 1023, 1, 1861),
        ("FRE", 1023, 2, 3161),
    ]
    assert idx[0].received_date == date(2010, 8, 13)


def test_categoria_desconhecida_no_indice_falha():
    raw = fixture_bytes("fre_cia_aberta_2010.csv").replace(b";FRE;", b";OUTRO;")
    with pytest.raises(ValueError, match="CATEG_DOC"):
        fre.parse_index(raw)


def test_capital_social_tipos_e_quantidades():
    rs = fre.parse_capital(fixture_bytes("fre_cia_aberta_capital_social_2010.csv"))
    assert [r.capital_type for r in rs] == [
        "Capital Emitido",
        "Capital Subscrito",
        "Capital Integralizado",
    ]
    r = rs[2]
    assert (r.doc_id, r.common, r.preferred, r.total) == (9670, 2860729247, 0, 2860729247)
    assert r.approved_on == date(2010, 4, 13)


def test_desdobramento_fator_e_tipo():
    rs = fre.parse_splits(fixture_bytes("fre_cia_aberta_capital_social_desdobramento_2018.csv"))
    assert [r.event_type for r in rs] == ["Grupamento"] * 3
    telebras, _, fictor = rs
    assert telebras.approved_on == date(2010, 12, 3)
    assert telebras.factor == D(109698912) / D(1096989129010)  # grupamento de 10.000 para 1
    assert fictor.factor == D(62696983) / D(313484914)  # 5 para 1
    assert (telebras.common_before, telebras.pref_after) == (886959131950, 21002999)


def test_evento_desconhecido_falha_em_vez_de_ser_ignorado():
    raw = fixture_bytes("fre_cia_aberta_capital_social_desdobramento_2018.csv")
    with pytest.raises(ValueError, match="Tipo_Evento"):
        fre.parse_splits(raw.replace(b"Grupamento", b"Fusao"))


def test_dividendos_por_classe_com_data_de_pagamento():
    rs, skipped = fre.parse_dividends(
        fixture_bytes("fre_cia_aberta_distribuicao_dividendos_classe_acao_2018.csv")
    )
    assert skipped == 0 and len(rs) == 3
    assert (rs[0].exercise_end, rs[0].share_type, rs[0].kind) == (
        date(2015, 12, 31),
        "Ordinária",
        "Dividendo Obrigatório",
    )
    assert rs[2].kind == "Juros Sobre Capital Próprio"
    assert rs[2].amount == D("246620000.00") and rs[2].paid_on == date(2016, 3, 11)
    assert sum(r.amount for r in rs if r.kind == "Dividendo Obrigatório") == D("1300507000.00")


def test_latin1_tambem_e_lido():
    raw = fixture_bytes("fre_cia_aberta_distribuicao_dividendos_classe_acao_2018.csv")
    rs, _ = fre.parse_dividends(raw.decode("utf-8").encode("latin-1"))
    assert rs[0].share_type == "Ordinária" and rs[2].kind == "Juros Sobre Capital Próprio"


def test_montante_vazio_e_exercicio_vazio_sao_descartados_e_contados():
    raw = fixture_bytes("fre_cia_aberta_distribuicao_dividendos_classe_acao_2018.csv").decode()
    lines = raw.splitlines()
    bad_amount = lines[1].replace("39046000.00", "")
    bad_end = lines[2].replace("2015-12-31", "")
    rs, skipped = fre.parse_dividends("\n".join([lines[0], bad_amount, bad_end, lines[3]]).encode())
    assert skipped == 2 and len(rs) == 1


def test_campo_com_aspas_e_ponto_e_virgula_usa_leitura_com_aspas():
    raw = b'A;B\nx;"um; dois"\n'
    assert fre.rows(raw) == [{"A": "x", "B": "um; dois"}]


def test_linha_com_campos_a_mais_falha():
    with pytest.raises(ValueError, match="campos"):
        fre.rows(b"A;B\n1;2;3\n")


def test_limites_de_data():
    b = fre.Bounds(min_year=1990, max_future_days=30)
    received = date(2018, 6, 1)
    assert b.ok(date(2016, 4, 4), received) == date(2016, 4, 4)
    assert b.ok(date(2077, 3, 8), received) is None  # caso real: aprovação em 2077
    assert b.ok(date(1899, 1, 1), received) is None
    assert b.ok(date(2018, 6, 25), received) == date(2018, 6, 25)
    assert b.ok(None, received) is None


# --- Carga -------------------------------------------------------------------

INDEX_HEADER = "CNPJ_CIA;DT_REFER;VERSAO;DENOM_CIA;CD_CVM;CATEG_DOC;ID_DOC;DT_RECEB;LINK_DOC\n"


def index_row(cnpj, name, cvm_code, version, doc_id, received, categ="FRE"):
    return f"{cnpj};2018-01-01;{version};{name};{cvm_code:06d};{categ};{doc_id};{received};x\n"


def fre_zip(year, index_rows, **members):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(fre.member("", year), (INDEX_HEADER + "".join(index_rows)).encode())
        for suffix, content in members.items():
            z.writestr(fre.member(suffix, year), content)
    return buf.getvalue()


@pytest.fixture
def served(monkeypatch):
    files: dict[str, bytes] = {}
    monkeypatch.setattr(
        http,
        "fetch",
        lambda url, retries=4, timeout=300: (
            FakeResponse(files[url]) if url in files else FakeResponse(b"", 404)
        ),
    )
    return files


def test_carga_do_fre_2018_com_desdobramento_e_dividendos(conn, served):
    # Linhas de índice sintéticas (só as de 2010 são reais): ligam os documentos às fixtures.
    idx = [
        index_row("00.000.000/0001-91", "BCO BRASIL S.A.", 1023, 28, 82919, "2018-06-20"),
        index_row("00.336.701/0001-04", "TELEBRAS", 11258, 10, 82472, "2018-06-21"),
        index_row("00.359.742/0001-08", "FICTOR", 8885, 5, 81590, "2018-06-22"),
    ]
    served[load.cvm.doc_url("FRE", 2018)] = fre_zip(
        2018,
        idx,
        capital_social_desdobramento=fixture_bytes(
            "fre_cia_aberta_capital_social_desdobramento_2018.csv"
        ),
        distribuicao_dividendos_classe_acao=fixture_bytes(
            "fre_cia_aberta_distribuicao_dividendos_classe_acao_2018.csv"
        ),
    )
    result = load.load_doc_year(conn, "FRE", 2018)
    assert result["filings"] == 3 and result["splits"] == 3 and result["dividends"] == 3
    assert result["absent_files"] == [fre.member("capital_social", 2018)]
    assert result["orphan_doc_ids"] == []
    assert result["splits_invalid_dates"] == 0

    assert conn.execute("SELECT doc_type, count(*) FROM filing GROUP BY 1").fetchall() == [
        ("FRE", 3)
    ]
    row = conn.execute(
        "SELECT s.event_type, s.approved_on, s.total_before, s.total_after, f.cvm_code, f.has_lines"
        " FROM fre_split s JOIN filing f ON f.id = s.filing_id WHERE f.cvm_code = 11258"
        " ORDER BY s.approved_on"
    ).fetchall()
    assert row[0] == ("Grupamento", date(2010, 12, 3), 1096989129010, 109698912, 11258, True)
    paid = conn.execute(
        "SELECT sum(amount), min(paid_on), max(paid_on) FROM fre_dividend"
    ).fetchone()
    assert paid == (D("1547127000.00"), date(2015, 5, 29), date(2016, 3, 11))

    # idempotente: sem mudança pula; com força reprocessa sem duplicar
    assert load.load_doc_year(conn, "FRE", 2018) == {"skipped": "sem mudança"}
    load.load_doc_year(conn, "FRE", 2018, force=True)
    assert conn.execute("SELECT count(*) FROM fre_dividend").fetchone()[0] == 3
    assert conn.execute("SELECT count(*) FROM fre_split").fetchone()[0] == 3


def test_carga_do_fre_2010_capital_social_e_arquivos_ausentes(conn, served):
    idx = fixture_bytes("fre_cia_aberta_2010.csv").decode().splitlines()[1:]
    idx.append(index_row("00.000.000/0001-91", "BCO BRASIL S.A.", 1023, 11, 9670, "2011-01-10"))
    idx = [line if line.endswith("\n") else line + "\n" for line in idx]
    served[load.cvm.doc_url("FRE", 2010)] = fre_zip(
        2010, idx, capital_social=fixture_bytes("fre_cia_aberta_capital_social_2010.csv")
    )
    result = load.load_doc_year(conn, "FRE", 2010)
    assert result["capital"] == 3 and result["orphan_doc_ids"] == []
    assert sorted(result["absent_files"]) == sorted(
        [
            fre.member("capital_social_desdobramento", 2010),
            fre.member("distribuicao_dividendos_classe_acao", 2010),
        ]
    )
    rows = conn.execute(
        "SELECT c.capital_type, c.shares_total, f.version, f.has_lines FROM fre_capital c"
        " JOIN filing f ON f.id = c.filing_id ORDER BY c.capital_type"
    ).fetchall()
    assert rows[0] == ("Capital Emitido", 2860729247, 11, True)
    # as versões 1 e 2 do índice ficam em filing, sem dados
    assert conn.execute(
        "SELECT version, has_lines FROM filing WHERE doc_type='FRE' ORDER BY version"
    ).fetchall() == [(1, False), (2, False), (11, True)]


def test_data_invalida_do_fre_e_descartada_e_contada(conn, served):
    raw = fixture_bytes("fre_cia_aberta_capital_social_desdobramento_2018.csv")
    raw = raw.replace(b"2016-04-29", b"2077-03-08")  # caso real: aprovação em 2077
    idx = [
        index_row("00.336.701/0001-04", "TELEBRAS", 11258, 10, 82472, "2018-06-21"),
        index_row("00.359.742/0001-08", "FICTOR", 8885, 5, 81590, "2018-06-22"),
    ]
    served[load.cvm.doc_url("FRE", 2018)] = fre_zip(2018, idx, capital_social_desdobramento=raw)
    result = load.load_doc_year(conn, "FRE", 2018)
    assert result["splits_invalid_dates"] == 1
    assert (
        conn.execute("SELECT count(*) FROM fre_split WHERE approved_on IS NULL").fetchone()[0] == 1
    )


def test_documento_fora_do_indice_e_registrado(conn, served):
    idx = [index_row("00.336.701/0001-04", "TELEBRAS", 11258, 10, 82472, "2018-06-21")]
    served[load.cvm.doc_url("FRE", 2018)] = fre_zip(
        2018,
        idx,
        capital_social_desdobramento=fixture_bytes(
            "fre_cia_aberta_capital_social_desdobramento_2018.csv"
        ),
    )
    result = load.load_doc_year(conn, "FRE", 2018)
    assert result["orphan_doc_ids"] == [81590]
    assert result["splits"] == 2
