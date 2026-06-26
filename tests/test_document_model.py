from pdf_to_epub.document.builder import build_document_model
from pdf_to_epub.extract.models import StyleFeatures
from pdf_to_epub.reconstruct.models import OrderedBlock, ReadingOrderDocument
from pdf_to_epub.visuals.models import VisualAsset, VisualAssetManifest


def test_build_document_model_groups_sections_and_toc() -> None:
    reading_order = ReadingOrderDocument(
        page_count=2,
        blocks=[
            _block(0, "page_break", "", 1),
            _block(1, "text", "Chapter 1. Foundations", 1, font_size=18),
            _block(2, "text", "A body paragraph.", 1, font_size=10),
            _block(3, "code_block", "print('hello')", 1, font_size=9, monospace=True),
            _block(4, "page_break", "", 2),
            _block(5, "text", "Chapter 2. Delivery", 2, font_size=18),
            _block(6, "text", "Another body paragraph.", 2, font_size=10),
        ],
    )

    model = build_document_model(reading_order, metadata={"title": "Sample Book"})

    assert model.metadata["title"] == "Sample Book"
    assert model.metadata["language"] == "en"
    assert [section.title for section in model.sections] == [
        "Chapter 1. Foundations",
        "Chapter 2. Delivery",
    ]
    assert [entry.title for entry in model.toc] == [
        "Chapter 1. Foundations",
        "Chapter 2. Delivery",
    ]
    assert model.sections[0].blocks[0].type == "page_break"
    assert model.sections[0].blocks[1].type == "heading"
    assert model.sections[0].blocks[2].type == "paragraph"
    assert model.sections[0].blocks[3].type == "code_block"
    assert "document_block_type:heading:2" in model.diagnostics


def test_build_document_model_attaches_figure_caption_and_assets() -> None:
    reading_order = ReadingOrderDocument(
        page_count=1,
        blocks=[
            _block(0, "page_break", "", 1),
            _block(
                1,
                "figure",
                "",
                1,
                asset_ref="images/figure.png",
                caption_block_id="ord-000002",
            ),
            _block(
                2,
                "caption",
                "Figure 1. System architecture",
                1,
                attached_to="ord-000001",
            ),
        ],
    )
    manifest = VisualAssetManifest(
        output_dir="/tmp/assets",
        page_count=1,
        assets=[
            VisualAsset(
                id="asset-000001",
                kind="embedded_image",
                file_name="figure.png",
                media_type="image/png",
                width=120,
                height=80,
                byte_size=100,
                content_hash="abc",
                source_pages=[1],
            )
        ],
    )

    model = build_document_model(reading_order, visual_manifest=manifest)
    figure = next(
        block for section in model.sections for block in section.blocks if block.type == "figure"
    )

    assert len(model.assets) == 1
    assert model.assets[0].source_path == "/tmp/assets/figure.png"
    assert figure.asset_id == "asset-000001"
    assert figure.caption == "Figure 1. System architecture"
    assert all(
        block.text != "Figure 1. System architecture"
        for section in model.sections
        for block in section.blocks
    )


def test_build_document_model_groups_list_items_and_detects_blockquote() -> None:
    reading_order = ReadingOrderDocument(
        page_count=1,
        blocks=[
            _block(0, "page_break", "", 1),
            _block(1, "text", "Body paragraph", 1, indentation=40),
            _block(2, "text", "- First item", 1, indentation=40),
            _block(3, "text", "- Second item", 1, indentation=40),
            _block(4, "text", "Indented quotation", 1, indentation=90),
        ],
    )

    model = build_document_model(reading_order)
    blocks = model.sections[0].blocks
    list_block = next(block for block in blocks if block.type == "list")
    quote_block = next(block for block in blocks if block.type == "blockquote")

    assert [child.text for child in list_block.children] == ["First item", "Second item"]
    assert "list_inferred:unordered" in list_block.diagnostics
    assert quote_block.text == "Indented quotation"


def _block(
    reading_order: int,
    block_type: str,
    text: str,
    page: int,
    *,
    font_size: float = 10,
    monospace: bool = False,
    indentation: float = 40,
    asset_ref: str = "",
    attached_to: str = "",
    caption_block_id: str = "",
) -> OrderedBlock:
    return OrderedBlock(
        id=f"ord-{reading_order:06d}",
        type=block_type,
        source_block_id=f"src-{reading_order}" if block_type != "page_break" else None,
        source_page=page,
        reading_order=reading_order,
        bbox=(10.0, 20.0, 100.0, 40.0),
        normalized_bbox=(10.0, 20.0, 100.0, 40.0),
        text=text,
        style_features=StyleFeatures(
            font_size=font_size,
            monospace=monospace,
            indentation=indentation,
        ),
        asset_ref=asset_ref or None,
        attached_to=attached_to or None,
        caption_block_id=caption_block_id or None,
    )
