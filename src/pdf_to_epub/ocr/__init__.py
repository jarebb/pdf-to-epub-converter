"""Conditional local OCR fallback support."""

from pdf_to_epub.ocr.fallback import (
    OcrConfig,
    OcrFallbackError,
    OcrFallbackRequiredError,
    OcrUnavailableError,
    apply_ocr_fallback,
    ensure_ocr_not_required,
    ocr_candidate_pages,
)
from pdf_to_epub.ocr.models import OcrDocumentReport, OcrPageReport

__all__ = [
    "OcrConfig",
    "OcrDocumentReport",
    "OcrFallbackError",
    "OcrFallbackRequiredError",
    "OcrPageReport",
    "OcrUnavailableError",
    "apply_ocr_fallback",
    "ensure_ocr_not_required",
    "ocr_candidate_pages",
]
