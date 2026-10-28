"""What's trending: recent window vs the window before it."""
import pandas as pd


def _mix_adjusted_price_change(recent: pd.DataFrame, prior: pd.DataFrame, by: str) -> pd.Series:
    """Price change comparing like with like (same model year), weighted by recent volume.

    A raw average jumps whenever newer or cleaner cars happen to run, which looks
    like a trend but isn't one.
    """
    r = recent[recent["sold"]].groupby([by, "year"])["sale_price"].agg(["mean", "size"])
    p = prior[prior["sold"]].groupby([by, "year"])["sale_price"].mean().rename("prior")
    j = r.join(p, how="inner")
    j["ratio"] = j["mean"] / j["prior"]
    return j.groupby(level=0).apply(lambda g: (g["ratio"] * g["size"]).sum() / g["size"].sum()) - 1


def trends(df: pd.DataFrame, by: str = "vehicle", window_days: int = 28, min_runs: int = 5) -> pd.DataFrame:
    """Compare the last `window_days` with the `window_days` before them.

    trend_score uses demand signals only: mix-adjusted price change and
    sell-through change. Lane volume is reported but not scored, because more
    units running can mean more supply rather than more demand. Rising volume
    with falling sell-through is flagged as a supply build-up.
    """
    end = df["sale_date"].max()
    recent_start = end - pd.Timedelta(days=window_days)
    prior_start = recent_start - pd.Timedelta(days=window_days)

    recent = df[df["sale_date"] > recent_start]
    prior = df[(df["sale_date"] > prior_start) & (df["sale_date"] <= recent_start)]

    def summarise(part: pd.DataFrame) -> pd.DataFrame:
        g = part.groupby(by)
        s = part[part["sold"]].groupby(by)
        return pd.DataFrame({
            "runs": g.size(),
            "sell_through": g["sold"].mean(),
            "avg_price": s["sale_price"].mean(),
        })

    r, p = summarise(recent), summarise(prior)
    out = r.join(p, lsuffix="_recent", rsuffix="_prior", how="inner")
    out = out[(out["runs_recent"] >= min_runs) & (out["runs_prior"] >= min_runs)].copy()

    out["volume_change"] = (out["runs_recent"] / out["runs_prior"] - 1).round(3)
    out["price_change"] = _mix_adjusted_price_change(recent, prior, by).reindex(out.index).round(3)
    out["sell_through_change"] = (out["sell_through_recent"] - out["sell_through_prior"]).round(3)
    out["trend_score"] = (0.5 * out["price_change"] + 0.5 * out["sell_through_change"]).round(3)
    out["direction"] = pd.cut(
        out["trend_score"], [-float("inf"), -0.03, 0.03, float("inf")],
        labels=["cooling", "flat", "heating up"],
    ).astype(str)
    glut = (out["volume_change"] > 0.15) & (out["sell_through_change"] < -0.05)
    out.loc[glut, "direction"] = "supply building"
    for col in ["avg_price_recent", "avg_price_prior"]:
        out[col] = out[col].round(0)
    return out.sort_values("trend_score", ascending=False)
