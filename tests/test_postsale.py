"""Post-sale column placement, repeat-download removal and pre-sale matching (made-up cars)."""
import pandas as pd

from manheim_pm.match import match_sale
from manheim_pm.postsale import _assign, _boundaries, drop_repeat_downloads

# Heading x-positions as printed by the Manheim post-sale portal
HEADER = [{"text": t, "x0": x} for t, x in [
    ("Year", 66), ("Make", 95), ("Model", 172), ("Subseries", 275), ("Color", 350), ("Drs", 399),
    ("Cyl", 428), ("Fuel", 452), ("Trans", 490), ("4x4", 531), ("Radio", 559), ("Int", 608),
    ("Odometer", 630), ("Price", 712)]]


def words(*pairs):
    return [{"text": t, "x0": x} for t, x in pairs]


def test_columns_that_run_together_are_split_by_position():
    row = words(("2023", 63), ("LAND", 95), ("ROVER", 126), ("RANGE", 172), ("R", 213), ("SPT", 223),
                ("6C", 246), ("SE", 275), ("DYNAMIC", 292), ("GRAY", 350), ("4", 403), ("G", 452),
                ("A", 497), ("AWD", 526), ("AM/FM", 559), ("43,910", 651), ("$51,000", 694))
    c = _assign(row, _boundaries(HEADER), 630)
    assert c["Make"] == "LAND ROVER" and c["Model"] == "RANGE R SPT 6C"
    assert c["Subseries"] == "SE DYNAMIC" and c["Color"] == "GRAY"
    assert c["4x4"] == "AWD" and c["Odometer"] == "43,910" and c["Price"] == "$51,000"


def test_blank_columns_and_na_mileage():
    row = words(("2015", 63), ("FORD", 95), ("T250", 172), ("CARGO", 200), ("V6", 240), ("WHITE", 350),
                ("2", 403), ("A", 497), ("RWD", 526), ("CD", 559), ("n/a", 655), ("$5,000", 700))
    c = _assign(row, _boundaries(HEADER), 630)
    assert c["Subseries"] is None and c["Fuel"] is None
    assert c["Odometer"] == "n/a" and c["Price"] == "$5,000"


def car(**kw):
    base = {"auction_code": "SKYA", "sale_date": "2026-10-20", "year": 2017, "make": "FORD",
            "model": "FUSION FWD 4C", "subseries": "SE", "color": "GRAY", "odometer": 75030,
            "price": 6200, "source_file": "a.pdf"}
    return {**base, **kw}


def test_same_page_downloaded_twice_counts_once():
    cars = pd.DataFrame([car(), car(odometer=1, price=500), car(source_file="b.pdf"),
                         car(odometer=1, price=500, source_file="b.pdf")])
    assert len(drop_repeat_downloads(cars)) == 2


def test_two_identical_cars_in_one_file_are_both_kept():
    cars = pd.DataFrame([car(odometer=1, price=500), car(odometer=1, price=500)])
    assert len(drop_repeat_downloads(cars)) == 2


def test_match_by_make_year_odometer():
    pre = pd.DataFrame([
        {"vin": "V1", "lane": 9, "run": 31, "make": "FORD", "year": 2017, "model": "FUSION SE",
         "odometer": 75030, "cr": 3.6, "mmr": 6625, "ev_battery_pct": None, "color": "GRAY", "not_at_auction": False},
        {"vin": "V2", "lane": 1, "run": 71, "make": "FORD", "year": 2017, "model": "TRANSIT 250 BASE",
         "odometer": 127732, "cr": 3.8, "mmr": 11700, "ev_battery_pct": None, "color": "WHITE", "not_at_auction": False},
        {"vin": "V3", "lane": 2, "run": 40, "make": "BUICK", "year": 2004, "model": "LESABRE CUSTOM",
         "odometer": 0, "cr": None, "mmr": 1000, "ev_battery_pct": None, "color": "SILVER", "not_at_auction": False},
    ])
    post = pd.DataFrame([
        car(),                                                               # exact
        car(model="T250 CARGO V6", subseries=None, odometer=127740, price=15800),  # close: 8 mi off, "250" agrees
        car(make="BUICK", year=2004, model="LESABRE", odometer=None, price=500),   # n/a mileage, unique model
        car(make="BMW", year=2016, model="320I XDRIVE", odometer=108139),          # not on the pre-sale
    ])
    m = match_sale(post, pre)
    assert list(m["match_quality"]) == ["exact", "close", "close", "none"]
    assert list(m["pre_vin"][:3]) == ["V1", "V2", "V3"]
    assert m["price_to_mmr"].iloc[0] == round(6200 / 6625, 3)
