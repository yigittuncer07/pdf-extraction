"""
Rules only, no model. Sources are the summary rows that reference the note;
targets are every row on the note's pages.
"""

from __future__ import annotations

import json
from pathlib import Path


def render(row: dict, table: dict, mode: str = "high") -> str:
    """
    `low` keeps only what varies between candidates under one note: the
    table's subject, the parent kalem and the label. High puts everything in, including the note reference and the values.
    """
    parts = []

    if mode == "high":
        parts.append(table["title"])

    # label headers don't mean anything in the summary tables but are important in the note tables.
    label_header = next((c["header"] for c in table["columns"] if c["role"] == "label"), "")
    if label_header:
        parts.append(f"tablo: {label_header}")

    parent = next((r for r in table["rows"] if r["id"] == row["parent_id"]), None)
    if parent:
        parts.append(f"ana kalem: {parent['label']}")
    parts.append(f"kalem: {row['label']}" if row["label"] else "kalem: (toplam satırı)") # assume no label means total row, which seems to be correct.

    if mode == "low":
        return " | ".join(p for p in parts if p)

    for col in table["columns"]:
        value = row["values"].get(col["id"])
        if value and value["kind"] != "empty":
            parts.append(f"{col['header']}: {value['raw']}")

    return " | ".join(p for p in parts if p)


class CandidateGenerator:
    def __init__(self, tables, summary_pages, note_pages, context_mode: str = "high"):
        self.tables = tables
        self.summary_pages = set(summary_pages)
        self.note_pages = set(note_pages)
        self.context_mode = context_mode

    def _rows(self, pages: set[int]):
        for table in self.tables:
            if table["page"] in pages:
                for row in table["rows"]:
                    if row["label"] or any(v["number"] is not None for v in row["values"].values()):
                        yield row, table

    def _entry(self, row: dict, table: dict) -> dict:
        periods = {c["id"]: c["period"]["year"] for c in table["columns"] if c["period"]}
        return {
            "id": row["id"],
            "label": row["label"],
            "table_id": table["id"],
            "context": render(row, table, mode=self.context_mode),
            # so the linker and its rule-based fallback
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


def run(tables, summary_pages, note_pages, note: int, out_dir: Path, context_mode: str = "high") -> dict:
    result = CandidateGenerator(tables, summary_pages, note_pages, context_mode=context_mode).generate(note)
    (out_dir / "04_candidates.json").write_text(json.dumps(result, ensure_ascii=False, indent=2))
    return result