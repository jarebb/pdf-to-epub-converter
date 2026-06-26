# PDF-to-EPUB Converter Technical Plan

## Current Decisions

- Primary goal: convert PDF file paths into high-quality, valid EPUB 3 files.
- First target: books, especially programming books.
- Sample input: `assets/Continuous Delivery Reliable Software Releases through Build, Test, and Deployment Automation by Jez Humble, David Farley (z-lib.org).pdf`.
- Language: Python.
- Runtime target: AWS EC2 `t3.xlarge`, 4 vCPU, 16 GB RAM, CPU only, burstable.
- No cloud or proprietary LLM APIs.
- Heuristics-first design.
- Optional local LLM is not part of MVP.
- OCR is deferred to a later milestone.
- Default language: English (`en`).
- Blocking errors should stop conversion. Do not write best-effort EPUBs in the initial version.

## 1. PDF Realities and Challenges

PDF is a fixed-layout presentation format. EPUB 3 is a semantic, ordered, reflowable publication format. The converter must infer semantic structure from page coordinates, text spans, fonts, spacing, images, drawing commands, outlines, and metadata.

Important realities:

- PDF reading order is not guaranteed by the file.
- A paragraph may be split into many text drawing operations.
- Multi-column layouts require region and column reconstruction.
- Headers, footers, running titles, and page numbers are usually normal text blocks that must be removed from the reading stream.
- De-hyphenation must be conservative to avoid corrupting intentional hyphenated words.
- Ligatures should be normalized for EPUB text quality.
- Tables may be represented by text positions, ruling lines, rectangles, or images.
- Native PDF vector diagrams do not necessarily have reusable image files.
- Tagged PDF structure, when present, can be incomplete or wrong.
- Perfect reconstruction is impossible for arbitrary PDFs.

Initial book-focused assumptions:

- The MVP should optimize for born-digital books with extractable text.
- Programming books often include headings, code blocks, figures, tables, callouts, and footnotes.
- The converter should preserve readability and structure rather than exact visual layout.
- OCR should not run in the first implementation path.

Born-digital, scanned, and mixed policy:

- Born-digital pages with meaningful extractable text: extract directly.
- Scanned/image-only pages: later OCR fallback.
- Mixed pages: extract direct text and source images; later OCR only truly textless regions/pages.
- OCR must never run merely because a page contains images.

Image and diagram policy:

- Embedded raster images: extract and embed original image asset where EPUB-compatible.
- Unsupported image formats: convert to PNG/JPEG.
- Native vector diagrams: rasterize only the detected diagram bounding region to PNG.
- Do not vectorize, redraw, or semantically interpret diagrams.
- Preserve placement relative to surrounding text.
- Attach captions when detectable.
- Derive alt text from source alt metadata or captions; otherwise use conservative generic alt text.

## 2. Architecture and Pipeline

The pipeline should be modular and centered on an intermediate document model. Stages should be independently testable and swappable.

### Stage A: Ingest

Responsibilities:

- Validate input path.
- Open PDF.
- Detect encryption and extraction permissions.
- Read page count, page sizes, rotations, metadata, and PDF outlines/bookmarks.
- Create a working directory for extracted assets and intermediate diagnostics.

Primary library:

- PyMuPDF (`fitz`).

Memory approach:

- Open the PDF once.
- Iterate page-by-page.
- Avoid loading full-document page renderings into memory.
- Store compact intermediate data.

Expected memory:

- Born-digital extraction should stay well below 1 GB for normal books.
- Image extraction and region rasterization can transiently use hundreds of MB.
- Later OCR workers should be capped because Tesseract/OCRmyPDF can be CPU and memory intensive.

### Stage B: Page Classification

Each page receives a classification:

- `born_digital_text`
- `image_only_scanned`
- `mixed_text_and_images`
- `low_confidence_text_layer`

Signals:

- Extracted character count.
- Extracted word count.
- Meaningful Unicode ratio.
- Image coverage ratio.
- Number and area of image objects.
- Presence of large full-page raster images.
- Presence of suspicious invisible or duplicate OCR text.
- Font/glyph extraction sanity.

