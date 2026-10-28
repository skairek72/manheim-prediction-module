"""Weekly history: every pre-sale snapshot ever imported, in one SQLite file."""
import sqlite3
from pathlib import Path

import pandas as pd

from .presale import COLUMNS

DEFAULT_DB = Path("data/real/manheim.db")


def connect(db: str | Path = DEFAULT_DB) -> sqlite3.Connection:
    Path(db).parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(db)
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS presale (
            {", ".join(COLUMNS)},
            PRIMARY KEY (auction, sale_date, snapshot_at, vin)
        )""")
    return con


def save_presale(con: sqlite3.Connection, df: pd.DataFrame) -> int:
    """Store one snapshot. Importing the same PDF twice replaces it instead of duplicating."""
    if df.empty:
        return 0
    first = df.iloc[0]
    con.execute(
        "DELETE FROM presale WHERE auction = ? AND sale_date = ? AND snapshot_at = ?",
        (first["auction"], str(first["sale_date"]), str(first["snapshot_at"])),
    )
    out = df.copy()
    out["sale_date"] = out["sale_date"].astype(str)
    out["snapshot_at"] = out["snapshot_at"].astype(str)
    out.to_sql("presale", con, if_exists="append", index=False)
    con.commit()
    return len(out)


def load_presales(con: sqlite3.Connection) -> pd.DataFrame:
    df = pd.read_sql("SELECT * FROM presale", con)
    df["sale_date"] = pd.to_datetime(df["sale_date"])
    df["snapshot_at"] = pd.to_datetime(df["snapshot_at"])
    df["not_at_auction"] = df["not_at_auction"].astype(bool)
    return df


def snapshots(df: pd.DataFrame) -> pd.DataFrame:
    """One row per imported snapshot: sale date, when it was printed, how many cars."""
    return (df.groupby(["auction", "sale_date", "snapshot_at"]).size()
              .rename("vehicles").reset_index().sort_values(["sale_date", "snapshot_at"]))


def final_lists(df: pd.DataFrame) -> pd.DataFrame:
    """The latest snapshot of each sale: the best picture of what actually ran."""
    last = df.groupby(["auction", "sale_date"])["snapshot_at"].transform("max")
    return df[df["snapshot_at"] == last]
