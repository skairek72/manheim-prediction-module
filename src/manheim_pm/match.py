"""Link post-sale results (no VIN, no lane) back to the pre-sale list.

The post-sale shows the exact odometer, so make + year + odometer almost always
points to exactly one pre-sale car. Model names differ ("FUSION FWD 4C" vs
"FUSION SE"), so they are only used to break ties.

match_quality:
  exact      one pre-sale car with the same make, year and odometer
  close      odometer within CLOSE_MILES, only one candidate, model words agree
  ambiguous  several candidates (e.g. odometer 1 or 0); not used for learning
  none       not on the pre-sale list (added on sale day, or another lane/channel)
"""
import pandas as pd

CLOSE_MILES = 50
PRESALE_FIELDS = ["vin", "lane", "run", "model", "cr", "mmr", "ev_battery_pct", "color", "not_at_auction"]


def _words(s) -> set[str]:
    return set(str(s).upper().replace("-", " ").split()) if isinstance(s, str) else set()


def _model_agrees(post_model: str, pre_model: str) -> bool:
    # "T250 CARGO V6" vs "TRANSIT 250 BASE" share nothing, so also compare digits-only tokens
    a, b = _words(post_model), _words(pre_model)
    if a & b:
        return True
    digits = lambda ws: {"".join(ch for ch in w if ch.isdigit()) for w in ws} - {""}
    return bool(digits(a) & digits(b))


def _row(car: pd.Series, quality: str, pick, pre: pd.DataFrame, used: set) -> dict:
    row = car.to_dict()
    row["match_quality"] = quality
    for f in PRESALE_FIELDS:
        row[f"pre_{f}"] = pre.at[pick, f] if pick is not None else None
    if pick is not None:
        used.add(pick)
    return row


def match_sale(post: pd.DataFrame, pre: pd.DataFrame) -> pd.DataFrame:
    """post: sold cars of one sale. pre: the final pre-sale list of the same sale.

    Returns post with pre-sale fields (prefixed pre_) and match_quality added.
    Each pre-sale car is used at most once.
    """
    pre = pre.reset_index(drop=True)
    used: set[int] = set()
    out = []
    by_key = pre.groupby(["make", "year"]).groups

    for _, car in post.iterrows():
        idx = [i for i in by_key.get((car["make"], car["year"]), []) if i not in used]
        cands = pre.loc[idx]
        agrees = lambda df: df[[_model_agrees(car["model"], m) for m in df["model"]]]
        quality, pick = "none", None
        odo = car["odometer"]
        if pd.isna(odo) or odo <= 10:
            # no real mileage (n/a, 0, 1): rely on make + year + model words, and only if unique
            pool = agrees(cands if pd.isna(odo) else cands[cands["odometer"].fillna(0) <= 10])
            if len(pool) == 1:
                quality, pick = "close", pool.index[0]
            elif len(pool) > 1:
                quality = "ambiguous"
            out.append(_row(car, quality, pick, pre, used))
            continue
        exact = cands[cands["odometer"] == odo]
        if len(exact) == 1:
            quality, pick = "exact", exact.index[0]
        elif len(exact) > 1:
            agree = agrees(exact)
            quality, pick = ("exact", agree.index[0]) if len(agree) == 1 else ("ambiguous", None)
        else:
            near = cands[(cands["odometer"] - car["odometer"]).abs() <= CLOSE_MILES]
            near = near[[_model_agrees(car["model"], m) for m in near["model"]]]
            if len(near) == 1:
                quality, pick = "close", near.index[0]
            elif len(near) > 1:
                quality = "ambiguous"

        out.append(_row(car, quality, pick, pre, used))

    res = pd.DataFrame(out)
    res["price_to_mmr"] = (res["price"] / pd.to_numeric(res["pre_mmr"])).round(3)
    return res


def sale_outcome(pre: pd.DataFrame, matched: pd.DataFrame) -> pd.DataFrame:
    """Every pre-sale car with sold / not-sold and its hammer price.

    Only meaningful when the post-sale folder holds the whole sale; a partial
    download makes unsold look higher than it is.
    """
    sold = matched[matched["match_quality"].isin(["exact", "close"])]
    sold = sold.set_index("pre_vin")[["price", "match_quality"]]
    out = pre.join(sold, on="vin")
    out["sold"] = out["price"].notna()
    return out
