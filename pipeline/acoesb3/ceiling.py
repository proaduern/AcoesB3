"""Preço teto (seção 5 da especificação). Funções puras, sem banco.

Todos os valores por ação estão na **base de ações da data-base** (``as_of``): cada exercício é
dividido pelas ações do fim do exercício (FRE) multiplicadas pelos eventos societários entre o
fim do exercício e a data-base (``YearData.shares_factor``), a mesma conta do filtro. O valor
por ação é o mesmo para todas as classes (ON, PN); a unit vale a soma das ações que a compõem.

Cada método devolve ``ok`` (com valor), ``excluded`` (regra da especificação tira o método) ou
``unavailable`` (falta dado). Dado ausente nunca vira zero.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from .fcfe import Fcfe
from .screen import YearData

D = Decimal

METHODS = ("bazin", "graham", "gordon", "multiples", "dcf")
BANDS = ("strong_buy", "buy", "hold", "expensive")


@dataclass(frozen=True)
class CeilingParams:
    bazin_rate: Decimal
    dividend_years: int
    min_valid_years: int
    tax_jcp: Decimal
    tax_dividend: Decimal
    graham_multiplier: Decimal
    lpa_years: int
    gordon_k: Decimal
    gordon_growth_years: int
    gordon_g_min: Decimal
    gordon_g_max: Decimal
    gordon_min_spread: Decimal
    multiple_years: int
    multiple_min_years: int
    k_by_methods: dict[int, int]
    band_strong: Decimal
    band_buy: Decimal
    band_hold: Decimal
    price_max_age_days: int
    financial_plans: tuple[str, ...]
    dcf_enabled: bool
    dcf_rate: Decimal
    dcf_years: int
    dcf_terminal_growth: Decimal
    dcf_history_years: int
    dcf_base_years: int
    dcf_g_min: Decimal
    dcf_g_max: Decimal

    @classmethod
    def from_config(cls, cfg: dict) -> CeilingParams:
        def num(k):
            return D(str(cfg[k]))

        return cls(
            bazin_rate=num("ceiling.bazin_rate"),
            dividend_years=int(cfg["ceiling.dividend_years"]),
            min_valid_years=int(cfg["outlier.min_valid_years"]),
            tax_jcp=num("tax.jcp"),
            tax_dividend=num("tax.dividend"),
            graham_multiplier=num("ceiling.graham_multiplier"),
            lpa_years=int(cfg["ceiling.lpa_years"]),
            gordon_k=num("ceiling.gordon_k"),
            gordon_growth_years=int(cfg["ceiling.gordon_growth_years"]),
            gordon_g_min=num("ceiling.gordon_g_min"),
            gordon_g_max=num("ceiling.gordon_g_max"),
            gordon_min_spread=num("ceiling.gordon_min_spread"),
            multiple_years=int(cfg["ceiling.multiple_years"]),
            multiple_min_years=int(cfg["ceiling.multiple_min_years"]),
            k_by_methods={int(n): int(k) for n, k in cfg["ceiling.k_by_methods"].items()},
            band_strong=num("ceiling.band_strong"),
            band_buy=num("ceiling.band_buy"),
            band_hold=num("ceiling.band_hold"),
            price_max_age_days=int(cfg["ceiling.price_max_age_days"]),
            financial_plans=tuple(cfg["ceiling.financial_plans"]),
            dcf_enabled=bool(cfg["ceiling.dcf_enabled"]),
            dcf_rate=num("ceiling.dcf_rate"),
            dcf_years=int(cfg["ceiling.dcf_years"]),
            dcf_terminal_growth=num("ceiling.dcf_terminal_growth"),
            dcf_history_years=int(cfg["ceiling.dcf_history_years"]),
            dcf_base_years=int(cfg["ceiling.dcf_base_years"]),
            dcf_g_min=num("ceiling.dcf_g_min"),
            dcf_g_max=num("ceiling.dcf_g_max"),
        )


@dataclass
class MethodResult:
    method: str
    status: str  # ok | excluded | unavailable
    value: Decimal | None = None  # R$ por ação, na base de ações da data-base
    reason: str | None = None
    inputs: dict = field(default_factory=dict)


@dataclass
class Consolidated:
    status: str  # ok | insufficient
    ceiling: Decimal | None  # mediana dos métodos aplicáveis (por ação)
    methods_ok: int
    k_required: int | None


@dataclass
class ClassValuation:
    ticker: str
    kind: str  # on | pn | unit
    multiplier: int  # ações por papel (units: soma da composição)
    price: Decimal
    price_date: date
    ceiling: Decimal | None
    ratio: Decimal | None  # preço / teto
    votes: int  # métodos cujo teto fica acima do preço
    k_required: int | None
    band: str | None
    buy: bool


# --- Por ação ---------------------------------------------------------------


def _per_share(value: Decimal | None, y: YearData) -> Decimal | None:
    """Valor total do exercício por ação, na base de ações da data-base."""
    if value is None or not y.shares:
        return None
    return value / y.shares / y.shares_factor


def _gross(y: YearData) -> Decimal | None:
    if y.jcp is None or y.dividends is None:
        return None
    return y.jcp + y.dividends


def _net(y: YearData, p: CeilingParams) -> Decimal | None:
    if y.jcp is None or y.dividends is None:
        return None
    return y.jcp * (1 - p.tax_jcp) + y.dividends * (1 - p.tax_dividend)


def _s(d: dict) -> dict:
    return {str(k): str(v) for k, v in d.items()}


def _unavailable(method: str, reason: str, **inputs) -> MethodResult:
    return MethodResult(method, "unavailable", None, reason, inputs)


def _excluded(method: str, reason: str, **inputs) -> MethodResult:
    return MethodResult(method, "excluded", None, reason, inputs)


def _window(years: dict[int, YearData], last: int, n: int) -> tuple[range, list[int]]:
    keys = range(last - n + 1, last + 1)
    return keys, [k for k in keys if k not in years]


def is_financial(plan: str | None, p: CeilingParams) -> bool:
    return plan in p.financial_plans


# --- Dividendo médio líquido por ação (Bazin e Gordon) ------------------------


def mean_net_dps(
    years: dict[int, YearData], last: int, p: CeilingParams
) -> tuple[Decimal | None, dict]:
    """Média do dividendo líquido por ação nos ``dividend_years`` últimos exercícios, sem os anos
    de outlier. Devolve (média, entradas); média None quando indisponível (``inputs['reason']``)."""
    keys, missing = _window(years, last, p.dividend_years)
    if missing:
        return None, {"reason": "faltam exercícios", "missing_years": missing}
    dps, no_data, outliers = {}, [], []
    for k in keys:
        y = years[k]
        if y.outlier:
            outliers.append(k)
            continue
        v = _per_share(_net(y, p), y)
        if v is None:
            no_data.append(k)
        else:
            dps[k] = v
    if no_data:
        return None, {"reason": "falta provento ou ações", "missing_years": no_data}
    if len(dps) < p.min_valid_years:
        return None, {"reason": "anos válidos insuficientes", "outlier_years": outliers}
    mean = sum(dps.values()) / len(dps)
    return mean, {"dps_net": _s(dps), "outlier_years": outliers, "mean": str(mean)}


def bazin(years: dict[int, YearData], last: int, p: CeilingParams) -> MethodResult:
    """Dividendo médio líquido por ação ÷ taxa (6%)."""
    mean, inputs = mean_net_dps(years, last, p)
    if mean is None:
        return _unavailable("bazin", inputs.pop("reason"), **inputs)
    if mean <= 0:
        return _unavailable("bazin", "dividendo médio líquido não positivo", **inputs)
    return MethodResult(
        "bazin", "ok", mean / p.bazin_rate, None, {**inputs, "rate": str(p.bazin_rate)}
    )


def dividend_growth(
    years: dict[int, YearData], last: int, p: CeilingParams
) -> tuple[Decimal | None, dict]:
    """Crescimento anual composto do dividendo **total** (bruto, não por ação) entre o primeiro e
    o último dos ``gordon_growth_years`` exercícios. Pontas ausentes, não positivas ou de outlier
    não permitem concluir."""
    n = p.gordon_growth_years
    keys, missing = _window(years, last, n)
    if missing:
        return None, {"reason": "faltam exercícios", "missing_years": missing}
    first = years[keys[0]]
    end = years[last]
    a, b = _gross(first), _gross(end)
    if a is None or b is None:
        return None, {"reason": "falta provento nas pontas", "years": [keys[0], last]}
    if first.outlier or end.outlier:
        return None, {"reason": "ponta da janela é outlier", "years": [keys[0], last]}
    if a <= 0 or b <= 0:
        return None, {"reason": "provento não positivo numa ponta", "years": [keys[0], last]}
    g = (b / a) ** (D(1) / D(n - 1)) - 1
    return g, {"first": str(a), "last": str(b), "first_year": keys[0], "last_year": last}


def gordon(years: dict[int, YearData], last: int, p: CeilingParams) -> MethodResult:
    """D1 ÷ (k − g): D1 = dividendo médio líquido por ação × (1 + g); g = crescimento histórico
    do dividendo total limitado a [g_min, g_max]."""
    mean, inputs = mean_net_dps(years, last, p)
    if mean is None:
        return _unavailable("gordon", inputs.pop("reason"), **inputs)
    g_raw, g_in = dividend_growth(years, last, p)
    if g_raw is None:
        return _unavailable("gordon", "crescimento: " + g_in.pop("reason"), **inputs, growth=g_in)
    g = min(max(g_raw, p.gordon_g_min), p.gordon_g_max)
    spread = p.gordon_k - g
    inputs |= {
        "g_raw": str(g_raw),
        "g": str(g),
        "k": str(p.gordon_k),
        "growth": g_in,
    }
    if spread < p.gordon_min_spread:
        return _excluded("gordon", "k − g abaixo do mínimo", **inputs)
    d1 = mean * (1 + g)
    if d1 <= 0:
        return _unavailable("gordon", "dividendo médio líquido não positivo", **inputs)
    return MethodResult("gordon", "ok", d1 / spread, None, {**inputs, "d1": str(d1)})


# --- LPA, VPA, Graham e múltiplos --------------------------------------------


def mean_lpa(
    years: dict[int, YearData], last: int, p: CeilingParams
) -> tuple[Decimal | None, dict]:
    """LPA médio dos ``lpa_years`` últimos exercícios: lucro do controlador ÷ ações do FRE."""
    keys, missing = _window(years, last, p.lpa_years)
    if missing:
        return None, {"reason": "faltam exercícios", "missing_years": missing}
    lpa, no_data = {}, []
    for k in keys:
        v = _per_share(years[k].profit, years[k])
        if v is None:
            no_data.append(k)
        else:
            lpa[k] = v
    if no_data:
        return None, {"reason": "falta lucro ou ações", "missing_years": no_data}
    mean = sum(lpa.values()) / len(lpa)
    return mean, {"lpa": _s(lpa), "lpa_mean": str(mean)}


def vpa_last(years: dict[int, YearData], last: int) -> tuple[Decimal | None, dict]:
    """VPA do último exercício: PL do controlador ÷ ações do fim do exercício, levado à base de
    ações da data-base."""
    v = _per_share(years[last].equity, years[last])
    if v is None:
        return None, {"reason": "falta PL ou ações", "year": last}
    return v, {"vpa": str(v), "vpa_year": last}


def graham(
    years: dict[int, YearData], last: int, plan: str | None, p: CeilingParams
) -> MethodResult:
    """√(22,5 × LPA médio de 3 anos × VPA). Fora: bancos e seguradoras, LPA ≤ 0, VPA ≤ 0."""
    if plan is None:
        return _unavailable("graham", "plano de contas não identificado")
    if is_financial(plan, p):
        return _excluded("graham", "banco ou seguradora", plan=plan)
    lpa, lpa_in = mean_lpa(years, last, p)
    if lpa is None:
        return _unavailable("graham", lpa_in.pop("reason"), **lpa_in)
    vpa, vpa_in = vpa_last(years, last)
    if vpa is None:
        return _unavailable("graham", vpa_in.pop("reason"), **lpa_in)
    inputs = {**lpa_in, **vpa_in, "multiplier": str(p.graham_multiplier)}
    if lpa <= 0 or vpa <= 0:
        return _excluded("graham", "LPA ou VPA não positivo", **inputs)
    return MethodResult("graham", "ok", (p.graham_multiplier * lpa * vpa).sqrt(), None, inputs)


def median_multiple(
    years: dict[int, YearData], last: int, p: CeilingParams, financial: bool
) -> tuple[Decimal | None, dict]:
    """Mediana de P/L (ou P/VP) dos exercícios da janela de ``multiple_years``: valor de mercado
    do fim do exercício ÷ lucro (ou PL). Anos de prejuízo (ou PL ≤ 0) saem; empresa com menos
    anos usa o que existe, com o mínimo ``multiple_min_years``."""
    keys = range(last - p.multiple_years + 1, last + 1)
    ratios, skipped = {}, {}
    for k in keys:
        y = years.get(k)
        if y is None:
            continue
        base = y.equity if financial else y.profit
        if y.market_cap is None or base is None:
            skipped[k] = "sem valor de mercado ou base"
        elif base <= 0:
            skipped[k] = "prejuízo" if not financial else "PL não positivo"
        else:
            ratios[k] = y.market_cap / base
    if len(ratios) < p.multiple_min_years:
        return None, {
            "reason": "anos válidos insuficientes",
            "valid_years": len(ratios),
            "skipped": skipped,
        }
    med = statistics.median(ratios.values())
    return med, {"ratios": _s(ratios), "median": str(med), "skipped": skipped}


def multiples(
    years: dict[int, YearData], last: int, plan: str | None, p: CeilingParams
) -> MethodResult:
    """Não financeiras: P/L mediano × LPA médio de 3 anos. Bancos e seguradoras: P/VP mediano ×
    VPA. Conta como um método."""
    if plan is None:
        return _unavailable("multiples", "plano de contas não identificado")
    fin = is_financial(plan, p)
    med, med_in = median_multiple(years, last, p, fin)
    if med is None:
        return _unavailable("multiples", med_in.pop("reason"), **med_in)
    if fin:
        base, base_in = vpa_last(years, last)
        kind = "P/VP"
    else:
        base, base_in = mean_lpa(years, last, p)
        kind = "P/L"
    if base is None:
        return _unavailable("multiples", base_in.pop("reason"), **med_in)
    inputs = {**med_in, **base_in, "kind": kind}
    if base <= 0:
        return _excluded("multiples", "LPA ou VPA não positivo", **inputs)
    return MethodResult("multiples", "ok", med * base, None, inputs)


def dcf(
    years: dict[int, YearData],
    last: int,
    plan: str | None,
    fcfe: dict[int, Fcfe],
    growth_override: Decimal | None,
    p: CeilingParams,
) -> MethodResult:
    """DCF do fluxo de caixa livre para o acionista (FCFE), descontado ao retorno exigido.

    Base = média do FCFE dos ``dcf_base_years`` últimos exercícios (suaviza investimentos em
    degraus). Crescimento = o informado para a empresa (``dcf_override``) ou o composto do FCFE
    entre as pontas dos ``dcf_history_years`` exercícios, limitado a [g_min, g_max]; ponta ausente
    ou não positiva e sem valor informado = indisponível. Projeta ``dcf_years`` anos e soma a
    perpetuidade (crescimento ``dcf_terminal_growth``). O valor total das ações é dividido pelas
    ações do último exercício na base de ações da data-base. Fora: bancos e seguradoras."""
    if plan is None:
        return _unavailable("dcf", "plano de contas não identificado")
    if is_financial(plan, p):
        return _excluded("dcf", "banco ou seguradora", plan=plan)
    keys, missing = _window(years, last, p.dcf_history_years)
    series, bad = {}, {}
    for k in keys:
        f = fcfe.get(k)
        if f is None or f.value is None:
            bad[k] = "sem DFC" if f is None else f.reason
        else:
            series[k] = f.value
    detail = {k: f.detail() for k, f in fcfe.items() if k in keys}
    inputs = {"fcfe": _s(series), "fcfe_detail": detail}
    if missing or bad:
        return _unavailable(
            "dcf", "FCFE indisponível em algum exercício", **inputs, missing_years=missing, why=bad
        )
    base_keys = keys[-p.dcf_base_years :]
    base = sum(series[k] for k in base_keys) / len(base_keys)
    inputs |= {"base": str(base), "base_years": list(base_keys)}
    if base <= 0:
        return _unavailable("dcf", "FCFE médio não positivo", **inputs)
    if growth_override is not None:
        g = growth_override
        inputs["growth_source"] = "informado para a empresa"
    else:
        first, end = series[keys[0]], series[last]
        if first <= 0 or end <= 0:
            return _unavailable(
                "dcf",
                "crescimento histórico indisponível: informe o crescimento da empresa",
                **inputs,
            )
        g_raw = (end / first) ** (D(1) / D(len(keys) - 1)) - 1
        g = min(max(g_raw, p.dcf_g_min), p.dcf_g_max)
        inputs |= {"growth_source": "histórico do FCFE", "g_raw": str(g_raw)}
    k_, gt = p.dcf_rate, p.dcf_terminal_growth
    inputs |= {"g": str(g), "k": str(k_), "terminal_growth": str(gt), "years": p.dcf_years}
    if k_ <= gt:
        return _excluded("dcf", "taxa de desconto não supera a perpetuidade", **inputs)
    flow, pv = base, D(0)
    for i in range(1, p.dcf_years + 1):
        flow *= 1 + g
        pv += flow / (1 + k_) ** i
    terminal = flow * (1 + gt) / (k_ - gt) / (1 + k_) ** p.dcf_years
    total = pv + terminal
    per_share = _per_share(total, years[last])
    inputs |= {"pv_projection": str(pv), "pv_terminal": str(terminal), "equity_value": str(total)}
    if per_share is None:
        return _unavailable("dcf", "faltam ações do último exercício", **inputs)
    return MethodResult("dcf", "ok", per_share, None, inputs)


def evaluate_methods(
    years: dict[int, YearData],
    plan: str | None,
    p: CeilingParams,
    fcfe: dict[int, Fcfe] | None = None,
    dcf_growth: Decimal | None = None,
) -> list[MethodResult]:
    """Os métodos de uma empresa: Bazin, Graham, Gordon, múltiplos e (se habilitado) o DCF."""
    names = ["bazin", "graham", "gordon", "multiples"] + (["dcf"] if p.dcf_enabled else [])
    if not years:
        return [_unavailable(m, "sem demonstrações") for m in names]
    last = max(years)
    out = [
        bazin(years, last, p),
        graham(years, last, plan, p),
        gordon(years, last, p),
        multiples(years, last, plan, p),
    ]
    if p.dcf_enabled:
        out.append(dcf(years, last, plan, fcfe or {}, dcf_growth, p))
    return out


# --- Consolidação, votação e faixas -----------------------------------------


def k_for(n: int, p: CeilingParams) -> int | None:
    """Votos exigidos para ``n`` métodos; None quando há menos que o mínimo configurado."""
    if n < min(p.k_by_methods):
        return None
    return p.k_by_methods[max(m for m in p.k_by_methods if m <= n)]


def consolidate(methods: list[MethodResult], p: CeilingParams) -> Consolidated:
    values = [m.value for m in methods if m.status == "ok" and m.value is not None]
    n = len(values)
    ceiling = statistics.median(values) if values else None
    k = k_for(n, p)
    return Consolidated("ok" if k is not None else "insufficient", ceiling, n, k)


def band_for(ratio: Decimal, p: CeilingParams) -> str:
    """Preço ÷ teto: < 80% compra forte; 80–100% compra; 100–120% manter; > 120% cara."""
    if ratio < p.band_strong:
        return "strong_buy"
    if ratio < p.band_buy:
        return "buy"
    if ratio <= p.band_hold:
        return "hold"
    return "expensive"


_UNIT_TOKEN = re.compile(r"(\d+)\s*(ON|PN[A-Z]?)\b", re.IGNORECASE)


def parse_unit_composition(text: str | None) -> int | None:
    """Ações por unit a partir do FCA (``"1 ON / 2 PN"`` = 3). Texto que não se reduz a
    "quantidade + classe" separadas por / + , ; e & fica indisponível (None)."""
    if not text:
        return None
    found = _UNIT_TOKEN.findall(text)
    if not found:
        return None
    rest = _UNIT_TOKEN.sub("", text)
    if re.sub(r"[\s/+,;&]|\be\b", "", rest, flags=re.IGNORECASE):
        return None
    total = sum(int(n) for n, _ in found)
    return total or None


def value_class(
    ticker: str,
    kind: str,
    multiplier: int,
    price: Decimal,
    price_date: date,
    methods: list[MethodResult],
    cons: Consolidated,
    p: CeilingParams,
) -> ClassValuation:
    """Teto e situação de um papel: o valor por ação vale para todas as classes e a unit soma as
    ações da composição. "Compra" = preço abaixo do teto (mediana) **e** abaixo do teto de pelo
    menos K métodos; com poucos métodos (``insufficient``) nunca é compra."""
    mult = D(multiplier)
    ceiling = cons.ceiling * mult if cons.ceiling is not None else None
    ratio = price / ceiling if ceiling else None
    votes = sum(
        1 for m in methods if m.status == "ok" and m.value is not None and price < m.value * mult
    )
    buy = (
        cons.status == "ok"
        and ceiling is not None
        and price < ceiling
        and cons.k_required is not None
        and votes >= cons.k_required
    )
    return ClassValuation(
        ticker, kind, multiplier, price, price_date, ceiling, ratio,
        votes, cons.k_required, band_for(ratio, p) if ratio is not None else None, buy,
    )  # fmt: skip
