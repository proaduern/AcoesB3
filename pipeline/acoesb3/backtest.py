"""Backtest (fase 4): estratégia mensal de compra pelo preço teto, com custos e impostos.

Funções puras (sem banco). Regras da estratégia, decididas pelo usuário em 08/10/2026:
compra quando ``buy`` é verdadeiro; vende a posição inteira acima de ``sell_above`` do teto;
decisão mensal; aporte fixo; pesos pela seção 6 da especificação, com limites de ação e de setor
só depois de haver posições suficientes; custos e impostos como parâmetros.

Ponto no tempo: o sinal de uma data usa só o que se conhecia nela (quem monta os sinais garante).
A ordem é executada no fechamento do pregão seguinte ao do sinal (``exec_lag_days``).
"""

from __future__ import annotations

import math
from bisect import bisect_left, bisect_right
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import ROUND_FLOOR, Decimal

D = Decimal
ZERO = D(0)


@dataclass(frozen=True)
class BacktestParams:
    contribution: Decimal  # aporte mensal (R$)
    sell_above: Decimal  # vende a posição inteira quando preço / teto passa disto
    max_stocks: int  # no máximo N empresas por aporte
    stock_cap: Decimal  # limite por empresa (fração da carteira)
    sector_cap: Decimal  # limite por setor
    brokerage: Decimal  # corretagem (fração do valor da ordem)
    fee_schedule: tuple[tuple[date, Decimal], ...]  # (a partir de, taxas B3 sobre o valor da ordem)
    cgt_rate: Decimal  # imposto sobre o ganho de capital
    cgt_exemption: Decimal  # vendas no mês até este valor: ganho isento
    offset_losses: bool  # compensa prejuízo acumulado em meses tributáveis
    cash_earns_cdi: bool  # caixa parado rende CDI
    tax_jcp: Decimal  # IR retido na fonte sobre JCP
    tax_dividend: Decimal
    exec_lag_days: int  # pregões entre o sinal e a ordem
    apply_costs: bool = True
    apply_taxes: bool = True

    @classmethod
    def from_config(
        cls, cfg: dict, contribution: Decimal | None = None, **flags: bool
    ) -> BacktestParams:
        def num(k):
            return D(str(cfg[k]))

        schedule = tuple(
            sorted((date.fromisoformat(d), D(str(r))) for d, r in cfg["backtest.b3_fee_schedule"])
        )
        return cls(
            contribution=contribution if contribution is not None else num("backtest.contribution"),
            sell_above=num("backtest.sell_above_ratio"),
            max_stocks=int(cfg["backtest.max_stocks_per_contribution"]),
            stock_cap=num("backtest.stock_cap"),
            sector_cap=num("backtest.sector_cap"),
            brokerage=num("backtest.brokerage"),
            fee_schedule=schedule,
            cgt_rate=num("backtest.cgt_rate"),
            cgt_exemption=num("backtest.cgt_monthly_exemption"),
            offset_losses=bool(cfg["backtest.cgt_offset_losses"]),
            cash_earns_cdi=bool(cfg["backtest.cash_earns_cdi"]),
            tax_jcp=num("tax.jcp"),
            tax_dividend=num("tax.dividend"),
            exec_lag_days=int(cfg["backtest.exec_lag_days"]),
            **flags,
        )

    def fee_rate(self, day: date) -> Decimal:
        """Taxa total de uma ordem (compra ou venda) na data."""
        if not self.apply_costs:
            return ZERO
        b3 = ZERO
        for start, rate in self.fee_schedule:
            if start <= day:
                b3 = rate
        return self.brokerage + b3


# --- Dados de entrada -----------------------------------------------------------


@dataclass(frozen=True)
class Candidate:
    """Situação de um papel na data do sinal."""

    company: int
    ticker: str
    sector: str
    price: Decimal
    ratio: Decimal | None  # preço / teto; None = sem teto (nada a decidir)
    buy: bool


@dataclass(frozen=True)
class Payment:
    """Provento pago: valor bruto por ação na data de pagamento (dividendo e JCP à parte)."""

    pay_date: date
    dividend: Decimal
    jcp: Decimal


