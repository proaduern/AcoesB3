"""Sonda temporária (fase 4, 4ª rodada): chamadas da API de estatísticas de índices da B3."""
import base64
import json
import re

import requests

H = {"User-Agent": "AcoesB3/0.1 (+https://github.com/proaduern/AcoesB3)", "Accept": "*/*"}
base = "https://sistemaswebb3-listados.b3.com.br"
api = f"{base}/indexStatisticsProxy/IndexCall"


def get(url):
    try:
        return requests.get(url, headers=H, timeout=60)
    except Exception as e:  # noqa: BLE001
        print(f"ERRO {url[:160]}: {e}")


def b64(d):
    return base64.b64encode(json.dumps(d, separators=(",", ":")).encode()).decode()


js = get(f"{base}/indexStatisticsPage/main-es2015.204ca04ae07d2c137636.js").text
for name in ("GetPortfolioDay", "GetMonthlyEvolution", "GetYearlyVariation", "GetDownloadPortfolioDay"):
    for m in list(re.finditer(name, js))[:3]:
        print(f"\n--- {name}:", js[max(0, m.start() - 350): m.end() + 250].replace("\n", " "))

for call in ("GetPortfolioDay", "GetMonthlyEvolution", "GetYearlyVariation", "GetDownloadPortfolioDay"):
    for idx in ("IBOVESPA", "IBOV"):
        for payload in ({"index": idx, "language": "pt-br", "year": "2024"},
                        {"language": "pt-br", "index": idx, "year": "2024", "pageNumber": 1, "pageSize": 20}):
            u = f"{api}/{call}/{b64(payload)}"
            r = get(u)
            if r is not None:
                print(f"\n=== {r.status_code} {r.headers.get('content-type')} len={len(r.content)} {call} {payload}")
                print(r.text[:700].replace("\n", "\\n"))
