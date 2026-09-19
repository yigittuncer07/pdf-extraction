import json
from pathlib import Path
from time import time

from .backends import DoclingVlmExtractor, TableExtractor


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

from pathlib import Path
from app.backends import QwenVlmExtractor
from app.pipeline import ingest

if __name__ == "__main__":
    t0 = time()
    ingest(
        Path("ornek_dokuman.pdf"),
        Path("artifacts"),
        extractor=QwenVlmExtractor(),
        pages=[4, 5, 6, 7],
    )
    print(f"Finished in {time() - t0:.2f}s")