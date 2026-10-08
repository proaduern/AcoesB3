"""Backtest (fase 4), parte com banco: coleta dos índices, sinais mensais do preço teto no ponto no
tempo, execução da estratégia (``backtest.py``), métricas (``performance.py``) e gravação.

Fluxo (``acoesb3 backtest``):
- ``benchmarks``: Ibovespa e IDIV (B3) e CDI (Banco Central) para ``benchmark_daily``.
- ``run``: ajuste. Roda os cenários só até ``validation_start - 1``; a validação não é calculada.
- ``freeze``: o usuário escolhe o cenário com os dados de ajuste.
- ``validate``: roda o cenário congelado até ``end_date`` e mede a validação **uma única vez**
  (índice único em ``backtest_run``). Se os parâmetros mudaram depois do congelamento, recusa.
"""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

import psycopg
from psycopg.types.json import Jsonb

from . import backtest as bt
from . import benchmarks as bm
from . import ceiling, fcfe, mapping
from . import performance as pf
from .compute import (
    _dumps,
    _load_fcfe,
    _load_years_context,
    _unit_compositions,
    _years_at,
)
from .http import download

D = Decimal

SURVIVORSHIP_WARNING = (
    "Viés de sobrevivência aceito (decisão de 08/10/2026): o universo é a lista acompanhada de "
    "hoje "
    "(carteira e radar), escolhida com o que se sabe agora. Empresas canceladas ou que nunca "
    "entraram na lista não aparecem, e isso tende a favorecer o resultado."
)

CONFIG_PREFIXES = (
    "backtest.", "ceiling.", "tax.", "outlier.", "fcfe.", "dividends.", "shares.", "events.",
    "market.",
)  # fmt: skip


# --- Cenários e congelamento ----------------------------------------------------------------


@dataclass(frozen=True)
class Scenario:
    name: str
    contribution: Decimal
    overrides: dict = field(default_factory=dict, compare=False, hash=False)

    def cfg(self, cfg: dict) -> dict:
        """Configuração efetiva: a base com as sobreposições do cenário."""
        return {**cfg, **self.overrides}


def scenarios_from_config(cfg: dict) -> list[Scenario]:
    return [
        Scenario(s["name"], D(str(s["contribution"])), dict(s.get("overrides", {})))
        for s in cfg["backtest.scenarios"]
    ]


def config_snapshot(cfg: dict, scenario: Scenario) -> dict:
    """Parâmetros que definem o resultado de um cenário (sem a lista de cenários em si)."""
    eff = scenario.cfg(cfg)
    snap = {
        k: v
        for k, v in sorted(eff.items())
        if k.startswith(CONFIG_PREFIXES) and k != "backtest.scenarios"
    }
    snap["scenario.contribution"] = str(scenario.contribution)
    return snap


def config_hash(snapshot: dict) -> str:
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, default=str).encode()).hexdigest()


# --- Coleta dos índices ---------------------------------------------------------------------


def load_benchmarks(conn: psycopg.Connection, cfg: dict, today: date | None = None) -> dict:
    """Ibovespa e IDIV (B3, por ano) e CDI (BCB, em janelas de 9 anos). Idempotente: arquivo sem
    mudança desde a última coleta é pulado."""
    today = today or date.today()
    first_year = int(cfg["benchmark.first_year"])
    out: dict[str, int] = {}
    for code, name in cfg["benchmark.b3_indices"].items():
        n = 0
        for year in range(first_year, today.year + 1):
            got = download(conn, f"b3_index_{code}", bm.b3_url(name, year))
            if got is None or got.content is None:
                continue
            rows = bm.parse_b3_year(json.loads(got.content), year)
            _store_benchmark(conn, code, rows, got.source_file_id)
            n += len(rows)
        out[code] = n
    series = int(cfg["benchmark.bcb_cdi_series"])
    n = 0
    for start, end in bm.bcb_windows(date(first_year, 1, 1), today):
        got = download(conn, "bcb_sgs", bm.bcb_url(series, start, end))
        if got is None or got.content is None:
            continue
        rows = bm.parse_bcb_json(got.content.decode("utf-8"))
        _store_benchmark(conn, "cdi", rows, got.source_file_id)
        n += len(rows)
    out["cdi"] = n
    conn.commit()
    return out


