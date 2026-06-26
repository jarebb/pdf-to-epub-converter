"""Image coverage metrics for page classification."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ImageCoverageMetrics:
    image_count: int
    image_area_ratio: float
    full_page_image: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "image_count": self.image_count,
            "image_area_ratio": self.image_area_ratio,
            "full_page_image": self.full_page_image,
        }


def extract_image_coverage_metrics(page: Any) -> ImageCoverageMetrics:
    page_area = float(page.rect.width * page.rect.height)
    images = page.get_images(full=True)
    image_area = 0.0

    for image in images:
        xref = int(image[0])
        for rect in page.get_image_rects(xref):
            image_area += float(rect.width * rect.height)

    image_area_ratio = 0.0 if page_area <= 0 else min(image_area / page_area, 1.0)
    rounded_ratio = round(image_area_ratio, 4)

    return ImageCoverageMetrics(
        image_count=len(images),
        image_area_ratio=rounded_ratio,
        full_page_image=rounded_ratio >= 0.85,
    )
