"""Anonymous user identity helpers (no PII)."""

from __future__ import annotations

import re

# Opaque client IDs only: letters, digits, underscore, hyphen. No emails/phones.
_OPAQUE_USER_ID = re.compile(r"^[A-Za-z0-9_-]{8,64}$")
_DIGIT_RUN = re.compile(r"\d{7,}")


def normalize_anonymous_user_id(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    if not stripped:
        return None
    if "@" in stripped or " " in stripped:
        raise ValueError("anonymous user_id must be an opaque ID (no email or spaces)")
    if _DIGIT_RUN.search(stripped):
        raise ValueError("anonymous user_id must not look like a phone number")
    if not _OPAQUE_USER_ID.match(stripped):
        raise ValueError("anonymous user_id must be 8-64 chars of [A-Za-z0-9_-] (no PII)")
    return stripped
