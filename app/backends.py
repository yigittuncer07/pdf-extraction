from abc import ABC, abstractmethod
from pathlib import Path

from docling.datamodel.base_models import InputFormat
from docling.datamodel.pipeline_options import (
    EasyOcrOptions,
    PdfPipelineOptions,
    TesseractCliOcrOptions,
)
from docling.document_converter import DocumentConverter, PdfFormatOption
from docling.pipeline.vlm_pipeline import VlmPipeline

import html
import re
import tempfile

import torch
from pdf2image import convert_from_path, pdfinfo_from_path
from transformers import AutoModel, AutoTokenizer

PROMPT = "<image>\n<|grounding|>Convert the document to markdown. "

TABLE_RE = re.compile(r"<table.*?>.*?</table>", re.DOTALL | re.I)
ROW_RE = re.compile(r"<tr.*?>(.*?)</tr>", re.DOTALL | re.I)
CELL_RE = re.compile(r"<t[dh].*?>(.*?)</t[dh]>", re.DOTALL | re.I)
GROUNDING_RE = re.compile(r"<\|(ref|det)\|>.*?<\|/\1\|>", re.DOTALL)
HEADING_RE = re.compile(r"^#+\s*(.+?)\s*$", re.M)

class TableExtractor(ABC):
    @abstractmethod
    def extract(self, pdf: Path, pages: list[int] | None = None) -> list[dict]:
        """"Extract pages: {'page': int, 'text': str, 'tables': [...], 'headings': [str]}."""


class DoclingVlmExtractor(TableExtractor):
    """Uses Docling's native Granite-Docling VLM end-to-end (no external OCR engine)."""

    def __init__(self):
        self.converter = DocumentConverter(
            format_options={
                InputFormat.PDF: PdfFormatOption(
                    pipeline_cls=VlmPipeline,
                ),
            }
        )

    def extract(self, pdf: Path, pages: list[int] | None = None) -> list[dict]:
        kwargs = {"page_range": (min(pages), max(pages))} if pages else {}
        doc = self.converter.convert(str(pdf), **kwargs).document

        page_map: dict[int, dict] = {}

        for item in doc.texts:
            p = item.prov[0].page_no if item.prov else 1
            page_map.setdefault(p, {"page": p, "text": [], "tables": []})["text"].append(item.text)

        for table in doc.tables:
            p = table.prov[0].page_no if table.prov else 1
            grid = table.export_to_dataframe().fillna("").values.tolist()
            page_map.setdefault(p, {"page": p, "text": [], "tables": []})["tables"].append(grid)

        return [
            {"page": p, "text": "\n".join(data["text"]), "tables": data["tables"],
            "headings": [""] * len(data["tables"])}
            for p, data in sorted(page_map.items())
        ]


class DoclingExtractor(TableExtractor):
    def __init__(self, ocr: str = "easyocr", lang: list[str] | tuple[str, ...] | None = None):
        opts = PdfPipelineOptions()
        opts.do_ocr = True
        opts.do_table_structure = True

        lang_list = list(lang) if lang else (["tr"] if ocr == "easyocr" else ["tur"])

        if ocr == "easyocr":
            opts.ocr_options = EasyOcrOptions(lang=lang_list, force_full_page_ocr=True)
        elif ocr in ("tesseract", "tesseract_cli"):
            opts.ocr_options = TesseractCliOcrOptions(lang=lang_list, force_full_page_ocr=True)
        else:
            raise ValueError(f"Unsupported OCR engine: {ocr}")

        self.converter = DocumentConverter(
            format_options={InputFormat.PDF: PdfFormatOption(pipeline_options=opts)}
        )

    def extract(self, pdf: Path, pages: list[int] | None = None) -> list[dict]:
        kwargs = {"page_range": (min(pages), max(pages))} if pages else {}
        doc = self.converter.convert(str(pdf), **kwargs).document

        page_map: dict[int, dict] = {}

        for item in doc.texts:
            if item.prov:
                p = item.prov[0].page_no
                page_map.setdefault(p, {"page": p, "text": [], "tables": []})["text"].append(item.text)

        for table in doc.tables:
            p = table.prov[0].page_no
            grid = table.export_to_dataframe().fillna("").values.tolist()
            page_map.setdefault(p, {"page": p, "text": [], "tables": []})["tables"].append(grid)

        return [
            {"page": p, "text": "\n".join(data["text"]), "tables": data["tables"],
            "headings": [""] * len(data["tables"])}
            for p, data in sorted(page_map.items())
        ]


