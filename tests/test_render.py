from pdf_to_epub.document.models import DocumentBlock, DocumentModel, DocumentSection
from pdf_to_epub.render.xhtml import render_book


def test_render_book_outputs_semantic_xhtml_css_and_nav() -> None:
    model = DocumentModel(
        metadata={"title": "Render Test", "language": "en"},
        page_count=1,
        sections=[
            DocumentSection(
                id="sec-0001",
                title="Chapter 1",
                level=1,
                source_pages=[1],
                blocks=[
                    DocumentBlock(
                        id="doc-000001",
                        type="heading",
                        text="Chapter 1",
                        level=1,
                        source_pages=[1],
                    ),
                    DocumentBlock(
                        id="doc-000002",
                        type="paragraph",
                        text="A <safe> paragraph & text.",
                        source_pages=[1],
                    ),
                    DocumentBlock(
                        id="doc-000003",
                        type="list",
                        text="",
                        source_pages=[1],
                        diagnostics=["list_inferred:ordered"],
                        children=[
                            DocumentBlock(
                                id="doc-000004",
                                type="list_item",
                                text="First",
                                source_pages=[1],
                            )
                        ],
                    ),
                ],
            )
        ],
    )

    rendered = render_book(model)

    assert rendered.css.href == "styles/book.css"
    assert rendered.nav.properties == ["nav"]
    assert len(rendered.xhtml_files) == 1
    chapter = rendered.xhtml_files[0].content
    assert "<h1" in chapter
    assert "A &lt;safe&gt; paragraph &amp; text." in chapter
    assert "<ol" in chapter
    assert "<li" in chapter
