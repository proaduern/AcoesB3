"""Backtest: alocação, impostos e simulação, com números conferidos à mão."""

from datetime import date, timedelta
from decimal import Decimal

from acoesb3 import backtest as bt
from acoesb3.backtest import Candidate, Payment, PriceBook

D = Decimal

CFG = {
    "backtest.contribution": "1000",
    "backtest.sell_above_ratio": "1.2",
    "backtest.max_stocks_per_contribution": 3,
    "backtest.stock_cap": "0.10",
    "backtest.sector_cap": "0.30",
    "backtest.brokerage": "0",
    "backtest.b3_fee_schedule": [["2000-01-01", "0.0003"]],
    "backtest.cgt_rate": "0.15",
    "backtest.cgt_monthly_exemption": "20000",
    "backtest.cgt_offset_losses": True,
    "backtest.cash_earns_cdi": False,
    "backtest.exec_lag_days": 1,
    "tax.jcp": "0.15",
    "tax.dividend": "0",
}


def params(**kw):
    p = bt.BacktestParams.from_config(CFG, **{k: v for k, v in kw.items() if k.startswith("apply")})
    over = {k: v for k, v in kw.items() if not k.startswith("apply")}
    return bt.BacktestParams(**{**p.__dict__, **over})


def cand(company, ticker, ratio, sector="s", price="10", buy=True):
    return Candidate(company, ticker, sector, D(price), D(ratio) if ratio else None, buy)


# --- parâmetros e taxas -------------------------------------------------------------


def test_fee_schedule_picks_latest_rule_in_force():
    cfg = {**CFG, "backtest.b3_fee_schedule": [["2000-01-01", "0.0005"], ["2020-01-01", "0.0003"]]}
    p = bt.BacktestParams.from_config(cfg)
    assert p.fee_rate(date(2015, 5, 5)) == D("0.0005")
    assert p.fee_rate(date(2020, 1, 1)) == D("0.0003")
    assert p.fee_rate(date(1999, 1, 1)) == D("0")  # antes da primeira regra, sem taxa
    assert params(apply_costs=False).fee_rate(date(2020, 1, 1)) == 0


def test_fee_rate_adds_brokerage():
    p = params(brokerage=D("0.001"))
    assert p.fee_rate(date(2024, 1, 2)) == D("0.0013")


# --- limites só com posições suficientes -------------------------------------------------


def test_limits_active_needs_enough_positions():
    assert not bt.limits_active(9, D("0.10"))
    assert bt.limits_active(10, D("0.10"))
    assert not bt.limits_active(3, D("0.30"))
    assert bt.limits_active(4, D("0.30"))  # ceil(1/0,30) = 4


# --- alocação ---------------------------------------------------------------------------------


def test_allocate_splits_by_discount_among_best_three():
    buys = [cand(1, "AAAA3", "0.5"), cand(2, "BBBB3", "0.8"), cand(3, "CCCC3", "0.9"),
            cand(4, "DDDD3", "0.95")]  # fmt: skip
    # Uma quarta empresa já na carteira (9.000) deixa espaço de sobra: o alvo é 2.500 por empresa.
    out = bt.allocate(D(1000), buys, {9: D(9000)}, {9: "x"}, params())
    assert [a.ticker for a in out] == ["AAAA3", "BBBB3", "CCCC3"]  # a 4ª fica de fora (max 3)
    amounts = {a.ticker: a.amount for a in out}
    assert sum(amounts.values()) == D(1000)
    # descontos 0,5 / 0,2 / 0,1: partes 62,5% / 25% / 12,5%
    assert amounts["AAAA3"] == D(625)
    assert amounts["BBBB3"] == D(250)
    assert amounts["CCCC3"] == D(125)


def test_allocate_empty_portfolio_converges_to_equal_weights():
    buys = [cand(1, "AAAA3", "0.5"), cand(2, "BBBB3", "0.8"), cand(3, "CCCC3", "0.9")]
    out = bt.allocate(D(900), buys, {}, {}, params())
    assert {a.amount for a in out} == {D(300)}  # alvo = 900 / 3: o desconto não passa do alvo