Initial behavior:

- For pages with meaningful direct text, direct extraction is used.
- For image-only pages, mark as requiring OCR later and fail or skip based on MVP policy.
- Because OCR is deferred, the MVP should report unsupported scanned pages clearly.

### Stage C: Text and Layout Extraction

Primary extraction:

- Use PyMuPDF for blocks, words, spans, fonts, geometry, images, drawings, metadata, outlines, and rendering.

Secondary extraction:

- Use pdfplumber for table-heavy pages, char-level diagnostics, line/rect inspection, and table candidates.

Fallback diagnostics:

- Use pdfminer.six when PyMuPDF output appears corrupted, sparse, or suspicious.

Per-page model:

```text
PageModel
  page_number
  width
  height
  rotation
  classification
  blocks[]
  images[]
  drawings[]
  diagnostics[]
```

Block model:

```text
Block
  id
  type
  bbox
  source_page
  text
  lines[]
  spans[]
  style_features
  asset_ref
  confidence
```

Style features:

- Font size.
- Font name.
- Bold/italic inference.
- Monospace inference.
- Text color.
- Indentation.
- Alignment.
- Line spacing.
- All-caps/small-caps signals.
- Superscript/subscript signals.

### Stage D: Reading Order Reconstruction

Book-first MVP:

- Start with single-column and mostly linear book layouts.
- Handle full-width headings, paragraphs, figures, captions, code blocks, and simple tables.

Algorithm:

1. Normalize page coordinates for rotation.
2. Detect repeated headers, footers, running titles, and page numbers across pages.
3. Remove repeated artifacts from the reading stream.
4. Group words/spans into lines.
5. Group lines into blocks.
6. Detect columns if needed, but keep MVP focused on one main reading column.
7. Sort blocks by reading order.
8. Attach nearby captions to figures/tables.
9. Preserve page break anchors separately from content text.
10. Record confidence and diagnostics.

Header/footer detection:

- Compare text signatures in top and bottom page bands.
- Use repeated normalized strings.
- Consider stable y-position and font size.
- Avoid deleting chapter titles that appear only once.

De-hyphenation:

- Merge line-final hyphen only when next line starts lowercase and combined token passes conservative checks.
- Preserve intentional hyphens in compounds where confidence is low.
- Track each merge in diagnostics for debugging.

Ligature normalization:

- Normalize common ligatures such as `fi`, `fl`, `ff`, `ffi`, and `ffl`.
- Preserve original source text in debug output if needed.

### Stage E: Image and Diagram Extraction

Embedded images:

- Extract original image streams with PyMuPDF.
- Deduplicate by content hash.
- Preserve format when EPUB-compatible and reasonable.
- Convert unsupported formats to PNG/JPEG.
- Cap extremely large dimensions where needed, preserving aspect ratio.

Vector diagrams:

- Inspect drawing objects and regions.
- Identify drawing-heavy regions with little text.
- Expand bounding box slightly for safe clipping.
- Rasterize the region to PNG.
- Default DPI target: 150-200 DPI.
- Use 300 DPI only for small diagrams or explicit high-quality mode.

Placement:

- Insert figures into the document model near their source position.
- Keep captions attached.
- Avoid floating layout that can confuse EPUB renderers.

Alt text:

- Prefer tagged PDF alt text if available.
- Else derive from caption.
- Else use generic `Figure from page N`.
- Do not invent diagram semantics.

### Stage F: OCR Fallback Later

OCR is deferred. When added:

- Use page classifier first.
- Run OCR only for image-only or textless pages/regions.
- Do not OCR born-digital pages with meaningful text.
- Prefer OCRmyPDF for scanned/mixed document normalization.
- Use Tesseract/pytesseract for targeted page or region OCR.
- Cap OCR parallelism to 1-2 workers on `t3.xlarge`.
- Track OCR pages and confidence in the report.

MVP behavior before OCR:

- If a PDF is primarily scanned/image-only, fail with a clear message.
- If isolated pages are image-only, decide whether to fail or emit placeholder diagnostics before implementation. Current default should be fail because best-effort output is not desired.

### Stage G: Intermediate Document Model

