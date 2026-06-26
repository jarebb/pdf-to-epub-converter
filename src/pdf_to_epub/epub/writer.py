"""Deterministic EPUB 3 package writer."""

from __future__ import annotations

import uuid
import zipfile
from datetime import datetime, timezone
from html import escape
from pathlib import Path

from pdf_to_epub.document.models import DocumentAsset, DocumentModel
from pdf_to_epub.render.xhtml import RenderedBook, RenderedFile, render_book

EPUB_CONTAINER_XML = """<?xml version="1.0" encoding="utf-8"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml" />
  </rootfiles>
</container>
"""


class EpubAssemblyError(RuntimeError):
    """Raised when an EPUB cannot be assembled completely."""


def write_epub(model: DocumentModel, output_path: Path) -> Path:
    output_path = output_path.expanduser()
    if output_path.suffix.lower() != ".epub":
        raise EpubAssemblyError(f"output path must end with .epub: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    rendered = render_book(model)
    _validate_assets(model.assets)
    package_opf = _package_opf(model, rendered)

    with zipfile.ZipFile(output_path, "w", compression=zipfile.ZIP_DEFLATED) as epub:
        epub.writestr(
            zipfile.ZipInfo("mimetype"),
            "application/epub+zip",
            compress_type=zipfile.ZIP_STORED,
        )
        epub.writestr("META-INF/container.xml", EPUB_CONTAINER_XML)
        epub.writestr("EPUB/package.opf", package_opf)
        epub.writestr(f"EPUB/{rendered.nav.href}", rendered.nav.content)
        epub.writestr(f"EPUB/{rendered.css.href}", rendered.css.content)
        for item in rendered.xhtml_files:
            epub.writestr(f"EPUB/{item.href}", item.content)
        for asset in model.assets:
            source_path = Path(asset.source_path or "")
            epub.write(source_path, f"EPUB/images/{asset.file_name}")

    return output_path


def _validate_assets(assets: list[DocumentAsset]) -> None:
    for asset in assets:
        if not asset.source_path:
            raise EpubAssemblyError(f"asset has no source path: {asset.id}")
        source_path = Path(asset.source_path)
        if not source_path.is_file():
            raise EpubAssemblyError(f"asset file does not exist: {source_path}")


def _package_opf(model: DocumentModel, rendered: RenderedBook) -> str:
    identifier = _identifier(model)
    modified = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    manifest_items = [
        _manifest_item(rendered.nav),
        _manifest_item(rendered.css),
        *[_manifest_item(item) for item in rendered.xhtml_files],
        *[_asset_manifest_item(asset) for asset in model.assets],
    ]
    spine_items = [f'    <itemref idref="{_attr(item.id)}" />' for item in rendered.xhtml_files]
    title = model.metadata.get("title") or "Untitled"
    language = model.metadata.get("language") or "en"
    author = model.metadata.get("author") or ""
    creator = f"\n    <dc:creator>{_text(author)}</dc:creator>" if author else ""

    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<package xmlns="http://www.idpf.org/2007/opf" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" version="3.0" '
        'unique-identifier="pub-id">\n'
        "  <metadata>\n"
        f'    <dc:identifier id="pub-id">{_text(identifier)}</dc:identifier>\n'
        f"    <dc:title>{_text(title)}</dc:title>\n"
        f"    <dc:language>{_text(language)}</dc:language>"
        f"{creator}\n"
        f'    <meta property="dcterms:modified">{_text(modified)}</meta>\n'
        "  </metadata>\n"
        "  <manifest>\n" + "\n".join(manifest_items) + "\n  </manifest>\n"
        "  <spine>\n" + "\n".join(spine_items) + "\n  </spine>\n"
        "</package>\n"
    )


def _manifest_item(file: RenderedFile) -> str:
    properties = (
        f' properties="{" ".join(_attr(item) for item in file.properties)}"'
        if file.properties
        else ""
    )
    return (
        f'    <item id="{_attr(file.id)}" href="{_attr(file.href)}" '
        f'media-type="{_attr(file.media_type)}"{properties} />'
    )


def _asset_manifest_item(asset: DocumentAsset) -> str:
    return (
        f'    <item id="{_attr(asset.id)}" href="images/{_attr(asset.file_name)}" '
        f'media-type="{_attr(asset.media_type)}" />'
    )


def _identifier(model: DocumentModel) -> str:
    title = model.metadata.get("title") or "Untitled"
    return f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, title)}"


def _text(value: str) -> str:
    return escape(value, quote=False)


def _attr(value: str) -> str:
    return escape(value, quote=True)
