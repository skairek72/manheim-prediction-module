"""Market patterns workbook from post-sale results (same tabs as the old .exe report).

Unlike the old report it also keeps every car on its own tab, and dates are
split by auction so Skyline (Tuesday) and New Jersey (Wednesday) never mix.
"""
import pandas as pd

PRICE_BANDS = [0, 3000, 5000, 7500, 10000, 15000, 20000, 25000, 30000, 40000, 50000, float("inf")]
PRICE_LABELS = ["<$3k", "$3k-$5k", "$5k-$7.5k", "$7.5k-$10k", "$10k-$15k", "$15k-$20k", "$20k-$25k",
                "$25k-$30k", "$30k-$40k", "$40k-$50k", "$50k+"]
MILE_BANDS = [-1, 30000, 60000, 90000, 120000, 150000, 200000, float("inf")]
MILE_LABELS = ["0-30k", "30-60k", "60-90k", "90-120k", "120-150k", "150-200k", "200k+"]


def _year_band(y: int, newest: int) -> str:
    if y >= 2024:
        return "2024+"
    for lo, hi in [(2021, 2023), (2018, 2020), (2015, 2017), (2011, 2014)]:
        if lo <= y <= hi:
            return f"{lo}-{hi}"
    return "2010 and older"


def _stats(g, extra: dict | None = None) -> pd.DataFrame:
    cols = {
        "Units_Sold": ("price", "size"), "Median_Price": ("price", "median"), "Avg_Price": ("price", "mean"),
        "Median_Mileage": ("odometer", "median"),
    }
    cols.update(extra or {})
    return g.agg(**cols).round(0).reset_index()


def build_tables(cars: pd.DataFrame) -> dict[str, pd.DataFrame]:
    c = cars.copy()
    c["sale_date"] = pd.to_datetime(c["sale_date"])
    c["Price_Band"] = pd.cut(c["price"], PRICE_BANDS, labels=PRICE_LABELS, right=False)
    c["Mileage_Band"] = pd.cut(c["odometer"], MILE_BANDS, labels=MILE_LABELS)
    c["Year_Band"] = c["year"].map(lambda y: _year_band(y, c["year"].max()))
    by_units = lambda df: df.sort_values("Units_Sold", ascending=False)

    overview = pd.DataFrame({"Metric": [
        "Total Vehicles", "Auction Dates", "Auctions", "Unique Makes", "Unique Models", "Average Sale Price",
        "Median Sale Price", "Minimum Sale Price", "Maximum Sale Price", "Average Mileage", "Median Mileage",
    ], "Value": [
        len(c), c["sale_date"].nunique(), ", ".join(sorted(c["auction"].dropna().unique())),
        c["make"].nunique(), c.groupby(["make", "model"]).ngroups, round(c["price"].mean(), 2),
        c["price"].median(), c["price"].min(), c["price"].max(), round(c["odometer"].mean()), c["odometer"].median(),
    ]})

    t = {"Overview": overview}
    t["By Auction"] = _stats(c.groupby("auction"), {"Sale_Dates": ("sale_date", "nunique")})
    t["Top Makes"] = by_units(_stats(c.groupby("make"), {
        "Avg_Mileage": ("odometer", "mean"), "Min_Price": ("price", "min"), "Max_Price": ("price", "max")}))
    t["Top Models"] = by_units(_stats(c.groupby(["make", "model"]), {
        "Avg_Mileage": ("odometer", "mean"), "Median_Year": ("year", "median"),
        "Min_Price": ("price", "min"), "Max_Price": ("price", "max")}))
    t["Make Model Year"] = by_units(_stats(c.groupby(["make", "model", "year"]), {
        "P25_Price": ("price", lambda s: s.quantile(0.25)), "P75_Price": ("price", lambda s: s.quantile(0.75))}))
    t["Price Bands"] = _stats(c.groupby("Price_Band", observed=True), {"Median_Year": ("year", "median")})
    t["Mileage Bands"] = _stats(c.groupby("Mileage_Band", observed=True), {"Median_Year": ("year", "median")})
    t["Year Bands"] = by_units(_stats(c.groupby("Year_Band")))
    t["Auction Date Trends"] = _stats(c.groupby(["auction", "sale_date"]), {
        "Avg_Mileage": ("odometer", "mean"), "Unique_Makes": ("make", "nunique"), "Unique_Models": ("model", "nunique")})
    mt = _stats(c.groupby(["auction", "sale_date", "make", "model"]))
    t["Model Trends"] = mt.sort_values(["auction", "sale_date", "Units_Sold"], ascending=[True, True, False])
    t["Price Trends"] = _stats(c.groupby(["auction", "sale_date", "make"])).sort_values(
        ["auction", "sale_date", "Units_Sold"], ascending=[True, True, False])
    t["Top Models by Day"] = (t["Model Trends"].groupby(["auction", "sale_date"]).head(10)
                              [["auction", "sale_date", "make", "model", "Units_Sold"]])

    dates = c["sale_date"].nunique()
    t["Data Sufficiency"] = pd.DataFrame({"Metric": ["Total Vehicles", "Auction Dates", "Interpretation"], "Value": [
        len(c), dates,
        "Single date: no trends yet." if dates < 2 else
        "A few dates: trends are early signals." if dates < 6 else
        "Multiple dates: trend analysis is becoming meaningful.",
    ]})
    t["All Vehicles"] = c.drop(columns=["Price_Band", "Mileage_Band", "Year_Band"]).sort_values(
        ["auction", "sale_date", "make", "model", "year"])
    return t


