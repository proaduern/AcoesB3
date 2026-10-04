"""Relatório de medição da fase 2 (temporário; roda no GitHub Actions depois do compute).

Lê o banco e imprime: cobertura por ano e plano, distribuição dos status, eventos societários
e o DISMES, outliers, mapeamento de tickers e a comparação das três regras em discussão
(payout, outlier, dividendo por ação). Só leitura.
"""

import os
import statistics
from collections import Counter, defaultdict
from datetime import date
from decimal import Decimal

import psycopg

from acoesb3 import compute, corporate, mapping

D = Decimal
LINES: list[str] = []


def out(*a):
    s = " ".join(str(x) for x in a)
    print(s)
    LINES.append(s)


def section(title):
    out(f"\n## {title}")


def q(conn, sql, params=None):
    return conn.execute(sql, params).fetchall()


def main():
    conn = psycopg.connect(os.environ["NEON_DATABASE_URL"])
    cfg = compute.load_config(conn)
    today = max(r[0] for r in q(conn, "SELECT DISTINCT as_of FROM screen_result"))

    section("Tabelas")
    for t in ("company", "filing", "financial_line", "quote_daily", "security", "company_security",
              "share_count", "indicator_annual", "dividend_outlier", "corporate_event",
              "screen_result", "screen_criterion"):
        out(f"{t:20} {q(conn, f'SELECT count(*) FROM {t}')[0][0]:>10}")

    section("Duração das etapas (collection_run)")
    for job, n, secs, bad in q(
        conn,
        """SELECT regexp_replace(job, '_[0-9]{4,8}$', '_*') AS j, count(*),
                  round(sum(extract(epoch FROM finished_at - started_at)))::int,
                  count(*) FILTER (WHERE status <> 'ok')
           FROM collection_run GROUP BY 1 ORDER BY 3 DESC NULLS LAST""",
    ):
        out(f"{job:28} {n:>4} execuções {secs or 0:>6} s  não-ok: {bad}")

    section("Cobertura dos fatos anuais por exercício (linhas; sem lucro / PL / proventos / ações / LPA ON)")
    out("ano   n  comum banco segur indef | sem_lucro sem_PL sem_prov sem_ações sem_LPA")
    for y, n, c, b, s, i, nl, ne, nd, ns, nlpa in q(
        conn,
        """SELECT extract(year FROM reference_date)::int, count(*),
                  count(*) FILTER (WHERE plan='comum'), count(*) FILTER (WHERE plan='banco'),
                  count(*) FILTER (WHERE plan='seguradora'), count(*) FILTER (WHERE plan IS NULL),
                  count(*) FILTER (WHERE profit IS NULL), count(*) FILTER (WHERE equity IS NULL),
                  count(*) FILTER (WHERE dividends IS NULL),
                  count(*) FILTER (WHERE shares_on IS NULL), count(*) FILTER (WHERE lpa_on IS NULL)
           FROM indicator_annual GROUP BY 1 ORDER BY 1""",
    ):
        out(f"{y} {n:>4} {c:>5} {b:>5} {s:>5} {i:>5} | {nl:>9} {ne:>6} {nd:>8} {ns:>9} {nlpa:>7}")

    section("Banco/seguradora sem proventos (deveria ser ~0 após reload das DFP)")
    for plan, n, nd in q(
        conn,
        """SELECT plan, count(*), count(*) FILTER (WHERE dividends IS NULL)
           FROM indicator_annual WHERE reference_date >= '2020-01-01' AND plan IS NOT NULL GROUP BY 1""",
    ):
        out(f"{plan:12} {n} exercícios 2020+, {nd} sem proventos")

    section("Empresas sem plano identificado (amostra)")
    for cvm, name, ref, notes in q(
        conn,
        """SELECT a.cvm_code, c.name, a.reference_date, a.notes::text FROM indicator_annual a
           JOIN company c USING (cvm_code) WHERE a.plan IS NULL AND a.reference_date >= '2022-01-01'
           ORDER BY random() LIMIT 8""",
    ):
        out(f"{cvm} {name[:40]} {ref} {notes[:140]}")

    section("Status dos retratos")
    for as_of, status, n in q(
        conn, "SELECT as_of, status, count(*) FROM screen_result GROUP BY 1, 2 ORDER BY 1, 3 DESC"
    ):
        out(f"{as_of} {status:22} {n}")

    section(f"Critérios em {today} (status e motivo de indisponibilidade)")
    for crit, status, reason, n in q(
        conn,
        """SELECT criterion, status, detail->>'reason', count(*) FROM screen_criterion
           WHERE as_of = %s GROUP BY 1, 2, 3 ORDER BY 1, 4 DESC""",
        (today,),
    ):
        out(f"{crit:28} {status:12} {str(reason):18} {n}")

    section("Empresas aprovadas hoje")
    rows = q(
        conn,
        """SELECT r.cvm_code, c.name, r.data_base FROM screen_result r JOIN company c USING (cvm_code)
           WHERE r.as_of = %s AND r.status = 'approved' ORDER BY c.name""",
        (today,),
    )
    out(f"{len(rows)} aprovadas")
    for cvm, name, base in rows[:80]:
        out(f"  {cvm:>6} {name[:44]:44} base {base}")

    section("Empresas conhecidas hoje (critério: status/valor)")
    for like in ("WEG S.A.", "ITAÚ UNIBANCO HOLDING", "BB SEGURIDADE", "TAESA", "BANCO DO BRASIL S.A.",
                 "PETRÓLEO BRASILEIRO", "VALE S.A.", "ITAÚSA", "AMBEV", "ENGIE BRASIL", "LOCALIZA"):
        for cvm, name in q(conn, "SELECT cvm_code, name FROM company WHERE upper(name) LIKE %s LIMIT 2",
                           (like.upper() + "%",)):
            res = q(conn, "SELECT status FROM screen_result WHERE cvm_code=%s AND as_of=%s", (cvm, today))
            out(f"{name[:40]} ({cvm}) -> {res[0][0] if res else 'sem retrato'}")
            for c, st, v, thr in q(
                conn,
                "SELECT criterion, status, value, threshold FROM screen_criterion"
                " WHERE cvm_code=%s AND as_of=%s ORDER BY 1", (cvm, today),
            ):
                out(f"      {c:28} {st:12} {str(v)[:14]:14} {thr}")

    section("Eventos societários")
    for st, n, ch in q(conn, "SELECT status, count(*), count(*) FILTER (WHERE dismes_changed) FROM corporate_event GROUP BY 1"):
        out(f"{st:10} {n:>5}  (DISMES mudou em {ch})")
    base = q(
        conn,
        """SELECT count(*), count(*) FILTER (WHERE distribution <> prev) FROM (
             SELECT distribution, lag(distribution) OVER (PARTITION BY security_id ORDER BY trade_date) AS prev
             FROM quote_daily) t WHERE prev IS NOT NULL""",
    )[0]
    out(f"DISMES muda em {base[1]} de {base[0]} pregões ({100 * base[1] / base[0]:.2f}%): "
        "se for alto, mudança de DISMES é evidência fraca de evento")
    for tk in ("WEGE3", "ITUB4", "PETR4", "VALE3", "BBAS3", "TAEE11", "TAEE3", "EGIE3", "ABEV3", "RENT3", "LREN3", "BBSE3"):
        evs = q(
            conn,
            """SELECT e.event_date, e.factor, e.observed_ratio, e.dismes_changed, e.status
               FROM corporate_event e JOIN security s ON s.id = e.security_id WHERE s.ticker = %s ORDER BY 1""",
            (tk,),
        )
        out(f"{tk:7} {len(evs)} eventos: " + "; ".join(f"{d} x{float(f):g} ({st}, DISMES {'sim' if ch else 'não'})" for d, f, _, ch, st in evs))
    out("-- 15 eventos 'suspected' mais recentes")
    for d, tk, f, r, ch in q(
        conn,
        """SELECT e.event_date, s.ticker, e.factor, e.observed_ratio, e.dismes_changed FROM corporate_event e
           JOIN security s ON s.id = e.security_id WHERE e.status = 'suspected' ORDER BY 1 DESC LIMIT 15""",
    ):
        out(f"   {d} {tk:8} fator {float(f):g} razão {float(r):.4f} DISMES {'sim' if ch else 'não'}")

    section("Outliers de proventos")
    n = q(conn, "SELECT count(*) FROM dividend_outlier")[0][0]
    out(f"{n} marcados")
    for cvm, name, ref, total, med, ratio in q(
        conn,
        """SELECT o.cvm_code, c.name, o.reference_date, o.total, o.median, o.ratio FROM dividend_outlier o
           JOIN company c USING (cvm_code) ORDER BY o.ratio DESC LIMIT 15""",
    ):
        out(f"   {name[:36]:36} {ref} total {total:,.0f} mediana {med:,.0f} x{float(ratio):.1f}")

    section("Mapeamento de tickers")
    by_company, ambiguous, unmapped = compute._company_securities(conn)
    out(f"{len(by_company)} empresas com papel; raízes ambíguas: {len(ambiguous)} {dict(list(ambiguous.items())[:10])}")
    out("papéis sem empresa (maior volume): " + ", ".join(f"{t} ({v / 1e9:.1f} bi)" for t, v in sorted(unmapped, key=lambda x: -x[1])[:15]))

    diagnostics(conn, today)
    sensitivity(conn, cfg, today, by_company)

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("```\n" + "\n".join(LINES)[:900_000] + "\n```\n")


