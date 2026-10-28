"""Shortlist: the cars on a pre-sale list worth bidding on, with a max bid for each.

max bid = estimated resale - auction fee - transport - partner fee - estimated recon - minimum profit

The predicted hammer says what the car will probably go for; if it is above
your max bid you will most likely be outbid, so those cars rank last.
"""
import tomllib
from pathlib import Path

import pandas as pd

from . import store
from .match import match_sale, sale_outcome
from .predict import Model
from .presale_report import flag_history

EV_ENGINES = ("E/", "H/")  # pre-sale engine codes for electric / hybrid


def load_criteria(path: str | Path = "criteria.toml") -> dict:
    with open(path, "rb") as f:
        return tomllib.load(f)


def training_outcomes(con) -> pd.DataFrame:
    """Every pre-sale car that has a matching post-sale, with sold / hammer price."""
    pre_hist, post = store.load_presales(con), store.load_postsales(con)
    if pre_hist.empty or post.empty:
        return pd.DataFrame()
    finals = store.final_lists(pre_hist)
    out = []
    for (name, date), sold in post.groupby(["auction", "sale_date"]):
        pre = finals[(finals["auction"] == name) & (finals["sale_date"] == date)]
        if len(pre):
            out.append(sale_outcome(pre, match_sale(sold, pre)))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame()


def estimate_recon(cr: pd.Series, rc: dict) -> pd.Series:
    steps = sorted(((float(k), v) for k, v in rc["by_cr"].items()), reverse=True)

    def one(x):
        if pd.isna(x):
            return rc["max"]
        for floor, cost in steps:
            if x >= floor:
                return cost
        return rc["max"]
    return cr.map(one).clip(rc["min"], rc["max"])


def build_shortlist(presale: pd.DataFrame, model: Model, c: dict) -> pd.DataFrame:
    b, costs, rc, rs = c["buy"], c["costs"], c["recon"], c["resale"]
    d = presale.copy()
    keep = (d["year"] >= b["oldest_year"]) & (d["odometer"] <= b["max_miles"]) & d["mmr"].notna()
    keep &= d["cr"].ge(b["min_cr"]) | (d["cr"].isna() & b["allow_no_cr"])
    if not b["allow_ev_hybrid"]:
        keep &= ~d["engine"].fillna("").str.startswith(EV_ENGINES)
    if b["avoid_makes"]:
        keep &= ~d["make"].isin([m.upper() for m in b["avoid_makes"]])
    if b["only_makes"]:
        keep &= d["make"].isin([m.upper() for m in b["only_makes"]])
    d = model.predict(d[keep])
    d = d[d["pred_hammer"].between(b["min_price"], b["max_price"])]

    fixed = costs["buyer_fee"] + costs["transport"] + costs["partner_fee"]
    d["est_recon"] = estimate_recon(d["cr"], rc)
    d["est_resale"] = (d["mmr"] * rs["markup"] + rs["add"]).round(-1)
    d["max_bid"] = (d["est_resale"] - fixed - d["est_recon"] - costs["min_profit"]).round(-1)
    d["max_bid_worst_recon"] = (d["est_resale"] - fixed - rc["max"] - costs["min_profit"]).round(-1)
    d["profit_if_bought_at_pred"] = (d["est_resale"] - d["pred_hammer"] - fixed - d["est_recon"]).round(-1)
    d["resale_needed_at_pred"] = (d["pred_hammer"] + fixed + d["est_recon"] + costs["min_profit"]).round(-1)
    d["winnable"] = d["pred_hammer"] <= d["max_bid"]

    notes = []
    for _, r in d.iterrows():
        n = ["check CR: " + ", ".join(c["pass"]["deal_breakers"])]
        if r.get("times_run", 1) > 1:
            n.append(f"run-back ({int(r['times_run'])}x)")
        if r.get("lane") == 98:
            n.append("lane 98: sells far under MMR, often announced problems - read announcements")
        if r.get("not_at_auction"):
            n.append("not on lot yet")
        if pd.notna(r.get("ev_battery_pct")):
            n.append(f"EV battery {int(r['ev_battery_pct'])}%")
        notes.append("; ".join(n))
    d["notes"] = notes

    d = d.sort_values(["winnable", "profit_if_bought_at_pred", "sell_chance"], ascending=[False, False, False])
    d.insert(0, "rank", range(1, len(d) + 1))
    return d


SHOW = ["rank", "lane", "run", "year", "make", "model", "cr", "odometer", "mmr", "pred_hammer",
        "pred_low", "pred_high", "sell_chance", "max_bid", "max_bid_worst_recon", "est_recon",
        "est_resale", "profit_if_bought_at_pred", "resale_needed_at_pred", "notes", "vin"]


def shortlist_for_sale(con, sale_date, criteria: dict) -> tuple[pd.DataFrame, Model, int]:
    train = training_outcomes(con)
    if train.empty:
        raise ValueError("No matched past sales yet: import a pre-sale and its post-sale folder first.")
    # learn only from sales before this one, so the shortlist is a fair test
    train = train[pd.to_datetime(train["sale_date"]) < pd.Timestamp(sale_date)]
    if train.empty:
        raise ValueError(f"No matched sales before {sale_date} to learn from.")
    model = Model().fit(train)
    flagged = flag_history(store.load_presales(con), sale_date)
    sl = build_shortlist(flagged, model, criteria)
    return sl, model, len(flagged)
