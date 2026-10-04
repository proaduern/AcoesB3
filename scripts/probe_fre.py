"""Sonda temporária do FRE (roda no GitHub Actions; remover depois de escrito o parser).

Verifica antes de codar: cabeçalho do índice, versões e datas de entrega, valores de
Tipo_Capital / Tipo_Evento / Especie_Acao / Dividendo_Distribuido, o significado de
Data_Referencia, a sobreposição de exercícios entre FRE de anos diferentes, e a escala das ações
(FRE x composicao_capital da DFP) para Ambev, Itaú e Vale.
"""

import csv
import io
import re
import zipfile
from collections import Counter, defaultdict

import requests

CVM = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC"
UA = {"User-Agent": "Mozilla/5.0 AcoesB3-probe"}
YEARS = (2010, 2015, 2020, 2025, 2026)
NAMES = ("AMBEV", "VALE S.A", "ITAÚ UNIBANCO HOLDING", "ITAU UNIBANCO HOLDING", "WEG S.A", "BCO BRASIL", "BANCO DO BRASIL", "PETROBRAS")


def fetch_zip(url):
    r = requests.get(url, headers=UA, timeout=300)
    print(f"GET {url} -> {r.status_code} len={len(r.content)} last-modified={r.headers.get('Last-Modified')}")
    return zipfile.ZipFile(io.BytesIO(r.content)) if r.status_code == 200 else None


def rows(zf, name):
    raw = zf.read(name)
    try:
        txt = raw.decode("utf-8")
    except UnicodeDecodeError:
        txt = raw.decode("latin-1")
    return list(csv.DictReader(io.StringIO(txt), delimiter=";"))


def find(zf, suffix, year):
    n = f"fre_cia_aberta_{suffix}_{year}.csv" if suffix else f"fre_cia_aberta_{year}.csv"
    if n in zf.namelist():
        return n
    print(f"   !! {n} não existe; parecidos: {[x for x in zf.namelist() if suffix.split('_')[-1] in x][:6]}")
    return None


def is_target(name):
    n = (name or "").upper()
    return any(t in n for t in NAMES)


def show(rs, n=3, cols=None):
    for r in rs[:n]:
        print("      |", {k: v for k, v in r.items() if cols is None or k in cols})


