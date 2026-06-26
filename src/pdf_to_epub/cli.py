"""Command line interface for the PDF-to-EPUB converter."""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

import fitz

from pdf_to_epub.classify.page_classifier import classify_document_pages
from pdf_to_epub.document.builder import build_document_model
from pdf_to_epub.document.models import DocumentModel
from pdf_to_epub.epub.writer import EpubAssemblyError, write_epub
from pdf_to_epub.extract.models import DocumentExtraction
from pdf_to_epub.extract.page_extractor import extract_document_model
from pdf_to_epub.ingest.metadata import normalize_pdf_metadata
from pdf_to_epub.ingest.pdf_loader import IngestError, ingest_pdf
from pdf_to_epub.ingest.permissions import authenticate_document, summarize_permissions
from pdf_to_epub.ocr.fallback import (
    OcrConfig,
    OcrFallbackError,
    apply_ocr_fallback,
    ensure_ocr_not_required,
)
from pdf_to_epub.reconstruct.reading_order import reconstruct_reading_order
from pdf_to_epub.report.conversion import ConversionReport, build_conversion_report
from pdf_to_epub.validate.epubcheck import (
    EpubCheckConfig,
    EpubCheckResult,
    ValidationError,
    validate_epub,
)
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
    _add_ocr_options(extract_parser)

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
    _add_ocr_options(reconstruct_parser)

    model_parser = subparsers.add_parser(
        "model",
        help="Build the intermediate semantic document model.",
    )
    model_parser.add_argument("input_pdf", type=Path, help="Path to the input PDF.")
    model_parser.add_argument(
        "--password",
        help="Password for encrypted PDFs. Refuses encrypted PDFs if omitted or invalid.",
    )
    model_parser.add_argument(
        "--assets-dir",
        type=Path,
        help="Optional directory where extracted visual assets will be written.",
    )
    model_parser.add_argument(
        "--report",
        type=Path,
        help="Optional path to write the document model as JSON.",
    )
    model_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON output.",
    )
    _add_ocr_options(model_parser)

    epub_parser = subparsers.add_parser(
        "epub",
        help="Build a reflowable EPUB 3 package.",
    )
    epub_parser.add_argument("input_pdf", type=Path, help="Path to the input PDF.")
    epub_parser.add_argument("output_epub", type=Path, help="Path to write the EPUB file.")
    epub_parser.add_argument(
        "--password",
        help="Password for encrypted PDFs. Refuses encrypted PDFs if omitted or invalid.",
    )
    epub_parser.add_argument(
        "--assets-dir",
        type=Path,
        help="Optional directory where extracted visual assets will be written.",
    )
    epub_parser.add_argument(
        "--report",
        type=Path,
        help="Optional path to write the conversion quality report as JSON.",
    )
    epub_parser.add_argument(
        "--pretty",
        action="store_true",
        help="Pretty-print JSON report output.",
    )
    epub_parser.add_argument(
        "--epubcheck-command",
        help="Optional epubcheck command to run after assembly.",
    )
    epub_parser.add_argument(
        "--epubcheck-jar",
        type=Path,
        help="Optional EPUBCheck jar path. Uses java -jar when provided.",
    )
    epub_parser.add_argument(
        "--java-command",
        default="java",
        help="Java command used with --epubcheck-jar.",
    )
    epub_parser.add_argument(
        "--require-epubcheck",
        action="store_true",
        help="Fail when EPUBCheck is unavailable or reports errors.",
    )
    _add_ocr_options(epub_parser)

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


