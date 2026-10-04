"""Filtro de empresas perenes (seção 4 da especificação). Funções puras, sem banco.

Cada critério devolve ``pass``, ``fail`` ou ``unavailable``. Dado ausente nunca vira zero:
fica ``unavailable`` com o motivo (``history``: a empresa não tem tantos anos de DFP;
``hole``: falta um ano no meio; ``data``: o ano existe mas falta a conta).
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

D = Decimal


@dataclass(frozen=True)
class ScreenParams:
    profit_window: int
    profit_min_positive: int
    roe_years: int
    roe_min: Decimal
    dividend_window: int
    dy_years: int
    dy_min: Decimal
    payout_years: int
    payout_min: Decimal
    payout_max: Decimal
    dps_window: int
    dps_max_drops: int
    dps_tolerance: Decimal
    dps_min_pairs: int
    tax_jcp: Decimal
    tax_dividend: Decimal
    outlier_multiple: Decimal
    outlier_median_years: int
    outlier_min_history: int
    min_valid_years: int
    liq_min_volume: Decimal
    liq_min_presence: Decimal
    max_data_age_days: int

    @classmethod
    def from_config(cls, cfg: dict) -> ScreenParams:
        def num(k):
            return D(str(cfg[k]))

        def integer(k):
            return int(cfg[k])

        return cls(
            profit_window=integer("screen.profit_window_years"),
            profit_min_positive=integer("screen.profit_min_positive_years"),
            roe_years=integer("screen.roe_years"),
            roe_min=num("screen.roe_min"),
            dividend_window=integer("screen.dividend_window_years"),
            dy_years=integer("screen.dy_years"),
            dy_min=num("screen.dy_min"),
            payout_years=integer("screen.payout_years"),
            payout_min=num("screen.payout_min"),
            payout_max=num("screen.payout_max"),
            dps_window=integer("screen.dps_window_years"),
            dps_max_drops=integer("screen.dps_max_drop_years"),
            dps_tolerance=num("screen.dps_drop_tolerance"),
            dps_min_pairs=integer("screen.dps_min_pairs"),
            tax_jcp=num("tax.jcp"),
            tax_dividend=num("tax.dividend"),
            outlier_multiple=num("outlier.multiple"),
            outlier_median_years=integer("outlier.median_years"),
            outlier_min_history=integer("outlier.min_history_years"),
            min_valid_years=integer("outlier.min_valid_years"),
            liq_min_volume=num("liquidity.min_avg_volume"),
            liq_min_presence=num("liquidity.min_presence"),
            max_data_age_days=integer("screen.max_data_age_days"),
        )


@dataclass
class YearData:
    """Um exercício disponível na data-base. Campos None = indisponível."""

    year: int
    reference_date: date
    filing_id: int
    received_date: date
    collected_at: datetime | None = None
    profit: Decimal | None = None
    equity: Decimal | None = None
    jcp: Decimal | None = None
    dividends: Decimal | None = None
    dividends_source: str | None = None
    market_cap: Decimal | None = None
    shares: int | None = None  # ações no fim do exercício (FRE, ajustadas por eventos)
    shares_factor: Decimal = D(1)  # eventos entre o fim do exercício e a data-base (base de shares)
    outlier: bool = False  # suspeito e não liberado pelo usuário: fora das médias


@dataclass
class Liquidity:
    avg_volume: Decimal
    presence: Decimal
    trading_days: int


@dataclass
class Criterion:
    name: str
    status: str
    value: Decimal | None = None
    threshold: str = ""
    detail: dict = field(default_factory=dict)


@dataclass
class Result:
    status: str
    data_base: date | None
    collected_at: datetime | None
    criteria: list[Criterion]


# --- Outliers ---------------------------------------------------------------


def find_outliers(
    totals: dict[int, Decimal], multiple: Decimal, median_years: int, min_history: int
) -> dict[int, tuple[Decimal, Decimal, int]]:
    """Anos com provento total > ``multiple`` x mediana dos ``median_years`` anos anteriores.

    ``totals``: ano -> JCP + dividendos brutos (só anos com dado). Devolve ano ->
    (mediana, razão, anos usados). Mediana zero não permite concluir: o ano não é marcado.
    """
    out = {}
    for y, total in totals.items():
        prev = [totals[k] for k in range(y - median_years, y) if k in totals]
        if len(prev) < min_history:
            continue
        med = statistics.median(prev)
        if med > 0 and total > multiple * med:
            out[y] = (med, total / med, len(prev))
    return out


# --- Auxiliares de janela ---------------------------------------------------


def _missing(years: dict[int, YearData], keys: range) -> tuple[list[int], str | None]:
    missing = [k for k in keys if k not in years]
    if not missing:
        return [], None
    first = min(years)
    return missing, "history" if all(k < first for k in missing) else "hole"


def _unavailable(name, threshold, reason, **detail) -> Criterion:
    return Criterion(name, "unavailable", None, threshold, {"reason": reason, **detail})


def _total(y: YearData) -> Decimal | None:
    if y.jcp is None or y.dividends is None:
        return None
    return y.jcp + y.dividends


def _net(y: YearData, p: ScreenParams) -> Decimal | None:
    if y.jcp is None or y.dividends is None:
        return None
    return y.jcp * (1 - p.tax_jcp) + y.dividends * (1 - p.tax_dividend)


def _series(years, keys, getter):
    """Valores por ano; devolve (valores, anos sem a conta)."""
    vals, no_data = {}, []
    for k in keys:
        v = getter(years[k])
        if v is None:
            no_data.append(k)
        else:
            vals[k] = v
    return vals, no_data


def _window_or_unavailable(name, threshold, years, last, n):
    keys = range(last - n + 1, last + 1)
    missing, why = _missing(years, keys)
    if missing:
        return keys, _unavailable(name, threshold, why, missing_years=missing)
    return keys, None


def _source_detail(years, keys) -> dict:
    return {"filings": {k: years[k].filing_id for k in keys if k in years}}


# --- Critérios --------------------------------------------------------------


def profit_positive(years, last, p: ScreenParams) -> Criterion:
    name, thr = "lucro_positivo", f">= {p.profit_min_positive} de {p.profit_window} anos"
    keys, bad = _window_or_unavailable(name, thr, years, last, p.profit_window)
    if bad:
        return bad
    vals, no_data = _series(years, keys, lambda y: y.profit)
    if no_data:
        return _unavailable(name, thr, "data", missing_years=no_data)
    n = sum(1 for v in vals.values() if v > 0)
    st = "pass" if n >= p.profit_min_positive else "fail"
    return Criterion(
        name,
        st,
        D(n),
        thr,
        {"profit": {k: str(v) for k, v in vals.items()}, **_source_detail(years, keys)},
    )


def roe_mean(years, last, p: ScreenParams) -> Criterion:
    """ROE = lucro do controlador / média do PL do controlador (início e fim do ano)."""
    name, thr = "roe_medio", f"> {p.roe_min}"
    keys, bad = _window_or_unavailable(name, thr, years, last, p.roe_years + 1)
    if bad:
        return bad
    roes, problems = {}, []
    for k in range(last - p.roe_years + 1, last + 1):
        profit, e1, e0 = years[k].profit, years[k].equity, years[k - 1].equity
        if profit is None or e1 is None or e0 is None:
            problems.append(k)
            continue
        avg = (e1 + e0) / 2
        if avg <= 0:
            problems.append(k)
            continue
        roes[k] = profit / avg
    if problems:
        return _unavailable(name, thr, "data", missing_years=problems)
    mean = sum(roes.values()) / len(roes)
    return Criterion(
        name,
        "pass" if mean > p.roe_min else "fail",
        mean,
        thr,
        {"roe": {k: str(v) for k, v in roes.items()}, **_source_detail(years, keys)},
    )


def dividends_every_year(years, last, p: ScreenParams) -> Criterion:
    """JCP + dividendos declarados na DVA maiores que zero em todos os anos da janela."""
    name, thr = "proventos_todos_os_anos", f"{p.dividend_window} de {p.dividend_window} anos"
    keys, bad = _window_or_unavailable(name, thr, years, last, p.dividend_window)
    if bad:
        return bad
    vals, no_data = _series(years, keys, _total)
    if no_data:
        return _unavailable(name, thr, "data", missing_years=no_data)
    paid = sum(1 for v in vals.values() if v > 0)
    return Criterion(
        name,
        "pass" if paid == p.dividend_window else "fail",
        D(paid),
        thr,
        {
            "total": {k: str(v) for k, v in vals.items()},
            "sources": {k: years[k].dividends_source for k in keys},
            **_source_detail(years, keys),
        },
    )


def _valid_years(keys, years):
    """Separa anos de outlier (fora da média) dos demais."""
    use = [k for k in keys if not years[k].outlier]
    return use, [k for k in keys if years[k].outlier]


def dy_mean(years, last, p: ScreenParams) -> Criterion:
    """DY líquido = proventos líquidos do ano / valor de mercado no fim do exercício."""
    name, thr = "dy_medio_liquido", f"> {p.dy_min}"
    keys, bad = _window_or_unavailable(name, thr, years, last, p.dy_years)
    if bad:
        return bad
    use, outliers = _valid_years(keys, years)
    dys, problems = {}, []
    for k in use:
        net, cap = _net(years[k], p), years[k].market_cap
        if net is None or cap is None or cap <= 0:
            problems.append(k)
        else:
            dys[k] = net / cap
    if problems:
        return _unavailable(name, thr, "data", missing_years=problems, outlier_years=outliers)
    if len(dys) < p.min_valid_years:
        return _unavailable(name, thr, "outliers", outlier_years=outliers)
    mean = sum(dys.values()) / len(dys)
    return Criterion(
        name,
        "pass" if mean > p.dy_min else "fail",
        mean,
        thr,
        {
            "dy": {k: str(v) for k, v in dys.items()},
            "outlier_years": outliers,
            **_source_detail(years, keys),
        },
    )


def payout_mean(years, last, p: ScreenParams) -> Criterion:
    """Payout bruto = (JCP + dividendos) / lucro do controlador. Anos de prejuízo e outliers
    ficam fora da média."""
    name, thr = "payout_medio", f"entre {p.payout_min} e {p.payout_max}"
    keys, bad = _window_or_unavailable(name, thr, years, last, p.payout_years)
    if bad:
        return bad
    use, outliers = _valid_years(keys, years)
    pays, problems, losses = {}, [], []
    for k in use:
        total, profit = _total(years[k]), years[k].profit
        if total is None or profit is None:
            problems.append(k)
        elif profit <= 0:
            losses.append(k)
        else:
            pays[k] = total / profit
    if problems:
        return _unavailable(name, thr, "data", missing_years=problems)
    if len(pays) < p.min_valid_years:
        return _unavailable(
            name, thr, "outliers_or_losses", outlier_years=outliers, loss_years=losses
        )
    mean = sum(pays.values()) / len(pays)
    ok = p.payout_min <= mean <= p.payout_max
    return Criterion(
        name,
        "pass" if ok else "fail",
        mean,
        thr,
        {
            "payout": {k: str(v) for k, v in pays.items()},
            "outlier_years": outliers,
            "loss_years": losses,
            **_source_detail(years, keys),
        },
    )


def _dps(y: YearData) -> Decimal | None:
    """Dividendo por ação do ano: total declarado / ações no fim do exercício, levado à base de
    ações da data-base pelos eventos societários posteriores. Ano de outlier não tem DPS."""
    total = _total(y)
    if y.outlier or total is None or not y.shares:
        return None
    return total / y.shares / y.shares_factor


def dps_drops(years, last, p: ScreenParams) -> Criterion:
    """Quedas do dividendo por ação na janela (ver ``_dps``).

    Comparações com ano de outlier ou sem ações são puladas; exige ``dps_min_pairs`` pares.
    """
    name = "queda_dividendo_por_acao"
    thr = f"<= {p.dps_max_drops} quedas em {p.dps_window} anos"
    keys, bad = _window_or_unavailable(name, thr, years, last, p.dps_window)
    if bad:
        return bad
    dps = {k: v for k in keys if (v := _dps(years[k])) is not None}
    pairs = [(k - 1, k) for k in keys if (k - 1) in dps and k in dps]
    if len(pairs) < p.dps_min_pairs:
        return _unavailable(name, thr, "data", comparable_pairs=len(pairs), needed=p.dps_min_pairs)
    drops = [k for a, k in pairs if dps[k] < dps[a] * (1 - p.dps_tolerance)]
    return Criterion(
        name,
        "pass" if len(drops) <= p.dps_max_drops else "fail",
        D(len(drops)),
        thr,
        {
            "dps": {k: str(v) for k, v in dps.items()},
            "drop_years": drops,
            "comparable_pairs": len(pairs),
            "sources": {k: years[k].dividends_source for k in keys},
            **_source_detail(years, keys),
        },
    )


def liquidity(liq: Liquidity | None, p: ScreenParams) -> Criterion:
    name = "liquidez"
    thr = f"volume >= {p.liq_min_volume} e presença >= {p.liq_min_presence}"
    if liq is None:
        return _unavailable(name, thr, "no_security")
    ok = liq.avg_volume >= p.liq_min_volume and liq.presence >= p.liq_min_presence
    return Criterion(
        name,
        "pass" if ok else "fail",
        liq.avg_volume,
        thr,
        {"presence": str(liq.presence), "trading_days": liq.trading_days},
    )


# --- Resultado --------------------------------------------------------------


def evaluate(
    years: dict[int, YearData],
    liq: Liquidity | None,
    p: ScreenParams,
    excluded: bool = False,
    as_of: date | None = None,
) -> Result:
    if excluded:
        return Result("excluded", None, None, [])
    if not years:
        return Result(
            "insufficient_history",
            None,
            None,
            [_unavailable("lucro_positivo", "", "history", missing_years=[])],
        )
    last = max(years)
    if as_of is not None and (as_of - years[last].reference_date).days > p.max_data_age_days:
        # A empresa parou de entregar DFP: não avaliar com dados velhos.
        return Result("stale", years[last].reference_date, None, [])
    criteria = [
        profit_positive(years, last, p),
        roe_mean(years, last, p),
        dividends_every_year(years, last, p),
        dy_mean(years, last, p),
        payout_mean(years, last, p),
        dps_drops(years, last, p),
        liquidity(liq, p),
    ]
    data_base = years[last].reference_date
    collected = max((y.collected_at for y in years.values() if y.collected_at), default=None)
    if any(c.status == "fail" for c in criteria):
        status = "rejected"
    elif any(c.status == "unavailable" for c in criteria):
        reasons = {c.detail.get("reason") for c in criteria if c.status == "unavailable"}
        status = "insufficient_history" if "history" in reasons else "insufficient_data"
    else:
        status = "approved"
    return Result(status, data_base, collected, criteria)