def main():
    fre = {}
    for y in YEARS:
        zf = fetch_zip(f"{CVM}/FRE/DADOS/fre_cia_aberta_{y}.zip")
        if zf:
            fre[y] = zf
            print(f"   [{y}] {len(zf.namelist())} arquivos")
    base = set(fre[min(fre)].namelist())
    for y, zf in fre.items():
        names = {re.sub(r"_\d{4}\.csv$", ".csv", n) for n in zf.namelist()}
        ref = {re.sub(r"_\d{4}\.csv$", ".csv", n) for n in base}
        print(f"[{y}] arquivos que existem no 2010 e não aqui: {sorted(ref - names)}; novos: {sorted(names - ref)}")

    print("\n===== ÍNDICE (fre_cia_aberta_AAAA.csv) =====")
    for y, zf in fre.items():
        n = find(zf, "", y)
        if not n:
            print(f"[{y}] índice ausente; arquivos: {zf.namelist()[:6]}")
            continue
        rs = rows(zf, n)
        print(f"[{y}] {n}: {len(rs)} linhas; colunas: {list(rs[0].keys())}")
        show(rs, 2)
        for col in ("VERSAO", "CATEG_DOC", "DT_REFER"):
            if col in rs[0]:
                print(f"      {col}: {Counter(r[col] for r in rs).most_common(8)}")
        if "DT_RECEB" in rs[0]:
            d = sorted(r["DT_RECEB"] for r in rs if r["DT_RECEB"])
            print(f"      DT_RECEB: {d[0]} .. {d[-1]}")
        keys = Counter((r.get("CNPJ_CIA"), r.get("DT_REFER")) for r in rs)
        print(f"      (CNPJ, DT_REFER) com mais de uma versão no índice: {sum(1 for v in keys.values() if v > 1)}")

    print("\n===== CAPITAL SOCIAL =====")
    for y, zf in fre.items():
        n = find(zf, "capital_social", y)
        if not n:
            continue
        rs = rows(zf, n)
        idx = rows(zf, find(zf, "", y))
        print(f"[{y}] {len(rs)} linhas")
        print(f"      Tipo_Capital: {Counter(r['Tipo_Capital'] for r in rs).most_common()}")
        print(f"      Data_Referencia: {Counter(r['Data_Referencia'] for r in rs).most_common(4)}")
        vers = {(r['CNPJ_Companhia'], r['Versao']) for r in rs}
        idx_vers = {(r.get('CNPJ_CIA'), r.get('VERSAO')) for r in idx}
        print(f"      (CNPJ, versão) no capital: {len(vers)}; no índice: {len(idx_vers)}; em comum: {len(vers & idx_vers)}")
        per = Counter(r['CNPJ_Companhia'] for r in rs if r['Tipo_Capital'] == 'Capital Integralizado')
        print(f"      empresas com 'Capital Integralizado': {len(per)}; com mais de uma linha: {sum(1 for v in per.values() if v > 1)}")
        for r in rs:
            if is_target(r["Nome_Companhia"]) and r["Tipo_Capital"] == "Capital Integralizado":
                print(f"      {r['Nome_Companhia'][:32]:32} v{r['Versao']} ref {r['Data_Referencia']} aprov {r['Data_Autorizacao_Aprovacao']} ON {r['Quantidade_Acoes_Ordinarias']} PN {r['Quantidade_Acoes_Preferenciais']} total {r['Quantidade_Total_Acoes']}")

    print("\n===== DESDOBRAMENTO / GRUPAMENTO / BONIFICAÇÃO =====")
    for y, zf in fre.items():
        n = find(zf, "capital_social_desdobramento", y)
        if not n:
            continue
        rs = rows(zf, n)
        print(f"[{y}] {len(rs)} linhas; Tipo_Evento: {Counter(r['Tipo_Evento'] for r in rs).most_common()}")
        ap = sorted(r["Data_Aprovacao"] for r in rs if r["Data_Aprovacao"])
        print(f"      Data_Aprovacao: {ap[0]} .. {ap[-1]}")
        for r in rs:
            if is_target(r["Nome_Companhia"]):
                print(f"      {r['Nome_Companhia'][:30]:30} {r['Data_Aprovacao']} {r['Tipo_Evento']:14} antes {r['Quantidade_Total_Acoes_Antes_Aprovacao']} depois {r['Quantidade_Total_Acoes_Depois_Aprovacao']}")
        ratio_bad = sum(1 for r in rs if not r["Quantidade_Total_Acoes_Antes_Aprovacao"] or not r["Quantidade_Total_Acoes_Depois_Aprovacao"])
        print(f"      linhas sem quantidade antes/depois: {ratio_bad}")
    zf = fre.get(2025)
    n = find(zf, "capital_social_aumento", 2025) if zf else None
    if n:
        rs = rows(zf, n)
        print(f"[2025] capital_social_aumento: {len(rs)} linhas; Tipo_Subscricao: {Counter(r['Tipo_Subscricao'] for r in rs).most_common(8)}")

    print("\n===== DIVIDENDOS POR CLASSE =====")
    exercises = defaultdict(set)
    for y, zf in fre.items():
        n = find(zf, "distribuicao_dividendos_classe_acao", y)
        if not n:
            continue
        rs = rows(zf, n)
        print(f"[{y}] {len(rs)} linhas; colunas {list(rs[0].keys())[5:]}")
        print(f"      Especie_Acao: {Counter(r['Especie_Acao'] for r in rs).most_common()}")
        print(f"      Classe_Acao: {Counter(r['Classe_Acao'] for r in rs).most_common(6)}")
        print(f"      Dividendo_Distribuido: {Counter(r['Dividendo_Distribuido'] for r in rs).most_common(10)}")
        print(f"      Data_Fim_Exercicio_Social: {sorted(Counter(r['Data_Fim_Exercicio_Social'] for r in rs).items())[-6:]}")
        print(f"      sem Data_Pagamento: {sum(1 for r in rs if not r['Data_Pagamento_Dividendo'])} de {len(rs)}")
        for r in rs:
            exercises[(r['CNPJ_Companhia'], r['Data_Fim_Exercicio_Social'])].add(y)
        for r in rs:
            if is_target(r["Nome_Companhia"]) and r["Data_Fim_Exercicio_Social"] >= f"{y - 3}-01-01":
                print(f"      {r['Nome_Companhia'][:26]:26} ex {r['Data_Fim_Exercicio_Social']} {r['Especie_Acao']:12} {r['Classe_Acao'][:10]:10} {r['Dividendo_Distribuido'][:30]:30} R$ {r['Montante']:>16} pago {r['Data_Pagamento_Dividendo']}")
    multi = Counter(len(v) for v in exercises.values())
    print(f"\nExercícios (CNPJ, fim) por quantos dos FRE amostrados aparecem: {dict(multi)}")

    print("\n===== ESCALA DAS AÇÕES: composicao_capital da DFP 2024 =====")
    zf = fetch_zip(f"{CVM}/DFP/DADOS/dfp_cia_aberta_2024.zip")
    if zf:
        for r in rows(zf, "dfp_cia_aberta_composicao_capital_2024.csv"):
            if is_target(r["DENOM_CIA"]):
                print("      ", {k: v for k, v in r.items() if k != "CNPJ_CIA"})


if __name__ == "__main__":
    main()
