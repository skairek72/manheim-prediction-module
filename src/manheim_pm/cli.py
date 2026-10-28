"""Command line.

    python -m manheim_pm.cli import  <pre-sale PDFs...>    store pre-sale snapshots
    python -m manheim_pm.cli presale [--sale YYYY-MM-DD] [--excel out.xlsx]
    python -m manheim_pm.cli postsale <folder> [--excel out.xlsx]   read a folder of post-sale PDFs
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
from .match import match_sale, sale_outcome
from .postsale import read_folder
from .postsale_report import build_tables, outcome_tables, write_workbook
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


def cmd_postsale(args) -> None:
    cars, infos = read_folder(args.folder)
    bad = [i for i in infos if i.get("error")]
    raw = sum(i["cars"] for i in infos)
    print(f"Read {len(infos)} PDF(s): {raw:,} car rows, {raw - len(cars):,} repeat download(s) removed -> {len(cars):,} cars")
    for i in bad:
        print(f"  SKIPPED {i['file']}: {i['error']}")
    for i in infos:
        for ln in i.get("problems", []):
            print(f"  could not read a line in {i['file']}: {ln}")
    if cars.empty:
        return
    con = store.connect(args.db)
    store.save_postsale(con, cars)
    summary = cars.groupby(["auction", "auction_code", "sale_date"]).size().rename("cars").reset_index()
    print(summary.to_string(index=False))

    tables = build_tables(store.load_postsales(con))

    # link each sale's sold cars back to its pre-sale list, where we have one
    pre_hist = store.load_presales(con)
    finals = store.final_lists(pre_hist) if not pre_hist.empty else pre_hist
    linked = []
    for (name, date), sold in cars.groupby(["auction", "sale_date"]):
        pre = finals[(finals["auction"] == name) & (finals["sale_date"] == pd.Timestamp(date))] if len(finals) else finals
        if len(pre) == 0:
            continue
        m = match_sale(sold, pre)
        q = m["match_quality"].value_counts()
        print(f"\n{name} {date}: matched to pre-sale {q.get('exact', 0)} exact + {q.get('close', 0)} close, "
              f"{q.get('ambiguous', 0)} ambiguous, {q.get('none', 0)} not on the pre-sale list "
              f"(of {len(m)} sold cars in these files)")
        ok = m[m["match_quality"].isin(["exact", "close"])]
        if len(ok) and ok["price_to_mmr"].notna().any():
            print(f"  hammer vs pre-sale MMR: median {ok['price_to_mmr'].median():.0%}")
        linked.append(m)

        later = finals[(finals["auction"] == name) & (finals["sale_date"] > pd.Timestamp(date))]
        nxt = set(later[later["sale_date"] == later["sale_date"].min()]["vin"]) if len(later) else set()
        out = outcome_tables(sale_outcome(pre, m), nxt)
        lanes = out["Outcome by Lane"]
        fates = out["Every Pre-Sale Car"]["fate"].value_counts()
        print(f"  of {len(pre):,} cars on the pre-sale list: {fates.get('sold', 0):,} sold, "
              f"{fates.get('ran again', 0):,} ran again next sale, {fates.get('gone', 0):,} gone"
              + ("" if nxt else " (next sale's pre-sale not imported yet, so 'gone' includes run-backs)"))
        for tab, df in out.items():
            tables[tab] = pd.concat([tables[tab], df.assign(sale=str(date))]) if tab in tables else df.assign(sale=str(date))
    if linked:
        tables["Matched to Pre-Sale"] = pd.concat(linked, ignore_index=True)

    if args.excel:
        write_workbook(tables, args.excel)
        print(f"\nSaved {args.excel}")


def cmd_history(args) -> None:
    hist = store.load_presales(store.connect(args.db))
    if hist.empty:
        print("Nothing stored yet. Run: import <pre-sale PDFs>")
        return
    print(store.snapshots(hist).to_string(index=False))
    post = store.load_postsales(store.connect(args.db))
    if not post.empty:
        print("\nPost-sale results:")
        print(post.groupby(["auction", "sale_date"]).size().rename("cars").reset_index().to_string(index=False))


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

    p = sub.add_parser("postsale", help="read a folder of post-sale PDFs, build the market patterns workbook")
    p.add_argument("folder", help="folder with the post-sale PDFs (e.g. manheim-pdf)")
    p.add_argument("--excel", help="save the market patterns workbook to this .xlsx file")
    p.set_defaults(func=cmd_postsale)

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
