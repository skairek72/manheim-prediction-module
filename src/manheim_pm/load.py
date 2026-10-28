"""Load and clean auction sales exports (CSV)."""
from pathlib import Path

import pandas as pd

REQUIRED = [
    "sale_date", "year", "make", "model", "mileage",
    "condition_grade", "region", "mmr", "sale_price", "sold",
]


def load_sales(path: str | Path) -> pd.DataFrame:
    """Read a sales CSV, check its columns and normalise types.

    One row per vehicle run through the lane. `sale_price` is empty when the
    vehicle did not sell; `mmr` is the Manheim Market Report value at sale time.
    """
    df = pd.read_csv(path)
    missing = [c for c in REQUIRED if c not in df.columns]
    if missing:
        raise ValueError(f"missing columns: {', '.join(missing)}")

    df["sale_date"] = pd.to_datetime(df["sale_date"])
    df["sold"] = df["sold"].astype(str).str.lower().isin(["1", "true", "yes", "y"])
    for col in ["year", "mileage", "condition_grade", "mmr", "sale_price"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["make"] = df["make"].str.strip().str.title()
    df["model"] = df["model"].str.strip()
    df["vehicle"] = df["make"] + " " + df["model"]
    return df