def _store_benchmark(conn, code: str, rows, source_file_id: int) -> None:
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO benchmark_daily (code, ref_date, value, source_file_id)"
            " VALUES (%s, %s, %s, %s)"
            " ON CONFLICT (code, ref_date) DO UPDATE SET value = EXCLUDED.value,"
            " source_file_id = EXCLUDED.source_file_id",
            [(code, d, v, source_file_id) for d, v in rows],
        )


# --- Dados do backtest ----------------------------------------------------------------------


@dataclass
class Data:
    cfg: dict
    watch: dict[int, str]  # cvm_code -> setor (segmento da lista)
    names: dict[int, str]
    ctx: object
    classes: dict[int, dict[str, str]]  # cvm -> {'on'|'pn': ticker canônico}
    other: dict[int, list[str]]  # cvm -> tickers de units
    book: bt.PriceBook
    days: list[date]
    events: dict[int, list[tuple[date, Decimal]]]
    fcfe_by_filing: dict
    growth: dict[int, Decimal]
    compositions: dict[str, str]
    payments: dict[int, list[bt.Payment]]
    cdi_rates: dict[date, Decimal]
    levels: dict[str, pf.LevelSeries]
    warnings: list[str]


def _merge_class_series(conn, sids: list[int], start: date, end: date):
    """Série de fechamento de uma classe que mudou de ticker (TRPL4 -> ISAE4): junta os papéis,
    prevalecendo o de ticker mais recente nas datas em comum. Devolve (ticker canônico, série)."""
    rows = conn.execute(
        "SELECT s.id, s.ticker, s.last_date FROM security s WHERE s.id = ANY(%s)", (sids,)
    ).fetchall()
    rows.sort(key=lambda r: r[2])  # o de último pregão mais recente por último (prevalece)
    merged: dict[date, Decimal] = {}
    for sid, _t, _l in rows:
        for d, c in conn.execute(
            "SELECT trade_date, close FROM quote_daily WHERE security_id = %s"
            " AND trade_date BETWEEN %s AND %s",
            (sid, start, end),
        ):
            merged[d] = c
    return rows[-1][1], sorted(merged.items())


def load_data(conn: psycopg.Connection, cfg: dict, end: date) -> Data:
    start = date.fromisoformat(cfg["backtest.start_date"])
    warn: list[str] = []
    watch = {c: seg for c, seg in conn.execute("SELECT cvm_code, segment FROM watchlist")}
    if not watch:
        raise RuntimeError("lista acompanhada vazia: nada a testar")
    names = {
        c: (n or str(c))
        for c, n in conn.execute(
            "SELECT cvm_code, coalesce(trade_name, name) FROM company WHERE cvm_code = ANY(%s)",
            (list(watch),),
        )
    }
    ctx = _load_years_context(conn, cfg, only=set(watch))

    series: dict[str, list[tuple[date, Decimal]]] = {}
    classes: dict[int, dict[str, str]] = defaultdict(dict)
    other: dict[int, list[str]] = defaultdict(list)
    lookback = start - timedelta(days=60)
    for cvm in watch:
        secs = ctx.by_company.get(cvm, [])
        for cls, sids in mapping.class_securities(secs).items():
            ticker, pts = _merge_class_series(conn, sids, lookback, end)
            if pts:
                series[ticker] = pts
                classes[cvm][cls] = ticker
        for sid, ticker, _vol in secs:
            if mapping.ticker_class(ticker) == "other":
                pts = [
                    (d, c)
                    for d, c in conn.execute(
                        "SELECT trade_date, close FROM quote_daily WHERE security_id = %s"
                        " AND trade_date BETWEEN %s AND %s ORDER BY trade_date",
                        (sid, lookback, end),
                    )
                ]
                if pts:
                    series[ticker] = pts
                    other[cvm].append(ticker)
    book = bt.PriceBook(series)

    days = [
        r[0]
        for r in conn.execute(
            "SELECT DISTINCT trade_date FROM quote_daily WHERE trade_date BETWEEN %s AND %s"
            " ORDER BY 1",
            (start, end),
        )
    ]
    events: dict[int, list[tuple[date, Decimal]]] = defaultdict(list)
    for cvm, d, f in conn.execute(
        "SELECT cvm_code, event_date, factor FROM company_event WHERE cvm_code = ANY(%s)"
        " ORDER BY event_date",
        (list(watch),),
    ):
        events[cvm].append((d, f))

    filing_ids = sorted({r[0] for rows in ctx.by_cvm.values() for r in rows})
    rules = fcfe.FcfeRules.from_config(cfg)
    fc = _load_fcfe(conn, filing_ids, rules) if filing_ids else {}
    growth = dict(conn.execute("SELECT cvm_code, growth FROM dcf_growth_override"))
    compositions = _unit_compositions(conn, end)

    payments = _load_payments(conn, cfg, ctx, events, warn)

    cdi_rates = {
        d: v / 100
        for d, v in conn.execute("SELECT ref_date, value FROM benchmark_daily WHERE code = 'cdi'")
    }
    levels = {}
    for code in ("ibov", "idiv"):
        levels[code] = pf.LevelSeries(
            conn.execute(
                "SELECT ref_date, value FROM benchmark_daily WHERE code = %s", (code,)
            ).fetchall()
        )
    levels["cdi"] = pf.LevelSeries(bm.cumulative_index(cdi_rates).items())
    for code, s in levels.items():
        if not s:
            raise RuntimeError(f"índice {code} ausente: rode `acoesb3 backtest benchmarks`")
    return Data(
        cfg, watch, names, ctx, dict(classes), dict(other), book, days, dict(events), fc, growth,
        compositions, payments, cdi_rates, levels, warn,
    )  # fmt: skip


