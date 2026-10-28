"""Weekly scorecard: how well did the predictions for a sale do, once its post-sale is in?

The model is trained only on sales before the one being scored, exactly as it
would have been when the shortlist was made, so the numbers are a fair test.
"""
import pandas as pd

from . import store
from .predict import Model
from .presale_report import flag_history
from .shortlist import build_shortlist, training_outcomes


def _errors(pred: pd.Series, actual: pd.Series) -> pd.Series:
    return (pred - actual).abs() / actual


def scorecard(con, sale_date, criteria: dict) -> dict:
    sale_date = pd.Timestamp(sale_date)
    o = training_outcomes(con)
    o["sale_date"] = pd.to_datetime(o["sale_date"])
    train, test = o[o["sale_date"] < sale_date], o[o["sale_date"] == sale_date]
    if train.empty or test.empty:
        raise ValueError("Need an earlier matched sale to learn from and this sale's post-sale.")
    model = Model().fit(train)
    p = model.predict(test)
    s = p[p["sold"] & p["mmr"].gt(0)]
    b = criteria["buy"]
    box = (s["year"] >= b["oldest_year"]) & (s["odometer"] <= b["max_miles"]) & s["cr"].ge(b["min_cr"]) \
        & s["pred_hammer"].between(b["min_price"], b["max_price"])
    em, eb = _errors(s["pred_hammer"], s["price"]), _errors(s["mmr"], s["price"])

    def row(label, mask):
        return {"group": label, "cars": int(mask.sum()),
                "model_median_error": round(em[mask].median(), 3), "mmr_median_error": round(eb[mask].median(), 3),
                "model_within_10pct": round((em[mask] <= 0.10).mean(), 2),
                "mmr_within_10pct": round((eb[mask] <= 0.10).mean(), 2)}

    accuracy = pd.DataFrame([row("All sold cars", pd.Series(True, index=s.index)), row("My buy box", box)])
    inside = ((s["price"] >= s["pred_low"]) & (s["price"] <= s["pred_high"])).mean()

    # which candidate factors would have helped this week?
    trials = []
    for f in [None, *Model.CANDIDATE_FEATURES]:
        feats = Model.PRICE_FEATURES + ([f] if f else [])
        m = Model()
        m.PRICE_FEATURES = feats
        e = _errors(m.fit(train).predict(s)["pred_hammer"], s["price"])
        trials.append({"model": " + ".join(feats), "median_error": round(e.median(), 3),
                       "buy_box_median_error": round(e[box].median(), 3)})

    sl = build_shortlist(flag_history(store.load_presales(con), sale_date), model, criteria)
    sl = sl.head(b["shortlist_size"]).merge(test[["vin", "sold", "price"]], on="vin", how="left")
    sl["actual_vs_pred"] = (sl["price"] / sl["pred_hammer"] - 1).round(3)
    sl["under_max_bid"] = sl["price"] <= sl["max_bid"]
    partial = not bool(test["sell_known"].all()) if "sell_known" in test else False

    per_car = s[["lane", "run", "year", "make", "model", "cr", "odometer", "mmr", "pred_hammer",
                 "pred_low", "pred_high", "price", "vin"]].assign(error=em.round(3), mmr_error=eb.round(3))
    return {"sale_date": sale_date, "trained_on": sorted(train["sale_date"].dt.date.unique()),
            "accuracy": accuracy, "inside_range": float(inside),
            "bias": float((s["price"] / s["pred_hammer"]).median()), "factor_trials": pd.DataFrame(trials),
            "shortlist": sl, "partial": partial, "per_car": per_car}
