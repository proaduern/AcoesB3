"""Sonda temporária (fase 4): formato real do CDI (BCB) e dos índices IBOV/IDIV (B3). Só imprime."""
import base64
import json
import re

import requests

H = {"User-Agent": "AcoesB3/0.1 (+https://github.com/proaduern/AcoesB3)", "Accept": "*/*"}


def show(url, n=600):
    try:
        r = requests.get(url, headers=H, timeout=60)
        print(f"\n=== {r.status_code} {r.headers.get('content-type')} len={len(r.content)} {url[:200]}")
        print(r.text[:n].replace("\n", "\\n"))
        return r
    except Exception as e:  # noqa: BLE001
        print(f"\n=== ERRO {url[:200]}: {e}")


def b64(d):
    return base64.b64encode(json.dumps(d, separators=(",", ":")).encode()).decode()


sgs = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.{}/dados"
for s in (12, 11, 4391, 4389, 7):
    show(sgs.format(s) + "/ultimos/3?formato=json")
show(sgs.format(12) + "?formato=json&dataInicial=02/01/2012&dataFinal=31/12/2012", 300)
show(sgs.format(12) + "?formato=json&dataInicial=02/01/2012&dataFinal=31/12/2023", 300)
show(sgs.format(12) + "?formato=json", 300)
show("https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados?formato=csv&dataInicial=02/01/2024&dataFinal=10/01/2024", 300)

base = "https://sistemaswebb3-listados.b3.com.br"
for idx in ("IBOV", "IDIV"):
    r = show(f"{base}/indexPage/day/{idx}?language=pt-br", 300)
    if r is not None:
        scripts = re.findall(r'src="([^"]+\.js)"', r.text)
        print("scripts:", scripts[:10])
        for sc in scripts[:6]:
            u = sc if sc.startswith("http") else base + sc
            try:
                t = requests.get(u, headers=H, timeout=60).text
            except Exception as e:  # noqa: BLE001
                print("erro js", u, e)
                continue
            found = set(re.findall(r'["\'`/]([A-Za-z]*Proxy/[A-Za-z]+/[A-Za-z]+)', t))
            print("js", u, len(t), sorted(found)[:30])
    for path in ("indexStatisticsProxy/IndexCall/GetDailyStatistics",
                 "indexStatisticsProxy/IndexCall/GetHistoricalData",
                 "indexProxy/indexCall/GetPortfolioDay",
                 "indexProxy/indexCall/GetDownloadPortfolioDay"):
        for payload in ({"language": "pt-br", "index": idx, "year": "2024"},
                        {"language": "pt-br", "pageNumber": 1, "pageSize": 20, "index": idx, "year": "2024"}):
            show(f"{base}/{path}/{b64(payload)}", 400)
for u in ("https://www.b3.com.br/pt_br/market-data-e-indices/indices/indices-amplos/ibovespa.htm",
          "https://www.b3.com.br/pt_br/market-data-e-indices/indices/indices-de-segmentos-e-setoriais/indice-dividendos-idiv.htm"):
    r = show(u, 200)
    if r is not None:
        print("links:", [x for x in re.findall(r'href="([^"]+)"', r.text) if re.search(r"hist|serie|download|xls|csv|indexPage|statistic", x, re.I)][:30])