def _add_ocr_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--enable-ocr",
        action="store_true",
        help="Run local Tesseract OCR only for pages classified as textless/image-only.",
    )
    parser.add_argument(
        "--ocr-language",
        default="eng",
        help="Tesseract language code used when --enable-ocr is set.",
    )
    parser.add_argument(
        "--ocr-dpi",
        type=int,
        default=300,
        help="Rasterization DPI used for OCR pages.",
    )
    parser.add_argument(
        "--ocr-command",
        default="tesseract",
        help="Local OCR command to execute when --enable-ocr is set.",
    )
    parser.add_argument(
        "--ocr-tessdata-dir",
        type=Path,
        help="Optional tessdata directory; auto-detected for Conda Tesseract installs.",
    )
    parser.add_argument(
        "--ocr-workers",
        type=int,
        default=1,
        help="Maximum OCR worker count; internally capped to 1-2 for CPU-only runtime.",
    )


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
            extraction_result = _extract_with_optional_ocr(document, args)
        except OcrFallbackError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
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
            extraction_result = _extract_with_optional_ocr(document, args)
            reconstruction_result = reconstruct_reading_order(extraction_result)
        except OcrFallbackError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
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

    if args.command == "model":
        try:
            document = _open_extractable_pdf(args.input_pdf, password=args.password)
        except IngestError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        try:
            document_model = _build_document_model_from_pdf(document, args, args.assets_dir)
        except OcrFallbackError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        finally:
            document.close()
        _write_json(document_model.to_dict(), args.report, args.pretty)
        return 0

    if args.command == "epub":
        try:
            document = _open_extractable_pdf(args.input_pdf, password=args.password)
        except IngestError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        try:
            if args.assets_dir:
                document_model, report = _convert_pdf_to_epub(
                    document,
                    args,
                    args.assets_dir,
                )
                output_path = write_epub(document_model, args.output_epub)
            else:
                with TemporaryDirectory(prefix="pdf-to-epub-assets-") as temp_dir:
                    document_model, report = _convert_pdf_to_epub(
                        document,
                        args,
                        Path(temp_dir),
                    )
                    output_path = write_epub(document_model, args.output_epub)
            epubcheck_result = validate_epub(output_path, _epubcheck_config(args))
            report = replace(
                report,
                output_path=str(output_path.expanduser()),
                epubcheck_result=epubcheck_result.to_dict(),
            )
            if args.report:
                _write_json(report.to_dict(), args.report, args.pretty)
        except (OcrFallbackError, EpubAssemblyError, ValidationError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        finally:
            document.close()
        print(str(output_path))
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


def _extract_with_optional_ocr(
    document: fitz.Document,
    args: argparse.Namespace,
) -> DocumentExtraction:
    classifications, _summary = classify_document_pages(document)
    if not args.enable_ocr:
        ensure_ocr_not_required(classifications)
        return extract_document_model(document, classifications=classifications)

    extraction_result = extract_document_model(document, classifications=classifications)
    ocr_config = OcrConfig(
        language=args.ocr_language,
        dpi=args.ocr_dpi,
        max_workers=args.ocr_workers,
        command=args.ocr_command,
        tessdata_dir=args.ocr_tessdata_dir,
    )
    extraction_result, _ocr_report = apply_ocr_fallback(
        document,
        extraction_result,
        classifications,
        ocr_config,
    )
    return extraction_result


def _build_document_model_from_pdf(
    document: fitz.Document,
    args: argparse.Namespace,
    assets_dir: Optional[Path],
) -> DocumentModel:
    extraction_result = _extract_with_optional_ocr(document, args)
    reconstruction_result = reconstruct_reading_order(extraction_result)
    visual_result = extract_visual_assets(document, assets_dir) if assets_dir else None
    metadata = normalize_pdf_metadata(document.metadata or {}, args.input_pdf)
    return build_document_model(
        reconstruction_result,
        metadata=metadata,
        visual_manifest=visual_result,
    )


def _convert_pdf_to_epub(
    document: fitz.Document,
    args: argparse.Namespace,
    assets_dir: Path,
) -> tuple[DocumentModel, ConversionReport]:
    classifications, classification_summary = classify_document_pages(document)
    if not args.enable_ocr:
        ensure_ocr_not_required(classifications)
        extraction_result = extract_document_model(document, classifications=classifications)
    else:
        extraction_result = extract_document_model(document, classifications=classifications)
        ocr_config = OcrConfig(
            language=args.ocr_language,
            dpi=args.ocr_dpi,
            max_workers=args.ocr_workers,
            command=args.ocr_command,
            tessdata_dir=args.ocr_tessdata_dir,
        )
        extraction_result, _ocr_report = apply_ocr_fallback(
            document,
            extraction_result,
            classifications,
            ocr_config,
        )

    reading_order = reconstruct_reading_order(extraction_result)
    visual_manifest = extract_visual_assets(document, assets_dir)
    metadata = normalize_pdf_metadata(document.metadata or {}, args.input_pdf)
    document_model = build_document_model(
        reading_order,
        metadata=metadata,
        visual_manifest=visual_manifest,
    )
    report = build_conversion_report(
        input_path=args.input_pdf,
        output_path=args.output_epub,
        classification_summary=classification_summary,
        reading_order=reading_order,
        document_model=document_model,
        visual_manifest=visual_manifest,
        epubcheck_result=EpubCheckResult(
            status="not_run",
            tool="epubcheck",
            messages=["validation_pending_until_epub_written"],
        ),
    )
    return document_model, report


def _epubcheck_config(args: argparse.Namespace) -> EpubCheckConfig:
    return EpubCheckConfig(
        command=args.epubcheck_command,
        jar_path=args.epubcheck_jar,
        java_command=args.java_command,
        required=args.require_epubcheck,
    )


if __name__ == "__main__":
    raise SystemExit(main())
