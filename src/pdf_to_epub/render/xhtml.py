"""Render the document model to EPUB 3 XHTML and CSS files."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from typing import Optional

from pdf_to_epub.document.models import DocumentBlock, DocumentModel, DocumentSection

CSS_PATH = "styles/book.css"
NAV_PATH = "nav.xhtml"


@dataclass(frozen=True)
class RenderedFile:
    href: str
    media_type: str
    content: str
    id: str
    properties: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class RenderedBook:
    xhtml_files: list[RenderedFile]
    css: RenderedFile
    nav: RenderedFile
    diagnostics: list[str] = field(default_factory=list)


def render_book(model: DocumentModel) -> RenderedBook:
    xhtml_files = [
        RenderedFile(
            href=f"text/chapter-{index:03d}.xhtml",
            media_type="application/xhtml+xml",
            content=_render_section(model, section, index),
            id=f"chapter-{index:03d}",
        )
        for index, section in enumerate(model.sections, start=1)
    ]
    css = RenderedFile(
        href=CSS_PATH,
        media_type="text/css",
        content=_book_css(),
        id="css-book",
    )
    nav = RenderedFile(
        href=NAV_PATH,
        media_type="application/xhtml+xml",
        content=_render_nav(model),
        id="nav",
        properties=["nav"],
    )
    return RenderedBook(
        xhtml_files=xhtml_files,
        css=css,
        nav=nav,
        diagnostics=[
            f"xhtml_files:{len(xhtml_files)}",
            f"nav_entries:{len(model.toc)}",
        ],
    )


def _render_section(model: DocumentModel, section: DocumentSection, index: int) -> str:
    title = section.title or model.metadata.get("title", "Untitled")
    asset_file_by_id = {asset.id: asset.file_name for asset in model.assets}
    blocks = "\n".join(_render_block(block, asset_file_by_id) for block in section.blocks)
    return _xhtml_document(
        title=title,
        body=f'<section id="{_xml_id(section.id)}">\n{blocks}\n</section>',
        css_href="../styles/book.css",
    )


def _render_block(block: DocumentBlock, asset_file_by_id: dict[str, str]) -> str:
    block_id = _xml_id(block.id)
    if block.type == "paragraph":
        return f'<p id="{block_id}">{_text(block.text)}</p>'
    if block.type == "heading":
        level = min(max(block.level or 1, 1), 6)
        return f'<h{level} id="{block_id}">{_text(block.text)}</h{level}>'
    if block.type == "code_block":
        return f'<pre id="{block_id}"><code>{_text(block.text)}</code></pre>'
    if block.type == "blockquote":
        return f'<blockquote id="{block_id}"><p>{_text(block.text)}</p></blockquote>'
    if block.type == "list":
        return _render_list(block)
    if block.type == "list_item":
        return f'<p id="{block_id}">{_text(block.text)}</p>'
    if block.type == "figure":
        return _render_figure(block, asset_file_by_id)
    if block.type == "page_break":
        page = block.source_pages[0] if block.source_pages else 0
        return f'<span id="{block_id}" epub:type="pagebreak" title="{page}"></span>'
    if block.type == "horizontal_rule":
        return f'<hr id="{block_id}" />'
    return f'<p id="{block_id}" class="unknown">{_text(block.text)}</p>'


def _render_list(block: DocumentBlock) -> str:
    tag = "ol" if any("list_inferred:ordered" in item for item in block.diagnostics) else "ul"
    items = "\n".join(
        f'<li id="{_xml_id(child.id)}">{_text(child.text)}</li>' for child in block.children
    )
    return f'<{tag} id="{_xml_id(block.id)}">\n{items}\n</{tag}>'


def _render_figure(block: DocumentBlock, asset_file_by_id: dict[str, str]) -> str:
    figure_id = _xml_id(block.id)
    alt_text = block.caption or _generic_alt_text(block)
    image = ""
    if block.asset_id:
        file_name = asset_file_by_id.get(block.asset_id, block.asset_id)
        image = f'<img src="../images/{_attr(file_name)}" alt="{_attr(alt_text)}" />'
    elif block.asset_ref:
        image = f'<img src="../{_attr(block.asset_ref)}" alt="{_attr(alt_text)}" />'
    caption = f"<figcaption>{_text(block.caption)}</figcaption>" if block.caption else ""
    return f'<figure id="{figure_id}">{image}{caption}</figure>'


def _render_nav(model: DocumentModel) -> str:
    title = model.metadata.get("title", "Untitled")
    entries = []
    if model.toc:
        for entry in model.toc:
            href = _href_for_section(model, entry.section_id, entry.block_id)
            entries.append(f'<li><a href="{_attr(href)}">{_text(entry.title)}</a></li>')
    else:
        for index, section in enumerate(model.sections, start=1):
            entries.append(
                f'<li><a href="text/chapter-{index:03d}.xhtml">{_text(section.title)}</a></li>'
            )
    nav_body = '<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>\n'
    nav_body += "\n".join(entries)
    nav_body += "\n</ol></nav>"
    return _xhtml_document(title=f"{title} Contents", body=nav_body, css_href="styles/book.css")


def _href_for_section(model: DocumentModel, section_id: str, block_id: Optional[str]) -> str:
    for index, section in enumerate(model.sections, start=1):
        if section.id == section_id:
            anchor = f"#{_xml_id(block_id)}" if block_id else ""
            return f"text/chapter-{index:03d}.xhtml{anchor}"
    return "text/chapter-001.xhtml"


def _xhtml_document(*, title: str, body: str, css_href: str) -> str:
    return (
        '<?xml version="1.0" encoding="utf-8"?>\n'
        "<!DOCTYPE html>\n"
        '<html xmlns="http://www.w3.org/1999/xhtml" '
        'xmlns:epub="http://www.idpf.org/2007/ops" xml:lang="en" lang="en">\n'
        "<head>\n"
        f"<title>{_text(title)}</title>\n"
        '<meta charset="utf-8" />\n'
        f'<link rel="stylesheet" type="text/css" href="{_attr(css_href)}" />\n'
        "</head>\n"
        f"<body>\n{body}\n</body>\n"
        "</html>\n"
    )


def _book_css() -> str:
    return """body {
  font-family: serif;
  line-height: 1.45;
  margin: 0 5%;
}

h1, h2, h3, h4, h5, h6 {
  break-after: avoid;
  line-height: 1.2;
  margin: 1.4em 0 0.45em;
}

p {
  margin: 0 0 0.8em;
}

pre {
  background: #f4f4f4;
  border: 1px solid #d8d8d8;
  font-family: monospace;
  overflow-x: auto;
  padding: 0.8em;
  white-space: pre-wrap;
}

figure {
  margin: 1em 0;
  text-align: center;
}

img {
  height: auto;
  max-width: 100%;
}

figcaption {
  font-size: 0.9em;
  margin-top: 0.4em;
}

blockquote {
  border-left: 0.25em solid #999;
  margin: 1em 0;
  padding-left: 1em;
}

.unknown {
  color: #444;
}
"""


def _generic_alt_text(block: DocumentBlock) -> str:
    if block.source_pages:
        return f"Figure from page {block.source_pages[0]}"
    return "Figure"


def _xml_id(value: Optional[str]) -> str:
    cleaned = "".join(char if char.isalnum() or char in "-_." else "-" for char in value or "id")
    if cleaned and cleaned[0].isdigit():
        return f"id-{cleaned}"
    return cleaned or "id"


def _text(value: Optional[str]) -> str:
    return escape(value or "", quote=False)


def _attr(value: Optional[str]) -> str:
    return escape(value or "", quote=True)
