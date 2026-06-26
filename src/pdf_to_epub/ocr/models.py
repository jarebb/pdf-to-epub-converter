"""OCR fallback report models."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class OcrPageReport:
    source_page: int
    status: str
    word_count: int = 0
    confidence: Optional[float] = None
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "source_page": self.source_page,
            "status": self.status,
            "word_count": self.word_count,
            "confidence": self.confidence,
            "diagnostics": self.diagnostics,
        }


@dataclass(frozen=True)
class OcrDocumentReport:
    page_count: int
    attempted_pages: list[int] = field(default_factory=list)
    skipped_pages: list[int] = field(default_factory=list)
    pages: list[OcrPageReport] = field(default_factory=list)
    diagnostics: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "page_count": self.page_count,
            "attempted_pages": self.attempted_pages,
            "skipped_pages": self.skipped_pages,
            "pages": [page.to_dict() for page in self.pages],
            "diagnostics": self.diagnostics,
        }
