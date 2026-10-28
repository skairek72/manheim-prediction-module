"""Pre-sale analysis: what's offered, which lanes, which cars keep coming back.

Run-backs are the key signal. A VIN that appears on a later sale's list almost
certainly did not sell the first time, so the seller may now take less.
"""
import pandas as pd

from .store import final_lists


def flag_history(history: pd.DataFrame, sale_date) -> pd.DataFrame:
    """The list for one sale, with each car's history from earlier sales attached.

    times_run: how many sales this VIN has been listed in, including this one
    first_seen: the first sale date it was listed
    mmr_change_since_first: MMR now vs MMR when first listed
    """
    sale_date = pd.Timestamp(sale_date)
    finals = final_lists(history)
    current = finals[finals["sale_date"] == sale_date].copy()
    past = finals[finals["sale_date"] < sale_date]

    seen = past.groupby("vin").agg(
        earlier_runs=("sale_date", "nunique"),
        first_seen=("sale_date", "min"),
    )
    first_mmr = past.sort_values("sale_date").groupby("vin")["mmr"].first().rename("first_mmr")
    last_lane = past.sort_values("sale_date").groupby("vin")["lane"].last().rename("previous_lane")

    current = current.join(seen, on="vin").join(first_mmr, on="vin").join(last_lane, on="vin")
    current["times_run"] = current["earlier_runs"].fillna(0).astype(int) + 1
    current["first_seen"] = current["first_seen"].fillna(sale_date)
    current["run_back"] = current["times_run"] > 1
    current["mmr_change_since_first"] = (current["mmr"] / current["first_mmr"] - 1).round(3)
    return current.drop(columns=["earlier_runs", "first_mmr"])


def snapshot_changes(history: pd.DataFrame, sale_date) -> dict | None:
    """Compare the first and last snapshot of one sale: late additions, withdrawals, MMR moves."""
    sale = history[history["sale_date"] == pd.Timestamp(sale_date)]
    times = sorted(sale["snapshot_at"].unique())
    if len(times) < 2:
        return None
    early = sale[sale["snapshot_at"] == times[0]].set_index("vin")
    late = sale[sale["snapshot_at"] == times[-1]].set_index("vin")
    both = early.index.intersection(late.index)
    mmr_moves = (late.loc[both, "mmr"] - early.loc[both, "mmr"]).dropna()
    return {
        "from": times[0], "to": times[-1],
        "added": late.loc[late.index.difference(early.index)].reset_index(),
        "withdrawn": early.loc[early.index.difference(late.index)].reset_index(),
        "mmr_moved": int((mmr_moves != 0).sum()),
        "mmr_total_change": float(late.loc[both, "mmr"].sum() / early.loc[both, "mmr"].sum() - 1),
        "lane_moves": int((early.loc[both, "lane"] != late.loc[both, "lane"]).sum()),
    }


def lane_profile(flagged: pd.DataFrame) -> pd.DataFrame:
    """One row per lane: size, typical car, and how much of it is run-backs."""
    g = flagged.groupby("lane")
    out = pd.DataFrame({
        "cars": g.size(),
        "run_back_pct": (g["run_back"].mean() * 100).round(0),
        "median_mmr": g["mmr"].median(),
        "median_year": g["year"].median(),
        "median_miles": g["odometer"].median(),
        "no_cr_pct": (g["cr"].apply(lambda s: s.isna().mean()) * 100).round(0),
        "top_makes": g["make"].agg(lambda s: ", ".join(s.value_counts().head(3).index)),
    })
    return out


def previous_sale_outcome(history: pd.DataFrame, sale_date) -> dict | None:
    """For the sale before this one: how many cars came back (did not sell) vs did not."""
    finals = final_lists(history)
    dates = sorted(d for d in finals["sale_date"].unique() if d < pd.Timestamp(sale_date))
    if not dates:
        return None
    prev = finals[finals["sale_date"] == dates[-1]]
    now = finals[finals["sale_date"] == pd.Timestamp(sale_date)]
    came_back = prev["vin"].isin(now["vin"])
    return {
        "sale_date": dates[-1], "listed": len(prev),
        "came_back": int(came_back.sum()), "did_not_come_back": int((~came_back).sum()),
        "came_back_pct": float(came_back.mean()),
    }


