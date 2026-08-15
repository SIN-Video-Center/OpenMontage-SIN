import json

from tools.analysis.transcriber import Transcriber


def test_transcriber_reuses_fresh_rendered_output_cache(tmp_path):
    media = tmp_path / "final.mp4"
    media.write_bytes(b"rendered-media")
    output_dir = tmp_path / "transcripts"
    output_dir.mkdir()
    transcript = output_dir / "final_transcript.json"
    payload = {
        "segments": [{"id": 1, "start": 0.0, "end": 1.0, "text": "Test"}],
        "word_timestamps": [{"word": "Test", "start": 0.0, "end": 1.0}],
        "language": "de",
        "duration_seconds": 1.0,
    }
    transcript.write_text(json.dumps(payload), encoding="utf-8")

    result = Transcriber().execute(
        {"input_path": str(media), "output_dir": str(output_dir)}
    )

    assert result.success is True
    assert result.duration_seconds == 0.0
    assert result.data == payload
    assert result.artifacts == [str(transcript)]
