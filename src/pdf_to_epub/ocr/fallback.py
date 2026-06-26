"""Conditional local OCR fallback for textless pages."""

from __future__ import annotations

import csv
import shutil
import subprocess
from dataclasses import dataclass, replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Optional

from pdf_to_epub.classify.page_classifier import PageClassification
from pdf_to_epub.extract.models import (
    BBox,
    DocumentExtraction,
    ExtractedBlock,
    PageModel,
    StyleFeatures,
    TextLine,
)
from pdf_to_epub.ocr.models import OcrDocumentReport, OcrPageReport

DEFAULT_OCR_DPI = 300
DEFAULT_OCR_LANGUAGE = "eng"
DEFAULT_OCR_PSM = 6
MAX_OCR_WORKERS = 2
MIN_OCR_WORD_CONFIDENCE = 0.0


class OcrFallbackError(RuntimeError):
    """Base OCR fallback error."""


class OcrFallbackRequiredError(OcrFallbackError):
    """Raised when OCR candidate pages are present but OCR is disabled."""


class OcrUnavailableError(OcrFallbackError):
    """Raised when the configured local OCR command is unavailable."""


@dataclass(frozen=True)
class OcrConfig:
    language: str = DEFAULT_OCR_LANGUAGE
    dpi: int = DEFAULT_OCR_DPI
    max_workers: int = 1
    command: str = "tesseract"
    psm: int = DEFAULT_OCR_PSM
    tessdata_dir: Optional[Path] = None

    def normalized(self) -> OcrConfig:
        workers = min(max(int(self.max_workers), 1), MAX_OCR_WORKERS)
        dpi = max(int(self.dpi), 72)
        return replace(
            self,
            dpi=dpi,
            max_workers=workers,
            tessdata_dir=self.tessdata_dir or _infer_tessdata_dir(self.command),
        )


@dataclass(frozen=True)
class _OcrWord:
    text: str
    bbox: BBox
    confidence: float
    line_key: tuple[int, int, int]


def ocr_candidate_pages(classifications: list[PageClassification]) -> list[int]:
    return [
        index + 1
        for index, classification in enumerate(classifications)
        if classification.ocr_recommended_later
    ]


def ensure_ocr_not_required(classifications: list[PageClassification]) -> None:
    candidate_pages = ocr_candidate_pages(classifications)
    if candidate_pages:
        formatted = ", ".join(str(page) for page in candidate_pages)
        raise OcrFallbackRequiredError(
            "OCR fallback is required for textless/image-only pages "
            f"({formatted}) but is disabled; rerun with --enable-ocr and a local "
            "Tesseract installation, or provide a born-digital PDF"
        )


def apply_ocr_fallback(
    document: Any,
    extraction: DocumentExtraction,
    classifications: list[PageClassification],
    config: Optional[OcrConfig] = None,
) -> tuple[DocumentExtraction, OcrDocumentReport]:
    config = (config or OcrConfig()).normalized()
    candidate_pages = ocr_candidate_pages(classifications)
    diagnostics = [f"ocr_worker_cap:{config.max_workers}", f"ocr_dpi:{config.dpi}"]
    if not candidate_pages:
        return extraction, OcrDocumentReport(
            page_count=extraction.page_count,
            skipped_pages=list(range(1, extraction.page_count + 1)),
            diagnostics=[*diagnostics, "ocr_candidate_pages:0"],
        )

    if shutil.which(config.command) is None:
        raise OcrUnavailableError(
            f"OCR fallback requested, but local command is unavailable: {config.command}"
        )

    page_reports: list[OcrPageReport] = []
    updated_pages = list(extraction.pages)
    with TemporaryDirectory(prefix="pdf-to-epub-ocr-") as temp_dir:
        temp_path = Path(temp_dir)
        for page_number in candidate_pages:
            page = document.load_page(page_number - 1)
            block, report = _ocr_page(page, page_number, temp_path, config)
            page_reports.append(report)
            if block is None:
                raise OcrFallbackError(
                    f"OCR fallback produced no text for page {page_number}; refusing "
                    "to continue with incomplete extraction"
                )
            updated_pages[page_number - 1] = _merge_ocr_block(
                updated_pages[page_number - 1],
                block,
                report,
            )

    skipped_pages = [
        page_number
        for page_number in range(1, extraction.page_count + 1)
        if page_number not in candidate_pages
    ]
    document_report = OcrDocumentReport(
        page_count=extraction.page_count,
        attempted_pages=candidate_pages,
        skipped_pages=skipped_pages,
        pages=page_reports,
        diagnostics=[*diagnostics, f"ocr_candidate_pages:{len(candidate_pages)}"],
    )
    return (
        replace(
            extraction,
            pages=updated_pages,
            diagnostics=[*extraction.diagnostics, *_report_diagnostics(document_report)],
        ),
        document_report,
    )


