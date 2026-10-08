"""Índices (B3) e CDI (BCB): parsers contra linhas reais das respostas."""

import json
from datetime import date
from decimal import Decimal

from acoesb3 import benchmarks as bm
from conftest import fixture_bytes

D = Decimal


def test_parse_br_number():
    assert bm.parse_br_number("128.481,02") == D("128481.02")
    assert bm.parse_br_number("3.124,94") == D("3124.94")
    assert bm.parse_br_number("99,5") == D("99.5")


def test_b3_url_is_base64_of_the_real_request_payload():
    url = bm.b3_url("IBOVESPA", 2024)
    # Valor observado na chamada real (probe de 08/10/2026).
    assert url.endswith("eyJpbmRleCI6IklCT1ZFU1BBIiwibGFuZ3VhZ2UiOiJwdC1iciIsInllYXIiOiIyMDI0In0=")
    assert url.startswith(
        "https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetPortfolioDay/"
    )


def test_parse_b3_year_idiv_2012_sample():
    payload = json.loads(fixture_bytes("b3_idiv_2012_head.json"))
    rows = dict(bm.parse_b3_year(payload, 2012))
    # 1º de janeiro: feriado (sem valor); 2/1 é o primeiro pregão.
    assert date(2012, 1, 1) not in rows
    assert rows[date(2012, 1, 2)] == D("2933.23")
    assert rows[date(2012, 1, 3)] == D("2952.86")
    assert rows[date(2012, 2, 1)] == D("3124.94")
    assert rows[date(2012, 12, 3)] == D("3306.39")
    assert len(rows) == 23  # 6 + 8 + 9 células preenchidas nos dias 1, 2 e 3
    assert list(rows) == sorted(rows)


def test_parse_b3_year_ignores_impossible_dates():
    payload = {"results": [{"day": 30, "rateValue2": "10,00", "rateValue3": "11,00"}]}
    assert bm.parse_b3_year(payload, 2012) == [(date(2012, 3, 30), D("11.00"))]


def test_parse_bcb_cdi_sample_and_daily_rate():
    rows = bm.parse_bcb_json(fixture_bytes("bcb_sgs12_2012_head.json").decode())
    assert rows[0] == (date(2012, 1, 2), D("0.041028"))
    assert rows[-1] == (date(2012, 1, 10), D("0.040813"))
    rates = bm.cdi_daily_rates(rows)
    assert rates[date(2012, 1, 2)] == D("0.00041028")  # % ao dia -> fração


def test_cumulative_index_compounds_daily():
    rates = {date(2012, 1, 2): D("0.01"), date(2012, 1, 3): D("0.02")}
    idx = bm.cumulative_index(rates, base=D(100))
    assert idx[date(2012, 1, 2)] == D("101.00")
    assert idx[date(2012, 1, 3)] == D("103.0200")


def test_bcb_windows_stay_under_ten_years():
    w = bm.bcb_windows(date(2011, 1, 1), date(2026, 10, 8))
    assert w[0] == (date(2011, 1, 1), date(2019, 12, 31))
    assert w[1] == (date(2020, 1, 1), date(2026, 10, 8))
    assert all((b - a).days < 3653 for a, b in w)
    # sem lacunas nem sobreposição
    assert all((w[i + 1][0] - w[i][1]).days == 1 for i in range(len(w) - 1))


def test_bcb_url_format():
    url = bm.bcb_url(12, date(2012, 1, 2), date(2012, 12, 31))
    assert url == (
        "https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados"
        "?formato=json&dataInicial=02/01/2012&dataFinal=31/12/2012"
    )
