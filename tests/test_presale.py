"""Pre-sale reader and run-back tracking, on made-up lines in the Manheim layout."""
import pandas as pd

from manheim_pm import store
from manheim_pm.presale import parse_lines
from manheim_pm.presale_report import flag_history, previous_sale_outcome, snapshot_changes


def page(sale: str, printed: str, rows: list[str]) -> list[str]:
    return [
        f"{printed} Manheim - Pre-Sale Inventory",
        "Pre-Sale Inventory",
        "Manheim Test Auction Switch to Pre-Sale Detail View",
        f"{sale} - ({len([r for r in rows if r[:1].isdigit()])} Vehicles)",
        "Ln/Run Year Make/Model Cond|EVBH Eng /T MMR($) Fuel Top Odometer Color VIN",
        *rows,
        "* Asterisk indicates that the vehicle is currently not at the auction",
    ]


CAMRY = "3-12 2021 TOYOTA CAMRY SE CR 3.6 4C/A 18,500 G SM 41,000 WHITE 4T1AAAAAAAA000001"
WRAPPED = [
    "HONDA ODYSSEY W/TOURING & ENTERTAINMENT",
    "7-20 2019 CR 4.4 6C/A 23,000 G SM 64,124 RED 5FNAAAAAAAA000002",
    "PACKAGES",
]
NO_CR_NO_COLOR = "4-176 2012 ACURA MDX BASE 6C/A 3,125 G SM 176,619 2HNAAAAAAAA000003"
EV = "1-76 2022 TESLA MODEL 3 STANDARD RANGE CR 3.4 | EVBH 92% E/A 17,350 X SM 85,849 BLUE 5YJAAAAAAAA000004"
NOT_HERE = "7-66 2019 *BMW X5 XDRIVE40I 6CT/A 14,400 G 109,202 BLACK 5UXAAAAAAAA000005"
JEEP = "5-150 2022 JEEP WRANGLER SAHARA CR 3.9 4CT/A 23,400 G TR 30,100 GRAY 1C4AAAAAAAA000006"
NO_MMR = "9-126 2007 FORD F-350 / N/A HT 1 WHITE 3FRAAAAAAAA000007"
LAND_ROVER = "2-25 2023 LAND ROVER RANGE ROVER SV LWB CR 4.2 8CT/A 122,000 G PR 35,525 BLACK SALAAAAAAAA000008"


def test_reads_every_layout_variant():
    df, info = parse_lines(page("10/20/2026", "10/19/26, 9:55 AM",
                                [CAMRY, *WRAPPED, NO_CR_NO_COLOR, EV, NOT_HERE, JEEP, NO_MMR, LAND_ROVER]))
    assert info["problems"] == []
    assert info["listed"] == info["parsed"] == 8
    assert info["auction"] == "Manheim Test Auction"
    r = df.set_index("vin")

    camry = r.loc["4T1AAAAAAAA000001"]
    assert (camry.lane, camry.run, camry.year, camry.make, camry.model) == (3, 12, 2021, "TOYOTA", "CAMRY SE")
    assert (camry.cr, camry.mmr, camry.odometer, camry.color, camry.top) == (3.6, 18500, 41000, "WHITE", "SM")

    assert r.loc["5FNAAAAAAAA000002", "model"] == "ODYSSEY W/TOURING & ENTERTAINMENT PACKAGES"
    assert pd.isna(r.loc["2HNAAAAAAAA000003", "cr"]) and pd.isna(r.loc["2HNAAAAAAAA000003", "color"])
    assert r.loc["5YJAAAAAAAA000004", "ev_battery_pct"] == 92 and r.loc["5YJAAAAAAAA000004", "cr"] == 3.4
    assert r.loc["5UXAAAAAAAA000005", "not_at_auction"] and r.loc["5UXAAAAAAAA000005", "make"] == "BMW"
    assert r.loc["1C4AAAAAAAA000006", "top"] == "TR"
    assert pd.isna(r.loc["3FRAAAAAAAA000007", "mmr"])
    assert r.loc["SALAAAAAAAA000008", "make"] == "LAND ROVER"


def test_misread_line_is_reported_not_guessed():
    _, info = parse_lines(page("10/20/2026", "10/19/26, 9:55 AM", ["3-1 2020 GARBLED LINE"]))
    assert info["parsed"] == 0 and len(info["problems"]) == 1


def test_run_backs_and_snapshot_changes(tmp_path):
    con = store.connect(tmp_path / "t.db")
    week1_early, _ = parse_lines(page("10/20/2026", "10/16/26, 1:25 PM", [CAMRY, NO_CR_NO_COLOR]))
    week1_late, _ = parse_lines(page("10/20/2026", "10/19/26, 9:55 AM",
                                     [CAMRY.replace("18,500", "18,300"), EV, JEEP]))
    week2, _ = parse_lines(page("10/27/2026", "10/23/26, 10:18 PM",
                                [CAMRY.replace("3-12", "1-40").replace("18,500", "18,000"), LAND_ROVER]))
    for df in (week1_early, week1_late, week2):
        store.save_presale(con, df)
    store.save_presale(con, week2)  # importing twice must not duplicate
    hist = store.load_presales(con)
    assert len(hist) == 7

    flagged = flag_history(hist, "2026-10-27").set_index("vin")
    camry = flagged.loc["4T1AAAAAAAA000001"]
    assert camry.run_back and camry.times_run == 2 and camry.previous_lane == 3
    assert camry.mmr_change_since_first == round(18000 / 18300 - 1, 3)  # vs the last snapshot of the first sale
    assert not flagged.loc["SALAAAAAAAA000008", "run_back"]

    outcome = previous_sale_outcome(hist, "2026-10-27")
    assert (outcome["listed"], outcome["came_back"], outcome["did_not_come_back"]) == (3, 1, 2)

    ch = snapshot_changes(hist, "2026-10-20")
    assert set(ch["added"]["vin"]) == {"5YJAAAAAAAA000004", "1C4AAAAAAAA000006"}
    assert set(ch["withdrawn"]["vin"]) == {"2HNAAAAAAAA000003"}
    assert ch["mmr_moved"] == 1


def test_auction_name_on_its_own_line():
    lines = page("11/03/2026", "10/28/26, 2:45 PM", [CAMRY])
    lines[2] = "Switch to Pre-Sale Detail View"
    lines.insert(3, "Manheim Test Auction")
    _, info = parse_lines(lines)
    assert info["auction"] == "Manheim Test Auction"
