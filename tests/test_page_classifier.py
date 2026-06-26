from pdf_to_epub.classify.image_coverage import ImageCoverageMetrics
from pdf_to_epub.classify.page_classifier import (
    BLANK_OR_UNKNOWN,
    BORN_DIGITAL_TEXT,
    IMAGE_ONLY_SCANNED,
    LOW_CONFIDENCE_TEXT_LAYER,
    MIXED_TEXT_AND_IMAGES,
    classify_page_metrics,
)
from pdf_to_epub.classify.text_layer import TextLayerMetrics


def test_classifies_meaningful_text_as_born_digital() -> None:
    classification = classify_page_metrics(
        text=_text(word_count=80, non_whitespace_char_count=420),
        images=_images(),
    )

    assert classification.category == BORN_DIGITAL_TEXT
    assert classification.has_text_layer
    assert classification.direct_extraction_recommended
    assert not classification.ocr_recommended_later


def test_classifies_meaningful_text_with_significant_images_as_mixed() -> None:
    classification = classify_page_metrics(
        text=_text(word_count=120, non_whitespace_char_count=700),
        images=_images(image_count=2, image_area_ratio=0.22),
    )

    assert classification.category == MIXED_TEXT_AND_IMAGES
    assert classification.has_text_layer
    assert classification.direct_extraction_recommended
    assert not classification.ocr_recommended_later


def test_classifies_sparse_text_layer_without_ocr() -> None:
    classification = classify_page_metrics(
        text=_text(word_count=2, non_whitespace_char_count=18),
        images=_images(),
    )

    assert classification.category == LOW_CONFIDENCE_TEXT_LAYER
    assert classification.has_text_layer
    assert classification.direct_extraction_recommended
    assert not classification.ocr_recommended_later


def test_classifies_full_page_image_without_text_as_ocr_candidate() -> None:
    classification = classify_page_metrics(
        text=_text(),
        images=_images(image_count=1, image_area_ratio=1.0, full_page_image=True),
    )

    assert classification.category == IMAGE_ONLY_SCANNED
    assert not classification.has_text_layer
    assert not classification.direct_extraction_recommended
    assert classification.ocr_recommended_later


def test_classifies_empty_page_as_blank_or_unknown() -> None:
    classification = classify_page_metrics(text=_text(), images=_images())

    assert classification.category == BLANK_OR_UNKNOWN
    assert not classification.has_text_layer
    assert not classification.direct_extraction_recommended
    assert not classification.ocr_recommended_later


def _text(
    *,
    word_count: int = 0,
    non_whitespace_char_count: int = 0,
) -> TextLayerMetrics:
    return TextLayerMetrics(
        char_count=non_whitespace_char_count,
        non_whitespace_char_count=non_whitespace_char_count,
        word_count=word_count,
        replacement_char_count=0,
        replacement_char_ratio=0,
        sample="",
    )


def _images(
    *,
    image_count: int = 0,
    image_area_ratio: float = 0,
    full_page_image: bool = False,
) -> ImageCoverageMetrics:
    return ImageCoverageMetrics(
        image_count=image_count,
        image_area_ratio=image_area_ratio,
        full_page_image=full_page_image,
    )
