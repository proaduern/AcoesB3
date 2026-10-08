"""Medidas de desempenho do backtest e critério de morte (seção 8 da especificação). Puro.

Todas as séries são níveis (cota da estratégia, índices, CDI acumulado) por data; o retorno de um
período é a razão entre o nível do fim e o do início.
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from dataclasses import dataclass
from datetime import date


class LevelSeries:
    """Níveis ordenados por data, com busca do último nível até uma data."""

    def __init__(self, points):
        pts = sorted(points)
        self.dates: list[date] = [d for d, _ in pts]
        self.values: list[float] = [float(v) for _, v in pts]

    def __bool__(self) -> bool:
        return bool(self.dates)

    def at(self, d: date) -> float | None:
        """Último nível em ou antes de ``d``."""
        i = bisect_right(self.dates, d) - 1
        return self.values[i] if i >= 0 else None

    def date_at(self, d: date) -> date | None:
        i = bisect_right(self.dates, d) - 1
        return self.dates[i] if i >= 0 else None

    def between(self, start: date, end: date) -> list[tuple[date, float]]:
        """Pontos com ``start <= data <= end``."""
        i, j = bisect_left(self.dates, start), bisect_right(self.dates, end)
        return list(zip(self.dates[i:j], self.values[i:j], strict=True))


@dataclass
class Drawdown:
    depth: float  # queda máxima (fração positiva: 0,35 = queda de 35%)
    peak: date | None
    trough: date | None


def max_drawdown(points: list[tuple[date, float]]) -> Drawdown:
    peak_val, peak_date = None, None
    worst = 0.0
    out = Drawdown(0.0, None, None)
    for d, v in points:
        if peak_val is None or v > peak_val:
            peak_val, peak_date = v, d
        dd = 1 - v / peak_val if peak_val else 0.0
        if dd > worst:
            worst = dd
            out = Drawdown(dd, peak_date, d)
    return out


def period_stats(s: LevelSeries, start: date, end: date) -> dict | None:
    """Retorno, retorno anualizado, volatilidade e queda máxima de ``s`` entre ``start`` e ``end``.

    O nível-base é o último antes de ``start`` (ou o primeiro disponível, se a série começa depois),
    de modo que o retorno do primeiro dia do período conta. None se a série não cobre o período."""
    if not s:
        return None
    base_date = s.date_at(date.fromordinal(start.toordinal() - 1))
    pts = s.between(start, end)
    if base_date is None:
        if not pts:
            return None
        base_date, base = pts[0]
        pts = pts[1:]
    else:
        base = s.at(base_date)
    if not pts or not base:
        return None
    path = [(base_date, base), *pts]
    last_date, last = path[-1]
    years = (last_date - base_date).days / 365.25
    total = last / base - 1
    rets = [math.log(b[1] / a[1]) for a, b in zip(path, path[1:], strict=False) if a[1] > 0]
    vol = None
    if len(rets) > 2:
        mean = sum(rets) / len(rets)
        var = sum((r - mean) ** 2 for r in rets) / (len(rets) - 1)
        vol = math.sqrt(var) * math.sqrt(252)
    dd = max_drawdown(path)
    return {
        "from": base_date.isoformat(),
        "to": last_date.isoformat(),
        "total_return": total,
        "cagr": (last / base) ** (1 / years) - 1 if years > 0.25 else None,
        "volatility": vol,
        "max_drawdown": dd.depth,
        "drawdown_peak": dd.peak.isoformat() if dd.peak else None,
        "drawdown_trough": dd.trough.isoformat() if dd.trough else None,
    }


def month_starts(days: list[date]) -> list[date]:
    """Primeiro pregão de cada mês."""
    out, seen = [], set()
    for d in days:
        key = (d.year, d.month)
        if key not in seen:
            seen.add(key)
            out.append(d)
    return out


def month_ends(days: list[date]) -> list[date]:
    """Último pregão de cada mês."""
    out = []
    for i, d in enumerate(days):
        if i + 1 == len(days) or (days[i + 1].year, days[i + 1].month) != (d.year, d.month):
            out.append(d)
    return out


def add_years(d: date, years: int) -> date:
    try:
        return d.replace(year=d.year + years)
    except ValueError:  # 29/02
        return d.replace(year=d.year + years, day=28)


def _base_level(s: LevelSeries, start: date, tolerance_days: int = 10) -> float | None:
    """Nível antes de ``start``; se a série começa depois, o primeiro nível, desde que seja de no
    máximo ``tolerance_days`` dias depois (a cota nasce no primeiro dia de operação)."""
    level = s.at(date.fromordinal(start.toordinal() - 1))
    if level is None and s.dates and (s.dates[0] - start).days <= tolerance_days:
        return s.values[0]
    return level


@dataclass
class Window:
    start: date
    end: date
    strategy: float  # retorno total no período
    bench: float
    lost: bool  # a estratégia perdeu da referência


def rolling_windows(
    strategy: LevelSeries,
    bench: LevelSeries,
    starts: list[date],
    years: int,
    end_min: date | None,
    end_max: date,
) -> list[Window]:
    """Janelas de ``years`` anos que começam em cada data de ``starts`` e terminam entre
    ``end_min`` (exclusive) e ``end_max`` (inclusive). Só entram janelas que cabem nas séries."""
    out = []
    for s in starts:
        e = add_years(s, years)
        if e > end_max or (end_min is not None and e <= end_min):
            continue
        if not strategy or not bench:
            break
        s_base = _base_level(strategy, s)
        b_base = _base_level(bench, s)
        s_end, b_end = strategy.at(e), bench.at(e)
        if None in (s_base, b_base, s_end, b_end) or not s_base or not b_base:
            continue
        sr, br = s_end / s_base - 1, b_end / b_base - 1
        out.append(Window(s, e, sr, br, sr < br))
    return out


def death_check(
    windows: list[Window],
    strategy_drawdown: float | None,
    bench_drawdown: float | None,
    max_lost_share: float,
    max_extra_drawdown: float,
) -> dict:
    """Critério de morte: o retorno perde da referência (IDIV) em mais de ``max_lost_share`` das
    janelas móveis, **ou** a queda máxima é mais de ``max_extra_drawdown`` (fração) pior. Cada
    regra é None quando não há dados para avaliá-la."""
    lost_rule = None
    share = None
    if windows:
        share = sum(w.lost for w in windows) / len(windows)
        lost_rule = share > max_lost_share
    dd_rule = None
    extra = None
    if strategy_drawdown is not None and bench_drawdown is not None:
        extra = strategy_drawdown - bench_drawdown
        dd_rule = extra > max_extra_drawdown
    rules = [r for r in (lost_rule, dd_rule) if r is not None]
    return {
        "windows": len(windows),
        "lost_windows": sum(w.lost for w in windows),
        "lost_share": share,
        "windows_rule_triggered": lost_rule,
        "extra_drawdown": extra,
        "drawdown_rule_triggered": dd_rule,
        "triggered": any(rules) if rules else None,
    }
