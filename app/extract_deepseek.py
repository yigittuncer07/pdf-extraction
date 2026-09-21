import json
from app.backends import DeepSeekExtractor, ingest
from app.config import ARTIFACTS_DIR, INPUT_DOCUMENT

if __name__ == "__main__":
    artifacts = ARTIFACTS_DIR

    # Ingest DeepSeek
    ingest(INPUT_DOCUMENT, artifacts, extractor=DeepSeekExtractor(), pages=[4,5,6,7,53,54,55], out_file="01_pages.json")

    # Splice Docling's indents
    docling = json.loads((artifacts / "00_pages.json").read_text())
    deepseek_pages = json.loads((artifacts / "01_pages.json").read_text())
    docling_indents = {p["page"]: p.get("indents", []) for p in docling}
    for p in deepseek_pages:
        p["indents"] = docling_indents.get(p["page"], [])
    (artifacts / "01_pages.json").write_text(json.dumps(deepseek_pages, ensure_ascii=False, indent=2))
    print("DeepSeek extracted and spliced to artifacts/01_pages.json")