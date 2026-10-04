"""Ações do FRE por data e fusão de eventos FRE + COTAHIST (lógica pura)."""

from datetime import date
from decimal import Decimal

from acoesb3 import corporate, shares

D = Decimal
FE = corporate.FreEvent
PE = corporate.PriceEvent

# --- Retratos do capital social ------------------------------------------------


def test_retrato_por_documento_prefere_integralizado_e_aprovacao_mais_recente():
    rows = [
        (1, date(2011, 1, 10), "Capital Emitido", date(2011, 4, 28), 999, 999),
        (1, date(2011, 1, 10), "Capital Integralizado", date(2010, 4, 22), 100, 50),
        (1, date(2011, 1, 10), "Capital Integralizado", date(2011, 4, 28), 110, 55),
        (2, date(2012, 6, 1), "Capital Emitido", date(2012, 1, 1), 120, 60),  # sem integralizado
        (3, date(2013, 6, 1), "Capital Autorizado", None, 1, 1),  # tipo ignorado
    ]
    snaps = shares.snapshots_from_capital(rows)
    assert [(s.received, s.common, s.preferred) for s in snaps] == [
        (date(2011, 1, 10), 110, 55),
        (date(2012, 6, 1), 120, 60),
    ]


def test_retrato_sem_quantidade_e_descartado():
    assert (
        shares.snapshots_from_capital(
            [(1, date(2011, 1, 1), "Capital Integralizado", None, None, 5)]
        )
        == []
    )


# --- Ações em uma data ---------------------------------------------------------

SNAPS = [
    shares.Snapshot(date(2019, 6, 1), 1000, 500),
    shares.Snapshot(date(2021, 6, 1), 2000, 1000),
]
GAP = 550


def test_usa_o_retrato_mais_proximo():
    got = shares.shares_at(SNAPS, [], date(2019, 12, 31), date(2030, 1, 1), GAP)
    assert got == (1000, 500, date(2019, 6, 1))  # 213 dias contra 518
    got = shares.shares_at(SNAPS, [], date(2021, 3, 31), date(2030, 1, 1), GAP)
    assert got == (2000, 1000, date(2021, 6, 1))  # 62 dias contra 669 (fora do limite)


def test_retrato_posterior_ao_fim_do_exercicio_desfaz_os_eventos_do_intervalo():
    # desdobramento 2:1 em março de 2021; o retrato de junho/2021 já tem as ações novas
    events = [(date(2021, 3, 10), D(2), None, None)]
    got = shares.shares_at(SNAPS, events, date(2020, 12, 31), date(2030, 1, 1), GAP)
    assert got == (1000, 500, date(2021, 6, 1))


def test_retrato_anterior_ao_fim_do_exercicio_aplica_os_eventos_do_intervalo():
    events = [(date(2019, 9, 1), D("1.1"), None, None)]  # bonificação de 10% depois do retrato
    got = shares.shares_at(SNAPS[:1], events, date(2019, 12, 31), date(2030, 1, 1), GAP)
    assert got == (1100, 550, date(2019, 6, 1))


def test_so_usa_retratos_ja_entregues_na_data_base():
    assert shares.shares_at(SNAPS, [], date(2021, 12, 31), date(2021, 1, 1), GAP) is None
    got = shares.shares_at(SNAPS, [], date(2020, 12, 31), date(2020, 1, 1), GAP)
    assert got is None  # só o retrato de jun/2019 existia e está a 579 dias (> 550)


def test_sem_retrato_perto_fica_indisponivel():
    assert shares.shares_at(SNAPS, [], date(2015, 12, 31), date(2030, 1, 1), GAP) is None
    assert shares.shares_at([], [], date(2020, 12, 31), date(2030, 1, 1), GAP) is None


# --- Fusão de eventos -----------------------------------------------------------

K = date(2018, 7, 1)  # entrega do documento do FRE


TOL = D("0.08")


def merge(fre_events, price_events, coverage=None, window=200, tol=TOL):
    return corporate.merge_events(fre_events, price_events, coverage, window, tol)


def test_fator_do_fre_com_data_de_efeito_do_salto_de_preco():
    # Caso real do Itaú: aprovado em 27/07/2018, preço saltou em 21/11/2018 (x1,5)
    fre = [FE(date(2018, 7, 27), D("1.5"), date(2019, 5, 1), "Desdobramento")]
    price = [PE(date(2018, 11, 21), D("1.5"), "auto")]
    events, dropped = merge(fre, price, coverage=date(2019, 5, 1))
    assert dropped == []
    (e,) = events
    assert (e.event_date, e.factor, e.source, e.date_basis) == (
        date(2018, 11, 21),
        D("1.5"),
        "fre",
        "cotahist",
    )
    assert e.known_from == date(2018, 11, 21)  # o salto de preço já mostrava o evento


