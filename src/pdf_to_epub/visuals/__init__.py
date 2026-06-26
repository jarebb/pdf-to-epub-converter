"""Image and diagram extraction stage."""

from pdf_to_epub.visuals.asset_extractor import extract_visual_assets
from pdf_to_epub.visuals.models import VisualAsset, VisualAssetManifest, VisualPlacement

__all__ = [
    "VisualAsset",
    "VisualAssetManifest",
    "VisualPlacement",
    "extract_visual_assets",
]