def diagnostics(conn, today):
    names = dict(q(conn, "SELECT cvm_code, name FROM company"))

    section("Diagnóstico: DFP sem plano de contas (2022+): escopo e contas de lucro presentes")
    combos = Counter()
    for fid, cons, codes, dre in q(
        conn,
        """SELECT f.id, bool_or(fl.consolidated),
                  array_agg(DISTINCT fl.account_code) FILTER (WHERE fl.statement = 'DRE' AND fl.account_code IN
                      ('3.09','3.11','3.13','3.09.01','3.11.01','3.13.01')),
                  count(*) FILTER (WHERE fl.statement = 'DRE')
           FROM indicator_annual a JOIN filing f ON f.id = a.filing_id
           LEFT JOIN financial_line fl ON fl.filing_id = f.id AND fl.period_end = f.reference_date
           WHERE a.plan IS NULL AND a.reference_date >= '2022-01-01' GROUP BY f.id""",
    ):
        combos[(cons, tuple(sorted(codes or [])), dre > 0)] += 1
    for (cons, codes, has_dre), n in combos.most_common(12):
        out(f"{n:>5}  consolidada={cons} DRE_presente={has_dre} contas={list(codes)}")

    section("Diagnóstico: fatos anuais de empresas conhecidas (R$ milhões; ações em milhões)")
    for cvm in (1023, 19348, 9512, 4170, 23264, 17329, 5410, 20257, 11258, 8036):
        out(f"-- {names.get(cvm, cvm)} ({cvm})")
        for ref, plan, pr, eq, jcp, div, src, lpa_on, lpa_pn, s_on, s_pn, notes in q(
            conn,
            """SELECT reference_date, plan, profit/1e6, equity/1e6, jcp/1e6, dividends/1e6, dividends_source,
                      lpa_on, lpa_pn, shares_on/1e6, shares_pn/1e6, notes::text
               FROM indicator_annual WHERE cvm_code = %s AND reference_date >= '2018-01-01' ORDER BY 1""",
            (cvm,),
        ):
            f = lambda v: "-" if v is None else f"{float(v):,.1f}"  # noqa: E731
            out(f"   {ref.year} {str(plan):10} lucro {f(pr):>10} PL {f(eq):>10} JCP {f(jcp):>9} div {f(div):>10} "
                f"LPA {f(lpa_on)}/{f(lpa_pn)} ações {f(s_on)}/{f(s_pn)} {notes[:90] if notes != '{}' else ''}")
        for crit, reason, detail in q(
            conn,
            "SELECT criterion, detail->>'reason', detail::text FROM screen_criterion"
            " WHERE cvm_code=%s AND as_of=%s AND status='unavailable' ORDER BY 1", (cvm, today),
        ):
            out(f"   indisponível {crit}: {detail[:200]}")

    section("Diagnóstico: escala das ações (ações x LPA / lucro, exercício mais recente; ~1 = coerente, ~1000 = ações em milhares)")
    ratios = []
    for cvm, ref, ratio in q(
        conn,
        """SELECT DISTINCT ON (cvm_code) cvm_code, reference_date,
                  (shares_on + shares_pn) * coalesce(lpa_on, lpa_pn) / nullif(profit, 0)
           FROM indicator_annual
           WHERE profit > 0 AND coalesce(lpa_on, lpa_pn) > 0 AND shares_on IS NOT NULL
           ORDER BY cvm_code, reference_date DESC""",
    ):
        ratios.append((cvm, float(ratio)))
    bins = Counter("<0,4" if r < 0.4 else "0,4-2,5" if r <= 2.5 else "2,5-400" if r < 400 else "~1000x (400-2500)" if r <= 2500 else ">2500" for _, r in ratios)
    out(f"{len(ratios)} empresas: {dict(bins)}")
    for cvm, r in sorted(ratios, key=lambda x: -abs(x[1] - 1))[:12]:
        out(f"   {names[cvm][:40]:40} razão {r:,.3f}")

    section("Diagnóstico: formatos de ticker no FCA e papéis sem empresa")
    odd = q(conn, "SELECT count(*), count(DISTINCT ticker) FROM company_security WHERE ticker IS NOT NULL AND ticker !~ '^[A-Z]{4}[0-9]{1,2}$'")[0]
    out(f"tickers fora do padrão 4 letras + número: {odd[0]} linhas, {odd[1]} distintos")
    out("amostra: " + ", ".join(r[0] for r in q(conn, "SELECT DISTINCT ticker FROM company_security WHERE ticker IS NOT NULL AND ticker !~ '^[A-Z]{4}[0-9]{1,2}$' ORDER BY 1 LIMIT 30")))
    _, _, unmapped = compute._company_securities(conn)
    for tk, vol in sorted(unmapped, key=lambda x: -x[1])[:12]:
        root = tk[:4]
        hit = q(conn, "SELECT DISTINCT cvm_code, ticker FROM company_security WHERE ticker ILIKE %s LIMIT 3", (root + "%",))
        out(f"   {tk:8} {vol / 1e9:7.1f} bi  FCA com '{root}': {hit}")

    section("Diagnóstico: líquidas com proventos zero em 5+ dos últimos 10 anos (DVA pode não cobrir)")
    for cvm, n0, nn in q(
        conn,
        """SELECT a.cvm_code, count(*) FILTER (WHERE a.jcp + a.dividends = 0), count(*)
           FROM indicator_annual a JOIN screen_criterion c ON c.cvm_code = a.cvm_code AND c.as_of = %s
                AND c.criterion = 'liquidez' AND c.status = 'pass'
           WHERE a.reference_date >= '2016-01-01' AND a.jcp IS NOT NULL AND a.dividends IS NOT NULL
           GROUP BY 1 HAVING count(*) FILTER (WHERE a.jcp + a.dividends = 0) >= 5 ORDER BY 2 DESC LIMIT 25""",
        (today,),
    ):
        out(f"   {names[cvm][:44]:44} {n0} de {nn} anos com proventos zero")


