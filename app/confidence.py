"""
Confidence scoring across cell, row, and table levels.
Computes deterministic confidence scores in [0.0, 1.0] using:
  1. Parse validity: whether a cell resolved to a valid financial type
     (number, dash, or blank).
  2. Cross-extractor agreement: validation against a secondary extractor
     (Docling) voting on the primary extractor's (DeepSeek) output.
"""
from .normalize import _tokens
from .helper import _overlap, _digits

AGREE = 1.0      # same text
SEPARATOR = 0.6  # same digits, different separators, one is wrong
DIFFER = 0.3     # different digits
NO_VOTE = 0.5    # the other extractor never saw this

# how much parse vs agreement affect cell confidence
CELL_WEIGHTS = {"parse": 0.4, "agreement": 0.6}

# How much columns vs rows affect table confidence
TABLE_WEIGHTS = {"rows": 0.80, "columns": 0.20}


class SecondOpinion:
    """What the other extractor read, looked up by page."""

    def __init__(self, pages: list[dict]):
        self.cells: dict[tuple, list[str]] = {}    # (page, label) -> cell texts
        self.columns: dict[tuple, list[str]] = {}  # (page, table index) -> column names

        for page in pages:
            n = page["page"]
            for index, grid in enumerate(page.get("tables", [])):
                if not grid:
                    continue
                self.columns[(n, index)] = [c.strip() for c in grid[0]]
                for row in grid[1:]:
                    if row and row[0].strip():
                        key = (n, _tokens(row[0]))
                        self.cells.setdefault(key, []).extend(c.strip() for c in row[1:])

    def cell(self, page: int, label: str, raw: str) -> float:
        others = self.cells.get((page, _tokens(label)))
        if not others:
            return NO_VOTE
        value = raw.strip()
        if value in others: # checks at row level, not cell level, so a different column value is still agreement.
            return AGREE
        if _digits(value) and any(_digits(o) == _digits(value) for o in others):
            return SEPARATOR
        return DIFFER

    def column_names(self, page: int, index: int, names: list[str]) -> float:
        """The same table as the other extractor read it, column by column.

        Divided by the wider of the two, so a differing column count costs
        points on its own.
        """
        others = self.columns.get((page, index))
        if not others or not names:
            return NO_VOTE
        matched = sum(_overlap(a, b) for a, b in zip(names, others))
        return round(matched / max(len(names), len(others)), 3)


def score(tables: list[dict], second: SecondOpinion | None = None) -> list[dict]:
    """Annotate every cell, row and table in place."""
    seen: dict[int, int] = {}
    for table in tables:
        page = table["page"]
        index = seen.get(page, 0)
        seen[page] = index + 1

        for row in table["rows"]:
            for value in row["values"].values():
                parse = 1.0 if value["kind"] in ("number", "dash", "empty") else 0.0
                # A blank cell has nothing to disagree about.
                agreement = NO_VOTE if not second or value["kind"] == "empty" \
                    else second.cell(page, row["label"], value["raw"])
                value["confidence_parts"] = {"parse": parse, "agreement": agreement}
                value["confidence"] = round(
                    CELL_WEIGHTS["parse"] * parse + CELL_WEIGHTS["agreement"] * agreement, 3
                )

            cells = [v["confidence"] for v in row["values"].values()]
            row["confidence"] = round(sum(cells) / len(cells), 3) if cells else NO_VOTE

        rows = [r["confidence"] for r in table["rows"]]
        parts = {
            "rows": round(sum(rows) / len(rows), 3) if rows else NO_VOTE,
            "columns": second.column_names(page, index, [c["header"] for c in table["columns"]])
            if second else NO_VOTE,
        }
        table["confidence_parts"] = parts
        table["confidence"] = round(
            sum(TABLE_WEIGHTS[k] * v for k, v in parts.items()), 3
        )

    return tables