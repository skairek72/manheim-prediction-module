"""Shortlist rules and max-bid math on made-up cars."""
import pandas as pd

from manheim_pm.predict import Model, backtest
from manheim_pm.shortlist import build_shortlist, estimate_recon, load_criteria

CRIT = load_criteria("criteria.toml")


def history(n=200):
    rows = []
    for i in range(n):
        cr = [2.5, 3.5, 4.5, None][i % 4]
        mmr = 4000 + 100 * (i % 50)
        sold = i % 5 != 0
        ratio = {2.5: 0.85, 3.5: 0.95, 4.5: 1.0, None: 0.9}[cr]
        rows.append({"lane": 1 + i % 3, "year": 2019, "make": "FORD", "model": "ESCAPE", "cr": cr,
                     "mmr": mmr, "odometer": 80000, "sold": sold, "price": mmr * ratio if sold else None,
                     "sale_date": "2026-10-20", "engine": "4C/A", "vin": f"V{i}"})
    return pd.DataFrame(rows)


def test_model_learns_condition_and_beats_plain_mmr():
    h = history()
    m = Model().fit(h)
    assert m.ratio_adj["cr_band"]["4.0+"] > m.ratio_adj["cr_band"]["2.0-2.9"]
    bt = backtest(h)
    assert bt["model_median_error"] < bt["mmr_median_error"]


def test_recon_by_condition():
    rc = CRIT["recon"]
    assert list(estimate_recon(pd.Series([4.7, 4.0, 3.6, 3.0, 2.0, None]), rc)) == [300, 500, 900, 1300, 2000, 2000]


def test_rules_and_max_bid():
    m = Model().fit(history())
    pre = pd.DataFrame([
        {"lane": 1, "run": 1, "year": 2020, "make": "FORD", "model": "ESCAPE", "cr": 4.0, "mmr": 8000,
         "odometer": 60000, "engine": "4C/A", "vin": "OK", "not_at_auction": False, "ev_battery_pct": None},
        {"lane": 1, "run": 2, "year": 2016, "make": "FORD", "model": "ESCAPE", "cr": 4.0, "mmr": 8000,
         "odometer": 60000, "engine": "4C/A", "vin": "OLD", "not_at_auction": False, "ev_battery_pct": None},
        {"lane": 1, "run": 3, "year": 2020, "make": "FORD", "model": "ESCAPE", "cr": 2.9, "mmr": 8000,
         "odometer": 60000, "engine": "4C/A", "vin": "ROUGH", "not_at_auction": False, "ev_battery_pct": None},
        {"lane": 1, "run": 4, "year": 2020, "make": "FORD", "model": "ESCAPE", "cr": None, "mmr": 8000,
         "odometer": 60000, "engine": "4C/A", "vin": "NOCR", "not_at_auction": False, "ev_battery_pct": None},
        {"lane": 1, "run": 5, "year": 2020, "make": "FORD", "model": "ESCAPE", "cr": 4.0, "mmr": 8000,
         "odometer": 130000, "engine": "4C/A", "vin": "MILES", "not_at_auction": False, "ev_battery_pct": None},
    ])
    sl = build_shortlist(pre, m, CRIT)
    assert list(sl["vin"]) == ["OK"]
    r = sl.iloc[0]
    c = CRIT["costs"]
    resale = 8000 * CRIT["resale"]["markup"] + CRIT["resale"]["add"]
    assert r["max_bid"] == round(resale - c["buyer_fee"] - c["transport"] - c["partner_fee"] - 500 - c["min_profit"], -1)
    assert r["max_bid_worst_recon"] < r["max_bid"]
