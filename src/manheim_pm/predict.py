"""v1 prediction: hammer price and chance of selling, learned from matched past sales.

Hammer is predicted as MMR x a ratio. The ratio starts at the overall median
(Skyline ~0.94) and is adjusted for condition grade, lane and price band, each
adjustment shrunk toward the overall median when it rests on few cars, so a
lane with 8 sales cannot swing the prediction much.

This is deliberately simple: with a few weeks of data, a heavier model would
just memorise noise. Replace it once there are 8-12 weeks of matched sales.
"""
import numpy as np
import pandas as pd

SHRINK = 25  # cars needed before a group's own median counts as much as the overall median


def add_features(df: pd.DataFrame) -> pd.DataFrame:
    d = df.copy()
    d["cr_band"] = pd.cut(d["cr"], [0, 2, 3, 4, 5.1], labels=["<2.0", "2.0-2.9", "3.0-3.9", "4.0+"],
                          right=False).astype(str).replace("nan", "no CR")
    d["mmr_band"] = pd.cut(d["mmr"], [0, 3000, 7500, 15000, 30000, float("inf")],
                           labels=["<3k", "3-7.5k", "7.5-15k", "15-30k", "30k+"]).astype(str)
    d["miles_band"] = pd.cut(d["odometer"], [-1, 30000, 60000, 90000, 120000, 150000, float("inf")],
                             labels=["<30k", "30-60k", "60-90k", "90-120k", "120-150k", "150k+"]).astype(str)
    d["lane_s"] = d["lane"].astype("Int64").astype(str)
    if "times_run" in d:
        tr = pd.to_numeric(d["times_run"], errors="coerce")
        d["run_back"] = tr.map(lambda t: "unknown" if pd.isna(t) else "first time" if t <= 1 else "run-back")
    else:
        d["run_back"] = "unknown"
    return d


class Model:
    # Condition only for now: tested on the 10/27 sale (trained on 10/20), adding lane, price band
    # or mileage made predictions worse. Re-test with the weekly scorecard as weeks accumulate.
    # Run-back added 10/28: on 10/27 run-backs sold at 81% of MMR vs 98% for first-time cars,
    # and sold half as often. First scored on the 11/03 sale.
    PRICE_FEATURES = ["cr_band", "run_back"]
    CANDIDATE_FEATURES = ["lane_s", "mmr_band", "miles_band"]
    SELL_FEATURES = ["cr_band", "lane_s", "mmr_band", "run_back"]

    def fit(self, outcome: pd.DataFrame) -> "Model":
        """outcome: pre-sale rows with sold (bool) and price (hammer, NaN if unsold)."""
        d = add_features(outcome)
        sold = d[d["sold"] & d["mmr"].gt(0) & d["price"].gt(0)].copy()
        sold["ratio"] = (sold["price"] / sold["mmr"]).clip(0.1, 2.0)
        self.n_sold, self.n_listed = len(sold), len(d)
        self.base_ratio = float(sold["ratio"].median())
        known = d[d["sell_known"].fillna(True).astype(bool)] if "sell_known" in d else d
        self.n_listed = len(known)
        self.base_sell = float(known["sold"].mean())
        # Fit each factor on what the others leave unexplained (backfitting), so overlapping
        # factors (rough cars cluster in lane 98) are not counted twice.
        self.ratio_adj = {f: {} for f in self.PRICE_FEATURES}
        for _ in range(5):
            for f in self.PRICE_FEATURES:
                others = self._ratio(sold, skip=f)
                resid = sold.assign(r=sold["ratio"] / others)
                self.ratio_adj[f] = self._shrunk(resid, f, "r", 1.0, np.median)
        self.sell_adj = {f: self._shrunk(known.assign(s=known["sold"].astype(float)), f, "s", self.base_sell, np.mean)
                         for f in self.SELL_FEATURES}
        # spread of actual vs predicted, for the likely range
        resid = sold["ratio"] / self._ratio(sold)
        self.lo, self.hi = float(resid.quantile(0.25)), float(resid.quantile(0.75))
        return self

    @staticmethod
    def _shrunk(d, feature, target, base, agg):
        g = d.groupby(feature)[target].agg([agg, "size"])
        g.columns = ["value", "n"]
        return ((g["value"] * g["n"] + base * SHRINK) / (g["n"] + SHRINK) / base).astype(float).to_dict()

    def _ratio(self, d: pd.DataFrame, skip: str | None = None) -> pd.Series:
        r = pd.Series(self.base_ratio, index=d.index)
        for f, adj in self.ratio_adj.items():
            if f != skip:
                r *= d[f].map(adj).fillna(1.0)
        return r.clip(0.1, 2.0)

    def predict(self, presale: pd.DataFrame) -> pd.DataFrame:
        d = add_features(presale)
        ratio = self._ratio(d)
        sell = pd.Series(self.base_sell, index=d.index)
        for f, adj in self.sell_adj.items():
            sell *= d[f].map(adj).fillna(1.0)
        out = presale.copy()
        out["pred_ratio"] = ratio.round(3)
        out["pred_hammer"] = (d["mmr"] * ratio).round(-1)
        out["pred_low"] = (d["mmr"] * ratio * self.lo).round(-1)
        out["pred_high"] = (d["mmr"] * ratio * self.hi).round(-1)
        out["sell_chance"] = sell.clip(0.02, 0.98).round(2)
        return out


def backtest(outcome: pd.DataFrame, folds: int = 5, seed: int = 7) -> dict:
    """Hide a fifth of the sold cars, predict them from the rest, repeat. Compare with plain MMR."""
    d = outcome[outcome["sold"] & outcome["mmr"].gt(0)].copy()
    rng = np.random.default_rng(seed)
    d["fold"] = rng.integers(0, folds, len(d))
    errs_model, errs_mmr = [], []
    for k in range(folds):
        train = pd.concat([outcome[~outcome.index.isin(d.index)], d[d["fold"] != k]])
        test = d[d["fold"] == k]
        p = Model().fit(train).predict(test)
        errs_model.append((p["pred_hammer"] - test["price"]).abs() / test["price"])
        errs_mmr.append((test["mmr"] - test["price"]).abs() / test["price"])
    em, eb = pd.concat(errs_model), pd.concat(errs_mmr)
    return {
        "cars": len(d),
        "model_median_error": float(em.median()), "mmr_median_error": float(eb.median()),
        "model_within_10pct": float((em <= 0.10).mean()), "mmr_within_10pct": float((eb <= 0.10).mean()),
    }
