"""Fase 2, lógica pura: eventos societários, outliers, extração por plano e critérios."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from acoesb3 import corporate, cvm, indicators, mapping, screen
from conftest import fixture_bytes

D = Decimal

# --- Eventos societários ------------------------------------------------------

SP = corporate.SplitParams(
    candidate_low=0.85,
    candidate_high=1.18,
    ratio_tolerance=0.03,
    auto_min_factor=1.5,
    max_gap_days=10,
    simple_factors=(1.1, 1.2, 1.25, 1.5, 2, 3, 4, 5, 10, 20),
)


def series(*closes_dis, start=date(2020, 1, 2)):
    out, d = [], start
    for close, dis in closes_dis:
        out.append((d, D(str(close)), dis))
        d += timedelta(days=1)
    return out


def test_desdobramento_2_para_1_com_mudanca_de_dismes_e_automatico():
    ev = corporate.detect_events(series((40, 1), (41, 1), (20.6, 2), (21, 2)), SP)
    assert len(ev) == 1
    assert ev[0].factor == D("2.0")
    assert ev[0].status == "auto"
    assert ev[0].event_date == date(2020, 1, 4)


def test_salto_limpo_sem_dismes_fica_suspeito():
    ev = corporate.detect_events(series((40, 1), (20, 1)), SP)
    assert [e.status for e in ev] == ["suspected"]


def test_grupamento_10_para_1():
    ev = corporate.detect_events(series((1.5, 1), (15.2, 2)), SP)
    assert len(ev) == 1
    assert ev[0].factor == D("0.1")
    assert ev[0].status == "auto"


def test_oscilacao_normal_nao_e_evento():
    assert corporate.detect_events(series((40, 1), (37, 1), (36, 1), (40, 1)), SP) == []


def test_queda_forte_fora_de_fator_simples_nao_e_evento():
    # -37%: razão 0,63 -> fator 1,59, a 6% de 1,5: acima da tolerância
    assert corporate.detect_events(series((100, 1), (63, 2)), SP) == []


def test_bonificacao_de_20_por_cento_so_com_revisao():
    ev = corporate.detect_events(series((12, 1), (10, 2)), SP)
    assert len(ev) == 1 and ev[0].factor == D("1.2") and ev[0].status == "suspected"


def test_bonificacao_pequena_nao_e_detectada():
    # 10%: razão 0,909 fica dentro da faixa de oscilação normal (limitação documentada)
    assert corporate.detect_events(series((11, 1), (10, 2)), SP) == []


def test_pregoes_muito_distantes_nao_sao_comparados():
    qs = [(date(2020, 1, 2), D(40), 1), (date(2020, 3, 2), D(20), 2)]
    assert corporate.detect_events(qs, SP) == []


def test_fator_acumulado_so_conta_eventos_no_intervalo():
    evs = [(date(2020, 5, 1), D(2)), (date(2022, 1, 10), D(5)), (date(2023, 1, 1), D("0.5"))]
    assert corporate.cumulative_factor(evs, date(2020, 5, 1), date(2022, 12, 31)) == D(5)
    assert corporate.cumulative_factor(evs, date(2019, 1, 1), date(2022, 12, 31)) == D(10)
    assert corporate.cumulative_factor(evs, date(2023, 1, 1), date(2024, 1, 1)) == D(1)


# --- Outliers -----------------------------------------------------------------


def test_outlier_acima_de_2x_a_mediana_de_5_anos():
    totals = {2016: D(100), 2017: D(110), 2018: D(90), 2019: D(100), 2020: D(105), 2021: D(300)}
    found = screen.find_outliers(totals, D(2), 5, 3)
    assert set(found) == {2021}
    med, ratio, n = found[2021]
    assert med == D(100) and ratio == D(3) and n == 5


def test_exatamente_2x_nao_e_outlier_e_pouco_historico_nao_marca():
    totals = {2016: D(100), 2017: D(100), 2018: D(100), 2019: D(200)}
    assert screen.find_outliers(totals, D(2), 5, 3) == {}
    assert screen.find_outliers({2018: D(100), 2019: D(900)}, D(2), 5, 3) == {}


def test_mediana_zero_nao_permite_concluir():
    totals = {2016: D(0), 2017: D(0), 2018: D(0), 2019: D(50)}
    assert screen.find_outliers(totals, D(2), 5, 3) == {}


# --- Extração conta a conta (linhas reais da DFP 2024) ------------------------

RULES = [
    cvm.AccountRule("DRE", "3.09", True),
    cvm.AccountRule("DRE", "3.11", True),
    cvm.AccountRule("DRE", "3.13", True),
    cvm.AccountRule("DRE", "3.99.01", True),
    cvm.AccountRule("BPP", "2.03", False),
    cvm.AccountRule("BPP", "2.03.09", False),
    cvm.AccountRule("BPP", "2.08", True),
    cvm.AccountRule("DVA", "7.08.04.01", False),
    cvm.AccountRule("DVA", "7.08.04.02", False),
    cvm.AccountRule("DVA", "7.09.04.01", False),
    cvm.AccountRule("DVA", "7.09.04.02", False),
    cvm.AccountRule("DVA", "7.11.04.01", False),
    cvm.AccountRule("DVA", "7.11.04.02", False),
]


def real_lines(cvm_code):
    out = {}
    for stmt, name in (
        ("DRE", "dfp_cia_aberta_DRE_con_2024.csv"),
        ("BPP", "dfp_cia_aberta_BPP_con_2024.csv"),
        ("DVA", "dfp_cia_aberta_DVA_con_2024.csv"),
    ):
        for x in cvm.parse_statement(fixture_bytes(name), stmt, True, RULES, ["3.99"]):
            if x.cvm_code == cvm_code:
                out[(x.statement, x.account_code)] = x.value
    return out


def test_weg_plano_comum():
    a = indicators.extract_annual(real_lines(5410), consolidated=True)
    assert a.plan == "comum"
    assert a.profit == D("6042593000")  # conferido pelo usuário
    assert a.equity == D("23125217000") - D("920996000")
    assert (a.jcp, a.dividends, a.dividends_source) == (D("1134258000"), D("2056668000"), "dva")
    assert a.lpa_on == D("1.44026")


def test_itau_plano_banco_usa_2_08_e_dva_7_09():
    a = indicators.extract_annual(real_lines(19348), consolidated=True)
    assert a.plan == "banco"
    assert a.profit == D("41085000000")  # conferido pelo usuário
    assert a.equity == D("221284000000") - D("10194000000")
    assert (a.jcp, a.dividends) == (D(0), D("28104000000"))
    assert a.shares_on is None and "shares" in a.notes


def test_bb_seguridade_plano_seguradora_usa_dva_7_11():
    a = indicators.extract_annual(real_lines(23159), consolidated=True)
    assert a.plan == "seguradora"
    assert a.profit == D("8703353000")  # conferido pelo usuário
    assert a.equity == D("9695421000")
    assert (a.jcp, a.dividends) == (D(0), D("7111000000"))


def test_plano_misto_do_banco_do_brasil_dre_comum_balanco_e_dva_de_banco():
    # Diagnóstico do Actions: BB 2020+ tem lucro em 3.11.01, PL em 2.08 e proventos em 7.09.04.
    lines = {
        ("DRE", "3.11"): D(10),
        ("DRE", "3.11.01"): D(9),
        ("BPP", "2.08"): D(100),
        ("BPP", "2.08.09"): D(4),
        ("DVA", "7.09.04.01"): D(1),
        ("DVA", "7.09.04.02"): D(2),
    }
    a = indicators.extract_annual(lines, consolidated=True)
    assert a.plan == "banco"
    assert (a.profit, a.equity, a.jcp, a.dividends) == (D(9), D(96), D(1), D(2))


def test_escopo_individual_usa_lucro_total_e_nao_subtrai_nao_controladores():
    # Diagnóstico do Actions: 962 DFP individuais só têm 3.09 e 3.11 (sem 3.xx.01).
    lines = {
        ("DRE", "3.09"): D(7),
        ("DRE", "3.11"): D(8),
        ("BPP", "2.03"): D(50),
        ("DVA", "7.08.04.01"): D(1),
        ("DVA", "7.08.04.02"): D(2),
    }
    a = indicators.extract_annual(lines, consolidated=False)
    assert a.plan == "comum"
    assert (a.profit, a.equity, a.jcp, a.dividends) == (D(8), D(50), D(1), D(2))
    # o mesmo documento tratado como consolidado fica indisponível (falta atribuição)
    b = indicators.extract_annual(lines, consolidated=True)
    assert b.profit is None and "profit" in b.notes and b.equity is None


def test_individual_de_seguradora_e_de_banco_escolhem_a_conta_do_plano():
    seg = {("DRE", "3.11"): D(1), ("DRE", "3.13"): D(5), ("DVA", "7.11.04.01"): D(1),
           ("DVA", "7.11.04.02"): D(1), ("BPP", "2.03"): D(9)}  # fmt: skip
    assert indicators.extract_annual(seg, consolidated=False).profit == D(5)
    banco = {("DRE", "3.09"): D(6), ("DRE", "3.11"): D(1), ("BPP", "2.08"): D(70)}
    a = indicators.extract_annual(banco, consolidated=False)
    assert (a.plan, a.profit, a.equity) == ("banco", D(6), D(70))


def test_duas_contas_de_lucro_dos_controladores_desempata_pelo_plano_ou_falha():
    lines = {("DRE", "3.09.01"): D(1), ("DRE", "3.11.01"): D(2), ("BPP", "2.03"): D(5),
             ("BPP", "2.03.09"): D(0)}  # fmt: skip
    assert indicators.extract_annual(lines, consolidated=True, forced_plan="comum").profit == D(2)
    assert indicators.extract_annual(lines, consolidated=True).profit is None  # sem plano: ambíguo


def test_conta_ausente_vira_indisponivel_nao_zero():
    lines = real_lines(5410)
    del lines[("DVA", "7.08.04.01")]
    a = indicators.extract_annual(lines, consolidated=True)
    assert a.jcp is None and a.dividends is None and a.dividends_source is None
    assert "dividends" in a.notes
    del lines[("BPP", "2.03.09")]
    b = indicators.extract_annual(lines, consolidated=True)
    assert b.equity is None and "equity" in b.notes


def test_sem_conta_de_lucro_nao_identifica_plano():
    a = indicators.extract_annual({("BPP", "2.03"): D(1)}, consolidated=True)
    assert a.plan is None and a.profit is None and a.equity is None and "plan" in a.notes


def test_plano_forcado_e_override_de_dividendos():
    lines = real_lines(5410)
    a = indicators.extract_annual(lines, forced_plan="banco", consolidated=True)
    assert a.plan == "banco" and a.profit == D("6042593000")  # só uma conta de lucro existe
    b = indicators.extract_annual(lines, dividend_override=(D(1), D(2), "manual"))
    assert (b.jcp, b.dividends, b.dividends_source) == (D(1), D(2), "manual")


def test_proventos_manual_fre_dva_nessa_ordem_e_o_fre_respeita_a_data():
    d = indicators.choose_dividends
    jcp, div = D(1), D(2)
    fre = (D(10), D(20), date(2019, 6, 1))
    assert d(jcp, div, "manual", *fre, as_of=date(2020, 1, 1)) == (jcp, div, "manual")
    assert d(jcp, div, "dva", *fre, as_of=date(2020, 1, 1)) == (D(10), D(20), "fre")
    assert d(jcp, div, "dva", *fre, as_of=date(2019, 1, 1)) == (
        jcp,
        div,
        "dva",
    )  # FRE ainda não saiu
    assert d(None, None, None, *fre, as_of=date(2019, 1, 1)) == (None, None, None)
    assert d(jcp, div, "dva", *fre, as_of=None) == (D(10), D(20), "fre")
    assert d(None, None, None, None, None, None) == (None, None, None)


# --- Mapeamento ticker -> empresa --------------------------------------------


def test_classe_e_raiz_do_ticker():
    assert mapping.ticker_root("TAEE11") == "TAEE"
    assert [mapping.ticker_class(t) for t in ("PETR3", "PETR4", "ITSA5", "TAEE11", "AAPL34")] == [
        "on",
        "pn",
        "pn",
        "other",
        "other",
    ]
    assert mapping.ticker_root("XPTO") is None


def test_raiz_ambigua_fica_de_fora_ate_haver_override():
    fca = [("ABCD3", 1), ("ABCD4", 1), ("WXYZ3", 2), ("WXYZ4", 3)]
    m, amb = mapping.build_root_map(fca, {})
    assert m == {"ABCD": 1} and amb == {"WXYZ": [2, 3]}
    m, amb = mapping.build_root_map(fca, {"WXYZ": 3})
    assert m["WXYZ"] == 3 and amb == {}


def test_papel_de_referencia_prefere_on_mais_negociada():
    secs = [(1, "TAEE4", 900.0), (2, "TAEE3", 10.0), (3, "TAEE11", 5000.0), (4, "TAEE3F", 1.0)]
    assert mapping.reference_security(secs) == ("on", 2)
    assert mapping.reference_security([(1, "ABCD4", 1.0)]) == ("pn", 1)
    assert mapping.reference_security([(1, "ABCD11", 1.0)]) is None
    assert mapping.class_securities(secs) == {"on": 2, "pn": 1}


# --- Critérios do filtro ------------------------------------------------------

P = screen.ScreenParams.from_config(
    {
        "screen.profit_window_years": 10,
        "screen.profit_min_positive_years": 8,
        "screen.roe_years": 5,
        "screen.roe_min": 0.10,
        "screen.dividend_window_years": 10,
        "screen.dy_years": 5,
        "screen.dy_min": 0.05,
        "screen.payout_years": 5,
        "screen.payout_min": 0.25,
        "screen.payout_max": 1.0,
        "screen.dps_window_years": 10,
        "screen.dps_max_drop_years": 3,
        "screen.dps_drop_tolerance": 0,
        "screen.dps_min_pairs": 6,
        "tax.jcp": 0.15,
        "tax.dividend": 0,
        "outlier.multiple": 2,
        "outlier.median_years": 5,
        "outlier.min_history_years": 3,
        "outlier.min_valid_years": 3,
        "liquidity.min_avg_volume": 1000000,
        "liquidity.min_presence": 0.90,
        "screen.max_data_age_days": 730,
    }
)
LIQ_OK = screen.Liquidity(D(5_000_000), D("0.98"), 63)


def good_years(first=2016, last=2025, **over):
    """Empresa saudável: lucro 100, PL 500 (ROE 20%), paga 50 (30 de dividendo + 20 de JCP),
    1000 ações (dividendo por ação 0,05 constante), valor de mercado 800
    (DY líquido = (30 + 17)/800 = 5,875%)."""
    ys = {}
    for y in range(first, last + 1):
        ys[y] = screen.YearData(
            year=y,
            reference_date=date(y, 12, 31),
            filing_id=y,
            received_date=date(y + 1, 3, 15),
            profit=D(100),
            equity=D(500),
            jcp=D(20),
            dividends=D(30),
            dividends_source="dva",
            shares=1000,
            market_cap=D(800),
        )
    for y, changes in over.items():
        for k, v in changes.items():
            setattr(ys[int(y[1:])], k, v)
    return ys


def crit(result, name):
    return next(c for c in result.criteria if c.name == name)


def test_empresa_saudavel_e_aprovada():
    r = screen.evaluate(good_years(), LIQ_OK, P)
    assert r.status == "approved", [(c.name, c.status, c.detail) for c in r.criteria]
    assert r.data_base == date(2025, 12, 31)
    assert crit(r, "roe_medio").value == D("0.2")
    assert crit(r, "payout_medio").value == D("0.5")
    assert crit(r, "dy_medio_liquido").value == D("47") / D("800")


def test_lucro_positivo_em_8_de_10_e_o_limite():
    ok = good_years(y2017={"profit": D(-5)}, y2018={"profit": D(-5)})
    assert crit(screen.evaluate(ok, LIQ_OK, P), "lucro_positivo").status == "pass"
    bad = good_years(y2017={"profit": D(-5)}, y2018={"profit": D(-5)}, y2019={"profit": D(0)})
    c = crit(screen.evaluate(bad, LIQ_OK, P), "lucro_positivo")
    assert (c.status, c.value) == ("fail", D(7))  # lucro zero não é positivo


def test_roe_exatamente_10_por_cento_reprova():
    ys = good_years()
    for y in ys.values():
        y.equity = D(1000)  # ROE = 100/1000 = 10%
    c = crit(screen.evaluate(ys, LIQ_OK, P), "roe_medio")
    assert c.value == D("0.1") and c.status == "fail"  # critério é "maior que 10%"


def test_roe_usa_media_do_pl_do_inicio_e_do_fim():
    ys = good_years(y2025={"equity": D(700)})  # média 2025 = (700 + 500) / 2 = 600
    c = crit(screen.evaluate(ys, LIQ_OK, P), "roe_medio")
    assert c.detail["roe"][2025] == str(D(100) / D(600))


def test_roe_precisa_do_pl_do_ano_anterior_a_janela():
    r = screen.evaluate(good_years(first=2021), LIQ_OK, P)  # 5 anos: falta 2020 para o ROE de 2021
    c = crit(r, "roe_medio")
    assert c.status == "unavailable" and c.detail["reason"] == "history"


def test_historico_menor_que_10_anos_e_historico_insuficiente_nao_reprovacao():
    r = screen.evaluate(good_years(first=2020), LIQ_OK, P)
    assert r.status == "insufficient_history"
    assert crit(r, "lucro_positivo").detail["missing_years"] == [2016, 2017, 2018, 2019]


def test_buraco_no_meio_e_dado_insuficiente():
    ys = good_years()
    del ys[2020]
    r = screen.evaluate(ys, LIQ_OK, P)
    assert crit(r, "lucro_positivo").detail["reason"] == "hole"
    assert r.status == "insufficient_data"


def test_dado_ausente_nao_vira_zero():
    ys = good_years(y2022={"jcp": None})
    r = screen.evaluate(ys, LIQ_OK, P)
    c = crit(r, "proventos_todos_os_anos")
    assert c.status == "unavailable" and c.detail["missing_years"] == [2022]
    assert r.status == "insufficient_data"


def test_proventos_zero_em_um_ano_reprova():
    r = screen.evaluate(good_years(y2019={"jcp": D(0), "dividends": D(0)}), LIQ_OK, P)
    c = crit(r, "proventos_todos_os_anos")
    assert (c.status, c.value) == ("fail", D(9))
    assert r.status == "rejected"


def test_outlier_fica_fora_da_media_do_dy_e_do_payout_mas_conta_como_pago():
    # 2025 pagou 10x; sem a regra o DY médio seria muito maior
    ys = good_years(y2025={"jcp": D(200), "dividends": D(300), "outlier": True})
    r = screen.evaluate(ys, LIQ_OK, P)
    assert crit(r, "dy_medio_liquido").value == D("47") / D("800")  # 4 anos, sem 2025
    assert crit(r, "dy_medio_liquido").detail["outlier_years"] == [2025]
    assert crit(r, "payout_medio").value == D("0.5")
    assert crit(r, "proventos_todos_os_anos").status == "pass"


def test_outlier_liberado_pelo_usuario_entra_na_media():
    ys = good_years(y2025={"jcp": D(200), "dividends": D(300), "outlier": False})
    c = crit(screen.evaluate(ys, LIQ_OK, P), "payout_medio")
    assert c.value == (D("0.5") * 4 + D(5)) / 5  # 2025: 500/100 = 500%


def test_poucos_anos_apos_excluir_outliers_e_indisponivel():
    ys = good_years(
        y2023={"outlier": True}, y2024={"outlier": True}, y2025={"outlier": True}
    )  # sobram 2 anos < 3
    r = screen.evaluate(ys, LIQ_OK, P)
    assert crit(r, "dy_medio_liquido").status == "unavailable"
    assert crit(r, "payout_medio").status == "unavailable"


def test_dy_liquido_desconta_ir_do_jcp():
    ys = good_years()
    for y in ys.values():
        y.jcp, y.dividends, y.market_cap = D(100), D(0), D(1000)  # bruto 10%, líquido 8,5%
    assert crit(screen.evaluate(ys, LIQ_OK, P), "dy_medio_liquido").value == D("0.085")


def test_dy_sem_valor_de_mercado_e_indisponivel():
    ys = good_years(y2024={"market_cap": None})
    assert crit(screen.evaluate(ys, LIQ_OK, P), "dy_medio_liquido").status == "unavailable"


@pytest.mark.parametrize(
    ("dividends", "expected"),
    [(0, "fail"), (24, "fail"), (25, "pass"), (40, "pass"), (100, "pass"), (101, "fail")],
)
def test_payout_faixa_25_a_100_inclusiva(dividends, expected):
    ys = good_years()
    for y in ys.values():
        y.jcp, y.dividends = D(0), D(dividends)  # lucro 100 -> payout = dividends / 100
    assert crit(screen.evaluate(ys, LIQ_OK, P), "payout_medio").status == expected


def test_payout_ano_de_prejuizo_fica_fora_da_media():
    ys = good_years(y2024={"profit": D(-10)})
    c = crit(screen.evaluate(ys, LIQ_OK, P), "payout_medio")
    assert c.detail["loss_years"] == [2024] and c.value == D("0.5")


def test_liquidez():
    thin = screen.Liquidity(D(900_000), D("0.99"), 63)
    sporadic = screen.Liquidity(D(5_000_000), D("0.89"), 63)
    assert crit(screen.evaluate(good_years(), thin, P), "liquidez").status == "fail"
    assert crit(screen.evaluate(good_years(), sporadic, P), "liquidez").status == "fail"
    edge = screen.Liquidity(D(1_000_000), D("0.90"), 63)
    assert crit(screen.evaluate(good_years(), edge, P), "liquidez").status == "pass"
    r = screen.evaluate(good_years(), None, P)
    assert crit(r, "liquidez").status == "unavailable" and r.status == "insufficient_data"


def test_reprovacao_vence_dado_indisponivel_e_setor_excluido_nao_avalia():
    ys = good_years(y2022={"jcp": None}, y2019={"profit": D(-1)})
    for y in (2017, 2018):
        ys[y].profit = D(-1)
    assert screen.evaluate(ys, LIQ_OK, P).status == "rejected"
    r = screen.evaluate(good_years(), LIQ_OK, P, excluded=True)
    assert r.status == "excluded" and r.criteria == []


def test_parametro_ausente_falha_em_vez_de_assumir_valor():
    with pytest.raises(KeyError):
        screen.ScreenParams.from_config({"screen.roe_min": 0.1})


# --- Dividendo por ação: total declarado / ações no fim do exercício ---------------


def set_shares(ys, values):
    for y, v in zip(sorted(ys), values, strict=True):
        ys[y].shares = v


def test_dps_mais_de_3_quedas_reprova():
    ys = good_years()
    # ações oscilando com dividendo total igual: o dividendo por ação cai quando as ações sobem
    set_shares(ys, (1000, 1100, 1000, 1100, 1000, 1100, 1000, 1100, 1000, 1100))
    c = crit(screen.evaluate(ys, LIQ_OK, P), "queda_dividendo_por_acao")
    assert c.detail["drop_years"] == [2017, 2019, 2021, 2023, 2025]
    assert (c.status, c.value) == ("fail", D(5))


def test_dps_exatamente_3_quedas_passa():
    ys = good_years()
    set_shares(ys, (1000, 1100, 1000, 1100, 1000, 1100, 1000, 1000, 1000, 1000))
    c = crit(screen.evaluate(ys, LIQ_OK, P), "queda_dividendo_por_acao")
    assert c.detail["drop_years"] == [2017, 2019, 2021]
    assert (c.status, c.value) == ("pass", D(3))


def test_dps_ajusta_por_evento_depois_do_fim_do_exercicio():
    # desdobramento 2:1 em 2022: ações dobram de 1000 para 2000 e o dividendo total é igual
    ys = good_years()
    for y in ys.values():
        y.shares = 1000 if y.year <= 2021 else 2000
        y.shares_factor = D(2) if y.year <= 2021 else D(1)
    c = crit(screen.evaluate(ys, LIQ_OK, P), "queda_dividendo_por_acao")
    assert c.detail["drop_years"] == [] and c.status == "pass"
    for y in ys.values():  # sem o evento conhecido, a queda de 2022 aparece
        y.shares_factor = D(1)
    c = crit(screen.evaluate(ys, LIQ_OK, P), "queda_dividendo_por_acao")
    assert c.detail["drop_years"] == [2022]


def test_dps_nao_depende_do_lucro():
    ys = good_years(y2020={"profit": D(-5)})  # prejuízo com dividendo declarado
    c = crit(screen.evaluate(ys, LIQ_OK, P), "queda_dividendo_por_acao")
    assert c.detail["comparable_pairs"] == 9 and 2020 in c.detail["dps"]


def test_dps_pula_comparacoes_com_outlier_sem_acoes_e_exige_minimo_de_pares():
    ys = good_years(y2020={"outlier": True})
    c = crit(screen.evaluate(ys, LIQ_OK, P), "queda_dividendo_por_acao")
    assert 2020 not in c.detail["dps"] and c.detail["comparable_pairs"] == 7
    ys = good_years(y2018={"shares": None})
    assert (
        crit(screen.evaluate(ys, LIQ_OK, P), "queda_dividendo_por_acao").detail["comparable_pairs"]
        == 7
    )
    many = good_years(**{f"y{y}": {"shares": None} for y in (2017, 2019, 2021, 2023)})
    c = crit(screen.evaluate(many, LIQ_OK, P), "queda_dividendo_por_acao")
    assert c.status == "unavailable"


def test_dps_guarda_a_fonte_dos_proventos_de_cada_ano():
    ys = good_years(y2024={"dividends_source": "fre"})
    c = crit(screen.evaluate(ys, LIQ_OK, P), "queda_dividendo_por_acao")
    assert c.detail["sources"][2024] == "fre" and c.detail["sources"][2023] == "dva"


# --- Dados desatualizados (regra de 2 anos) ------------------------------------


def test_empresa_que_parou_de_entregar_dfp_fica_stale():
    ys = good_years(last=2021)
    r = screen.evaluate(ys, LIQ_OK, P, as_of=date(2026, 10, 4))
    assert r.status == "stale" and r.data_base == date(2021, 12, 31) and r.criteria == []


def test_limite_de_730_dias_e_inclusivo():
    ys = good_years()  # data-base 31/12/2025
    assert screen.evaluate(ys, LIQ_OK, P, as_of=date(2027, 12, 31)).status != "stale"  # 730 dias
    assert screen.evaluate(ys, LIQ_OK, P, as_of=date(2028, 1, 1)).status == "stale"  # 731 dias


def test_sem_data_de_referencia_nao_aplica_a_regra():
    assert screen.evaluate(good_years(last=2016), LIQ_OK, P).status != "stale"
