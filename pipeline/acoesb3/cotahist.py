"""Parser do COTAHIST da B3 (arquivo texto de largura fixa, 245 posições).

Layout conferido contra os arquivos reais COTAHIST_A2024/A2010 (ver
docs/fontes.md). Preços e volume vêm com 2 casas decimais implícitas.
Registros: 00 = header, 01 = cotação, 99 = trailer.
"""

from __future__ import annotations

import io
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import IO

RECORD_LENGTH = 245


@dataclass(frozen=True)
class Quote:
    trade_date: date
    codbdi: str
    ticker: str
    market_type: str  # TPMERC: '010' = mercado à vista, '020' = fracionário
    short_name: str
    especi: str  # especificação do papel: 'ON NM', 'PN N1', 'UNT N2'...
    open: Decimal
    high: Decimal
    low: Decimal
    avg: Decimal
    close: Decimal
    trades: int
    quantity: int
    volume: Decimal
    quote_factor: int  # FATCOT: 1 = preço por unidade, 1000 = por lote de mil
    isin: str
    distribution: int  # DISMES: número de distribuição (muda a cada provento/evento)


def _dec2(field: str) -> Decimal:
    return Decimal(int(field)).scaleb(-2)


def parse_line(line: str) -> Quote | None:
    """Converte uma linha tipo 01. Retorna None para header/trailer."""
    if len(line) < RECORD_LENGTH:
        raise ValueError(f"linha COTAHIST com {len(line)} posições (esperado {RECORD_LENGTH})")
    if line[0:2] != "01":
        return None
    d = line[2:10]
    factor = int(line[210:217])
    return Quote(
        trade_date=date(int(d[0:4]), int(d[4:6]), int(d[6:8])),
        codbdi=line[10:12],
        ticker=line[12:24].strip(),
        market_type=line[24:27],
        short_name=line[27:39].strip(),
        especi=" ".join(line[39:49].split()),
        open=_dec2(line[56:69]),
        high=_dec2(line[69:82]),
        low=_dec2(line[82:95]),
        avg=_dec2(line[95:108]),
        close=_dec2(line[108:121]),
        trades=int(line[147:152]),
        quantity=int(line[152:170]),
        volume=_dec2(line[170:188]),
        quote_factor=factor,
        isin=line[230:242],
        distribution=int(line[242:245]),
    )


def _iter_text(binary: IO[bytes]) -> Iterator[str]:
    for line in io.TextIOWrapper(binary, encoding="latin-1", newline=None):
        line = line.rstrip("\r\n")
        if line:
            yield line


def iter_lines(raw: bytes) -> Iterator[str]:
    yield from _iter_text(io.BytesIO(raw))


def iter_zip(content: bytes) -> Iterator[str]:
    """Lê o zip em fluxo (o anual descompactado passa de 600 MB)."""
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        for name in z.namelist():
            with z.open(name) as f:
                yield from _iter_text(f)


def select_quotes(
    lines: Iterable[str], codbdi: set[str], market_types: set[str], isin_types: set[str]
) -> Iterator[Quote]:
    """Filtra cotações pelo código BDI, tipo de mercado e tipo de ativo do ISIN configurados.

    O tipo do ISIN (posições 7-9: 'ACN' ação, 'UNT'/'CDA' unit, 'BDR'...) é necessário porque
    em 2020-2022 a B3 marcou BDRs com CODBDI 02, o mesmo das ações.
    """
    for line in lines:
        # filtro barato antes de converter a linha inteira
        if (
            line[0:2] != "01"
            or line[10:12] not in codbdi
            or line[24:27] not in market_types
            or line[236:239] not in isin_types
        ):
            continue
        q = parse_line(line)
        if q is not None:
            yield q
