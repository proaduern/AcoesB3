"""Sonda temporária (fase 4, 5ª rodada): série diária de IBOV e IDIV na API de estatísticas da B3."""
import base64
import json
import re

import requests

H = {"User-Agent": "AcoesB3/0.1 (+https://github.com/proaduern/AcoesB3)", "Accept": "*/*"}
api = "https://sistemaswebb3-listados.b3.com.br/indexStatisticsProxy/IndexCall/GetPortfolioDay"


def b64(d):
    return base64.b64encode(json.dumps(d, separators=(",", ":")).encode()).decode()


def year(idx, y):
    r = requests.get(f"{api}/{b64({'index': idx, 'language': 'pt-br', 'year': str(y)})}", headers=H, timeout=60)
    return r


for idx in ("IBOVESPA", "IDIV"):
    for y in (2005, 2011, 2012, 2013, 2023, 2026):
        r = year(idx, y)
        try:
            j = r.json()
        except Exception:  # noqa: BLE001
            print(idx, y, r.status_code, "sem JSON", r.text[:200])
            continue
        res = j.get("results", [])
        n = sum(1 for row in res for k, v in row.items() if k.startswith("rateValue") and v)
        print(idx, y, r.status_code, "chaves:", sorted(j), "linhas:", len(res), "valores:", n,
              "dias:", [row["day"] for row in res][:3], "...", [row["day"] for row in res][-2:])

print("\nIDIV 2012 completo:")
print(json.dumps(year("IDIV", 2012).json(), ensure_ascii=False)[:9000])
print("\nIBOVESPA 2026 (linhas 1-3 e 28-31):")
j = year("IBOVESPA", 2026).json()
for row in j["results"][:3] + j["results"][-4:]:
    print(row)
print("min/max:", j.get("min"), j.get("max"))

for u in ("https://www.b3.com.br/pt_br/market-data-e-indices/indices/indices-de-segmentos-e-setoriais/indice-dividendos-idiv.htm",
          "https://www.b3.com.br/pt_br/market-data-e-indices/indices/indices-amplos/ibovespa.htm"):
    t = requests.get(u, headers=H, timeout=60).text
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", t, flags=re.S)
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))
    print("\n", u)
    for kw in ("retorno total", "Retorno Total", "total return", "reinvest", "Reinvest", "dividendos"):
        for m in list(re.finditer(kw, t))[:2]:
            print(f"[{kw}]", t[max(0, m.start() - 250): m.end() + 250])