class PriceBook:
    """Fechamentos por papel, com busca do último fechamento até uma data."""

    def __init__(self, series: dict[str, list[tuple[date, Decimal]]]):
        self._dates = {t: [d for d, _ in s] for t, s in series.items()}
        self._close = {t: [c for _, c in s] for t, s in series.items()}

    def at(self, ticker: str, day: date, max_age: int | None = None) -> Decimal | None:
        dates = self._dates.get(ticker)
        if not dates:
            return None
        i = bisect_right(dates, day) - 1
        if i < 0:
            return None
        if max_age is not None and (day - dates[i]).days > max_age:
            return None
        return self._close[ticker][i]

    def exact(self, ticker: str, day: date) -> Decimal | None:
        dates = self._dates.get(ticker)
        if not dates:
            return None
        i = bisect_left(dates, day)
        return self._close[ticker][i] if i < len(dates) and dates[i] == day else None


# --- Alocação do aporte (seção 6) -------------------------------------------------


def limits_active(n_positions: int, cap: Decimal) -> bool:
    """O limite só vale quando há posições suficientes para respeitá-lo: com um teto de 10% é
    preciso ao menos 10 posições (1 / 0,10), senão nenhuma carteira o cumpriria."""
    return cap > 0 and n_positions >= math.ceil(D(1) / cap)


@dataclass
class Allocation:
    company: int
    ticker: str
    amount: Decimal
    discount: Decimal


def allocate(
    cash: Decimal,
    buys: list[Candidate],
    value_by_company: dict[int, Decimal],
    sector_of: dict[int, str],
    p: BacktestParams,
) -> list[Allocation]:
    """Reparte ``cash`` entre as empresas elegíveis.

    - ``buys``: um papel por empresa (o de menor preço / teto) com ``buy`` verdadeiro.
    - Peso-alvo igual: 1 / N. Elegível: peso abaixo de 1 / (carteira + candidatas); escolhem-se até
      ``max_stocks`` com maior desconto (1 - razão); o alvo final é 1 / (carteira + escolhidas).
    - O desconto define a parte de cada uma (proporcional), limitada ao que falta para o alvo e,
      se ativos, aos limites por empresa e por setor; a sobra de uma redistribui-se às outras.
    - O que não coube fica em caixa (quem chama decide o que fazer com ele).
    """
    if cash <= 0 or not buys:
        return []
    total = cash + sum(value_by_company.values(), ZERO)
    if total <= 0:
        return []
    held_all = set(value_by_company)
    # Escolha: quem está abaixo do peso igual de (carteira + candidatas), os de maior desconto.
    target0 = total / len(held_all | {c.company for c in buys})
    eligible = [c for c in buys if value_by_company.get(c.company, ZERO) < target0]
    eligible.sort(key=lambda c: (c.ratio, c.ticker))
    chosen = eligible[: p.max_stocks]
    if not chosen:
        return []
    # Peso-alvo final: igual entre as empresas que ficam na carteira (as atuais e as escolhidas).
    target = total / len(held_all | {c.company for c in chosen})

    held = {c for c, v in value_by_company.items() if v > 0}
    n_positions = len(held | {c.company for c in chosen})
    sectors_held = {sector_of[c] for c in held if c in sector_of}
    n_sectors = len(sectors_held | {c.sector for c in chosen})
    stock_cap_on = limits_active(n_positions, p.stock_cap)
    sector_cap_on = limits_active(n_sectors, p.sector_cap)

    sector_value: dict[str, Decimal] = defaultdict(Decimal)
    for c, v in value_by_company.items():
        if c in sector_of:
            sector_value[sector_of[c]] += v

    room: dict[int, Decimal] = {}
    for c in chosen:
        r = target - value_by_company.get(c.company, ZERO)
        if stock_cap_on:
            r = min(r, p.stock_cap * total - value_by_company.get(c.company, ZERO))
        room[c.company] = max(r, ZERO)

    amounts: dict[int, Decimal] = defaultdict(Decimal)
    open_ = {c.company: c for c in chosen}
    remaining = cash
    while open_ and remaining > 0:
        weights = {k: max(D(1) - c.ratio, D("0.0001")) for k, c in open_.items()}
        wsum = sum(weights.values())
        saturated = []
        for k, c in open_.items():
            share = remaining * weights[k] / wsum
            free = room[k] - amounts[k]
            if sector_cap_on:
                used = sector_value[c.sector] + sum(
                    amounts[o.company] for o in chosen if o.sector == c.sector
                )
                free = min(free, p.sector_cap * total - used)
            if share >= free:
                saturated.append((k, max(free, ZERO)))
        if not saturated:
            for k in open_:
                amounts[k] += remaining * weights[k] / wsum
            remaining = ZERO
            break
        for k, free in saturated:
            amounts[k] += free
            remaining -= free
            del open_[k]
    by_company = {c.company: c for c in chosen}
    return [
        Allocation(k, by_company[k].ticker, a, D(1) - by_company[k].ratio)
        for k, a in amounts.items()
        if a > 0
    ]


