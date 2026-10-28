"""Read Manheim "Post-Sale Results - Vehicle Listing" PDFs (printed from postsales.manheim.com).

The portal prints about 20-25 cars per PDF, so a sale arrives as a folder of
many small PDFs. Columns can be blank or run into each other ("SE DYNAMIC GRAY"
is subseries "SE DYNAMIC" + colour "GRAY"), so each word is placed in a column
by its position under the column headings, not by splitting text.
"""
import logging
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import pdfplumber

logging.getLogger("pdfminer").setLevel(logging.ERROR)

HEADINGS = ["Year", "Make", "Model", "Subseries", "Color", "Drs", "Cyl", "Fuel", "Trans", "4x4",
            "Radio", "Int", "Odometer", "Price"]
FIELD = {"4x4": "drive", "Int": "interior"}
SALE_LINE = re.compile(r"^([A-Z0-9]{3,5}) (\d\d/\d\d/\d{4}) Sales Results for")
AUCTION_LINE = re.compile(r"Post-Sale Results / (.+)$")
URL_PAGE = re.compile(r"[?&]page=(\d+)")
URL_MAKE = re.compile(r"[?&]make=([A-Z%0-9 +-]+?)(?:&|…|$)")

# The make column is narrow, so long makes are cut off ("MERCEDES-B", "MERCEDES B").
FULL_MAKES = ["ALFA ROMEO", "ASTON MARTIN", "LAND ROVER", "MERCEDES-BENZ", "MITSUBISHI", "ROLLS-ROYCE",
              "VOLKSWAGEN", "CHEVROLET", "CHRYSLER", "LAMBORGHINI", "MASERATI", "OLDSMOBILE", "PONTIAC",
              "FREIGHTLINER", "INTERNATIONAL", "LINCOLN", "CADILLAC", "INFINITI", "GENESIS", "HYUNDAI",
              "PORSCHE", "SUBARU", "SUZUKI", "MERCURY", "POLESTAR", "HUMMER"]


def full_make(make: str | None) -> str | None:
    """Expand a cut-off make to its full name when exactly one known make starts with it."""
    if not make:
        return make
    norm = lambda s: s.replace("-", " ")
    hits = [m for m in FULL_MAKES if norm(m).startswith(norm(make))]
    return hits[0] if len(hits) == 1 and make not in FULL_MAKES else make


COLUMNS = ["auction", "auction_code", "sale_date", "year", "make", "model", "subseries", "color",
           "doors", "cyl", "fuel", "trans", "drive", "radio", "interior", "odometer", "price",
           "source_file", "source_page"]


def _lines(page) -> list[list[dict]]:
    """Group words into lines by vertical position."""
    rows: dict[int, list[dict]] = {}
    for w in page.extract_words():
        key = round(w["top"])
        near = next((k for k in rows if abs(k - key) <= 2), key)
        rows.setdefault(near, []).append(w)
    return [sorted(rows[k], key=lambda w: w["x0"]) for k in sorted(rows)]


def _boundaries(header: list[dict]) -> list[tuple[str, float]]:
    """Each column starts a little left of its heading (numbers are right-aligned under it)."""
    xs = {w["text"]: w["x0"] for w in header}
    return [(h, xs[h] - 6) for h in HEADINGS if h in xs]


def _assign(words: list[dict], bounds: list[tuple[str, float]], odo_x: float) -> dict:
    cells: dict[str, list[str]] = {h: [] for h, _ in bounds}
    for w in words:
        t = w["text"]
        if t.startswith("$"):
            cells["Price"].append(t)
        elif w["x0"] >= odo_x - 30 and (re.fullmatch(r"[\d,]+", t) or t.lower() == "n/a"):
            cells["Odometer"].append(t)
        else:
            col = bounds[0][0]
            for h, start in bounds:
                if w["x0"] >= start and h not in ("Odometer", "Price"):
                    col = h
            cells[col].append(t)
    return {h: " ".join(v) or None for h, v in cells.items()}


