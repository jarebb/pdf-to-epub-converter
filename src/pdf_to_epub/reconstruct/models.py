"""Reading-order reconstruction models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pdf_to_epub.extract.models import BBox, StyleFeatures


@dataclass(frozen=True)
class OrderedBlock:
    id: str
    type: str
    source_block_id: Optional[str]
    source_page: int
    reading_order: int
    bbox: BBox
    normalized_bbox: BBox
    text: str
    style_features: StyleFeatures = field(default_factory=StyleFeatures)
    asset_ref: Optional[str] = None
    confidence: float = 1.0
    attached_to: Optional[str] = None
    caption_block_id: Optional[str] = None
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": self.type,
            "source_block_id": self.source_block_id,
            "source_page": self.source_page,
            "reading_order": self.reading_order,
            "bbox": self.bbox,
            "normalized_bbox": self.normalized_bbox,
            "text": self.text,
            "style_features": self.style_features.to_dict(),
            "asset_ref": self.asset_ref,
            "confidence": self.confidence,
            "attached_to": self.attached_to,
            "caption_block_id": self.caption_block_id,
            "diagnostics": self.diagnostics,
        }


@dataclass(frozen=True)
class RemovedArtifact:
    source_block_id: str
    source_page: int
    text: str
    reason: str
    bbox: BBox

    def to_dict(self) -> dict[str, object]:
        return {
            "source_block_id": self.source_block_id,
            "source_page": self.source_page,
            "text": self.text,
            "reason": self.reason,
            "bbox": self.bbox,
        }


@dataclass(frozen=True)
class ReadingOrderDocument:
    page_count: int
    blocks: list[OrderedBlock] = field(default_factory=list)
    removed_artifacts: list[RemovedArtifact] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "page_count": self.page_count,
            "blocks": [block.to_dict() for block in self.blocks],
            "removed_artifacts": [artifact.to_dict() for artifact in self.removed_artifacts],
            "diagnostics": self.diagnostics,
        }