def _load_payments(conn, cfg, ctx, events, warn) -> dict[int, list[bt.Payment]]:
    """Proventos de cada exercício (versão mais recente de cada um), com as datas do FRE."""
    jcp_kinds = set(cfg["fre.jcp_kinds"])
    best: dict[tuple[int, date], tuple[date, int]] = {}
    for cvm, end, fid, received in conn.execute(
        """
        SELECT f.cvm_code, d.exercise_end, f.id, f.received_date
        FROM fre_dividend d JOIN filing f ON f.id = d.filing_id
        WHERE f.cvm_code = ANY(%s) GROUP BY 1, 2, 3, 4
        """,
        (list(ctx.by_cvm),),
    ):
        key = (cvm, end)
        if key not in best or (received, fid) > best[key]:
            best[key] = (received, fid)
    lines: dict[tuple[int, date], list[bt.FreLine]] = defaultdict(list)
    fid_key = {fid: key for key, (_r, fid) in best.items()}
    if fid_key:
        for fid, end, kind, amount, paid in conn.execute(
            "SELECT filing_id, exercise_end, kind, amount, paid_on FROM fre_dividend"
            " WHERE filing_id = ANY(%s)",
            (list(fid_key),),
        ):
            key = fid_key[fid]
            if key[1] == end:
                lines[key].append((kind in jcp_kinds, amount, paid))
    timing = cfg["backtest.dividend_timing"]
    if timing not in bt.DIVIDEND_TIMINGS:
        raise ValueError(f"backtest.dividend_timing inválido: {timing}")
    out: dict[int, list[bt.Payment]] = defaultdict(list)
    missing = 0
    today = date.today()
    for cvm in ctx.by_cvm:
        years, _plans = _years_at(ctx, cvm, today)
        for y in years.values():
            pays = bt.payments_for_year(
                y.reference_date, y.shares, y.jcp, y.dividends, y.received_date,
                lines.get((cvm, y.reference_date), []), events.get(cvm, []), timing,
            )  # fmt: skip
            if not pays and timing != "none":
                missing += 1
            out[cvm].extend(pays)
    if missing:
        warn.append(
            f"{missing} exercícios sem proventos utilizáveis (sem dado ou sem ações): "
            "o retorno total fica subestimado nesses anos."
        )
    return dict(out)


# --- Sinais mensais ---------------------------------------------------------------------------


def build_signals(
    data: Data, cfg: dict, decision_days: list[date]
) -> dict[date, list[bt.Candidate]]:
    """Situação de cada papel em cada data de decisão, só com o que se conhecia nela: DFP entregues
    até a data, ações e eventos conhecidos e o fechamento do dia. Reutiliza os métodos do preço
    teto (``ceiling.py``) e a mesma votação K."""
    p = ceiling.CeilingParams.from_config(cfg)
    max_age = int(cfg["backtest.price_max_age_days"])
    rules_growth = data.growth
    out: dict[date, list[bt.Candidate]] = {}
    for d in decision_days:
        cands: list[bt.Candidate] = []
        for cvm, sector in data.watch.items():
            years, plans = _years_at(data.ctx, cvm, d)
            if not years:
                continue
            last = max(years)
            by_year = {
                y: data.fcfe_by_filing[v.filing_id]
                for y, v in years.items()
                if v.filing_id in data.fcfe_by_filing
            }
            methods = ceiling.evaluate_methods(
                years, plans.get(last), p, by_year, rules_growth.get(cvm)
            )
            cons = ceiling.consolidate(methods, p)
            tickers = [
                (t, "on" if c == "on" else "pn", 1) for c, t in data.classes.get(cvm, {}).items()
            ]
            for ticker in data.other.get(cvm, []):
                mult = ceiling.parse_unit_composition(data.compositions.get(ticker))
                if mult is not None:
                    tickers.append((ticker, "unit", mult))
            for ticker, kind, mult in tickers:
                price = data.book.at(ticker, d, max_age)
                if price is None:
                    continue
                v = ceiling.value_class(ticker, kind, mult, price, d, methods, cons, p)
                cands.append(bt.Candidate(cvm, ticker, sector, price, v.ratio, v.buy))
        out[d] = cands
    return out