def write_workbook(tables: dict[str, pd.DataFrame], path: str) -> None:
    with pd.ExcelWriter(path, engine="openpyxl") as xl:
        for name, df in tables.items():
            df.to_excel(xl, sheet_name=name[:31], index=False)
            ws = xl.sheets[name[:31]]
            for col in ws.columns:
                width = max(len(str(v.value)) if v.value is not None else 0 for v in col[:200])
                ws.column_dimensions[col[0].column_letter].width = min(max(width + 2, 8), 45)
            ws.freeze_panes = "A2"


def outcome_tables(outcome: pd.DataFrame, next_list_vins: set | None = None) -> dict[str, pd.DataFrame]:
    """What happened to every car on a pre-sale list: sold, ran again next sale, or gone.

    outcome comes from match.sale_outcome. "gone" means neither in the sold files nor
    on the next list: withdrawn, sold privately after the sale, or a post-sale page
    that was not downloaded.
    """
    o = outcome.copy()
    nxt = next_list_vins or set()
    o["fate"] = "gone"
    o.loc[o["vin"].isin(nxt), "fate"] = "ran again"
    o.loc[o["sold"], "fate"] = "sold"
    o["hammer_vs_mmr"] = (o["price"] / o["mmr"]).round(3)
    o["CR_Band"] = pd.cut(o["cr"], [0, 2, 3, 4, 5.1], labels=["<2.0", "2.0-2.9", "3.0-3.9", "4.0+"],
                          right=False).cat.add_categories("no CR").fillna("no CR")
    o["MMR_Band"] = pd.cut(o["mmr"], [0, 3000, 7500, 15000, 30000, float("inf")],
                           labels=["<$3k", "$3k-$7.5k", "$7.5k-$15k", "$15k-$30k", "$30k+"])

    def summary(by):
        g = o.groupby(by, observed=True)
        t = pd.DataFrame({
            "Cars": g.size(),
            "Sold_%": (g["sold"].mean() * 100).round(0),
            "Ran_Again_%": (g["fate"].apply(lambda s: (s == "ran again").mean()) * 100).round(0),
            "Gone_%": (g["fate"].apply(lambda s: (s == "gone").mean()) * 100).round(0),
            "Median_Hammer_vs_MMR_%": (g["hammer_vs_mmr"].median() * 100).round(0),
        })
        return t.reset_index()

    cols = ["sale_date", "lane", "run", "year", "make", "model", "cr", "mmr", "odometer", "vin",
            "fate", "price", "hammer_vs_mmr", "match_quality"]
    return {
        "Outcome by Lane": summary("lane"),
        "Outcome by CR": summary("CR_Band"),
        "Outcome by MMR": summary("MMR_Band"),
        "Outcome by Make": summary("make").sort_values("Cars", ascending=False),
        "Every Pre-Sale Car": o[cols].sort_values(["lane", "run"]),
    }
