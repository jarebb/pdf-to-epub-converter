"""Metadata normalization for PDF ingest."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

PDF_DATE_RE = re.compile(
    r"^D:"
    r"(?P<year>\d{4})"
    r"(?P<month>\d{2})?"
    r"(?P<day>\d{2})?"
    r"(?P<hour>\d{2})?"
    r"(?P<minute>\d{2})?"
    r"(?P<second>\d{2})?"
    r"(?P<tz>Z|[+-]\d{2}'?\d{2}'?)?"
)


def clean_metadata_value(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip().replace("\x00", "")


def normalize_pdf_metadata(raw_metadata: dict[str, object], input_path: Path) -> dict[str, str]:
    raw = {key: clean_metadata_value(value) for key, value in raw_metadata.items()}
    title = choose_display_title(raw.get("title", ""), input_path)

    return {
        "title": title,
        "author": raw.get("author", ""),
        "subject": raw.get("subject", ""),
        "keywords": raw.get("keywords", ""),
        "creator": raw.get("creator", ""),
        "producer": raw.get("producer", ""),
        "creation_date": normalize_pdf_date(raw.get("creationDate", "")) or "",
        "modification_date": normalize_pdf_date(raw.get("modDate", "")) or "",
        "format": raw.get("format", ""),
        "encryption": raw.get("encryption", ""),
        "language": "en",
        "source_title": raw.get("title", ""),
        "source_creation_date": raw.get("creationDate", ""),
        "source_modification_date": raw.get("modDate", ""),
    }


def normalize_pdf_date(value: str) -> Optional[str]:
    """Convert common PDF date strings to ISO-8601.

    Invalid or partial dates are returned as the best available valid prefix.
    """
    value = clean_metadata_value(value)
    if not value:
        return None

    match = PDF_DATE_RE.match(value)
    if not match:
        return value

    parts = match.groupdict()
    year = int(parts["year"])
    month = int(parts["month"] or "1")
    day = int(parts["day"] or "1")
    hour = int(parts["hour"] or "0")
    minute = int(parts["minute"] or "0")
    second = int(parts["second"] or "0")

    tzinfo = None
    raw_tz = parts.get("tz")
    if raw_tz == "Z":
        tzinfo = timezone.utc
    elif raw_tz:
        cleaned = raw_tz.replace("'", "")
        sign = 1 if cleaned[0] == "+" else -1
        offset_hours = int(cleaned[1:3])
        offset_minutes = int(cleaned[3:5])
        tzinfo = timezone(sign * timedelta(hours=offset_hours, minutes=offset_minutes))

    try:
        parsed = datetime(year, month, day, hour, minute, second, tzinfo=tzinfo)
    except ValueError:
        return value
    return parsed.isoformat()


def choose_display_title(source_title: str, input_path: Path) -> str:
    source_title = clean_metadata_value(source_title)
    if not source_title or _looks_like_pdf_filename(source_title):
        return input_path.stem
    return source_title


def _looks_like_pdf_filename(value: str) -> bool:
    lowered = value.lower()
    if lowered.endswith(".pdf"):
        return True
    if re.fullmatch(r"[\w.-]+", value) and "." in value:
        return True
    return False
