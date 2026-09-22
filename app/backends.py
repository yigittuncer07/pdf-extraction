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

import json
import tempfile

import torch
from pdf2image import convert_from_path, pdfinfo_from_path
from transformers import AutoModel, AutoTokenizer

from .config import PROMPT
from .helper import _parse_page

class TableExtractor(ABC):
    @abstractmethod
    def extract(self, pdf: Path, pages: list[int] | None = None) -> list[dict]:
        """"Extract pages: {'page': int, 'text': str, 'tables': [...], 'headings': [str]}."""


class DoclingVlmExtractor(TableExtractor):
    """Uses Docling's native Granite-Docling VLM"""

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
                page_map.setdefault(p, {"page": p, "text": [], "tables": [], "indents": []})["text"].append(item.text)

        for table in doc.tables:
            p = table.prov[0].page_no if table.prov else 1
            df = table.export_to_dataframe().fillna("")

            if hasattr(df.columns, "levels"):  # MultiIndex
                header_row = [" ".join(str(part) for part in col if str(part).strip())
                              for col in df.columns]
            else:
                header_row = [str(col) for col in df.columns]

            # extract index positions. Deepseek does not provide this information, but Docling does. 
            # later on we will splice the indents from Docling's output into Deepseek's output, so that we can use them for table normalization.
            indents = [None] * (table.data.num_rows + 1)
            for cell in table.data.table_cells:
                if cell.start_col_offset_idx == 0 and cell.bbox:
                    indents[cell.start_row_offset_idx] = round(cell.bbox.l, 1)

            entry = page_map.setdefault(p, {"page": p, "text": [], "tables": [], "indents": []})
            entry["tables"].append([header_row] + df.values.tolist())
            entry["indents"].append(indents)

        return [
            {"page": p, "text": "\n".join(data["text"]), "tables": data["tables"],
            "headings": [""] * len(data["tables"]), "indents": data["indents"]}
            for p, data in sorted(page_map.items())
        ]


class DeepSeekExtractor(TableExtractor):
    """DeepSeek-OCR-2, one page image at a time.

    Docling's table model loses cells on this scan, most damagingly the note
    reference "11" on the income statement, the we need. This
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
        if pages is None or pages == []:
            pages = range(1, pdfinfo_from_path(str(pdf))["Pages"] + 1)

        out = []
        for page in pages:
            with tempfile.TemporaryDirectory() as tmp:
                work = Path(tmp)
                image = work / f"page_{page:03d}.png"
                convert_from_path(str(pdf), dpi=self.dpi, first_page=page, last_page=page)[0].save(image)
                parsed = _parse_page(self._infer(image, work))
            out.append({"page": page, **parsed})
            print(f"page {page}: {len(parsed['tables'])} tables")
        return out


def ingest(
    pdf: Path,
    out_dir: Path,
    extractor: TableExtractor,
    pages: list[int] | None = None,
    out_file: str = "01_pages.json",
) -> list[dict]:
    out_dir.mkdir(parents=True, exist_ok=True)
    pages_data = extractor.extract(pdf, pages)

    (out_dir / out_file).write_text(
        json.dumps(pages_data, ensure_ascii=False, indent=2)
    )
    return pages_data