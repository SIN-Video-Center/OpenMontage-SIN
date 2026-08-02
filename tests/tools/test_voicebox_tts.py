from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from tools.audio.voicebox_tts import VoiceboxTTS


def test_parse_voicebox_sse_payloads_ignores_non_data_lines():
    raw = (
        'event: progress\n'
        'data: {"id":"g1","status":"processing"}\n\n'
        ': keepalive\n'
        'data: not-json\n\n'
        'data: {"id":"g1","status":"completed","duration":8.08}\n\n'
    )
    assert VoiceboxTTS._parse_sse_payloads(raw) == [
        {"id": "g1", "status": "processing"},
        {"id": "g1", "status": "completed", "duration": 8.08},
    ]


def test_wait_for_generation_reads_sse_then_history_without_new_post():
    stream = BytesIO(b'data: {"id":"g1","status":"completed","duration":8.08}\n\n')
    stream.status = 200
    stream.__enter__ = lambda self: self
    stream.__exit__ = lambda *args: None

    tool = VoiceboxTTS()
    with patch.object(tool, "_urlopen", return_value=stream), patch.object(
        tool,
        "_fetch_generation_history",
        return_value={"audio_path": "generations/g1.wav", "duration": 8.08},
    ) as history:
        result = tool._wait_for_generation("g1", "http://127.0.0.1:17493", timeout=30)

    assert result == {
        "success": True,
        "audio_path": "generations/g1.wav",
        "duration": 8.08,
    }
    history.assert_called_once_with("g1", "http://127.0.0.1:17493")


def test_download_audio_writes_returned_bytes(tmp_path: Path):
    response = BytesIO(b"RIFF-test-wave")
    response.__enter__ = lambda self: self
    response.__exit__ = lambda *args: None
    output = tmp_path / "voice.wav"
    tool = VoiceboxTTS()

    with patch.object(tool, "_urlopen", return_value=response):
        tool._download_audio("http://127.0.0.1:17493/audio/g1", output)

    assert output.read_bytes() == b"RIFF-test-wave"


def test_voicebox_applies_display_to_spoken_pronunciation_before_post(tmp_path: Path):
    from unittest.mock import MagicMock

    post_response = BytesIO(b'{"id":"g1","audio_path":"generations/g1.wav"}')
    post_response.__enter__ = lambda self: self
    post_response.__exit__ = lambda *args: None
    audio_response = BytesIO(b"RIFF-test-wave")
    audio_response.__enter__ = lambda self: self
    audio_response.__exit__ = lambda *args: None
    captured = {}

    def fake_open(request, *, timeout):
        if request.full_url.endswith("/generate"):
            import json
            captured.update(json.loads(request.data))
            return post_response
        return audio_response

    tool = VoiceboxTTS()
    with patch.object(tool, "_check_health", return_value=True), patch.object(
        tool, "_resolve_profile", return_value="p1"
    ), patch.object(tool, "_urlopen", side_effect=fake_open), patch(
        "tools.analysis.audio_probe.probe_duration", return_value=2.0
    ):
        result = tool.execute({
            "text": "OpenAfD Chat beginnt bei den Quellen.",
            "profile_id": "p1",
            "output_path": str(tmp_path / "voice.wav"),
            "pronunciation_guides": [{
                "display_text": "OpenAfD Chat",
                "spoken_text": "Open A Eff De Chat",
                "expected_transcript_aliases": ["Open A Eff De Chat"],
            }],
        })

    assert result.success is True
    assert captured["text"] == "Open A Eff De Chat beginnt bei den Quellen."
    assert result.data["display_text"] == "OpenAfD Chat beginnt bei den Quellen."
    assert result.data["spoken_text"] == "Open A Eff De Chat beginnt bei den Quellen."
    assert result.data["pronunciation_guides_applied"][0]["display_text"] == "OpenAfD Chat"
