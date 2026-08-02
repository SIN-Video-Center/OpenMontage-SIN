import json
from pathlib import Path

from lib.pronunciation import apply_pronunciation_guides, transcript_matches_any_alias

ROOT = Path(__file__).resolve().parents[2]


def test_display_text_is_preserved_while_provider_text_uses_german_letters():
    display = "OpenAfD Chat beginnt bei den Quellen."
    spoken, applied = apply_pronunciation_guides(display, [{
        "display_text": "OpenAfD Chat",
        "spoken_text": "Open A Eff De Chat",
    }])
    assert display == "OpenAfD Chat beginnt bei den Quellen."
    assert spoken == "Open A Eff De Chat beginnt bei den Quellen."
    assert applied[0]["count"] == "1"


def test_pronunciation_alias_check_accepts_german_letter_transcript():
    assert transcript_matches_any_alias(
        "Open A Eff De Chat. Quellen sichtbar.",
        ["Open A Eff De Chat", "Open A F D Chat"],
    )
    assert not transcript_matches_any_alias(
        "Open Ei Ef Di Chat.",
        ["Open A Eff De Chat", "Open A F D Chat"],
    )


def test_script_schema_supports_display_spoken_and_transcript_aliases():
    schema = json.loads((ROOT / "schemas/artifacts/script.schema.json").read_text())
    props = schema["properties"]["sections"]["items"]["properties"]["pronunciation_guides"]["items"]["properties"]
    assert {"display_text", "spoken_text", "expected_transcript_aliases"} <= set(props)
