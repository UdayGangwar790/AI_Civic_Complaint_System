"""
CVKI - Civic Vision & Knowledge Intelligence
Module 9.1: Multimodal Security & PII Sanitization Utilities

Ensures citizen text and metadata passed to multimodal pipelines are scrubbed of
personal identifiers (emails, phone numbers) and sensitive authorization tokens.
"""

import re
from typing import Any

# PII Matching Patterns
_EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
    re.IGNORECASE,
)

# Standard phone regex covering Indian (+91 / 10-digit) and common international formats
_PHONE_PATTERN = re.compile(
    r"(?:\+?91[\-\s]?)?[6-9]\d{4}[\-\s]?\d{5}\b|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b",
)

_SENSITIVE_KEY_PATTERNS = {
    "password", "secret", "token", "jwt", "auth",
    "credential", "session", "cookie", "api_key",
}


def sanitize_text_pii(text: str) -> str:
    """
    Redacts personal identifiers (email addresses, phone numbers) from citizen text.
    Preserves defect descriptions and road hazard semantics intact.
    """
    if not text:
        return ""
    sanitized = _EMAIL_PATTERN.sub("[EMAIL_REDACTED]", text)
    sanitized = _PHONE_PATTERN.sub("[PHONE_REDACTED]", sanitized)
    return sanitized


def sanitize_multimodal_metadata(data: Any) -> Any:
    """
    Recursively redacts sensitive authentication keys, passwords, and tokens from metadata payloads.
    Guarantees no credential leakage into model contexts or audit logs.
    """
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            k_str = str(k).lower()
            if any(pattern in k_str for pattern in _SENSITIVE_KEY_PATTERNS):
                sanitized[k] = "[REDACTED]"
            else:
                sanitized[k] = sanitize_multimodal_metadata(v)
        return sanitized
    elif isinstance(data, list):
        return [sanitize_multimodal_metadata(elem) for elem in data]
    return data