def test_allocate_skips_companies_at_or_above_target_weight():
    # Carteira de 1.000 em AAAA; aporte de 1.000; N = 2 empresas -> alvo = 1.000 cada.
    buys = [cand(1, "AAAA3", "0.5"), cand(2, "BBBB3", "0.9")]
    out = bt.allocate(D(1000), buys, {1: D(1000)}, {1: "s"}, params())
    assert [a.ticker for a in out] == ["BBBB3"]
    assert out[0].amount == D(1000)


def test_allocate_caps_at_room_to_target_and_redistributes():
    # N = 2, total = 1.600 (cash 1.000 + 600 em AAAA), alvo = 800.
    # BBBB (desconto maior) tem espaço 800; sobra 200 vai para AAAA (espaço 200).
    buys = [cand(1, "AAAA3", "0.9"), cand(2, "BBBB3", "0.1")]
    out = bt.allocate(D(1000), buys, {1: D(600)}, {1: "s"}, params())
    got = {a.ticker: a.amount for a in out}
    assert got == {"BBBB3": D(800), "AAAA3": D(200)}


def test_allocate_leaves_cash_beyond_room_unspent():
    # Duas empresas de 1.000; caixa 500; total 2.500; alvo 1.250: só 250 cabem na candidata.
    held = {1: D(1000), 2: D(1000)}
    out = bt.allocate(D(500), [cand(1, "AAAA3", "0.5")], held, {1: "s", 2: "t"}, params())
    assert [(a.ticker, a.amount) for a in out] == [("AAAA3", D(250))]


def test_stock_cap_applies_only_with_ten_positions():
    # 1 posição existente + 1 candidata: o teto de 10% não vale e a candidata recebe tudo.
    out = bt.allocate(D(1000), [cand(2, "BBBB3", "0.5")], {1: D(1000)}, {1: "s"}, params())
    assert out[0].amount == D(1000)

    # Com 10 empresas, o teto de 10% vale: 9 posições de 1.000 + candidata nova; total 10.000.
    held = {c: D(1000) for c in range(1, 10)}
    sectors = {c: f"s{c}" for c in range(1, 10)}
    out = bt.allocate(D(1000), [cand(10, "ZZZZ3", "0.5", sector="s10")], held, sectors, params())
    assert out[0].amount == D(1000)  # 10% de 10.000 = 1.000: cabe exatamente
    out = bt.allocate(
        D(1000),
        [cand(10, "ZZZZ3", "0.5", sector="s10")],
        held,
        sectors,
        params(stock_cap=D("0.05")),
    )
    # Teto de 5% exige 20 posições; só há 10, portanto não vale.
    assert out[0].amount == D(1000)


def test_sector_cap_limits_one_sector_when_enough_sectors():
    # 4 setores (teto 30% vale). Setor "e" já tem 2.000 de 10.000 (+1.000 de aporte = 11.000...).
    held = {1: D(2000), 2: D(2000), 3: D(2000), 4: D(2000)}
    sectors = {1: "e", 2: "f", 3: "g", 4: "h"}
    buys = [cand(5, "NNNN3", "0.3", sector="e"), cand(6, "MMMM3", "0.9", sector="f")]
    out = bt.allocate(D(1000), buys, held, sectors, params(stock_cap=D("0.50")))
    got = {a.ticker: a.amount for a in out}
    total = D(9000)
    # 'e' não pode passar de 30% de 9.000 = 2.700: com 2.000 já, cabem 700.
    assert got["NNNN3"] <= D(700)
    assert sum(got.values()) <= D(1000)
    assert total * D("0.30") >= D(2000) + got["NNNN3"]


# --- impostos ------------------------------------------------------------------------------------


