"""Preço teto: funções puras, com números conferidos à mão."""

from datetime import date
from decimal import Decimal

import pytest

from acoesb3 import ceiling
from acoesb3.screen import YearData

D = Decimal

CFG = {
    "ceiling.bazin_rate": "0.06",
    "ceiling.dividend_years": 5,
    "ceiling.graham_multiplier": "22.5",
    "ceiling.lpa_years": 3,
    "ceiling.gordon_k": "0.12",
    "ceiling.gordon_growth_years": 5,
    "ceiling.gordon_g_min": "0",
    "ceiling.gordon_g_max": "0.05",
    "ceiling.gordon_min_spread": "0.03",
    "ceiling.multiple_years": 10,
    "ceiling.multiple_min_years": 3,
    "ceiling.k_by_methods": {"3": 2, "4": 3, "5": 3},
    "ceiling.band_strong": "0.8",
    "ceiling.band_buy": "1.0",
    "ceiling.band_hold": "1.2",
    "ceiling.price_max_age_days": 10,
    "ceiling.financial_plans": ["banco", "seguradora"],
    "outlier.min_valid_years": 3,
    "tax.jcp": "0.15",
    "tax.dividend": "0",
}
P = ceiling.CeilingParams.from_config(CFG)


def year(y, **kw):
    kw.setdefault("shares", 1000)
    return YearData(
        year=y, reference_date=date(y, 12, 31), filing_id=y, received_date=date(y + 1, 3, 1), **kw
    )


def divs(values, jcp=False, **kw):
    """Exercícios 2020..2024 com dividendos (ou JCP) dados, em R$ totais."""
    return {
        2020 + i: year(
            2020 + i,
            jcp=D(v) if jcp else D(0),
            dividends=D(0) if jcp else D(v),
            **kw,
        )
        for i, v in enumerate(values)
    }


# --- Bazin ------------------------------------------------------------------


def test_bazin_dividendo_liquido_por_acao_sobre_seis_por_cento():
    # JCP de 100 por ano, 1.000 ações: líquido 100 x 0,85 = 85 -> R$ 0,085 por ação -> / 0,06
    r = ceiling.bazin(divs([100] * 5, jcp=True), 2024, P)
    assert r.status == "ok"
    assert r.value == D("0.085") / D("0.06")


def test_bazin_dividendo_sem_imposto_vale_o_bruto():
    r = ceiling.bazin(divs([60] * 5), 2024, P)
    assert r.value == D("1")  # 0,06 por ação / 0,06


def test_bazin_leva_o_dividendo_a_base_de_acoes_da_data_base():
    # desdobramento 1:2 depois do exercício: o dobro de ações, dividendo por ação cai à metade
    years = divs([60] * 5, shares_factor=D(2))
    assert ceiling.bazin(years, 2024, P).value == D("0.5")


def test_bazin_ano_de_outlier_sai_da_media():
    years = divs([60, 60, 6000, 60, 60])
    years[2022].outlier = True
    r = ceiling.bazin(years, 2024, P)
    assert r.value == D("1") and r.inputs["outlier_years"] == [2022]


def test_bazin_poucos_anos_validos_fica_indisponivel():
    years = divs([60] * 5)
    for k in (2020, 2021, 2022):
        years[k].outlier = True
    r = ceiling.bazin(years, 2024, P)
    assert r.status == "unavailable" and r.value is None


def test_bazin_exercicio_faltando_fica_indisponivel_com_o_ano():
    years = divs([60] * 5)
    del years[2022]
    r = ceiling.bazin(years, 2024, P)
    assert r.status == "unavailable" and r.inputs["missing_years"] == [2022]


def test_bazin_sem_acoes_ou_sem_provento_fica_indisponivel_nunca_zero():
    years = divs([60] * 5)
    years[2023].shares = None
    assert ceiling.bazin(years, 2024, P).status == "unavailable"
    years = divs([60] * 5)
    years[2023].jcp = None
    assert ceiling.bazin(years, 2024, P).status == "unavailable"


