import os
from pathlib import Path

import pytest

from pdf_to_epub.validate.epubcheck import (
    EpubCheckConfig,
    ValidationError,
    validate_epub,
)


def test_validate_epub_skips_when_epubcheck_unavailable(tmp_path: Path) -> None:
    result = validate_epub(
        tmp_path / "book.epub",
        EpubCheckConfig(command="/tmp/does-not-exist-epubcheck"),
    )

    assert result.status == "skipped"
    assert "epubcheck_unavailable" in result.messages


def test_validate_epub_requires_available_epubcheck(tmp_path: Path) -> None:
    with pytest.raises(ValidationError, match="EPUBCheck is required"):
        validate_epub(
            tmp_path / "book.epub",
            EpubCheckConfig(command="/tmp/does-not-exist-epubcheck", required=True),
        )


def test_validate_epub_parses_success_report(tmp_path: Path) -> None:
    command = _fake_epubcheck(tmp_path, return_code=0, messages=[])

    result = validate_epub(tmp_path / "book.epub", EpubCheckConfig(command=str(command)))

    assert result.status == "passed"
    assert result.return_code == 0
    assert result.errors == 0


def test_validate_epub_errors_are_blocking(tmp_path: Path) -> None:
    command = _fake_epubcheck(
        tmp_path,
        return_code=1,
        messages=[
            {
                "severity": "ERROR",
                "ID": "RSC-001",
                "message": "Broken XHTML",
                "locations": [{"path": "EPUB/text/chapter.xhtml", "line": 12}],
            }
        ],
    )

    with pytest.raises(ValidationError, match="EPUBCheck failed with 1 errors"):
        validate_epub(tmp_path / "book.epub", EpubCheckConfig(command=str(command)))


def _fake_epubcheck(tmp_path: Path, *, return_code: int, messages: list[dict[str, object]]) -> Path:
    script = tmp_path / "fake-epubcheck"
    script.write_text(
        "\n".join(
            [
                "#!/usr/bin/env python",
                "import json, sys",
                "report = {'messages': " + repr(messages) + "}",
                "json_path = sys.argv[sys.argv.index('--json') + 1]",
                "open(json_path, 'w', encoding='utf-8').write(json.dumps(report))",
                f"raise SystemExit({return_code})",
            ]
        ),
        encoding="utf-8",
    )
    os.chmod(script, 0o755)
    return script