def test_tax_exempt_when_monthly_sales_within_limit():
    st = bt.TaxState()
    assert bt.monthly_tax(st, D(20000), D(5000), params()) == 0
    assert st.loss_carry == 0


def test_tax_exempt_month_loss_still_accumulates():
    st = bt.TaxState()
    assert bt.monthly_tax(st, D(10000), D(-300), params()) == 0
    assert st.loss_carry == D(300)


def test_tax_above_limit_is_15_percent_of_gain_net_of_carried_loss():
    st = bt.TaxState(loss_carry=D(1000))
    tax = bt.monthly_tax(st, D(30000), D(5000), params())
    assert tax == D("600")  # (5.000 - 1.000) x 15%
    assert st.loss_carry == 0


def test_tax_above_limit_with_loss_larger_than_gain_carries_the_rest():
    st = bt.TaxState(loss_carry=D(1000))
    assert bt.monthly_tax(st, D(30000), D(400), params()) == 0
    assert st.loss_carry == D(600)


def test_exempt_gain_does_not_consume_carried_loss():
    st = bt.TaxState(loss_carry=D(1000))
    assert bt.monthly_tax(st, D(15000), D(3000), params()) == 0
    assert st.loss_carry == D(1000)


def test_tax_switched_off():
    st = bt.TaxState()
    assert bt.monthly_tax(st, D(50000), D(9000), params(apply_taxes=False)) == 0


# --- simulação -----------------------------------------------------------------------------------


def calendar(start, n):
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def flat_book(days, prices):
    """prices: ticker -> {data: preço} ou preço fixo."""
    series = {}
    for t, px in prices.items():
        series[t] = [(d, D(px[d] if isinstance(px, dict) else px)) for d in days]
    return PriceBook(series)


def test_buys_whole_shares_at_next_close_and_cota_reflects_fee_only():
    days = calendar(date(2024, 1, 2), 5)
    book = flat_book(days, {"AAAA3": "10"})
    signals = {days[0]: [cand(1, "AAAA3", "0.5", price="10")]}
    r = bt.simulate(params(), days, signals, book, {}, {}, {}, 10)
    buy = r.trades[0]
    # Ordem no pregão seguinte ao do sinal. 1.000 / (10 x 1,0003) = 99,97 -> 99 ações.
    assert (buy.day, buy.side, buy.qty) == (days[1], "buy", D(99))
    assert buy.fee == D(99) * D(10) * D("0.0003")
    assert r.invested == D(1000)
    # Sem variação de preço, a cota só perde a taxa.
    assert r.cota[days[1]] < 1.0
    assert abs(r.cota[days[1]] - (1000 - 0.297) / 1000) < 1e-9
    # Caixa que sobrou (1.000 - 990 - 0,297) permanece, sem rendimento (cash_earns_cdi falso).
    assert r.final_positions == {"AAAA3": D(99)}


def test_no_costs_gives_cota_exactly_one_when_price_flat():
    days = calendar(date(2024, 1, 2), 6)
    book = flat_book(days, {"AAAA3": "10"})
    signals = {days[0]: [cand(1, "AAAA3", "0.5")]}
    r = bt.simulate(params(apply_costs=False), days, signals, book, {}, {}, {}, 10)
    assert all(abs(v - 1.0) < 1e-12 for v in r.cota.values())


def test_cota_is_time_weighted_not_distorted_by_contributions():
    days = calendar(date(2024, 1, 2), 8)
    prices = {d: ("10" if i < 4 else "20") for i, d in enumerate(days)}
    book = flat_book(days, {"AAAA3": prices})
    # Dois aportes: um no pregão 1 (preço 10) e outro no 5 (preço 20, depois da alta).
    signals = {
        days[0]: [cand(1, "AAAA3", "0.5", price="10")],
        days[4]: [cand(1, "AAAA3", "0.5", price="20")],
    }
    r = bt.simulate(params(apply_costs=False), days, signals, book, {}, {}, {}, 10)
    # Preço dobrou: a cota dobra, com o 2º aporte entrando a 20 sem inflar o retorno.
    assert abs(r.cota[days[3]] - 1.0) < 1e-12
    assert abs(r.cota[days[5]] - 2.0) < 1e-12
    assert abs(r.cota[days[7]] - 2.0) < 1e-12


