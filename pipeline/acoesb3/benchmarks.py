"""Índices de comparação do backtest: Ibovespa e IDIV (B3) e CDI (Banco Central).

Formatos verificados nas respostas reais (08/10/2026, ver docs/fontes.md):

- B3: ``https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetPortfolioDay/``
  seguido do base64 de ``{"index":"IBOVESPA","language":"pt-br","year":"2024"}``. Devolve JSON com
  ``results``: 31 linhas (``day``) com ``rateValue1`` a ``rateValue12`` (mês), texto em formato
  brasileiro (``"128.481,02"``) ou ``null`` (sem pregão). O IDIV da B3 é índice de retorno total.
- Banco Central (SGS, série 12 = CDI diário, em % ao dia):
  ``https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=json&dataInicial=dd/mm/aaaa&dataFinal=dd/mm/aaaa``
  devolve ``[{"data":"02/01/2012","valor":"0.041028"}, ...]``; a API aceita no máximo 10 anos
  por consulta em séries diárias (HTTP 406 acima disso).
"""

from __future__ import annotations

import base64
import json
from datetime import date, timedelta
from decimal import Decimal

B3_API = "https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetPortfolioDay"
BCB_API = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{series}/dados"


def parse_br_number(text: str) -> Decimal:
    """``"128.481,02"`` -> ``Decimal("128481.02")``."""
    return Decimal(text.replace(".", "").replace(",", "."))


def b3_url(index: str, year: int) -> str:
    payload = json.dumps(
        {"index": index, "language": "pt-br", "year": str(year)}, separators=(",", ":")
    )
    return f"{B3_API}/{base64.b64encode(payload.encode()).decode()}"


def parse_b3_year(payload: dict, year: int) -> list[tuple[date, Decimal]]:
    """Fechamentos do ano em ordem de data. Células vazias são dias sem pregão; o par (dia, mês)
    que não existe no calendário (30/02) é ignorado."""
    out = []
    for row in payload.get("results", []):
        day = int(row["day"])
        for month in range(1, 13):
            text = row.get(f"rateValue{month}")
            if not text:
                continue
            try:
                d = date(year, month, day)
            except ValueError:
                continue
            out.append((d, parse_br_number(text)))
    return sorted(out)


def bcb_url(series: int, start: date, end: date) -> str:
    return (
        BCB_API.format(series=series)
        + f"?formato=json&dataInicial={start:%d/%m/%Y}&dataFinal={end:%d/%m/%Y}"
    )


def bcb_windows(start: date, end: date, years: int = 9) -> list[tuple[date, date]]:
    """Janelas consecutivas de até ``years`` anos (a API recusa mais de 10 em série diária)."""
    out, cur = [], start
    while cur <= end:
        try:
            nxt = cur.replace(year=cur.year + years)
        except ValueError:  # 29/02
            nxt = cur.replace(year=cur.year + years, day=28)
        stop = min(nxt - timedelta(days=1), end)
        out.append((cur, stop))
        cur = stop + timedelta(days=1)
    return out


def parse_bcb_json(text: str) -> list[tuple[date, Decimal]]:
    out = []
    for row in json.loads(text):
        d, m, y = row["data"].split("/")
        out.append((date(int(y), int(m), int(d)), Decimal(row["valor"])))
    return sorted(out)


def cdi_daily_rates(rows: list[tuple[date, Decimal]]) -> dict[date, Decimal]:
    """Taxa diária como fração (a série vem em % ao dia)."""
    return {d: v / 100 for d, v in rows}


def cumulative_index(
    rates: dict[date, Decimal], base: Decimal = Decimal(100)
) -> dict[date, Decimal]:
    """Número-índice do CDI: capitaliza a taxa de cada dia (valor no fechamento do dia)."""
    level, out = base, {}
    for d in sorted(rates):
        level *= 1 + rates[d]
        out[d] = level
    return out
