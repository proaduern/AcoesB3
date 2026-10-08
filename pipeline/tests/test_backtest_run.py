"""Backtest ponta a ponta no Postgres: ajuste, congelamento e validação única."""

from datetime import date, timedelta
from decimal import Decimal

import pytest
from test_compute import World, run, watched

from acoesb3 import backtest_run as br
from acoesb3 import compute

D = Decimal


def cfg_for(conn):
    cfg = compute.load_config(conn)
    cfg.update(
        {
            "backtest.start_date": "2024-09-01",
            "backtest.validation_start": "2025-09-01",
            "backtest.end_date": "2025-12-31",
            "backtest.window_years": 1,
            "ceiling.price_max_age_days": 10,
        }
    )
    return cfg


def add_benchmarks(conn):
    sf = conn.execute("SELECT id FROM source_file LIMIT 1").fetchone()[0]
    d = date(2024, 8, 1)
    level = {"ibov": 100.0, "idiv": 100.0}
    rows = []
    while d <= date(2025, 12, 31):
        if d.weekday() < 5:
            level["ibov"] *= 1.0004
            level["idiv"] *= 1.0003
            rows += [("ibov", d, level["ibov"], sf), ("idiv", d, level["idiv"], sf)]
            rows.append(("cdi", d, 0.04, sf))  # 0,04% ao dia
        d += timedelta(days=1)
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO benchmark_daily (code, ref_date, value, source_file_id)"
            " VALUES (%s, %s, %s, %s)",
            rows,
        )
    conn.commit()


def world(conn, price="0.5"):
    """Uma empresa na lista acompanhada, com preço abaixo do teto nos dias de 2024 e 2025."""
    World(conn).company(1, "ABCD")
    watched(conn)
    run(conn)
    conn.execute("UPDATE quote_daily SET close = %s WHERE trade_date >= '2024-08-01'", (price,))
    conn.commit()
    add_benchmarks(conn)


def test_ajuste_roda_so_ate_o_fim_do_ajuste_e_grava_resultado(conn):
    world(conn)
    cfg = cfg_for(conn)
    out = br.run_fit(conn, cfg, only=["aporte_1000"])
    assert set(out) == {"aporte_1000"}
    kind, end, metrics, warnings = conn.execute(
        "SELECT kind, end_date, metrics, warnings FROM backtest_run"
    ).fetchone()
    assert kind == "fit" and end <= date(2025, 8, 31)
    assert "validation" not in metrics  # a validação não é calculada no ajuste
    assert metrics["fit"]["end"] == "2025-08-31"
    assert any("sobrevivência" in w for w in warnings)
    last = conn.execute("SELECT max(ref_date) FROM backtest_series").fetchone()[0]
    assert last <= date(2025, 8, 31)
    names = {r[0] for r in conn.execute("SELECT DISTINCT series FROM backtest_series")}
    assert names == {"strategy_net", "strategy_gross", "ibov", "idiv", "cdi"}
    # compra de papel barato: há ordens e posição final
    assert metrics["flows"]["net_trades"] >= 1
    assert metrics["flows"]["net_first_buy"] is not None
    assert conn.execute("SELECT count(*) FROM backtest_trade").fetchone()[0] >= 1


def test_ajuste_repetido_substitui_a_execucao_anterior(conn):
    world(conn)
    cfg = cfg_for(conn)
    br.run_fit(conn, cfg, only=["aporte_1000"])
    br.run_fit(conn, cfg, only=["aporte_1000"])
    assert conn.execute("SELECT count(*) FROM backtest_run").fetchone()[0] == 1


def test_cenarios_do_usuario_estao_na_configuracao(conn):
    cfg = compute.load_config(conn)
    names = {s.name: s.contribution for s in br.scenarios_from_config(cfg)}
    assert [names[n] for n in ("aporte_1000", "aporte_1250", "aporte_1500")] == [
        D(1000), D(1250), D(1500)
    ]  # fmt: skip
    assert "dy_5" in names and "k_estrito" in names


def test_aporte_maior_investe_mais(conn):
    world(conn)
    cfg = cfg_for(conn)
    br.run_fit(conn, cfg, only=["aporte_1000", "aporte_1500"])
    inv = dict(
        conn.execute(
            "SELECT scenario, (metrics->'flows'->>'net_invested')::numeric FROM backtest_run"
        ).fetchall()
    )
    assert inv["aporte_1500"] == inv["aporte_1000"] * D("1.5")


