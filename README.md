# PDF to EPUB Converter

A local, Python-based PDF-to-EPUB 3 conversion tool focused on producing readable,
valid, reflowable EPUBs from books, especially programming books.

The project is being built incrementally with a staged pipeline:

1. Ingest PDF metadata, permissions, outlines, and page geometry.
2. Classify pages as born-digital text, mixed content, image-only, or low-confidence.
3. Extract text, layout, structure, images, and diagrams.
4. Build an intermediate structured document model.
5. Render semantic XHTML/CSS.
6. Assemble a valid EPUB 3 package.
7. Validate with EPUBCheck and emit a quality report.

## Goals

- Produce valid EPUB 3 output.
- Preserve reading order and book structure where possible.
- Preserve source images and diagrams without redrawing or semantic reconstruction.
- Prefer deterministic heuristics over model-based extraction.
- Run locally on CPU-only infrastructure.

The target runtime is an AWS EC2 `t3.xlarge` instance: 4 vCPU, 16 GB RAM, CPU only.

## Constraints

- Python only.
- No cloud or proprietary LLM APIs.
- OCR is conditional and deferred; born-digital PDFs with extractable text must not run OCR.
- Optional local LLM support, if ever added, must be off by default and used only as a last-resort tie-breaker.
- Blocking conversion errors should fail the run instead of writing best-effort EPUBs.

## Current Status

Implemented:

- Stage A: PDF ingest.
- Stage B: page classification.
- Stage C: text and layout extraction.
- Stage D: reading-order reconstruction.
- Stage E: image and diagram extraction.
- CLI commands for ingest, extraction, reconstruction, and visual asset reports.
- Ruff, mypy, pytest, and pre-commit setup.

Not implemented yet:

- Full semantic document model.
- EPUB rendering and packaging.
- EPUBCheck validation.
- OCR fallback.

## Setup

```bash
python -m pip install -e ".[dev]"
pre-commit install --hook-type pre-commit --hook-type commit-msg
```

The pre-commit config installs both pre-commit checks and a commit-message hook.
Commit messages must follow Conventional Commits, for example:
`feat(extract): add page layout models`.

## Usage

Generate a JSON ingest and page-classification report:

```bash
PYTHONPATH=src python -m pdf_to_epub.cli ingest path/to/book.pdf --pretty
```

Write the report to a file:

```bash
PYTHONPATH=src python -m pdf_to_epub.cli ingest path/to/book.pdf --report reports/ingest.json --pretty
```

Generate a JSON text/layout extraction report:

```bash
PYTHONPATH=src python -m pdf_to_epub.cli extract path/to/book.pdf --report reports/extract.json --pretty
```

Generate a JSON reading-order reconstruction report:

```bash
PYTHONPATH=src python -m pdf_to_epub.cli reconstruct path/to/book.pdf --report reports/reconstruct.json --pretty
```

Extract embedded images and rasterized vector diagram regions:

```bash
PYTHONPATH=src python -m pdf_to_epub.cli visuals path/to/book.pdf --assets-dir reports/assets --report reports/visuals.json --pretty
```

## Development

Run tests:

```bash
pytest -q
```

Run quality checks:

```bash
pre-commit run --all-files
```

## Repository Layout

```text
src/pdf_to_epub/
  cli.py
  classify/
  ingest/

tests/
docs/
assets/
```

PDF files under `assets/` are ignored by Git.

## Codex Assistance

This project is being created with Codex as the coding assistant. Codex is used to
help plan the architecture, implement staged changes, run checks, and maintain the
project documentation.
