from dataclasses import replace
from typing import Optional

from pdf_to_epub.classify.image_coverage import ImageCoverageMetrics
from pdf_to_epub.classify.page_classifier import BORN_DIGITAL_TEXT, PageClassification
from pdf_to_epub.classify.text_layer import TextLayerMetrics
from pdf_to_epub.extract.models import (
    DocumentExtraction,
    ExtractedBlock,
    PageModel,
    StyleFeatures,
    TextLine,
)
from pdf_to_epub.reconstruct.reading_order import reconstruct_reading_order


def test_reconstruct_removes_repeated_artifacts_and_page_numbers() -> None:
    extraction = DocumentExtraction(
        page_count=3,
        pages=[
            _page(1, [_text("h1", "Book Title", (40, 20, 200, 30)), _text("b1", "Body 1")]),
            _page(2, [_text("h2", "Book Title", (40, 20, 200, 30)), _text("b2", "Body 2")]),
            _page(3, [_text("h3", "Book Title", (40, 20, 200, 30)), _text("b3", "Body 3")]),
        ],
    )
    pages = [
        _replace_blocks(
            page,
            [
                *page.blocks,
                _text(f"n{page.page_number}", str(page.page_number), (140, 780, 160, 790)),
            ],
        )
        for page in extraction.pages
    ]

    reconstruction = reconstruct_reading_order(DocumentExtraction(page_count=3, pages=pages))

    assert [block.text for block in reconstruction.blocks if block.type == "text"] == [
        "Body 1",
        "Body 2",
        "Body 3",
    ]
    assert len([block for block in reconstruction.blocks if block.type == "page_break"]) == 3
    assert len(reconstruction.removed_artifacts) == 6
    assert {artifact.reason for artifact in reconstruction.removed_artifacts} == {
        "repeated_top_artifact",
        "bottom_page_number",
    }


def test_reconstruct_normalizes_ligatures_and_dehyphenates_line_breaks() -> None:
    block = _text(
        "b1",
        "of\ufb01ce exam-\nple",
        lines=[
            TextLine(text="of\ufb01ce exam-", bbox=(40, 100, 120, 112)),
            TextLine(text="ple", bbox=(40, 114, 55, 126)),
        ],
    )
    extraction = DocumentExtraction(page_count=1, pages=[_page(1, [block])])

    reconstruction = reconstruct_reading_order(extraction)
    text_blocks = [block for block in reconstruction.blocks if block.type == "text"]

    assert text_blocks[0].text == "office example"
    assert "dehyphenated_line_break" in text_blocks[0].diagnostics


def test_reconstruct_keeps_single_page_top_text() -> None:
    extraction = DocumentExtraction(
        page_count=1,
        pages=[_page(1, [_text("h1", "Chapter 1", (40, 20, 200, 40))])],
    )

    reconstruction = reconstruct_reading_order(extraction)

    assert [block.text for block in reconstruction.blocks if block.type == "text"] == ["Chapter 1"]
    assert reconstruction.removed_artifacts == []


def test_reconstruct_attaches_nearby_figure_caption() -> None:
    image = ExtractedBlock(
        id="img1",
        type="image",
        bbox=(40, 100, 160, 160),
        source_page=1,
        text="",
        asset_ref="images/img1.png",
    )
    caption = _text("cap1", "Figure 1. Build pipeline", (40, 170, 220, 185))
    extraction = DocumentExtraction(page_count=1, pages=[_page(1, [image, caption])])

    reconstruction = reconstruct_reading_order(extraction)
    figure = next(block for block in reconstruction.blocks if block.type == "figure")
    caption_block = next(block for block in reconstruction.blocks if block.type == "caption")

    assert figure.caption_block_id == caption_block.id
    assert caption_block.attached_to == figure.id


def _page(page_number: int, blocks: list[ExtractedBlock]) -> PageModel:
    return PageModel(
        page_number=page_number,
        width=400,
        height=800,
        rotation=0,
        classification=_classification(),
        blocks=[replace(block, source_page=page_number) for block in blocks],
    )


def _replace_blocks(page: PageModel, blocks: list[ExtractedBlock]) -> PageModel:
    return PageModel(
        page_number=page.page_number,
        width=page.width,
        height=page.height,
        rotation=page.rotation,
        classification=page.classification,
        blocks=[replace(block, source_page=page.page_number) for block in blocks],
        images=page.images,
        drawings=page.drawings,
        diagnostics=page.diagnostics,
    )


def _text(
    block_id: str,
    text: str,
    bbox: tuple[float, float, float, float] = (40, 100, 220, 125),
    lines: Optional[list[TextLine]] = None,
) -> ExtractedBlock:
    return ExtractedBlock(
        id=block_id,
        type="text",
        bbox=bbox,
        source_page=1,
        text=text,
        lines=lines or [TextLine(text=text, bbox=bbox)],
        style_features=StyleFeatures(font_size=10),
    )


def _classification() -> PageClassification:
    return PageClassification(
        category=BORN_DIGITAL_TEXT,
        has_text_layer=True,
        direct_extraction_recommended=True,
        ocr_recommended_later=False,
        confidence=0.95,
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