def test_congelar_exige_ajuste_com_os_mesmos_parametros(conn):
    world(conn)
    cfg = cfg_for(conn)
    with pytest.raises(RuntimeError, match="ajuste"):
        br.freeze(conn, cfg, "aporte_1000", None)
    br.run_fit(conn, cfg, only=["aporte_1000"])
    assert br.freeze(conn, cfg, "aporte_1000", "melhor no ajuste")["scenario"] == "aporte_1000"
    with pytest.raises(RuntimeError, match="desconhecido"):
        br.freeze(conn, cfg, "nao_existe", None)


def test_validacao_so_uma_vez_e_so_com_parametros_congelados(conn):
    world(conn)
    cfg = cfg_for(conn)
    with pytest.raises(RuntimeError, match="congelado"):
        br.validate(conn, cfg)
    br.run_fit(conn, cfg, only=["aporte_1000"])
    br.freeze(conn, cfg, "aporte_1000", None)

    changed = {**cfg, "backtest.sell_above_ratio": "1.5"}  # mexer nos parâmetros depois de congelar
    with pytest.raises(RuntimeError, match="mudaram"):
        br.validate(conn, changed)

    out = br.validate(conn, cfg)
    assert out["scenario"] == "aporte_1000"
    kind, metrics = conn.execute(
        "SELECT kind, metrics FROM backtest_run WHERE kind = 'validation'"
    ).fetchone()
    assert kind == "validation" and metrics["validation"]["start"] == "2025-09-01"
    assert metrics["validation"]["end"] == "2025-12-31"
    # segundo disparo é recusado, e não dá para congelar de novo
    with pytest.raises(RuntimeError, match="uma vez"):
        br.validate(conn, cfg)
    with pytest.raises(RuntimeError, match="já foi medida"):
        br.freeze(conn, cfg, "aporte_1000", None)


def test_indice_unico_impede_duas_validacoes_mesmo_por_sql(conn):
    import psycopg

    world(conn)
    cfg = cfg_for(conn)
    br.run_fit(conn, cfg, only=["aporte_1000"])
    br.freeze(conn, cfg, "aporte_1000", None)
    br.validate(conn, cfg)
    with pytest.raises(psycopg.errors.UniqueViolation):
        conn.execute(
            "INSERT INTO backtest_run (kind, scenario, cfg_hash, config, start_date, end_date,"
            " universe, metrics) VALUES ('validation', 'x', 'h', '{}', now(), now(), '{}', '{}')"
        )
    conn.rollback()


def test_ajuste_da_validacao_reproduz_o_ajuste_original(conn):
    world(conn)
    cfg = cfg_for(conn)
    br.run_fit(conn, cfg, only=["aporte_1000"])
    fit = conn.execute("SELECT metrics FROM backtest_run WHERE kind = 'fit'").fetchone()[0]
    br.freeze(conn, cfg, "aporte_1000", None)
    br.validate(conn, cfg)
    val = conn.execute("SELECT metrics FROM backtest_run WHERE kind = 'validation'").fetchone()[0]
    a, b = fit["fit"]["series"]["strategy_net"], val["fit"]["series"]["strategy_net"]
    assert a["total_return"] == pytest.approx(b["total_return"])
    assert a["max_drawdown"] == pytest.approx(b["max_drawdown"])


def test_relatorio_lista_as_execucoes(conn):
    world(conn)
    cfg = cfg_for(conn)
    br.run_fit(conn, cfg, only=["aporte_1000"])
    rows = br.report(conn)
    assert [(r["kind"], r["scenario"]) for r in rows] == [("fit", "aporte_1000")]


def test_hash_da_configuracao_muda_com_os_parametros(conn):
    cfg = compute.load_config(conn)
    sc = br.scenarios_from_config(cfg)[0]
    h1 = br.config_hash(br.config_snapshot(cfg, sc))
    h2 = br.config_hash(br.config_snapshot({**cfg, "backtest.cgt_rate": "0.2"}, sc))
    other = br.scenarios_from_config(cfg)[1]
    assert h1 != h2 and h1 != br.config_hash(br.config_snapshot(cfg, other))
    # a lista de cenários em si não entra: acrescentar cenário não invalida o congelamento
    h3 = br.config_hash(br.config_snapshot({**cfg, "backtest.scenarios": []}, sc))
    assert h1 == h3
