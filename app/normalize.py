"""Stage 2 - normalization.

Grids of strings in, typed tables out: parsed values, periods, note
references and a main item / sub-item / total hierarchy.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

CONFIG = {"pages": [5, 6, 7], "note": 11}

DASHES = {"-", "–", "—"}
HEADING_RE = re.compile(r"^#+\s*(.+?)\s*$", re.M)
CURRENCY_RE = re.compile(r"\(Tüm tutarlar\s+(.+?)\s+olarak", re.I)
YEAR_RE = re.compile(r"\b(20\d{2})\b")
# Rows holding ratios rather than money, where a dot is a decimal point.
RATIO_RE = re.compile(r"hisse başına|oranı", re.I)


def parse_value(raw: str, ratio: bool = False) -> dict:
    """A dash, an empty cell and a zero are three different things."""
    s = raw.strip()
    if not s:
        return {"raw": raw, "kind": "empty", "number": None}
    if s in DASHES:
        return {"raw": raw, "kind": "dash", "number": None}

    negative = s.startswith("(") and s.endswith(")")
    body = s.strip("()").replace("%", "").strip()
    if not re.fullmatch(r"[\d.,]+", body):
        return {"raw": raw, "kind": "text", "number": None}

    if "," in body:  # Turkish decimal comma
        body = body.replace(".", "").replace(",", ".")
    elif not ratio:  # dot is the thousands separator
        body = body.replace(".", "")

    try:
        n = Decimal(body)
    except InvalidOperation:
        return {"raw": raw, "kind": "text", "number": None}
    return {"raw": raw, "kind": "number", "number": str(-n if negative else n)}


def parse_note_refs(raw: str) -> list[int]:
    """"8,21" is two references, not a decimal."""
    return [int(n) for n in re.findall(r"\d+", raw)]


def split_header(grid: list[list[str]]) -> tuple[list[str], list[list[str]]]:
    """Peel off the header band, one flattened header per column.

    The income statement stacks its header over seven rows. A row belongs to
    the band while its label cell is empty and none of its cells is a number.
    """
    n = 0
    for row in grid:
        if row[0].strip() or any(parse_value(c)["kind"] == "number" for c in row[1:]):
            break
        n += 1
    n = max(n, 1)
    header = [" ".join(p.strip() for p in col if p.strip()) for col in zip(*grid[:n])]
    return header, grid[n:]


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


def normalize_table(grid: list[list[str]], page: int, text: str) -> dict:
    headings = [h for h in HEADING_RE.findall(text) if "ORTAKLIKLARI" not in h]
    title = headings[-1] if headings else ""
    kind = "balance_sheet" if "BİLANÇO" in title else "income_statement"

    header, body = split_header(grid)
    columns = build_columns(header, kind)
    ref_col = next((i for i, c in enumerate(columns) if c["role"] == "note_ref"), None)
    val_cols = [i for i, c in enumerate(columns) if c["role"] == "value"]

    rows = []
    for i, raw in enumerate(body):
        raw = list(raw) + [""] * (len(columns) - len(raw))
        label = raw[0].strip()
        values = {columns[j]["id"]: parse_value(raw[j], bool(RATIO_RE.search(label))) for j in val_cols}
        refs = parse_note_refs(raw[ref_col]) if ref_col is not None else []
        rows.append({
            "id": f"p{page:03d}.r{i:02d}",
            "label": label,
            "note_refs": refs,
            "note_refs_inherited": False,
            "role": classify(label, values, refs),
            "parent_id": None,
            "values": values,
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

    currency = CURRENCY_RE.search(text)
    return {
        "page": page,
        "title": title,
        "kind": kind,
        "currency": currency.group(1) if currency else None,
        "columns": columns,
        "rows": rows,
    }


def run(in_dir: Path, out_dir: Path, config: dict = CONFIG) -> list[dict]:
    pages = json.loads((in_dir / "01_pages.json").read_text())
    tables = [
        normalize_table(grid, page["page"], page["text"])
        for page in pages
        if page["page"] in set(config["pages"])
        for grid in page["tables"]
    ]
    (out_dir / "02_tables.json").write_text(json.dumps(tables, ensure_ascii=False, indent=1))
    return tables