# --- Impostos -------------------------------------------------------------------------


@dataclass
class TaxState:
    loss_carry: Decimal = ZERO  # prejuízo acumulado a compensar


def monthly_tax(state: TaxState, sales: Decimal, result: Decimal, p: BacktestParams) -> Decimal:
    """Imposto do mês sobre vendas de ações (swing trade) e atualização do prejuízo acumulado.

    - Vendas do mês até ``cgt_exemption``: ganho isento (e ele não consome prejuízo acumulado);
      um prejuízo nesse mês ainda se acumula para compensar depois.
    - Acima: resultado do mês menos prejuízo acumulado, tributado se positivo.
    """
    if not p.apply_taxes or sales <= 0:
        return ZERO
    if sales <= p.cgt_exemption:
        if result < 0 and p.offset_losses:
            state.loss_carry += -result
        return ZERO
    net = result - (state.loss_carry if p.offset_losses else ZERO)
    if net > 0:
        state.loss_carry = ZERO
        return net * p.cgt_rate
    state.loss_carry = -net if p.offset_losses else ZERO
    return ZERO


# --- Simulação --------------------------------------------------------------------------


@dataclass
class Position:
    ticker: str
    company: int
    sector: str
    qty: Decimal
    cost: Decimal  # custo total, com taxas de compra (preço médio x quantidade)


@dataclass
class Trade:
    day: date
    ticker: str
    side: str  # buy | sell
    qty: Decimal
    price: Decimal
    fee: Decimal
    tax: Decimal = ZERO  # só nas vendas, imposto do mês atribuído à última venda do dia
    note: str = ""


@dataclass
class SimResult:
    # cota = retorno ponderado no tempo (o aporte entra ao valor da cota do dia)
    cota: dict[date, float] = field(default_factory=dict)
    nav: dict[date, Decimal] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)
    invested: Decimal = ZERO  # soma dos aportes
    fees: Decimal = ZERO
    taxes: Decimal = ZERO
    dividends: Decimal = ZERO  # proventos líquidos recebidos
    final_positions: dict[str, Decimal] = field(default_factory=dict)
    unfilled_cash_days: int = 0
    warnings: list[str] = field(default_factory=list)


def _bucket(days: list[date], when: date) -> date | None:
    """Primeiro pregão em ou depois de ``when`` (None se passa do fim do calendário)."""
    i = bisect_left(days, when)
    return days[i] if i < len(days) else None


