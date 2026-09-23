"""
One document, assembled from the stage artifacts. Nothing is recomputed here.
every field already exists upstream and this only decides what belongs in the
final schema and how it is arranged
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from .helper import HEADING_RE


def company_of(pages: list[dict]) -> str:
    """The heading that repeats on every page is the running header."""
    headings = Counter(h for p in pages for h in set(HEADING_RE.findall(p.get("text", ""))))
    return headings.most_common(1)[0][0] if headings else ""


def flatten(table: dict) -> list[dict]:
    """A table's rows, each carrying the table context a reader needs."""
    columns = {c["id"]: c for c in table["columns"]}
    return [
        {
            "id": row["id"],
            "table_id": table["id"],
            "table_title": table["title"],
            "page": table["page"],
            "label": row["label"],
            "role": row["role"],
            "parent_id": row["parent_id"],
            "note_refs": row["note_refs"],
            "note_refs_inherited": row["note_refs_inherited"],
            "values": [
                {
                    "column": columns[col]["header"],
                    "period": columns[col]["period"],
                    "raw": value["raw"],
                    "kind": value["kind"],
                    "number": value["number"],
                    "confidence": value.get("confidence"),
                    "flags": value.get("flags", []),
                }
                for col, value in row["values"].items()
            ],
            "confidence": row.get("confidence"),
            "flags": row.get("flags", []),
        }
        for row in table["rows"] if row["label"]
    ]


def build(pages: list[dict], tables: list[dict], found: dict, relations: list[dict],
          issues: list[dict], config: dict) -> dict:
    summary_pages, note_pages = set(config["pages"]), set(found["pages"])
    summary = [t for t in tables if t["page"] in summary_pages]
    note = [t for t in tables if t["page"] in note_pages]

    years = sorted({c["period"]["year"] for t in summary for c in t["columns"] if c["period"]},
                   reverse=True)
    currency = next((t["currency"] for t in summary if t["currency"]), None)

    return {
        "document": {
            "company": company_of(pages),
            "periods": years,
            "currency": currency,
        },
        "config": config,
        "note": found,
        "tables": [
            {k: t[k] for k in ("id", "page", "title", "kind", "currency")}
            | {"confidence": t.get("confidence"), "flags": t.get("flags", [])}
            for t in summary + note
        ],
        "summary_rows": [r for t in summary for r in flatten(t)],
        "note_rows": [r for t in note for r in flatten(t)],
        "relations": relations,
        "validation": {
            "issues": issues,
            "counts": {g: sum(1 for i in issues if i["group"] == g)
                       for g in ("structural", "format", "financial")},
        },
    }


def run(pages, tables, found, relations, issues, config, out_dir: Path) -> dict:
    output = build(pages, tables, found, relations, issues, config)
    (out_dir / "08_output.json").write_text(json.dumps(output, ensure_ascii=False, indent=2))
    return output