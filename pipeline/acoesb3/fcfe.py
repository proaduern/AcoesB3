"""Fluxo de caixa livre para o acionista (FCFE) a partir do DFC. Funções puras, sem banco.

Verificado nos dados reais (DFP 2021 e 2024 das empresas da lista, ver ``docs/fontes.md``): só os
totais 6.01 (operacional), 6.02 (investimento) e 6.03 (financiamento) são padronizados. As contas
filhas mudam de código e de nome de empresa para empresa (Alupar 6.02.08 = imobilizado; Cemig
6.02.03; Sanepar 6.02.01). Por isso o FCFE classifica as contas filhas pela **descrição**, com
listas de expressões em ``app_config`` (``fcfe.*``):

    FCFE = caixa operacional (6.01)
         + investimento em ativos (6.02.xx de imobilizado, intangível, ativos de contrato/concessão,
           inclusive a venda de imobilizado)
         + dividendos e JCP recebidos de investidas (6.02.xx)
         + fluxo de dívida (6.03.xx que não são de acionistas: captações, amortizações, juros,
           arrendamentos, derivativos, custos de captação)

Fora do FCFE: aplicações e resgates financeiros, compra e venda de participações, dividendos e JCP
pagos, aumentos e reduções de capital, ações em tesouraria. Cada linha usada ou excluída fica no
detalhe, para revisão. Companhias de transmissão e concessionárias que registram o investimento em
ativo de contrato dentro do caixa operacional já o têm descontado em 6.01.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from decimal import Decimal

from .cvm import ascii_upper

D = Decimal

_CHILD = re.compile(r"^6\.0[23]\.\d{2}$")


@dataclass(frozen=True)
class FcfeRules:
    capex: tuple[re.Pattern, ...]
    inflow: tuple[re.Pattern, ...]
    non_debt: tuple[re.Pattern, ...]

    @classmethod
    def from_config(cls, cfg: dict) -> FcfeRules:
        def compile_all(key):
            return tuple(re.compile(p) for p in cfg[key])

        return cls(
            capex=compile_all("fcfe.capex_patterns"),
            inflow=compile_all("fcfe.inflow_patterns"),
            non_debt=compile_all("fcfe.non_debt_patterns"),
        )


@dataclass
class Fcfe:
    value: Decimal | None
    reason: str | None = None  # quando value é None
    cfo: Decimal | None = None
    capex: Decimal = D(0)
    inflow: Decimal = D(0)
    debt: Decimal = D(0)
    lines: dict[str, list[tuple[str, str, str]]] = field(default_factory=dict)

    def detail(self) -> dict:
        out = {
            "fcfe": None if self.value is None else str(self.value),
            "cfo": None if self.cfo is None else str(self.cfo),
            "capex": str(self.capex),
            "inflow": str(self.inflow),
            "debt": str(self.debt),
            "lines": self.lines,
        }
        if self.reason:
            out["reason"] = self.reason
        return out


def _matches(patterns, text: str) -> bool:
    return any(p.search(text) for p in patterns)


def compute_fcfe(lines: list[tuple[str, str, Decimal]], rules: FcfeRules) -> Fcfe:
    """``lines``: (código, descrição, valor em R$) das contas 6.01, 6.02.xx e 6.03.xx de um DFC.

    Sem o total operacional, ou sem detalhamento de investimento e de financiamento, o FCFE fica
    indisponível (nunca zero)."""
    cfo = next((v for c, _, v in lines if c == "6.01"), None)
    if cfo is None:
        return Fcfe(None, "sem caixa operacional (6.01)")
    invest = [(c, d, v) for c, d, v in lines if _CHILD.match(c) and c.startswith("6.02.")]
    financing = [(c, d, v) for c, d, v in lines if _CHILD.match(c) and c.startswith("6.03.")]
    if not invest or not financing:
        return Fcfe(None, "sem detalhamento do investimento ou do financiamento", cfo=cfo)
    out = Fcfe(D(0), cfo=cfo, lines={"capex": [], "inflow": [], "debt": [], "excluded": []})

    def keep(kind, c, d, v):
        out.lines[kind].append((c, d, str(v)))

    for c, d, v in invest:
        text = ascii_upper(d)
        if _matches(rules.inflow, text):
            out.inflow += v
            keep("inflow", c, d, v)
        elif _matches(rules.capex, text):
            out.capex += v
            keep("capex", c, d, v)
        else:
            keep("excluded", c, d, v)
    for c, d, v in financing:
        if _matches(rules.non_debt, ascii_upper(d)):
            keep("excluded", c, d, v)
        else:
            out.debt += v
            keep("debt", c, d, v)
    out.value = cfo + out.capex + out.inflow + out.debt
    return out
