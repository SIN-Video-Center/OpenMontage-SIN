import base64
import json
from pathlib import Path
from unittest.mock import patch

from tools.audio.vercel_gateway_tts import GatewayCredential, VercelGatewayTTS


def test_estimate_cost_uses_provider_character_pricing_and_spoken_form():
    tool = VercelGatewayTTS()
    inputs = {
        "text": "OpenAfD Chat",
        "model": "xai/grok-tts",
        "pronunciation_guides": [{
            "display_text": "OpenAfD Chat",
            "spoken_text": "Open A Eff De Chat",
        }],
    }
    assert tool.estimate_cost(inputs) == round(len("Open A Eff De Chat") * 0.000015, 6)


def test_audio_bytes_accepts_raw_binary_and_base64_json():
    raw = b"RIFF" + b"x" * 100
    assert VercelGatewayTTS._audio_bytes(raw, "audio/wav") == raw

    encoded = base64.b64encode(raw).decode("ascii")
    body = json.dumps({"audio": encoded}).encode("utf-8")
    assert VercelGatewayTTS._audio_bytes(body, "application/json") == raw


def test_execute_applies_pronunciation_and_never_returns_secret(tmp_path: Path):
    output = tmp_path / "sample.wav"
    captured = {}

    def fake_post(*, base_url, api_key, payload, timeout):
        captured.update({
            "base_url": base_url,
            "api_key": api_key,
            "payload": payload,
            "timeout": timeout,
        })
        return b"RIFF" + b"x" * 512, "audio/wav", {"x-vercel-id": "iad1::test"}

    tool = VercelGatewayTTS()
    with patch.object(
        tool,
        "_credentials",
        return_value=[GatewayCredential("pool-1", "super-secret", "omniroute_pool")],
    ), patch.object(tool, "_post", side_effect=fake_post), patch(
        "tools.analysis.audio_probe.probe_duration", return_value=2.4
    ):
        result = tool.execute({
            "text": "OpenAfD Chat. Quellen sichtbar.",
            "model": "xai/grok-tts",
            "voice": "rex",
            "output_path": str(output),
            "pronunciation_guides": [{
                "display_text": "OpenAfD Chat",
                "spoken_text": "Open A Eff De Chat",
            }],
            "instructions": "Ruhig und präzise sprechen.",
        })

    assert result.success is True
    assert output.exists()
    assert captured["api_key"] == "super-secret"
    assert captured["payload"]["input"] == "Open A Eff De Chat. Quellen sichtbar."
    assert result.data["display_text"] == "OpenAfD Chat. Quellen sichtbar."
    assert result.data["spoken_text"] == "Open A Eff De Chat. Quellen sichtbar."
    assert result.data["credential_connection_id"] == "pool-1"
    assert result.data["credential_source"] == "omniroute_pool"
    assert "super-secret" not in json.dumps(result.data)
    assert result.data["gateway_request_id"] == "iad1::test"


def test_execute_rotates_pool_after_retryable_http_error(tmp_path: Path):
    import urllib.error

    tool = VercelGatewayTTS()
    calls = []

    def fake_post(*, base_url, api_key, payload, timeout):
        calls.append(api_key)
        if api_key == "exhausted-key":
            raise urllib.error.HTTPError(
                url="https://ai-gateway.vercel.sh/v1/audio/speech",
                code=402,
                msg="Payment Required",
                hdrs={},
                fp=None,
            )
        return b"RIFF" + b"y" * 512, "audio/wav", {}

    with patch.object(
        tool,
        "_credentials",
        return_value=[
            GatewayCredential("pool-1", "exhausted-key", "omniroute_pool"),
            GatewayCredential("pool-2", "working-key", "omniroute_pool"),
        ],
    ), patch.object(tool, "_post", side_effect=fake_post), patch(
        "tools.analysis.audio_probe.probe_duration", return_value=1.0
    ):
        result = tool.execute({
            "text": "Quellen sichtbar.",
            "model": "openai/tts-1-hd",
            "voice": "onyx",
            "output_path": str(tmp_path / "sample.wav"),
        })

    assert result.success is True
    assert calls == ["exhausted-key", "working-key"]
    assert result.data["credential_connection_id"] == "pool-2"
    assert result.data["pool_attempt_count"] == 2


def test_rejects_voice_that_does_not_belong_to_model():
    result = VercelGatewayTTS().execute({
        "text": "Test",
        "model": "openai/tts-1-hd",
        "voice": "rex",
    })
    assert result.success is False
    assert "not supported" in (result.error or "")
