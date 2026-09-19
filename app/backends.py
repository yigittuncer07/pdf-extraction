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


class TableExtractor(ABC):
    @abstractmethod
    def extract(self, pdf: Path, pages: list[int] | None = None) -> list[dict]:
        """Extract pages returning a list of dicts: {'page': int, 'text': str, 'tables': list[list[list[str]]]}."""


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
            {"page": p, "text": "\n".join(data["text"]), "tables": data["tables"]}
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
            {"page": p, "text": "\n".join(data["text"]), "tables": data["tables"]}
            for p, data in sorted(page_map.items())
        ]