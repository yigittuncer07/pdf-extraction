"""Stage 2 - normalization.

Grids of strings in, typed tables out: parsed values, periods, note
references and a main item / sub-item / total hierarchy.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from .config import ARTIFACTS_DIR, CONFIG
from .helper import (
    CURRENCY_RE,
    DECIMAL_DOT,
    DOT_THOUSANDS,
    HEADING_RE,
    YEAR_RE,
    _parse_note_refs,
    _split_header,
    _tokens,
)

DASHES = {"-", "–", "—"}


def attach_indents(rows: list[dict], indents: list[float | None],
                   labels: list[str] | None = None) -> None:
    """Take the label x position from the second extractor, by row index.

    Checked against the label text rather than assumed: a row whose labels do
    not agree gets no indent and falls back to the '-' prefix rule. Trusting
    the index alone is worse than skipping, because a one-row shift yields a
    wrong hierarchy rather than none.
    """
    for i, (row, x) in enumerate(zip(rows, indents)):
        if labels and not (_tokens(row["label"]) & _tokens(labels[i])):
            continue
        row["indent"] = x


def link_indents(rows: list[dict], tolerance: float = 4.0) -> None:
    """Parent = the nearest row above at a shallower indent.

    Read from the page rather than inferred from the numbers, which is what
    lets validation check the sums against it independently.
    """
    xs = sorted({r["indent"] for r in rows if r.get("indent") is not None})
    levels: list[float] = []
    for x in xs:
        if not levels or x - levels[-1] > tolerance:
            levels.append(x)

    for row in rows:
        x = row.get("indent")
        row["level"] = (min(range(len(levels)), key=lambda i: abs(levels[i] - x))
                        if x is not None and levels else None)

    for i, row in enumerate(rows):
        if row["level"] is None or row["parent_id"]:
            continue
        parent = next((p for p in reversed(rows[:i])
                       if p["level"] is not None and p["level"] < row["level"]), None)
        if parent:
            row["parent_id"] = parent["id"]


def parse_value(raw: str) -> dict:
    """A dash, an empty cell and a zero are three different things."""
    s = raw.strip()
    if not s:
        return {"raw": raw, "kind": "empty", "number": None}
    if s in DASHES:
        return {"raw": raw, "kind": "dash", "number": None}

    negative = s.startswith("(") and s.endswith(")")
    body = s.strip("()").replace("%", "").strip()

    if DOT_THOUSANDS.fullmatch(body):
        body = body.replace(".", "").replace(",", ".")
    elif DECIMAL_DOT.fullmatch(body) and body.startswith("0."):
        pass
    else:
        return {"raw": raw, "kind": "text", "number": None}

    try:
        n = Decimal(body)
    except InvalidOperation:
        return {"raw": raw, "kind": "text", "number": None}
    return {"raw": raw, "kind": "number", "number": str(-n if negative else n)}


def build_columns(header: list[str], kind: str) -> list[dict]:
    columns = []
    for i, h in enumerate(header):
        role = "label" if i == 0 else "note_ref" if re.search(r"dipnot", h, re.I) else "value"
        year = YEAR_RE.search(h)
        columns.append({
            "id": f"c{i}",
            "header": h,
            "role": role,
            "period": {
                "kind": "instant" if kind == "balance_sheet" else "duration",
                "year": int(year.group(1)),
            } if role == "value" and year else None,
        })
    return columns


def classify(label: str, values: dict, refs: list[int]) -> str:
    letters = [c for c in label if c.isalpha()]
    if label[:1] in ("-", "~", "–"):
        return "subitem"
    if all(v["kind"] == "empty" for v in values.values()) and not refs:
        return "section"
    if letters and all(c.isupper() for c in letters):
        return "total"
    return "item"


def normalize_table(grid, page: int, index: int, text: str, heading: str = "", indents: list[float | None] | None = None) -> dict:
    # The extractor knows which heading preceded which table; fall back to the
    # page's last heading for extractors that do not report it.
    headings = HEADING_RE.findall(text)
    title = heading or (headings[-1] if headings else "")
    kind = ("balance_sheet" if "BİLANÇO" in title
            else "income_statement" if "GELİR TABLOSU" in title else "note")

    header, body = _split_header(grid, parse_value)
    columns = build_columns(header, kind)
    ref_col = next((i for i, c in enumerate(columns) if c["role"] == "note_ref"), None)
    val_cols = [i for i, c in enumerate(columns) if c["role"] == "value"]

    rows = []
    for i, raw in enumerate(body):
        raw = list(raw) + [""] * (len(columns) - len(raw))
        label = raw[0].strip()
        label_year = YEAR_RE.search(label)
        values = {columns[j]["id"]: parse_value(raw[j]) for j in val_cols}
        refs = _parse_note_refs(raw[ref_col]) if ref_col is not None else []
        rows.append({
            "id": f"p{page:03d}.t{index}.r{i:02d}",
            "label": label,
            "note_refs": refs,
            "note_refs_inherited": False,
            "role": classify(label, values, refs),
            "parent_id": None,
            "values": values,
            "label_year": int(label_year.group(1)) if label_year else None, 
        })

    # A sub-item belongs to the item above it, and inherits its note reference.
    for i, row in enumerate(rows):
        if row["role"] != "subitem":
            continue
        parent = next((p for p in reversed(rows[:i]) if p["role"] == "item"), None)
        if parent:
            row["parent_id"] = parent["id"]
            if not row["note_refs"]:
                row["note_refs"] = list(parent["note_refs"])
                row["note_refs_inherited"] = True
                
    if kind != "income_statement" and indents:
        attach_indents(rows, indents[1:])
        link_indents(rows)

    currency = CURRENCY_RE.search(text)
    return {
        "id": f"p{page:03d}.t{index}",
        "page": page,
        "title": title,
        "kind": kind,
        "currency": currency.group(1) if currency else None,
        "columns": columns,
        "rows": rows,
    }


def run(
    in_file: Path | str | None = None,
    directory: Path = ARTIFACTS_DIR,
) -> list[dict]:
    directory = Path(directory)
    in_path = directory / (in_file or "01_pages.json")

    pages = json.loads(in_path.read_text())

    tables = []
    for page in pages:
        headings = page.get("headings") or []
        page_indents = page.get("indents") or []

        for i, grid in enumerate(page["tables"]):
            heading = headings[i] if i < len(headings) else ""
            tbl_indents = page_indents[i] if i < len(page_indents) else None
            tables.append(normalize_table(grid, page["page"], i, page["text"], heading, indents=tbl_indents))

    (directory / "02_tables.json").write_text(json.dumps(tables, ensure_ascii=False, indent=1))
    return tables