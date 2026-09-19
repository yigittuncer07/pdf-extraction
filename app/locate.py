"""Stage 3 - page location.

The note number comes from config, so the pages it lives on have to be found
in the document rather than written down.

Two signals. The table of contents gives a printed page range, which the
printed-to-PDF offset turns into PDF pages. The note's own heading on those
pages then confirms it. They usually agree; when they do not, the caller is
told so rather than being handed a silent guess.
"""

from __future__ import annotations

import re

TOC_MARKER = "İÇİNDEKİLER"
FIRST_ENTRY_RE = re.compile(r"\.{2,}\s*(\d+)")


class PageFinder:
    def __init__(self, pages: list[dict]):
        self.pages = pages
        self.toc = next((p for p in pages if TOC_MARKER in p["text"]), None)

    def offset(self) -> int:
        """Printed page 1 is the page right after the contents page."""
        first = FIRST_ENTRY_RE.search(self.toc["text"])
        return self.toc["page"] + 1 - int(first.group(1))

    def printed_range(self, note: int) -> list[int]:
        """"NOT 11 YATIRIM AMAÇLI GAYRİMENKULLER..... 49-50" -> [49, 50]."""
        m = re.search(rf"NOT\s+{note}\.?\s+.*?\.{{2,}}\s*(\d+)(?:\s*-\s*(\d+))?", self.toc["text"])
        if not m:
            return []
        start, end = int(m.group(1)), int(m.group(2) or m.group(1))
        return list(range(start, end + 1))

    def heading_pages(self, note: int) -> list[int]:
        """Pages whose text carries the note's own heading, e.g. "## 11. ..."."""
        pattern = re.compile(rf"^#*\s*{note}\.\s+\S", re.M)
        return [p["page"] for p in self.pages if pattern.search(p["text"])]

    def find(self, note: int) -> dict:
        if not self.toc:
            found = self.heading_pages(note)
            return {"note": note, "pages": found, "source": "heading", "verified": False}

        offset = self.offset()
        from_toc = [n + offset for n in self.printed_range(note)]
        from_heading = self.heading_pages(note)
        return {
            "note": note,
            "pages": sorted(set(from_toc) | set(from_heading)) or from_toc,
            "toc_pages": from_toc,
            "heading_pages": from_heading,
            "offset": offset,
            "source": "toc",
            "verified": bool(from_toc) and set(from_toc) == set(from_heading),
        }