def simulate(
    p: BacktestParams,
    days: list[date],
    signals: dict[date, list[Candidate]],
    book: PriceBook,
    events: dict[int, list[tuple[date, Decimal]]],
    dividends: dict[int, list[Payment]],
    cdi: dict[date, Decimal],
    price_max_age: int,
) -> SimResult:
    """Roda a estratégia sobre o calendário ``days``. ``signals``: data da decisão -> situação de
    cada papel com teto. Devolve a cota diária, as ordens e os totais de custos e impostos."""
    res = SimResult()
    positions: dict[str, Position] = {}
    cash = ZERO
    units = D(0)
    tax_state = TaxState()
    day_index = {d: i for i, d in enumerate(days)}

    exec_map: dict[date, list[Candidate]] = {}
    for d, sig in signals.items():
        i = day_index.get(d)
        if i is None or i + p.exec_lag_days >= len(days):
            continue
        exec_map[days[i + p.exec_lag_days]] = sig

    ev_map: dict[date, list[tuple[int, Decimal]]] = defaultdict(list)
    for cvm, evs in events.items():
        for d, f in evs:
            b = _bucket(days, d)
            if b is not None:
                ev_map[b].append((cvm, f))
    pay_map: dict[date, list[tuple[int, Payment]]] = defaultdict(list)
    for cvm, pays in dividends.items():
        for pay in pays:
            b = _bucket(days, pay.pay_date)
            if b is not None:
                pay_map[b].append((cvm, pay))

    def value_positions(day: date) -> Decimal:
        total = ZERO
        for pos in positions.values():
            px = book.at(pos.ticker, day)
            if px is not None:
                total += pos.qty * px
        return total

    for day in days:
        if p.cash_earns_cdi and cash > 0:
            cash += cash * cdi.get(day, ZERO)
        for cvm, f in ev_map.get(day, ()):
            for pos in positions.values():
                if pos.company == cvm:
                    pos.qty *= f
        for cvm, pay in pay_map.get(day, ()):
            for pos in positions.values():
                if pos.company == cvm:
                    net = pos.qty * (
                        pay.dividend * (1 - p.tax_dividend) + pay.jcp * (1 - p.tax_jcp)
                    )
                    cash += net
                    res.dividends += net

        sig = exec_map.get(day)
        if sig is not None:
            # A cota antes do aporte e das ordens: o aporte entra a esse valor.
            nav_pre = cash + value_positions(day)
            cota_pre = nav_pre / units if units > 0 else D(1)
            cash += p.contribution
            res.invested += p.contribution
            units += p.contribution / cota_pre
            cash = _execute(p, day, sig, positions, cash, book, price_max_age, tax_state, res)

        if units > 0:
            nav = cash + value_positions(day)
            res.nav[day] = nav
            res.cota[day] = float(nav / units)

    res.final_positions = {t: pos.qty for t, pos in positions.items()}
    return res


