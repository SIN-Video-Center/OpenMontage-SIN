"""Vercel AI Gateway text-to-speech provider with optional OmniRoute key pool.

The provider keeps API credentials out of artifacts and logs. Authentication is
resolved in this order:

1. explicit ``api_key`` input (intended for short-lived CI injection),
2. ``AI_GATEWAY_API_KEY`` / ``VERCEL_AI_GATEWAY_API_KEY`` environment variable,
3. active ``vercel-ai-gateway`` connections in OmniRoute's local SQLite store.

Only connection IDs are returned in metadata. Secret values are never surfaced.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import sqlite3
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from lib.pronunciation import apply_pronunciation_guides
from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ToolResult,
    ToolRuntime,
    ToolStability,
    ToolStatus,
    ToolTier,
)

DEFAULT_BASE_URL = "https://ai-gateway.vercel.sh/v1"
DEFAULT_OMNIROUTE_DB = Path.home() / ".omniroute" / "storage.sqlite"

_MODEL_PRICING_PER_CHARACTER = {
    "xai/grok-tts": 0.000015,
    "openai/tts-1": 0.000015,
    "openai/tts-1-hd": 0.000030,
}

_MODEL_VOICES = {
    "xai/grok-tts": {"rex", "sal", "leo", "ara", "eve"},
    "openai/tts-1": {"alloy", "echo", "fable", "onyx", "nova", "shimmer"},
    "openai/tts-1-hd": {"alloy", "echo", "fable", "onyx", "nova", "shimmer"},
}


@dataclass(frozen=True)
class GatewayCredential:
    connection_id: str
    api_key: str
    source: str


class VercelGatewayTTS(BaseTool):
    name = "vercel_gateway_tts"
    version = "0.1.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "vercel-ai-gateway"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies: list[str] = []
    install_instructions = (
        "Configure AI_GATEWAY_API_KEY, VERCEL_AI_GATEWAY_API_KEY, or an active "
        "vercel-ai-gateway connection in ~/.omniroute/storage.sqlite."
    )
    fallback_tools = ["openai_tts", "voicebox_tts", "piper_tts"]
    agent_skills = ["text-to-speech"]

    capabilities = [
        "text_to_speech",
        "voice_selection",
        "gateway_routing",
        "omniroute_key_pool",
        "pronunciation_guides",
        "multilingual",
    ]
    supports = {
        "voice_cloning": False,
        "multilingual": True,
        "offline": False,
        "native_audio": True,
        "pronunciation_guides": True,
        "key_pool_rotation": True,
    }
    best_for = [
        "fast production narration through a managed provider pool",
        "German overview-video narration with verified acronym pronunciation",
        "voice auditions across xAI Grok TTS and OpenAI TTS-1 HD",
    ]
    not_good_for = [
        "offline-only productions",
        "voice cloning",
        "zero-data-retention requirements for models that do not support ZDR",
    ]

    input_schema = {
        "type": "object",
        "required": ["text"],
        "properties": {
            "text": {"type": "string", "minLength": 1, "maxLength": 4096},
            "model": {
                "type": "string",
                "default": "xai/grok-tts",
                "enum": sorted(_MODEL_VOICES),
            },
            "voice": {"type": "string", "default": "rex"},
            "response_format": {
                "type": "string",
                "default": "wav",
                "enum": ["mp3", "wav", "flac", "opus", "aac"],
            },
            "speed": {"type": "number", "default": 1.0, "minimum": 0.25, "maximum": 4.0},
            "language": {"type": "string", "default": "de"},
            "instructions": {
                "type": "string",
                "description": "Delivery direction. Primarily supported by xai/grok-tts.",
            },
            "pronunciation_guides": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "display_text": {"type": "string"},
                        "spoken_text": {"type": "string"},
                        "expected_transcript_aliases": {"type": "array", "items": {"type": "string"}},
                    },
                },
            },
            "output_path": {"type": "string"},
            "api_key": {"type": "string", "description": "Optional runtime-only key. Never returned."},
            "base_url": {"type": "string", "default": DEFAULT_BASE_URL},
            "omniroute_db_path": {"type": "string"},
            "max_pool_attempts": {"type": "integer", "default": 6, "minimum": 1, "maximum": 20},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=256, vram_mb=0, disk_mb=100, network_required=True
    )
    retry_policy = RetryPolicy(
        max_retries=2,
        backoff_seconds=1.0,
        retryable_errors=["rate_limit", "timeout", "gateway_error"],
    )
    idempotency_key_fields = [
        "text",
        "model",
        "voice",
        "response_format",
        "speed",
        "language",
        "instructions",
        "pronunciation_guides",
    ]
    side_effects = [
        "writes audio file to output_path",
        "calls Vercel AI Gateway",
        "uses paid gateway credits",
    ]
    user_visible_verification = [
        "Listen to the selected voice for tone and intelligibility",
        "Transcribe pronunciation-sensitive samples before batch generation",
        "Verify displayed brand text remains unchanged in captions",
    ]

    def get_status(self) -> ToolStatus:
        return ToolStatus.AVAILABLE if self._credentials({}) else ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        model = str(inputs.get("model", "xai/grok-tts"))
        rate = _MODEL_PRICING_PER_CHARACTER.get(model, 0.000030)
        spoken_text, _ = apply_pronunciation_guides(
            str(inputs.get("text", "")), inputs.get("pronunciation_guides")
        )
        return round(len(spoken_text) * rate, 6)

    @staticmethod
    def voices_for_model(model: str) -> list[str]:
        return sorted(_MODEL_VOICES.get(model, set()))

    @staticmethod
    def _read_env_value(path: Path, name: str) -> str | None:
        if not path.is_file():
            return None
        try:
            for raw_line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip() != name:
                    continue
                value = value.strip()
                if value[:1] in {"'", '"'} and value[-1:] == value[:1]:
                    value = value[1:-1]
                return value or None
        except OSError:
            return None
        return None

    @classmethod
    def _decrypt_omniroute_value(cls, stored: str, db_path: Path) -> str | None:
        if not stored.startswith("enc:v1:"):
            return stored

        secret = os.environ.get("STORAGE_ENCRYPTION_KEY") or cls._read_env_value(
            db_path.parent / ".env", "STORAGE_ENCRYPTION_KEY"
        )
        if not secret:
            return None

        parts = stored[len("enc:v1:"):].split(":")
        if len(parts) != 3:
            return None
        iv_hex, ciphertext_hex, tag_hex = parts
        try:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            key = hashlib.scrypt(
                secret.encode("utf-8"),
                salt=b"omniroute-field-encryption-v1",
                n=16384,
                r=8,
                p=1,
                dklen=32,
            )
            iv = bytes.fromhex(iv_hex)
            ciphertext = bytes.fromhex(ciphertext_hex)
            tag = bytes.fromhex(tag_hex)
            return AESGCM(key).decrypt(iv, ciphertext + tag, None).decode("utf-8")
        except Exception:
            return None

    @classmethod
    def _omniroute_credentials(cls, db_path: Path) -> list[GatewayCredential]:
        if not db_path.is_file():
            return []
        try:
            connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=2)
            rows = connection.execute(
                """
                SELECT id, api_key
                FROM provider_connections
                WHERE provider = 'vercel-ai-gateway'
                  AND is_active = 1
                  AND test_status = 'active'
                  AND length(coalesce(api_key, '')) > 20
                ORDER BY coalesce(last_used_at, '') DESC, coalesce(updated_at, '') DESC
                """
            ).fetchall()
            connection.close()
        except (sqlite3.Error, OSError):
            return []

        credentials: list[GatewayCredential] = []
        for connection_id, api_key in rows:
            stored = str(api_key or "").strip()
            value = cls._decrypt_omniroute_value(stored, db_path) if stored else None
            if not value:
                continue
            credentials.append(
                GatewayCredential(
                    connection_id=str(connection_id),
                    api_key=value,
                    source="omniroute_pool",
                )
            )
        return credentials

    def _credentials(self, inputs: dict[str, Any]) -> list[GatewayCredential]:
        explicit = str(inputs.get("api_key") or "").strip()
        if explicit:
            return [GatewayCredential("runtime", explicit, "runtime_input")]

        for name in ("AI_GATEWAY_API_KEY", "VERCEL_AI_GATEWAY_API_KEY"):
            value = os.environ.get(name, "").strip()
            if value:
                return [GatewayCredential(name.lower(), value, "environment")]

        configured = inputs.get("omniroute_db_path") or os.environ.get("OMNIROUTE_DB_PATH")
        db_path = Path(configured).expanduser() if configured else DEFAULT_OMNIROUTE_DB
        return self._omniroute_credentials(db_path)

    @staticmethod
    def _audio_bytes(body: bytes, content_type: str | None) -> bytes:
        ctype = (content_type or "").lower()
        if "json" not in ctype:
            return body

        payload = json.loads(body.decode("utf-8"))
        candidates: list[Any] = [
            payload.get("audio"),
            payload.get("b64_json"),
            payload.get("data"),
            payload.get("output"),
        ]
        for candidate in candidates:
            if isinstance(candidate, dict):
                candidate = candidate.get("audio") or candidate.get("b64_json") or candidate.get("data")
            if isinstance(candidate, list) and candidate:
                candidate = candidate[0]
                if isinstance(candidate, dict):
                    candidate = candidate.get("audio") or candidate.get("b64_json") or candidate.get("data")
            if isinstance(candidate, str) and candidate:
                if candidate.startswith("data:") and "," in candidate:
                    candidate = candidate.split(",", 1)[1]
                return base64.b64decode(candidate)
        raise ValueError("Vercel AI Gateway returned JSON without base64 audio data")

    @staticmethod
    def _post(
        *,
        base_url: str,
        api_key: str,
        payload: dict[str, Any],
        timeout: float,
    ) -> tuple[bytes, str | None, dict[str, str]]:
        request = urllib.request.Request(
            f"{base_url.rstrip('/')}/audio/speech",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json, audio/*",
                "User-Agent": "OpenMontage/vercel-gateway-tts",
            },
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            headers = {key.lower(): value for key, value in response.headers.items()}
            return response.read(), response.headers.get("content-type"), headers

    @staticmethod
    def _safe_http_error(exc: urllib.error.HTTPError) -> str:
        try:
            payload = json.loads(exc.read().decode("utf-8", errors="replace"))
            error = payload.get("error", payload)
            if isinstance(error, dict):
                return str(error.get("message") or error.get("type") or "Gateway request failed")[:300]
            return str(error)[:300]
        except Exception:
            return f"HTTP {exc.code}"

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        started = time.time()
        text = str(inputs.get("text", "")).strip()
        if not text:
            return ToolResult(success=False, error="text must not be empty")

        model = str(inputs.get("model", "xai/grok-tts"))
        voice = str(inputs.get("voice") or ("rex" if model == "xai/grok-tts" else "onyx"))
        allowed = _MODEL_VOICES.get(model)
        if not allowed:
            return ToolResult(success=False, error=f"Unsupported gateway speech model: {model}")
        if voice not in allowed:
            return ToolResult(
                success=False,
                error=f"Voice {voice!r} is not supported by {model}. Choose one of: {', '.join(sorted(allowed))}",
            )

        spoken_text, applied = apply_pronunciation_guides(text, inputs.get("pronunciation_guides"))
        response_format = str(inputs.get("response_format", "wav"))
        output_path = Path(inputs.get("output_path") or f"vercel_gateway_tts.{response_format}")
        output_path.parent.mkdir(parents=True, exist_ok=True)

        payload: dict[str, Any] = {
            "model": model,
            "input": spoken_text,
            "voice": voice,
            "response_format": response_format,
            "speed": float(inputs.get("speed", 1.0)),
        }
        if inputs.get("language"):
            payload["language"] = inputs["language"]
        if inputs.get("instructions") and model == "xai/grok-tts":
            payload["instructions"] = inputs["instructions"]

        credentials = self._credentials(inputs)
        if not credentials:
            return ToolResult(success=False, error="No Vercel AI Gateway credential available. " + self.install_instructions)

        max_attempts = min(int(inputs.get("max_pool_attempts", 6)), len(credentials))
        base_url = str(inputs.get("base_url", DEFAULT_BASE_URL))
        errors: list[str] = []
        selected: GatewayCredential | None = None
        response_headers: dict[str, str] = {}

        for credential in credentials[:max_attempts]:
            try:
                body, content_type, response_headers = self._post(
                    base_url=base_url,
                    api_key=credential.api_key,
                    payload=payload,
                    timeout=float(inputs.get("timeout_seconds", 90)),
                )
                audio = self._audio_bytes(body, content_type)
                if len(audio) < 64:
                    raise ValueError("Gateway returned an implausibly small audio payload")
                output_path.write_bytes(audio)
                selected = credential
                break
            except urllib.error.HTTPError as exc:
                errors.append(f"{credential.connection_id}: HTTP {exc.code} {self._safe_http_error(exc)}")
                if exc.code not in {401, 402, 403, 408, 409, 429, 500, 502, 503, 504}:
                    break
            except (urllib.error.URLError, TimeoutError, ValueError, OSError, json.JSONDecodeError) as exc:
                errors.append(f"{credential.connection_id}: {type(exc).__name__}: {str(exc)[:200]}")

        if selected is None:
            return ToolResult(
                success=False,
                error="Vercel AI Gateway TTS failed across the credential pool: " + " | ".join(errors[:max_attempts]),
                duration_seconds=round(time.time() - started, 2),
                cost_usd=0.0,
                model=model,
            )

        try:
            from tools.analysis.audio_probe import probe_duration

            duration = probe_duration(output_path)
        except Exception:
            duration = None

        cost = self.estimate_cost({**inputs, "text": text, "model": model})
        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "model": model,
                "voice": voice,
                "language": inputs.get("language", "de"),
                "format": response_format,
                "speed": float(inputs.get("speed", 1.0)),
                "instructions": inputs.get("instructions") if model == "xai/grok-tts" else None,
                "display_text": text,
                "spoken_text": spoken_text,
                "pronunciation_guides_applied": applied,
                "text_length": len(spoken_text),
                "audio_duration_seconds": round(duration, 3) if duration else None,
                "output": str(output_path),
                "credential_source": selected.source,
                "credential_connection_id": selected.connection_id,
                "gateway_request_id": response_headers.get("x-vercel-id") or response_headers.get("x-request-id"),
                "pool_attempt_count": len(errors) + 1,
            },
            artifacts=[str(output_path)],
            cost_usd=cost,
            duration_seconds=round(time.time() - started, 2),
            model=model,
        )