def text_report(history: pd.DataFrame, sale_date) -> str:
    sale_date = pd.Timestamp(sale_date)
    flagged = flag_history(history, sale_date)
    if flagged.empty:
        return f"No pre-sale stored for {sale_date:%Y-%m-%d}."
    out = []
    auction = flagged["auction"].iloc[0]
    out.append(f"PRE-SALE REPORT: {auction}, sale of {sale_date:%a %m/%d/%Y}")
    out.append(f"Snapshot printed {flagged['snapshot_at'].iloc[0]:%m/%d %I:%M %p}\n")

    n = len(flagged)
    out.append("== WHAT'S OFFERED ==")
    out.append(f"{n:,} cars | median MMR ${flagged['mmr'].median():,.0f} | median {flagged['odometer'].median():,.0f} mi | "
               f"median year {flagged['year'].median():.0f}")
    out.append(f"No condition report: {flagged['cr'].isna().sum()} | Not on the lot yet (*): {flagged['not_at_auction'].sum()} | "
               f"No MMR: {flagged['mmr'].isna().sum()}")
    out.append("Top makes: " + ", ".join(f"{m} {c}" for m, c in flagged["make"].value_counts().head(8).items()))

    prev = previous_sale_outcome(history, sale_date)
    if prev:
        out.append(f"\n== LAST SALE ({prev['sale_date']:%m/%d}) ==")
        out.append(f"{prev['came_back']:,} of {prev['listed']:,} cars are back on this list ({prev['came_back_pct']:.0%}): "
                   "they did not sell.")
        out.append(f"{prev['did_not_come_back']:,} did not come back: sold, or withdrawn.")

    rb = flagged[flagged["run_back"]]
    out.append("\n== RUN-BACKS (listed before, still unsold) ==")
    if rb.empty:
        out.append("None yet. Run-backs show up once two or more weeks are imported.")
    else:
        out.append(f"{len(rb):,} of {n:,} cars ({len(rb) / n:.0%}) are run-backs.")
        out.append("By number of times listed: " + ", ".join(
            f"{t}x: {c}" for t, c in rb["times_run"].value_counts().sort_index().items()))
        cols = ["lane", "run", "year", "make", "model", "cr", "mmr", "odometer", "times_run", "mmr_change_since_first"]
        top = rb.sort_values(["times_run", "mmr"], ascending=[False, False]).head(15)
        out.append(top[cols].to_string(index=False))

    out.append("\n== LANES ==")
    out.append(lane_profile(flagged).to_string())

    ch = snapshot_changes(history, sale_date)
    if ch:
        out.append(f"\n== CHANGES BETWEEN SNAPSHOTS ({ch['from']:%m/%d %H:%M} -> {ch['to']:%m/%d %H:%M}) ==")
        out.append(f"Added late: {len(ch['added'])} | Withdrawn: {len(ch['withdrawn'])} | "
                   f"MMR moved on {ch['mmr_moved']} cars (total {ch['mmr_total_change']:+.2%}) | Lane moves: {ch['lane_moves']}")
        if len(ch["added"]):
            out.append("Late additions (fewer buyers have looked at these):")
            out.append(ch["added"][["lane", "run", "year", "make", "model", "cr", "mmr", "odometer"]]
                       .sort_values("mmr", ascending=False).head(10).to_string(index=False))
    return "\n".join(out)


def export_excel(history: pd.DataFrame, sale_date, path: str) -> None:
    """The flagged run list plus the lane table, for opening in Excel."""
    flagged = flag_history(history, sale_date)
    cols = ["lane", "run", "year", "make", "model", "cr", "ev_battery_pct", "mmr", "odometer", "color",
            "engine", "fuel", "top", "vin", "not_at_auction", "times_run", "first_seen", "previous_lane",
            "mmr_change_since_first"]
    with pd.ExcelWriter(path, engine="openpyxl") as xl:
        flagged.sort_values(["lane", "run"])[cols].to_excel(xl, sheet_name="Run list", index=False)
        lane_profile(flagged).to_excel(xl, sheet_name="Lanes")
        ch = snapshot_changes(history, sale_date)
        if ch and len(ch["added"]):
            ch["added"][cols[:14]].to_excel(xl, sheet_name="Added late", index=False)
        if ch and len(ch["withdrawn"]):
            ch["withdrawn"][cols[:14]].to_excel(xl, sheet_name="Withdrawn", index=False)
