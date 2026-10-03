"""Sonda as fontes reais (CVM Dados Abertos e B3 COTAHIST) e imprime o formato.

Uso único para verificar formatos antes de escrever os parsers. Roda no
GitHub Actions porque o ambiente de desenvolvimento não alcança esses hosts.
"""
import io
import re
import sys
import zipfile
from collections import Counter

import requests

CVM = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC"
UA = {"User-Agent": "Mozilla/5.0 AcoesB3-probe"}


def get(url, **kw):
    r = requests.get(url, headers=UA, timeout=180, **kw)
    print(f"GET {url} -> {r.status_code} len={len(r.content)} "
          f"last-modified={r.headers.get('Last-Modified')} "
          f"content-type={r.headers.get('Content-Type')}")
    return r


def listing(url):
    r = get(url)
    text = r.text
    rows = re.findall(r'href="([^"?/][^"]*)".*?(\d{4}-\d{2}-\d{2} \d{2}:\d{2}|\d{2}-\w{3}-\d{4} \d{2}:\d{2})\s+(\S+)', text)
    for row in rows:
        print("   ", *row)
    if not rows:
        print(text[:3000])


def show_zip(url, max_files=40, lines=3, scan_cols=("ESCALA_MOEDA", "MOEDA", "ORDEM_EXERC", "ST_CONTA_FIXA", "VERSAO")):
    r = get(url)
    z = zipfile.ZipFile(io.BytesIO(r.content))
    for info in z.infolist()[:max_files]:
        print(f"== {info.filename} size={info.file_size} date={info.date_time}")
        raw = z.read(info.filename)
        for enc in ("utf-8", "latin-1"):
            try:
                txt = raw.decode(enc)
                print(f"   encoding OK: {enc}")
                break
            except UnicodeDecodeError:
                print(f"   encoding fails: {enc}")
        head = txt.splitlines()
        for ln in head[:lines + 1]:
            print("   |", ln[:600])
        print(f"   total lines={len(head)}")
        if ";" in head[0]:
            cols = head[0].split(";")
            for c in scan_cols:
                if c in cols:
                    i = cols.index(c)
                    cnt = Counter(l.split(";")[i] for l in head[1:] if l.count(";") == len(cols) - 1)
                    print(f"   distinct {c}: {cnt.most_common(10)}")
            for c in ("DT_RECEB",):
                if c in cols:
                    i = cols.index(c)
                    vals = sorted({l.split(";")[i] for l in head[1:] if l.count(";") == len(cols) - 1})
                    print(f"   {c} min={vals[:1]} max={vals[-5:]}")
            bad = sum(1 for l in head[1:] if l.count(";") != len(cols) - 1)
            print(f"   lines with wrong field count: {bad}")


def main():
    for kind in ("DFP", "ITR", "FCA"):
        print(f"\n######## {kind} META")
        listing(f"{CVM}/{kind}/META/")
        print(f"\n######## {kind} DADOS listing")
        listing(f"{CVM}/{kind}/DADOS/")
    for meta in ("DFP/META/meta_dfp_cia_aberta.txt", "ITR/META/meta_itr_cia_aberta.txt"):
        print(f"\n######## {meta}")
        r = get(f"{CVM}/{meta}")
        print(r.content.decode("latin-1")[:6000])
    print("\n######## FCA meta zip")
    try:
        show_zip(f"{CVM}/FCA/META/meta_fca_cia_aberta_txt.zip", lines=200)
    except Exception as e:  # noqa: BLE001
        print("fca meta failed", e)
    print("\n######## DFP 2024")
    show_zip(f"{CVM}/DFP/DADOS/dfp_cia_aberta_2024.zip")
    print("\n######## ITR 2026")
    show_zip(f"{CVM}/ITR/DADOS/itr_cia_aberta_2026.zip")
    print("\n######## FCA 2026")
    show_zip(f"{CVM}/FCA/DADOS/fca_cia_aberta_2026.zip")
    print("\n######## CAD")
    r = get("https://dados.cvm.gov.br/dados/CIA_ABERTA/CAD/DADOS/cad_cia_aberta.csv")
    t = r.content.decode("latin-1").splitlines()
    print("\n".join(x[:600] for x in t[:3]), "\n lines=", len(t))

    print("\n######## COTAHIST")
    base = "https://bvmf.bmfbovespa.com.br/InstDados/SerHist"
    for name in ("COTAHIST_A2024.ZIP", "COTAHIST_A2010.ZIP", "COTAHIST_A1986.ZIP"):
        try:
            r = get(f"{base}/{name}")
            z = zipfile.ZipFile(io.BytesIO(r.content))
            for info in z.infolist():
                print(f"== {info.filename} size={info.file_size}")
                raw = z.read(info.filename)
                lines = raw.split(b"\r\n") if b"\r\n" in raw else raw.split(b"\n")
                print("   line lengths:", Counter(len(l) for l in lines).most_common(5))
                for l in lines[:4] + lines[-3:]:
                    print("   |", l.decode("latin-1"))
                # amostra de ações conhecidas
                for l in lines:
                    s = l.decode("latin-1")
                    if s[2:10] in ("20240102", "20100104") and s[12:24].strip() in ("PETR4", "TAEE11", "ITUB4", "BBAS3"):
                        print("   sample |", s)
                tpm = Counter(l[24:27].decode("latin-1") for l in lines if l[:2] == b"01")
                print("   TPMERC:", tpm.most_common(20))
                codbdi = Counter(l[10:12].decode("latin-1") for l in lines if l[:2] == b"01")
                print("   CODBDI:", codbdi.most_common(30))
                fat = Counter(l[210:217].decode("latin-1") for l in lines if l[:2] == b"01")
                print("   FATCOT:", fat.most_common(5))
        except Exception as e:  # noqa: BLE001
            print("failed", name, e)
    for name in ("COTAHIST_D30092026.ZIP", "COTAHIST_M092026.ZIP"):
        try:
            r = get(f"{base}/{name}")
            z = zipfile.ZipFile(io.BytesIO(r.content))
            print([i.filename for i in z.infolist()])
        except Exception as e:  # noqa: BLE001
            print("failed", name, e)


if __name__ == "__main__":
    sys.exit(main())
