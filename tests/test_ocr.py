import pytest

from pdf_to_epub.classify.image_coverage import ImageCoverageMetrics
from pdf_to_epub.classify.page_classifier import (
    BORN_DIGITAL_TEXT,
    IMAGE_ONLY_SCANNED,
    PageClassification,
)
from pdf_to_epub.classify.text_layer import TextLayerMetrics
from pdf_to_epub.extract.models import DocumentExtraction, PageModel
from pdf_to_epub.ocr import fallback
from pdf_to_epub.ocr.fallback import (
    OcrFallbackRequiredError,
    OcrUnavailableError,
    apply_ocr_fallback,
    ensure_ocr_not_required,
)


def test_ensure_ocr_not_required_fails_for_ocr_candidate_pages() -> None:
    with pytest.raises(OcrFallbackRequiredError, match="pages \\(2\\)"):
        ensure_ocr_not_required([_born_digital(), _image_only_scanned()])


def test_apply_ocr_fallback_skips_when_no_pages_need_ocr() -> None:
    extraction = DocumentExtraction(page_count=1, pages=[_page(_born_digital())])

    updated, report = apply_ocr_fallback(
        document=object(),
        extraction=extraction,
        classifications=[_born_digital()],
    )

    assert updated == extraction
    assert report.attempted_pages == []
    assert report.skipped_pages == [1]
    assert "ocr_candidate_pages:0" in report.diagnostics


def test_apply_ocr_fallback_requires_local_tesseract(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(fallback.shutil, "which", lambda _command: None)
    extraction = DocumentExtraction(page_count=1, pages=[_page(_image_only_scanned())])

    with pytest.raises(OcrUnavailableError, match="local command is unavailable"):
        apply_ocr_fallback(
            document=object(),
            extraction=extraction,
            classifications=[_image_only_scanned()],
        )


def test_tesseract_tsv_words_convert_to_extracted_block() -> None:
    tsv = "\n".join(
        [
            "level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext",
            "5\t1\t1\t1\t1\t1\t100\t200\t40\t10\t95.0\tHello",
            "5\t1\t1\t1\t1\t2\t150\t200\t50\t10\t85.0\tworld",
            "5\t1\t1\t1\t2\t1\t100\t240\t45\t10\t90.0\tAgain",
        ]
    )

    words = fallback._parse_tesseract_tsv(tsv, scale=0.5)
    block = fallback._words_to_block(words, page_number=3)

    assert block is not None
    assert block.id == "p3-ocr0"
    assert block.text == "Hello world\nAgain"
    assert block.bbox == (50.0, 100.0, 100.0, 125.0)
    assert block.confidence == 0.9
    assert [line.text for line in block.lines] == ["Hello world", "Again"]


def _page(classification: PageClassification) -> PageModel:
    return PageModel(
        page_number=1,
        width=300,
        height=400,
        rotation=0,
        classification=classification,
    )


def _born_digital() -> PageClassification:
    return PageClassification(
        category=BORN_DIGITAL_TEXT,
        has_text_layer=True,
        direct_extraction_recommended=True,
        ocr_recommended_later=False,
        confidence=0.92,
        text=TextLayerMetrics(
            char_count=100,
            non_whitespace_char_count=90,
            word_count=20,
            replacement_char_count=0,
            replacement_char_ratio=0,
            sample="",
        ),
        images=ImageCoverageMetrics(
            image_count=0,
            image_area_ratio=0,
            full_page_image=False,
        ),
    )


def _image_only_scanned() -> PageClassification:
    return PageClassification(
        category=IMAGE_ONLY_SCANNED,
        has_text_layer=False,
        direct_extraction_recommended=False,
        ocr_recommended_later=True,
        confidence=0.78,
        text=TextLayerMetrics(
            char_count=0,
            non_whitespace_char_count=0,
            word_count=0,
            replacement_char_count=0,
            replacement_char_ratio=0,
            sample="",
        ),
        images=ImageCoverageMetrics(
            image_count=1,
            image_area_ratio=1.0,
            full_page_image=True,
        ),
    )
