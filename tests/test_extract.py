import base64
from pathlib import Path

import fitz

from pdf_to_epub.extract.page_extractor import extract_document_model, extract_page_model

PNG_1X1 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def test_extract_page_model_text_blocks_and_style_features(tmp_path: Path) -> None:
    pdf_path = tmp_path / "text.pdf"
    document = fitz.open()
    page = document.new_page(width=300, height=400)
    page.insert_text((50, 50), "HELLO WORLD", fontsize=12, fontname="helv")
    page.insert_text((50, 80), "print('hi')", fontsize=10, fontname="cour")
    page.draw_rect(fitz.Rect(40, 100, 80, 130))
    document.save(pdf_path)
    document.close()

    with fitz.open(pdf_path) as reopened:
        model = extract_page_model(reopened.load_page(0), page_number=1)

    text_blocks = [block for block in model.blocks if block.type == "text"]
    assert model.page_number == 1
    assert model.width == 300
    assert len(text_blocks) == 2
    assert text_blocks[0].text == "HELLO WORLD"
    assert text_blocks[0].style_features.font_size == 12
    assert text_blocks[0].style_features.all_caps
    assert text_blocks[1].style_features.monospace
    assert model.drawings
    assert "vector_drawings_present" in model.diagnostics


def test_extract_document_model_image_blocks(tmp_path: Path) -> None:
    pdf_path = tmp_path / "image.pdf"
    document = fitz.open()
    page = document.new_page(width=200, height=200)
    page.insert_image(
        fitz.Rect(10, 10, 30, 30),
        stream=base64.b64decode(PNG_1X1),
    )
    document.save(pdf_path)
    document.close()

    with fitz.open(pdf_path) as reopened:
        extraction = extract_document_model(reopened)

    assert extraction.page_count == 1
    assert len(extraction.pages) == 1
    assert len(extraction.pages[0].images) == 1
    assert extraction.pages[0].images[0].asset_ref.startswith("images/p1-img")
    assert extraction.pages[0].blocks[0].type == "image"
