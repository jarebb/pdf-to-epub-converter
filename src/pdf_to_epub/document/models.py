"""Stable intermediate document model for EPUB rendering."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pdf_to_epub.extract.models import BBox, StyleFeatures


@dataclass(frozen=True)
class DocumentAsset:
    id: str
    kind: str
    file_name: str
    media_type: str
    width: int
    height: int
    source_path: Optional[str] = None
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
            "source_path": self.source_path,
            "source_pages": self.source_pages,
            "diagnostics": self.diagnostics,
        }


@dataclass(frozen=True)
class DocumentBlock:
    id: str
    type: str
    text: str
    source_pages: list[int]
    source_block_ids: list[str] = field(default_factory=list)
    bbox: Optional[BBox] = None
    normalized_bbox: Optional[BBox] = None
    style_features: StyleFeatures = field(default_factory=StyleFeatures)
    asset_id: Optional[str] = None
    asset_ref: Optional[str] = None
    caption: Optional[str] = None
    level: Optional[int] = None
    confidence: float = 1.0
    diagnostics: list[str] = field(default_factory=list)
    children: list[DocumentBlock] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": self.type,
            "text": self.text,
            "source_pages": self.source_pages,
            "source_block_ids": self.source_block_ids,
            "bbox": self.bbox,
            "normalized_bbox": self.normalized_bbox,
            "style_features": self.style_features.to_dict(),
            "asset_id": self.asset_id,
            "asset_ref": self.asset_ref,
            "caption": self.caption,
            "level": self.level,
            "confidence": self.confidence,
            "diagnostics": self.diagnostics,
            "children": [child.to_dict() for child in self.children],
        }


@dataclass(frozen=True)
class TocEntry:
    id: str
    title: str
    level: int
    section_id: str
    source_page: int
    block_id: Optional[str] = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "level": self.level,
            "section_id": self.section_id,
            "source_page": self.source_page,
            "block_id": self.block_id,
        }


@dataclass(frozen=True)
class DocumentNote:
    id: str
    text: str
    source_page: int
    reference_block_id: Optional[str] = None
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "text": self.text,
            "source_page": self.source_page,
            "reference_block_id": self.reference_block_id,
            "diagnostics": self.diagnostics,
        }


@dataclass(frozen=True)
class DocumentSection:
    id: str
    title: str
    level: int
    source_pages: list[int]
    blocks: list[DocumentBlock] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "level": self.level,
            "source_pages": self.source_pages,
            "blocks": [block.to_dict() for block in self.blocks],
            "diagnostics": self.diagnostics,
        }


@dataclass(frozen=True)
class DocumentModel:
    metadata: dict[str, str]
    page_count: int
    assets: list[DocumentAsset] = field(default_factory=list)
    sections: list[DocumentSection] = field(default_factory=list)
    toc: list[TocEntry] = field(default_factory=list)
    notes: list[DocumentNote] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "metadata": self.metadata,
            "page_count": self.page_count,
            "assets": [asset.to_dict() for asset in self.assets],
            "sections": [section.to_dict() for section in self.sections],
            "toc": [entry.to_dict() for entry in self.toc],
            "notes": [note.to_dict() for note in self.notes],
            "diagnostics": self.diagnostics,
        }
