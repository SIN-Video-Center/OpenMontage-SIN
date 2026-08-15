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


def test_execute_applies_pronunciation_and_never_returns_secret(tmp_path: Path):
    output = tmp_path / "sample.wav"
    captured = {}

    def fake_generate(*, api_key, payload, timeout):
        captured.update({"api_key": api_key, "payload": payload, "timeout": timeout})
        Path(payload["outputPath"]).write_bytes(b"RIFF" + b"x" * 512)
        return {
            "success": True,
            "mediaType": "audio/wav",
            "format": "wav",
            "warnings": [],
            "providerMetadata": {"gateway": {"generationId": "gen_test"}},
            "response": {"modelId": "xai/grok-tts"},
        }

    tool = VercelGatewayTTS()
    with patch.object(
        tool,
        "_credentials",
        return_value=[GatewayCredential("pool-1", "super-secret", "omniroute_pool")],
    ), patch.object(tool, "_generate_with_sdk", side_effect=fake_generate), patch(
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
    assert captured["payload"]["text"] == "Open A Eff De Chat. Quellen sichtbar."
    assert captured["payload"]["outputFormat"] == "wav"
    assert result.data["display_text"] == "OpenAfD Chat. Quellen sichtbar."
    assert result.data["spoken_text"] == "Open A Eff De Chat. Quellen sichtbar."
    assert result.data["credential_connection_id"] == "pool-1"
    assert result.data["credential_source"] == "omniroute_pool"
    assert result.data["gateway_generation_id"] == "gen_test"
    assert result.data["transport"] == "vercel-ai-sdk-gateway-speech-v4"
    assert "super-secret" not in json.dumps(result.data)


def test_execute_rotates_pool_after_retryable_error(tmp_path: Path):
    tool = VercelGatewayTTS()
    calls = []

    def fake_generate(*, api_key, payload, timeout):
        calls.append(api_key)
        if api_key == "exhausted-key":
            error = RuntimeError("Payment Required")
            error.status_code = 402
            error.retryable = True
            raise error
        Path(payload["outputPath"]).write_bytes(b"RIFF" + b"y" * 512)
        return {
            "success": True,
            "mediaType": "audio/wav",
            "format": "wav",
            "warnings": [],
            "providerMetadata": {},
            "response": {"modelId": "openai/tts-1-hd"},
        }

    with patch.object(
        tool,
        "_credentials",
        return_value=[
            GatewayCredential("pool-1", "exhausted-key", "omniroute_pool"),
            GatewayCredential("pool-2", "working-key", "omniroute_pool"),
        ],
    ), patch.object(tool, "_generate_with_sdk", side_effect=fake_generate), patch(
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


def test_execute_stops_pool_rotation_on_non_retryable_error(tmp_path: Path):
    tool = VercelGatewayTTS()
    calls = []

    def fake_generate(*, api_key, payload, timeout):
        calls.append(api_key)
        error = RuntimeError("Unsupported parameter")
        error.status_code = 400
        error.retryable = False
        raise error

    with patch.object(
        tool,
        "_credentials",
        return_value=[
            GatewayCredential("pool-1", "first", "omniroute_pool"),
            GatewayCredential("pool-2", "second", "omniroute_pool"),
        ],
    ), patch.object(tool, "_generate_with_sdk", side_effect=fake_generate):
        result = tool.execute({
            "text": "Quellen sichtbar.",
            "model": "openai/tts-1-hd",
            "voice": "onyx",
            "output_path": str(tmp_path / "sample.wav"),
        })

    assert result.success is False
    assert calls == ["first"]
    assert "Unsupported parameter" in (result.error or "")


def test_rejects_voice_that_does_not_belong_to_model():
    result = VercelGatewayTTS().execute({
        "text": "Test",
        "model": "openai/tts-1-hd",
        "voice": "rex",
    })
    assert result.success is False
    assert "not supported" in (result.error or "")
