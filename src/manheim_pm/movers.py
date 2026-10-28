"""What's moving: sell-through, volume and price strength by vehicle."""
import pandas as pd


def movers(df: pd.DataFrame, by: str = "vehicle", min_runs: int = 10) -> pd.DataFrame:
    """Rank vehicles by how readily they sell.

    - sell_through: share of runs that sold
    - price_to_mmr: average sale price / MMR for sold units (>1.0 = selling above book)
    - move_score: sell_through weighted by price strength and volume
    """
    sold = df[df["sold"]]
    g = df.groupby(by)
    out = pd.DataFrame({
        "runs": g.size(),
        "sold": g["sold"].sum(),
        "sell_through": g["sold"].mean(),
        "avg_mileage": g["mileage"].mean().round(0),
    })
    sg = sold.groupby(by)
    out["avg_sale_price"] = sg["sale_price"].mean().round(0)
    out["price_to_mmr"] = (sg["sale_price"].sum() / sg["mmr"].sum()).round(3)
    out = out[out["runs"] >= min_runs].copy()

    volume_weight = (out["runs"] / out["runs"].max()) ** 0.5
    out["move_score"] = (out["sell_through"] * out["price_to_mmr"].fillna(0) * volume_weight).round(3)
    out["sell_through"] = out["sell_through"].round(3)
    return out.sort_values("move_score", ascending=False)
