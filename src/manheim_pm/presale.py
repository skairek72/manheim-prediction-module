"""Read Manheim "Pre-Sale Inventory" PDFs (list view) into a table.

Each vehicle line looks like:
    3-75 2025 ACURA MDX W/A-SPEC ADVANCE PACKAGE CR 4.9 6C/A 51,200 G PR 10,984 BLACK 5J8YE1H99SL802482

Columns can be blank (CR grade, fuel, top, colour) and long model names wrap
onto the lines above and below, so the line is read from both ends: lane-run and
year from the left, VIN / colour / odometer / top / fuel / MMR / engine from the
right, and whatever is left in the middle is the model.
"""
import logging
import re
from datetime import datetime
from pathlib import Path

import pandas as pd
import pdfplumber

logging.getLogger("pdfminer").setLevel(logging.ERROR)

ROW_START = re.compile(r"^(\d{1,3})-(\d{1,4}) ((?:19|20)\d\d)\b ?(.*)$")
SALE_HEADER = re.compile(r"(\d\d/\d\d/\d{4}) - \((\d+) Vehicles\)")
PRINTED_AT = re.compile(r"^(\d\d?/\d\d?/\d\d), (\d\d?:\d\d [AP]M)")
AUCTION = re.compile(r"^(Manheim .+?) Switch to")
NUMBER = re.compile(r"^\d[\d,]*$")
CR = re.compile(r"\bCR (\d\.\d)$")
EVBH = re.compile(r"\s*\|?\s*EVBH (\d+)%$")  # EV battery health, after the CR grade
TWO_WORD_MAKES = {
    "ALFA ROMEO", "ASTON MARTIN", "LAND ROVER", "ROLLS ROYCE", "ROLLS-ROYCE",
    "MERCEDES BENZ",
}
SKIP = ("Ln/Run", "Pre-Sale Inventory", "* Asterisk", "https://", "Manheim ")

COLUMNS = [
    "auction", "sale_date", "snapshot_at", "lane", "run", "year", "make", "model",
    "cr", "ev_battery_pct", "engine", "mmr", "fuel", "top", "odometer", "color", "vin", "not_at_auction",
]


class PresaleParseError(ValueError):
    pass


def _parse_tail(tokens: list[str]) -> dict | None:
    """Read engine..VIN from the right-hand end of a vehicle line."""
    if len(tokens) < 4:
        return None
    vin = tokens.pop()
    if not re.fullmatch(r"[A-Z0-9]{5,17}", vin):
        return None

    color = []
    while tokens and not NUMBER.match(tokens[-1]):
        color.insert(0, tokens.pop())
    if not tokens:
        return None
    odometer = int(tokens.pop().replace(",", ""))

    top = tokens.pop() if tokens and re.fullmatch(r"[A-Z]{2}", tokens[-1]) else None
    fuel = tokens.pop() if tokens and re.fullmatch(r"[A-Z]", tokens[-1]) else None

    mmr = None
    if tokens and (NUMBER.match(tokens[-1]) or tokens[-1] in {"N/A", "-", "--"}):
        raw = tokens.pop()
        mmr = int(raw.replace(",", "")) if NUMBER.match(raw) else None

    engine = None
    if tokens and "/" in tokens[-1] and not tokens[-1].startswith("W/"):
        engine = tokens.pop().strip("/") or None

    return {
        "rest": " ".join(tokens), "engine": engine, "mmr": mmr, "fuel": fuel, "top": top,
        "odometer": odometer, "color": " ".join(color) or None, "vin": vin,
    }


def _split_make(name: str) -> tuple[str, str]:
    words = name.split()
    if len(words) >= 2 and " ".join(words[:2]) in TWO_WORD_MAKES:
        return " ".join(words[:2]), " ".join(words[2:])
    return words[0], " ".join(words[1:])


def parse_presale(path: str | Path) -> tuple[pd.DataFrame, dict]:
    """Return (vehicles, info). info has auction, sale_date, snapshot_at, listed, parsed, problems."""
    with pdfplumber.open(path) as pdf:
        lines = [ln.strip() for page in pdf.pages for ln in (page.extract_text() or "").splitlines()]
    try:
        return parse_lines(lines)
    except PresaleParseError as e:
        raise PresaleParseError(f"{path}: {e}") from None


def parse_lines(lines: list[str]) -> tuple[pd.DataFrame, dict]:
    """Parse the text lines of a pre-sale PDF (split out so tests don't need a PDF)."""
    lines = list(lines)
    info = {"auction": None, "sale_date": None, "snapshot_at": None, "listed": None, "problems": []}
    for ln in lines[:10]:
        if m := SALE_HEADER.search(ln):
            info["sale_date"] = datetime.strptime(m.group(1), "%m/%d/%Y").date()
            info["listed"] = int(m.group(2))
        if (m := PRINTED_AT.match(ln)) and info["snapshot_at"] is None:
            info["snapshot_at"] = datetime.strptime(f"{m.group(1)} {m.group(2)}", "%m/%d/%y %I:%M %p")
        if m := AUCTION.match(ln):
            info["auction"] = m.group(1)
    if info["sale_date"] is None:
        raise PresaleParseError("no 'MM/DD/YYYY - (N Vehicles)' header; is this a pre-sale list PDF?")

    rows, pending_name = [], []
    for i, ln in enumerate(lines):
        m = ROW_START.match(ln)
        if not m:
            if ln and not ln.startswith(SKIP) and not PRINTED_AT.match(ln) and not SALE_HEADER.search(ln):
                pending_name.append(ln)  # wrapped model text (line above or below a vehicle)
            continue
        lane, run, year, after = m.groups()
        tail = _parse_tail(after.split())
        if tail is None:
            info["problems"].append(ln)
            pending_name = []
            continue

        rest = tail.pop("rest")
        ev_battery = None
        if e := EVBH.search(rest):
            ev_battery = int(e.group(1))
            rest = rest[:e.start()].strip()
        cr = None
        if c := CR.search(rest):
            cr = float(c.group(1))
            rest = rest[:c.start()].strip()
        if not rest:
            # Name wrapped: first part on the line above, last part on the line below.
            below = lines[i + 1] if i + 1 < len(lines) and not ROW_START.match(lines[i + 1]) else ""
            rest = " ".join(pending_name[-1:] + [below]).strip()
            if below:
                lines[i + 1] = ""  # consumed
        pending_name = []

        if re.search(r"\d,\d{3}|\bCR \d", rest):  # columns leaked into the name: misread line
            info["problems"].append(ln)
            continue

        not_here = rest.startswith("*")
        make, model = _split_make(rest.lstrip("* "))
        rows.append({
            "auction": info["auction"], "sale_date": info["sale_date"], "snapshot_at": info["snapshot_at"],
            "lane": int(lane), "run": int(run), "year": int(year), "make": make, "model": model,
            "cr": cr, "ev_battery_pct": ev_battery, **tail, "not_at_auction": not_here,
        })

    df = pd.DataFrame(rows, columns=COLUMNS)
    info["parsed"] = len(df)
    return df, info