def test_split_event_multiplies_quantity_and_keeps_value():
    days = calendar(date(2024, 1, 2), 8)
    prices = {d: ("10" if i < 4 else "5") for i, d in enumerate(days)}
    book = flat_book(days, {"AAAA3": prices})
    signals = {days[0]: [cand(1, "AAAA3", "0.5")]}
    events = {1: [(days[4], D(2))]}
    r = bt.simulate(params(apply_costs=False), days, signals, book, events, {}, {}, 10)
    assert r.final_positions["AAAA3"] == D(200)
    assert all(abs(v - 1.0) < 1e-12 for v in r.cota.values())


def test_dividend_and_jcp_are_credited_net_of_withholding():
    days = calendar(date(2024, 1, 2), 8)
    book = flat_book(days, {"AAAA3": "10"})
    signals = {days[0]: [cand(1, "AAAA3", "0.5")]}
    pays = {1: [Payment(days[4], D("0.50"), D("0.20"))]}
    r = bt.simulate(params(apply_costs=False), days, signals, book, {}, pays, {}, 10)
    # 100 ações x (0,50 x 1 + 0,20 x 0,85) = 67
    assert r.dividends == D(67)
    assert abs(r.cota[days[4]] - 1.067) < 1e-9


def test_sells_whole_position_above_ceiling_ratio_and_pays_tax():
    days = calendar(date(2024, 1, 2), 40)
    # Aporte alto para passar do limite de isenção de R$ 20 mil na venda.
    big = params(apply_costs=False, contribution=D(30000))
    prices = {d: ("10" if i < 25 else "20") for i, d in enumerate(days)}
    book = flat_book(days, {"AAAA3": prices})
    signals = {
        days[0]: [cand(1, "AAAA3", "0.5", price="10")],
        days[24]: [cand(1, "AAAA3", "1.3", price="10", buy=False)],  # razão 1,3 > 1,2: vende
    }
    r = bt.simulate(big, days, signals, book, {}, {}, {}, 10)
    sells = [t for t in r.trades if t.side == "sell"]
    assert len(sells) == 1 and sells[0].qty == D(3000)
    assert sells[0].day == days[25]
    # Ganho = 3.000 x (20 - 10) = 30.000; vendas 60.000 > 20.000; imposto 15% = 4.500.
    assert sells[0].tax == D(4500)
    assert r.taxes == D(4500)
    assert r.final_positions == {}


def test_hold_between_ceiling_and_sell_ratio():
    days = calendar(date(2024, 1, 2), 10)
    book = flat_book(days, {"AAAA3": "10"})
    signals = {
        days[0]: [cand(1, "AAAA3", "0.5")],
        days[5]: [cand(1, "AAAA3", "1.1", buy=False)],  # 'manter': nem compra nem vende
    }
    r = bt.simulate(params(apply_costs=False), days, signals, book, {}, {}, {}, 10)
    # Razão 1,1 (manter): o 2º mês nem compra (não é 'buy') nem vende.
    assert [t.side for t in r.trades] == ["buy"]
    assert r.final_positions == {"AAAA3": D(100)}


def test_cash_earns_cdi_when_enabled():
    days = calendar(date(2024, 1, 2), 5)
    book = flat_book(days, {"AAAA3": "2000"})  # ação cara demais: não compra nada
    signals = {days[0]: [cand(1, "AAAA3", "0.5", price="2000")]}
    cdi = {d: D("0.001") for d in days}
    r = bt.simulate(
        params(apply_costs=False, cash_earns_cdi=True), days, signals, book, {}, {}, cdi, 10
    )
    assert r.final_positions == {}
    # 1.000 em caixa no pregão 1 renderam 0,1% nos 3 pregões seguintes.
    last = r.nav[days[-1]]
    assert abs(float(last) - 1000 * 1.001**3) < 1e-6


