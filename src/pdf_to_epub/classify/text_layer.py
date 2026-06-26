"""Text-layer metrics for page classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class TextLayerMetrics:
    char_count: int
    non_whitespace_char_count: int
    word_count: int
    replacement_char_count: int
    replacement_char_ratio: float
    sample: str

    def to_dict(self) -> dict[str, object]:
        return {
            "char_count": self.char_count,
            "non_whitespace_char_count": self.non_whitespace_char_count,
            "word_count": self.word_count,
            "replacement_char_count": self.replacement_char_count,
            "replacement_char_ratio": self.replacement_char_ratio,
            "sample": self.sample,
        }


def extract_text_layer_metrics(page: Any) -> TextLayerMetrics:
    text = page.get_text("text") or ""
    words = page.get_text("words") or []
    non_whitespace = "".join(text.split())
    replacement_char_count = text.count("\ufffd")
    char_count = len(text)
    replacement_char_ratio = 0.0
    if char_count:
        replacement_char_ratio = replacement_char_count / char_count

    return TextLayerMetrics(
        char_count=char_count,
        non_whitespace_char_count=len(non_whitespace),
        word_count=len(words),
        replacement_char_count=replacement_char_count,
        replacement_char_ratio=round(replacement_char_ratio, 4),
        sample=_sample_text(text),
    )


def _sample_text(text: str, limit: int = 120) -> str:
    collapsed = " ".join(text.split())
    return collapsed[:limit]
