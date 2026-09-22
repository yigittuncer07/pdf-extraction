from pathlib import Path

ARTIFACTS_DIR = Path("artifacts")
INPUT_DOCUMENT = Path("ornek_dokuman.pdf")

# DEEPSEEK OCR STANDARD PROMPT
PROMPT = "<image>\n<|grounding|>Convert the document to markdown. "

CONFIG = {
    "pages": [5, 6, 7],
    "note": 11,
}
