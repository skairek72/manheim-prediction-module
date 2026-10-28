"""Command line: python -m manheim_pm.cli data/sample_sales.csv"""
import argparse

import pandas as pd

from .load import load_sales
from .movers import movers
from .pitches import pitches
from .trends import trends


def main() -> None:
    ap = argparse.ArgumentParser(description="Manheim auction analysis: movers, trends, pitches")
    ap.add_argument("csv", help="sales export CSV")
    ap.add_argument("--top", type=int, default=10)
    ap.add_argument("--window", type=int, default=28, help="trend window in days")
    args = ap.parse_args()

    df = load_sales(args.csv)
    mv = movers(df)
    tr = trends(df, window_days=args.window)

    pd.set_option("display.width", 160)
    print(f"{len(df):,} runs, {df['sale_date'].min():%Y-%m-%d} to {df['sale_date'].max():%Y-%m-%d}\n")
    print("== WHAT'S MOVING ==")
    print(mv.head(args.top).to_string(), "\n")
    print("== WHAT'S TRENDING ==")
    cols = ["runs_recent", "avg_price_recent", "price_change", "volume_change", "sell_through_change", "direction"]
    print(tr[cols].head(args.top).to_string(), "\n")
    print("== SALES PITCHES ==")
    print("\n\n".join(pitches(mv, tr)))


if __name__ == "__main__":
    main()