def _cell_text(raw: str) -> str:
    text = re.sub(r"<br\s*/?>", " ", raw, flags=re.I)
    text = re.sub(r"<.*?>", "", text)
    return re.sub(r"\s+", " ", html.unescape(text)).strip()


def _rows(table_html: str) -> list[list[str]]:
    """One list of cell texts per <tr>.

    colspan and rowspan are ignored on purpose. They are the least reliable
    thing the model emits -- it invents a colspan whenever a header label is
    typeset on two lines -- and honouring them is what pushes every body cell
    one column to the right. Counting <td> tags is stable.
    """
    out = []
    for row in ROW_RE.findall(table_html):
        cells = [_cell_text(c) for c in CELL_RE.findall(row)]
        if cells:
            out.append(cells)
    return out


def _fit(row: list[str], width: int) -> list[str]:
    """Force a row to `width` by shedding empty cells from the ends."""
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


def parse_page(raw: str) -> dict:
    """Model output -> {'text', 'tables', 'headings'}.

    `headings[i]` is the last markdown heading seen before `tables[i]`, so a
    page holding several tables can still tell them apart. Walking the raw
    output in order is the only place that association exists -- once text and
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


class DeepSeekExtractor(TableExtractor):
    """DeepSeek-OCR-2, one page image at a time.

    Docling's table model loses cells on this scan -- most damagingly the note
    reference "11" on the income statement, the one the task turns on. This
    model reads every note reference correctly; what it sometimes gets wrong is table
    structure, which is repairable here and only here.
    """

    def __init__(self, model_name: str = "deepseek-ai/DeepSeek-OCR-2", dpi: int = 200):
        self.model_name = model_name
        self.dpi = dpi
        self._model = None
        self._tokenizer = None

    def _load(self):
        if self._model is not None:
            return
        self._tokenizer = AutoTokenizer.from_pretrained(self.model_name, trust_remote_code=True)
        kwargs = dict(trust_remote_code=True, use_safetensors=True)
        try:
            model = AutoModel.from_pretrained(
                self.model_name, _attn_implementation="flash_attention_2", **kwargs
            )
        except Exception:
            model = AutoModel.from_pretrained(self.model_name, **kwargs)
        self._model = model.eval().cuda().to(torch.bfloat16)

    def _infer(self, image: Path, work_dir: Path) -> str:
        res = self._model.infer(
            self._tokenizer,
            prompt=PROMPT,
            image_file=str(image),
            output_path=str(work_dir),
            base_size=1024,
            image_size=768,
            crop_mode=True,
            save_results=True,
        )
        if isinstance(res, str) and res.strip():
            return res
        mmd = sorted(work_dir.glob("*.mmd"))
        return mmd[0].read_text(encoding="utf-8") if mmd else ""

    def extract(self, pdf: Path, pages: list[int] | None = None) -> list[dict]:
        self._load()
        if pages is None:
            pages = range(1, pdfinfo_from_path(str(pdf))["Pages"] + 1)

        out = []
        for page in pages:
            with tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                image = work / f"page_{page:03d}.png"
                convert_from_path(str(pdf), dpi=self.dpi, first_page=page, last_page=page)[0].save(image)
                parsed = parse_page(self._infer(image, work))
            out.append({"page": page, **parsed})
            print(f"page {page}: {len(parsed['tables'])} tables")
        return out