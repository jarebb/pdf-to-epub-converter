"""EPUBCheck subprocess integration."""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional


class ValidationError(RuntimeError):
    """Raised when EPUB validation reports blocking errors."""


@dataclass(frozen=True)
class EpubCheckConfig:
    command: Optional[str] = None
    jar_path: Optional[Path] = None
    java_command: str = "java"
    required: bool = False


@dataclass(frozen=True)
class EpubCheckResult:
    status: str
    tool: str
    command: list[str] = field(default_factory=list)
    return_code: Optional[int] = None
    errors: int = 0
    warnings: int = 0
    fatals: int = 0
    messages: list[str] = field(default_factory=list)
    stdout: str = ""
    stderr: str = ""

    @property
    def passed(self) -> bool:
        return self.status == "passed"

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "tool": self.tool,
            "command": self.command,
            "return_code": self.return_code,
            "errors": self.errors,
            "warnings": self.warnings,
            "fatals": self.fatals,
            "messages": self.messages,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


def validate_epub(epub_path: Path, config: Optional[EpubCheckConfig] = None) -> EpubCheckResult:
    config = config or EpubCheckConfig()
    command = _epubcheck_command(epub_path, config)
    if command is None:
        result = EpubCheckResult(
            status="skipped",
            tool="epubcheck",
            messages=["epubcheck_unavailable"],
        )
        if config.required:
            raise ValidationError("EPUBCheck is required but no command or jar is available")
        return result

    with TemporaryDirectory(prefix="pdf-to-epub-epubcheck-") as temp_dir:
        report_path = Path(temp_dir) / "epubcheck.json"
        command = [*command, "--json", str(report_path)]
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
            )
        except OSError as exc:
            result = EpubCheckResult(
                status="skipped",
                tool="epubcheck",
                command=command,
                messages=[f"epubcheck_unavailable:{exc}"],
            )
            if config.required:
                raise ValidationError(str(exc)) from exc
            return result
        result = _result_from_completed_process(completed, command, report_path)

    if result.status == "failed":
        raise ValidationError(
            f"EPUBCheck failed with {result.errors} errors and {result.fatals} fatal errors"
        )
    return result


def _epubcheck_command(epub_path: Path, config: EpubCheckConfig) -> Optional[list[str]]:
    if config.command:
        resolved = shutil.which(config.command)
        if resolved is None:
            command_path = Path(config.command)
            if command_path.is_file():
                resolved = str(command_path)
        if resolved is None:
            return None
        return [resolved, str(epub_path)]
    if config.jar_path:
        if not config.jar_path.is_file() or shutil.which(config.java_command) is None:
            return None
        return [config.java_command, "-jar", str(config.jar_path), str(epub_path)]
    discovered = shutil.which("epubcheck")
    if discovered:
        return [discovered, str(epub_path)]
    return None


def _result_from_completed_process(
    completed: subprocess.CompletedProcess[str],
    command: list[str],
    report_path: Path,
) -> EpubCheckResult:
    payload = _read_json_report(report_path)
    errors, warnings, fatals, messages = _message_counts(payload)
    status = "passed" if completed.returncode == 0 and errors == 0 and fatals == 0 else "failed"
    return EpubCheckResult(
        status=status,
        tool="epubcheck",
        command=command,
        return_code=completed.returncode,
        errors=errors,
        warnings=warnings,
        fatals=fatals,
        messages=messages,
        stdout=completed.stdout.strip(),
        stderr=completed.stderr.strip(),
    )


def _read_json_report(report_path: Path) -> dict[str, object]:
    if not report_path.is_file():
        return {}
    try:
        payload = json.loads(report_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _message_counts(payload: dict[str, object]) -> tuple[int, int, int, list[str]]:
    messages = payload.get("messages", [])
    if not isinstance(messages, list):
        return 0, 0, 0, []

    errors = 0
    warnings = 0
    fatals = 0
    summaries: list[str] = []
    for raw in messages:
        if not isinstance(raw, dict):
            continue
        severity = str(raw.get("severity", "")).lower()
        if severity == "error":
            errors += 1
        elif severity == "fatal":
            fatals += 1
        elif severity == "warning":
            warnings += 1
        summaries.append(_message_summary(raw))
    return errors, warnings, fatals, summaries


def _message_summary(message: dict[str, object]) -> str:
    severity = str(message.get("severity", "info")).lower()
    message_id = str(message.get("ID", message.get("id", ""))).strip()
    text = str(message.get("message", "")).strip()
    location = message.get("locations", [])
    location_text = ""
    if isinstance(location, list) and location:
        first = location[0]
        if isinstance(first, dict):
            path = str(first.get("path", "")).strip()
            line = str(first.get("line", "")).strip()
            location_text = f":{path}:{line}" if path or line else ""
    prefix = f"{severity}:{message_id}" if message_id else severity
    return f"{prefix}{location_text}:{text}".rstrip(":")
