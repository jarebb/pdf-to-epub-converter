"""Command line interface for the PDF-to-EPUB converter."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Optional

import fitz

from pdf_to_epub.classify.page_classifier import classify_document_pages
from pdf_to_epub.extract.page_extractor import extract_document_model
from pdf_to_epub.ingest.pdf_loader import IngestError, ingest_pdf
from pdf_to_epub.ingest.permissions import authenticate_document, summarize_permissions
from pdf_to_epub.reconstruct.reading_order import reconstruct_reading_order
from pdf_to_epub.visuals.asset_extractor import extract_visual_assets


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdf-to-epub",
        description="Local, heuristics-first PDF to EPUB 3 converter.",
    )
    subparsers = parser.add_subparsers(dest="command")

    ingest_parser = subparsers.add_parser(
        "ingest",
        help="Read PDF metadata, permissions, outlines, and page geometry.",
    )
    ingest_parser.add_argument("input_pdf", type=Path, help="Path to the input PDF.")
    ingest_parser.add_argument(
        "--password",
        help="Password for encrypted PDFs. Refuses encrypted PDFs if omitted or invalid.",
    )
    ingest_parser.add_argument(
        "--report",
        type=Path,
        help="Optional path to write the ingest report as JSON.",
    )
    ingest_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )

    extract_parser = subparsers.add_parser(
        "extract",
        help="Extract page text, layout, images, drawings, and diagnostics.",
    )
    extract_parser.add_argument("input_pdf", type=Path, help="Path to the input PDF.")
    extract_parser.add_argument(
        "--password",
        help="Password for encrypted PDFs. Refuses encrypted PDFs if omitted or invalid.",
    )
    extract_parser.add_argument(
        "--report",
        type=Path,
        help="Optional path to write the extraction report as JSON.",
    )
    extract_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )

    reconstruct_parser = subparsers.add_parser(
        "reconstruct",
        help="Infer a reading-order stream from extracted page models.",
    )
    reconstruct_parser.add_argument("input_pdf", type=Path, help="Path to the input PDF.")
    reconstruct_parser.add_argument(
        "--password",
        help="Password for encrypted PDFs. Refuses encrypted PDFs if omitted or invalid.",
    )
    reconstruct_parser.add_argument(
        "--report",
        type=Path,
        help="Optional path to write the reconstruction report as JSON.",
    )
    reconstruct_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )

    visuals_parser = subparsers.add_parser(
        "visuals",
        help="Extract embedded images and rasterized vector diagram regions.",
    )
    visuals_parser.add_argument("input_pdf", type=Path, help="Path to the input PDF.")
    visuals_parser.add_argument(
        "--assets-dir",
        required=True,
        type=Path,
        help="Directory where extracted visual assets will be written.",
    )
    visuals_parser.add_argument(
        "--password",
        help="Password for encrypted PDFs. Refuses encrypted PDFs if omitted or invalid.",
    )
    visuals_parser.add_argument(
        "--report",
        type=Path,
        help="Optional path to write the visual asset manifest as JSON.",
    )
    visuals_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )

    return parser


def _write_json(data: object, report_path: Optional[Path], pretty: bool) -> None:
    indent = 2 if pretty else None
    payload = json.dumps(data, indent=indent, sort_keys=pretty)
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(payload + "\n", encoding="utf-8")
    else:
        print(payload)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "ingest":
        try:
            ingest_result = ingest_pdf(args.input_pdf, password=args.password)
        except IngestError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        _write_json(ingest_result.to_dict(), args.report, args.pretty)
        return 0

    if args.command == "extract":
        try:
            document = _open_extractable_pdf(args.input_pdf, password=args.password)
        except IngestError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        try:
            classifications, _summary = classify_document_pages(document)
            extraction_result = extract_document_model(document, classifications=classifications)
        finally:
            document.close()
        _write_json(extraction_result.to_dict(), args.report, args.pretty)
        return 0

    if args.command == "reconstruct":
        try:
            document = _open_extractable_pdf(args.input_pdf, password=args.password)
        except IngestError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        try:
            classifications, _summary = classify_document_pages(document)
            extraction_result = extract_document_model(document, classifications=classifications)
            reconstruction_result = reconstruct_reading_order(extraction_result)
        finally:
            document.close()
        _write_json(reconstruction_result.to_dict(), args.report, args.pretty)
        return 0

    if args.command == "visuals":
        try:
            document = _open_extractable_pdf(args.input_pdf, password=args.password)
        except IngestError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        try:
            visual_result = extract_visual_assets(document, args.assets_dir)
        finally:
            document.close()
        _write_json(visual_result.to_dict(), args.report, args.pretty)
        return 0

    parser.print_help()
    return 2


def _open_extractable_pdf(input_path: Path, password: Optional[str]) -> fitz.Document:
    path = input_path.expanduser()
    if not path.exists():
        raise IngestError(f"input PDF does not exist: {path}")
    if not path.is_file():
        raise IngestError(f"input path is not a file: {path}")
    if path.suffix.lower() != ".pdf":
        raise IngestError(f"input path must point to a PDF file: {path}")

    try:
        document = fitz.open(path)
    except Exception as exc:  # pragma: no cover - exact PyMuPDF exception varies.
        raise IngestError(f"failed to open PDF: {exc}") from exc

    authenticated = authenticate_document(document, password)
    permissions = summarize_permissions(document, authenticated=authenticated)
    if permissions.needs_password and not authenticated:
        document.close()
        raise IngestError("PDF is encrypted and requires a valid password")
    if not permissions.can_extract and not permissions.can_access:
        document.close()
        raise IngestError("PDF permissions do not allow text/content extraction")
    return document


if __name__ == "__main__":
    raise SystemExit(main())