def test_bazin_sem_dividendo_fica_indisponivel():
    assert ceiling.bazin(divs([0] * 5), 2024, P).status == "unavailable"


# --- Gordon -----------------------------------------------------------------


def test_gordon_com_crescimento_de_cinco_por_cento():
    years = divs(["1000", "1050", "1102.5", "1157.625", "1215.50625"])
    r = ceiling.gordon(years, 2024, P)
    assert r.status == "ok"
    mean = D("5.52563125") / 5  # dividendos por ação 1; 1,05; ...
    assert r.inputs["g"] == "0.05" or abs(D(r.inputs["g"]) - D("0.05")) < D("1e-20")
    assert abs(r.value - mean * D("1.05") / D("0.07")) < D("1e-15")


def test_gordon_crescimento_acima_do_limite_fica_no_limite():
    years = divs([1000, 1000, 1000, 1000, 2000])  # g ~ 18,9% a.a.
    r = ceiling.gordon(years, 2024, P)
    assert D(r.inputs["g"]) == D("0.05") and D(r.inputs["g_raw"]) > D("0.18")
    assert r.value == D("1.2") * D("1.05") / D("0.07")  # média por ação 1,2


def test_gordon_crescimento_negativo_vira_zero():
    years = divs([2000, 1500, 1200, 1100, 1000])
    r = ceiling.gordon(years, 2024, P)
    assert D(r.inputs["g"]) == 0 and D(r.inputs["g_raw"]) < 0
    assert r.value == D("1.36") * 1 / D("0.12")  # média (2+1,5+1,2+1,1+1)/5 = 1,36


def test_gordon_usa_o_dividendo_total_e_nao_o_por_acao():
    # mesmas pontas em R$, mas o número de ações dobra: o DPS cai, o crescimento (total) não
    years = divs([1000, 1000, 1000, 1000, 1050])
    for y in years.values():
        y.shares_factor = D(1)
    years[2024].shares = 2000
    r = ceiling.gordon(years, 2024, P)
    assert abs(D(r.inputs["g_raw"]) - (D("1.05") ** (D(1) / 4) - 1)) < D("1e-20")


def test_gordon_spread_curto_exclui_o_metodo():
    p = ceiling.CeilingParams.from_config({**CFG, "ceiling.gordon_k": "0.07"})
    years = divs(["1000", "1050", "1102.5", "1157.625", "1215.50625"])
    r = ceiling.gordon(years, 2024, p)  # k - g = 0,02 < 0,03
    assert r.status == "excluded"


def test_gordon_ponta_de_outlier_ou_sem_pagamento_fica_indisponivel():
    years = divs([1000] * 5)
    years[2024].outlier = True
    assert ceiling.gordon(years, 2024, P).status == "unavailable"
    years = divs([0, 1000, 1000, 1000, 1000])
    assert ceiling.gordon(years, 2024, P).status == "unavailable"


# --- Graham -----------------------------------------------------------------


def graham_years():
    return {
        2022: year(2022, profit=D(1000), equity=D(5000)),
        2023: year(2023, profit=D(2000), equity=D(6500)),
        2024: year(2024, profit=D(3000), equity=D(8000)),
    }


def test_graham_raiz_de_22_5_x_lpa_medio_x_vpa():
    # LPA 1, 2, 3 -> média 2; VPA 8; raiz de 22,5 x 2 x 8 = raiz de 360
    r = ceiling.graham(graham_years(), 2024, "comum", P)
    assert r.status == "ok"
    assert abs(r.value - D("18.97366596101027598")) < D("1e-12")


def test_graham_vpa_leva_a_base_de_acoes_da_data_base():
    years = graham_years()
    for y in years.values():
        y.shares_factor = D(2)  # dobro de ações: LPA e VPA caem à metade, raiz cai à metade
    r = ceiling.graham(years, 2024, "comum", P)
    assert abs(r.value - D("18.97366596101027598") / 2) < D("1e-12")


