"""Stage 4 - candidate generation.

Rules only, no model. Sources are the summary rows that reference the note;
targets are every row on the note's pages. The candidate set is their cross
product, and it is the same set whichever scorer runs next -- otherwise
comparing two scorers would be comparing two different problems.

Both page sets are passed in: the summary pages from config, the note pages
from the page finder. Nothing here infers which table is which.

Each row is also rendered to a string, because a note row's meaning is not in
its own label -- "31 Aralık 2012 itibari ile kapanış bakiyesi" means nothing
until you know which table it closes.
"""

from __future__ import annotations

import json
from pathlib import Path


def render(row: dict, table: dict) -> str:
    """A row plus the context it needs to be understood on its own."""
    parts = [table["title"], f"sayfa {table['page']}"]
    
    # The label column's header names what the table is about. Empty on the
    # summary statements, but on a note table it is often the only thing
    # separating one table from the next.
    label_header = next((c["header"] for c in table["columns"] if c["role"] == "label"), "")
    if label_header:
        parts.append(f"tablo: {label_header}")

    parent = next((r for r in table["rows"] if r["id"] == row["parent_id"]), None)

    if parent:
        parts.append(f"ana kalem: {parent['label']}")
    parts.append(f"kalem: {row['label']}")

    if row["note_refs"]:
        refs = ", ".join(str(n) for n in row["note_refs"])
        parts.append(f"dipnot: {refs}" + (" (üst kalemden)" if row["note_refs_inherited"] else ""))

    for col in table["columns"]:
        value = row["values"].get(col["id"])
        if value and value["kind"] != "empty":
            parts.append(f"{col['header']}: {value['raw']}")

    return " | ".join(p for p in parts if p)


class CandidateGenerator:
    def __init__(self, tables: list[dict], summary_pages: list[int], note_pages: list[int]):
        self.tables = tables
        self.summary_pages = set(summary_pages)
        self.note_pages = set(note_pages)

    def _rows(self, pages: set[int]):
        for table in self.tables:
            if table["page"] in pages:
                for row in table["rows"]:
                    if row["label"]:
                        yield row, table

    @staticmethod
    def _entry(row: dict, table: dict) -> dict:
        periods = {c["id"]: c["period"]["year"] for c in table["columns"] if c["period"]}
        return {
            "id": row["id"],
            "label": row["label"],
            "table_id": table["id"],
            "context": render(row, table),
            # Structured evidence, so the linker and its rule-based fallback
            # never have to reach back into the tables.
            "values": {c: v["number"] for c, v in row["values"].items() if v["number"]},
            "periods": periods,
            "label_year": row.get("label_year"),
            "confidence": row.get("confidence", 0.5),
        }

    def generate(self, note: int) -> dict:
        sources = [self._entry(r, t) for r, t in self._rows(self.summary_pages) if note in r["note_refs"]]
        targets = [self._entry(r, t) for r, t in self._rows(self.note_pages)]
        return {
            "note": note,
            "sources": sources,
            "targets": targets,
            "pairs": [[s["id"], t["id"]] for s in sources for t in targets],
        }


def run(tables, summary_pages, note_pages, note: int, out_dir: Path) -> dict:
    result = CandidateGenerator(tables, summary_pages, note_pages).generate(note)
    (out_dir / "04_candidates.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result