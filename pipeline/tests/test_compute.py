"""Fase 2 no Postgres: fatos anuais a partir das fixtures reais e filtro ponta a ponta."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from test_load import FakeResponse, make_zip

from acoesb3 import compute, http, load, review

D = Decimal
TODAY = date(2026, 6, 30)


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


# --- Fatos anuais a partir das linhas reais ----------------------------------


def test_fatos_anuais_das_tres_empresas_reais(conn, served):
    served[load.cvm.doc_url("DFP", 2024)] = make_zip("dfp_cia_aberta_", 2024)
    load.load_doc_year(conn, "DFP", 2024)
    result = compute.build_annual(conn)
    assert result["plans"] == {"comum": 2, "banco": 1, "seguradora": 1}  # WEG, CEL, Itaú, BB Seg

    rows = {
        r[0]: r[1:]
        for r in conn.execute(
            "SELECT cvm_code, plan, profit, equity, jcp, dividends, dividends_source, lpa_on,"
            " shares_on FROM indicator_annual"
        )
    }
    weg = rows[5410]
    assert weg[0] == "comum" and weg[1] == D("6042593000")
    assert weg[2] == D("23125217000") - D("920996000")
    assert (weg[3], weg[4], weg[5]) == (D("1134258000"), D("2056668000"), "dva")
    assert weg[6] == D("1.44026") and weg[7] > 0  # ações em circulação vindas da CVM
    assert rows[19348][:2] == ("banco", D("41085000000"))
    assert rows[19348][4] == D("28104000000")  # DVA 7.09.04.02 só existe após a migração 0004
    assert rows[23159][:2] == ("seguradora", D("8703353000"))
    assert rows[23159][4] == D("7111000000")


def test_fatos_anuais_idempotentes_e_com_override_de_proventos(conn, served):
    served[load.cvm.doc_url("DFP", 2024)] = make_zip("dfp_cia_aberta_", 2024)
    load.load_doc_year(conn, "DFP", 2024)
    compute.build_annual(conn)
    review.set_dividends(conn, 5410, date(2024, 12, 31), D("100"), D("200"), "manual", "teste")
    compute.build_annual(conn)
    n = conn.execute("SELECT count(*) FROM indicator_annual").fetchone()[0]
    compute.build_annual(conn)
    assert conn.execute("SELECT count(*) FROM indicator_annual").fetchone()[0] == n
    row = conn.execute(
        "SELECT jcp, dividends, dividends_source FROM indicator_annual WHERE cvm_code = 5410"
    ).fetchone()
    assert row == (D(100), D(200), "manual")
    review.clear_dividends(conn, 5410, date(2024, 12, 31))
    compute.build_annual(conn)
    assert conn.execute(
        "SELECT dividends_source FROM indicator_annual WHERE cvm_code = 5410"
    ).fetchone() == ("dva",)


def insert_dfp_lines(conn, cvm, lines, consolidated, ref=date(2024, 12, 31)):
    """DFP sintética com contas (R$), para exercitar o escopo e o plano de contas no banco."""
    sf = conn.execute(
        "INSERT INTO source_file (source, url, sha256, size_bytes)"
        " VALUES ('cvm_dfp', %s, 'h', 1) RETURNING id",
        (f"u{cvm}",),
    ).fetchone()[0]
    fid = conn.execute(
        "INSERT INTO filing (doc_type, cvm_code, cnpj, reference_date, version, doc_id,"
        " received_date, source_file_id, has_lines) VALUES ('DFP', %s, %s, %s, 1, %s, %s, %s, true)"
        " RETURNING id",
        (cvm, f"{cvm:014d}", ref, cvm, date(2025, 3, 15), sf),
    ).fetchone()[0]
    for (stmt, code), value in lines.items():
        conn.execute(
            "INSERT INTO financial_line (filing_id, statement, consolidated, account_code,"
            " period_start, period_end, value, source_scale)"
            " VALUES (%s, %s, %s, %s, NULL, %s, %s, 'UNIDADE')",
            (fid, stmt, consolidated, code, ref, value),
        )
    conn.commit()


def test_dfp_individual_e_plano_misto_no_banco(conn):
    individual = {
        ("DRE", "3.09"): D(7), ("DRE", "3.11"): D(8), ("BPP", "2.03"): D(50),
        ("DVA", "7.08.04.01"): D(1), ("DVA", "7.08.04.02"): D(2),
    }  # fmt: skip
    mixed = {
        ("DRE", "3.11"): D(10), ("DRE", "3.11.01"): D(9), ("BPP", "2.08"): D(100),
        ("BPP", "2.08.09"): D(4), ("DVA", "7.09.04.01"): D(1), ("DVA", "7.09.04.02"): D(2),
    }  # fmt: skip
    insert_dfp_lines(conn, 101, individual, consolidated=False)
    insert_dfp_lines(conn, 102, mixed, consolidated=True)
    result = compute.build_annual(conn)
    assert result["plans"] == {"comum": 1, "banco": 1}
    rows = {
        r[0]: r[1:]
        for r in conn.execute(
            "SELECT cvm_code, plan, profit, equity, jcp, dividends, notes->>'scope'"
            " FROM indicator_annual"
        )
    }
    assert rows[101] == ("comum", D(8), D(50), D(1), D(2), "individual")
    assert rows[102] == ("banco", D(9), D(96), D(1), D(2), "consolidada")


def test_override_exige_dfp_existente(conn):
    with pytest.raises(ValueError):
        review.set_dividends(conn, 1, date(2020, 12, 31), D(1), D(1), "manual", None)


# --- Filtro ponta a ponta com dados sintéticos --------------------------------

YEARS = range(2013, 2026)


def weekdays(end: date, days: int = 100):
    d = end - timedelta(days=days)
    while d <= end:
        if d.weekday() < 5:
            yield d
        d += timedelta(days=1)


class World:
    """Monta empresas, DFPs, FRE e cotações mínimas para exercitar o filtro."""

    def __init__(self, conn):
        self.conn = conn
        self.sf = conn.execute(
            "INSERT INTO source_file (source, url, sha256, size_bytes)"
            " VALUES ('cvm_dfp', 'x', 'h', 1) RETURNING id"
        ).fetchone()[0]
        self.next_doc = 1

    def company(
        self,
        cvm,
        ticker_root,
        sector="Energia",
        volume=3_000_000,
        every=1,
        dividends=None,
        split=None,
        shares=None,
        fre_dividends=None,
        fre_splits=(),
        last_year=2025,
    ):
        """``shares(ano)``: ações no fim do exercício; ``fre_dividends(ano)``: [(espécie, R$)] do
        exercício, num documento do FRE entregue em 15/06 do ano seguinte; ``fre_splits``:
        [(aprovação, antes, depois)] num documento do FRE entregue em 15/07/2022."""
        c = self.conn
        shares = shares or (lambda y: 1000)
        c.execute(
            "INSERT INTO company (cvm_code, cnpj, name, cvm_sector, status, source)"
            " VALUES (%s, %s, %s, %s, 'ATIVO', 'cvm_cad')",
            (cvm, f"{cvm:014d}", f"Empresa {cvm}", sector),
        )
        fca = self.filing("FCA", cvm, date(2025, 12, 31), date(2026, 1, 10), has_lines=True)
        c.execute(
            "INSERT INTO company_security (cvm_code, ticker, security_type, filing_id)"
            " VALUES (%s, %s, 'Ações Ordinárias', %s)",
            (cvm, f"{ticker_root}3", fca),
        )
        for y in range(YEARS.start, last_year + 1):
            fid = self.filing("DFP", cvm, date(y, 12, 31), date(y + 1, 3, 15))
            div = dividends(y) if dividends else (D(20), D(30))
            c.execute(
                "INSERT INTO indicator_annual (filing_id, cvm_code, reference_date, plan, profit,"
                " equity, jcp, dividends, dividends_source)"
                " VALUES (%s, %s, %s, 'comum', 100, 500, %s, %s, 'dva')",
                (fid, cvm, date(y, 12, 31), div[0], div[1]),
            )
        # FRE: um retrato do capital por ano (entregue em 30/05) com as ações do fim do ano anterior
        for y in range(2014, 2027):
            fid = self.filing("FRE", cvm, date(y, 1, 1), date(y, 5, 30))
            c.execute(
                "INSERT INTO fre_capital (filing_id, capital_type, approved_on, shares_common,"
                " shares_pref, shares_total) VALUES (%s, 'Capital Integralizado', %s, %s, 0, %s)",
                (fid, date(y, 1, 1), shares(min(y - 1, 2025)), shares(min(y - 1, 2025))),
            )
        if fre_dividends:
            for y in YEARS:
                fid = self.filing("FRE", cvm, date(y + 1, 1, 1), date(y + 1, 6, 15), version=2)
                for kind, amount in fre_dividends(y):
                    c.execute(
                        "INSERT INTO fre_dividend (filing_id, exercise_start, exercise_end,"
                        " share_type, share_class, kind, amount, paid_on)"
                        " VALUES (%s, %s, %s, 'Ordinária', '', %s, %s, %s)",
                        (fid, date(y, 1, 1), date(y, 12, 31), kind, amount, date(y + 1, 4, 30)),
                    )
        if fre_splits:
            fid = self.filing("FRE", cvm, date(2022, 1, 1), date(2022, 7, 15), version=3)
            for approved, before, after in fre_splits:
                c.execute(
                    "INSERT INTO fre_split (filing_id, event_type, approved_on, total_before,"
                    " total_after) VALUES (%s, 'Desdobramento', %s, %s, %s)",
                    (fid, approved, before, after),
                )
        sec = c.execute(
            "INSERT INTO security (ticker, isin, especi, short_name, first_date, last_date)"
            " VALUES (%s, %s, 'ON NM', %s, '2010-01-04', '2026-06-30') RETURNING id",
            (f"{ticker_root}3", f"BR{ticker_root}ACNOR0", ticker_root),
        ).fetchone()[0]
        days = [date(y, 12, 30) for y in YEARS]  # fechamento do fim de cada exercício
        for end in (date(2024, 12, 31), date(2025, 12, 31), TODAY):
            days += [d for i, d in enumerate(weekdays(end)) if i % every == 0]
        quotes = {d: (D("0.8"), 1) for d in set(days)}
        if split:  # (data, preço antes, preço depois)
            when, before, after = split
            for i in range(-2, 3):
                d = when + timedelta(days=i)
                if d.weekday() < 5:
                    quotes[d] = (before, 1) if d < when else (after, 2)
        for d, (close, dis) in quotes.items():
            c.execute(
                "INSERT INTO quote_daily VALUES (%s, %s, %s, %s, %s, %s, %s, 1, 1, %s, %s, %s)",
                (sec, d, close, close, close, close, close, volume, dis, self.sf),
            )
        c.commit()
        return sec

    def filing(self, doc_type, cvm, ref, received, has_lines=True, version=1):
        self.next_doc += 1
        return self.conn.execute(
            "INSERT INTO filing (doc_type, cvm_code, cnpj, reference_date, version, doc_id,"
            " received_date, source_file_id, has_lines) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
            " RETURNING id",
            (
                doc_type,
                cvm,
                f"{cvm:014d}",
                ref,
                version,
                self.next_doc,
                received,
                self.sf,
                has_lines,
            ),
        ).fetchone()[0]


def apply_fre_dividends(conn, cfg):
    """O que build_annual faz com o FRE, sem apagar as linhas sintéticas do mundo de teste."""
    for (cvm, end), (jcp, other, received) in compute._fre_dividends(conn, cfg).items():
        conn.execute(
            "UPDATE indicator_annual SET fre_jcp = %s, fre_dividends = %s, fre_available_from = %s"
            " WHERE cvm_code = %s AND reference_date = %s",
            (jcp, other, received, cvm, end),
        )
    conn.commit()


def run(conn, excluded=()):
    cfg = compute.load_config(conn)
    cfg["screen.snapshot_first_year"] = 2024
    cfg["screen.excluded_sectors"] = list(excluded)
    apply_fre_dividends(conn, cfg)
    compute.build_outliers(conn, cfg)
    compute.detect_events(conn, cfg)
    compute.build_company_events(conn, cfg)
    return compute.build_screens(conn, cfg, TODAY)


def status(conn, cvm, as_of):
    row = conn.execute(
        "SELECT status, data_base FROM screen_result WHERE cvm_code = %s AND as_of = %s",
        (cvm, as_of),
    ).fetchone()
    return row


def criterion(conn, cvm, as_of, name):
    return conn.execute(
        "SELECT status, value, detail FROM screen_criterion"
        " WHERE cvm_code = %s AND as_of = %s AND criterion = %s",
        (cvm, as_of, name),
    ).fetchone()


def drops(conn):
    return criterion(conn, 1, TODAY, "queda_dividendo_por_acao")[2]["drop_years"]


def test_empresa_saudavel_aprovada_e_ponto_no_tempo(conn):
    World(conn).company(1, "ABCD")
    out = run(conn)
    assert set(out["snapshots"]) == {"2024-12-31", "2025-12-31", "2026-06-30"}
    assert status(conn, 1, TODAY) == ("approved", date(2025, 12, 31))
    # Em 31/12/2025 a DFP 2025 ainda não tinha sido entregue (15/03/2026): o último é 2024.
    assert status(conn, 1, date(2025, 12, 31)) == ("approved", date(2024, 12, 31))
    assert status(conn, 1, date(2024, 12, 31)) == ("approved", date(2023, 12, 31))
    # cada critério guarda a fonte (filing) usada
    detail = criterion(conn, 1, TODAY, "roe_medio")[2]
    assert detail["filings"]
    row = conn.execute(
        "SELECT collected_at FROM screen_result WHERE cvm_code = 1 AND as_of = %s", (TODAY,)
    ).fetchone()
    assert row[0] is not None


def test_rodar_de_novo_nao_duplica(conn):
    World(conn).company(1, "ABCD")
    run(conn)
    n = conn.execute("SELECT count(*) FROM screen_criterion").fetchone()[0]
    run(conn)
    assert conn.execute("SELECT count(*) FROM screen_criterion").fetchone()[0] == n == 3 * 7


def test_retrato_de_hoje_substitui_o_anterior(conn):
    World(conn).company(1, "ABCD")
    run(conn)
    cfg = compute.load_config(conn)
    cfg["screen.snapshot_first_year"] = 2024
    compute.build_screens(conn, cfg, date(2026, 7, 15))
    dates = {r[0] for r in conn.execute("SELECT DISTINCT as_of FROM screen_result")}
    assert dates == {date(2024, 12, 31), date(2025, 12, 31), date(2026, 7, 15)}


def test_setor_excluido_e_reclassificacao_manual(conn):
    w = World(conn)
    w.company(1, "ABCD", sector="Bancos")
    w.company(2, "EFGH", sector="Energia")
    run(conn, excluded=["Bancos"])
    assert status(conn, 1, TODAY)[0] == "excluded"
    assert status(conn, 2, TODAY)[0] == "approved"
    review.set_class(conn, 2, "Bancos", None, "reclassificada")
    review.set_class(conn, 1, "Energia", None, "reclassificada")
    run(conn, excluded=["Bancos"])
    assert status(conn, 1, TODAY)[0] == "approved"
    assert status(conn, 2, TODAY)[0] == "excluded"


def test_liquidez_volume_e_presenca(conn):
    w = World(conn)
    w.company(1, "ABCD")
    w.company(2, "EFGH", volume=100_000)  # volume baixo
    w.company(3, "IJKL", every=2)  # presente em metade dos pregões
    run(conn)
    assert criterion(conn, 1, TODAY, "liquidez")[0] == "pass"
    assert criterion(conn, 2, TODAY, "liquidez")[0] == "fail"
    assert criterion(conn, 3, TODAY, "liquidez")[0] == "fail"
    assert status(conn, 2, TODAY)[0] == "rejected"


def test_sem_ticker_no_cadastro_liquidez_indisponivel(conn):
    w = World(conn)
    w.company(1, "ABCD")
    conn.execute("DELETE FROM company_security")
    conn.commit()
    run(conn)
    assert criterion(conn, 1, TODAY, "liquidez")[0] == "unavailable"
    assert status(conn, 1, TODAY)[0] == "insufficient_data"
    # override manual de raiz resolve
    review.set_ticker_root(conn, "abcd", 1, "teste")
    run(conn)
    assert criterion(conn, 1, TODAY, "liquidez")[0] == "pass"


def test_empresa_que_parou_de_entregar_dfp_fica_stale_hoje_mas_nao_no_passado(conn):
    World(conn).company(1, "ABCD", last_year=2023)  # última DFP: exercício 2023
    run(conn)
    assert status(conn, 1, TODAY) == ("stale", date(2023, 12, 31))  # 912 dias
    assert status(conn, 1, date(2024, 12, 31))[0] != "stale"  # dados do exercício 2023: 366 dias
    assert conn.execute(
        "SELECT count(*) FROM screen_criterion WHERE cvm_code = 1 AND as_of = %s", (TODAY,)
    ).fetchone() == (0,)


def burst(y):  # dividendos normais e 10x em 2025
    return (D(200), D(300)) if y == 2025 else (D(20), D(30))


def test_outlier_pendente_fica_fora_e_usuario_pode_liberar(conn):
    World(conn).company(1, "ABCD", dividends=burst)
    out = compute.build_outliers(conn, compute.load_config(conn))
    assert out == {"outliers": 1, "pending_review": 1}
    run(conn)
    assert conn.execute("SELECT ratio FROM dividend_outlier WHERE cvm_code = 1").fetchone()[0] == 10
    _, dy_excluded, detail = criterion(conn, 1, TODAY, "dy_medio_liquido")
    assert detail["outlier_years"] == [2025] and dy_excluded == D("47") / D("800")
    # usuário libera: o ano entra no histórico
    review.decide_outlier(conn, 1, date(2025, 12, 31), "include", "bonificação real")
    run(conn)
    _, dy_included, detail = criterion(conn, 1, TODAY, "dy_medio_liquido")
    assert detail["outlier_years"] == [] and dy_included > dy_excluded
    # volta para pendente
    review.decide_outlier(conn, 1, date(2025, 12, 31), "reset", None)
    run(conn)
    assert criterion(conn, 1, TODAY, "dy_medio_liquido")[2]["outlier_years"] == [2025]
    with pytest.raises(ValueError):
        review.decide_outlier(conn, 1, date(2020, 12, 31), "include", None)


def no_dva(y):  # a DVA zerada (caso Vale/Gerdau do diagnóstico)
    return (D(0), D(0))


def fre_pays(y):
    return [("Juros Sobre Capital Próprio", D(20)), ("Dividendo Obrigatório", D(30))]


def test_proventos_do_fre_substituem_a_dva_zerada(conn):
    World(conn).company(1, "ABCD", dividends=no_dva, fre_dividends=fre_pays)
    run(conn)
    row = conn.execute(
        "SELECT jcp, dividends, fre_jcp, fre_dividends, fre_available_from FROM indicator_annual"
        " WHERE cvm_code = 1 AND reference_date = '2024-12-31'"
    ).fetchone()
    assert row == (D(0), D(0), D(20), D(30), date(2025, 6, 15))
    c = criterion(conn, 1, TODAY, "proventos_todos_os_anos")
    assert c[0] == "pass" and set(c[2]["sources"].values()) == {"fre"}
    assert criterion(conn, 1, TODAY, "dy_medio_liquido")[1] == D("47") / D("800")
    assert status(conn, 1, TODAY)[0] == "approved"


def test_sem_fre_a_dva_zerada_reprova(conn):
    World(conn).company(1, "ABCD", dividends=no_dva)
    run(conn)
    assert criterion(conn, 1, TODAY, "proventos_todos_os_anos")[0] == "fail"


def test_fre_entregue_depois_da_data_base_nao_vale_naquela_data(conn):
    World(conn).company(1, "ABCD", dividends=no_dva, fre_dividends=fre_pays)
    # o FRE do exercício 2024 só foi entregue em 2026-03: em 31/12/2025 ainda não existia
    conn.execute(
        "UPDATE filing SET received_date = '2026-03-01' WHERE doc_type = 'FRE' AND version = 2"
        " AND reference_date = '2025-01-01'"
    )
    conn.commit()
    run(conn)
    ok = criterion(conn, 1, TODAY, "proventos_todos_os_anos")
    assert ok[0] == "pass"
    early = criterion(conn, 1, date(2025, 12, 31), "proventos_todos_os_anos")
    assert early[0] == "fail"  # 2024 voltou para a DVA zerada
    assert early[2]["sources"]["2024"] == "dva" and early[2]["sources"]["2023"] == "fre"


def test_dividendo_manual_vence_o_fre(conn):
    World(conn).company(1, "ABCD", dividends=no_dva, fre_dividends=fre_pays)
    conn.execute(
        "UPDATE indicator_annual SET jcp = 5, dividends = 5, dividends_source = 'manual'"
        " WHERE cvm_code = 1 AND reference_date = '2025-12-31'"
    )
    conn.commit()
    run(conn)
    assert criterion(conn, 1, TODAY, "proventos_todos_os_anos")[2]["sources"]["2025"] == "manual"


def post_split_shares(y):  # ações no fim do exercício: dobram em 2022
    return 1000 if y <= 2021 else 2000


def split_world(conn, **kw):
    w = World(conn)
    w.company(1, "ABCD", shares=post_split_shares, **kw)
    return w


def test_desdobramento_so_do_cotahist_vale_enquanto_nao_rejeitado(conn):
    split_world(conn, split=(date(2022, 6, 1), D("20"), D("10")))
    out = run(conn)
    assert conn.execute("SELECT factor, status FROM corporate_event").fetchall() == [
        (D("2"), "auto")
    ]
    assert out["suspected_events_pending"] == 0
    assert drops(conn) == []
    # Usuário rejeita o evento: sem ajuste, a queda de 2022 aparece
    eid = conn.execute("SELECT id FROM corporate_event").fetchone()[0]
    review.decide_event(conn, eid, "reject")
    run(conn)
    assert drops(conn) == [2022]
    # e a decisão sobrevive a nova detecção
    run(conn)
    assert conn.execute("SELECT status FROM corporate_event").fetchone() == ("rejected",)


def test_evento_do_fre_fixa_o_fator_e_o_salto_de_preco_a_data(conn):
    split_world(
        conn,
        split=(date(2022, 6, 1), D("20"), D("10")),
        fre_splits=[(date(2022, 5, 10), 1000, 2000)],
    )
    out = run(conn)
    rows = conn.execute(
        "SELECT event_date, factor, source, date_basis, known_from FROM company_event"
    ).fetchall()
    assert rows == [(date(2022, 6, 1), D(2), "fre", "cotahist", date(2022, 6, 1))]
    assert out["suspected_events_pending"] == 0 and drops(conn) == []
    # Rejeitar o salto de preço não tira o evento oficial: passa a valer a data de aprovação
    review.decide_event(
        conn, conn.execute("SELECT id FROM corporate_event").fetchone()[0], "reject"
    )
    run(conn)
    rows = conn.execute(
        "SELECT event_date, source, date_basis, known_from FROM company_event"
    ).fetchall()
    assert rows == [(date(2022, 5, 10), "fre", "approval", date(2022, 7, 15))]
    assert drops(conn) == []


def test_evento_suspeito_so_vale_depois_de_confirmado(conn):
    w = split_world(conn)
    sec = conn.execute("SELECT id FROM security").fetchone()[0]
    # salto de 50% sem mudança de DISMES: suspeito
    for d, close in ((date(2022, 5, 31), D("20")), (date(2022, 6, 1), D("10"))):
        conn.execute(
            "INSERT INTO quote_daily VALUES (%s, %s, %s, %s, %s, %s, %s, 1, 1, 1000, 1, %s)",
            (sec, d, close, close, close, close, close, w.sf),
        )
    conn.commit()
    out = run(conn)
    assert out["suspected_events_pending"] == 1
    assert drops(conn) == [2022]
    eid = conn.execute("SELECT id FROM corporate_event").fetchone()[0]
    review.decide_event(conn, eid, "confirm")
    run(conn)
    assert drops(conn) == []


def test_evento_manual_e_ticker_inexistente(conn):
    split_world(conn)
    review.add_event(conn, "ABCD3", date(2022, 6, 1), D(2), "bonificação não detectada")
    run(conn)
    assert drops(conn) == []
    assert conn.execute("SELECT source FROM company_event").fetchall() == [("manual",)]
    with pytest.raises(ValueError):
        review.add_event(conn, "ZZZZ3", date(2022, 6, 1), D(2), None)
    review.decide_event(conn, conn.execute("SELECT id FROM corporate_event").fetchone()[0], "reset")
    run(conn)
    assert conn.execute("SELECT count(*) FROM company_event").fetchone()[0] == 0


def test_sem_acoes_do_fre_valor_de_mercado_e_dps_indisponiveis(conn):
    World(conn).company(1, "ABCD")
    conn.execute("DELETE FROM fre_capital")
    conn.commit()
    run(conn)
    assert criterion(conn, 1, TODAY, "dy_medio_liquido")[0] == "unavailable"
    assert criterion(conn, 1, TODAY, "queda_dividendo_por_acao")[0] == "unavailable"
    assert status(conn, 1, TODAY)[0] == "insufficient_data"


def test_historico_curto_e_historico_insuficiente(conn):
    World(conn).company(1, "ABCD")
    conn.execute("DELETE FROM indicator_annual WHERE reference_date < '2022-01-01'")
    conn.commit()
    run(conn)
    assert status(conn, 1, TODAY)[0] == "insufficient_history"


def test_dois_eventos_do_fre_na_mesma_data_nao_quebram_a_gravacao(conn):
    # Falha real do Actions: UniqueViolation (cvm 8192, 16/10/2012) com a chave antiga
    split_world(conn, fre_splits=[(date(2022, 5, 10), 1000, 2000), (date(2022, 5, 10), 2000, 2200)])
    out = run(conn)
    rows = conn.execute("SELECT factor FROM company_event ORDER BY factor").fetchall()
    assert rows == [(D("1.1"),), (D(2),)]
    assert out["snapshots"]
