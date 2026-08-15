"""Deterministic display-text quality gates.

This module intentionally does not try to be a general grammar checker. It blocks
specific production failures that are mechanically detectable before rendering:
non-NFC Unicode and German ASCII transliterations in viewer-facing copy.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata
from typing import Any, Iterable


@dataclass(frozen=True)
class TextQualityIssue:
    token: str
    replacement: str
    start: int
    end: int
    rule: str


_GERMAN_ASCII_REPLACEMENTS: dict[str, str] = {
    "aeusser": "äußer",
    "aeussere": "äußere",
    "aeusseren": "äußeren",
    "eigenstaendig": "eigenständig",
    "fuer": "für",
    "groesser": "größer",
    "koennen": "können",
    "muessen": "müssen",
    "oeffentlich": "öffentlich",
    "pruefbar": "prüfbar",
    "pruefen": "prüfen",
    "quellengestuetzt": "quellengestützt",
    "souveraen": "souverän",
    "strasse": "Straße",
    "unterstuetzt": "unterstützt",
    "ueber": "über",
    "ueberpruefbar": "überprüfbar",
    "ueberpruefen": "überprüfen",
    "verlaesslich": "verlässlich",
    "waehlen": "wählen",
    "waehlt": "wählt",
    "zurueck": "zurück",
}

_GERMAN_ASCII_PATTERN = re.compile(
    r"\b(" + "|".join(
        sorted((re.escape(token) for token in _GERMAN_ASCII_REPLACEMENTS), key=len, reverse=True)
    ) + r")\b",
    flags=re.IGNORECASE,
)


def _preserve_case(source: str, replacement: str) -> str:
    if source.isupper():
        return replacement.upper()
    if source[:1].isupper():
        return replacement[:1].upper() + replacement[1:]
    return replacement


def find_german_ascii_transliterations(text: str) -> list[TextQualityIssue]:
    """Return viewer-facing German ASCII substitutions such as ``waehlen``.

    The word list is deliberately explicit to avoid flagging names, URLs, and
    arbitrary source-code identifiers merely because they contain ``ae`` or ``ue``.
    """

    issues: list[TextQualityIssue] = []
    for match in _GERMAN_ASCII_PATTERN.finditer(text):
        token = match.group(0)
        replacement = _GERMAN_ASCII_REPLACEMENTS[token.lower()]
        issues.append(
            TextQualityIssue(
                token=token,
                replacement=_preserve_case(token, replacement),
                start=match.start(),
                end=match.end(),
                rule="german_ascii_transliteration",
            )
        )
    return issues


def find_unicode_normalization_issues(text: str) -> list[TextQualityIssue]:
    """Return a single issue when text is not normalized to Unicode NFC."""

    normalized = unicodedata.normalize("NFC", text)
    if normalized == text:
        return []
    return [
        TextQualityIssue(
            token=text,
            replacement=normalized,
            start=0,
            end=len(text),
            rule="unicode_not_nfc",
        )
    ]


def validate_display_text(text: str, *, language_code: str | None) -> list[TextQualityIssue]:
    issues = find_unicode_normalization_issues(text)
    if (language_code or "").lower().startswith("de"):
        issues.extend(find_german_ascii_transliterations(text))
    return issues


def iter_string_values(value: Any) -> Iterable[str]:
    """Yield every human-readable string value from nested JSON-like data."""

    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for nested in value.values():
            yield from iter_string_values(nested)
    elif isinstance(value, (list, tuple)):
        for nested in value:
            yield from iter_string_values(nested)
