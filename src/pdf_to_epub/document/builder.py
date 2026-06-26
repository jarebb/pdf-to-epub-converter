"""Build the semantic document model from reconstructed reading order."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import replace
from pathlib import Path
from typing import Optional

from pdf_to_epub.document.models import (
    DocumentAsset,
    DocumentBlock,
    DocumentModel,
    DocumentSection,
    TocEntry,
)
from pdf_to_epub.extract.models import BBox
from pdf_to_epub.reconstruct.models import OrderedBlock, ReadingOrderDocument
from pdf_to_epub.visuals.models import VisualAssetManifest, VisualPlacement

DEFAULT_TITLE = "Untitled"
CHAPTER_PATTERN = re.compile(r"^\s*(chapter|part|appendix)\s+[\wivxlcdm.-]+", re.IGNORECASE)
LIST_MARKER_PATTERN = re.compile(r"^\s*(?:[-*•]|\d+[.)]|[A-Za-z][.)])\s+")
MAX_HEADING_WORDS = 18
BLOCKQUOTE_INDENT_DELTA = 36.0


def build_document_model(
    reading_order: ReadingOrderDocument,
    *,
    metadata: Optional[dict[str, str]] = None,
    visual_manifest: Optional[VisualAssetManifest] = None,
) -> DocumentModel:
    metadata = _normalize_metadata(metadata)
    assets = _document_assets(visual_manifest)
    asset_id_by_ref = _asset_id_by_ref(assets)
    asset_id_by_figure = _asset_id_by_figure(reading_order.blocks, visual_manifest)
    body_font_size = _body_font_size(reading_order.blocks)
    body_left_margin = _body_left_margin(reading_order.blocks)
    caption_by_id = {
        block.id: block
        for block in reading_order.blocks
        if block.type == "caption" and block.attached_to
    }

    sections: list[DocumentSection] = []
    toc: list[TocEntry] = []
    current_blocks: list[DocumentBlock] = []
    current_title = metadata.get("title", DEFAULT_TITLE) or DEFAULT_TITLE
    current_level = 1
    current_section_id = "sec-0001"

    for ordered in reading_order.blocks:
        document_block = _document_block(
            ordered,
            body_font_size=body_font_size,
            body_left_margin=body_left_margin,
            caption_by_id=caption_by_id,
            asset_id_by_ref=asset_id_by_ref,
            asset_id_by_figure=asset_id_by_figure,
        )
        if document_block is None:
            continue

        if document_block.type == "heading" and document_block.level == 1:
            if sections or _has_content_blocks(current_blocks):
                sections.append(
                    _section(current_section_id, current_title, current_level, current_blocks)
                )
                current_blocks = []
            current_section_id = f"sec-{len(sections) + 1:04d}"
            current_title = document_block.text
            current_level = document_block.level or 1
            toc.append(
                TocEntry(
                    id=f"toc-{len(toc) + 1:04d}",
                    title=document_block.text,
                    level=current_level,
                    section_id=current_section_id,
                    source_page=document_block.source_pages[0],
                    block_id=document_block.id,
                )
            )

        current_blocks.append(document_block)

    if current_blocks or not sections:
        sections.append(_section(current_section_id, current_title, current_level, current_blocks))

    diagnostics = [
        f"document_sections:{len(sections)}",
        f"document_assets:{len(assets)}",
        f"document_toc_entries:{len(toc)}",
        f"body_font_size:{body_font_size:.3f}" if body_font_size else "body_font_size:unknown",
        (
            f"body_left_margin:{body_left_margin:.3f}"
            if body_left_margin is not None
            else "body_left_margin:unknown"
        ),
    ]
    diagnostics.extend(_type_count_diagnostics(sections))

    return DocumentModel(
        metadata=metadata,
        page_count=reading_order.page_count,
        assets=assets,
        sections=sections,
        toc=toc,
        notes=[],
        diagnostics=diagnostics,
    )


def _normalize_metadata(metadata: Optional[dict[str, str]]) -> dict[str, str]:
    normalized = dict(metadata or {})
    normalized.setdefault("title", DEFAULT_TITLE)
    normalized.setdefault("language", "en")
    return normalized


def _document_assets(visual_manifest: Optional[VisualAssetManifest]) -> list[DocumentAsset]:
    if visual_manifest is None:
        return []
    return [
        DocumentAsset(
            id=asset.id,
            kind=asset.kind,
            file_name=asset.file_name,
            media_type=asset.media_type,
            width=asset.width,
            height=asset.height,
            source_path=str(Path(visual_manifest.output_dir) / asset.file_name),
            source_pages=asset.source_pages,
            diagnostics=asset.diagnostics,
        )
        for asset in visual_manifest.assets
    ]


def _asset_id_by_ref(assets: list[DocumentAsset]) -> dict[str, str]:
    return {asset.file_name: asset.id for asset in assets}


def _asset_id_by_figure(
    blocks: list[OrderedBlock],
    visual_manifest: Optional[VisualAssetManifest],
) -> dict[str, str]:
    if visual_manifest is None:
        return {}

    placements_by_page: dict[int, list[VisualPlacement]] = {}
    for placement in visual_manifest.placements:
        placements_by_page.setdefault(placement.source_page, []).append(placement)

    asset_id_by_block: dict[str, str] = {}
    used_placement_ids: set[str] = set()
    for block in sorted(blocks, key=lambda item: item.reading_order):
        if block.type != "figure":
            continue
        candidates = [
            placement
            for placement in placements_by_page.get(block.source_page, [])
            if placement.id not in used_placement_ids
        ]
        matched_placement = _best_matching_placement(block, candidates)
        if matched_placement is None:
            continue
        asset_id_by_block[block.id] = matched_placement.asset_id
        used_placement_ids.add(matched_placement.id)
    return asset_id_by_block


def _best_matching_placement(
    block: OrderedBlock,
    placements: list[VisualPlacement],
) -> Optional[VisualPlacement]:
    scored = [
        (_placement_match_score(block.bbox, placement.bbox), placement) for placement in placements
    ]
    scored = [(score, placement) for score, placement in scored if score >= 0.5]
    if not scored:
        return None
    return max(scored, key=lambda item: item[0])[1]


def _placement_match_score(block_bbox: BBox, placement_bbox: BBox) -> float:
    block_area = _bbox_area(block_bbox)
    placement_area = _bbox_area(placement_bbox)
    if block_area <= 0 or placement_area <= 0:
        return 0.0
    overlap = _bbox_overlap_area(block_bbox, placement_bbox)
    return overlap / min(block_area, placement_area)


def _bbox_area(bbox: BBox) -> float:
    width = max(float(bbox[2]) - float(bbox[0]), 0.0)
    height = max(float(bbox[3]) - float(bbox[1]), 0.0)
    return width * height


def _bbox_overlap_area(left: BBox, right: BBox) -> float:
    x0 = max(float(left[0]), float(right[0]))
    y0 = max(float(left[1]), float(right[1]))
    x1 = min(float(left[2]), float(right[2]))
    y1 = min(float(left[3]), float(right[3]))
    return _bbox_area((x0, y0, x1, y1))


def _document_block(
    ordered: OrderedBlock,
    *,
    body_font_size: Optional[float],
    body_left_margin: Optional[float],
    caption_by_id: dict[str, OrderedBlock],
    asset_id_by_ref: dict[str, str],
    asset_id_by_figure: dict[str, str],
) -> Optional[DocumentBlock]:
    if ordered.attached_to:
        return None

    block_type, level, diagnostics = _semantic_type(ordered, body_font_size, body_left_margin)
    caption = None
    if ordered.caption_block_id:
        caption_block = caption_by_id.get(ordered.caption_block_id)
        if caption_block is not None:
            caption = caption_block.text

    asset_id = _asset_id_for_block(ordered, asset_id_by_ref, asset_id_by_figure)
    source_block_ids = [ordered.source_block_id] if ordered.source_block_id else []
    return DocumentBlock(
        id=f"doc-{ordered.reading_order:06d}",
        type=block_type,
        text=ordered.text,
        source_pages=[ordered.source_page],
        source_block_ids=source_block_ids,
        bbox=ordered.bbox,
        normalized_bbox=ordered.normalized_bbox,
        style_features=ordered.style_features,
        asset_id=asset_id,
        asset_ref=ordered.asset_ref,
        caption=caption,
        level=level,
        confidence=ordered.confidence,
        diagnostics=[*ordered.diagnostics, *diagnostics],
    )


def _semantic_type(
    block: OrderedBlock,
    body_font_size: Optional[float],
    body_left_margin: Optional[float],
) -> tuple[str, Optional[int], list[str]]:
    if block.type == "page_break":
        return "page_break", None, []
    if block.type == "figure":
        return "figure", None, []
    if block.type == "code_block":
        return "code_block", None, []
    if block.type == "caption":
        return "paragraph", None, ["unattached_caption_as_paragraph"]
    if block.type != "text":
        return "unknown", None, [f"unknown_ordered_type:{block.type}"]
    if _looks_like_heading(block, body_font_size):
        return "heading", _heading_level(block, body_font_size), ["heading_inferred"]
    if _looks_like_list_item(block.text):
        return "list_item", None, ["list_item_inferred"]
    if _looks_like_blockquote(block, body_left_margin):
        return "blockquote", None, ["blockquote_inferred"]
    return "paragraph", None, []


def _looks_like_heading(block: OrderedBlock, body_font_size: Optional[float]) -> bool:
    text = block.text.strip()
    if not text:
        return False
    words = text.split()
    if len(words) > MAX_HEADING_WORDS:
        return False
    if CHAPTER_PATTERN.match(text):
        return True
    font_size = block.style_features.font_size
    if body_font_size is not None and font_size is not None and font_size >= body_font_size * 1.22:
        return True
    return bool(block.style_features.bold and len(words) <= 10)


def _heading_level(block: OrderedBlock, body_font_size: Optional[float]) -> int:
    if CHAPTER_PATTERN.match(block.text):
        return 1
    font_size = block.style_features.font_size
    if body_font_size is not None and font_size is not None and font_size >= body_font_size * 1.6:
        return 1
    return 2


def _asset_id_for_block(
    block: OrderedBlock,
    asset_id_by_ref: dict[str, str],
    asset_id_by_figure: dict[str, str],
) -> Optional[str]:
    if block.id in asset_id_by_figure:
        return asset_id_by_figure[block.id]
    if block.asset_ref is None:
        return None
    file_name = block.asset_ref.rsplit("/", 1)[-1]
    return asset_id_by_ref.get(file_name)


def _looks_like_list_item(text: str) -> bool:
    return bool(LIST_MARKER_PATTERN.match(text))


def _looks_like_blockquote(
    block: OrderedBlock,
    body_left_margin: Optional[float],
) -> bool:
    indentation = block.style_features.indentation
    if body_left_margin is None or indentation is None:
        return False
    return indentation >= body_left_margin + BLOCKQUOTE_INDENT_DELTA


def _body_font_size(blocks: list[OrderedBlock]) -> Optional[float]:
    sizes = [
        round(float(block.style_features.font_size), 3)
        for block in blocks
        if block.type == "text" and block.style_features.font_size is not None
    ]
    if not sizes:
        return None
    counts = Counter(sizes)
    highest_count = max(counts.values())
    return float(min(size for size, count in counts.items() if count == highest_count))


def _body_left_margin(blocks: list[OrderedBlock]) -> Optional[float]:
    margins = [
        round(float(block.style_features.indentation), 3)
        for block in blocks
        if block.type == "text" and block.style_features.indentation is not None
    ]
    if not margins:
        return None
    counts = Counter(margins)
    highest_count = max(counts.values())
    return float(min(margin for margin, count in counts.items() if count == highest_count))


def _section(
    section_id: str,
    title: str,
    level: int,
    blocks: list[DocumentBlock],
) -> DocumentSection:
    return DocumentSection(
        id=section_id,
        title=title,
        level=level,
        source_pages=_source_pages(blocks),
        blocks=_group_consecutive_list_items(blocks),
    )


def _source_pages(blocks: list[DocumentBlock]) -> list[int]:
    pages = sorted({page for block in blocks for page in block.source_pages})
    return pages


def _has_content_blocks(blocks: list[DocumentBlock]) -> bool:
    return any(block.type != "page_break" for block in blocks)


def _group_consecutive_list_items(blocks: list[DocumentBlock]) -> list[DocumentBlock]:
    grouped: list[DocumentBlock] = []
    current_items: list[DocumentBlock] = []
    list_index = 1

    for block in blocks:
        if block.type == "list_item":
            current_items.append(block)
            continue
        if current_items:
            grouped.append(_list_block(current_items, list_index))
            list_index += 1
            current_items = []
        grouped.append(block)

    if current_items:
        grouped.append(_list_block(current_items, list_index))
    return grouped


def _list_block(items: list[DocumentBlock], list_index: int) -> DocumentBlock:
    list_kind = (
        "ordered" if all(_is_ordered_list_item(item.text) for item in items) else "unordered"
    )
    return DocumentBlock(
        id=f"list-{items[0].id}-{list_index:03d}",
        type="list",
        text="",
        source_pages=_source_pages(items),
        source_block_ids=[source_id for item in items for source_id in item.source_block_ids],
        bbox=items[0].bbox,
        normalized_bbox=items[0].normalized_bbox,
        confidence=min(item.confidence for item in items),
        diagnostics=[f"list_inferred:{list_kind}", f"list_items:{len(items)}"],
        children=[replace(item, text=_strip_list_marker(item.text)) for item in items],
    )


def _is_ordered_list_item(text: str) -> bool:
    return bool(re.match(r"^\s*(?:\d+[.)]|[A-Za-z][.)])\s+", text))


def _strip_list_marker(text: str) -> str:
    return LIST_MARKER_PATTERN.sub("", text, count=1).strip()


def _type_count_diagnostics(sections: list[DocumentSection]) -> list[str]:
    counts = Counter(block.type for section in sections for block in section.blocks)
    return [
        f"document_block_type:{block_type}:{count}" for block_type, count in sorted(counts.items())
    ]
