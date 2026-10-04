"""Sonda temporária da fase 2 (roda no GitHub Actions; remover depois de usada).

1. FRE (Formulário de Referência) da CVM Dados Abertos: existe? desde quando? traz quantidade
   de ações por classe? Nada é presumido: a listagem do diretório diz o que existe.
2. Descrição (DS_CONTA) das contas 3.99.01.0x (LPA) e 7.0x.04.0x (proventos na DVA) na DFP real:
   confirma se .01 é sempre ON e .02 sempre PN, e como bancos/seguradoras rotulam os proventos.
"""

import io
import re
import zipfile
from collections import Counter, defaultdict

import requests

CVM = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC"
UA = {"User-Agent": "Mozilla/5.0 AcoesB3-probe"}


def get(url):
    r = requests.get(url, headers=UA, timeout=300)
    print(f"GET {url} -> {r.status_code} len={len(r.content)} "
          f"last-modified={r.headers.get('Last-Modified')}")
    return r


def hrefs(url):
    r = get(url)
    if r.status_code != 200:
        return []
    found = re.findall(r'href="([^"?/][^"]*)"', r.text)
    print("   itens:", found[:80], "..." if len(found) > 80 else "")
    return found


def decode(raw):
    for enc in ("utf-8", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    raise ValueError("encoding")


def probe_fre():
    print("\n===== FRE =====")
    top = hrefs(f"{CVM}/")
    if not any("FRE" in h for h in top):
        print("!! diretório FRE não aparece em DOC/")
    for sub in ("FRE/", "FRE/DADOS/", "FRE/META/"):
        items = hrefs(f"{CVM}/{sub}")
        print(f"   {sub}: {len(items)} itens")
    zips = sorted(h for h in hrefs(f"{CVM}/FRE/DADOS/") if h.lower().endswith(".zip"))
    years = {}
    for z in zips:
        m = re.search(r"(\d{4})\.zip$", z, re.I)
        if m:
            years[int(m.group(1))] = z
    print("   anos com zip:", sorted(years))
    if not years:
        return
    pick = sorted({min(years), 2012 if 2012 in years else min(years), 2018 if 2018 in years else max(years), max(years)})
    for y in pick:
        r = get(f"{CVM}/FRE/DADOS/{years[y]}")
        if r.status_code != 200:
            continue
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        names = [i.filename for i in zf.infolist()]
        print(f"   [{y}] {len(names)} arquivos: {names}")
        for n in names:
            if re.search(r"capital|acao|acoes|valor_mobiliario|composicao", n, re.I) and n.endswith(".csv"):
                txt = decode(zf.read(n)).splitlines()
                print(f"   == [{y}] {n}: {len(txt) - 1} linhas")
                for ln in txt[:4]:
                    print("      |", ln[:700])
                cols = txt[0].split(";")
                cnpj_i = next((i for i, c in enumerate(cols) if c.upper().startswith("CNPJ")), None)
                if cnpj_i is not None:
                    cnpjs = {l.split(";")[cnpj_i] for l in txt[1:] if l.count(";") == len(cols) - 1}
                    print(f"      empresas distintas: {len(cnpjs)}")


def probe_accounts():
    print("\n===== DESCRIÇÃO DAS CONTAS (DFP) =====")
    for y in (2012, 2020, 2024):
        r = get(f"{CVM}/DFP/DADOS/dfp_cia_aberta_{y}.zip")
        if r.status_code != 200:
            continue
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        for member, patt in (
            (f"dfp_cia_aberta_DRE_con_{y}.csv", r"^3\.99\.01\.0\d$"),
            (f"dfp_cia_aberta_DVA_con_{y}.csv", r"^7\.(08|09|11)\.04\.0[12]$"),
            (f"dfp_cia_aberta_DVA_ind_{y}.csv", r"^7\.(08|09|11)\.04\.0[12]$"),
        ):
            if member not in zf.namelist():
                print(f"   [{y}] {member}: ausente")
                continue
            lines = decode(zf.read(member)).splitlines()
            cols = lines[0].split(";")
            ic, id_, io_ = cols.index("CD_CONTA"), cols.index("DS_CONTA"), cols.index("ORDEM_EXERC")
            tally = defaultdict(Counter)
            companies = set()
            for ln in lines[1:]:
                p = ln.split(";")
                if len(p) != len(cols) or p[io_] != "ÚLTIMO" or not re.match(patt, p[ic]):
                    continue
                tally[p[ic]][p[id_]] += 1
                companies.add(p[cols.index("CD_CVM")])
            print(f"   [{y}] {member}: {len(companies)} empresas com a conta")
            for code in sorted(tally):
                print(f"      {code}: {tally[code].most_common(6)}")


if __name__ == "__main__":
    probe_fre()
    probe_accounts()
