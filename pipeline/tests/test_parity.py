"""Fixture de paridade do simulador da tela (web/tests/parity/cases.json)."""

import json
from decimal import Decimal

import pytest

from acoesb3 import cli, parity
from acoesb3.compute import load_config

D = Decimal


def test_a_saida_e_deterministica():
    assert parity.render() == parity.render()


def test_fixture_versionado_esta_em_dia():
    """Mudou ceiling.py ou parity.py: regerar (`ceilings parity-export`) e conferir o TS."""
    assert parity.DEFAULT_PATH.exists(), "rode `acoesb3 ceilings parity-export`"
    assert parity.DEFAULT_PATH.read_text(encoding="utf-8") == parity.render(), (
        "web/tests/parity/cases.json defasado: rode `acoesb3 ceilings parity-export` e atualize "
        "o simulador (web/src/lib/ceiling) se a regra mudou"
    )


def test_comando_nao_usa_o_banco(tmp_path, monkeypatch):
    monkeypatch.delenv("NEON_DATABASE_URL", raising=False)
    out = tmp_path / "x" / "cases.json"
    assert cli.main(["ceilings", "parity-export", "--out", str(out)]) == 0
    assert out.read_text(encoding="utf-8") == parity.render()


def test_cobre_todos_os_status_faixas_e_votos():
    data = json.loads(parity.render())
    methods = {(m["method"], m["status"]) for c in data["cases"] for m in c["expected"]["methods"]}
    for method in ("bazin", "graham", "gordon", "multiples", "dcf"):
        # Bazin nunca é excluído por regra: só aplicável ou indisponível
        for status in ("ok", "unavailable") + (() if method == "bazin" else ("excluded",)):
            assert (method, status) in methods, f"{method}/{status} sem caso"
    classes = [k for c in data["cases"] for k in c["expected"]["classes"]]
    assert {k["band"] for k in classes} == {None, "strong_buy", "buy", "hold", "expensive"}
    assert {k["buy"] for k in classes} == {True, False}
    cons = {c["expected"]["consolidated"]["status"] for c in data["cases"]}
    assert cons == {"ok", "insufficient"}
    assert {k["ticker"] for k in classes} >= {"P_80", "P_100", "P_120", "U_80", "U_120"}


def test_sem_mudar_parametros_o_esperado_e_o_gravado():
    """Caso 'padrao': o que o Python recalcula é exatamente o que o pipeline gravou."""
    data = json.loads(parity.render())
    for c in data["cases"]:
        if not c["name"].endswith("__padrao"):
            continue
        snap = data["snapshots"][c["fixture"]]["methods"]
        got = [(m["method"], m["status"], m["value"], m["reason"]) for m in snap]
        want = [
            (m["method"], m["status"], m["value"], m["reason"]) for m in c["expected"]["methods"]
        ]
        assert got == want, c["name"]


def test_snapshot_do_dcf_guarda_o_divisor_por_acao():
    data = json.loads(parity.render())
    dcf = next(m for m in data["snapshots"]["comum_completo"]["methods"] if m["method"] == "dcf")
    assert dcf["status"] == "ok"
    assert dcf["inputs"]["shares"] == "1000" and dcf["inputs"]["shares_factor"] == "1.4"
    # valor = total / ações / fator: refazer a conta com os insumos dá o valor gravado
    total = D(dcf["inputs"]["equity_value"])
    assert abs(
        total / D(dcf["inputs"]["shares"]) / D(dcf["inputs"]["shares_factor"]) - D(dcf["value"])
    ) < D("1e-12")


def test_config_base_igual_ao_das_migracoes(conn):
    cfg = load_config(conn)
    for key, want in parity.BASE_CONFIG.items():
        got = cfg[key]
        if isinstance(want, (dict, list, bool)):
            assert got == want, key
        else:
            assert D(str(got)) == D(str(want)), key


@pytest.mark.parametrize("name", ["padrao", "dcf_crescimento_3"])
def test_casos_basicos_existem(name):
    names = {c["name"] for c in json.loads(parity.render())["cases"]}
    assert f"comum_completo__{name}" in names
