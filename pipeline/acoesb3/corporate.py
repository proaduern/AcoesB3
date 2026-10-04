"""Detecção de desdobramentos, grupamentos e bonificações a partir da série COTAHIST.

O COTAHIST traz preços sem ajuste. Um evento aparece como salto de preço de um pregão para o
seguinte, perto de um fator simples (2, 3, 10, 1/10...). Preço sozinho não prova evento (um
tombo de 50% também é um salto), então:

- ``auto``: razão perto de um fator simples **e** mudança de DISMES **e** fator grande o
  bastante; aplicado direto.
- ``suspected``: razão limpa e fator grande, mas sem mudança de DISMES; só vale depois que o
  usuário confirma.

Bonificações pequenas (fator abaixo de 1,5) só entram como ``suspected``. O que não for
detectado não é ajustado: ver limitações em docs/fase2.md.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal


@dataclass(frozen=True)
class SplitParams:
    candidate_low: float
    candidate_high: float
    ratio_tolerance: float
    auto_min_factor: float
    max_gap_days: int
    simple_factors: tuple[float, ...]


@dataclass(frozen=True)
class Event:
    event_date: date
    factor: Decimal  # > 1: mais ações
    observed_ratio: Decimal
    dismes_changed: bool
    status: str  # 'auto' | 'suspected'


def _allowed(simple_factors) -> list[float]:
    fs = sorted(set(float(f) for f in simple_factors))
    return sorted(set(fs + [1.0 / f for f in fs]))


def snap(factor: float, allowed: list[float]) -> tuple[float, float]:
    """Fator simples mais próximo (em escala logarítmica) e o desvio relativo."""
    best = min(allowed, key=lambda a: abs(math.log(factor / a)))
    return best, abs(factor / best - 1.0)


def detect_events(quotes: list[tuple[date, Decimal, int]], p: SplitParams) -> list[Event]:
    """``quotes``: (data, fechamento, DISMES) ordenado por data, de um único papel."""
    allowed = _allowed(p.simple_factors)
    events: list[Event] = []
    for (d0, c0, dis0), (d1, c1, dis1) in zip(quotes, quotes[1:], strict=False):
        if c0 <= 0 or c1 <= 0 or (d1 - d0).days > p.max_gap_days:
            continue
        ratio = float(c1 / c0)
        if p.candidate_low < ratio < p.candidate_high:
            continue
        factor, deviation = snap(1.0 / ratio, allowed)
        if deviation > p.ratio_tolerance:
            continue
        big = max(factor, 1.0 / factor) >= p.auto_min_factor
        changed = dis0 != dis1
        if big and changed:
            status = "auto"
        elif max(factor, 1.0 / factor) >= 2:
            status = "suspected"
        elif changed:
            status = "suspected"
        else:
            continue
        events.append(
            Event(
                d1,
                Decimal(repr(round(factor, 8))),
                Decimal(repr(round(ratio, 8))),
                changed,
                status,
            )
        )
    return events


def cumulative_factor(events: list[tuple[date, Decimal]], after: date, until: date) -> Decimal:
    """Produto dos fatores dos eventos com ``after < data <= until``.

    Dividir um valor por ação publicado em ``after`` por este produto o leva à base de ações
    vigente em ``until``.
    """
    f = Decimal(1)
    for d, factor in events:
        if after < d <= until:
            f *= factor
    return f


# --- Eventos por empresa: FRE (fator oficial) + COTAHIST (data de efeito) ---------------------


@dataclass(frozen=True)
class FreEvent:
    approved_on: date
    factor: Decimal  # ações depois / antes
    known_from: date  # entrega do documento do FRE
    event_type: str
    total_before: int | None = None
    total_after: int | None = None


@dataclass(frozen=True)
class PriceEvent:
    event_date: date
    factor: Decimal
    status: str  # auto, confirmed, suspected ou manual


@dataclass(frozen=True)
class CompanyEvent:
    event_date: date
    factor: Decimal
    source: str  # fre, cotahist, manual
    date_basis: str  # cotahist (salto de preço) ou approval (data de aprovação)
    known_from: date
    event_type: str | None = None
    shares_before: int | None = None
    shares_after: int | None = None


def merge_events(
    fre_events: list[FreEvent],
    price_events: list[PriceEvent],
    coverage_end: date | None,
    window_days: int,
    tolerance: Decimal,
) -> tuple[list[CompanyEvent], list[PriceEvent]]:
    """Junta eventos do FRE e do COTAHIST de uma empresa.

    O fator vem do FRE (contagem oficial de ações); a data de efeito vem do salto de preço que
    casa com o evento (até ``window_days`` depois da aprovação, fator dentro de ``tolerance``).
    Evento do COTAHIST sem par no FRE só entra se for manual, ou se for confirmado/automático e
    posterior ao que o FRE cobre (``coverage_end``; sem cobertura, entra). Devolve também os
    eventos do COTAHIST descartados por divergirem do FRE, para revisão.
    """
    unique: dict[tuple[date, Decimal], FreEvent] = {}
    for e in fre_events:
        key = (e.approved_on, round(e.factor, 4))
        if key not in unique or e.known_from < unique[key].known_from:
            unique[key] = e
    used: set[int] = set()
    out: list[CompanyEvent] = []
    for e in sorted(unique.values(), key=lambda x: x.approved_on):
        best = None
        for i, pe in enumerate(price_events):
            if i in used or pe.status == "manual":
                continue
            lag = (pe.event_date - e.approved_on).days
            if not -10 <= lag <= window_days:
                continue
            if abs(pe.factor / e.factor - 1) > tolerance:
                continue
            if best is None or abs(lag) < best[0]:
                best = (abs(lag), i)
        if best is None:
            out.append(
                CompanyEvent(
                    e.approved_on,
                    e.factor,
                    "fre",
                    "approval",
                    e.known_from,
                    e.event_type,
                    e.total_before,
                    e.total_after,
                )  # fmt: skip
            )
            continue
        used.add(best[1])
        pe = price_events[best[1]]
        known = e.known_from
        if pe.status in ("auto", "confirmed"):
            known = min(known, pe.event_date)
        out.append(
            CompanyEvent(
                pe.event_date,
                e.factor,
                "fre",
                "cotahist",
                known,
                e.event_type,
                e.total_before,
                e.total_after,
            )  # fmt: skip
        )
    dropped: list[PriceEvent] = []
    for i, pe in enumerate(price_events):
        if i in used:
            continue
        if pe.status == "manual":
            out.append(CompanyEvent(pe.event_date, pe.factor, "manual", "cotahist", pe.event_date))
        elif pe.status in ("auto", "confirmed"):
            if coverage_end is None or pe.event_date > coverage_end:
                out.append(
                    CompanyEvent(pe.event_date, pe.factor, "cotahist", "cotahist", pe.event_date)
                )
            else:
                dropped.append(pe)
    return sorted(out, key=lambda c: c.event_date), dropped
