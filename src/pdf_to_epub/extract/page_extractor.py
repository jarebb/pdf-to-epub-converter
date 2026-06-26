"""PyMuPDF-backed text and layout extraction."""

from __future__ import annotations

from collections import Counter
from typing import Any, Optional

import fitz

from pdf_to_epub.classify.page_classifier import PageClassification, classify_page
from pdf_to_epub.extract.models import (
    BBox,
    DocumentExtraction,
    DrawingRegion,
    ExtractedBlock,
    ExtractedImage,
    PageModel,
    StyleFeatures,
    TextLine,
    TextSpan,
)

TEXT_FONT_SUPERSCRIPT = 1
TEXT_FONT_ITALIC = 2
TEXT_FONT_MONOSPACED = 8
TEXT_FONT_BOLD = 16


def extract_document_model(
    document: Any,
    classifications: Optional[list[PageClassification]] = None,
) -> DocumentExtraction:
    pages = [
        extract_page_model(
            document.load_page(index),
            page_number=index + 1,
            classification=_classification_for_page(document, classifications, index),
        )
        for index in range(document.page_count)
    ]
    return DocumentExtraction(page_count=document.page_count, pages=pages)


def extract_page_model(
    page: Any,
    *,
    page_number: int,
    classification: Optional[PageClassification] = None,
) -> PageModel:
    classification = classification or classify_page(page)
    diagnostics: list[str] = []
    text_dict = _get_text_dict(page, diagnostics)
    blocks: list[ExtractedBlock] = []
    images: list[ExtractedImage] = []

    for block_index, raw_block in enumerate(text_dict.get("blocks", [])):
        block_type = int(raw_block.get("type", -1))
        if block_type == 0:
            blocks.append(_extract_text_block(raw_block, page_number, block_index))
        elif block_type == 1:
            image = _extract_image_block(raw_block, page_number, block_index)
            images.append(image)
            blocks.append(_image_as_block(image, page_number))
        else:
            diagnostics.append(f"skipped_unknown_block_type:{block_type}")

    drawings = _extract_drawings(page, page_number, diagnostics)
    rect = page.rect
    _add_quality_diagnostics(blocks, images, drawings, diagnostics)

    return PageModel(
        page_number=page_number,
        width=round(float(rect.width), 3),
        height=round(float(rect.height), 3),
        rotation=int(page.rotation or 0),
        classification=classification,
        blocks=blocks,
        images=images,
        drawings=drawings,
        diagnostics=diagnostics,
    )


def _classification_for_page(
    document: Any,
    classifications: Optional[list[PageClassification]],
    index: int,
) -> PageClassification:
    if classifications is not None:
        return classifications[index]
    return classify_page(document.load_page(index))


def _get_text_dict(page: Any, diagnostics: list[str]) -> dict[str, Any]:
    try:
        result = page.get_text("dict") or {}
    except Exception as exc:  # pragma: no cover - exact PyMuPDF exception varies.
        diagnostics.append(f"pymupdf_text_dict_failed:{exc}")
        return {}
    if not isinstance(result, dict):
        diagnostics.append("pymupdf_text_dict_unexpected_type")
        return {}
    return result


def _extract_text_block(
    raw_block: dict[str, Any],
    page_number: int,
    block_index: int,
) -> ExtractedBlock:
    lines = [_extract_line(line) for line in raw_block.get("lines", [])]
    spans = [span for line in lines for span in line.spans]
    text = "\n".join(line.text for line in lines if line.text).strip()
    bbox = _bbox(raw_block.get("bbox", (0, 0, 0, 0)))

    return ExtractedBlock(
        id=f"p{page_number}-b{block_index}",
        type="text",
        bbox=bbox,
        source_page=page_number,
        text=text,
        lines=lines,
        spans=spans,
        style_features=_style_features_for_block(bbox, lines, spans),
        confidence=_text_block_confidence(text, spans),
    )


def _extract_line(raw_line: dict[str, Any]) -> TextLine:
    spans = [_extract_span(span) for span in raw_line.get("spans", [])]
    return TextLine(
        text="".join(span.text for span in spans),
        bbox=_bbox(raw_line.get("bbox", (0, 0, 0, 0))),
        spans=spans,
    )


def _extract_span(raw_span: dict[str, Any]) -> TextSpan:
    flags = int(raw_span.get("flags", 0) or 0)
    text = str(raw_span.get("text", ""))
    font_size = round(float(raw_span.get("size", 0.0) or 0.0), 3)
    bbox = _bbox(raw_span.get("bbox", (0, 0, 0, 0)))

    return TextSpan(
        text=text,
        bbox=bbox,
        font_name=str(raw_span.get("font", "")),
        font_size=font_size,
        flags=flags,
        color=_color_to_hex(raw_span.get("color")),
        bold=_flag_enabled(flags, TEXT_FONT_BOLD),
        italic=_flag_enabled(flags, TEXT_FONT_ITALIC),
        monospace=_flag_enabled(flags, TEXT_FONT_MONOSPACED),
        superscript=_flag_enabled(flags, TEXT_FONT_SUPERSCRIPT),
        subscript=False,
    )


def _extract_image_block(
    raw_block: dict[str, Any],
    page_number: int,
    block_index: int,
) -> ExtractedImage:
    image_id = f"p{page_number}-img{block_index}"
    extension = _optional_str(raw_block.get("ext"))
    return ExtractedImage(
        id=image_id,
        bbox=_bbox(raw_block.get("bbox", (0, 0, 0, 0))),
        width=int(raw_block.get("width", 0) or 0),
        height=int(raw_block.get("height", 0) or 0),
        extension=extension,
        colorspace=_optional_str(raw_block.get("colorspace")),
        xres=_optional_int(raw_block.get("xres")),
        yres=_optional_int(raw_block.get("yres")),
        bits_per_component=_optional_int(raw_block.get("bpc")),
        byte_size=_optional_int(raw_block.get("size")),
        asset_ref=f"images/{image_id}.{extension or 'bin'}",
    )


