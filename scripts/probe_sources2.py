"""Segunda sonda: versões, códigos de conta, frequência de atualização, Neon."""
import io
import os
import re
import zipfile
from collections import Counter, defaultdict

import requests

CVM = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC"
UA = {"User-Agent": "Mozilla/5.0 AcoesB3-probe"}
COMPANIES = {"001023": "BB", "009512": "PETROBRAS", "019348": "ITAU", "023159": "BBSEG",
             "020257": "TAESA", "005410": "WEG", "004170": "VALE"}


def zip_csv(url):
    r = requests.get(url, headers=UA, timeout=300)
    print("GET", url, r.status_code, r.headers.get("Last-Modified"))
    z = zipfile.ZipFile(io.BytesIO(r.content))
    return {n: z.read(n).decode("latin-1").splitlines() for n in z.namelist()}


def rows(lines):
    cols = lines[0].split(";")
    for ln in lines[1:]:
        yield dict(zip(cols, ln.split(";")))


print("######## dataset pages")
for ds in ("cia_aberta-doc-dfp", "cia_aberta-doc-itr", "cia_aberta-doc-fca", "cia_aberta-cad"):
    try:
        r = requests.get(f"https://dados.cvm.gov.br/dataset/{ds}", headers=UA, timeout=60)
        txt = re.sub(r"<[^>]+>", " ", r.text)
        txt = re.sub(r"\s+", " ", txt)
        for kw in ("Frequ", "Atualiza", "atualiza", "Periodicidade"):
            for m in re.finditer(kw, txt):
                print(f"  [{ds}] ...{txt[max(0, m.start()-150):m.start()+250]}...")
    except Exception as e:  # noqa: BLE001
        print("fail", ds, e)

print("\n######## DFP 2024: versões por documento")
f = zip_csv(f"{CVM}/DFP/DADOS/dfp_cia_aberta_2024.zip")
idx = list(rows(f["dfp_cia_aberta_2024.csv"]))
idx_versions = defaultdict(set)
for r in idx:
    idx_versions[(r["CD_CVM"], r["DT_REFER"])].add(r["VERSAO"])
bpa_versions = defaultdict(set)
for r in rows(f["dfp_cia_aberta_BPA_con_2024.csv"]):
    bpa_versions[(r["CD_CVM"], r["DT_REFER"])].add(r["VERSAO"])
multi = sum(1 for v in bpa_versions.values() if len(v) > 1)
print("docs no índice:", len(idx_versions), "docs no BPA_con:", len(bpa_versions),
      "docs com >1 versão no BPA_con:", multi)
latest_match = sum(1 for k, v in bpa_versions.items()
                   if max(v, key=int) == max(idx_versions[k], key=int))
print("BPA_con versão == maior versão do índice:", latest_match, "de", len(bpa_versions))
for k in list(bpa_versions)[:0]:
    pass
print("índice com >1 linha por (CD_CVM, DT_REFER):",
      sum(1 for v in idx_versions.values() if len(v) > 1))
dtref = Counter(r["DT_REFER"] for r in idx)
print("DT_REFER no índice DFP 2024:", dtref.most_common(8))

print("\n######## DFP 2024: contas por empresa (ÚLTIMO)")
for stmt in ("BPA_con", "BPP_con", "DRE_con", "DFC_MI_con", "DVA_con"):
    lines = f[f"dfp_cia_aberta_{stmt}_2024.csv"]
    for r in rows(lines):
        if r.get("CD_CVM") not in COMPANIES or r["ORDEM_EXERC"] != "ÚLTIMO":
            continue
        code = r["CD_CONTA"]
        lvl = code.count(".") + 1
        maxlvl = 4 if stmt in ("DVA_con",) else 3
        if lvl <= maxlvl or code.startswith("3.99"):
            print(f"  {COMPANIES[r['CD_CVM']]:9} {stmt:10} {r['ESCALA_MOEDA']:7} {code:14} "
                  f"{r['ST_CONTA_FIXA']} {r['DS_CONTA'][:60]:60} {r['VL_CONTA']}")

print("\n######## DFP 2024: DRE_con vs DRE_ind presença")
con = {r["CD_CVM"] for r in rows(f["dfp_cia_aberta_DRE_con_2024.csv"])}
ind = {r["CD_CVM"] for r in rows(f["dfp_cia_aberta_DRE_ind_2024.csv"])}
print("con:", len(con), "ind:", len(ind), "ind sem con:", len(ind - con), "con sem ind:", len(con - ind))

print("\n######## DFP 2024 DRE: códigos de LPA (3.99*) distintos")
c = Counter((r["CD_CONTA"], r["DS_CONTA"]) for r in rows(f["dfp_cia_aberta_DRE_con_2024.csv"])
            if r["CD_CONTA"].startswith("3.99") and r["ORDEM_EXERC"] == "ÚLTIMO")
