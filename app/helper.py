""""Helper functions"""
import html
import re

TABLE_RE = re.compile(r"<table.*?>.*?</table>", re.DOTALL | re.I)
ROW_RE = re.compile(r"<tr.*?>(.*?)</tr>", re.DOTALL | re.I)
CELL_RE = re.compile(r"<t[dh].*?>(.*?)</t[dh]>", re.DOTALL | re.I)
GROUNDING_RE = re.compile(r"<\|(ref|det)\|>.*?<\|/\1\|>", re.DOTALL)
HEADING_RE = re.compile(r"^#+\s*(.+?)\s*$", re.M)
CURRENCY_RE = re.compile(r"\(Tüm tutarlar\s+(.+?)\s+olarak", re.I)
YEAR_RE = re.compile(r"\b(20\d{2})\b")
YEAR_ONLY_RE = re.compile(r"(19|20)\d{2}")
DOT_THOUSANDS = re.compile(r"\d{1,3}(\.\d{3})*(,\d+)?$")
DECIMAL_DOT = re.compile(r"\d+\.\d+$")


def _tokens(text: str) -> frozenset[str]:
    """Order-insensitive key. docling writes "Gelirleri Satış" for "Satış Gelirleri". Still want to keep since docling is a second opinion only."""
    lowered = text.replace("I", "ı").replace("İ", "i").lower()
    return frozenset(re.findall(r"[0-9a-zçğıöşü]+", lowered))


def _digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def _overlap(a: str, b: str) -> float:
    """Return the fraction of shared tokens between two strings, ignoring order and case."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        return 1.0
    return len(ta & tb) / len(ta | tb) if ta and tb else 0.0


def _parse_note_refs(raw: str) -> list[int]:
    """"8,21" is two references, not a decimal."""
    return [int(n) for n in re.findall(r"\d+", raw)]


def _split_header(grid: list[list[str]], parse_value) -> tuple[list[str], list[list[str]]]:
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