The document model is the contract between extraction/analysis and EPUB rendering.

```text
DocumentModel
  metadata
  assets
  sections[]
  toc[]
  notes[]
  diagnostics[]
```

Section:

```text
Section
  id
  title
  level
  source_pages
  blocks[]
```

Block types:

- paragraph
- heading
- code_block
- list
- list_item
- table
- figure
- blockquote
- footnote
- page_break
- horizontal_rule
- unknown

Reasons for this model:

- Extraction stages can change without rewriting EPUB output.
- EPUB writer can be tested with synthetic document models.
- Quality diagnostics can refer to stable block IDs.
- Later OCR or advanced extraction backends can feed the same renderer.

### Stage H: Structure Detection

Use document-level statistics:

- Body font size mode.
- Common line height.
- Common left margin.
- Font size distribution.
- Bold/italic/monospace patterns.
- Repeated page artifacts.
- PDF outline/bookmark data.
- Numbering patterns.

Headings:

- Larger than body text.
- Bold or distinct font.
- Extra spacing before/after.
- Shorter isolated blocks.
- Matches chapter/section patterns.
- Present in PDF outline.

Chapter detection:

- Prefer PDF outline when it is sane.
- Else infer top-level headings.
- Split EPUB XHTML files at chapter boundaries.
- Keep generated XHTML files moderately sized.

Programming book structures:

- Code blocks:
  - Monospace font.
  - Consistent indentation.
  - Smaller font.
  - Often inside shaded/ruled regions.
  - Preserve whitespace with `<pre><code>`.
- Callouts:
  - Indented or bordered blocks.
  - Distinct background or smaller font.
  - Render as `<aside>` or styled blockquote when clear.
- Lists:
  - Bullet/number markers.
  - Hanging indent.
  - Consecutive aligned items.
- Tables:
  - Use pdfplumber for candidates.
  - Emit HTML tables when confidence is high.
  - Rasterize table region as fallback later if semantic extraction is poor.
- Footnotes:
  - Detect smaller bottom-page text.
  - Match superscript references.
  - Use EPUB note links when confidence is high.

### Stage I: XHTML and CSS Reconstruction

Output should be semantic EPUB 3 XHTML.

Mappings:

- Paragraph: `<p>`
- Heading: `<h1>` through `<h6>`
- Code block: `<pre><code>`
- Figure: `<figure><img/><figcaption>`
- Table: `<table>`
- List: `<ol>` / `<ul>`
- Blockquote: `<blockquote>`
- Aside/callout: `<aside>`
- Footnote ref: `epub:type="noteref"` where practical
- Page break: page-list/nav anchors later

CSS principles:

- Reader-friendly, reflowable, minimal.
- Preserve styling intent, not exact PDF coordinates.
- Avoid absolute positioning in MVP.
- Use relative units.
- Keep images responsive with `max-width: 100%`.
- Preserve code whitespace and readable monospace styling.
- Keep tables readable, with horizontal overflow handling if needed.

### Stage J: EPUB Assembly

Preferred approach:

- Hand-build EPUB 3 package for deterministic control.
- Use open-source EPUB examples/spec references as needed.
- Consider EbookLib only as a reference or prototype helper.

EPUB layout:

```text
mimetype
META-INF/container.xml
EPUB/package.opf
EPUB/nav.xhtml
EPUB/styles/book.css
EPUB/text/chapter-001.xhtml
EPUB/text/chapter-002.xhtml
EPUB/images/...
```

Important packaging rules:

- `mimetype` must be the first ZIP entry and uncompressed.
- OPF manifest must include all XHTML, CSS, nav, and image assets.
- Spine order must match reading order.
- XHTML must be valid XML.
- `nav.xhtml` must be included and marked as nav.
- Metadata must include identifier, title, language, and modified date.

### Stage K: Validation and Reporting

Validation:

- Run EPUBCheck via subprocess.
- Treat EPUBCheck errors as blocking.
- Do not save best-effort EPUBs in the initial version.
- Warnings should be included in the report and can be promoted later if they cause renderer problems.

Quality report:

