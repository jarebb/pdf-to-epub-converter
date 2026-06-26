"""Visual asset extraction models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pdf_to_epub.extract.models import BBox


@dataclass(frozen=True)
class VisualAsset:
    id: str
    kind: str
    file_name: str
    media_type: str
    width: int
    height: int
    byte_size: int
    content_hash: str
    source_xref: Optional[int] = None
    source_pages: list[int] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "kind": self.kind,
            "file_name": self.file_name,
            "media_type": self.media_type,
            "width": self.width,
            "height": self.height,
            "byte_size": self.byte_size,
            "content_hash": self.content_hash,
            "source_xref": self.source_xref,
            "source_pages": self.source_pages,
            "diagnostics": self.diagnostics,
        }


@dataclass(frozen=True)
class VisualPlacement:
    id: str
    asset_id: str
    kind: str
    source_page: int
    bbox: BBox
    role: str
    confidence: float
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "asset_id": self.asset_id,
            "kind": self.kind,
            "source_page": self.source_page,
            "bbox": self.bbox,
            "role": self.role,
            "confidence": self.confidence,
            "diagnostics": self.diagnostics,
        }


@dataclass(frozen=True)
class VisualAssetManifest:
    output_dir: str
    page_count: int
    assets: list[VisualAsset] = field(default_factory=list)
    placements: list[VisualPlacement] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "output_dir": self.output_dir,
            "page_count": self.page_count,
            "assets": [asset.to_dict() for asset in self.assets],
            "placements": [placement.to_dict() for placement in self.placements],
            "diagnostics": self.diagnostics,
        }
