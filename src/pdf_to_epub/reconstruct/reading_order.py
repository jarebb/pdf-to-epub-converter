"""Book-first reading-order reconstruction."""

from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import replace
from typing import Optional

from pdf_to_epub.extract.models import (
    BBox,
    DocumentExtraction,
    ExtractedBlock,
    PageModel,
    TextLine,
)
from pdf_to_epub.reconstruct.models import OrderedBlock, ReadingOrderDocument, RemovedArtifact

TOP_BOTTOM_BAND_RATIO = 0.12
MIN_REPEATED_ARTIFACT_PAGES = 3
CAPTION_DISTANCE = 90.0

CAPTION_PATTERN = re.compile(r"^\s*(figure|fig\.|table)\s+\d+[\w.-]*[:.\s-]", re.IGNORECASE)
PAGE_NUMBER_PATTERN = re.compile(r"^\s*(?:[-–—]\s*)?(?:[ivxlcdm]+|\d+)(?:\s*[-–—])?\s*$", re.I)
WORD_BREAK_PATTERN = re.compile(r"[A-Za-z]{2,}-$")

LIGATURES = {
    "\ufb00": "ff",
    "\ufb01": "fi",
    "\ufb02": "fl",
    "\ufb03": "ffi",
    "\ufb04": "ffl",
    "\ufb05": "st",
    "\ufb06": "st",
}


def reconstruct_reading_order(extraction: DocumentExtraction) -> ReadingOrderDocument:
    diagnostics: list[str] = []
    artifact_signatures = _detect_repeated_artifacts(extraction.pages, diagnostics)
    removed_artifacts: list[RemovedArtifact] = []
    ordered_blocks: list[OrderedBlock] = []

    for page in extraction.pages:
        ordered_blocks.append(_page_break_block(page, len(ordered_blocks)))
        page_blocks = sorted(
            page.blocks,
            key=lambda block: _reading_sort_key(page, block.bbox),
        )

        for block in page_blocks:
            artifact_reason = _artifact_reason(page, block, artifact_signatures)
            if artifact_reason:
                removed_artifacts.append(
                    RemovedArtifact(
                        source_block_id=block.id,
                        source_page=block.source_page,
                        text=block.text,
                        reason=artifact_reason,
                        bbox=block.bbox,
                    )
                )
                continue
            ordered_blocks.append(_ordered_block(page, block, len(ordered_blocks)))

    ordered_blocks = _attach_captions(ordered_blocks)
    diagnostics.extend(_summary_diagnostics(ordered_blocks, removed_artifacts))

    return ReadingOrderDocument(
        page_count=extraction.page_count,
        blocks=ordered_blocks,
        removed_artifacts=removed_artifacts,
        diagnostics=diagnostics,
    )


def _detect_repeated_artifacts(
    pages: list[PageModel],
    diagnostics: list[str],
) -> set[tuple[str, str]]:
    if len(pages) < MIN_REPEATED_ARTIFACT_PAGES:
        return set()

    positions_by_signature: dict[tuple[str, str], set[int]] = defaultdict(set)
    for page in pages:
        for block in page.blocks:
            if block.type != "text":
                continue
            band = _page_band(page, block.bbox)
            if band is None:
                continue
            signature = _text_signature(block.text)
            if not signature:
                continue
            positions_by_signature[(band, signature)].add(page.page_number)

    artifacts = {
        key
        for key, page_numbers in positions_by_signature.items()
        if len(page_numbers) >= MIN_REPEATED_ARTIFACT_PAGES
    }
    if artifacts:
        diagnostics.append(f"repeated_artifact_signatures:{len(artifacts)}")
    return artifacts


def _artifact_reason(
    page: PageModel,
    block: ExtractedBlock,
    artifact_signatures: set[tuple[str, str]],
) -> Optional[str]:
    if block.type != "text":
        return None
    band = _page_band(page, block.bbox)
    if band is None:
        return None
    signature = _text_signature(block.text)
    if PAGE_NUMBER_PATTERN.match(block.text):
        return f"{band}_page_number"
    if (band, signature) in artifact_signatures:
        return f"repeated_{band}_artifact"
    return None


def _ordered_block(page: PageModel, block: ExtractedBlock, reading_order: int) -> OrderedBlock:
    diagnostics: list[str] = []
    text = _block_text(block, diagnostics)
    block_type = _ordered_type(block, text)
    return OrderedBlock(
        id=f"ord-{reading_order:06d}",
        type=block_type,
        source_block_id=block.id,
        source_page=block.source_page,
        reading_order=reading_order,
        bbox=block.bbox,
        normalized_bbox=_normalize_bbox(block.bbox, page.width, page.height, page.rotation),
        text=text,
        style_features=block.style_features,
        asset_ref=block.asset_ref,
        confidence=block.confidence,
        diagnostics=diagnostics,
    )


def _page_break_block(page: PageModel, reading_order: int) -> OrderedBlock:
    return OrderedBlock(
        id=f"ord-{reading_order:06d}",
        type="page_break",
        source_block_id=None,
        source_page=page.page_number,
        reading_order=reading_order,
        bbox=(0.0, 0.0, 0.0, 0.0),
        normalized_bbox=(0.0, 0.0, 0.0, 0.0),
        text="",
        confidence=1.0,
    )