def _ocr_page(
    page: Any,
    page_number: int,
    temp_path: Path,
    config: OcrConfig,
) -> tuple[Optional[ExtractedBlock], OcrPageReport]:
    image_path = temp_path / f"page-{page_number:06d}.png"
    try:
        pixmap = page.get_pixmap(dpi=config.dpi, alpha=False)
        pixmap.save(image_path)
    except Exception as exc:  # pragma: no cover - exact PyMuPDF exception varies.
        raise OcrFallbackError(f"failed to rasterize page {page_number} for OCR: {exc}") from exc

    command = [
        config.command,
        str(image_path),
        "stdout",
        "--psm",
        str(config.psm),
        "-l",
        config.language,
        "tsv",
    ]
    if config.tessdata_dir is not None:
        command[3:3] = ["--tessdata-dir", str(config.tessdata_dir)]
    try:
        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
        )
    except OSError as exc:
        raise OcrUnavailableError(f"failed to run OCR command {config.command}: {exc}") from exc

    if completed.returncode != 0:
        stderr = completed.stderr.strip() or "no stderr"
        raise OcrFallbackError(f"OCR command failed on page {page_number}: {stderr}")

    words = _parse_tesseract_tsv(completed.stdout, scale=72.0 / config.dpi)
    block = _words_to_block(words, page_number)
    confidence = None if block is None else block.confidence
    return block, OcrPageReport(
        source_page=page_number,
        status="ocr_text_extracted" if block else "ocr_no_text",
        word_count=len(words),
        confidence=confidence,
        diagnostics=["local_tesseract_tsv"],
    )


def _parse_tesseract_tsv(tsv: str, scale: float) -> list[_OcrWord]:
    words: list[_OcrWord] = []
    reader = csv.DictReader(StringIO(tsv), delimiter="\t")
    for row in reader:
        if row.get("level") != "5":
            continue
        text = (row.get("text") or "").strip()
        if not text:
            continue
        confidence = _optional_float(row.get("conf"))
        if confidence is None or confidence < MIN_OCR_WORD_CONFIDENCE:
            continue
        left = _required_float(row.get("left")) * scale
        top = _required_float(row.get("top")) * scale
        width = _required_float(row.get("width")) * scale
        height = _required_float(row.get("height")) * scale
        words.append(
            _OcrWord(
                text=text,
                bbox=_round_bbox((left, top, left + width, top + height)),
                confidence=confidence / 100.0,
                line_key=(
                    _required_int(row.get("block_num")),
                    _required_int(row.get("par_num")),
                    _required_int(row.get("line_num")),
                ),
            )
        )
    return words


def _words_to_block(words: list[_OcrWord], page_number: int) -> Optional[ExtractedBlock]:
    if not words:
        return None

    lines: list[TextLine] = []
    for line_key in sorted({word.line_key for word in words}):
        line_words = [word for word in words if word.line_key == line_key]
        lines.append(
            TextLine(
                text=" ".join(word.text for word in line_words),
                bbox=_union_bbox([word.bbox for word in line_words]),
            )
        )

    text = "\n".join(line.text for line in lines).strip()
    confidence = round(sum(word.confidence for word in words) / len(words), 4)
    return ExtractedBlock(
        id=f"p{page_number}-ocr0",
        type="text",
        bbox=_union_bbox([line.bbox for line in lines]),
        source_page=page_number,
        text=text,
        lines=lines,
        style_features=StyleFeatures(),
        confidence=confidence,
    )


def _merge_ocr_block(
    page: PageModel,
    block: ExtractedBlock,
    report: OcrPageReport,
) -> PageModel:
    non_text_blocks = [existing for existing in page.blocks if existing.type != "text"]
    diagnostics = [
        *page.diagnostics,
        "ocr_fallback_applied",
        f"ocr_words:{report.word_count}",
    ]
    if report.confidence is not None:
        diagnostics.append(f"ocr_confidence:{report.confidence:.4f}")
    return replace(page, blocks=[block, *non_text_blocks], diagnostics=diagnostics)


def _report_diagnostics(report: OcrDocumentReport) -> list[str]:
    diagnostics = [
        *report.diagnostics,
        "ocr_attempted_pages:" + ",".join(str(page) for page in report.attempted_pages),
    ]
    for page in report.pages:
        diagnostics.append(f"ocr_page:{page.source_page}:words:{page.word_count}")
        if page.confidence is not None:
            diagnostics.append(f"ocr_page:{page.source_page}:confidence:{page.confidence:.4f}")
    return diagnostics


def _union_bbox(boxes: list[BBox]) -> BBox:
    return _round_bbox(
        (
            min(box[0] for box in boxes),
            min(box[1] for box in boxes),
            max(box[2] for box in boxes),
            max(box[3] for box in boxes),
        )
    )


def _round_bbox(bbox: BBox) -> BBox:
    return tuple(round(float(value), 3) for value in bbox)  # type: ignore[return-value]


def _infer_tessdata_dir(command: str) -> Optional[Path]:
    resolved = shutil.which(command)
    if resolved is None:
        return None
    executable = Path(resolved)
    candidates = [
        executable.parent.parent / "share" / "tessdata",
        executable.parent.parent / "share" / "tesseract-ocr" / "5" / "tessdata",
        executable.parent.parent / "share" / "tesseract" / "tessdata",
    ]
    for candidate in candidates:
        if (candidate / "eng.traineddata").is_file():
            return candidate
    return None


def _optional_float(value: Optional[str]) -> Optional[float]:
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _required_float(value: Optional[str]) -> float:
    if value is None:
        return 0.0
    return float(value)


def _required_int(value: Optional[str]) -> int:
    if value is None:
        return 0
    return int(value)
