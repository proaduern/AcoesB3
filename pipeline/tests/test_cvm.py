from datetime import date
from decimal import Decimal

import pytest

from acoesb3 import cvm
from conftest import fixture_bytes

PER_SHARE = ["3.99"]
RULES = [
    cvm.AccountRule("DRE", "3.09", True),
    cvm.AccountRule("DRE", "3.11", True),
    cvm.AccountRule("DRE", "3.13", True),
    cvm.AccountRule("DRE", "3.99.01", True),
    cvm.AccountRule("BPP", "2.03", False),
    cvm.AccountRule("BPP", "2.08", True),
]


def lines(name, statement, consolidated=True):
    return list(cvm.parse_statement(fixture_bytes(name), statement, consolidated, RULES, PER_SHARE))


def value(ls, cvm_code, code, period_start=None):
    found = [
        x
        for x in ls
        if x.cvm_code == cvm_code
        and x.account_code == code
        and (period_start is None or x.period_start == period_start)
    ]
    assert len(found) == 1, found
    return found[0]


# --- ESCALA_MOEDA -------------------------------------------------------------


def test_escala_mil_multiplica_por_mil():
    # WEG 2024, lucro atribuído ao controlador: 6.042.593 (R$ mil) no arquivo
    x = value(lines("dfp_cia_aberta_DRE_con_2024.csv", "DRE"), 5410, "3.11.01")
    assert x.source_scale == "MIL"
    assert x.value == Decimal("6042593000")


def test_escala_unidade_nao_multiplica():
    # CEL Participações declara em UNIDADE: 152.557 reais
    x = value(lines("dfp_cia_aberta_DRE_con_2024.csv", "DRE"), 16675, "3.11")
    assert x.source_scale == "UNIDADE"
    assert x.value == Decimal("152557")


def test_lpa_nao_recebe_escala_mesmo_com_mil():
    # WEG 2024: LPA básico ON = 1,44026 R$/ação, mas a linha vem com ESCALA_MOEDA = MIL
    x = value(lines("dfp_cia_aberta_DRE_con_2024.csv", "DRE"), 5410, "3.99.01.01")
    assert x.source_scale == "MIL"
    assert x.value == Decimal("1.4402600000")


def test_escala_desconhecida_falha():
    with pytest.raises(ValueError):
        cvm.scale_value("1", "MILHAO", "3.11", PER_SHARE)


def test_escala_prefixo_por_acao_nao_pega_conta_vizinha():
    # '3.99' não pode casar com '3.990' nem afetar outras contas
    assert cvm.scale_value("2", "MIL", "3.990", PER_SHARE) == Decimal(2000)


# --- Planos de contas diferentes ---------------------------------------------


def test_lucro_controlador_por_plano_de_contas():
    # Valores conferidos pelo usuário contra os balanços publicados de 2024 (03/10/2026),
    # conforme a seção 10 da especificação. Não alterar sem nova conferência.
    ls = lines("dfp_cia_aberta_DRE_con_2024.csv", "DRE")
    assert value(ls, 19348, "3.09.01").value == Decimal("41085000000")  # Itaú (banco)
    assert value(ls, 23159, "3.13.01").value == Decimal("8703353000")  # BB Seguridade
    assert value(ls, 5410, "3.11.01").value == Decimal("6042593000")  # WEG (comum)


def test_patrimonio_liquido_banco_e_comum():
    ls = lines("dfp_cia_aberta_BPP_con_2024.csv", "BPP")
    assert value(ls, 19348, "2.08").value == Decimal("221284000000")  # Itaú
    assert value(ls, 5410, "2.03").value == Decimal("23125217000")  # WEG


def test_so_contas_da_lista_e_so_exercicio_corrente():
    ls = lines("dfp_cia_aberta_DRE_con_2024.csv", "DRE")
    # 3.09 na WEG é "operações continuadas": entra porque a regra 3.09 existe para bancos.
    assert {x.account_code for x in ls if x.cvm_code == 5410} == {
        "3.09",
        "3.11",
        "3.11.01",
        "3.11.02",
        "3.99.01",
        "3.99.01.01",
    }
    assert all(x.period_end == date(2024, 12, 31) for x in ls if x.cvm_code == 5410)


def test_itr_dre_tem_trimestre_e_acumulado():
    ls = lines("itr_cia_aberta_DRE_con_2025.csv", "DRE")
    q2 = [x for x in ls if x.account_code == "3.11" and x.reference_date == date(2025, 6, 30)]
    assert {x.period_start for x in q2} == {date(2025, 1, 1), date(2025, 4, 1)}


# --- Índice, versões, escopo --------------------------------------------------


def test_indice_traz_todas_as_versoes_com_data_de_entrega():
    idx = cvm.parse_index(fixture_bytes("dfp_cia_aberta_2024.csv"))
    brb = sorted((r.version, r.received_date) for r in idx if r.cvm_code == 14206)
    assert [v for v, _ in brb] == [1, 2, 3]
    assert brb[0][1] == date(2025, 4, 9)
    assert all(r.doc_type == "DFP" for r in idx)


def _line(consolidated, statement="DRE", code=1):
    return cvm.Line(
        code,
        date(2024, 12, 31),
        1,
        statement,
        consolidated,
        "3.11",
        None,
        date(2024, 12, 31),
        Decimal(1),
        "MIL",
    )


def test_escopo_consolidado_senao_individual():
    ls = [_line(True), _line(False), _line(False, code=2), _line(False, "BPP")]
    out = cvm.choose_scope(ls)
    assert _line(False) not in out  # empresa 1 tem consolidada de DRE
    assert _line(False, code=2) in out  # empresa 2 só tem individual
    assert _line(False, "BPP") in out  # decisão é por demonstração


def test_csv_com_campos_a_mais_falha():
    raw = "A;B\n1;2\n1;2;3\n".encode("latin-1")
    with pytest.raises(ValueError):
        list(cvm.read_csv(raw))


def test_composicao_capital():
    rows = cvm.parse_share_counts(fixture_bytes("dfp_cia_aberta_composicao_capital_2024.csv"))
    itau = next(r for r in rows if r.cnpj == "60.872.504/0001-23")
    assert itau.total == itau.common + itau.preferred


# --- FCA e cadastro ------------------------------------------------------------


def test_fca_unit_com_composicao():
    rows = cvm.parse_fca_securities(fixture_bytes("fca_cia_aberta_valor_mobiliario_2026.csv"))
    taee11 = next(r for r in rows if r.ticker == "TAEE11")
    assert taee11.security_type == "Units"
    assert taee11.unit_composition == "1 ON / 2 PN"


def test_cad_deduplica_e_mantem_canceladas():
    rows = {r.cvm_code: r for r in cvm.parse_cad(fixture_bytes("cad_cia_aberta.csv"))}
    assert rows[21954].status == "CANCELADA"
    assert rows[21954].canceled_at == date(2015, 12, 18)
    assert rows[5410].status == "ATIVO"
    raw_count = fixture_bytes("cad_cia_aberta.csv").decode("latin-1").count("\n") - 1
    assert len(rows) < raw_count  # havia CD_CVM duplicado


def test_duplicata_identica_fica_uma_e_conflito_some():
    a = _line(True)
    b = _line(True, code=2)
    c = cvm.Line(
        2, date(2024, 12, 31), 1, "DRE", True, "3.11", None, date(2024, 12, 31), Decimal(999), "MIL"
    )  # mesma chave de b, valor diferente
    kept, identical, conflicts = cvm.dedupe([a, a, b, c])
    assert kept == [a]
    assert identical == 1
    assert len(conflicts) == 1 and conflicts[0][0] == 2
