"""Parsers do FRE (Formulário de Referência) da CVM Dados Abertos. Sem banco.

Formato conferido nos arquivos reais em 03-04/10/2026 (docs/fontes.md):
- ``https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/FRE/DADOS/fre_cia_aberta_AAAA.zip``, 2010 a 2026;
- índice ``fre_cia_aberta_AAAA.csv`` com as colunas do DFP (CNPJ_CIA, DT_REFER, VERSAO, CD_CVM,
  CATEG_DOC, ID_DOC, DT_RECEB...). CATEG_DOC é ``FRE``, ``FRE NOVO`` (2020) ou ``FRE WEB`` (2025+);
  DT_REFER é só um marcador do ano (1º de janeiro até 2024, 31 de dezembro depois);
- os demais arquivos trazem só a última versão de cada documento, ligada ao índice por
  ``ID_Documento`` = ``ID_DOC``;
- ``capital_social``: ações por classe, por tipo de capital e data de aprovação;
- ``capital_social_desdobramento``: Desdobramento, Grupamento e Bonificação, com ações antes e
  depois e a data de APROVAÇÃO (a de efeito na negociação costuma ser semanas ou meses depois);
- ``distribuicao_dividendos_classe_acao``: proventos por exercício, espécie (ON/PN), classe e
  tipo, com valor total (R$) e data de pagamento; cada documento lista alguns exercícios e os
  documentos de anos seguidos se sobrepõem;
- os zips de 2025 e 2026 (layout novo) NÃO trazem desdobramento nem dividendos;
- datas inválidas existem (ex.: aprovação em 2077): são descartadas, não corrigidas.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation

from . import cvm

CATEG_DOC = {"FRE", "FRE NOVO", "FRE WEB"}
SPLIT_TYPES = {"Desdobramento", "Grupamento", "Bonificação"}


def member(suffix: str, year: int) -> str:
    return f"fre_cia_aberta_{suffix}_{year}.csv" if suffix else f"fre_cia_aberta_{year}.csv"


def rows(raw: bytes) -> list[dict[str, str]]:
    """Linhas do CSV. Tenta UTF-8 e cai para latin-1; tenta sem aspas e, se o número de campos
    não bater, com aspas. Falha se ainda assim houver linha com campos a mais ou a menos."""
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    last = None
    for quoting in (csv.QUOTE_NONE, csv.QUOTE_MINIMAL):
        reader = csv.reader(io.StringIO(text), delimiter=";", quoting=quoting)
        header = next(reader)
        out, bad = [], None
        for n, row in enumerate(reader, start=2):
            if not row:
                continue
            if len(row) != len(header):
                bad = f"linha {n}: {len(row)} campos, cabeçalho tem {len(header)}"
                break
            out.append(dict(zip(header, row, strict=True)))
        if bad is None:
            return out
        last = bad
    raise ValueError(last)


def parse_index(raw: bytes) -> list[cvm.IndexRow]:
    """Índice do FRE; todo CATEG_DOC conhecido vira doc_type 'FRE'."""
    out = []
    for r in cvm.parse_index(raw):
        if r.doc_type not in CATEG_DOC:
            raise ValueError(f"CATEG_DOC inesperado no índice do FRE: {r.doc_type!r}")
        out.append(replace(r, doc_type="FRE"))
    return out


@dataclass(frozen=True)
class Bounds:
    """Limites de datas plausíveis (configuráveis em app_config)."""

    min_year: int
    max_future_days: int

    def ok(self, d: date | None, received: date) -> date | None:
        if d is None:
            return None
        if d.year < self.min_year or d > received + timedelta(days=self.max_future_days):
            return None
        return d


def _date(s: str) -> date | None:
    s = s.strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _int(s: str) -> int | None:
    s = s.strip()
    return int(s) if s else None


@dataclass(frozen=True)
class CapitalRow:
    doc_id: int
    capital_type: str
    approved_on: date | None
    common: int | None
    preferred: int | None
    total: int | None


def parse_capital(raw: bytes) -> list[CapitalRow]:
    return [
        CapitalRow(
            doc_id=int(r["ID_Documento"]),
            capital_type=r["Tipo_Capital"],
            approved_on=_date(r["Data_Autorizacao_Aprovacao"]),
            common=_int(r["Quantidade_Acoes_Ordinarias"]),
            preferred=_int(r["Quantidade_Acoes_Preferenciais"]),
            total=_int(r["Quantidade_Total_Acoes"]),
        )
        for r in rows(raw)
    ]


@dataclass(frozen=True)
class SplitRow:
    doc_id: int
    event_type: str
    approved_on: date | None
    total_before: int | None
    total_after: int | None
    common_before: int | None
    common_after: int | None
    pref_before: int | None
    pref_after: int | None

    @property
    def factor(self) -> Decimal | None:
        """Ações depois / ações antes (2 = desdobramento 1:2; 0,1 = grupamento 10:1)."""
        if self.total_before and self.total_after:
            return Decimal(self.total_after) / Decimal(self.total_before)
        return None


def parse_splits(raw: bytes) -> list[SplitRow]:
    out = []
    for r in rows(raw):
        if r["Tipo_Evento"] not in SPLIT_TYPES:
            raise ValueError(f"Tipo_Evento inesperado no FRE: {r['Tipo_Evento']!r}")
        out.append(
            SplitRow(
                doc_id=int(r["ID_Documento"]),
                event_type=r["Tipo_Evento"],
                approved_on=_date(r["Data_Aprovacao"]),
                total_before=_int(r["Quantidade_Total_Acoes_Antes_Aprovacao"]),
                total_after=_int(r["Quantidade_Total_Acoes_Depois_Aprovacao"]),
                common_before=_int(r["Quantidade_Acoes_Ordinarias_Antes_Aprovacao"]),
                common_after=_int(r["Quantidade_Acoes_Ordinarias_Depois_Aprovacao"]),
                pref_before=_int(r["Quantidade_Acoes_Preferenciais_Antes_Aprovacao"]),
                pref_after=_int(r["Quantidade_Acoes_Preferenciais_Depois_Aprovacao"]),
            )
        )
    return out


@dataclass(frozen=True)
class DividendRow:
    doc_id: int
    exercise_start: date | None
    exercise_end: date
    share_type: str
    share_class: str
    kind: str
    amount: Decimal
    paid_on: date | None


def parse_dividends(raw: bytes) -> tuple[list[DividendRow], int]:
    """Devolve as linhas válidas e quantas foram descartadas (sem exercício ou sem valor)."""
    out, skipped = [], 0
    for r in rows(raw):
        end = _date(r["Data_Fim_Exercicio_Social"])
        try:
            amount = Decimal(r["Montante"].strip())
        except InvalidOperation:
            amount = None
        if end is None or amount is None:
            skipped += 1
            continue
        out.append(
            DividendRow(
                doc_id=int(r["ID_Documento"]),
                exercise_start=_date(r["Data_Inicio_Exercicio_Social"]),
                exercise_end=end,
                share_type=r["Especie_Acao"],
                share_class=r["Classe_Acao"],
                kind=r["Dividendo_Distribuido"],
                amount=amount,
                paid_on=_date(r["Data_Pagamento_Dividendo"]),
            )
        )
    return out, skipped
