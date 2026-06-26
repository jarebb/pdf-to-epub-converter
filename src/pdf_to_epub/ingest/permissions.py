"""Permission handling for PDF ingest."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import fitz


@dataclass(frozen=True)
class PermissionSummary:
    encrypted: bool
    needs_password: bool
    authenticated: bool
    permissions_value: int
    can_extract: bool
    can_access: bool
    can_print: bool
    can_modify: bool
    can_annotate: bool
    can_assemble: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "encrypted": self.encrypted,
            "needs_password": self.needs_password,
            "authenticated": self.authenticated,
            "permissions_value": self.permissions_value,
            "can_extract": self.can_extract,
            "can_access": self.can_access,
            "can_print": self.can_print,
            "can_modify": self.can_modify,
            "can_annotate": self.can_annotate,
            "can_assemble": self.can_assemble,
        }


def authenticate_document(document: Any, password: Optional[str]) -> bool:
    if not document.needs_pass:
        return True
    if not password:
        return False
    return bool(document.authenticate(password))


def summarize_permissions(document: Any, authenticated: bool) -> PermissionSummary:
    permissions_value = int(getattr(document, "permissions", 0) or 0)
    encrypted = bool(getattr(document, "is_encrypted", False) or document.needs_pass)
    needs_password = bool(document.needs_pass)

    can_extract = _has_permission(permissions_value, fitz.PDF_PERM_COPY)
    can_access = _has_permission(permissions_value, fitz.PDF_PERM_ACCESSIBILITY)

    if not encrypted:
        can_extract = True
        can_access = True

    return PermissionSummary(
        encrypted=encrypted,
        needs_password=needs_password,
        authenticated=authenticated,
        permissions_value=permissions_value,
        can_extract=can_extract,
        can_access=can_access,
        can_print=_has_permission(permissions_value, fitz.PDF_PERM_PRINT),
        can_modify=_has_permission(permissions_value, fitz.PDF_PERM_MODIFY),
        can_annotate=_has_permission(permissions_value, fitz.PDF_PERM_ANNOTATE),
        can_assemble=_has_permission(permissions_value, fitz.PDF_PERM_ASSEMBLE),
    )


def _has_permission(permissions_value: int, flag: int) -> bool:
    return bool(permissions_value & flag)