def parse_postsale(path: str | Path) -> tuple[pd.DataFrame, dict]:
    """Return (cars, info). info has auction, auction_code, sale_date, page, make_filter, problems."""
    path = Path(path)
    info = {"file": path.name, "auction": None, "auction_code": None, "sale_date": None,
            "page": None, "make_filter": None, "problems": []}
    rows, bounds, odo_x = [], None, None

    with pdfplumber.open(path) as pdf:
        for pno, page in enumerate(pdf.pages, 1):
            for words in _lines(page):
                text = " ".join(w["text"] for w in words)
                if info["auction"] is None and (m := AUCTION_LINE.search(text)):
                    info["auction"] = m.group(1).strip()
                if m := SALE_LINE.match(text):
                    info["auction_code"] = m.group(1)
                    info["sale_date"] = datetime.strptime(m.group(2), "%m/%d/%Y").date()
                if text.startswith("https://postsales.manheim.com"):
                    if (m := URL_PAGE.search(text)) and info["page"] is None:
                        info["page"] = int(m.group(1))
                    if (m := URL_MAKE.search(text)) and info["make_filter"] is None:
                        info["make_filter"] = m.group(1).replace("%20", " ").replace("+", " ")
                if words[0]["text"] == "Year" and any(w["text"] == "Odometer" for w in words):
                    bounds = _boundaries(words)
                    odo_x = next(w["x0"] for w in words if w["text"] == "Odometer")
                    continue
                if bounds is None or not re.fullmatch(r"(19|20)\d\d", words[0]["text"]):
                    continue

                c = _assign(words, bounds, odo_x)
                try:
                    price = int(c["Price"].lstrip("$").replace(",", ""))
                    odometer = None if c["Odometer"].lower() == "n/a" else int(c["Odometer"].replace(",", ""))
                except (AttributeError, ValueError):
                    info["problems"].append(text)
                    continue
                rows.append({
                    "year": int(c["Year"]), "make": full_make(c["Make"]), "model": c["Model"],
                    "subseries": c["Subseries"], "color": c["Color"],
                    "doors": int(c["Drs"]) if c["Drs"] and c["Drs"].isdigit() else None,
                    "cyl": c["Cyl"], "fuel": c["Fuel"], "trans": c["Trans"], "drive": c["4x4"],
                    "radio": c["Radio"], "interior": c["Int"], "odometer": odometer, "price": price,
                    "source_file": path.name, "source_page": pno,
                })

    if info["sale_date"] is None:
        raise ValueError(f"{path.name}: no 'CODE MM/DD/YYYY Sales Results for' line; is this a post-sale PDF?")
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["auction"], df["auction_code"], df["sale_date"] = info["auction"], info["auction_code"], info["sale_date"]
    info["cars"] = len(df)
    return df, info


def read_folder(folder: str | Path) -> tuple[pd.DataFrame, list[dict]]:
    """Read every PDF in a folder (and sub-folders) and drop cars downloaded twice.

    A car counts as a duplicate when another file has the same auction, date,
    year, make, model, subseries, colour, odometer and price. Within one file
    identical rows are kept (two genuinely identical cars can sell).
    """
    frames, infos = [], []
    for pdf in sorted(Path(folder).rglob("*.pdf"), key=lambda p: p.name.lower()):
        try:
            df, info = parse_compact(pdf) if is_compact(pdf) else parse_postsale(pdf)
        except Exception as e:  # one bad file should not stop the folder
            infos.append({"file": pdf.name, "error": str(e), "cars": 0, "problems": []})
            continue
        frames.append(df)
        infos.append(info)
    if not frames:
        return pd.DataFrame(columns=COLUMNS + ["partial"]), infos

    cars = drop_repeat_downloads(pd.concat(frames, ignore_index=True))
    partial = {(i["auction_code"], i["sale_date"]) for i in infos if i.get("partial")}
    cars["partial"] = [(a, d) in partial for a, d in zip(cars["auction_code"], cars["sale_date"])]
    return cars, infos


def drop_repeat_downloads(cars: pd.DataFrame) -> pd.DataFrame:
    """Remove cars that appear in more than one file (the same page downloaded twice)."""
    key = ["auction_code", "sale_date", "year", "make", "model", "subseries", "color", "odometer", "price"]
    filled = cars.fillna({"subseries": "", "color": ""})
    copy = filled.groupby(key + ["source_file"]).cumcount()
    # keep, for each identical car, as many copies as the file that has the most of them
    keep = filled.assign(copy=copy).drop_duplicates(key + ["copy"]).index
    return cars.loc[keep].reset_index(drop=True)


