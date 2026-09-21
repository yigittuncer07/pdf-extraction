"""Stage 7 - validation.

Confidence says how sure the pipeline is. Validation asks a different
question: is the output consistent with what the document asserts about
itself. Two extractors can agree on a wrong number and both cells score high;
only the arithmetic notices.

Three groups, as the task requires:
  structural -- was the note found on the page we think it was
  format     -- did values parse, did period and currency survive
  financial  -- do sub-items add up, and do summary values appear in the note

Anything that fails a check, or falls below the confidence threshold, is
flagged on the record itself.
"""

from __future__ import annotations

import json
import re
from decimal import Decimal
from pathlib import Path

LOW_CONFIDENCE = 0.6
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")


def issue(code: str, group: str, scope: str, message: str) -> dict:
    return {"code": code, "group": group, "scope": scope, "message": message}


def numbers(row: dict) -> dict[str, Decimal]:
    """A row's parsed values, keyed by column."""
    return {c: Decimal(v["number"]) for c, v in row["values"].items()
            if v["number"] is not None}


def check_note_page(found: dict) -> list[dict]:
    """The contents page and the note's own heading should agree."""
    if found.get("verified"):
        return []
    return [issue("NOTE_PAGE_UNVERIFIED", "structural", f"note:{found['note']}",
                  f"toc says {found.get('toc_pages')}, headings say {found.get('heading_pages')}")]


def check_parsing(tables: list[dict]) -> list[dict]:
    """Every cell in a value column should be a number, a dash or blank."""
    return [
        issue("VALUE_UNPARSED", "format", f"{row['id']}.{col}",
              f"{value['raw']!r} did not parse")
        for table in tables for row in table["rows"]
        for col, value in row["values"].items() if value["kind"] == "text"
    ]


def check_metadata(tables: list[dict]) -> list[dict]:
    """Currency and period have to survive extraction.

    Not every table has a period -- a note table may split by asset class
    instead -- so the check is preservation, not presence: a column header
    naming a year must have produced a parsed period.
    """
    out = []
    for table in tables:
        if not table["currency"]:
            out.append(issue("CURRENCY_MISSING", "format", table["id"],
                             "no currency on the page"))
        for column in table["columns"]:
            if column["role"] == "value" and not column["period"] \
                    and YEAR_RE.search(column["header"]):
                out.append(issue("PERIOD_LOST", "format", f"{table['id']}.{column['id']}",
                                 f"{column['header']!r} names a year but no period was parsed"))
    return out


def check_subitems(tables: list[dict]) -> list[dict]:
    """Sub-items must add up to the item they hang off.

    Scoped to the parent's cell in that column: the check is per column, and
    the failure belongs to the value that did not reconcile rather than to the
    whole row, whose other columns may be fine.
    """
    out = []
    for table in tables:
        for parent in table["rows"]:
            children = [r for r in table["rows"] if r["parent_id"] == parent["id"]]
            if not children:
                continue
            for col, total in numbers(parent).items():
                parts = [numbers(c).get(col) for c in children]
                # A child with no number here makes the sum meaningless
                # rather than wrong.
                if None in parts:
                    continue
                if sum(parts) != total:
                    out.append(issue("SUM_MISMATCH", "financial",
                                     f"{parent['id']}.{col}",
                                     f"sub-items sum to {sum(parts)}, "
                                     f"{parent['label']!r} says {total}"))
    return out


def check_note_values(tables: list[dict], note: int, note_pages: list[int]) -> list[dict]:
    """Every summary value pointing at the note should turn up inside it."""
    pages = set(note_pages)
    in_note = {v for t in tables if t["page"] in pages
               for r in t["rows"] for v in numbers(r).values()}
    if not in_note:
        return []
    return [
        issue("VALUE_NOT_IN_NOTE", "financial", f"{row['id']}.{col}",
              f"{row['label']!r} = {value} does not appear in note {note}")
        for table in tables if table["page"] not in pages
        for row in table["rows"] if note in row["note_refs"]
        for col, value in numbers(row).items() if value not in in_note
    ]


def flag(tables: list[dict], relations: list[dict], issues: list[dict],
         threshold: float = LOW_CONFIDENCE) -> None:
    """Mark every record that failed a check or scored below the threshold."""
    by_scope: dict[str, list[str]] = {}
    for i in issues:
        by_scope.setdefault(i["scope"], []).append(i["code"])

    def flags(scope: str, confidence: float) -> list[str]:
        found = list(by_scope.get(scope, []))
        if confidence < threshold:
            found.append("LOW_CONFIDENCE")
        return found

    for table in tables:
        table["flags"] = flags(table["id"], table.get("confidence", 1.0))
        for row in table["rows"]:
            row["flags"] = flags(row["id"], row.get("confidence", 1.0))
            for col, value in row["values"].items():
                value["flags"] = flags(f"{row['id']}.{col}", value.get("confidence", 1.0))

    for relation in relations:
        relation["flags"] = flags(relation["source_id"], relation.get("confidence", 1.0))


def validate(tables: list[dict], found: dict, note: int,
             relations: list[dict] | None = None,
             out_dir: Path | None = None) -> list[dict]:
    issues = (
        check_note_page(found)
        + check_parsing(tables)
        + check_metadata(tables)
        + check_subitems(tables)
        + check_note_values(tables, note, found["pages"])
    )
    flag(tables, relations or [], issues)

    if out_dir:
        (out_dir / "06_validation.json").write_text(json.dumps({
            "issues": issues,
            "counts": {g: sum(1 for i in issues if i["group"] == g)
                       for g in ("structural", "format", "financial")},
        }, ensure_ascii=False, indent=2))
    return issues