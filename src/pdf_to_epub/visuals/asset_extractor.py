"""Embedded image and vector diagram extraction."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from pathlib import Path
from typing import Any, Optional

import fitz

from pdf_to_epub.extract.models import BBox
from pdf_to_epub.visuals.models import VisualAsset, VisualAssetManifest, VisualPlacement

DEFAULT_DIAGRAM_DPI = 180
MIN_DIAGRAM_AREA = 1200.0
MIN_DIAGRAM_WIDTH = 48.0
MIN_DIAGRAM_HEIGHT = 24.0
DIAGRAM_PADDING = 4.0
MAX_IMAGE_DIMENSION = 3200

EPUB_MEDIA_TYPES = {
    "gif": "image/gif",
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "svg": "image/svg+xml",
}


def extract_visual_assets(
    document: Any,
    output_dir: Path,
    *,
    diagram_dpi: int = DEFAULT_DIAGRAM_DPI,
) -> VisualAssetManifest:
    output_dir.mkdir(parents=True, exist_ok=True)
    diagnostics: list[str] = []
    assets_by_hash: dict[str, VisualAsset] = {}
    placements: list[VisualPlacement] = []

    for page_index in range(document.page_count):
        page = document.load_page(page_index)
        page_number = page_index + 1
        _extract_embedded_images(
            document=document,
            page=page,
            page_number=page_number,
            output_dir=output_dir,
            assets_by_hash=assets_by_hash,
            placements=placements,
            diagnostics=diagnostics,
        )
        _extract_vector_diagrams(
            page=page,
            page_number=page_number,
            output_dir=output_dir,
            assets_by_hash=assets_by_hash,
            placements=placements,
            diagnostics=diagnostics,
            diagram_dpi=diagram_dpi,
        )

    assets = sorted(assets_by_hash.values(), key=lambda asset: asset.id)
    diagnostics.extend(
        [
            f"visual_assets:{len(assets)}",
            f"visual_placements:{len(placements)}",
        ]
    )
    return VisualAssetManifest(
        output_dir=str(output_dir.resolve()),
        page_count=document.page_count,
        assets=assets,
        placements=placements,
        diagnostics=diagnostics,
    )


def _extract_embedded_images(
    *,
    document: Any,
    page: Any,
    page_number: int,
    output_dir: Path,
    assets_by_hash: dict[str, VisualAsset],
    placements: list[VisualPlacement],
    diagnostics: list[str],
) -> None:
    for image in page.get_images(full=True):
        xref = int(image[0])
        rects = page.get_image_rects(xref)
        if not rects:
            diagnostics.append(f"image_without_rect:p{page_number}:xref{xref}")
            continue

        image_data = _extract_image_data(document, xref, diagnostics)
        if image_data is None:
            continue
        payload, extension, width, height, media_type, asset_diagnostics = image_data
        content_hash = hashlib.sha256(payload).hexdigest()
        asset = assets_by_hash.get(content_hash)
        if asset is None:
            asset = _write_asset(
                kind="embedded_image",
                payload=payload,
                extension=extension,
                media_type=media_type,
                width=width,
                height=height,
                content_hash=content_hash,
                output_dir=output_dir,
                source_xref=xref,
                source_page=page_number,
                diagnostics=asset_diagnostics,
                asset_index=len(assets_by_hash) + 1,
            )
            assets_by_hash[content_hash] = asset
        else:
            assets_by_hash[content_hash] = _add_source_page(asset, page_number)

        for rect in rects:
            placements.append(
                VisualPlacement(
                    id=f"place-{len(placements) + 1:06d}",
                    asset_id=assets_by_hash[content_hash].id,
                    kind="embedded_image",
                    source_page=page_number,
                    bbox=_bbox(rect),
                    role="figure",
                    confidence=0.95,
                )
            )


def _extract_vector_diagrams(
    *,
    page: Any,
    page_number: int,
    output_dir: Path,
    assets_by_hash: dict[str, VisualAsset],
    placements: list[VisualPlacement],
    diagnostics: list[str],
    diagram_dpi: int,
) -> None:
    candidates = _diagram_candidates(page)
    for index, rect in enumerate(candidates):
        clipped = _pad_rect(rect, page.rect, DIAGRAM_PADDING)
        try:
            pixmap = page.get_pixmap(clip=clipped, dpi=diagram_dpi, alpha=False)
            payload = pixmap.tobytes("png")
        except Exception as exc:  # pragma: no cover - exact PyMuPDF exception varies.
            diagnostics.append(f"diagram_rasterize_failed:p{page_number}:{index}:{exc}")
            continue

        content_hash = hashlib.sha256(payload).hexdigest()
        asset = assets_by_hash.get(content_hash)
        asset_diagnostics = _dimension_diagnostics(pixmap.width, pixmap.height)
        if asset is None:
            asset = _write_asset(
                kind="vector_diagram",
                payload=payload,
                extension="png",
                media_type="image/png",
                width=pixmap.width,
                height=pixmap.height,
                content_hash=content_hash,
                output_dir=output_dir,
                source_xref=None,
                source_page=page_number,
                diagnostics=asset_diagnostics,
                asset_index=len(assets_by_hash) + 1,
            )
            assets_by_hash[content_hash] = asset
        else:
            assets_by_hash[content_hash] = _add_source_page(asset, page_number)

        placements.append(
            VisualPlacement(
                id=f"place-{len(placements) + 1:06d}",
                asset_id=assets_by_hash[content_hash].id,
                kind="vector_diagram",
                source_page=page_number,
                bbox=_bbox(clipped),
                role="diagram",
                confidence=0.72,
                diagnostics=["rasterized_from_pdf_drawings"],
            )
        )


def _extract_image_data(
    document: Any,
    xref: int,
    diagnostics: list[str],
) -> Optional[tuple[bytes, str, int, int, str, list[str]]]:
    try:
        extracted = document.extract_image(xref)
    except Exception as exc:  # pragma: no cover - exact PyMuPDF exception varies.
        diagnostics.append(f"image_extract_failed:xref{xref}:{exc}")
        return None

    extension = _normalize_extension(str(extracted.get("ext", "")))
    width = int(extracted.get("width", 0) or 0)
    height = int(extracted.get("height", 0) or 0)
    asset_diagnostics = _dimension_diagnostics(width, height)
    if extension in EPUB_MEDIA_TYPES and not _is_oversized(width, height):
        return (
            bytes(extracted.get("image", b"")),
            extension,
            width,
            height,
            EPUB_MEDIA_TYPES[extension],
            asset_diagnostics,
        )

    try:
        pixmap = _epub_pixmap(document, xref)
        if _is_oversized(pixmap.width, pixmap.height):
            _shrink_to_limit(pixmap, MAX_IMAGE_DIMENSION)
            asset_diagnostics.append(f"resized_to:{pixmap.width}x{pixmap.height}")
        payload = pixmap.tobytes("png")
    except Exception as exc:  # pragma: no cover - exact PyMuPDF exception varies.
        diagnostics.append(f"image_convert_failed:xref{xref}:{exc}")
        return None

    if extension in EPUB_MEDIA_TYPES:
        asset_diagnostics.append(f"reencoded_from:{extension}")
    else:
        asset_diagnostics.append(f"converted_from:{extension or 'unknown'}")
    return payload, "png", pixmap.width, pixmap.height, "image/png", asset_diagnostics


def _write_asset(
    *,
    kind: str,
    payload: bytes,
    extension: str,
    media_type: str,
    width: int,
    height: int,
    content_hash: str,
    output_dir: Path,
    source_xref: Optional[int],
    source_page: int,
    diagnostics: list[str],
    asset_index: int,
) -> VisualAsset:
    file_name = f"{kind}-{asset_index:06d}-{content_hash[:12]}.{extension}"
    (output_dir / file_name).write_bytes(payload)
    return VisualAsset(
        id=f"asset-{asset_index:06d}",
        kind=kind,
        file_name=file_name,
        media_type=media_type,
        width=width,
        height=height,
        byte_size=len(payload),
        content_hash=content_hash,
        source_xref=source_xref,
        source_pages=[source_page],
        diagnostics=diagnostics,
    )


def _diagram_candidates(page: Any) -> list[fitz.Rect]:
    drawings = [drawing for drawing in page.get_drawings() if drawing.get("rect") is not None]
    if not drawings:
        return []

    rects = [drawing["rect"] for drawing in drawings if _looks_like_diagram_region(drawing)]
    return _merge_overlapping_rects(rects)


def _looks_like_diagram_region(drawing: dict[str, Any]) -> bool:
    rect = drawing["rect"]
    if rect.width < MIN_DIAGRAM_WIDTH or rect.height < MIN_DIAGRAM_HEIGHT:
        return False
    if _rect_area(rect) >= MIN_DIAGRAM_AREA:
        return True
    return len(drawing.get("items", [])) >= 4


def _merge_overlapping_rects(rects: list[fitz.Rect]) -> list[fitz.Rect]:
    merged: list[fitz.Rect] = []
    for rect in sorted(rects, key=lambda item: (item.y0, item.x0)):
        current = fitz.Rect(rect)
        for index, existing in enumerate(merged):
            if existing.intersects(current) or _rect_gap(existing, current) <= 6.0:
                merged[index] = existing | current
                break
        else:
            merged.append(current)
    return merged


def _rect_gap(left: fitz.Rect, right: fitz.Rect) -> float:
    if left.intersects(right):
        return 0.0
    dx = max(left.x0 - right.x1, right.x0 - left.x1, 0.0)
    dy = max(left.y0 - right.y1, right.y0 - left.y1, 0.0)
    return (dx**2 + dy**2) ** 0.5


def _pad_rect(rect: fitz.Rect, page_rect: fitz.Rect, padding: float) -> fitz.Rect:
    padded = fitz.Rect(
        rect.x0 - padding,
        rect.y0 - padding,
        rect.x1 + padding,
        rect.y1 + padding,
    )
    return padded & page_rect


def _add_source_page(asset: VisualAsset, page_number: int) -> VisualAsset:
    if page_number in asset.source_pages:
        return asset
    return replace(asset, source_pages=[*asset.source_pages, page_number])


def _dimension_diagnostics(width: int, height: int) -> list[str]:
    if _is_oversized(width, height):
        return [f"large_visual_asset:{width}x{height}"]
    return []


def _is_oversized(width: int, height: int) -> bool:
    return max(width, height) > MAX_IMAGE_DIMENSION


def _epub_pixmap(document: Any, xref: int) -> fitz.Pixmap:
    pixmap = fitz.Pixmap(document, xref)
    if pixmap.colorspace is None or pixmap.n - pixmap.alpha > 3:
        return fitz.Pixmap(fitz.csRGB, pixmap)
    return pixmap


def _shrink_to_limit(pixmap: fitz.Pixmap, max_dimension: int) -> None:
    factor = 0
    largest = max(pixmap.width, pixmap.height)
    while largest > max_dimension:
        factor += 1
        largest //= 2
    if factor:
        pixmap.shrink(factor)


def _normalize_extension(extension: str) -> str:
    normalized = extension.lower().lstrip(".")
    if normalized == "jpeg":
        return "jpg"
    return normalized


def _rect_area(rect: fitz.Rect) -> float:
    return float(rect.width * rect.height)


def _bbox(value: Any) -> BBox:
    rect = fitz.Rect(value)
    return (
        round(float(rect.x0), 3),
        round(float(rect.y0), 3),
        round(float(rect.x1), 3),
        round(float(rect.y1), 3),
    )
