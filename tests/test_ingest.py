from pathlib import Path

from pdf_to_epub.ingest.metadata import choose_display_title
from pdf_to_epub.ingest.metadata import normalize_pdf_date
from pdf_to_epub.ingest.pdf_loader import IngestError, ingest_pdf


SAMPLE_PDF = Path(
    "assets/Continuous Delivery Reliable Software Releases through Build, Test, and Deployment Automation by Jez Humble, David Farley (z-lib.org).pdf"
)


def test_normalize_pdf_date_utc():
    assert normalize_pdf_date("D:20100716151324Z") == "2010-07-16T15:13:24+00:00"


def test_normalize_pdf_date_offset():
    assert normalize_pdf_date("D:20101004171922+03'00'") == "2010-10-04T17:19:22+03:00"


def test_display_title_falls_back_when_source_title_is_pdf_filename():
    title = choose_display_title("0321670272.pdf", Path("assets/Continuous Delivery.pdf"))

    assert title == "Continuous Delivery"


def test_ingest_sample_pdf():
    result = ingest_pdf(SAMPLE_PDF)

    assert result.page_count == 497
    assert result.metadata["language"] == "en"
    assert result.metadata["title"]
    assert result.permissions.can_extract
    assert len(result.pages) == result.page_count
    assert result.pages[0].number == 1
    assert result.pages[0].width > 0
    assert len(result.outline) > 0


def test_ingest_rejects_missing_pdf():
    missing = Path("assets/does-not-exist.pdf")

    try:
        ingest_pdf(missing)
    except IngestError as exc:
        assert "does not exist" in str(exc)
    else:
        raise AssertionError("expected IngestError")
