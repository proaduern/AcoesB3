"""Sonda temporária do DFC (fluxo de caixa) das empresas da lista, para escolher as contas do FCFE.

Imprime, por empresa e exercício, as contas 6.01, 6.02 e 6.03 e os filhos (até o 3º nível) do
DFC consolidado (método indireto ou direto), com descrição e valor. Roda no GitHub Actions.
"""
import csv
import io
import sys
import zipfile

import requests

URL = "https://dados.cvm.gov.br/dados/CIA_ABERTA/DOC/DFP/DADOS/dfp_cia_aberta_{y}.zip"
# Lista acompanhada, sem bancos e seguradoras
CVM = {
    21490: "Alupar", 17329: "Engie", 18376: "ISA", 18627: "Sanepar", 19445: "Copasa",
    17671: "Vivo", 2453: "Cemig", 18660: "CPFL", 20257: "Taesa", 14443: "Sabesp", 24929: "TIM",
}
years = [int(y) for y in sys.argv[1:]] or [2024]
for y in years:
    r = requests.get(URL.format(y=y), headers={"User-Agent": "AcoesB3-probe"}, timeout=300)
    print(f"##### {y} status={r.status_code} bytes={len(r.content)}")
    z = zipfile.ZipFile(io.BytesIO(r.content))
    names = [n for n in z.namelist() if "DFC" in n]
    print("arquivos DFC:", names)
    for scope in ("con", "ind"):
        for kind in ("MI", "MD"):
            fname = f"dfp_cia_aberta_DFC_{kind}_{scope}_{y}.csv"
            if fname not in z.namelist():
                continue
            rows = list(csv.DictReader(io.TextIOWrapper(z.open(fname), encoding="latin-1"), delimiter=";"))
            present = {int(r["CD_CVM"]) for r in rows}
            for cvm, name in CVM.items():
                sel = [
                    r for r in rows
                    if int(r["CD_CVM"]) == cvm and r["ORDEM_EXERC"].startswith("ÚLT")
                    and r["CD_CONTA"].count(".") <= 2
                ]
                if not sel:
                    continue
                print(f"== {name} ({cvm}) {fname} escala={sel[0]['ESCALA_MOEDA']} fim={sel[0]['DT_FIM_EXERC']}")
                for r in sel:
                    print(f"  {r['CD_CONTA']:10} {r['DS_CONTA'][:90]:90} {r['VL_CONTA']}")
