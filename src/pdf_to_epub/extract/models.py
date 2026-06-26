"""Intermediate page-level extraction models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from pdf_to_epub.classify.page_classifier import PageClassification

BBox = tuple[float, float, float, float]
Color = tuple[float, ...]


@dataclass(frozen=True)
class StyleFeatures:
    font_size: Optional[float] = None
    font_name: Optional[str] = None
    bold: bool = False
    italic: bool = False
    monospace: bool = False
    text_color: Optional[str] = None
    indentation: Optional[float] = None
    alignment: Optional[str] = None
    line_spacing: Optional[float] = None
    all_caps: bool = False
    superscript: bool = False
    subscript: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "font_size": self.font_size,
            "font_name": self.font_name,
            "bold": self.bold,
            "italic": self.italic,
            "monospace": self.monospace,
            "text_color": self.text_color,
            "indentation": self.indentation,
            "alignment": self.alignment,
            "line_spacing": self.line_spacing,
            "all_caps": self.all_caps,
            "superscript": self.superscript,
            "subscript": self.subscript,
        }


@dataclass(frozen=True)
class TextSpan:
    text: str
    bbox: BBox
    font_name: str
    font_size: float
    flags: int
    color: Optional[str]
    bold: bool
    italic: bool
    monospace: bool
    superscript: bool
    subscript: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "bbox": self.bbox,
            "font_name": self.font_name,
            "font_size": self.font_size,
            "flags": self.flags,
            "color": self.color,
            "bold": self.bold,
            "italic": self.italic,
            "monospace": self.monospace,
            "superscript": self.superscript,
            "subscript": self.subscript,
        }


@dataclass(frozen=True)
class TextLine:
    text: str
    bbox: BBox
    spans: list[TextSpan] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text,
            "bbox": self.bbox,
            "spans": [span.to_dict() for span in self.spans],
        }


@dataclass(frozen=True)
class ExtractedImage:
    id: str
    bbox: BBox
    width: int
    height: int
    extension: Optional[str]
    colorspace: Optional[str]
    xres: Optional[int]
    yres: Optional[int]
    bits_per_component: Optional[int]
    byte_size: Optional[int]
    asset_ref: str

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "bbox": self.bbox,
            "width": self.width,
            "height": self.height,
            "extension": self.extension,
            "colorspace": self.colorspace,
            "xres": self.xres,
            "yres": self.yres,
            "bits_per_component": self.bits_per_component,
            "byte_size": self.byte_size,
            "asset_ref": self.asset_ref,
        }


@dataclass(frozen=True)
class DrawingRegion:
    id: str
    bbox: BBox
    drawing_type: str
    item_count: int
    fill: Optional[Color]
    stroke: Optional[Color]
    stroke_width: Optional[float]

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "bbox": self.bbox,
            "drawing_type": self.drawing_type,
            "item_count": self.item_count,
            "fill": self.fill,
            "stroke": self.stroke,
            "stroke_width": self.stroke_width,
        }


@dataclass(frozen=True)
class ExtractedBlock:
    id: str
    type: str
    bbox: BBox
    source_page: int
    text: str
    lines: list[TextLine] = field(default_factory=list)
    spans: list[TextSpan] = field(default_factory=list)
    style_features: StyleFeatures = field(default_factory=StyleFeatures)
    asset_ref: Optional[str] = None
    confidence: float = 1.0

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "type": self.type,
            "bbox": self.bbox,
            "source_page": self.source_page,
            "text": self.text,
            "lines": [line.to_dict() for line in self.lines],
            "spans": [span.to_dict() for span in self.spans],
            "style_features": self.style_features.to_dict(),
            "asset_ref": self.asset_ref,
            "confidence": self.confidence,
        }


@dataclass(frozen=True)
class PageModel:
    page_number: int
    width: float
    height: float
    rotation: int
    classification: PageClassification
    blocks: list[ExtractedBlock] = field(default_factory=list)
    images: list[ExtractedImage] = field(default_factory=list)
    drawings: list[DrawingRegion] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "page_number": self.page_number,
            "width": self.width,
            "height": self.height,
            "rotation": self.rotation,
            "classification": self.classification.to_dict(),
            "blocks": [block.to_dict() for block in self.blocks],
            "images": [image.to_dict() for image in self.images],
            "drawings": [drawing.to_dict() for drawing in self.drawings],
            "diagnostics": self.diagnostics,
        }


@dataclass(frozen=True)
class DocumentExtraction:
    page_count: int
    pages: list[PageModel] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "page_count": self.page_count,
            "pages": [page.to_dict() for page in self.pages],
        }