```text
report.json
  input_path
  output_path
  page_count
  classifications
  metadata
  toc_source
  headings_detected
  images_extracted
  vector_regions_rasterized
  tables_detected
  code_blocks_detected
  headers_footers_removed
  low_confidence_blocks
  unsupported_pages
  epubcheck_result
  timings
  peak_memory_if_available
```

Manual renderer checks:

- Apple Books.
- Calibre.
- Kindle Previewer.
- Thorium.

Automated tests:

- Unit tests for model serialization, XHTML escaping, OPF/nav generation, and artifact detection.
- Integration tests on the sample programming book and smaller synthetic PDFs.

## 3. Library Evaluation

### PyMuPDF

Primary library for:

- PDF loading.
- Metadata.
- Outlines.
- Text blocks, words, spans, and geometry.
- Image extraction.
- Drawing/vector inspection.
- Region rendering.

Rationale:

- Fast local PDF engine.
- Good geometry access.
- Practical for CPU-only processing.

### pdfplumber

Secondary library for:

- Table-heavy pages.
- Char-level layout analysis.
- Lines, rectangles, and ruling detection.
- Diagnostics when PyMuPDF extraction is ambiguous.

Rationale:

- Useful for tables and precise layout inspection.

### pdfminer.six

Fallback/diagnostic library for:

- Comparing text extraction.
- Handling some encoding/layout cases differently than PyMuPDF.

Rationale:

- Mature source-text extraction library.

### OCRmyPDF and Tesseract

Deferred until OCR milestone.

Use for:

- Scanned/image-only pages.
- Mixed PDFs with textless pages.

Constraints:

- Conditional only.
- Never used on pages with meaningful direct text.
- Worker count capped for `t3.xlarge`.

### EPUB Writer

Preferred:

- Hand-built EPUB package writer.

Reason:

- More deterministic.
- Easier to make epubcheck-clean.
- Easier to debug OPF/nav/spine/manifest issues.

EbookLib:

- Acceptable as a reference or experiment.
- Do not depend on it if it limits EPUB 3 control.

### Docling and Marker

Not recommended for MVP.

Reasons:

- Heavier dependency stack.
- More runtime variability.
- Potentially expensive on CPU-only burstable EC2.
- May be useful later as optional comparison or enhanced backend.

### Optional Local LLM

Not worth including in MVP.

If added later:

- Off by default.
- Local only.
- Quantized <=8B.
- Batched only.
- Used only for ambiguous structural tie-breaks.
- Must never be required for completion.
- Must have deterministic heuristic fallback.
- Cache decisions.
- Disable when CPU budget or runtime risk is high.

## 4. Quality Dimensions

### Text Fidelity and Reading Order

Handled by:

- Direct text extraction.
- Page classification.
- Header/footer removal.
- Conservative de-hyphenation.
- Ligature normalization.
- Reading-order confidence.
- Diagnostic extraction comparisons.

### Structure

Handled by:

- PDF outline import.
- Heading inference.
- Chapter splitting.
- EPUB nav generation.
- Spine generation from document order.

### Styling

Handled by:

- Mapping font size/weight/italic/monospace to semantic HTML/CSS.
- Preserving code blocks.
- Preserving blockquotes/callouts when clear.
- Avoiding pixel-perfect absolute layout.

### Layout

Handled by:

- Paragraph grouping.
- List detection.
- Code block detection.
- Basic table detection.
- Figure/caption association.
- Page break anchors.

### Images and Diagrams

Handled by:

- Extracting embedded images.
- Rasterizing vector regions.
- Preserving nearby placement.
- Captions and conservative alt text.

### Metadata

Sources:

- PDF metadata.
- XMP metadata if available.
- PDF outline.
- First-page title heuristics.
- User overrides.
- Filename fallback.

Fields:

- title
- author/creator
- language, default `en`
- publisher if present
- date if present
- subject/description if present
- identifier
- cover if detected or provided

## 5. Validation and Quality Measurement

Validation gates:

- EPUBCheck must pass.
- XHTML must be valid XML.
- Manifest must include every referenced asset.
- No missing image/CSS references.
- Output should open in common readers.

Quality metrics:

