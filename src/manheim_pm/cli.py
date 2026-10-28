"""Command line.

    python -m manheim_pm.cli import  <pre-sale PDFs...>    store pre-sale snapshots
    python -m manheim_pm.cli presale [--sale YYYY-MM-DD] [--excel out.xlsx]
    python -m manheim_pm.cli history                        list what's stored
    python -m manheim_pm.cli analyze <sales.csv>            post-sale movers / trends / pitches
"""
import argparse
import sys

import pandas as pd

from . import store
from .load import load_sales
from .movers import movers
from .pitches import pitches
from .presale import PresaleParseError, parse_presale
from .presale_report import export_excel, text_report
from .trends import trends


def cmd_import(args) -> None:
    con = store.connect(args.db)
    for path in args.pdfs:
        try:
            df, info = parse_presale(path)
        except PresaleParseError as e:
            print(f"SKIPPED {e}", file=sys.stderr)
            continue
        store.save_presale(con, df)
        print(f"{path}\n  {info['auction']} | sale {info['sale_date']} | printed {info['snapshot_at']:%m/%d %I:%M %p} | "
              f"PDF says {info['listed']} cars, read {info['parsed']}")
        if info["problems"]:
            print(f"  {len(info['problems'])} line(s) could not be read:")
            for ln in info["problems"]:
                print(f"    {ln}")
        elif info["listed"] != info["parsed"]:
            print("  WARNING: count does not match the PDF header; check for pages missing from the PDF.")


def cmd_history(args) -> None:
    hist = store.load_presales(store.connect(args.db))
    if hist.empty:
        print("Nothing stored yet. Run: import <pre-sale PDFs>")
        return
    print(store.snapshots(hist).to_string(index=False))


def cmd_presale(args) -> None:
    hist = store.load_presales(store.connect(args.db))
    if hist.empty:
        print("Nothing stored yet. Run: import <pre-sale PDFs>")
        return
    sale = pd.Timestamp(args.sale) if args.sale else hist["sale_date"].max()
    pd.set_option("display.width", 200)
    pd.set_option("display.max_colwidth", 40)
    print(text_report(hist, sale))
    if args.excel:
        export_excel(hist, sale, args.excel)
        print(f"\nSaved {args.excel}")


def cmd_analyze(args) -> None:
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


def main() -> None:
    ap = argparse.ArgumentParser(description="Manheim auction analysis")
    ap.add_argument("--db", default=store.DEFAULT_DB, help="history database (default: data/real/manheim.db)")
    sub = ap.add_subparsers(dest="command", required=True)

    p = sub.add_parser("import", help="store pre-sale PDF snapshots")
    p.add_argument("pdfs", nargs="+")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("history", help="list stored snapshots")
    p.set_defaults(func=cmd_history)

    p = sub.add_parser("presale", help="pre-sale report for one sale")
    p.add_argument("--sale", help="sale date YYYY-MM-DD (default: latest)")
    p.add_argument("--excel", help="also save the flagged run list to this .xlsx file")
    p.set_defaults(func=cmd_presale)

    p = sub.add_parser("analyze", help="post-sale movers / trends / pitches from a CSV")
    p.add_argument("csv")
    p.add_argument("--top", type=int, default=10)
    p.add_argument("--window", type=int, default=28, help="trend window in days")
    p.set_defaults(func=cmd_analyze)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