@pytest.mark.parametrize("plan", ["banco", "seguradora"])
def test_graham_exclui_banco_e_seguradora(plan):
    assert ceiling.graham(graham_years(), 2024, plan, P).status == "excluded"


def test_graham_lpa_ou_vpa_nao_positivo_exclui():
    years = graham_years()
    years[2024].equity = D(-10)
    assert ceiling.graham(years, 2024, "comum", P).status == "excluded"
    years = graham_years()
    for y in years.values():
        y.profit = D(-100)
    assert ceiling.graham(years, 2024, "comum", P).status == "excluded"


def test_graham_sem_plano_ou_sem_dado_fica_indisponivel():
    assert ceiling.graham(graham_years(), 2024, None, P).status == "unavailable"
    years = graham_years()
    years[2023].profit = None
    assert ceiling.graham(years, 2024, "comum", P).status == "unavailable"
    years = graham_years()
    years[2024].equity = None
    assert ceiling.graham(years, 2024, "comum", P).status == "unavailable"


# --- Múltiplos --------------------------------------------------------------


def multiple_years():
    caps = {2020: 5000, 2021: 8000, 2022: 10000, 2023: 24000, 2024: 60000}
    profit = {2020: -500, 2021: 1000, 2022: 1000, 2023: 2000, 2024: 3000}
    return {y: year(y, profit=D(profit[y]), equity=D(10000), market_cap=D(caps[y])) for y in caps}


def test_multiplos_pl_mediano_vezes_lpa_medio_de_tres_anos():
    # P/L: 2020 prejuízo (fora), 8, 10, 12, 20 -> mediana 11; LPA 2022-2024 = (1+2+3)/3 = 2
    r = ceiling.multiples(multiple_years(), 2024, "comum", P)
    assert r.status == "ok" and r.inputs["kind"] == "P/L"
    assert r.inputs["skipped"] == {"2020": "prejuízo"} or r.inputs["skipped"] == {2020: "prejuízo"}
    assert r.value == D("22")


def test_multiplos_banco_usa_pvp_mediano_vezes_vpa():
    years = {
        y: year(y, profit=D(1), equity=D(10000), market_cap=D(c))
        for y, c in {2022: 10000, 2023: 12000, 2024: 14000}.items()
    }
    # P/VP 1,0 / 1,2 / 1,4 -> mediana 1,2; VPA 10
    r = ceiling.multiples(years, 2024, "banco", P)
    assert r.status == "ok" and r.inputs["kind"] == "P/VP"
    assert r.value == D("12")


def test_multiplos_usa_so_a_janela_de_dez_anos():
    years = {
        y: year(y, profit=D(1000), equity=D(1), market_cap=D(1000 * (y - 2000)))
        for y in range(2000, 2025)
    }
    r = ceiling.multiples(years, 2024, "comum", P)
    assert len(r.inputs["ratios"]) == 10  # 2015..2024, mediana de 15..24 = 19,5
    assert r.value == D("19.5") * D(1)  # LPA médio = 1


def test_multiplos_poucos_anos_validos_ou_sem_mercado_ficam_indisponiveis():
    years = {2024: year(2024, profit=D(1000), equity=D(1), market_cap=D(10000))}
    assert ceiling.multiples(years, 2024, "comum", P).status == "unavailable"
    years = multiple_years()
    for y in years.values():
        y.market_cap = None
    assert ceiling.multiples(years, 2024, "comum", P).status == "unavailable"


# --- Consolidação, votos e faixas -------------------------------------------


def ok(method, v):
    return ceiling.MethodResult(method, "ok", D(v))


def test_consolidacao_mediana_e_k_pela_quantidade_de_metodos():
    three = [ok("bazin", 10), ok("gordon", 20), ok("multiples", 30)]
    c = ceiling.consolidate(three, P)
    assert (c.status, c.ceiling, c.methods_ok, c.k_required) == ("ok", D(20), 3, 2)
    four = [*three, ok("graham", 40)]
    c = ceiling.consolidate(four, P)
    assert (c.ceiling, c.k_required) == (D(25), 3)  # mediana de 10, 20, 30, 40
    five = [*four, ok("dcf", 50)]
    c = ceiling.consolidate(five, P)
    assert (c.ceiling, c.k_required) == (D(30), 3)


