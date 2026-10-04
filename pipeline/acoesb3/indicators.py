"""Fatos anuais de uma DFP (lucro, PL, proventos) lidos conta a conta.

Os códigos mudam de sentido entre empresa comum, banco e seguradora (docs/fontes.md), e há
empresas com planos misturados (o Banco do Brasil a partir de 2020 tem DRE no padrão comum,
balanço e DVA no padrão de banco). Por isso cada conceito é resolvido por conta, olhando o que
existe no documento, e não por um "plano" único:

| conceito              | consolidada                   | individual             |
|-----------------------|-------------------------------|------------------------|
| lucro do controlador  | única entre 3.09.01, 3.11.01, | 3.11 (comum), 3.09     |
|                       | 3.13.01 (empate: a do plano)  | (banco), 3.13 (segur.) |
| PL do controlador     | 2.08 (se existir) ou 2.03,    | idem, sem subtrair     |
|                       | menos a conta .09 (não contr.)| não controladores      |
| JCP e dividendos      | DVA 7.09.04 (banco), 7.11.04 (seguradora) ou 7.08.04 (comum): o  |
|                       | conjunto que existir                                            |

O "plano" (comum, banco, seguradora) é só um rótulo, deduzido da DVA, do balanço e da DRE
(nessa ordem), usado para desempatar o lucro e escolher a conta de lucro no escopo individual.
Conferido nas linhas reais da DFP 2024 de WEG, Itaú e BB Seguridade (tests/fixtures) e nos
diagnósticos do Actions (962 DFP individuais, BB 2020+). Tudo o que faltar vira ``None``
(indisponível); nada é preenchido com zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

Lines = dict[tuple[str, str], Decimal]  # (demonstração, código da conta) -> valor em R$

# plano -> (lucro consolidado atribuído, lucro total no escopo individual)
PROFIT = {
    "comum": ("3.11.01", "3.11"),
    "banco": ("3.09.01", "3.09"),
    "seguradora": ("3.13.01", "3.13"),
}
# plano -> (JCP, dividendos) na DVA
DVA = {
    "banco": ("7.09.04.01", "7.09.04.02"),
    "seguradora": ("7.11.04.01", "7.11.04.02"),
    "comum": ("7.08.04.01", "7.08.04.02"),
}
LPA_ON = ("DRE", "3.99.01.01")
LPA_PN = ("DRE", "3.99.01.02")

# Contas lidas das demonstrações (usado pela carga do banco).
NEEDED = sorted(
    {("DRE", c) for pair in PROFIT.values() for c in pair}
    | {("BPP", c) for c in ("2.03", "2.03.09", "2.08", "2.08.09")}
    | {("DVA", c) for pair in DVA.values() for c in pair}
    | {LPA_ON, LPA_PN}
)


@dataclass
class Annual:
    plan: str | None = None
    profit: Decimal | None = None
    equity: Decimal | None = None
    jcp: Decimal | None = None
    dividends: Decimal | None = None
    dividends_source: str | None = None
    lpa_on: Decimal | None = None
    lpa_pn: Decimal | None = None
    shares_on: int | None = None
    shares_pn: int | None = None
    consolidated: bool | None = None
    notes: dict = field(default_factory=dict)


def _dva_plan(lines: Lines) -> tuple[str | None, str | None]:
    present = [p for p, (j, d) in DVA.items() if ("DVA", j) in lines and ("DVA", d) in lines]
    if len(present) == 1:
        return present[0], None
    if not present:
        return None, "sem JCP/dividendos na DVA (7.08.04, 7.09.04 ou 7.11.04)"
    return None, f"mais de um conjunto de proventos na DVA: {present}"


def detect_plan(lines: Lines, forced: str | None = None) -> str | None:
    """Rótulo do plano: DVA, depois balanço (2.08 = banco), depois DRE."""
    if forced:
        return forced
    plan, _ = _dva_plan(lines)
    if plan:
        return plan
    if ("BPP", "2.08") in lines:
        return "banco"
    attrib = [p for p, (a, _) in PROFIT.items() if ("DRE", a) in lines]
    if len(attrib) == 1:
        return attrib[0]
    if ("DRE", "3.13") in lines:
        return "seguradora"
    if ("DRE", "3.11") in lines:
        return "comum"
    return None


def _profit(lines: Lines, plan: str | None, consolidated: bool | None, notes: dict):
    if consolidated is False:
        if plan is None:
            notes["profit"] = "escopo individual sem plano identificado"
            return None
        value = lines.get(("DRE", PROFIT[plan][1]))
        if value is None:
            notes["profit"] = f"falta DRE {PROFIT[plan][1]} (lucro, escopo individual)"
        return value
    present = [a for a, _ in PROFIT.values() if ("DRE", a) in lines]
    if len(present) == 1:
        return lines[("DRE", present[0])]
    if not present:
        notes["profit"] = "sem lucro atribuído aos controladores (3.09.01, 3.11.01, 3.13.01)"
        return None
    preferred = PROFIT[plan][0] if plan else None
    if preferred in present:
        return lines[("DRE", preferred)]
    notes["profit"] = f"mais de uma conta de lucro dos controladores: {present}"
    return None


def _equity(lines: Lines, consolidated: bool | None, notes: dict):
    root = "2.08" if ("BPP", "2.08") in lines else "2.03"
    total = lines.get(("BPP", root))
    nci = lines.get(("BPP", f"{root}.09"))
    if total is None:
        notes["equity"] = f"falta BPP {root}"
        return None
    if nci is not None:
        return total - nci
    if consolidated is False:
        return total  # individual não tem participação de não controladores
    notes["equity"] = f"falta BPP {root}.09 (não controladores)"
    return None


def extract_annual(
    lines: Lines,
    shares: tuple[int, int, int, int] | None = None,
    forced_plan: str | None = None,
    dividend_override: tuple[Decimal, Decimal, str] | None = None,
    consolidated: bool | None = None,
) -> Annual:
    """``shares``: (ordinárias, preferenciais, tesouraria ON, tesouraria PN) da DFP, ou None.

    ``consolidated``: escopo das demonstrações do documento (financial_line.consolidated).
    """
    a = Annual(consolidated=consolidated)
    a.plan = detect_plan(lines, forced_plan)
    if a.plan is None:
        a.notes["plan"] = "plano de contas não identificado"
    a.lpa_on = lines.get(LPA_ON)
    a.lpa_pn = lines.get(LPA_PN)
    if shares is not None:
        common, preferred, t_common, t_pref = shares
        a.shares_on = common - t_common
        a.shares_pn = preferred - t_pref
    else:
        a.notes["shares"] = "composicao_capital indisponível neste documento"
    a.profit = _profit(lines, a.plan, consolidated, a.notes)
    a.equity = _equity(lines, consolidated, a.notes)
    dva_plan, why = _dva_plan(lines)
    if dva_plan:
        jcp, div = DVA[dva_plan]
        a.jcp, a.dividends, a.dividends_source = lines[("DVA", jcp)], lines[("DVA", div)], "dva"
    else:
        a.notes["dividends"] = why
    if dividend_override is not None:
        a.jcp, a.dividends, a.dividends_source = dividend_override
    return a


def choose_dividends(
    jcp: Decimal | None,
    dividends: Decimal | None,
    source: str | None,
    fre_jcp: Decimal | None,
    fre_dividends: Decimal | None,
    fre_available_from,
    as_of=None,
) -> tuple[Decimal | None, Decimal | None, str | None]:
    """Proventos do exercício: valor manual (ou de outra fonte) > FRE > DVA.

    O FRE só vale se já tinha sido entregue em ``as_of`` (ponto no tempo). Sem nenhum, None.
    """
    if source not in (None, "dva") and jcp is not None and dividends is not None:
        return jcp, dividends, source
    if (
        fre_jcp is not None
        and fre_dividends is not None
        and (as_of is None or (fre_available_from is not None and fre_available_from <= as_of))
    ):
        return fre_jcp, fre_dividends, "fre"
    if jcp is not None and dividends is not None:
        return jcp, dividends, source or "dva"
    return None, None, None


def scale_mismatch(dva_total, fre_total, low: Decimal, high: Decimal) -> bool:
    """FRE e DVA do mesmo exercício diferem por ~1000x (ou o inverso): uma das duas fontes está
    na escala errada (a CVM mistura R$ e R$ mil) e não há como saber qual. Só vale quando as duas
    são positivas."""
    if not dva_total or not fre_total or dva_total <= 0 or fre_total <= 0:
        return False
    ratio = fre_total / dva_total
    return low <= ratio <= high or low <= 1 / ratio <= high
