import base64
from pathlib import Path

import fitz

from pdf_to_epub.visuals.asset_extractor import extract_visual_assets

PNG_1X1 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/p9sAAAAASUVORK5CYII="
)


def test_extract_visual_assets_deduplicates_embedded_images(tmp_path: Path) -> None:
    pdf_path = tmp_path / "images.pdf"
    output_dir = tmp_path / "visuals"
    document = fitz.open()
    image_bytes = base64.b64decode(PNG_1X1)
    for _page_number in range(2):
        page = document.new_page(width=200, height=200)
        page.insert_image(fitz.Rect(10, 10, 40, 40), stream=image_bytes)
    document.save(pdf_path)
    document.close()

    with fitz.open(pdf_path) as reopened:
        manifest = extract_visual_assets(reopened, output_dir)

    assert len(manifest.assets) == 1
    assert len(manifest.placements) == 2
    assert manifest.assets[0].kind == "embedded_image"
    assert manifest.assets[0].source_pages == [1, 2]
    assert (output_dir / manifest.assets[0].file_name).is_file()


def test_extract_visual_assets_rasterizes_vector_diagrams(tmp_path: Path) -> None:
    pdf_path = tmp_path / "diagram.pdf"
    output_dir = tmp_path / "visuals"
    document = fitz.open()
    page = document.new_page(width=300, height=300)
    page.draw_rect(fitz.Rect(50, 50, 180, 130), color=(0, 0, 0), fill=(0.9, 0.9, 0.9))
    page.draw_line(fitz.Point(60, 70), fitz.Point(170, 110))
    document.save(pdf_path)
    document.close()

    with fitz.open(pdf_path) as reopened:
        manifest = extract_visual_assets(reopened, output_dir, diagram_dpi=72)

    diagram_assets = [asset for asset in manifest.assets if asset.kind == "vector_diagram"]
    diagram_placements = [
        placement for placement in manifest.placements if placement.kind == "vector_diagram"
    ]
    assert len(diagram_assets) == 1
    assert len(diagram_placements) == 1
    assert diagram_placements[0].role == "diagram"
    assert (output_dir / diagram_assets[0].file_name).is_file()


def test_extract_visual_assets_caps_large_embedded_images(tmp_path: Path) -> None:
    pdf_path = tmp_path / "large-image.pdf"
    output_dir = tmp_path / "visuals"
    pixmap = fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 3301, 4), 0)
    pixmap.clear_with(255)
    image_bytes = pixmap.tobytes("png")

    document = fitz.open()
    page = document.new_page(width=300, height=100)
    page.insert_image(fitz.Rect(10, 10, 290, 30), stream=image_bytes)
    document.save(pdf_path)
    document.close()

    with fitz.open(pdf_path) as reopened:
        manifest = extract_visual_assets(reopened, output_dir)

    assert len(manifest.assets) == 1
    assert max(manifest.assets[0].width, manifest.assets[0].height) <= 3200
    assert "large_visual_asset:3301x4" in manifest.assets[0].diagnostics
    assert any(item.startswith("resized_to:") for item in manifest.assets[0].diagnostics)
