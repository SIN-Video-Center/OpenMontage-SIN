from lib.text_quality import (
    find_german_ascii_transliterations,
    find_unicode_normalization_issues,
    validate_display_text,
)


def test_german_ascii_transliterations_are_blocked_with_unicode_replacements():
    issues = find_german_ascii_transliterations(
        "SOUVERAEN. EIGENSTAENDIG. Provider frei waehlen."
    )
    assert [(issue.token, issue.replacement) for issue in issues] == [
        ("SOUVERAEN", "SOUVERÄN"),
        ("EIGENSTAENDIG", "EIGENSTÄNDIG"),
        ("waehlen", "wählen"),
    ]


def test_real_german_unicode_passes():
    assert validate_display_text(
        "SOUVERÄN. EIGENSTÄNDIG. Provider frei wählen.",
        language_code="de-DE",
    ) == []


def test_non_german_text_does_not_trigger_german_word_rules():
    assert validate_display_text("waehlen", language_code="en-US") == []


def test_non_nfc_text_is_blocked():
    decomposed = "wa\u0308hlen"
    issues = find_unicode_normalization_issues(decomposed)
    assert len(issues) == 1
    assert issues[0].replacement == "wählen"
