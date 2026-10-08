"""Sonda temporária (fase 4, 2ª rodada): onde a B3 publica a série histórica de IBOV e IDIV."""
import base64
import json
import re

import requests

H = {"User-Agent": "AcoesB3/0.1 (+https://github.com/proaduern/AcoesB3)", "Accept": "*/*"}


def get(url, **kw):
    try:
        return requests.get(url, headers=H, timeout=60, **kw)
    except Exception as e:  # noqa: BLE001
        print(f"ERRO {url[:160]}: {e}")


def show(url, n=500):
    r = get(url)
    if r is not None:
        print(f"\n=== {r.status_code} {r.headers.get('content-type')} len={len(r.content)} {url[:220]}")
        print(r.text[:n].replace("\n", "\\n"))
    return r


def b64(d):
    return base64.b64encode(json.dumps(d, separators=(",", ":")).encode()).decode()


for u in (
    "https://www.b3.com.br/pt_br/market-data-e-indices/indices/indices-amplos/indice-ibovespa-ibovespa-estatisticas-historicas.htm",
    "https://www.b3.com.br/pt_br/market-data-e-indices/indices/indices-de-segmentos-e-setoriais/indice-dividendos-idiv-estatisticas-historicas.htm",
):
    r = get(u)
    if r is None:
        continue
    t = r.text
    print(f"\n=== {r.status_code} len={len(t)} {u}")
    print("iframes:", re.findall(r"<iframe[^>]+>", t)[:5])
    print("srcs:", [s for s in re.findall(r'(?:src|href)="([^"]+)"', t) if re.search(r"index|statist|download|xls|csv|b3\.com\.br/(?!pt_br)", s, re.I)][:30])
    print("proxy:", sorted(set(re.findall(r"[A-Za-z]*(?:Proxy|proxy)/[A-Za-z/]+", t)))[:20])

base = "https://sistemaswebb3-listados.b3.com.br"
for page in ("indexPage/day/IBOV?language=pt-br", "indexStatisticsPage/day/IBOV?language=pt-br",
             "indexStatisticsPage/IBOV?language=pt-br", "indexPage/statistics/IBOV?language=pt-br"):
    show(f"{base}/{page}", 300)

r = get(f"{base}/indexPage/main-es2015.734bba7ef4f937ebc80b.js")
if r is not None:
    t = r.text
    print("\nmain js len", len(t))
    print("proxy:", sorted(set(re.findall(r"[A-Za-z]*Proxy/[A-Za-z]+/[A-Za-z]+", t))))
    for m in re.finditer(r"(GetDaily|Historic|Statistic|GetDownload|GetPortfolio|GetChart|GetAnnual|GetYear)[A-Za-z]*", t):
        pass
    print("calls:", sorted(set(re.findall(r"(?:Get|Download)[A-Za-z]{4,40}", t)))[:80])
    print("trechos:", [t[max(0, m.start() - 120): m.end() + 200].replace("\n", " ") for m in re.finditer(r"Proxy/", t)][:6])