def _image_as_block(image: ExtractedImage, page_number: int) -> ExtractedBlock:
    return ExtractedBlock(
        id=f"{image.id}-block",
        type="image",
        bbox=image.bbox,
        source_page=page_number,
        text="",
        asset_ref=image.asset_ref,
        confidence=0.95,
    )


def _extract_drawings(page: Any, page_number: int, diagnostics: list[str]) -> list[DrawingRegion]:
    try:
        raw_drawings = page.get_drawings()
    except Exception as exc:  # pragma: no cover - exact PyMuPDF exception varies.
        diagnostics.append(f"pymupdf_drawings_failed:{exc}")
        return []

    drawings: list[DrawingRegion] = []
    for index, raw in enumerate(raw_drawings):
        drawings.append(
            DrawingRegion(
                id=f"p{page_number}-draw{index}",
                bbox=_bbox(raw.get("rect", (0, 0, 0, 0))),
                drawing_type=str(raw.get("type", "")),
                item_count=len(raw.get("items", [])),
                fill=_color_tuple(raw.get("fill")),
                stroke=_color_tuple(raw.get("color")),
                stroke_width=_optional_float(raw.get("width")),
            )
        )
    return drawings


def _style_features_for_block(
    bbox: BBox,
    lines: list[TextLine],
    spans: list[TextSpan],
) -> StyleFeatures:
    if not spans:
        return StyleFeatures(indentation=round(float(bbox[0]), 3))

    text = "".join(span.text for span in spans)
    font_size = _most_common_float([span.font_size for span in spans])
    font_name = _most_common_str([span.font_name for span in spans])

    return StyleFeatures(
        font_size=font_size,
        font_name=font_name,
        bold=any(span.bold for span in spans),
        italic=any(span.italic for span in spans),
        monospace=any(span.monospace for span in spans),
        text_color=_most_common_str([span.color for span in spans if span.color]),
        indentation=round(float(bbox[0]), 3),
        alignment=_infer_alignment(bbox, lines),
        line_spacing=_infer_line_spacing(lines),
        all_caps=_is_all_caps(text),
        superscript=any(span.superscript for span in spans),
        subscript=any(span.subscript for span in spans),
    )


def _text_block_confidence(text: str, spans: list[TextSpan]) -> float:
    if not spans:
        return 0.0
    if "\ufffd" in text:
        return 0.7
    return 0.95


def _infer_alignment(bbox: BBox, lines: list[TextLine]) -> Optional[str]:
    if not lines:
        return None
    lefts = [line.bbox[0] for line in lines]
    rights = [line.bbox[2] for line in lines]
    if max(lefts) - min(lefts) <= 2.0 and max(rights) - min(rights) <= 2.0:
        return "justified"
    if max(lefts) - min(lefts) <= 2.0:
        return "left"
    block_mid = (bbox[0] + bbox[2]) / 2
    line_mids = [(line.bbox[0] + line.bbox[2]) / 2 for line in lines]
    if max(abs(mid - block_mid) for mid in line_mids) <= 2.0:
        return "center"
    return "unknown"


def _infer_line_spacing(lines: list[TextLine]) -> Optional[float]:
    if len(lines) < 2:
        return None
    distances = [
        round(float(lines[index + 1].bbox[1] - lines[index].bbox[1]), 3)
        for index in range(len(lines) - 1)
    ]
    return _most_common_float(distances)


def _is_all_caps(text: str) -> bool:
    letters = [char for char in text if char.isalpha()]
    return len(letters) >= 3 and all(char.upper() == char for char in letters)


def _add_quality_diagnostics(
    blocks: list[ExtractedBlock],
    images: list[ExtractedImage],
    drawings: list[DrawingRegion],
    diagnostics: list[str],
) -> None:
    text_blocks = [block for block in blocks if block.type == "text"]
    if not blocks:
        diagnostics.append("no_blocks_extracted")
    if not text_blocks and not images:
        diagnostics.append("no_text_or_image_blocks_extracted")
    if drawings and not images:
        diagnostics.append("vector_drawings_present")


def _bbox(value: Any) -> BBox:
    if isinstance(value, fitz.Rect):
        coords = (value.x0, value.y0, value.x1, value.y1)
    else:
        coords = tuple(value)
    padded = tuple(float(item) for item in coords[:4])
    if len(padded) != 4:
        return (0.0, 0.0, 0.0, 0.0)
    return tuple(round(item, 3) for item in padded)  # type: ignore[return-value]


def _color_to_hex(value: Any) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, int):
        return f"#{value & 0xFFFFFF:06x}"
    return None


def _color_tuple(value: Any) -> Optional[tuple[float, ...]]:
    if value is None:
        return None
    return tuple(round(float(item), 4) for item in value)


def _optional_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value)
    return text or None


def _optional_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    return int(value)


def _optional_float(value: Any) -> Optional[float]:
    if value is None:
        return None
    return round(float(value), 4)


def _flag_enabled(flags: int, flag: int) -> bool:
    return bool(flags & flag)


def _most_common_float(values: list[float]) -> Optional[float]:
    if not values:
        return None
    return float(Counter(values).most_common(1)[0][0])


def _most_common_str(values: list[str]) -> Optional[str]:
    if not values:
        return None
    return Counter(values).most_common(1)[0][0]
