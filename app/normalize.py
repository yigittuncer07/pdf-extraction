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
YEAR_ONLY_RE = re.compile(r"(19|20)\d{2}")

def parse_value(raw: str) -> dict:
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
    elif not body.startswith("0."):  # a leading "0." can only be a decimal point
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
    the band while its label cell is empty and none of its cells is a number. This is a postfix for OCR errors splitting header cells into multiple rows, so we take the first row that looks like data as the start of the body.
    """
    def is_data(cell: str) -> bool:
        # A bare year belongs to the header band; any other number is data.
        s = cell.strip()
        return parse_value(s)["kind"] == "number" and not YEAR_ONLY_RE.fullmatch(s)

    n = 0
    for row in grid:
        if row[0].strip() or any(is_data(c) for c in row[1:]):
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


def normalize_table(grid, page: int, index: int, text: str, heading: str = "") -> dict:
    # The extractor knows which heading preceded which table; fall back to the
    # page's last heading for extractors that do not report it.
    headings = HEADING_RE.findall(text)
    title = heading or (headings[-1] if headings else "")
    kind = ("balance_sheet" if "BİLANÇO" in title
            else "income_statement" if "GELİR TABLOSU" in title else "note")

    header, body = split_header(grid)
    columns = build_columns(header, kind)
    ref_col = next((i for i, c in enumerate(columns) if c["role"] == "note_ref"), None)
    val_cols = [i for i, c in enumerate(columns) if c["role"] == "value"]

    rows = []
    for i, raw in enumerate(body):
        raw = list(raw) + [""] * (len(columns) - len(raw))
        label = raw[0].strip()
        values = {columns[j]["id"]: parse_value(raw[j]) for j in val_cols}
        refs = parse_note_refs(raw[ref_col]) if ref_col is not None else []
        rows.append({
            "id": f"p{page:03d}.t{index}.r{i:02d}",
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
    directory: Path = Path("artifacts"),
    config: dict = CONFIG,
) -> list[dict]:
    directory = Path(directory)
    if in_file is None:
        in_path = directory / "01_pages.json"
    else:
        in_path = directory / in_file if not Path(in_file).is_absolute() else Path(in_file)

    pages = json.loads(in_path.read_text())
    target_pages = set(config["pages"]) if config.get("pages") else None

    tables = []
    for page in pages:
        if target_pages is not None and page["page"] not in target_pages:
            continue
        headings = page.get("headings") or []
        for i, grid in enumerate(page["tables"]):
            heading = headings[i] if i < len(headings) else ""
            tables.append(normalize_table(grid, page["page"], i, page["text"], heading))

    (directory / "02_tables.json").write_text(json.dumps(tables, ensure_ascii=False, indent=1))
    return tables