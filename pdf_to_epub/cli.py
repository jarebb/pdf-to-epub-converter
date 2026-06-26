"""Command line interface for the PDF-to-EPUB converter."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, Sequence

from pdf_to_epub.ingest.pdf_loader import IngestError, ingest_pdf


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
            result = ingest_pdf(args.input_pdf, password=args.password)
        except IngestError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        _write_json(result.to_dict(), args.report, args.pretty)
        return 0

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
