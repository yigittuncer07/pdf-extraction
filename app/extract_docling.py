from app.backends import DoclingExtractor, ingest
from app.config import ARTIFACTS_DIR, INPUT_DOCUMENT

if __name__ == "__main__":
    artifacts = ARTIFACTS_DIR
    ingest(INPUT_DOCUMENT, artifacts, extractor=DoclingExtractor(), pages=[5, 6, 7], out_file="00_pages.json")
    print("Docling extracted to artifacts/00_pages.json")