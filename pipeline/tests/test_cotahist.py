from datetime import date
from decimal import Decimal

import pytest

from acoesb3.cotahist import iter_lines, parse_line, select_quotes
from conftest import fixture_bytes


def lines(name):
    return list(iter_lines(fixture_bytes(name)))


def by_ticker(name, ticker, day):
    for ln in lines(name):
        q = parse_line(ln)
        if q and q.ticker == ticker and q.trade_date == day:
            return q
    raise AssertionError(f"{ticker} {day} não encontrado")


def test_petr4_2024_valores_conferidos():
    q = by_ticker("COTAHIST_A2024_A2010_A1986_sample.txt", "PETR4", date(2024, 1, 2))
    assert q.close == Decimal("37.78")
    assert q.open == Decimal("37.44")
    assert q.avg == Decimal("37.66")
    assert q.quantity == 24_043_800
    assert q.volume == Decimal("905513838.00")
    assert q.trades == 39280
    assert q.especi == "PN N2"
    assert q.isin == "BRPETRACNPR6"
    assert q.quote_factor == 1
    assert q.codbdi == "02" and q.market_type == "010"
    # volume = preço médio × quantidade (confere posições dos campos)
    assert abs(q.avg * q.quantity - q.volume) / q.volume < Decimal("0.001")


def test_unit_taee11():
    q = by_ticker("COTAHIST_A2024_A2010_A1986_sample.txt", "TAEE11", date(2024, 1, 2))
    assert q.especi == "UNT N2"
    assert q.close == Decimal("38.13")


def test_fatcot_1000_preco_por_lote_de_mil():
    q = by_ticker("COTAHIST_A2010_sample.TXT", "CBEE3", date(2010, 1, 4))
    assert q.quote_factor == 1000
    # preço por ação = preço do lote / 1000 (o carregador faz a divisão)
    assert q.close / q.quote_factor < q.close


def test_header_e_trailer_ignorados():
    ls = lines("COTAHIST_A2010_sample.TXT")
    assert ls[0].startswith("00COTAHIST")
    assert parse_line(ls[0]) is None
    assert parse_line(ls[-1]) is None


def test_linha_curta_falha():
    with pytest.raises(ValueError):
        parse_line("01" + "0" * 100)


STOCKS = {"ACN", "UNT", "CDA"}


def test_filtro_codbdi_e_mercado():
    qs = list(select_quotes(lines("COTAHIST_A2010_sample.TXT"), {"02"}, {"010"}, STOCKS))
    tickers = {q.ticker for q in qs}
    assert {"PETR4", "WEGE3", "CBEE3"} <= tickers
    assert "ABCB4F" not in tickers  # fracionário (020 / BDI 96) fica fora


def test_bdr_com_codbdi_02_fica_fora():
    # Em 2021 a B3 marcou BDRs (ex.: A1AP34, ESPECI DRN) com CODBDI 02, igual às ações
    ls = lines("COTAHIST_A2024_A2010_A1986_sample.txt")
    bdr = next(parse_line(ln) for ln in ls if ln[12:24].strip() == "A1AP34")
    assert bdr.codbdi == "02" and bdr.especi == "DRN"
    tickers = {q.ticker for q in select_quotes(ls, {"02"}, {"010"}, STOCKS)}
    assert "A1AP34" not in tickers
    assert {"PETR4", "TAEE11", "EQMA3B"} <= tickers  # ação, unit (ISIN CDA) e ação 3B