# --- Execução e métricas -------------------------------------------------------------------------


def simulate_scenario(
    data: Data,
    cfg: dict,
    scenario: Scenario,
    end: date,
    signals_cache: dict[str, dict[date, list[bt.Candidate]]],
):
    """Roda a estratégia líquida (custos e impostos) e a bruta (sem eles) até ``end``."""
    eff = scenario.cfg(cfg)
    start = date.fromisoformat(cfg["backtest.start_date"])
    days = [d for d in data.days if start <= d <= end]
    decisions = pf.month_ends(days)
    key = json.dumps(
        {k: v for k, v in sorted(eff.items()) if k.startswith("ceiling.")}, default=str
    ) + str(end)
    if key not in signals_cache:
        signals_cache[key] = build_signals(data, eff, decisions)
    signals = signals_cache[key]
    max_age = int(eff["backtest.price_max_age_days"])
    runs = {}
    for label, flags in (("net", {}), ("gross", {"apply_costs": False, "apply_taxes": False})):
        params = bt.BacktestParams.from_config(eff, scenario.contribution, **flags)
        runs[label] = bt.simulate(
            params, days, signals, data.book, data.events, data.payments,
            {d: r for d, r in data.cdi_rates.items()}, max_age,
        )  # fmt: skip
    return runs, days


def segment_metrics(
    cfg: dict,
    levels: dict[str, pf.LevelSeries],
    start: date,
    end: date,
    window_end_min: date | None,
) -> dict:
    """Medidas de cada série no período e critério de morte contra o IDIV."""
    stats = {name: pf.period_stats(s, start, end) for name, s in levels.items()}
    years = int(cfg["backtest.window_years"])
    starts = pf.month_starts(levels["strategy_net"].dates)
    windows = {}
    for ref in ("idiv", "ibov", "cdi"):
        ws = pf.rolling_windows(
            levels["strategy_net"], levels[ref], starts, years, window_end_min, end
        )
        windows[ref] = {
            "windows": len(ws),
            "lost": sum(w.lost for w in ws),
            "lost_share": (sum(w.lost for w in ws) / len(ws)) if ws else None,
        }
    ws_idiv = pf.rolling_windows(
        levels["strategy_net"], levels["idiv"], starts, years, window_end_min, end
    )
    s, i = stats.get("strategy_net"), stats.get("idiv")
    death = pf.death_check(
        ws_idiv,
        s["max_drawdown"] if s else None,
        i["max_drawdown"] if i else None,
        float(cfg["backtest.death_lost_share"]),
        float(cfg["backtest.death_drawdown_pp"]),
    )
    return {"start": start.isoformat(), "end": end.isoformat(), "series": stats,
            "windows": windows, "death": death}  # fmt: skip


def _flows(res: bt.SimResult, label: str) -> dict:
    last = max(res.nav) if res.nav else None
    buys = [t for t in res.trades if t.side == "buy"]
    return {
        f"{label}_invested": res.invested,
        f"{label}_final_value": res.nav[last] if last else None,
        f"{label}_fees": res.fees,
        f"{label}_taxes": res.taxes,
        f"{label}_dividends": res.dividends,
        f"{label}_trades": len(res.trades),
        f"{label}_first_buy": buys[0].day.isoformat() if buys else None,
        f"{label}_final_positions": {
            t: format(q, "f") for t, q in sorted(res.final_positions.items())
        },
    }


def _levels(data: Data, runs) -> dict[str, pf.LevelSeries]:
    return {
        "strategy_net": pf.LevelSeries(runs["net"].cota.items()),
        "strategy_gross": pf.LevelSeries(runs["gross"].cota.items()),
        "ibov": data.levels["ibov"],
        "idiv": data.levels["idiv"],
        "cdi": data.levels["cdi"],
    }


