import json
from time import time

from .normalize import run as normalize
from .confidence import SecondOpinion, score
from .locate import PageFinder
from .candidates import run as generate_candidates
from .linking import EmbeddingScorer, CrossEncoderScorer, RuleScorer, run as link_candidates
from .validation import validate
from .merge import run as export_deliverable
from .config import ARTIFACTS_DIR, CONFIG

if __name__ == "__main__":
    artifacts = ARTIFACTS_DIR
    docling = json.loads((artifacts / "00_pages.json").read_text())

    # ------------ 2. Normalize the extracted tables into a standard format ------------
    t0 = time()
    tables = normalize(in_file="01_pages.json", directory=artifacts)
    print(f"normalized in {time() - t0:.2f}s")
    
    # ----------- 3. Score confidence using second opinion ------------
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
    if False : # enable to test embedding vs cross encoder scorers
        t0 = time()
        try:
            scorer = EmbeddingScorer()
        except Exception as e:
            print(f"Embedding scorer unavailable ({e}); falling back to rules")
            scorer = RuleScorer()

        relations = link_candidates(candidates, scorer, artifacts, threshold=0.8) # determined after inspecting output logs. The bi encoder approach results in high simarities for all rows, very minimal difference, the rules are what choose really.    
        print(f"Linked in {time() - t0:.2f}s via {scorer.name}")

        accepted = sum(1 for r in relations if r["status"] == "accepted")
        unlinked = sum(1 for r in relations if r["status"] == "unlinked")
        print(f"Relations: {accepted} accepted, {unlinked} unlinked")
    
    else: # second experiment, try with a cross encoder scorer
        try:
            scorer = CrossEncoderScorer()
        except Exception as e:
            print(f"cross-encoder unavailable ({e}); falling back to rules")
            scorer = RuleScorer()

        relations = link_candidates(candidates, scorer, artifacts, threshold=0.55)
        print(f"Linked in {time() - t0:.2f}s via {scorer.name}")

        accepted = sum(1 for r in relations if r["status"] == "accepted")
        unlinked = sum(1 for r in relations if r["status"] == "unlinked")
        print(f"Relations: {accepted} accepted, {unlinked} unlinked")
    
    # ------------ 7. Validate output (structural, format, financial) ------------
    t0 = time()
    issues = validate(tables, found, CONFIG["note"], relations=relations, out_dir=artifacts)
    
    # Re-save relations to persist the appended validation flags
        # validate() writes flags in place, so both artifacts need re-saving
    (artifacts / "07_final_table.json").write_text(
        json.dumps(tables, ensure_ascii=False, indent=2)
    )
    (artifacts / "05_relations.json").write_text(
        json.dumps(relations, ensure_ascii=False, indent=2)
    )
    counts = {g: sum(1 for i in issues if i["group"] == g) for g in ("structural", "format", "financial")}
    print(f"Validated in {time() - t0:.2f}s: {len(issues)} issues found {counts}")

    # ------------ 8. Build Deliverable ------------
    t0 = time()
    export_deliverable(
        pages=pages_data,
        tables=tables,
        found=found,
        relations=relations,
        issues=issues,
        config=CONFIG,
        out_dir=artifacts,
    )
    print(f"Deliverable exported to {artifacts / '08_output.json'} in {time() - t0:.2f}s")