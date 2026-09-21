import html
import re

TABLE_RE = re.compile(r"<table.*?>.*?</table>", re.DOTALL | re.I)
ROW_RE = re.compile(r"<tr.*?>(.*?)</tr>", re.DOTALL | re.I)
CELL_RE = re.compile(r"<t[dh].*?>(.*?)</t[dh]>", re.DOTALL | re.I)
GROUNDING_RE = re.compile(r"<\|(ref|det)\|>.*?<\|/\1\|>", re.DOTALL)
HEADING_RE = re.compile(r"^#+\s*(.+?)\s*$", re.M)


def _cell_text(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", raw, flags=re.I)
    text = re.sub(r"<.*?>", "", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _rows(table_html: str) -> list[list[str]]:
    """One list of cell texts per <tr>."""
    out = []
    for row in ROW_RE.findall(table_html):
        cells = [_cell_text(c) for c in CELL_RE.findall(row)]
        if cells:
            out.append(cells)
    return out


def _fit(row: list[str], width: int) -> list[str]:
    """Force a row to `width` by shedding empty cells from the ends.
    This is a heuristic to help out with OCR issues and guarantee a grid.
    """
    row = list(row)
    while len(row) > width and row and row[-1] == "":
        row.pop()
    while len(row) > width and row and row[0] == "":
        row.pop(0)
    while len(row) < width:
        row.insert(0, "")  # short rows are header fragments missing the label cell
    return row[:width]


def _grid(table_html: str) -> list[list[str]]:
    rows = _rows(table_html)
    if not rows:
        return []

    # The true column count is whatever most rows agree on. Header fragments
    # are the minority and get fitted to it rather than defining it.
    counts = [len(r) for r in rows]
    width = max(set(counts), key=lambda n: (counts.count(n), n))
    body = [r for r in rows if len(r) == width]

    # A column empty in every body row is padding the model inserted. Drop it.
    keep = [j for j in range(width) if any(r[j] for r in body)]
    if len(keep) < 2:
        keep = list(range(width))

    return [_fit([r[j] for j in keep] if len(r) == width else r, len(keep)) for r in rows]


def _parse_page(raw: str) -> dict:
    """Model output -> {'text', 'tables', 'headings'}.

    `headings[i]` is the last markdown heading seen before `tables[i]`, so a
    page holding several tables can still tell them apart. Walking the raw
    output in order is the only place that association exists, once text and
    tables are split into separate lists it is gone.
    """
    raw = GROUNDING_RE.sub("", raw)

    tables, headings, heading, cursor = [], [], "", 0
    for match in TABLE_RE.finditer(raw):
        found = HEADING_RE.findall(raw[cursor:match.start()])
        if found:
            heading = found[-1]
        grid = _grid(match.group(0))
        if grid:
            tables.append(grid)
            headings.append(heading)
        cursor = match.end()

    text = re.sub(r"\n{3,}", "\n\n", TABLE_RE.sub("\n", raw)).strip()
    return {"text": html.unescape(text), "tables": tables, "headings": headings}