def _execute(
    p: BacktestParams,
    day: date,
    sig: list[Candidate],
    positions: dict[str, Position],
    cash: Decimal,
    book: PriceBook,
    price_max_age: int,
    tax_state: TaxState,
    res: SimResult,
) -> Decimal:
    """Vendas (acima de ``sell_above``), imposto do mês e compras do aporte. Devolve o caixa."""
    rate = p.fee_rate(day)
    by_ticker = {c.ticker: c for c in sig}

    # 1. Vendas da posição inteira.
    sales = ZERO
    result = ZERO
    sold: list[Trade] = []
    for ticker in sorted(positions):
        pos = positions[ticker]
        c = by_ticker.get(ticker)
        if c is None or c.ratio is None or c.ratio <= p.sell_above:
            continue
        px = book.at(ticker, day, price_max_age)
        if px is None:
            res.warnings.append(f"{day}: {ticker} sem pregão recente, venda adiada")
            continue
        gross = pos.qty * px
        fee = gross * rate
        proceeds = gross - fee
        cash += proceeds
        sales += gross
        result += proceeds - pos.cost
        res.fees += fee
        sold.append(Trade(day, ticker, "sell", pos.qty, px, fee, note=f"razão {c.ratio:.2f}"))
        del positions[ticker]
    if sold:
        tax = monthly_tax(tax_state, sales, result, p)
        if tax > 0:
            cash -= tax
            res.taxes += tax
            sold[-1].tax = tax
        res.trades.extend(sold)

    # 2. Compras: um papel por empresa (o de menor razão), valores pelos preços de hoje.
    value_by_company: dict[int, Decimal] = defaultdict(Decimal)
    sector_of: dict[int, str] = {}
    for pos in positions.values():
        px = book.at(pos.ticker, day)
        if px is not None:
            value_by_company[pos.company] += pos.qty * px
        sector_of[pos.company] = pos.sector
    best: dict[int, Candidate] = {}
    for c in sig:
        if not c.buy or c.ratio is None:
            continue
        if book.at(c.ticker, day, price_max_age) is None:
            continue
        sector_of.setdefault(c.company, c.sector)
        cur = best.get(c.company)
        if cur is None or (c.ratio, c.ticker) < (cur.ratio, cur.ticker):
            best[c.company] = c
    budget = cash
    allocs = allocate(budget, list(best.values()), dict(value_by_company), sector_of, p)
    spent_any = False
    for a in allocs:
        px = book.at(a.ticker, day, price_max_age)
        if px is None or px <= 0:
            continue
        qty = (a.amount / (px * (1 + rate))).to_integral_value(rounding=ROUND_FLOOR)
        if qty < 1:
            continue
        gross = qty * px
        fee = gross * rate
        cash -= gross + fee
        res.fees += fee
        cand = best[a.company]
        pos = positions.get(a.ticker)
        if pos is None:
            positions[a.ticker] = Position(a.ticker, a.company, cand.sector, qty, gross + fee)
        else:
            pos.qty += qty
            pos.cost += gross + fee
        res.trades.append(
            Trade(day, a.ticker, "buy", qty, px, fee, note=f"desconto {a.discount:.2f}")
        )
        spent_any = True
    if not spent_any and cash > 0:
        res.unfilled_cash_days += 1
    return cash


# --- Proventos recebidos -------------------------------------------------------------------------

# (é JCP, valor em R$, data de pagamento ou None): uma linha do FRE
FreLine = tuple[bool, Decimal, date | None]

DIVIDEND_TIMINGS = ("fre_dates_else_filing", "filing", "none")


def payments_for_year(
    ref: date,
    shares: int | None,
    jcp: Decimal | None,
    dividends: Decimal | None,
    filing_date: date,
    fre_lines: list[FreLine],
    events: list[tuple[date, Decimal]],
    timing: str,
) -> list[Payment]:
    """Proventos de um exercício como pagamentos por ação nas datas de pagamento.

    O total do exercício (``jcp`` e ``dividends``, da fonte já escolhida pelo filtro) é repartido
    pelas datas de pagamento do FRE, na proporção dos valores do FRE (linhas sem data caem na data
    de entrega da DFP). Sem linhas do FRE para a espécie (anos de FRE 2025 em diante, que não trazem
    pagamentos), o total é pago inteiro na data de entrega da DFP. ``timing``: ``filing`` ignora
    o FRE; ``none`` desliga os proventos (retorno só de preço).

    Valor por ação = total ÷ ações no fim do exercício, levado à base de ações da data de pagamento
    pelos eventos societários entre as duas datas.
    """
    if timing == "none" or not shares or jcp is None or dividends is None:
        return []
    by_date: dict[date, list[Decimal]] = defaultdict(lambda: [ZERO, ZERO])  # [dividendo, jcp]
    for idx, (total, want_jcp) in enumerate(((dividends, False), (jcp, True))):
        if total <= 0:
            continue
        weights: dict[date, Decimal] = defaultdict(Decimal)
        if timing == "fre_dates_else_filing":
            for is_jcp, amount, paid_on in fre_lines:
                if is_jcp == want_jcp and amount > 0:
                    weights[paid_on or filing_date] += amount
        wsum = sum(weights.values(), ZERO)
        if wsum <= 0:
            weights, wsum = {filing_date: D(1)}, D(1)
        for when, w in weights.items():
            share = total * w / wsum
            factor = D(1)
            for d, f in events:
                if ref < d <= when:
                    factor *= f
            by_date[when][idx] += share / (D(shares) * factor)
    return [Payment(d, v[0], v[1]) for d, v in sorted(by_date.items())]
