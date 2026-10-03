"""Fatos anuais de uma DFP (lucro, PL, proventos, LPA, ações) por plano de contas.

Os códigos mudam de sentido entre empresa comum, banco e seguradora (docs/fontes.md).
A conta "Atribuído a Sócios da Empresa Controladora" identifica o plano:

| plano      | lucro do controlador | PL consolidado / não controlad. | JCP / dividendos (DVA)  |
|------------|----------------------|---------------------------------|-------------------------|
| comum      | DRE 3.11.01          | BPP 2.03 / 2.03.09              | 7.08.04.01 / 7.08.04.02 |
| banco      | DRE 3.09.01          | BPP 2.08 / 2.08.09              | 7.09.04.01 / 7.09.04.02 |
| seguradora | DRE 3.13.01          | BPP 2.03 / 2.03.09              | 7.11.04.01 / 7.11.04.02 |

Conferido nas linhas reais da DFP 2024 de WEG, Itaú e BB Seguridade (tests/fixtures).
Tudo o que faltar vira ``None`` (indisponível); nada é preenchido com zero.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

Lines = dict[tuple[str, str], Decimal]  # (demonstração, código da conta) -> valor em R$


@dataclass(frozen=True)
class Plan:
    name: str
    profit: str
    equity: str
    equity_nci: str
    jcp: str
    dividends: str


PLANS = {
    "comum": Plan("comum", "3.11.01", "2.03", "2.03.09", "7.08.04.01", "7.08.04.02"),
    "banco": Plan("banco", "3.09.01", "2.08", "2.08.09", "7.09.04.01", "7.09.04.02"),
    "seguradora": Plan("seguradora", "3.13.01", "2.03", "2.03.09", "7.11.04.01", "7.11.04.02"),
}
LPA_ON = ("DRE", "3.99.01.01")
LPA_PN = ("DRE", "3.99.01.02")


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
    notes: dict = field(default_factory=dict)


def detect_plan(lines: Lines, forced: str | None = None) -> tuple[str | None, str | None]:
    """Plano de contas e, se não houver, o motivo. ``forced`` vem de company_class_override."""
    if forced:
        return forced, None
    present = [p.name for p in PLANS.values() if ("DRE", p.profit) in lines]
    if len(present) == 1:
        return present[0], None
    if not present:
        return None, "sem conta de lucro atribuído aos controladores (3.09.01, 3.11.01, 3.13.01)"
    return None, f"mais de um plano de contas possível: {present}"


def extract_annual(
    lines: Lines,
    shares: tuple[int, int, int, int] | None,
    forced_plan: str | None = None,
    dividend_override: tuple[Decimal, Decimal, str] | None = None,
) -> Annual:
    """``shares``: (ordinárias, preferenciais, tesouraria ON, tesouraria PN) ou None."""
    a = Annual()
    plan_name, why = detect_plan(lines, forced_plan)
    if why:
        a.notes["plan"] = why
    a.plan = plan_name
    a.lpa_on = lines.get(LPA_ON)
    a.lpa_pn = lines.get(LPA_PN)
    if shares is not None:
        common, preferred, t_common, t_pref = shares
        a.shares_on = common - t_common
        a.shares_pn = preferred - t_pref
    else:
        a.notes["shares"] = "composicao_capital indisponível neste documento"
    if plan_name is not None:
        plan = PLANS[plan_name]
        a.profit = lines.get(("DRE", plan.profit))
        total = lines.get(("BPP", plan.equity))
        nci = lines.get(("BPP", plan.equity_nci))
        if total is not None and nci is not None:
            a.equity = total - nci
        else:
            a.notes["equity"] = f"falta BPP {plan.equity} ou {plan.equity_nci}"
        jcp = lines.get(("DVA", plan.jcp))
        div = lines.get(("DVA", plan.dividends))
        if jcp is not None and div is not None:
            a.jcp, a.dividends, a.dividends_source = jcp, div, "dva"
        else:
            a.notes["dividends"] = f"falta DVA {plan.jcp} ou {plan.dividends}"
    if dividend_override is not None:
        a.jcp, a.dividends, a.dividends_source = dividend_override
    return a
