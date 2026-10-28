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


def save_postsale(con: sqlite3.Connection, cars: pd.DataFrame) -> int:
    """Store post-sale cars. Re-importing a sale replaces that sale's rows."""
    if cars.empty:
        return 0
    out = cars.copy()
    out["sale_date"] = out["sale_date"].astype(str)
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "postsale" in tables:
        have = {r[1] for r in con.execute("PRAGMA table_info(postsale)")}
        for col in out.columns.difference(list(have)):
            con.execute(f'ALTER TABLE postsale ADD COLUMN "{col}"')
        for code, date in out[["auction_code", "sale_date"]].drop_duplicates().itertuples(index=False):
            con.execute("DELETE FROM postsale WHERE auction_code = ? AND sale_date = ?", (code, date))
    out.to_sql("postsale", con, if_exists="append", index=False)
    con.commit()
    return len(out)


def load_postsales(con: sqlite3.Connection) -> pd.DataFrame:
    tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if "postsale" not in tables:
        return pd.DataFrame()
    df = pd.read_sql("SELECT * FROM postsale", con)
    df["sale_date"] = pd.to_datetime(df["sale_date"])
    df["partial"] = df["partial"].fillna(0).astype(bool) if "partial" in df else False
    return df


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
