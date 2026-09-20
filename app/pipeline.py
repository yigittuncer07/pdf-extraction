"""The pipeline spine.

Each stage reads the previous stage's artifact and writes its own, so a stage
can be re-run without repeating the ones before it. That matters most at
ingestion, where OCR costs seconds per page.
"""

import json
from pathlib import Path
from time import time

from .backends import DeepSeekExtractor, ingest, DoclingExtractor
from .candidates import run as generate_candidates
from .locate import PageFinder
from .normalize import run as normalize
from .confidence import SecondOpinion, score
from .linking import EmbeddingScorer, CrossEncoderScorer, RuleScorer, run as link_candidates

CONFIG = {
    "pages": [5, 6, 7],
    "note": 11,
}

if __name__ == "__main__":
    artifacts = Path("artifacts")

    # ------------ 1. Ingest the PDF, extract tables, titles, and text ------------
    t0 = time()
    pages = [4, 5, 6, 7, 50, 51, 52, 53, 54, 55]
    # pages = []
    # ingest(Path("ornek_dokuman.pdf"), artifacts, extractor=DeepSeekExtractor(), pages = pages, out_file="01_pages.json")
    print(f"DeepSeek ingested in {time() - t0:.2f}s")
    
    t0 = time()
    # ingest(Path("ornek_dokuman.pdf"), artifacts, extractor=DoclingExtractor(), pages = pages, out_file="00_pages.json")
    print(f"Docling (OCR) ingested in {time() - t0:.2f}s")
    
    # ------------ 2. Normalize the extracted tables into a standard format ------------
    t0 = time()
    tables = normalize(in_file="01_pages.json", directory=artifacts, config={"pages": []})
    print(f"normalized in {time() - t0:.2f}s")
    
    # ----------- 3. Score confidence using second opinion ------------
    docling = json.loads((artifacts / "00_pages.json").read_text()) 
    tables = score(tables, SecondOpinion(docling))
    with open(artifacts / "03_confidence.json", "w") as f:
        json.dump(tables, f, indent=2, ensure_ascii=False)
    
    #------------ 4. Locate the note reference page numbers ------------
    pages_data = json.loads((artifacts / "01_pages.json").read_text())
    found = PageFinder(pages_data).find(CONFIG["note"])
    print(f"note {found['note']} -> pages {found['pages']} (verified: {found['verified']})") # verified means TOC confirmed

    # ------------ 5. Generate candidate pairs of source and target tables ------------
    candidates = generate_candidates(
        tables, CONFIG["pages"], found["pages"], CONFIG["note"], artifacts
    )
    print(f"{len(candidates['sources'])} sources x {len(candidates['targets'])} targets "
          f"= {len(candidates['pairs'])} pairs")

    # ------------ 6. Link line items to footnote rows ------------
    t0 = time()
    try:
        scorer = EmbeddingScorer()
    except Exception as e:
        print(f"Embedding scorer unavailable ({e}); falling back to rules")
        scorer = RuleScorer()

    relations = link_candidates(candidates, scorer, artifacts)
    print(f"Linked in {time() - t0:.2f}s via {scorer.name}")

    accepted = sum(1 for r in relations if r["status"] == "accepted")
    low_conf = sum(1 for r in relations if r["status"] == "low_confidence")
    unlinked = sum(1 for r in relations if r["status"] == "unlinked")
    print(f"Relations: {accepted} accepted, {low_conf} low confidence, {unlinked} unlinked")
    
    # second experiment, try with a cross encoder scorer, which is more expensive but more accurate
    try:
        scorer = CrossEncoderScorer()
    except Exception as e:
        print(f"cross-encoder unavailable ({e}); falling back to rules")
        scorer = RuleScorer()

    relations = link_candidates(candidates, scorer, artifacts)
    print(f"Linked in {time() - t0:.2f}s via {scorer.name}")

    accepted = sum(1 for r in relations if r["status"] == "accepted")
    low_conf = sum(1 for r in relations if r["status"] == "low_confidence")
    unlinked = sum(1 for r in relations if r["status"] == "unlinked")
    print(f"Relations: {accepted} accepted, {low_conf} low confidence, {unlinked} unlinked")