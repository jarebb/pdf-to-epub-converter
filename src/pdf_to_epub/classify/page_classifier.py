"""Page-level classification for direct extraction vs later OCR fallback."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from pdf_to_epub.classify.image_coverage import (
    ImageCoverageMetrics,
    extract_image_coverage_metrics,
)
from pdf_to_epub.classify.text_layer import TextLayerMetrics, extract_text_layer_metrics

BORN_DIGITAL_TEXT = "born_digital_text"
IMAGE_ONLY_SCANNED = "image_only_scanned"
MIXED_TEXT_AND_IMAGES = "mixed_text_and_images"
LOW_CONFIDENCE_TEXT_LAYER = "low_confidence_text_layer"
BLANK_OR_UNKNOWN = "blank_or_unknown"

MIN_MEANINGFUL_CHARS = 25
MIN_MEANINGFUL_WORDS = 5
SIGNIFICANT_IMAGE_AREA_RATIO = 0.05
HIGH_IMAGE_AREA_RATIO = 0.60


@dataclass(frozen=True)
class PageClassification:
    category: str
    has_text_layer: bool
    direct_extraction_recommended: bool
    ocr_recommended_later: bool
    confidence: float
    text: TextLayerMetrics
    images: ImageCoverageMetrics
    reasons: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "category": self.category,
            "has_text_layer": self.has_text_layer,
            "direct_extraction_recommended": self.direct_extraction_recommended,
            "ocr_recommended_later": self.ocr_recommended_later,
            "confidence": self.confidence,
            "text": self.text.to_dict(),
            "images": self.images.to_dict(),
            "reasons": self.reasons,
        }


@dataclass(frozen=True)
class ClassificationSummary:
    page_count: int
    categories: dict[str, int]
    pages_with_text_layer: int
    pages_requiring_ocr_later: int
    pages_recommended_for_direct_extraction: int

    def to_dict(self) -> dict[str, object]:
        return {
            "page_count": self.page_count,
            "categories": self.categories,
            "pages_with_text_layer": self.pages_with_text_layer,
            "pages_requiring_ocr_later": self.pages_requiring_ocr_later,
            "pages_recommended_for_direct_extraction": (
                self.pages_recommended_for_direct_extraction
            ),
        }


def classify_page(page: Any) -> PageClassification:
    text = extract_text_layer_metrics(page)
    images = extract_image_coverage_metrics(page)
    return classify_page_metrics(text, images)


def classify_document_pages(
    document: Any,
) -> tuple[list[PageClassification], ClassificationSummary]:
    classifications = [
        classify_page(document.load_page(index)) for index in range(document.page_count)
    ]
    counts = Counter(classification.category for classification in classifications)
    summary = ClassificationSummary(
        page_count=len(classifications),
        categories=dict(sorted(counts.items())),
        pages_with_text_layer=sum(1 for item in classifications if item.has_text_layer),
        pages_requiring_ocr_later=sum(1 for item in classifications if item.ocr_recommended_later),
        pages_recommended_for_direct_extraction=sum(
            1 for item in classifications if item.direct_extraction_recommended
        ),
    )
    return classifications, summary


def classify_page_metrics(
    text: TextLayerMetrics,
    images: ImageCoverageMetrics,
) -> PageClassification:
    reasons: list[str] = []
    has_meaningful_text = (
        text.word_count >= MIN_MEANINGFUL_WORDS
        or text.non_whitespace_char_count >= MIN_MEANINGFUL_CHARS
    )
    has_any_text = text.word_count > 0 or text.non_whitespace_char_count > 0
    has_significant_images = images.image_area_ratio >= SIGNIFICANT_IMAGE_AREA_RATIO
    has_high_image_coverage = images.image_area_ratio >= HIGH_IMAGE_AREA_RATIO

    if has_meaningful_text and has_significant_images:
        reasons.extend(["meaningful_text_layer", "significant_image_coverage"])
        return PageClassification(
            category=MIXED_TEXT_AND_IMAGES,
            has_text_layer=True,
            direct_extraction_recommended=True,
            ocr_recommended_later=False,
            confidence=0.88,
            text=text,
            images=images,
            reasons=reasons,
        )

    if has_meaningful_text:
        reasons.append("meaningful_text_layer")
        if images.image_count:
            reasons.append("minor_image_content")
        return PageClassification(
            category=BORN_DIGITAL_TEXT,
            has_text_layer=True,
            direct_extraction_recommended=True,
            ocr_recommended_later=False,
            confidence=0.92,
            text=text,
            images=images,
            reasons=reasons,
        )

    if has_any_text:
        reasons.append("sparse_text_layer")
        if images.image_count:
            reasons.append("image_content_present")
        return PageClassification(
            category=LOW_CONFIDENCE_TEXT_LAYER,
            has_text_layer=True,
            direct_extraction_recommended=True,
            ocr_recommended_later=False,
            confidence=0.58,
            text=text,
            images=images,
            reasons=reasons,
        )

    if images.image_count and (has_high_image_coverage or images.full_page_image):
        reasons.append("no_text_layer")
        reasons.append("high_image_coverage")
        return PageClassification(
            category=IMAGE_ONLY_SCANNED,
            has_text_layer=False,
            direct_extraction_recommended=False,
            ocr_recommended_later=True,
            confidence=0.78,
            text=text,
            images=images,
            reasons=reasons,
        )

    if images.image_count:
        reasons.append("no_text_layer")
        reasons.append("image_content_present")
        return PageClassification(
            category=IMAGE_ONLY_SCANNED,
            has_text_layer=False,
            direct_extraction_recommended=False,
            ocr_recommended_later=True,
            confidence=0.62,
            text=text,
            images=images,
            reasons=reasons,
        )

    reasons.append("no_text_or_image_content")
    return PageClassification(
        category=BLANK_OR_UNKNOWN,
        has_text_layer=False,
        direct_extraction_recommended=False,
        ocr_recommended_later=False,
        confidence=0.74,
        text=text,
        images=images,
        reasons=reasons,
    )
