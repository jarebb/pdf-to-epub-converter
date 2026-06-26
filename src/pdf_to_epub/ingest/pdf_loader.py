"""Stage A PDF ingest implementation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import fitz

from pdf_to_epub.ingest.metadata import normalize_pdf_metadata
from pdf_to_epub.ingest.permissions import (
    PermissionSummary,
    authenticate_document,
    summarize_permissions,
)


class IngestError(RuntimeError):
    """Raised when the input PDF cannot be ingested safely."""


@dataclass(frozen=True)
class PageSummary:
    index: int
    number: int
    width: float
    height: float
    rotation: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "index": self.index,
            "number": self.number,
            "width": self.width,
            "height": self.height,
            "rotation": self.rotation,
        }


@dataclass(frozen=True)
class OutlineItem:
    level: int
    title: str
    page_number: int

    def to_dict(self) -> Dict[str, object]:
        return {
            "level": self.level,
            "title": self.title,
            "page_number": self.page_number,
        }


@dataclass(frozen=True)
class IngestResult:
    input_path: str
    file_size_bytes: int
    page_count: int
    metadata: Dict[str, str]
    permissions: PermissionSummary
    pages: List[PageSummary] = field(default_factory=list)
    outline: List[OutlineItem] = field(default_factory=list)
    xmp_metadata_present: bool = False

    def to_dict(self) -> Dict[str, object]:
        return {
            "input_path": self.input_path,
            "file_size_bytes": self.file_size_bytes,
            "page_count": self.page_count,
            "metadata": self.metadata,
            "permissions": self.permissions.to_dict(),
            "pages": [page.to_dict() for page in self.pages],
            "outline": [item.to_dict() for item in self.outline],
            "xmp_metadata_present": self.xmp_metadata_present,
        }


def ingest_pdf(input_path: Path, password: Optional[str] = None) -> IngestResult:
    path = input_path.expanduser()
    if not path.exists():
        raise IngestError(f"input PDF does not exist: {path}")
    if not path.is_file():
        raise IngestError(f"input path is not a file: {path}")
    if path.suffix.lower() != ".pdf":
        raise IngestError(f"input path must point to a PDF file: {path}")

    try:
        document = fitz.open(path)
    except Exception as exc:  # pragma: no cover - exact PyMuPDF exception varies.
        raise IngestError(f"failed to open PDF: {exc}") from exc

    try:
        authenticated = authenticate_document(document, password)
        permissions = summarize_permissions(document, authenticated=authenticated)
        if permissions.needs_password and not authenticated:
            raise IngestError("PDF is encrypted and requires a valid password")
        if not permissions.can_extract and not permissions.can_access:
            raise IngestError("PDF permissions do not allow text/content extraction")

        metadata = normalize_pdf_metadata(document.metadata or {}, path)
        pages = [_summarize_page(document, index) for index in range(document.page_count)]
        outline = _summarize_outline(document)
        xmp_metadata_present = bool(_get_xmp_metadata(document))

        return IngestResult(
            input_path=str(path.resolve()),
            file_size_bytes=path.stat().st_size,
            page_count=document.page_count,
            metadata=metadata,
            permissions=permissions,
            pages=pages,
            outline=outline,
            xmp_metadata_present=xmp_metadata_present,
        )
    finally:
        document.close()


def _summarize_page(document: Any, index: int) -> PageSummary:
    page = document.load_page(index)
    rect = page.rect
    return PageSummary(
        index=index,
        number=index + 1,
        width=round(float(rect.width), 3),
        height=round(float(rect.height), 3),
        rotation=int(page.rotation or 0),
    )


def _summarize_outline(document: Any) -> List[OutlineItem]:
    items: List[OutlineItem] = []
    for raw in document.get_toc(simple=True):
        if len(raw) < 3:
            continue
        level, title, page_number = raw[:3]
        title = str(title).strip()
        if not title:
            continue
        items.append(
            OutlineItem(
                level=int(level),
                title=title,
                page_number=int(page_number),
            )
        )
    return items


def _get_xmp_metadata(document: Any) -> str:
    try:
        return document.get_xml_metadata() or ""
    except Exception:
        return ""
