"""Sonda temporária (fase 4): tarifas da B3 para ações à vista (negociação e pós-negociação)."""
import io
import re

import requests

H = {"User-Agent": "AcoesB3/0.1 (+https://github.com/proaduern/AcoesB3)", "Accept": "*/*"}


def get(url):
    try:
        r = requests.get(url, headers=H, timeout=90)
        print(f"\n=== {r.status_code} {r.headers.get('content-type')} len={len(r.content)} {url}")
        return r
    except Exception as e:  # noqa: BLE001
        print(f"ERRO {url}: {e}")


page = get("https://www.b3.com.br/pt_br/produtos-e-servicos/tarifas/listados-a-vista-e-derivativos/renda-variavel/")
if page is not None:
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", page.text, flags=re.S)
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"\s+", " ", t)
    for m in list(re.finditer(r"(?i)a vista|à vista", t))[:0]:
        pass
    i = t.lower().find("ações")
    print("texto (trecho):", t[:200])
    for kw in ("Tarifação", "vigência", "Vigência", "0,0", "ADTV", "pessoa física", "Pessoa Física"):
        for m in list(re.finditer(kw, t))[:4]:
            print(f"[{kw}]", t[max(0, m.start() - 200): m.end() + 400])
    print("links:", [x for x in re.findall(r'href="([^"]+)"', page.text) if re.search(r"(?i)tarifa|pdf|equities", x)][:40])

for url in (
    "https://www.b3.com.br/data/files/8D/10/AA/8A/964599100A29E189AC094EA8/Tarifacao_Equities_V3_PT.pdf",
):
    r = get(url)
    if r is not None and r.status_code == 200:
        try:
            import subprocess
            import sys
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", "pypdf"], check=True)
            from pypdf import PdfReader
            rd = PdfReader(io.BytesIO(r.content))
            print("páginas:", len(rd.pages))
            for i, p in enumerate(rd.pages):
                txt = p.extract_text() or ""
                if 4 <= i <= 9 or i == 0:
                    print(f"--- pág {i + 1}")
                    print(txt[:3800])
        except Exception as e:  # noqa: BLE001
            print("erro pdf", e)
