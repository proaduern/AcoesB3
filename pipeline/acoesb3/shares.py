"""Quantidade de ações em uma data, a partir dos retratos do capital social do FRE. Sem banco.

Cada documento do FRE (a versão guardada) traz o capital da empresa no momento da entrega.
Para o fim de um exercício usa-se o retrato mais próximo no tempo e leva-se a contagem até a
data pedida pelos desdobramentos, grupamentos e bonificações conhecidos entre as duas datas.
Compras e cancelamentos de ações sem evento societário não são corrigidos (tesouraria também
não: o FRE não traz).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

PREFERRED_TYPES = ("Capital Integralizado", "Capital Emitido")


@dataclass(frozen=True)
class Snapshot:
    received: date  # entrega do documento (versão guardada)
    common: int
    preferred: int


def snapshots_from_capital(
    rows: list[tuple[int, date, str, date | None, int | None, int | None]],
) -> list[Snapshot]:
    """Um retrato por documento. ``rows``: (filing_id, entrega, tipo de capital, aprovação, ON, PN).

    Por documento vale o tipo preferido (integralizado, senão emitido) e, nele, a aprovação mais
    recente: o documento lista também mudanças de capital anteriores.
    """
    best: dict[int, tuple[int, date, tuple, Snapshot]] = {}
    for fid, received, ctype, approved, common, pref in rows:
        if ctype not in PREFERRED_TYPES or common is None or pref is None:
            continue
        key = (-PREFERRED_TYPES.index(ctype), approved or date.min)
        cur = best.get(fid)
        if cur is None or key > cur[2]:
            best[fid] = (fid, received, key, Snapshot(received, common, pref))
    return sorted((v[3] for v in best.values()), key=lambda s: s.received)


Event = tuple[date, Decimal, int | None, int | None]  # data, fator, ações antes, ações depois


def _in_snapshot(event: Event, total: int) -> bool:
    """O retrato já traz as ações novas do evento? Compara o total do retrato com as contagens
    de antes e de depois do próprio evento (o FRE pode ser entregue antes ou depois de o evento
    valer). Sem as contagens, assume que um evento anterior ao retrato já está nele."""
    _, _, before, after = event
    if before and after and total > 0:
        return abs(math.log(total / after)) < abs(math.log(total / before))
    return True


def shares_at(
    snaps: list[Snapshot],
    events: list[Event],
    d: date,
    as_of: date,
    max_gap_days: int,
) -> tuple[int, int, date] | None:
    """(ON, PN, entrega do retrato usado) em ``d``, usando só o que se conhecia em ``as_of``.

    ``events`` já filtrados pelo que era conhecido em ``as_of``. Sem retrato a ``max_gap_days``
    de ``d``, devolve None (indisponível).
    """
    usable = [
        s for s in snaps if s.received <= as_of and abs((s.received - d).days) <= max_gap_days
    ]
    if not usable:
        return None
    s = min(usable, key=lambda x: (abs((x.received - d).days), x.received < d))
    total = s.common + s.preferred
    if s.received > d:
        # retrato posterior ao fim do exercício: desfaz os eventos que ele já contém
        f = Decimal(1)
        for e in events:
            if d < e[0] <= s.received and _in_snapshot(e, total):
                f *= e[1]
        scale = Decimal(1) / f
    else:
        # retrato anterior: aplica os eventos depois dele (e os anteriores que ele ainda não tinha)
        scale = Decimal(1)
        for e in events:
            if e[0] <= d and (e[0] > s.received or not _in_snapshot(e, total)):
                scale *= e[1]
    return (round(s.common * scale), round(s.preferred * scale), s.received)
