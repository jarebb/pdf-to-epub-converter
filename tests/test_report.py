from pathlib import Path

from pdf_to_epub.classify.page_classifier import ClassificationSummary
from pdf_to_epub.document.models import DocumentBlock, DocumentModel, DocumentSection
from pdf_to_epub.reconstruct.models import ReadingOrderDocument, RemovedArtifact
from pdf_to_epub.report.conversion import build_conversion_report
from pdf_to_epub.validate.epubcheck import EpubCheckResult
from pdf_to_epub.visuals.models import VisualAsset, VisualAssetManifest


def test_build_conversion_report_summarizes_pipeline_outputs() -> None:
    classification_summary = ClassificationSummary(
        page_count=1,
        categories={"born_digital_text": 1},
        pages_with_text_layer=1,
        pages_requiring_ocr_later=0,
        pages_recommended_for_direct_extraction=1,
    )
    reading_order = ReadingOrderDocument(
        page_count=1,
        removed_artifacts=[
            RemovedArtifact(
                source_block_id="b1",
                source_page=1,
                text="1",
                reason="bottom_page_number",
                bbox=(0, 0, 1, 1),
            )
        ],
        diagnostics=["reading_order_blocks:4"],
    )
    model = DocumentModel(
        metadata={"title": "Report Test", "language": "en"},
        page_count=1,
        sections=[
            DocumentSection(
                id="sec-0001",
                title="Chapter",
                level=1,
                source_pages=[1],
                blocks=[
                    DocumentBlock(
                        id="h1",
                        type="heading",
                        text="Chapter",
                        source_pages=[1],
                    ),
                    DocumentBlock(
                        id="c1",
                        type="code_block",
                        text="print('x')",
                        source_pages=[1],
                        confidence=0.7,
                    ),
                ],
            )
        ],
        diagnostics=["document_sections:1"],
    )
    visuals = VisualAssetManifest(
        output_dir="/tmp/assets",
        page_count=1,
        assets=[
            VisualAsset(
                id="asset-1",
                kind="embedded_image",
                file_name="image.png",
                media_type="image/png",
                width=1,
                height=1,
                byte_size=10,
                content_hash="abc",
            ),
            VisualAsset(
                id="asset-2",
                kind="vector_diagram",
                file_name="diagram.png",
                media_type="image/png",
                width=1,
                height=1,
                byte_size=10,
                content_hash="def",
            ),
        ],
        diagnostics=["visual_assets:2"],
    )

    report = build_conversion_report(
        input_path=Path("input.pdf"),
        output_path=Path("output.epub"),
        classification_summary=classification_summary,
        reading_order=reading_order,
        document_model=model,
        visual_manifest=visuals,
        epubcheck_result=EpubCheckResult(status="passed", tool="epubcheck"),
    )

    assert report.headings_detected == 1
    assert report.images_extracted == 1
    assert report.vector_regions_rasterized == 1
    assert report.code_blocks_detected == 1
    assert report.headers_footers_removed == 1
    assert report.low_confidence_blocks == 1
    assert report.epubcheck_result["status"] == "passed"
