"""Quality and conversion report models."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from pdf_to_epub.classify.page_classifier import ClassificationSummary
from pdf_to_epub.document.models import DocumentModel
from pdf_to_epub.reconstruct.models import ReadingOrderDocument
from pdf_to_epub.validate.epubcheck import EpubCheckResult
from pdf_to_epub.visuals.models import VisualAssetManifest


@dataclass(frozen=True)
class ConversionReport:
    input_path: str
    output_path: str
    page_count: int
    classifications: dict[str, object]
    metadata: dict[str, str]
    headings_detected: int
    images_extracted: int
    vector_regions_rasterized: int
    code_blocks_detected: int
    list_blocks_detected: int
    blockquotes_detected: int
    headers_footers_removed: int
    low_confidence_blocks: int
    unsupported_pages: list[int] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)
    epubcheck_result: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "input_path": self.input_path,
            "output_path": self.output_path,
            "page_count": self.page_count,
            "classifications": self.classifications,
            "metadata": self.metadata,
            "headings_detected": self.headings_detected,
            "images_extracted": self.images_extracted,
            "vector_regions_rasterized": self.vector_regions_rasterized,
            "code_blocks_detected": self.code_blocks_detected,
            "list_blocks_detected": self.list_blocks_detected,
            "blockquotes_detected": self.blockquotes_detected,
            "headers_footers_removed": self.headers_footers_removed,
            "low_confidence_blocks": self.low_confidence_blocks,
            "unsupported_pages": self.unsupported_pages,
            "diagnostics": self.diagnostics,
            "epubcheck_result": self.epubcheck_result,
        }


def build_conversion_report(
    *,
    input_path: Path,
    output_path: Path,
    classification_summary: ClassificationSummary,
    reading_order: ReadingOrderDocument,
    document_model: DocumentModel,
    visual_manifest: VisualAssetManifest,
    epubcheck_result: EpubCheckResult,
) -> ConversionReport:
    blocks = [block for section in document_model.sections for block in section.blocks]
    return ConversionReport(
        input_path=str(input_path.expanduser()),
        output_path=str(output_path.expanduser()),
        page_count=document_model.page_count,
        classifications=classification_summary.to_dict(),
        metadata=document_model.metadata,
        headings_detected=sum(1 for block in blocks if block.type == "heading"),
        images_extracted=sum(
            1 for asset in visual_manifest.assets if asset.kind == "embedded_image"
        ),
        vector_regions_rasterized=sum(
            1 for asset in visual_manifest.assets if asset.kind == "vector_diagram"
        ),
        code_blocks_detected=sum(1 for block in blocks if block.type == "code_block"),
        list_blocks_detected=sum(1 for block in blocks if block.type == "list"),
        blockquotes_detected=sum(1 for block in blocks if block.type == "blockquote"),
        headers_footers_removed=len(reading_order.removed_artifacts),
        low_confidence_blocks=sum(1 for block in blocks if block.confidence < 0.75),
        unsupported_pages=[],
        diagnostics=[
            *reading_order.diagnostics,
            *document_model.diagnostics,
            *visual_manifest.diagnostics,
        ],
        epubcheck_result=epubcheck_result.to_dict(),
    )