def _ordered_type(block: ExtractedBlock, text: str) -> str:
    if block.type == "image":
        return "figure"
    if block.type != "text":
        return block.type
    if block.style_features.monospace:
        return "code_block"
    if CAPTION_PATTERN.match(text):
        return "caption"
    return "text"


def _block_text(block: ExtractedBlock, diagnostics: list[str]) -> str:
    if block.type != "text":
        return ""
    if not block.lines:
        return _normalize_text(block.text)
    return _normalize_lines(block.lines, diagnostics)


def _normalize_lines(lines: list[TextLine], diagnostics: list[str]) -> str:
    output: list[str] = []
    skip_next_join_space = False
    for index, line in enumerate(lines):
        text = _normalize_text(line.text).strip()
        if not text:
            continue

        if output and skip_next_join_space:
            output[-1] = f"{output[-1]}{text}"
            skip_next_join_space = False
            continue

        if index + 1 < len(lines) and _should_dehyphenate(text, lines[index + 1].text):
            output.append(text[:-1])
            skip_next_join_space = True
            diagnostics.append("dehyphenated_line_break")
            continue

        output.append(text)
    return " ".join(output).strip()


def _should_dehyphenate(current: str, next_line: str) -> bool:
    next_text = _normalize_text(next_line).lstrip()
    if not next_text or not next_text[0].islower():
        return False
    return bool(WORD_BREAK_PATTERN.search(current))


def _normalize_text(text: str) -> str:
    normalized = text
    for source, replacement in LIGATURES.items():
        normalized = normalized.replace(source, replacement)
    return " ".join(normalized.split())


def _attach_captions(blocks: list[OrderedBlock]) -> list[OrderedBlock]:
    replacements: dict[str, OrderedBlock] = {}
    figures = [block for block in blocks if block.type == "figure"]
    captions = [block for block in blocks if block.type == "caption"]

    for figure in figures:
        caption = _nearest_caption(figure, captions)
        if caption is None:
            continue
        replacements[figure.id] = replace(
            figure,
            caption_block_id=caption.id,
            diagnostics=[*figure.diagnostics, "caption_attached"],
        )
        replacements[caption.id] = replace(
            caption,
            attached_to=figure.id,
            diagnostics=[*caption.diagnostics, "attached_to_figure"],
        )

    return [replacements.get(block.id, block) for block in blocks]


def _nearest_caption(
    figure: OrderedBlock,
    captions: list[OrderedBlock],
) -> Optional[OrderedBlock]:
    same_page = [
        caption
        for caption in captions
        if caption.source_page == figure.source_page
        and caption.normalized_bbox[1] >= figure.normalized_bbox[1]
        and caption.normalized_bbox[1] - figure.normalized_bbox[3] <= CAPTION_DISTANCE
    ]
    if not same_page:
        return None
    return min(same_page, key=lambda caption: caption.normalized_bbox[1])


def _page_band(page: PageModel, bbox: BBox) -> Optional[str]:
    top_limit = page.height * TOP_BOTTOM_BAND_RATIO
    bottom_limit = page.height * (1.0 - TOP_BOTTOM_BAND_RATIO)
    midpoint = (bbox[1] + bbox[3]) / 2
    if midpoint <= top_limit:
        return "top"
    if midpoint >= bottom_limit:
        return "bottom"
    return None


def _text_signature(text: str) -> str:
    normalized = _normalize_text(text).lower()
    normalized = re.sub(r"\d+", "#", normalized)
    normalized = re.sub(r"[^a-z#]+", " ", normalized)
    return " ".join(normalized.split())


def _reading_sort_key(page: PageModel, bbox: BBox) -> tuple[int, float, float]:
    normalized = _normalize_bbox(bbox, page.width, page.height, page.rotation)
    return (page.page_number, normalized[1], normalized[0])


def _normalize_bbox(bbox: BBox, width: float, height: float, rotation: int) -> BBox:
    x0, y0, x1, y1 = bbox
    normalized_rotation = rotation % 360
    if normalized_rotation == 90:
        return _round_bbox((y0, width - x1, y1, width - x0))
    if normalized_rotation == 180:
        return _round_bbox((width - x1, height - y1, width - x0, height - y0))
    if normalized_rotation == 270:
        return _round_bbox((height - y1, x0, height - y0, x1))
    return _round_bbox(bbox)


def _round_bbox(bbox: BBox) -> BBox:
    return tuple(round(float(value), 3) for value in bbox)  # type: ignore[return-value]


def _summary_diagnostics(
    blocks: list[OrderedBlock],
    removed_artifacts: list[RemovedArtifact],
) -> list[str]:
    diagnostics = [
        f"reading_order_blocks:{len(blocks)}",
        f"removed_artifacts:{len(removed_artifacts)}",
    ]
    type_counts = Counter(block.type for block in blocks)
    diagnostics.extend(
        f"block_type:{block_type}:{count}" for block_type, count in sorted(type_counts.items())
    )
    return diagnostics