- Extracted character count.
- Number of pages with meaningful text.
- Number of unsupported scanned pages.
- Heading count and TOC source.
- Images extracted.
- Tables detected.
- Code blocks detected.
- Low-confidence reading-order blocks.
- Header/footer removal patterns.
- EPUBCheck warnings/errors.

Test corpus:

- Sample programming book in `assets/`.
- Single-column novel.
- Programming book with code blocks.
- Programming book with figures and tables.
- Multi-column technical report.
- Image-heavy book/manual.
- Scanned book for later OCR milestone.
- Mixed PDF for later OCR milestone.
- Vector-diagram-heavy PDF.
- Rotated pages.
- Encrypted PDF.
- Large 500+ page PDF.

## 6. Risks and Edge Cases

Risks:

- Complex reading order.
- Incorrect heading hierarchy.
- Header/footer false positives.
- Code block corruption.
- Complex table extraction.
- Footnote/reference mismatch.
- Huge images bloating EPUB.
- Bad source encodings.
- Renderer-specific CSS quirks.
- CPU throttling on burstable EC2 during heavy extraction or later OCR.

Edge policies:

- Encrypted/DRM PDFs: refuse unless password is provided and extraction is allowed.
- Scanned/image-only PDFs before OCR milestone: fail clearly.
- Complex tables: use semantic extraction only when confident; fallback strategy to be added.
- Math/equations: preserve text when extractable; rasterize region later when necessary.
- RTL/CJK/vertical text: detect and report initially; enhance later.
- Broken metadata: use user overrides or filename fallback.

## 7. Proposed Project Structure

```text
src/
  pdf_to_epub/
    __init__.py
    cli.py

    config.py
    logging_config.py

    ingest/
      pdf_loader.py
      permissions.py
      metadata.py

    classify/
      page_classifier.py
      text_layer.py
      image_coverage.py

    extract/
      pymupdf_extractor.py
      pdfplumber_tables.py
      pdfminer_fallback.py
      images.py
      drawings.py
      ocr.py

    model/
      document.py
      blocks.py
      assets.py
      diagnostics.py
      serialization.py

    analysis/
      reading_order.py
      columns.py
      headers_footers.py
      headings.py
      lists.py
      code_blocks.py
      tables.py
      footnotes.py
      captions.py
      cleanup.py

    render/
      html_writer.py
      css_writer.py
      nav_writer.py
      opf_writer.py
      asset_writer.py
      epub_zip.py

    validate/
      epubcheck.py
      quality_report.py

    optional/
      llm_tiebreaker.py

tests/
  unit/
  integration/
  fixtures/
    pdfs/
    expected/

docs/
  TECHNICAL_PLAN.md
```

## 8. Milestones

### Milestone 1: Valid EPUB Skeleton

Goal:

- Input PDF path.
- Extract basic metadata.
- Emit minimal EPUB 3.
- Run EPUBCheck.

Scope:

- Hand-built EPUB package.
- Minimal XHTML.
- Minimal nav.
- Minimal CSS.
- Quality report shell.

Exit criteria:

- EPUB passes EPUBCheck.
- Opens in Calibre/Thorium.
- Blocking validation errors stop conversion.

### Milestone 2: Born-Digital Book Text

Goal:

- Produce readable EPUB from single-column born-digital books.

Scope:

- PyMuPDF text extraction.
- Paragraph reconstruction.
- Header/footer/page number removal.
- Conservative de-hyphenation.
- Ligature normalization.
- Basic heading detection.
- PDF outline import.

Exit criteria:

- Sample programming book produces readable chapter text.
- TOC works if outline or headings are detected.

### Milestone 3: Programming Book Features

Goal:

- Better handling for programming books.

Scope:

- Code block detection.
- Monospace preservation.
- Basic callout/block quote detection.
- Lists.
- Simple tables.

Exit criteria:

- Code samples remain readable.
- Lists and simple tables are not flattened into broken paragraphs.

### Milestone 4: Images and Captions

Goal:

- Preserve source images and diagrams.

Scope:

- Embedded raster extraction.
- Vector region rasterization.
- Figure placement.
- Caption association.
- Alt text fallback.

