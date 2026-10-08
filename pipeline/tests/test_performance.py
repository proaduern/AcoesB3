"""Desempenho e critério de morte: números conferidos à mão."""

from datetime import date, timedelta

import pytest

from acoesb3 import performance as pf
from acoesb3.performance import LevelSeries


def daily(start, values):
    return [(start + timedelta(days=i), v) for i, v in enumerate(values)]


def test_level_series_lookup():
    s = LevelSeries(daily(date(2020, 1, 1), [1.0, 2.0, 3.0]))
    assert s.at(date(2020, 1, 2)) == 2.0
    assert s.at(date(2020, 1, 10)) == 3.0
    assert s.at(date(2019, 12, 31)) is None
    assert s.between(date(2020, 1, 2), date(2020, 1, 3)) == [
        (date(2020, 1, 2), 2.0),
        (date(2020, 1, 3), 3.0),
    ]


def test_max_drawdown_peak_to_trough():
    pts = daily(date(2020, 1, 1), [100, 120, 90, 110, 60, 130])
    dd = pf.max_drawdown(pts)
    assert dd.depth == pytest.approx(0.5)  # 120 -> 60
    assert (dd.peak, dd.trough) == (date(2020, 1, 2), date(2020, 1, 5))


def test_max_drawdown_of_rising_series_is_zero():
    assert pf.max_drawdown(daily(date(2020, 1, 1), [1, 2, 3])).depth == 0


def test_period_stats_total_return_uses_level_before_start():
    s = LevelSeries(daily(date(2020, 1, 1), [100, 110, 121]))
    st = pf.period_stats(s, date(2020, 1, 2), date(2020, 1, 3))
    assert st["total_return"] == pytest.approx(0.21)  # 121 / 100 - 1: a alta do 1º dia entra
    assert st["from"] == "2020-01-01"


def test_period_stats_when_series_starts_inside_period():
    s = LevelSeries(daily(date(2020, 1, 5), [1.0, 1.5]))
    st = pf.period_stats(s, date(2020, 1, 1), date(2020, 1, 31))
    assert st["total_return"] == pytest.approx(0.5)
    assert st["from"] == "2020-01-05"


def test_period_stats_cagr_over_two_years():
    s = LevelSeries([(date(2020, 1, 1), 100.0), (date(2022, 1, 1), 121.0)])
    st = pf.period_stats(s, date(2020, 1, 2), date(2022, 1, 1))
    assert st["cagr"] == pytest.approx(0.10, abs=2e-3)


def test_period_stats_none_when_no_data():
    assert pf.period_stats(LevelSeries([]), date(2020, 1, 1), date(2020, 2, 1)) is None
    s = LevelSeries(daily(date(2021, 1, 1), [1, 2]))
    assert pf.period_stats(s, date(2020, 1, 1), date(2020, 2, 1)) is None


def test_month_starts_and_ends():
    days = [date(2024, 1, 30), date(2024, 1, 31), date(2024, 2, 1), date(2024, 2, 2)]
    assert pf.month_starts(days) == [date(2024, 1, 30), date(2024, 2, 1)]
    assert pf.month_ends(days) == [date(2024, 1, 31), date(2024, 2, 2)]


def test_add_years_leap_day():
    assert pf.add_years(date(2020, 2, 29), 1) == date(2021, 2, 28)


def monthly_series(start_year, years, growth):
    pts, level = [], 100.0
    for i in range(years * 12 + 1):
        y, m = start_year + i // 12, i % 12 + 1
        pts.append((date(y, m, 1), level))
        level *= 1 + growth
    return LevelSeries(pts)


def test_rolling_windows_counts_and_loss_flag():
    strat = monthly_series(2012, 8, 0.005)
    bench = monthly_series(2012, 8, 0.006)  # a referência sempre rende mais
    starts = [d for d, _ in zip(strat.dates, strat.values, strict=True)]
    w = pf.rolling_windows(strat, bench, starts, 5, None, date(2020, 1, 1))
    # inícios de 2012-01 a 2015-01, com fim até 2020-01
    assert len(w) == 37
    assert all(x.lost for x in w)
    assert w[0].end == date(2017, 1, 1)


def test_rolling_windows_respect_end_bounds():
    strat = monthly_series(2012, 12, 0.005)
    bench = monthly_series(2012, 12, 0.004)
    starts = strat.dates
    fit = pf.rolling_windows(strat, bench, starts, 5, None, date(2020, 12, 31))
    val = pf.rolling_windows(strat, bench, starts, 5, date(2020, 12, 31), date(2023, 12, 31))
    assert all(w.end <= date(2020, 12, 31) for w in fit)
    assert all(date(2020, 12, 31) < w.end <= date(2023, 12, 31) for w in val)
    assert not any(w.lost for w in fit + val)


def test_death_check_lost_share_rule():
    from acoesb3.performance import Window

    ws = [Window(date(2012, 1, 1), date(2017, 1, 1), 0.1, 0.2, True)] * 6 + [
        Window(date(2012, 2, 1), date(2017, 2, 1), 0.3, 0.2, False)
    ] * 4
    r = pf.death_check(ws, 0.20, 0.15, 0.5, 0.10)
    assert r["lost_share"] == pytest.approx(0.6)
    assert r["windows_rule_triggered"] is True  # 60% > 50%
    assert r["drawdown_rule_triggered"] is False  # 5 p.p. pior, abaixo de 10
    assert r["triggered"] is True


def test_death_check_exactly_half_does_not_trigger():
    from acoesb3.performance import Window

    ws = [Window(date(2012, 1, 1), date(2017, 1, 1), 0.1, 0.2, True)] * 5 + [
        Window(date(2012, 2, 1), date(2017, 2, 1), 0.3, 0.2, False)
    ] * 5
    assert pf.death_check(ws, None, None, 0.5, 0.10)["windows_rule_triggered"] is False


def test_death_check_drawdown_rule():
    r = pf.death_check([], 0.40, 0.25, 0.5, 0.10)
    assert r["windows_rule_triggered"] is None  # sem janelas
    assert r["extra_drawdown"] == pytest.approx(0.15)
    assert r["drawdown_rule_triggered"] is True
    assert r["triggered"] is True


def test_death_check_unavailable_without_data():
    r = pf.death_check([], None, None, 0.5, 0.10)
    assert r["triggered"] is None
