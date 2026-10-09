"""Casos de paridade entre ``ceiling.py`` e o simulador em TypeScript (``web/src/lib/ceiling``).

O simulador da tela refaz o preço teto com outros parâmetros **a partir dos insumos gravados** em
``ceiling_method.inputs``, sem reler as demonstrações. Este módulo gera, sem banco, o fixture que
prova que isso dá o mesmo resultado que o Python faria com os dados brutos:

1. monta empresas sintéticas (``YearData`` e FCFE) e roda ``evaluate_methods`` com os parâmetros
   padrão: é o que o pipeline gravaria (o ``snapshot``);
2. roda de novo com os parâmetros alterados (``config``): é o ``expected``;
3. o TypeScript recebe ``snapshot`` + ``config`` e precisa chegar ao ``expected``.

Casos ``direct`` não passam por insumos: os métodos entram prontos (valores redondos) para testar a
mediana, o K, as faixas e a votação em fronteiras exatas (80%, 100% e 120% do teto).

Mudou uma regra de ``ceiling.py``? Mudar o simulador e regerar o fixture no mesmo commit:
``acoesb3 ceilings parity-export``. O teste ``test_parity.py`` falha se o arquivo versionado
estiver defasado.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

from . import ceiling
from .ceiling import CeilingParams, MethodResult
from .fcfe import Fcfe
from .screen import YearData

D = Decimal

VERSION = 1
DEFAULT_PATH = Path(__file__).resolve().parents[2] / "web" / "tests" / "parity" / "cases.json"

# Os valores padrão de app_config (migrações 0013 e 0014, mais outlier.min_valid_years e tax.*).
# Um teste com banco confere que continuam iguais aos das migrações.
BASE_CONFIG: dict = {
    "ceiling.bazin_rate": "0.06",
    "ceiling.dividend_years": 5,
    "ceiling.graham_multiplier": "22.5",
    "ceiling.lpa_years": 3,
    "ceiling.gordon_k": "0.12",
    "ceiling.gordon_growth_years": 5,
    "ceiling.gordon_g_min": "0",
    "ceiling.gordon_g_max": "0.05",
    "ceiling.gordon_min_spread": "0.03",
    "ceiling.multiple_years": 10,
    "ceiling.multiple_min_years": 3,
    "ceiling.k_by_methods": {"3": 2, "4": 3, "5": 3},
    "ceiling.band_strong": "0.8",
    "ceiling.band_buy": "1.0",
    "ceiling.band_hold": "1.2",
    "ceiling.price_max_age_days": 10,
    "ceiling.financial_plans": ["banco", "seguradora"],
    "ceiling.dcf_enabled": True,
    "ceiling.dcf_rate": "0.12",
    "ceiling.dcf_years": 5,
    "ceiling.dcf_terminal_growth": "0.04",
    "ceiling.dcf_history_years": 5,
    "ceiling.dcf_base_years": 3,
    "ceiling.dcf_g_min": "0",
    "ceiling.dcf_g_max": "0.05",
    "outlier.min_valid_years": 3,
    "tax.jcp": "0.15",
    "tax.dividend": "0",
}

# Parâmetros que o simulador altera (os que agem sobre os insumos gravados). Janelas, alíquotas e
# anos mínimos mudam *quais* exercícios entram nas médias e exigem os dados brutos: ficam de fora.
DELTAS: dict[str, dict] = {
    "padrao": {},
    "bazin_8": {"ceiling.bazin_rate": "0.08"},
    "bazin_4": {"ceiling.bazin_rate": "0.04"},
    "graham_15": {"ceiling.graham_multiplier": "15"},
    "gordon_k10": {"ceiling.gordon_k": "0.10"},
    "gordon_k7_exclui": {"ceiling.gordon_k": "0.07"},
    "gordon_gmax3": {"ceiling.gordon_g_max": "0.03"},
    "gordon_gmin2": {"ceiling.gordon_g_min": "0.02"},
    "gordon_spread8": {"ceiling.gordon_min_spread": "0.08"},
    "dcf_taxa10": {"ceiling.dcf_rate": "0.10"},
    "dcf_perpetuidade3": {"ceiling.dcf_terminal_growth": "0.03"},
    "dcf_8_anos": {"ceiling.dcf_years": 8},
    "dcf_gmax3": {"ceiling.dcf_g_max": "0.03"},
    "dcf_gmin1": {"ceiling.dcf_g_min": "0.01"},
    "dcf_desligado": {"ceiling.dcf_enabled": False},
    "dcf_taxa_igual_perpetuidade": {"ceiling.dcf_rate": "0.04"},
    "dcf_crescimento_3": {"__dcf_growth": "0.03"},
    "k_tabela": {"ceiling.k_by_methods": {"3": 3, "4": 2, "5": 4}},
    "faixas": {
        "ceiling.band_strong": "0.7",
        "ceiling.band_buy": "0.95",
        "ceiling.band_hold": "1.1",
    },
    "combinado": {
        "ceiling.bazin_rate": "0.07",
        "ceiling.gordon_k": "0.11",
        "ceiling.graham_multiplier": "20",
        "ceiling.dcf_rate": "0.11",
        "ceiling.k_by_methods": {"3": 2, "4": 2, "5": 3},
    },
}

# Preço do papel em relação ao teto consolidado, longe das fronteiras das faixas (as fronteiras
# exatas ficam nos casos "direct").
PRICE_FACTORS = ["0.5", "0.85", "0.95", "1.1", "1.4"]


# --- Empresas sintéticas ----------------------------------------------------


def _year(y: int, **kw) -> YearData:
    kw.setdefault("shares", 1000)
    return YearData(
        year=y, reference_date=date(y, 12, 31), filing_id=y, received_date=date(y + 1, 3, 1), **kw
    )


JCP_SHARE = D("0.4")
MARKET_CAP_PL = D(12)
SHARES_FACTOR = D("1.4")


def _company(
    first: int = 2015,
    last: int = 2024,
    *,
    profit=None,
    equity=None,
    gross=None,
    jcp_share=JCP_SHARE,
    market_cap_pl=MARKET_CAP_PL,
    factor=SHARES_FACTOR,
    outlier_years=(),
    drop_dividends=(),
) -> dict[int, YearData]:
    """Dez exercícios: lucro, PL, proventos (JCP + dividendos) e valor de mercado, com fator de
    ações de data-base diferente de 1 (o valor por ação passa por ele)."""
    n = last - first + 1
    profit = profit or [800 + 75 * i for i in range(n)]
    equity = equity or [8000 + 600 * i for i in range(n)]
    gross = gross or [250 + 20 * i for i in range(n)]
    out = {}
    for i, y in enumerate(range(first, last + 1)):
        total = D(gross[i])
        out[y] = _year(
            y,
            profit=D(profit[i]) if profit[i] is not None else None,
            equity=D(equity[i]),
            jcp=None if y in drop_dividends else total * jcp_share,
            dividends=None if y in drop_dividends else total * (1 - jcp_share),
            market_cap=D(profit[i]) * market_cap_pl if profit[i] is not None else None,
            shares_factor=factor,
            outlier=y in outlier_years,
        )
    return out


def _flows(values) -> dict[int, Fcfe]:
    return {
        2020 + i: Fcfe(None, "sem DFC detalhado") if v is None else Fcfe(D(v))
        for i, v in enumerate(values)
    }


def fixtures() -> list[dict]:
    """(nome, exercícios, plano, FCFE, crescimento do DCF informado no snapshot)."""
    div_flat = [300, 300, 305, 306, 309]
    out = [
        {
            "name": "comum_completo",
            "years": _company(gross=[200, 210, 220, 235, 250, 300, 320, 350, 390, 430]),
            "plan": "comum",
            "fcfe": _flows([900, 950, 1000, 1100, 1200]),
        },
        {
            "name": "comum_dividendo_estavel",
            "years": _company(gross=[300] * 5 + div_flat),
            "plan": "comum",
            "fcfe": _flows([1000] * 5),
        },
        {
            "name": "dcf_pede_crescimento",
            "years": _company(),
            "plan": "comum",
            "fcfe": _flows([-100, 500, 600, 700, 800]),
        },
        {
            "name": "dcf_crescimento_informado",
            "years": _company(),
            "plan": "comum",
            "fcfe": _flows([-100, 500, 600, 700, 800]),
            "dcf_growth": D("0.02"),
        },
        {
            "name": "banco",
            "years": _company(equity=[9000 + 700 * i for i in range(10)], market_cap_pl=D(9)),
            "plan": "banco",
            "fcfe": {},
        },
        {
            "name": "prejuizo_nos_ultimos_anos",
            "years": _company(profit=[800 + 50 * i for i in range(7)] + [-200, -150, -100]),
            "plan": "comum",
            "fcfe": _flows([900, 950, 1000, 1100, 1200]),
        },
        {
            "name": "ano_de_outlier",
            "years": _company(
                gross=[200, 210, 220, 235, 250, 300, 2200, 350, 390, 430], outlier_years=(2021,)
            ),
            "plan": "comum",
            "fcfe": _flows([900, 950, 1000, 1100, 1200]),
        },
        {
            "name": "dois_metodos_dados_insuficientes",
            "years": _company(profit=[None] * 10),
            "plan": "comum",
            "fcfe": {},
        },
        {
            "name": "dividendo_faltando",
            "years": _company(drop_dividends=(2022,)),
            "plan": "comum",
            "fcfe": _flows([900, 950, 1000, 1100, 1200]),
        },
        {"name": "sem_demonstracoes", "years": {}, "plan": "comum", "fcfe": {}},
        {
            "name": "plano_nao_identificado",
            "years": _company(),
            "plan": None,
            "fcfe": _flows([900, 950, 1000, 1100, 1200]),
        },
    ]
    return out


# --- Serialização -----------------------------------------------------------


def _num(v: Decimal | None) -> str | None:
    return None if v is None else format(v, "f")


def _plain(inputs: dict) -> dict:
    """Insumos como o banco os guarda (JSON), sem o detalhe longo do DCF que a tela não usa."""
    raw = json.loads(json.dumps(inputs, default=str, ensure_ascii=False))
    raw.pop("fcfe_detail", None)
    return raw


def _method_out(m: MethodResult) -> dict:
    return {"method": m.method, "status": m.status, "value": _num(m.value), "reason": m.reason}


def _snapshot_method(m: MethodResult) -> dict:
    return {**_method_out(m), "inputs": _plain(m.inputs)}


def _cons_out(c: ceiling.Consolidated) -> dict:
    return {
        "status": c.status,
        "ceiling": _num(c.ceiling),
        "methods_ok": c.methods_ok,
        "k_required": c.k_required,
    }


def _class_out(v: ceiling.ClassValuation) -> dict:
    return {
        "ticker": v.ticker,
        "ceiling": _num(v.ceiling),
        "ratio": _num(v.ratio),
        "votes": v.votes,
        "k_required": v.k_required,
        "band": v.band,
        "buy": v.buy,
    }


CLASSES = [("ALFA3", "on", 1), ("ALFA11", "unit", 3)]


def _price_for(ceiling_value: Decimal | None, mult: int, idx: int) -> Decimal:
    if ceiling_value is None or ceiling_value <= 0:
        return D("10.00")
    factor = D(PRICE_FACTORS[idx % len(PRICE_FACTORS)])
    return max((ceiling_value * mult * factor).quantize(D("0.01")), D("0.01"))


def _classes(cons, methods, p, start: int, price_date=date(2026, 10, 2)):
    rows, expected = [], []
    for j, (ticker, kind, mult) in enumerate(CLASSES):
        price = _price_for(cons.ceiling, mult, start + j)
        rows.append({"ticker": ticker, "kind": kind, "multiplier": mult, "price": _num(price)})
        expected.append(
            _class_out(ceiling.value_class(ticker, kind, mult, price, price_date, methods, cons, p))
        )
    return rows, expected


def _config_with(delta: dict) -> dict:
    cfg = json.loads(json.dumps(BASE_CONFIG))
    for k, v in delta.items():
        if not k.startswith("__"):
            cfg[k] = v
    return cfg


def _snapshot_of(fx: dict) -> dict:
    """O que o pipeline gravaria para esta empresa com os parâmetros padrão."""
    p0 = CeilingParams.from_config(BASE_CONFIG)
    snap = ceiling.evaluate_methods(fx["years"], fx["plan"], p0, fx["fcfe"], fx.get("dcf_growth"))
    return {"plan": fx["plan"], "methods": [_snapshot_method(m) for m in snap]}


def _case_from_years(fx: dict, delta_name: str, delta: dict, n: int) -> dict:
    cfg1 = _config_with(delta)
    p1 = CeilingParams.from_config(cfg1)
    growth0 = fx.get("dcf_growth")
    growth1 = D(delta["__dcf_growth"]) if "__dcf_growth" in delta else growth0

    methods1 = ceiling.evaluate_methods(fx["years"], fx["plan"], p1, fx["fcfe"], growth1)
    cons1 = ceiling.consolidate(methods1, p1)
    classes, expected_classes = _classes(cons1, methods1, p1, n)
    return {
        "name": f"{fx['name']}__{delta_name}",
        "fixture": fx["name"],
        "config": cfg1,
        "dcf_growth": _num(growth1) if "__dcf_growth" in delta else None,
        "classes": classes,
        "expected": {
            "methods": [_method_out(m) for m in methods1],
            "consolidated": _cons_out(cons1),
            "classes": expected_classes,
        },
    }


def _direct(name: str, values: list[tuple[str, str, str | None]], prices: dict, delta=None):
    """Métodos prontos (sem insumos): a mediana, o K, as faixas e os votos em valores redondos."""
    cfg = _config_with(delta or {})
    p = CeilingParams.from_config(cfg)
    methods = [
        MethodResult(m, st, None if v is None else D(v), None if st == "ok" else "motivo", {})
        for m, st, v in values
    ]
    cons = ceiling.consolidate(methods, p)
    classes, expected = [], []
    for ticker, (kind, mult, price) in prices.items():
        classes.append({"ticker": ticker, "kind": kind, "multiplier": mult, "price": price})
        expected.append(
            _class_out(
                ceiling.value_class(
                    ticker, kind, mult, D(price), date(2026, 10, 2), methods, cons, p
                )
            )
        )
    snapshot = {"plan": "comum", "methods": [_snapshot_method(m) for m in methods]}
    case = {
        "name": name,
        "fixture": name,
        "config": cfg,
        "dcf_growth": None,
        "classes": classes,
        "expected": {
            "methods": [_method_out(m) for m in methods],
            "consolidated": _cons_out(cons),
            "classes": expected,
        },
    }
    return snapshot, case


def direct_cases() -> list[dict]:
    # Teto 12 (mediana de 10, 12 e 14). Fronteiras exatas: 80% = 9,60; 100% = 12; 120% = 14,40.
    three = [("bazin", "ok", "10"), ("graham", "ok", "12"), ("gordon", "ok", "14")]
    edge = {
        "P_FORTE": ("on", 1, "7.00"),
        "P_80": ("on", 1, "9.60"),
        "P_80_ACIMA": ("on", 1, "9.61"),
        "P_99": ("on", 1, "11.99"),
        "P_100": ("on", 1, "12.00"),
        "P_120": ("on", 1, "14.40"),
        "P_120_ACIMA": ("on", 1, "14.41"),
        "U_80": ("unit", 3, "28.80"),
        "U_100": ("unit", 3, "36.00"),
        "U_120": ("unit", 3, "43.20"),
    }
    return [
        _direct("direto_3_metodos_fronteiras", three, edge),
        _direct(
            "direto_4_metodos_mediana_par",
            three + [("multiples", "ok", "16")],
            {"A3": ("on", 1, "12.50"), "A4": ("on", 1, "13.00"), "A5": ("on", 1, "11.00")},
        ),
        _direct(
            "direto_5_metodos_k3",
            three + [("multiples", "ok", "16"), ("dcf", "ok", "8")],
            {"A3": ("on", 1, "9.00"), "A4": ("on", 1, "10.50"), "A5": ("on", 1, "13.00")},
        ),
        _direct(
            "direto_dois_metodos_insuficiente",
            [("bazin", "ok", "10"), ("graham", "ok", "12"), ("gordon", "unavailable", None)],
            {"A3": ("on", 1, "5.00")},
        ),
        _direct(
            "direto_nenhum_metodo",
            [("bazin", "unavailable", None), ("graham", "excluded", None)],
            {"A3": ("on", 1, "5.00")},
        ),
        _direct(
            "direto_k_tabela_alterada",
            three,
            {"A3": ("on", 1, "9.00"), "A4": ("on", 1, "11.00")},
            {"ceiling.k_by_methods": {"3": 3, "4": 3, "5": 3}},
        ),
        _direct(
            "direto_votos_por_metodo",
            three + [("multiples", "ok", "16")],  # teto 13; preço 11 fica abaixo de 12, 14 e 16
            {"A3": ("on", 1, "11.00"), "A4": ("on", 1, "9.00")},
        ),
    ]


def build() -> tuple[dict, list[dict]]:
    """(snapshots por nome, casos). Cada snapshot é gravado uma vez e referenciado pelos casos."""
    snapshots: dict[str, dict] = {}
    cases: list[dict] = []
    n = 0
    for fx in fixtures():
        snapshots[fx["name"]] = _snapshot_of(fx)
        for name, delta in DELTAS.items():
            cases.append(_case_from_years(fx, name, delta, n))
            n += 1
    for snapshot, case in direct_cases():
        snapshots[case["fixture"]] = snapshot
        cases.append(case)
    return snapshots, cases


def render(built: tuple[dict, list[dict]] | None = None) -> str:
    """Um caso por linha (diff legível), chaves ordenadas e sem datas: a saída é determinística."""
    snapshots, cases = build() if built is None else built
    dump = lambda o: json.dumps(o, sort_keys=True, separators=(",", ":"), ensure_ascii=False)  # noqa: E731
    head = dump({"version": VERSION, "generated_by": "acoesb3 ceilings parity-export"})
    snaps = ",\n".join(f"{dump(k)}:{dump(v)}" for k, v in sorted(snapshots.items()))
    body = ",\n".join(dump(c) for c in cases)
    return f'{{"header":{head},"snapshots":{{\n{snaps}\n}},"cases":[\n{body}\n]}}\n'


def export(path: Path = DEFAULT_PATH) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    built = build()
    path.write_text(render(built), encoding="utf-8")
    return len(built[1])