def universe_info(data: Data) -> dict:
    return {
        "companies": {
            str(c): {"name": data.names.get(c), "segment": s} for c, s in data.watch.items()
        },
        "survivorship_warning": SURVIVORSHIP_WARNING,
    }


def run_warnings(data: Data, runs, cfg: dict) -> list[str]:
    out = [SURVIVORSHIP_WARNING, *data.warnings]
    out.append(
        f"Retorno total: o COTAHIST não traz ajuste por proventos; os proventos vêm da DVA/FRE "
        f"(modo {cfg['backtest.dividend_timing']}) e são creditados em caixa, sem reinvestimento "
        "automático além do aporte mensal."
    )
    out.append(
        "Custos: corretagem e taxas da B3 conforme `backtest.b3_fee_schedule` (tabela vigente; a "
        "de "
        "anos anteriores não foi verificada). Imposto: 15% sobre ganho de capital com isenção de "
        "R$ 20 mil de vendas/mês e compensação de prejuízo; sem IRRF 'dedo-duro' (0,005%)."
    )
    if runs["net"].unfilled_cash_days:
        out.append(
            f"{runs['net'].unfilled_cash_days} meses sem compra (sem papel elegível): o aporte "
            "ficou em caixa rendendo CDI."
        )
    out.extend(runs["net"].warnings[:20])
    return out


def _monthly_rows(run_id: int, levels: dict[str, pf.LevelSeries], days: list[date]):
    rows = []
    for d in pf.month_ends(days):
        for name, s in levels.items():
            v = s.at(d)
            if v is not None:
                rows.append((run_id, d, name, v))
    return rows


def store_run(
    conn: psycopg.Connection,
    kind: str,
    scenario: Scenario,
    cfg: dict,
    data: Data,
    runs,
    days: list[date],
    metrics: dict,
    freeze_id: int | None = None,
) -> int:
    snap = config_snapshot(cfg, scenario)
    run_id = conn.execute(
        "INSERT INTO backtest_run (kind, scenario, freeze_id, cfg_hash, config, start_date,"
        " end_date, universe, metrics, warnings)"
        " VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING id",
        (
            kind, scenario.name, freeze_id, config_hash(snap), Jsonb(snap, dumps=_dumps),
            days[0], days[-1], Jsonb(universe_info(data), dumps=_dumps),
            Jsonb(metrics, dumps=_dumps), Jsonb(run_warnings(data, runs, cfg), dumps=_dumps),
        ),
    ).fetchone()[0]  # fmt: skip
    levels = _levels(data, runs)
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO backtest_series (run_id, ref_date, series, value) VALUES (%s, %s, %s, %s)",
            _monthly_rows(run_id, levels, days),
        )
        cur.executemany(
            "INSERT INTO backtest_trade (run_id, seq, trade_date, ticker, side, quantity, price,"
            " fee, tax, note) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            [
                (run_id, i, t.day, t.ticker, t.side, t.qty, t.price, t.fee, t.tax, t.note)
                for i, t in enumerate(runs["net"].trades)
            ],
        )
    return run_id


# --- Comandos ------------------------------------------------------------------------------------


def fit_end(cfg: dict) -> date:
    return date.fromisoformat(cfg["backtest.validation_start"]) - timedelta(days=1)


def run_fit(conn: psycopg.Connection, cfg: dict, only: list[str] | None = None) -> dict:
    """Ajuste: cada cenário roda até ``validation_start - 1``. A validação não é calculada."""
    scenarios = [s for s in scenarios_from_config(cfg) if not only or s.name in only]
    if not scenarios:
        raise RuntimeError("nenhum cenário selecionado")
    end = fit_end(cfg)
    data = load_data(conn, cfg, end)
    start = date.fromisoformat(cfg["backtest.start_date"])
    cache: dict = {}
    summary = {}
    for sc in scenarios:
        runs, days = simulate_scenario(data, cfg, sc, end, cache)
        metrics = {
            "fit": segment_metrics(sc.cfg(cfg), _levels(data, runs), start, end, None),
            "flows": {**_flows(runs["net"], "net"), **_flows(runs["gross"], "gross")},
        }
        conn.execute(
            "DELETE FROM backtest_run WHERE kind = 'fit' AND scenario = %s AND cfg_hash = %s",
            (sc.name, config_hash(config_snapshot(cfg, sc))),
        )
        rid = store_run(conn, "fit", sc, cfg, data, runs, days, metrics)
        conn.commit()
        summary[sc.name] = {"run_id": rid, **brief(metrics["fit"])}
    return summary