def test_consolidacao_ignora_metodos_excluidos_e_indisponiveis():
    methods = [
        ok("bazin", 10),
        ok("gordon", 20),
        ceiling.MethodResult("graham", "excluded", None, "banco"),
        ceiling.MethodResult("multiples", "unavailable", None, "sem dado"),
    ]
    c = ceiling.consolidate(methods, P)
    assert c.status == "insufficient" and c.methods_ok == 2 and c.k_required is None
    assert c.ceiling == D(15)  # continua visível, mas fora da compra


@pytest.mark.parametrize(
    "ratio,band",
    [
        ("0.79", "strong_buy"),
        ("0.80", "buy"),
        ("0.99", "buy"),
        ("1.00", "hold"),
        ("1.20", "hold"),
        ("1.21", "expensive"),
    ],
)
def test_faixas_nos_limites(ratio, band):
    assert ceiling.band_for(D(ratio), P) == band


def test_compra_exige_preco_abaixo_da_mediana_e_de_k_metodos():
    methods = [ok("bazin", 20), ok("gordon", 30), ok("graham", 40), ok("multiples", 50)]
    cons = ceiling.consolidate(methods, P)  # mediana 35, K = 3
    v = ceiling.value_class("XXXX3", "on", 1, D(29), date(2026, 10, 5), methods, cons, P)
    assert v.ceiling == D(35) and v.votes == 3 and v.buy  # 30, 40, 50 acima de 29
    assert v.band == "buy" and v.ratio == D(29) / D(35)
    # preço abaixo da mediana, mas só 2 métodos acima: sem compra
    methods = [ok("bazin", 10), ok("gordon", 20), ok("graham", 30), ok("multiples", 40)]
    cons = ceiling.consolidate(methods, P)  # mediana 25, K = 3
    v = ceiling.value_class("XXXX3", "on", 1, D(24), date(2026, 10, 5), methods, cons, P)
    assert v.votes == 2 and v.price < v.ceiling and not v.buy


def test_preco_acima_do_teto_nao_e_compra_e_cai_na_faixa_cara():
    methods = [ok("bazin", 10), ok("gordon", 20), ok("multiples", 30)]
    cons = ceiling.consolidate(methods, P)
    v = ceiling.value_class("XXXX3", "on", 1, D(30), date(2026, 10, 5), methods, cons, P)
    assert not v.buy and v.band == "expensive" and v.votes == 0


def test_dados_insuficientes_nunca_e_compra():
    methods = [ok("bazin", 100), ok("gordon", 100)]
    cons = ceiling.consolidate(methods, P)
    v = ceiling.value_class("XXXX3", "on", 1, D(10), date(2026, 10, 5), methods, cons, P)
    assert not v.buy and v.ceiling == D(100) and v.band == "strong_buy"


def test_unit_vale_a_soma_das_acoes_da_composicao():
    # TAEE11 = 1 ON + 2 PN: três ações, cada uma com o mesmo valor por ação
    methods = [ok("bazin", 10), ok("gordon", 20), ok("multiples", 30)]
    cons = ceiling.consolidate(methods, P)
    v = ceiling.value_class("TAEE11", "unit", 3, D(50), date(2026, 10, 5), methods, cons, P)
    assert v.ceiling == D(60) and v.votes == 2 and v.buy  # 60 e 90 acima de 50; 30 abaixo


@pytest.mark.parametrize(
    "text,total",
    [
        ("1 ON / 2 PN", 3),
        ("1 ON + 2 PNA", 3),
        ("1 ON e 4 PNB", 5),
        ("1 ON / 1 PNA / 1 PNB", 3),
        ("", None),
        (None, None),
        ("ver regulamento", None),
        ("1 ON / 2 PN / xyz", None),
    ],
)
def test_composicao_da_unit(text, total):
    assert ceiling.parse_unit_composition(text) == total
