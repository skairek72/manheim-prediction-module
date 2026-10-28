"""Turn the numbers into short sales pitches.

Template-based so every claim traces back to a figure in the data. Swap in an
LLM later if you want more natural wording, but keep the numbers as the source.
"""
import pandas as pd


def _pct(x: float) -> str:
    return f"{x * 100:+.0f}%"


def pitch(vehicle: str, mv: pd.Series | None, tr: pd.Series | None) -> str:
    lines = [f"{vehicle}"]
    if tr is not None and tr["direction"] == "heating up":
        lines.append(
            f"  Demand is climbing over the last 4 weeks: price {_pct(tr['price_change'])}, "
            f"lane volume {_pct(tr['volume_change'])}, sell-through "
            f"{tr['sell_through_change'] * 100:+.0f} pts."
        )
    elif tr is not None and tr["direction"] == "cooling":
        lines.append(
            f"  Softening over the last 4 weeks: price {_pct(tr['price_change'])}, "
            f"sell-through {tr['sell_through_change'] * 100:+.0f} pts. Buy carefully; don't overstock."
        )
    elif tr is not None and tr["direction"] == "supply building":
        lines.append(
            f"  More units hitting the lanes (volume {_pct(tr['volume_change'])}) while sell-through "
            f"fell {abs(tr['sell_through_change']) * 100:.0f} pts. Expect prices to soften; buy, don't sell."
        )
    if mv is not None:
        lines.append(
            f"  Sells through {mv['sell_through'] * 100:.0f}% of the time at "
            f"{mv['price_to_mmr'] * 100:.0f}% of MMR (avg ${mv['avg_sale_price']:,.0f})."
        )
        if mv["price_to_mmr"] >= 1.02 and mv["sell_through"] >= 0.75:
            lines.append("  Pitch: proven seller that brings over book. Low risk to stock.")
        elif mv["sell_through"] >= 0.65 and mv["price_to_mmr"] < 0.98:
            lines.append("  Pitch: moves fast below book. Room for margin on retail.")
    return "\n".join(lines)


def pitches(mv: pd.DataFrame, tr: pd.DataFrame, top: int = 5) -> list[str]:
    """Pitches for the top movers plus the hottest and coolest trends."""
    picks = list(dict.fromkeys(
        list(mv.head(top).index) + list(tr.head(top).index) + list(tr.tail(2).index)
    ))
    return [
        pitch(v, mv.loc[v] if v in mv.index else None, tr.loc[v] if v in tr.index else None)
        for v in picks
    ]