def test_no_signal_no_trades():
    days = calendar(date(2024, 1, 2), 5)
    book = flat_book(days, {"AAAA3": "10"})
    r = bt.simulate(params(), days, {}, book, {}, {}, {}, 10)
    assert r.trades == [] and r.cota == {} and r.invested == 0


# --- proventos por exercício ----------------------------------------------------------------------

REF = date(2020, 12, 31)


def pays_for(
    shares, jcp, div, filing, lines=(), events=(), timing="fre_dates_else_filing", ref=REF
):
    return bt.payments_for_year(ref, shares, jcp, div, filing, list(lines), list(events), timing)


def test_payments_follow_fre_dates_proportionally():
    lines = [
        (False, D(300), date(2020, 6, 1)),
        (False, D(700), date(2021, 3, 1)),
        (True, D(100), date(2020, 12, 1)),
    ]
    pays = pays_for(1000, D(80), D(500), date(2021, 3, 20), lines)
    got = {p.pay_date: (p.dividend, p.jcp) for p in pays}
    # dividendos 500 repartidos 30% / 70% por 1.000 ações; JCP 80 inteiro em 1/12
    assert got[date(2020, 6, 1)] == (D("0.15"), D(0))
    assert got[date(2021, 3, 1)] == (D("0.35"), D(0))
    assert got[date(2020, 12, 1)] == (D(0), D("0.08"))


def test_payments_without_fre_fall_back_to_filing_date():
    pays = pays_for(100, D(10), D(90), date(2026, 3, 20), ref=date(2025, 12, 31))
    assert pays == [Payment(date(2026, 3, 20), D("0.9"), D("0.1"))]


def test_payments_lines_without_date_use_filing_date():
    pays = pays_for(10, D(0), D(50), date(2021, 3, 20), [(False, D(100), None)])
    assert pays == [Payment(date(2021, 3, 20), D(5), D(0))]


def test_payments_filing_timing_ignores_fre_dates():
    lines = [(False, D(100), date(2020, 6, 1))]
    pays = pays_for(10, D(0), D(50), date(2021, 3, 20), lines, timing="filing")
    assert [p.pay_date for p in pays] == [date(2021, 3, 20)]


def test_payments_none_timing_and_missing_inputs():
    assert pays_for(10, D(0), D(50), date(2021, 3, 20), timing="none") == []
    assert pays_for(None, D(0), D(50), date(2021, 3, 20), timing="filing") == []
    assert pays_for(10, None, D(50), date(2021, 3, 20), timing="filing") == []


def test_payments_adjusted_for_split_between_exercise_end_and_payment():
    # Desdobramento 2:1 em 01/02/2021; pagamento em 01/03/2021: o valor por ação cai à metade.
    pays = pays_for(100, D(0), D(100), date(2021, 3, 1), events=[(date(2021, 2, 1), D(2))],
                    timing="filing")  # fmt: skip
    assert pays[0].dividend == D("0.5")  # 100 / (100 ações x 2)


def test_sector_cap_is_shared_by_companies_of_the_same_sector():
    # 4 setores (limite de 30% vale). Dois candidatos do setor 'e' dividem o espaço do setor.
    held = {1: D(2000), 2: D(2000), 3: D(2000)}
    sectors = {1: "f", 2: "g", 3: "h"}
    buys = [cand(4, "AAAA3", "0.2", sector="e"), cand(5, "BBBB3", "0.3", sector="e")]
    out = bt.allocate(D(1000), buys, held, sectors, params(stock_cap=D("0.50")))
    total = D(7000)
    assert sum(a.amount for a in out) <= total * D("0.30")
    assert sum(a.amount for a in out) > 0
