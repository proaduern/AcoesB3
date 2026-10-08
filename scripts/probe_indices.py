"""Sonda temporária (fase 4, 3ª rodada): API da página de evolução diária dos índices da B3."""
import base64
import json
import re

import requests

H = {"User-Agent": "AcoesB3/0.1 (+https://github.com/proaduern/AcoesB3)", "Accept": "*/*"}
base = "https://sistemaswebb3-listados.b3.com.br"


def get(url):
    try:
        return requests.get(url, headers=H, timeout=60)
    except Exception as e:  # noqa: BLE001
        print(f"ERRO {url[:160]}: {e}")


def b64(d):
    return base64.b64encode(json.dumps(d, separators=(",", ":")).encode()).decode()


page = get(f"{base}/indexStatisticsPage/daily-evolution/IBOVESPA?language=pt-br")
print("page", page.status_code, len(page.text))
scripts = re.findall(r'src="([^"]+\.js)"', page.text)
print("scripts", scripts)
for sc in scripts:
    if "main" not in sc:
        continue
    u = sc if sc.startswith("http") else f"{base}/indexStatisticsPage/{sc.lstrip('/').removeprefix('indexStatisticsPage/')}"
    r = get(u)
    if r is None:
        continue
    t = r.text
    print("\njs", u, r.status_code, len(t))
    print("bases:", sorted(set(re.findall(r"https://sistemaswebb3-listados\.b3\.com\.br/[A-Za-z]+/[A-Za-z]+/?", t))))
    print("calls:", sorted(set(re.findall(r"(?:Get|Download)[A-Za-z]{4,50}", t)))[:100])
    for m in list(re.finditer(r"(?:Daily|Evolution|Annual|Year)[A-Za-z]*", t))[:0]:
        pass
    for m in list(re.finditer(r"indexStatisticsProxy|IndexCall|GetDaily|GetAnnual|GetEvolution", t))[:8]:
        print("trecho:", t[max(0, m.start() - 200): m.end() + 300].replace("\n", " "))