def test_fator_oficial_prevalece_sobre_o_aproximado_do_preco():
    fre = [FE(date(2014, 4, 23), D("1.3"), K, "Bonificação")]
    price = [PE(date(2014, 4, 24), D("1.25"), "suspected")]  # 4% de diferença, dentro de 8%
    (e,), _ = merge(fre, price)
    assert e.factor == D("1.3") and e.date_basis == "cotahist"
    assert e.known_from == K  # salto só suspeito não antecipa o conhecimento


def test_sem_salto_correspondente_usa_a_data_de_aprovacao():
    fre = [FE(date(2016, 4, 4), D("0.1"), K, "Grupamento")]
    (e,), _ = merge(fre, [PE(date(2020, 1, 1), D(2), "auto")], coverage=date(2021, 1, 1))
    assert (e.event_date, e.date_basis) == (date(2016, 4, 4), "approval")


def test_salto_fora_da_janela_ou_com_fator_diferente_nao_casa():
    fre = [FE(date(2016, 4, 4), D(2), K, "Desdobramento")]
    far = PE(date(2016, 12, 1), D(2), "auto")  # 241 dias depois
    other = PE(date(2016, 4, 10), D(3), "auto")
    events, dropped = merge(fre, [far, other], coverage=date(2018, 1, 1))
    assert [(e.source, e.date_basis) for e in events] == [("fre", "approval")]
    assert len(dropped) == 2  # automáticos dentro da cobertura do FRE e sem par: divergência


def test_documentos_sobrepostos_do_fre_nao_duplicam_o_evento():
    a = FE(date(2015, 3, 31), D(2), date(2016, 5, 1), "Desdobramento")
    b = FE(date(2015, 3, 31), D(2), date(2015, 6, 1), "Desdobramento")
    (e,), _ = merge([a, b], [])
    assert e.known_from == date(2015, 6, 1)


def test_evento_do_cotahist_depois_da_cobertura_do_fre_entra():
    # layout novo do FRE (2025+) não traz desdobramentos: o preço é a única fonte
    price = [PE(date(2025, 8, 5), D(2), "auto"), PE(date(2025, 9, 1), D(2), "suspected")]
    events, _ = merge([], price, coverage=date(2024, 6, 1))
    assert [(e.event_date, e.source) for e in events] == [(date(2025, 8, 5), "cotahist")]


def test_sem_cobertura_do_fre_o_cotahist_automatico_entra_e_o_manual_sempre():
    price = [PE(date(2012, 1, 5), D(2), "auto"), PE(date(2013, 1, 5), D("1.1"), "manual")]
    events, dropped = merge([], price, coverage=None)
    assert [(e.source, e.event_date) for e in events] == [
        ("cotahist", date(2012, 1, 5)),
        ("manual", date(2013, 1, 5)),
    ]
    assert dropped == []
    inside = merge([], price, coverage=date(2020, 1, 1))
    assert [e.source for e in inside[0]] == ["manual"] and len(inside[1]) == 1


# --- Retrato que já tem (ou ainda não tem) a contagem nova do evento -------------


def test_retrato_posterior_que_ainda_tem_a_contagem_antiga_nao_desfaz_o_evento():
    # desdobramento 1000 -> 2000 aprovado em 10/05; o FRE de 30/05 ainda diz 1000 ações
    event = (date(2022, 5, 10), D(2), 1000, 2000)
    snaps = [shares.Snapshot(date(2022, 5, 30), 1000, 0)]
    got = shares.shares_at(snaps, [event], date(2021, 12, 31), date(2030, 1, 1), GAP)
    assert got == (1000, 0, date(2022, 5, 30))


def test_retrato_posterior_que_ja_tem_a_contagem_nova_desfaz_o_evento():
    event = (date(2022, 5, 10), D(2), 1000, 2000)
    snaps = [shares.Snapshot(date(2022, 5, 30), 2000, 0)]
    got = shares.shares_at(snaps, [event], date(2021, 12, 31), date(2030, 1, 1), GAP)
    assert got == (1000, 0, date(2022, 5, 30))


def test_retrato_anterior_sem_a_contagem_nova_aplica_o_evento_aprovado_antes_dele():
    # bonificação 10% aprovada em 01/04, mas o retrato de 15/04 ainda tem 1000
    event = (date(2022, 4, 1), D("1.1"), 1000, 1100)
    snaps = [shares.Snapshot(date(2022, 4, 15), 1000, 0)]
    got = shares.shares_at(snaps, [event], date(2022, 12, 31), date(2030, 1, 1), GAP)
    assert got == (1100, 0, date(2022, 4, 15))
    # com a contagem nova já no retrato, não aplica de novo
    snaps = [shares.Snapshot(date(2022, 4, 15), 1100, 0)]
    got = shares.shares_at(snaps, [event], date(2022, 12, 31), date(2030, 1, 1), GAP)
    assert got == (1100, 0, date(2022, 4, 15))