for k, v in c.most_common(20):
    print("  ", k, v)
print("\n######## UNIDADE: exemplo de empresa em UNIDADE")
for r in rows(f["dfp_cia_aberta_DRE_con_2024.csv"]):
    if r["ESCALA_MOEDA"] == "UNIDADE" and r["CD_CONTA"] == "3.11" and r["ORDEM_EXERC"] == "ÚLTIMO":
        print("  ", r["CD_CVM"], r["DENOM_CIA"], r["CD_CONTA"], r["VL_CONTA"])
        break
print("\n######## escala por conta 3.99 (LPA) — vem em MIL também?")
for r in rows(f["dfp_cia_aberta_DRE_con_2024.csv"]):
    if r["CD_CVM"] in ("009512", "001023") and r["CD_CONTA"].startswith("3.99") and r["ORDEM_EXERC"] == "ÚLTIMO":
        print("  ", r["CD_CVM"], r["ESCALA_MOEDA"], r["CD_CONTA"], r["DS_CONTA"], r["VL_CONTA"])
del f

print("\n######## DFP 2010 cabeçalhos")
f = zip_csv(f"{CVM}/DFP/DADOS/dfp_cia_aberta_2010.zip")
for n, lines in f.items():
    print("  ", n, "|", lines[0][:300], "| linhas", len(lines))
del f

print("\n######## ITR 2025: períodos da DRE (Petrobras)")
f = zip_csv(f"{CVM}/ITR/DADOS/itr_cia_aberta_2025.zip")
for r in rows(f["itr_cia_aberta_DRE_con_2025.csv"]):
    if r["CD_CVM"] == "009512" and r["CD_CONTA"] in ("3.11", "3.99.01.01"):
        print("  ", r["DT_REFER"], r["VERSAO"], r["ORDEM_EXERC"], r["DT_INI_EXERC"], r["DT_FIM_EXERC"],
              r["CD_CONTA"], r["VL_CONTA"])
for r in rows(f["itr_cia_aberta_DFC_MI_con_2025.csv"]):
    if r["CD_CVM"] == "009512" and r["CD_CONTA"] == "6.01":
        print("  DFC", r["DT_REFER"], r["ORDEM_EXERC"], r["DT_INI_EXERC"], r["DT_FIM_EXERC"], r["VL_CONTA"])
print("ITR 2025 arquivos:", list(f))
del f

print("\n######## FCA 2026 valor_mobiliario")
f = zip_csv(f"{CVM}/FCA/DADOS/fca_cia_aberta_2026.zip")
vm = list(rows(f["fca_cia_aberta_valor_mobiliario_2026.csv"]))
print(Counter(r["Valor_Mobiliario"] for r in vm).most_common())
print(Counter(r["Mercado"] for r in vm).most_common())
print(Counter(r["Segmento"] for r in vm).most_common())
for r in vm:
    if r["Codigo_Negociacao"] in ("TAEE11", "TAEE3", "TAEE4", "ITUB4", "PETR4", "SANB11"):
        print("  ", r)
ger = list(rows(f["fca_cia_aberta_geral_2026.csv"]))
print(Counter(r["Setor_Atividade"] for r in ger).most_common(60))
del f
print("\n######## FCA 2010 valor_mobiliario header")
f = zip_csv(f"{CVM}/FCA/DADOS/fca_cia_aberta_2010.zip")
for n, lines in f.items():
    if "valor_mobiliario" in n or "geral" in n or n.endswith("_2010.csv"):
        print("  ", n, "|", lines[0][:400], "| linhas", len(lines))
        for ln in lines[1:3]:
            print("     ", ln[:400])

print("\n######## CAD: situações")
r = requests.get("https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv", headers=UA, timeout=60)
cad = list(rows(r.content.decode("latin-1").splitlines()))
print(Counter(x["SIT"] for x in cad).most_common())
print(Counter(x["TP_MERC"] for x in cad).most_common())
print("CD_CVM repetido:", sum(1 for k, v in Counter(x["CD_CVM"] for x in cad).items() if v > 1))

print("\n######## Neon plans page")
try:
    r = requests.get("https://neon.com/docs/introduction/plans", headers=UA, timeout=60)
    txt = re.sub(r"<[^>]+>", " ", r.text)
    txt = re.sub(r"\s+", " ", txt)
    for m in re.finditer(r"0\.5 GB|512 MB|Storage", txt):
        print("  ...", txt[max(0, m.start()-200):m.start()+200])
        break
    for m in list(re.finditer(r"Free", txt))[:6]:
        print("  ...", txt[max(0, m.start()-100):m.start()+300])
except Exception as e:  # noqa: BLE001
    print("neon page fail", e)