# --- Compact summary format -------------------------------------------------------------
# A single multi-page PDF titled "<auction>: Post-Sale Results, MM/DD/YYYY" with columns
# Year | Make | Model | Trim | Drive | Miles | Sold Price, mileage rounded to 100 mi and
# price to $50. It may say which makes are missing ("Not included: ...").

COMPACT_TITLE = re.compile(r"^(Manheim .+?): Post-Sale Results, (\d\d/\d\d/\d{4})")
COMPACT_HEADINGS = ["Year", "Make", "Model", "Trim", "Drive", "Miles"]
AUCTION_CODES = {"Manheim NY Metro Skyline": "SKYA", "Manheim New Jersey": "NADE"}


def is_compact(path: str | Path) -> bool:
    with pdfplumber.open(path) as pdf:
        first = (pdf.pages[0].extract_text() or "").splitlines()[:2]
    return any(COMPACT_TITLE.match(ln.strip()) for ln in first)


def parse_compact(path: str | Path) -> tuple[pd.DataFrame, dict]:
    path = Path(path)
    info = {"file": path.name, "auction": None, "auction_code": None, "sale_date": None, "page": None,
            "make_filter": None, "problems": [], "partial": False, "missing_makes": [], "odometer_rounding": 100}
    rows, bounds = [], None
    with pdfplumber.open(path) as pdf:
        intro = " ".join((pdf.pages[0].extract_text() or "").split("Summary by make")[0].split())
        for pno, page in enumerate(pdf.pages, 1):
            for words in _lines(page):
                text = " ".join(w["text"] for w in words)
                if m := COMPACT_TITLE.match(text):
                    info["auction"] = m.group(1)
                    info["auction_code"] = AUCTION_CODES.get(m.group(1), m.group(1)[:5].upper())
                    info["sale_date"] = datetime.strptime(m.group(2), "%m/%d/%Y").date()
                if words[0]["text"] == "Year" and any(w["text"] == "Miles" for w in words):
                    xs = {w["text"]: w["x0"] for w in words}
                    bounds = [(h, xs[h] - 6) for h in COMPACT_HEADINGS if h in xs]
                    continue
                if bounds is None or not re.fullmatch(r"(19|20)\d\d", words[0]["text"]):
                    continue
                price = next((w["text"] for w in reversed(words) if w["text"].startswith("$")), None)
                body = [w for w in words if not w["text"].startswith("$")]
                miles = body.pop()["text"] if body and re.fullmatch(r"[\d,]+", body[-1]["text"]) else None
                cells = {h: [] for h, _ in bounds}
                for w in body:
                    col = bounds[0][0]
                    for h, start in bounds:
                        if w["x0"] >= start and h != "Miles":
                            col = h
                    cells[col].append(w["text"])
                c = {h: " ".join(v) or None for h, v in cells.items()}
                try:
                    rows.append({
                        "year": int(c["Year"]), "make": full_make(c["Make"]), "model": c["Model"],
                        "subseries": c["Trim"], "drive": c["Drive"],
                        "odometer": int(miles.replace(",", "")) if miles else None,
                        "price": int(price.lstrip("$").replace(",", "")),
                        "source_file": path.name, "source_page": pno,
                    })
                except (AttributeError, TypeError, ValueError):
                    info["problems"].append(text)
    if info["sale_date"] is None:
        raise ValueError(f"{path.name}: not a compact post-sale summary")
    if m := re.search(r"Not included: (.+?), about \d+ cars", intro):
        info["missing_makes"] = [s.strip().upper() for s in re.split(r",| and ", m.group(1)) if s.strip()]
        info["partial"] = True
    if re.search(r"partway|blocked|partial", intro, re.I):
        info["partial"] = True
    df = pd.DataFrame(rows, columns=COLUMNS)
    df["auction"], df["auction_code"], df["sale_date"] = info["auction"], info["auction_code"], info["sale_date"]
    info["cars"] = len(df)
    return df, info
