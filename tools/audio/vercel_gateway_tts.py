"""Vercel AI Gateway speech provider with OmniRoute credential-pool support.

Speech is generated through Vercel's official AI SDK transport:
``experimental_generateSpeech`` + ``gateway.speechModel(...)``. Credentials are
resolved without exposing secret values in artifacts or process arguments:

1. explicit runtime-only ``api_key`` input,
2. ``AI_GATEWAY_API_KEY`` / ``VERCEL_AI_GATEWAY_API_KEY`` environment variable,
3. active ``vercel-ai-gateway`` connections in OmniRoute's encrypted SQLite store.

Only credential source and connection ID are returned as metadata.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

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

RUNTIME_DIR = Path(__file__).resolve().parent / "vercel_gateway_runtime"
RUNTIME_SCRIPT = RUNTIME_DIR / "generate.mjs"
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

_RETRYABLE_STATUS_CODES = {401, 402, 403, 408, 409, 429, 500, 502, 503, 504}


@dataclass(frozen=True)
class GatewayCredential:
    connection_id: str
    api_key: str
    source: str


class VercelGatewayTTS(BaseTool):
    name = "vercel_gateway_tts"
    version = "1.0.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "vercel-ai-gateway"
    stability = ToolStability.PRODUCTION
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.API

    dependencies = ["binary:node"]
    install_instructions = (
        "Install Node.js >=22, run `npm install --prefix "
        "tools/audio/vercel_gateway_runtime`, and configure an AI Gateway key "
        "or active OmniRoute vercel-ai-gateway pool."
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
        "official_ai_sdk_transport": True,
    }
    best_for = [
        "fast production narration through a managed Vercel Gateway pool",
        "German overview-video narration with verified acronym pronunciation",
        "voice auditions across xAI Grok TTS and OpenAI TTS-1 HD",
    ]
    not_good_for = ["offline-only productions", "voice cloning"]

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
            "instructions": {"type": "string"},
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
            "api_key": {"type": "string", "description": "Runtime-only key; never logged or returned."},
            "base_url": {"type": "string", "description": "Optional AI SDK Gateway base URL override."},
            "omniroute_db_path": {"type": "string"},
            "max_pool_attempts": {"type": "integer", "default": 6, "minimum": 1, "maximum": 20},
            "timeout_seconds": {"type": "number", "default": 90, "minimum": 5, "maximum": 300},
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=1, ram_mb=384, vram_mb=0, disk_mb=100, network_required=True
    )
    retry_policy = RetryPolicy(
        max_retries=2,
        backoff_seconds=1.0,
        retryable_errors=["rate_limit", "timeout", "gateway_error"],
    )
    idempotency_key_fields = [
        "text", "model", "voice", "response_format", "speed", "language",
        "instructions", "pronunciation_guides",
    ]
    side_effects = [
        "writes audio file to output_path",
        "calls Vercel AI Gateway through the official AI SDK",
        "uses paid gateway credits",
    ]
    user_visible_verification = [
        "Listen to the selected voice for tone and intelligibility",
        "Transcribe pronunciation-sensitive samples before batch generation",
        "Verify displayed brand text remains unchanged in captions",
    ]

    def get_status(self) -> ToolStatus:
        runtime_ready = (
            shutil.which("node") is not None
            and RUNTIME_SCRIPT.is_file()
            and (RUNTIME_DIR / "node_modules" / "ai" / "package.json").is_file()
            and (RUNTIME_DIR / "node_modules" / "@ai-sdk" / "gateway" / "package.json").is_file()
        )
        return ToolStatus.AVAILABLE if runtime_ready and self._credentials({}) else ToolStatus.UNAVAILABLE

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
            return AESGCM(key).decrypt(
                bytes.fromhex(iv_hex),
                bytes.fromhex(ciphertext_hex) + bytes.fromhex(tag_hex),
                None,
            ).decode("utf-8")
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
            if value:
                credentials.append(GatewayCredential(str(connection_id), value, "omniroute_pool"))
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
    def _generate_with_sdk(
        *,
        api_key: str,
        payload: dict[str, Any],
        timeout: float,
    ) -> dict[str, Any]:
        env = os.environ.copy()
        env["AI_GATEWAY_API_KEY"] = api_key
        env.pop("VERCEL_AI_GATEWAY_API_KEY", None)
        process = subprocess.run(
            [shutil.which("node") or "node", str(RUNTIME_SCRIPT)],
            input=json.dumps(payload, ensure_ascii=False),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=RUNTIME_DIR,
            env=env,
            timeout=timeout,
            check=False,
        )
        try:
            result = json.loads(process.stdout or "{}")
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"AI SDK speech runtime returned invalid JSON: {(process.stderr or process.stdout)[:300]}"
            ) from exc
        if process.returncode != 0 or not result.get("success"):
            status_code = result.get("statusCode")
            message = str(result.get("error") or process.stderr or "AI Gateway speech generation failed")[:500]
            error = RuntimeError(message)
            setattr(error, "status_code", status_code)
            setattr(error, "retryable", bool(result.get("retryable", status_code in _RETRYABLE_STATUS_CODES)))
            raise error
        return result

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
        output_path = Path(inputs.get("output_path") or f"vercel_gateway_tts.{response_format}").resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        payload: dict[str, Any] = {
            "model": model,
            "text": spoken_text,
            "voice": voice,
            "outputFormat": response_format,
            "speed": float(inputs.get("speed", 1.0)),
            "language": inputs.get("language", "de"),
            "outputPath": str(output_path),
        }
        if inputs.get("base_url"):
            payload["baseURL"] = str(inputs["base_url"])
        if inputs.get("instructions"):
            payload["instructions"] = str(inputs["instructions"])

        credentials = self._credentials(inputs)
        if not credentials:
            return ToolResult(success=False, error="No Vercel AI Gateway credential available. " + self.install_instructions)

        max_attempts = min(int(inputs.get("max_pool_attempts", 6)), len(credentials))
        timeout = float(inputs.get("timeout_seconds", 90))
        errors: list[str] = []
        selected: GatewayCredential | None = None
        sdk_result: dict[str, Any] = {}

        for credential in credentials[:max_attempts]:
            try:
                sdk_result = self._generate_with_sdk(
                    api_key=credential.api_key,
                    payload=payload,
                    timeout=timeout,
                )
                if not output_path.is_file() or output_path.stat().st_size < 64:
                    raise RuntimeError("AI SDK returned an implausibly small or missing audio file")
                selected = credential
                break
            except (RuntimeError, subprocess.TimeoutExpired, OSError) as exc:
                status_code = getattr(exc, "status_code", None)
                errors.append(
                    f"{credential.connection_id}: "
                    f"{('HTTP ' + str(status_code) + ' ') if status_code else ''}{str(exc)[:240]}"
                )
                retryable = bool(getattr(exc, "retryable", True))
                if not retryable:
                    break

        if selected is None:
            output_path.unlink(missing_ok=True)
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

        response = sdk_result.get("response") or {}
        provider_metadata = sdk_result.get("providerMetadata") or {}
        generation_id = None
        if isinstance(provider_metadata, dict):
            gateway_meta = provider_metadata.get("gateway") or {}
            if isinstance(gateway_meta, dict):
                generation_id = gateway_meta.get("generationId") or gateway_meta.get("id")

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "transport": "vercel-ai-sdk-gateway-speech-v4",
                "model": model,
                "resolved_model": response.get("modelId") or model,
                "voice": voice,
                "language": inputs.get("language", "de"),
                "format": sdk_result.get("format") or response_format,
                "media_type": sdk_result.get("mediaType"),
                "speed": float(inputs.get("speed", 1.0)),
                "instructions": inputs.get("instructions"),
                "display_text": text,
                "spoken_text": spoken_text,
                "pronunciation_guides_applied": applied,
                "text_length": len(spoken_text),
                "audio_duration_seconds": round(duration, 3) if duration else None,
                "audio_bytes": output_path.stat().st_size,
                "output": str(output_path),
                "credential_source": selected.source,
                "credential_connection_id": selected.connection_id,
                "gateway_generation_id": generation_id,
                "pool_attempt_count": len(errors) + 1,
                "warnings": sdk_result.get("warnings") or [],
            },
            artifacts=[str(output_path)],
            cost_usd=self.estimate_cost({**inputs, "text": text, "model": model}),
            duration_seconds=round(time.time() - started, 2),
            model=model,
        )
