"""Parsers e carga dos arquivos da CVM Dados Abertos (DFP, ITR, FCA, cadastro).

Formato conferido nos arquivos reais (ver docs/fontes.md):
- zip anual com CSVs `;`, codificação latin-1, sem aspas;
- `<tipo>_cia_aberta_<ano>.csv` é o índice: uma linha por versão entregue, com DT_RECEB;
- os arquivos de demonstrações trazem só a versão mais recente de cada documento;
- ESCALA_MOEDA = 'MIL' ou 'UNIDADE'. Contas de valor por ação (3.99, LPA) vêm com a
  mesma ESCALA_MOEDA da demonstração, mas já estão em reais por ação: não escalar.
"""

from __future__ import annotations

import csv
import io
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

BASE_URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA"

SCALE = {"UNIDADE": Decimal(1), "MIL": Decimal(1000)}

# Arquivos de demonstração lidos de cada zip DFP/ITR.
STATEMENTS = ("BPA", "BPP", "DRE", "DFC_MI", "DFC_MD", "DVA")

LATEST = "ÚLTIMO"


def doc_url(doc_type: str, year: int) -> str:
    t = doc_type.lower()
    return f"{BASE_URL}/DOC/{doc_type}/DADOS/{t}_cia_aberta_{year}.zip"


CAD_URL = f"{BASE_URL}/CAD/DADOS/cad_cia_aberta.csv"


def read_csv(raw: bytes) -> Iterator[dict[str, str]]:
    """Lê um CSV da CVM. Falha se alguma linha tiver número de campos diferente do cabeçalho."""
    reader = csv.reader(io.StringIO(raw.decode("latin-1")), delimiter=";", quoting=csv.QUOTE_NONE)
    header = next(reader)
    for n, row in enumerate(reader, start=2):
        if not row:
            continue
        if len(row) != len(header):
            raise ValueError(f"linha {n}: {len(row)} campos, cabeçalho tem {len(header)}")
        yield dict(zip(header, row, strict=True))


def _date(s: str) -> date | None:
    return date.fromisoformat(s) if s else None


@dataclass(frozen=True)
class IndexRow:
    doc_type: str
    cvm_code: int
    cnpj: str
    reference_date: date
    version: int
    doc_id: int
    received_date: date
    link: str


def parse_index(raw: bytes) -> list[IndexRow]:
    return [
        IndexRow(
            doc_type=r["CATEG_DOC"],
            cvm_code=int(r["CD_CVM"]),
            cnpj=r["CNPJ_CIA"],
            reference_date=date.fromisoformat(r["DT_REFER"]),
            version=int(r["VERSAO"]),
            doc_id=int(r["ID_DOC"]),
            received_date=date.fromisoformat(r["DT_RECEB"]),
            link=r["LINK_DOC"],
        )
        for r in read_csv(raw)
    ]


@dataclass(frozen=True)
class AccountRule:
    statement: str
    code: str
    include_children: bool

    def matches(self, statement: str, code: str) -> bool:
        if statement != self.statement:
            return False
        return code == self.code or (self.include_children and code.startswith(self.code + "."))


@dataclass(frozen=True)
class Line:
    cvm_code: int
    reference_date: date
    version: int
    statement: str
    consolidated: bool
    account_code: str
    period_start: date | None
    period_end: date
    value: Decimal
    source_scale: str


def scale_value(
    raw_value: str, escala: str, account_code: str, per_share_prefixes: Iterable[str]
) -> Decimal:
    """Converte VL_CONTA para reais. Contas por ação não são escaladas."""
    if escala not in SCALE:
        raise ValueError(f"ESCALA_MOEDA desconhecida: {escala!r}")
    value = Decimal(raw_value)
    if any(account_code == p or account_code.startswith(p + ".") for p in per_share_prefixes):
        return value
    return value * SCALE[escala]


def parse_statement(
    raw: bytes,
    statement: str,
    consolidated: bool,
    rules: list[AccountRule],
    per_share_prefixes: Iterable[str],
) -> Iterator[Line]:
    """Linhas do exercício corrente (ORDEM_EXERC = ÚLTIMO) das contas selecionadas."""
    per_share_prefixes = tuple(per_share_prefixes)
    for r in read_csv(raw):
        if r["ORDEM_EXERC"] != LATEST:
            continue
        code = r["CD_CONTA"]
        if not any(rule.matches(statement, code) for rule in rules):
            continue
        if r["MOEDA"] != "REAL":
            raise ValueError(f"MOEDA inesperada: {r['MOEDA']!r} (CD_CVM {r['CD_CVM']})")
        yield Line(
            cvm_code=int(r["CD_CVM"]),
            reference_date=date.fromisoformat(r["DT_REFER"]),
            version=int(r["VERSAO"]),
            statement=statement,
            consolidated=consolidated,
            account_code=code,
            period_start=_date(r.get("DT_INI_EXERC", "")),
            period_end=date.fromisoformat(r["DT_FIM_EXERC"]),
            value=scale_value(r["VL_CONTA"], r["ESCALA_MOEDA"], code, per_share_prefixes),
            source_scale=r["ESCALA_MOEDA"],
        )


