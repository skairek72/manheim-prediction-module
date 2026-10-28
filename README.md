# Manheim Prediction Module

Analyzes wholesale auction results to answer three questions:

1. **What's moving?** Sell-through rate, volume and price vs MMR by vehicle (`movers.py`)
2. **What's trending?** The last 4 weeks vs the 4 before them (`trends.py`)
3. **What do I say?** Short sales pitches built only from those numbers (`pitches.py`)

## Quick start

```bash
pip install -e ".[dev]"
python scripts/make_sample_data.py          # FAKE data for development
python -m manheim_pm.cli data/sample_sales.csv
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

## Roadmap ideas

- Break down by region and by mileage/condition band (where a car moves, not just whether it does)
- Price-forecast model (next 4 weeks) once there are a few months of real history
- Weekly report emailed or posted automatically
