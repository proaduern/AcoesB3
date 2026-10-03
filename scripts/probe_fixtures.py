"""Terceira sonda: extrai linhas reais para fixtures de teste (impressas entre marcadores)."""
import io
import zipfile

import requests

CVM = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC"
UA = {"User-Agent": "Mozilla/5.0 AcoesB3-probe"}
CODES = {"005410", "019348", "023159", "016675"}  # WEG, Itaú, BB Seguridade, CELPAR (UNIDADE)
CNPJS = set()


def members(url):
    r = requests.get(url, headers=UA, timeout=300)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    return {n: z.read(n).decode("latin-1").splitlines() for n in z.namelist()}


def dump(name, lines):
    print(f"=====BEGIN {name}")
    for ln in lines:
        print(ln)
    print(f"=====END {name}")


def pick(lines, col, values, extra=lambda c: True):
    cols = lines[0].split(";")
    i = cols.index(col)
    out = [lines[0]]
    for ln in lines[1:]:
        f = ln.split(";")
        if f[i] in values and extra(dict(zip(cols, f))):
            out.append(ln)
    return out


m = members(f"{CVM}/DFP/DADOS/dfp_cia_aberta_2024.zip")
idx = pick(m["dfp_cia_aberta_2024.csv"], "CD_CVM", CODES | {"014206"})
dump("dfp_cia_aberta_2024.csv", idx)
for ln in idx[1:]:
    CNPJS.add(ln.split(";")[0])
keep = lambda r: r["ORDEM_EXERC"] in ("ÚLTIMO", "PENÚLTIMO")  # noqa: E731
for st in ("DRE_con", "DRE_ind", "BPP_con", "BPP_ind", "DVA_con", "BPA_con", "DFC_MI_con"):
    rows = pick(m[f"dfp_cia_aberta_{st}_2024.csv"], "CD_CVM", CODES)
    dump(f"dfp_cia_aberta_{st}_2024.csv", rows)
dump("dfp_cia_aberta_composicao_capital_2024.csv",
     pick(m["dfp_cia_aberta_composicao_capital_2024.csv"], "CNPJ_CIA", CNPJS))

m = members(f"{CVM}/ITR/DADOS/itr_cia_aberta_2025.zip")
dump("itr_cia_aberta_2025.csv", pick(m["itr_cia_aberta_2025.csv"], "CD_CVM", {"005410"}))
dump("itr_cia_aberta_DRE_con_2025.csv",
     pick(m["itr_cia_aberta_DRE_con_2025.csv"], "CD_CVM", {"005410"},
          lambda r: r["CD_CONTA"].startswith(("3.11", "3.99", "3.01"))))

m = members(f"{CVM}/FCA/DADOS/fca_cia_aberta_2026.zip")
fidx = pick(m["fca_cia_aberta_2026.csv"], "CD_CVM", {"020257", "001023"})
dump("fca_cia_aberta_2026.csv", fidx)
dump("fca_cia_aberta_valor_mobiliario_2026.csv",
     pick(m["fca_cia_aberta_valor_mobiliario_2026.csv"], "CNPJ_Companhia",
          {"07.859.971/0001-30", "00.000.000/0001-91"}))

r = requests.get("https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv",
                 headers=UA, timeout=60)
cad = r.content.decode("latin-1").splitlines()
cols = cad[0].split(";")
ci = cols.index("CD_CVM")
from collections import Counter  # noqa: E402
dup = [k for k, v in Counter(ln.split(";")[ci] for ln in cad[1:]).items() if v > 1][:2]
dump("cad_cia_aberta.csv", pick(cad, "CD_CVM", {"5410", "19348", "21954"} | set(dup)))

# COTAHIST: linhas reais com FATCOT 1000 e linhas comuns
r = requests.get("https://bvmf.bmfbovespa.com.br/InstDados/SerHist/COTAHIST_A2010.ZIP",
                 headers=UA, timeout=300)
z = zipfile.ZipFile(io.BytesIO(r.content))
raw = z.read(z.namelist()[0]).decode("latin-1").splitlines()
out = [raw[0]]
fat = [ln for ln in raw if ln[:2] == "01" and ln[210:217] == "0001000" and ln[10:12] == "02"
       and ln[24:27] == "010"][:3]
out += fat
out += [ln for ln in raw if ln[:2] == "01" and ln[12:24].strip() in ("PETR4", "WEGE3")
        and ln[2:10] == "20100104"]
out += [ln for ln in raw if ln[:2] == "01" and ln[2:10] == "20100104" and ln[24:27] == "020"][:1]
out.append(raw[-1])
dump("COTAHIST_A2010_sample.TXT", out)