def choose_scope(lines: Iterable[Line]) -> list[Line]:
    """Consolidada; individual só para (documento, demonstração) sem consolidada."""
    lines = list(lines)

    def key(x: Line) -> tuple:
        return (x.cvm_code, x.reference_date, x.version, x.statement)

    has_con = {key(x) for x in lines if x.consolidated}
    return [x for x in lines if x.consolidated or key(x) not in has_con]


@dataclass(frozen=True)
class ShareCount:
    cnpj: str
    reference_date: date
    version: int
    common: int
    preferred: int
    total: int
    treasury_common: int
    treasury_preferred: int
    treasury_total: int


def parse_share_counts(raw: bytes) -> list[ShareCount]:
    """composicao_capital: não tem CD_CVM; liga-se ao documento por CNPJ + data + versão."""
    return [
        ShareCount(
            cnpj=r["CNPJ_CIA"],
            reference_date=date.fromisoformat(r["DT_REFER"]),
            version=int(r["VERSAO"]),
            common=int(r["QT_ACAO_ORDIN_CAP_INTEGR"]),
            preferred=int(r["QT_ACAO_PREF_CAP_INTEGR"]),
            total=int(r["QT_ACAO_TOTAL_CAP_INTEGR"]),
            treasury_common=int(r["QT_ACAO_ORDIN_TESOURO"]),
            treasury_preferred=int(r["QT_ACAO_PREF_TESOURO"]),
            treasury_total=int(r["QT_ACAO_TOTAL_TESOURO"]),
        )
        for r in read_csv(raw)
    ]


@dataclass(frozen=True)
class SecurityRow:
    doc_id: int
    cnpj: str
    ticker: str | None  # vazio nos FCA antigos (ex.: 2010)
    security_type: str
    preferred_class: str | None
    unit_composition: str | None
    market: str | None
    segment: str | None
    trading_start: date | None
    trading_end: date | None


def parse_fca_securities(raw: bytes) -> list[SecurityRow]:
    return [
        SecurityRow(
            doc_id=int(r["ID_Documento"]),
            cnpj=r["CNPJ_Companhia"],
            ticker=r["Codigo_Negociacao"].strip() or None,
            security_type=r["Valor_Mobiliario"],
            preferred_class=r["Sigla_Classe_Acao_Preferencial"] or None,
            unit_composition=r["Composicao_BDR_Unit"] or None,
            market=r["Mercado"] or None,
            segment=r["Segmento"] or None,
            trading_start=_date(r["Data_Inicio_Negociacao"]),
            trading_end=_date(r["Data_Fim_Negociacao"]),
        )
        for r in read_csv(raw)
    ]


@dataclass(frozen=True)
class CadRow:
    cvm_code: int
    cnpj: str
    name: str
    trade_name: str | None
    cvm_sector: str | None
    status: str
    status_since: date | None
    registered_at: date | None
    canceled_at: date | None
    cancel_reason: str | None
    category: str | None


def parse_cad(raw: bytes) -> list[CadRow]:
    """Cadastro de companhias. O mesmo CD_CVM pode aparecer mais de uma vez
    (registros diferentes); fica o ativo, senão o de registro mais recente."""
    best: dict[int, CadRow] = {}
    for r in read_csv(raw):
        row = CadRow(
            cvm_code=int(r["CD_CVM"]),
            cnpj=r["CNPJ_CIA"],
            name=r["DENOM_SOCIAL"],
            trade_name=r["DENOM_COMERC"] or None,
            cvm_sector=r["SETOR_ATIV"] or None,
            status=r["SIT"],
            status_since=_date(r["DT_INI_SIT"]),
            registered_at=_date(r["DT_REG"]),
            canceled_at=_date(r["DT_CANCEL"]),
            cancel_reason=r["MOTIVO_CANCEL"] or None,
            category=r["CATEG_REG"] or None,
        )
        cur = best.get(row.cvm_code)
        if cur is None or _cad_rank(row) > _cad_rank(cur):
            best[row.cvm_code] = row
    return list(best.values())


def _cad_rank(r: CadRow) -> tuple:
    return (r.status == "ATIVO", r.registered_at or date.min, r.status_since or date.min)


class ZipMembers:
    """Acesso sob demanda aos arquivos do zip (os de ITR passam de 400 MB descompactados)."""

    def __init__(self, content: bytes):
        self._zip = zipfile.ZipFile(io.BytesIO(content))
        self._names = set(self._zip.namelist())

    def __contains__(self, name: str) -> bool:
        return name in self._names

    def __getitem__(self, name: str) -> bytes:
        if name not in self._names:
            raise KeyError(f"arquivo ausente no zip: {name}")
        return self._zip.read(name)