def sensitivity(conn, cfg, today, by_company):
    section("Sensibilidade das regras em discussão (retrato de hoje)")

    # 1. Payout: média de 5 anos (atual) x cada ano dentro da faixa
    lo, hi = D(str(cfg["screen.payout_min"])), D(str(cfg["screen.payout_max"]))
    diff = []
    total = 0
    for cvm, st, detail in q(
        conn,
        "SELECT cvm_code, status, detail FROM screen_criterion WHERE as_of=%s AND criterion='payout_medio' AND status <> 'unavailable'",
        (today,),
    ):
        pays = [D(v) for v in detail["payout"].values()]
        mean_ok = st == "pass"
        each_ok = all(lo <= p <= hi for p in pays)
        total += 1
        if mean_ok != each_ok:
            diff.append((cvm, mean_ok, each_ok, min(pays), max(pays)))
    out(f"Payout: {total} empresas avaliáveis; média passa e 'todo ano' reprova (ou o inverso) em {len(diff)}")
    names = dict(q(conn, "SELECT cvm_code, name FROM company"))
    for cvm, m, e, mn, mx in diff[:10]:
        out(f"   {names[cvm][:36]:36} média {'passa' if m else 'reprova'} | todo ano {'passa' if e else 'reprova'} | min {float(mn):.2f} max {float(mx):.2f}")

    # 2. Outlier: mediana dos 5 anos anteriores (atual) x janela de 5 anos incluindo o próprio ano
    mult = D(str(cfg["outlier.multiple"]))
    my = int(cfg["outlier.median_years"])
    mh = int(cfg["outlier.min_history_years"])
    totals = defaultdict(dict)
    for cvm, ref, jcp, div in q(conn, "SELECT cvm_code, reference_date, jcp, dividends FROM indicator_annual WHERE jcp IS NOT NULL AND dividends IS NOT NULL"):
        totals[cvm][ref.year] = jcp + div
    cur, alt = set(), set()
    for cvm, t in totals.items():
        for y, tot in t.items():
            prev = [t[k] for k in range(y - my, y) if k in t]
            if len(prev) >= mh:
                med = statistics.median(prev)
                if med > 0 and tot > mult * med:
                    cur.add((cvm, y))
            incl = [t[k] for k in range(y - my + 1, y + 1) if k in t]
            if len(incl) >= mh:
                med = statistics.median(incl)
                if med > 0 and tot > mult * med:
                    alt.add((cvm, y))
    out(f"Outlier: sem o próprio ano {len(cur)} marcados | incluindo o próprio ano {len(alt)} | só no primeiro {len(cur - alt)} | só no segundo {len(alt - cur)}")
    out("   (a mediana que inclui o próprio ano torna difícil passar de 2x; observar se o segundo perde os casos extremos)")

    # 3. Dividendo por ação: payout x LPA (atual) x total / ações (2020+)
    events = compute._applied_events(conn)
    refs = {c: mapping.reference_security(s) for c, s in by_company.items()}
    rows = defaultdict(dict)
    for cvm, ref, profit, jcp, div, lpa_on, lpa_pn, s_on, s_pn in q(
        conn,
        "SELECT cvm_code, reference_date, profit, jcp, dividends, lpa_on, lpa_pn, shares_on, shares_pn"
        " FROM indicator_annual WHERE reference_date >= '2020-01-01'",
    ):
        rows[cvm][ref.year] = (ref, profit, jcp, div, lpa_on, lpa_pn, s_on, s_pn)
    comparable = same = 0
    differ = []
    multi = 0
    for cvm, ys in rows.items():
        r = refs.get(cvm)
        ev = events.get(r[1], []) if r else []
        a, b = {}, {}
        for y, (ref, profit, jcp, div, lpa_on, lpa_pn, s_on, s_pn) in ys.items():
            if jcp is None or div is None or not profit or profit <= 0:
                continue
            tot = jcp + div
            lpa = lpa_on if (r is None or r[0] == "on") else lpa_pn
            f = corporate.cumulative_factor(ev, ref, today)
            if lpa is not None:
                a[y] = tot / profit * lpa / f
            if s_on is not None and s_pn is not None and s_on + s_pn > 0:
                b[y] = tot / (s_on + s_pn) / f
            if s_on and s_pn:
                multi += 1
        def drops(d):
            return {y for y in d if y - 1 in d and d[y] < d[y - 1]}
        common = a.keys() & b.keys()
        if len(common) >= 4:
            comparable += 1
            da, db = drops({y: a[y] for y in common}), drops({y: b[y] for y in common})
            if da == db:
                same += 1
            else:
                differ.append((cvm, sorted(da), sorted(db), bool(ys and any(v[6] and v[7] for v in ys.values()))))
    out(f"Dividendo por ação (2020+): {comparable} empresas comparáveis; mesmas quedas nos dois métodos em {same}; diferem em {len(differ)}")
    both = sum(1 for d in differ if d[3])
    out(f"   das que diferem, {both} têm ON e PN (onde a aproximação payout x LPA é esperada falhar)")
    for cvm, da, db, two in differ[:12]:
        out(f"   {names[cvm][:36]:36} payout×LPA quedas {da} | total/ações quedas {db} | ON+PN {two}")


if __name__ == "__main__":
    main()
