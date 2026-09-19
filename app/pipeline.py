"""The pipeline spine.

Each stage reads the previous stage's artifact and writes its own, so a stage
can be re-run without repeating the ones before it. That matters most at
ingestion, where OCR costs seconds per page.
"""

import json
from pathlib import Path
from time import time

from .backends import DeepSeekExtractor, TableExtractor
from .candidates import run as generate_candidates
from .locate import PageFinder
from .normalize import run as normalize

CONFIG = {
    "pages": [5, 6, 7],
    "note": 11,
}


def ingest(
    pdf: Path,
    out_dir: Path,
    extractor: TableExtractor,
    pages: list[int] | None = None,
) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pages_data = extractor.extract(pdf, pages)

    (out_dir / "01_pages.json").write_text(
        json.dumps(pages_data, ensure_ascii=False, indent=2)
    )
    return pages_data


if __name__ == "__main__":
    artifacts = Path("artifacts")

    t0 = time()
    # pages_data = ingest(
    #     Path("ornek_dokuman.pdf"),
    #     artifacts,
    #     extractor=DeepSeekExtractor(),
    #     # pages=[53, 54]  # EXTRACT ALL PAGES
    #     pages = [5, 6, 7, 50, 51, 52, 53, 54, 55]  
    # )
    print(f"Finished in {time() - t0:.2f}s")

    tables = normalize(artifacts, artifacts, config={"pages": []})  # NORMALIZE ALL PAGES

    # Read directly from the ingestion artifact
    pages_data = json.loads((artifacts / "01_pages.json").read_text())
    found = PageFinder(pages_data).find(CONFIG["note"])
    print(f"note {found['note']} -> pages {found['pages']} (verified: {found['verified']})")

    candidates = generate_candidates(
        tables, CONFIG["pages"], found["pages"], CONFIG["note"], artifacts
    )
    print(f"{len(candidates['sources'])} sources x {len(candidates['targets'])} targets "
          f"= {len(candidates['pairs'])} pairs")