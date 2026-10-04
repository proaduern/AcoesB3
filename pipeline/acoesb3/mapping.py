"""Ligação ticker -> empresa e classe da ação (ON/PN), sem banco.

Convenção da B3: ticker = raiz de 4 letras + número. 3 = ordinária; 4 a 8 = preferenciais;
11 em diante = units/recibos (não entram no LPA nem no valor de mercado: o LPA da CVM é por
classe e as units são compostas pelas classes).
"""

from __future__ import annotations

import re

# A raiz tem 4 caracteres e pode ter dígito (B3SA3).
_TICKER = re.compile(r"^([A-Z][A-Z0-9]{3})(\d{1,2})$")


def ticker_root(ticker: str) -> str | None:
    m = _TICKER.match(ticker.strip().upper())
    return m.group(1) if m else None


def ticker_class(ticker: str) -> str:
    """'on', 'pn' ou 'other' (units, recibos, formatos fora do padrão)."""
    m = _TICKER.match(ticker.strip().upper())
    if not m:
        return "other"
    num = m.group(2)
    if num == "3":
        return "on"
    if num in {"4", "5", "6", "7", "8"}:
        return "pn"
    return "other"


def build_root_map(
    fca_rows: list[tuple[str, int]], overrides: dict[str, int]
) -> tuple[dict[str, int], dict[str, list[int]]]:
    """Raiz -> cvm_code a partir dos tickers do FCA. Raiz com mais de uma empresa fica de fora
    (devolvida em ``ambiguous``) até haver override manual."""
    seen: dict[str, set[int]] = {}
    for ticker, cvm_code in fca_rows:
        root = ticker_root(ticker) if ticker else None
        if root:
            seen.setdefault(root, set()).add(cvm_code)
    mapping, ambiguous = {}, {}
    for root, codes in seen.items():
        if len(codes) == 1:
            mapping[root] = next(iter(codes))
        else:
            ambiguous[root] = sorted(codes)
    for root, code in overrides.items():
        mapping[root] = code
        ambiguous.pop(root, None)
    return mapping, ambiguous


def reference_security(securities: list[tuple[int, str, float]]) -> tuple[str, int] | None:
    """Papel de referência da empresa: o mais negociado entre as ON; sem ON, entre as PN.

    ``securities``: (security_id, ticker, volume total). Devolve (classe, security_id).
    """
    for cls in ("on", "pn"):
        cands = [(vol, sid) for sid, t, vol in securities if ticker_class(t) == cls]
        if cands:
            return cls, max(cands)[1]
    return None


def class_securities(securities: list[tuple[int, str, float]]) -> dict[str, int]:
    """Papel mais negociado de cada classe ('on', 'pn') para o valor de mercado."""
    out: dict[str, int] = {}
    for cls in ("on", "pn"):
        cands = [(vol, sid) for sid, t, vol in securities if ticker_class(t) == cls]
        if cands:
            out[cls] = max(cands)[1]
    return out
