# Manheim Prediction Module

Analyzes wholesale auction results to answer three questions:

1. **What's moving?** Sell-through rate, volume and price vs MMR by vehicle (`movers.py`)
2. **What's trending?** The last 4 weeks vs the 4 before them (`trends.py`)
3. **What do I say?** Short sales pitches built only from those numbers (`pitches.py`)

## Windows app (no typing commands)

Download **ManheimPrediction.exe** from the repo's **Releases → latest** and double-click it.
GitHub builds it automatically on every change to `main` (`.github/workflows/build-exe.yml`).

Buttons: 1 Import pre-sale PDFs · 2 Pre-sale report · 3 Make shortlist · 4 Import post-sale folder ·
5 Scorecard · Open reports folder · Edit my criteria.

Your data lives in `Documents\Manheim Prediction` (history database, `criteria.toml`, `reports\`), so
replacing the .exe with a newer one keeps everything.

## Weekly pre-sale routine (Manheim NY Metro Skyline)

1. Download the **Pre-Sale Inventory** list as PDF (one or more snapshots before the sale).
2. Put the PDFs in `data/real/presale/` (private, never uploaded to GitHub).
3. Import and report:

```bash
python -m manheim_pm.cli import data/real/presale/*.pdf
python -m manheim_pm.cli presale --excel data/real/presale_report.xlsx
python -m manheim_pm.cli history
```

The report shows:
- **What's offered:** count, median MMR / miles / year, top makes, cars missing a CR or not yet on the lot
- **Last sale:** how many cars from the previous sale are back on this list (= did not sell)
- **Run-backs:** cars listed before, how many times, and how their MMR moved
- **Lanes:** size, typical car, and run-back share per lane (low = cars in that lane sell)
- **Changes between snapshots:** late additions, withdrawals, MMR moves

Importing the same PDF again replaces it; it never duplicates. The history lives in `data/real/manheim.db`.

## Weekly post-sale routine

1. After the sale, print the **Post-Sale Results** from postsales.manheim.com page by page as PDF
   (any file names; downloading a page twice is fine, repeats are removed).
2. Put them all in one folder, e.g. `data/real/manheim-pdf/` (sub-folders are fine).
3. Run:

```bash
python -m manheim_pm.cli postsale data/real/manheim-pdf --excel data/real/market_patterns_report.xlsx
```

This replaces the old .exe. The workbook has the same tabs (Overview, Top Makes, Top Models,
Make Model Year, Price/Mileage/Year Bands, Auction Date Trends, Model Trends, Price Trends,
Top Models by Day, Data Sufficiency) plus:
- **By Auction**: Skyline (SKYA, Tuesday) and New Jersey (NADE, Wednesday) kept apart
- **All Vehicles**: every sold car on its own row
- **Matched to Pre-Sale**: each sold car linked to its pre-sale row (lane, run, CR, MMR) by
  make + year + exact odometer; `match_quality` is exact / close / ambiguous / none

## Shortlist: cars to bid on

1. Edit `criteria.toml` (price range, year, miles, CR, costs, recon by CR, resale estimate).
2. Import the pre-sale for the coming sale, then:

```bash
python -m manheim_pm.cli shortlist --excel data/real/shortlist.xlsx
```

For each car that fits your rules it shows the **predicted hammer** (with a likely range), the
**chance it sells**, and your **max bid**:

    max bid = estimated resale - auction fee - transport - partner fee - estimated recon - minimum profit

The prediction (v1, `predict.py`) is MMR x a ratio learned from past matched sales, adjusted for
condition, lane, price band and mileage. It only learns from sales *before* the one being
shortlisted, so every shortlist is a fair test once that sale's post-sale is imported.

**The resale estimate in `criteria.toml` is a placeholder** (MMR + $3,500). Replace it with
your real resale numbers; every max bid depends on it.

## Weekly scorecard

Once a sale's post-sale is imported, score the predictions that were made before it:

```bash
python -m manheim_pm.cli scorecard --sale 2026-10-27 --excel data/real/scorecard.xlsx
```

It shows the median error of the predicted hammer vs plain MMR (overall and in your buy box),
how often the actual price fell inside the predicted range, how the shortlist did, and whether
adding lane / price band / mileage would have helped that week. Factors are only added to the
model when they keep helping.

Post-sales in the compact one-file format (rounded mileage, "Not included: ..." makes) are read
too and marked **partial**: their prices are learned, their sell / no-sell is not.

## Post-sale analysis (sample data)

### Quick start

```bash
pip install -e ".[dev]"
python scripts/make_sample_data.py          # FAKE data for development
python -m manheim_pm.cli analyze data/sample_sales.csv
pytest
```

## Input format

A CSV with one row per vehicle run through the lane:

| column | meaning |
|---|---|
| sale_date | YYYY-MM-DD |
| year, make, model | vehicle |
| mileage, condition_grade | odometer, condition report grade (1-5) |
| region | auction region or location |
| mmr | Manheim Market Report value at sale time |
| sale_price | hammer price, empty if no sale |
| sold | true / false |

Put real exports in `data/real/`. That folder is git-ignored so your data stays off GitHub.

## How the trend score works

- **Price change is mix-adjusted:** it compares the same model years across windows. A raw average jumps
  whenever newer cars happen to run, which looks like a trend but isn't one.
- **Volume is not counted as demand.** More units in the lanes can mean more supply. Rising volume with
  falling sell-through is labelled **supply building**, which is an early sign that prices will soften.
- `trend_score = 0.5 × price change + 0.5 × sell-through change` → heating up / flat / cooling.

## Data source note

Manheim data (MMR, sale results, Manheim Market Index) is licensed. Use the exports and API access that come with
your own Manheim account. Scraping the site breaks its terms of use and can get the account suspended.

## Roadmap

- [x] Pre-sale PDF reader, weekly history, run-backs, lanes, snapshot changes
- [x] Post-sale PDF reader (folder of page PDFs), market patterns workbook, match to pre-sale
- [x] Buying criteria + shortlist with predicted hammer price and max bid (v1 model)
- [ ] Weekly scorecard: prediction vs actual hammer; learn from misses

### Ideas

- Break down by region and by mileage/condition band (where a car moves, not just whether it does)
- Price-forecast model (next 4 weeks) once there are a few months of real history
- Weekly report emailed or posted automatically
