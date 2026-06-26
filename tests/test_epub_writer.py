import zipfile
from pathlib import Path

import pytest

from pdf_to_epub.document.models import DocumentAsset, DocumentBlock, DocumentModel, DocumentSection
from pdf_to_epub.epub.writer import EpubAssemblyError, write_epub


def test_write_epub_creates_expected_package(tmp_path: Path) -> None:
    image_path = tmp_path / "image.png"
    image_path.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01")
    model = DocumentModel(
        metadata={"title": "Package Test", "language": "en"},
        page_count=1,
        assets=[
            DocumentAsset(
                id="asset-000001",
                kind="embedded_image",
                file_name="image.png",
                media_type="image/png",
                width=1,
                height=1,
                source_path=str(image_path),
                source_pages=[1],
            )
        ],
        sections=[
            DocumentSection(
                id="sec-0001",
                title="Chapter 1",
                level=1,
                source_pages=[1],
                blocks=[
                    DocumentBlock(
                        id="doc-000001",
                        type="paragraph",
                        text="Hello EPUB",
                        source_pages=[1],
                    )
                ],
            )
        ],
    )
    output_path = tmp_path / "book.epub"

    write_epub(model, output_path)

    with zipfile.ZipFile(output_path) as epub:
        names = epub.namelist()
        assert names[0] == "mimetype"
        assert epub.read("mimetype") == b"application/epub+zip"
        assert "META-INF/container.xml" in names
        assert "EPUB/package.opf" in names
        assert "EPUB/nav.xhtml" in names
        assert "EPUB/styles/book.css" in names
        assert "EPUB/text/chapter-001.xhtml" in names
        assert "EPUB/images/image.png" in names
        package = epub.read("EPUB/package.opf").decode("utf-8")
        assert 'properties="nav"' in package
        assert 'href="images/image.png"' in package


def test_write_epub_fails_for_missing_asset(tmp_path: Path) -> None:
    model = DocumentModel(
        metadata={"title": "Missing Asset", "language": "en"},
        page_count=1,
        assets=[
            DocumentAsset(
                id="asset-000001",
                kind="embedded_image",
                file_name="missing.png",
                media_type="image/png",
                width=1,
                height=1,
                source_path=str(tmp_path / "missing.png"),
            )
        ],
    )

    with pytest.raises(EpubAssemblyError, match="asset file does not exist"):
        write_epub(model, tmp_path / "book.epub")