def brief(seg: dict) -> dict:
    s = seg["series"]
    pick = lambda name, k: (s.get(name) or {}).get(k)  # noqa: E731
    return {
        "net_cagr": pick("strategy_net", "cagr"),
        "gross_cagr": pick("strategy_gross", "cagr"),
        "idiv_cagr": pick("idiv", "cagr"),
        "ibov_cagr": pick("ibov", "cagr"),
        "cdi_cagr": pick("cdi", "cagr"),
        "net_mdd": pick("strategy_net", "max_drawdown"),
        "idiv_mdd": pick("idiv", "max_drawdown"),
        "death": seg["death"],
    }


def freeze(conn: psycopg.Connection, cfg: dict, scenario_name: str, note: str | None) -> dict:
    if conn.execute("SELECT 1 FROM backtest_run WHERE kind = 'validation'").fetchone():
        raise RuntimeError("a validação já foi medida; os parâmetros não podem mais ser congelados")
    sc = next((s for s in scenarios_from_config(cfg) if s.name == scenario_name), None)
    if sc is None:
        raise RuntimeError(f"cenário desconhecido: {scenario_name}")
    if not conn.execute(
        "SELECT 1 FROM backtest_run WHERE kind = 'fit' AND scenario = %s AND cfg_hash = %s",
        (sc.name, config_hash(config_snapshot(cfg, sc))),
    ).fetchone():
        raise RuntimeError("rode o ajuste (`backtest run`) com estes parâmetros antes de congelar")
    snap = config_snapshot(cfg, sc)
    fid = conn.execute(
        "INSERT INTO backtest_freeze (scenario, cfg_hash, config, note) VALUES (%s, %s, %s, %s)"
        " RETURNING id",
        (sc.name, config_hash(snap), Jsonb(snap, dumps=_dumps), note),
    ).fetchone()[0]
    conn.commit()
    return {"freeze_id": fid, "scenario": sc.name, "cfg_hash": config_hash(snap)}


def validate(conn: psycopg.Connection, cfg: dict) -> dict:
    """Mede a validação uma única vez, com o cenário congelado e sem nenhum reajuste."""
    if conn.execute("SELECT 1 FROM backtest_run WHERE kind = 'validation'").fetchone():
        raise RuntimeError("a validação já foi medida uma vez; não se repete (sem reajuste)")
    fz = conn.execute(
        "SELECT id, scenario, cfg_hash FROM backtest_freeze ORDER BY id DESC LIMIT 1"
    ).fetchone()
    if fz is None:
        raise RuntimeError("nenhum cenário congelado: rode `backtest freeze` primeiro")
    fid, name, frozen_hash = fz
    sc = next((s for s in scenarios_from_config(cfg) if s.name == name), None)
    if sc is None or config_hash(config_snapshot(cfg, sc)) != frozen_hash:
        raise RuntimeError(
            "os parâmetros mudaram depois do congelamento; restaure-os "
            "(a validação não admite reajuste)"
        )
    end = date.fromisoformat(cfg["backtest.end_date"])
    split = fit_end(cfg)
    start = date.fromisoformat(cfg["backtest.start_date"])
    data = load_data(conn, cfg, end)
    runs, days = simulate_scenario(data, cfg, sc, end, {})
    levels = _levels(data, runs)
    eff = sc.cfg(cfg)
    metrics = {
        "fit": segment_metrics(eff, levels, start, split, None),
        "validation": segment_metrics(eff, levels, split + timedelta(days=1), end, split),
        "flows": {**_flows(runs["net"], "net"), **_flows(runs["gross"], "gross")},
    }
    rid = store_run(conn, "validation", sc, cfg, data, runs, days, metrics, freeze_id=fid)
    conn.commit()
    return {"run_id": rid, "scenario": name, "validation": brief(metrics["validation"])}


def report(conn: psycopg.Connection) -> list[dict]:
    """Última execução de ajuste de cada cenário e a validação, se já medida."""
    rows = conn.execute(
        """
        SELECT DISTINCT ON (kind, scenario) id, kind, scenario, created_at, metrics, warnings
        FROM backtest_run ORDER BY kind, scenario, created_at DESC
        """
    ).fetchall()
    return [
        {"id": r[0], "kind": r[1], "scenario": r[2], "created_at": r[3], "metrics": r[4],
         "warnings": r[5]}
        for r in rows
    ]  # fmt: skip
