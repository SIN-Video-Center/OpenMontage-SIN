"""Pronunciation contracts for separating viewer-facing and provider-facing text."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Iterable


def _guide_values(guide: dict[str, Any]) -> tuple[str, str]:
    display = str(guide.get("display_text") or guide.get("word") or "").strip()
    spoken = str(guide.get("spoken_text") or guide.get("phonetic") or "").strip()
    return display, spoken


def apply_pronunciation_guides(
    text: str,
    guides: Iterable[dict[str, Any]] | None,
) -> tuple[str, list[dict[str, str]]]:
    """Return provider-ready text and the replacements that were applied.

    Exact display spellings remain untouched in scripts/captions. Only the TTS
    provider input is rewritten. Longest display forms are replaced first so a
    brand phrase wins over a shorter token contained inside it.
    """
    spoken_text = unicodedata.normalize("NFC", text)
    normalized_guides: list[tuple[str, str]] = []
    for guide in guides or []:
        display, spoken = _guide_values(guide)
        if display and spoken and display != spoken:
            normalized_guides.append((display, spoken))
    normalized_guides.sort(key=lambda pair: len(pair[0]), reverse=True)

    applied: list[dict[str, str]] = []
    for display, spoken in normalized_guides:
        pattern = re.compile(re.escape(display))
        spoken_text, count = pattern.subn(spoken, spoken_text)
        if count:
            applied.append(
                {"display_text": display, "spoken_text": spoken, "count": str(count)}
            )
    return spoken_text, applied


def normalize_transcript_text(text: str) -> str:
    value = unicodedata.normalize("NFC", text).casefold()
    value = re.sub(r"[^\wäöüß]+", " ", value, flags=re.UNICODE)
    return " ".join(value.split())


def transcript_matches_any_alias(
    transcript: str,
    aliases: Iterable[str] | None,
) -> bool:
    normalized_transcript = normalize_transcript_text(transcript)
    return any(
        normalize_transcript_text(alias) in normalized_transcript
        for alias in aliases or []
        if alias.strip()
    )