Exit criteria:

- Image-heavy sections of sample books render with figures in sensible locations.

### Milestone 5: Multi-Column and Complex Layouts

Goal:

- Improve technical reports and complex pages.

Scope:

- Column detection.
- Spanning heading detection.
- Sidebar handling.
- Better table fallback.

Exit criteria:

- Multi-column layouts have acceptable reading order and clear diagnostics.

### Milestone 6: OCR Fallback

Goal:

- Support scanned and mixed PDFs.

Scope:

- OCRmyPDF/Tesseract integration.
- Page-level OCR gating.
- OCR confidence/reporting.
- Worker limits for `t3.xlarge`.

Exit criteria:

- Born-digital pages never OCR.
- Scanned pages produce readable text.
- Mixed PDFs OCR only textless pages/regions.

### Milestone 7: Renderer Hardening

Goal:

- Improve Apple Books, Calibre, Kindle Previewer, and Thorium compatibility.

Scope:

- CSS compatibility.
- EPUB packaging refinements.
- Image sizing.
- Kindle-friendly behavior.
- Regression corpus.

Exit criteria:

- EPUBCheck clean.
- Manual renderer matrix documented.

### Milestone 8: Optional Advanced Backends

Goal:

- Evaluate optional non-default enhancement paths.

Scope:

- Docling/Marker experiments.
- Optional local LLM tie-breaker.
- Benchmarks against heuristic pipeline.

Exit criteria:

- Disabled by default.
- Pure heuristic path remains complete.
- Runtime and quality tradeoffs are documented.

## 9. Open Decisions Before Coding

- Confirm the first implementation should create a Python package plus CLI, likely using `pyproject.toml`.
- Choose the CLI name: proposed `pdf-to-epub`.
- Decide whether to vendor/download EPUBCheck later or require a local `epubcheck` command/Java jar path.
- Decide whether the sample PDF can be used in integration tests directly, or whether tests should use smaller generated/synthetic fixtures.
- Decide whether output should include page break anchors in MVP or defer them.
- Decide whether chapter splitting should start from PDF outline first, then heading inference, or heading inference first for programming books.

## 10. Stage A Implementation Notes

Stage A has been started with a narrow ingest package and CLI.

Implemented modules:

```text
src/
  pdf_to_epub/
    cli.py
    ingest/
      metadata.py
      permissions.py
      pdf_loader.py
```

Current behavior:

- Validates that the input exists and is a PDF file.
- Opens the PDF with PyMuPDF.
- Refuses encrypted PDFs without a valid password.
- Refuses PDFs whose permissions do not allow extraction/access.
- Reads normalized metadata with default language `en`.
- Preserves source metadata fields for audit.
- Falls back from weak embedded PDF-file-like titles to the input filename.
- Reads page count, page dimensions, page rotation, PDF outline/bookmark entries, and XMP presence.
- Classifies every page for Stage B:
  - `born_digital_text`
  - `mixed_text_and_images`
  - `low_confidence_text_layer`
  - `image_only_scanned`
  - `blank_or_unknown`
- Reports text-layer metrics, image coverage metrics, direct-extraction recommendation, and later OCR recommendation per page.
- Emits a JSON-serializable ingest result.

CLI usage:

```bash
PYTHONPATH=src python -m pdf_to_epub.cli ingest path/to/input.pdf --pretty
PYTHONPATH=src python -m pdf_to_epub.cli ingest path/to/input.pdf --report reports/ingest.json --pretty
```

Sample smoke command:

```bash
PYTHONPATH=src python -m pdf_to_epub.cli ingest "assets/Continuous Delivery Reliable Software Releases through Build, Test, and Deployment Automation by Jez Humble, David Farley (z-lib.org).pdf" --pretty --report /tmp/pdf-to-epub-ingest.json
```

Current test command:

```bash
pytest -q
```

Developer quality checks:

```bash
python -m pip install -e ".[dev]"
pre-commit install
pre-commit run --all-files
```

The configured pre-commit hooks run:

- `ruff check --fix`
- `ruff format`
- `mypy src tests`
