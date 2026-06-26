# Agent Project Context

This repository is for a Python PDF-to-EPUB 3 converter.

## Product Goal

Build a local, CPU-only PDF-to-EPUB conversion tool that takes a PDF file path and produces a valid EPUB 3. The output should prioritize high-quality reading experience for books first, especially programming books, while preserving structure, images, captions, tables, lists, footnotes, metadata, and reader-compatible styling where practical.

## Hard Constraints

- Language: Python.
- No cloud or proprietary LLM APIs.
- Runtime target: AWS EC2 `t3.xlarge` with 4 vCPU, 16 GB RAM, CPU only, burstable.
- Heuristics-first architecture.
- Local LLM support, if ever added, must be optional, off by default, local-only, <=8B quantized, batched, and used only as a last-resort tie-breaker. The pure heuristic path must always produce a complete result.
- OCR is not part of the first coding phase. Add it later as a conditional fallback only for pages without extractable text.
- Born-digital pages with extractable text must not run OCR.
- Default language: English (`en`).
- If a blocking error occurs, fail instead of writing a best-effort EPUB.

## Initial Product Focus

- Books first, not arbitrary reports.
- Early target corpus: programming books.
- Sample source PDF is in `assets/`.
- Favor reflowable EPUB quality over pixel-perfect page reproduction.
- Preserve source images/diagrams:
  - Extract embedded raster images and reuse them.
  - Rasterize native PDF vector diagram regions to PNG.
  - Do not vectorize, redraw, or semantically interpret diagrams.

## Architecture Direction

Use a staged pipeline:

1. Ingest PDF.
2. Classify pages.
3. Extract text, layout, images, and metadata.
4. Build an intermediate document model.
5. Infer reading order and structure.
6. Reconstruct semantic XHTML and CSS.
7. Assemble EPUB 3.
8. Validate with EPUBCheck.
9. Emit a quality/conversion report.

Core libraries to prefer:

- PyMuPDF (`fitz`) as the primary PDF engine.
- pdfplumber for table-heavy or layout-diagnostic paths.
- pdfminer.six as a fallback/diagnostic extractor.
- Hand-built EPUB packaging preferred for deterministic EPUB 3 output; use open-source references as needed.
- EPUBCheck via subprocess for validation.
- OCR later with OCRmyPDF/Tesseract, conditional only.

See `docs/TECHNICAL_PLAN.md` for the detailed plan, staged milestones, project structure, and open decisions.
