"""Voicebox local TTS provider tool — Qwen3-TTS + 6 more engines."""

from __future__ import annotations

import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlparse

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

VOICEBOX_BASE_URL = os.environ.get("VOICEBOX_URL", "http://127.0.0.1:17493")


class VoiceboxTTS(BaseTool):
    name = "voicebox_tts"
    version = "0.2.0"
    tier = ToolTier.VOICE
    capability = "tts"
    provider = "voicebox"
    stability = ToolStability.BETA
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.STOCHASTIC
    runtime = ToolRuntime.LOCAL_GPU

    dependencies = []
    install_instructions = (
        "1. Clone Voicebox:\n"
        "   git clone https://github.com/jamiepine/voicebox.git ~/dev/voicebox\n"
        "2. Setup:\n"
        "   cd ~/dev/voicebox && just setup\n"
        "3. Start backend:\n"
        "   just dev-backend\n"
        "   (REST API runs on http://127.0.0.1:17493)\n"
        "4. Create voice profiles via the UI (Voice Cloning tab)."
    )
    fallback_tools = ["piper_tts"]
    agent_skills = ["text-to-speech", "voicebox", "qwen3-tts", "voice-cloning"]

    capabilities = [
        "text_to_speech",
        "voice_cloning",
        "voice_selection",
        "multilingual",
        "offline_generation",
        "post_processing",
    ]
    supports = {
        "voice_cloning": True,
        "multilingual": True,
        "offline": True,
        "native_audio": True,
    }
    best_for = [
        "local voice cloning",
        "Qwen3-TTS high-quality German narration",
        "zero-cost local TTS",
        "privacy-sensitive workflows",
    ]
    not_good_for = [
        "cloud-only deployments",
    ]

    LANGUAGES = [
        "de", "en", "zh", "ja", "ko", "fr", "ru", "pt", "es", "it",
        "he", "ar", "da", "el", "fi", "hi", "ms", "nl", "no", "pl", "sv", "sw", "tr",
    ]

    ENGINES = ["qwen", "qwen_custom_voice", "luxtts", "chatterbox", "chatterbox_turbo", "tada", "kokoro"]

    input_schema = {
        "type": "object",
        "required": ["text", "profile_id"],
        "properties": {
            "text": {"type": "string", "minLength": 1, "maxLength": 50000},
            "profile_id": {
                "type": "string",
                "description": "Voicebox voice profile ID (required).",
            },
            "profile_name": {
                "type": "string",
                "description": "Voicebox voice profile name — resolved to ID automatically.",
            },
            "language": {
                "type": "string",
                "default": "de",
                "enum": LANGUAGES,
                "description": "Language code for TTS generation.",
            },
            "engine": {
                "type": "string",
                "default": "qwen",
                "enum": ENGINES,
                "description": "TTS engine. qwen = Qwen3-TTS (best quality), kokoro = fast/preset voices.",
            },
            "model_size": {
                "type": "string",
                "default": "1.7B",
                "enum": ["0.6B", "1.7B", "1B", "3B"],
                "description": "Qwen3-TTS model size (larger = better quality, more VRAM).",
            },
            "instruct": {
                "type": "string",
                "maxLength": 500,
                "description": "Natural-language delivery instructions (Qwen3-TTS): 'speak slowly', 'whisper', 'excited', etc.",
            },
            "pronunciation_guides": {
                "type": "array",
                "description": "Display/spoken replacements applied only to provider input.",
                "items": {
                    "type": "object",
                    "properties": {
                        "word": {"type": "string"},
                        "phonetic": {"type": "string"},
                        "display_text": {"type": "string"},
                        "spoken_text": {"type": "string"},
                        "expected_transcript_aliases": {
                            "type": "array", "items": {"type": "string"}
                        },
                    },
                },
            },
            "seed": {
                "type": "integer",
                "minimum": 0,
                "description": "Random seed for reproducibility.",
            },
            "normalize": {
                "type": "boolean",
                "default": True,
                "description": "Normalize output audio volume.",
            },
            "output_path": {"type": "string"},
            "base_url": {
                "type": "string",
                "default": VOICEBOX_BASE_URL,
                "description": "Voicebox API base URL.",
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=4, ram_mb=2048, vram_mb=2048, disk_mb=4096, network_required=False
    )
    retry_policy = RetryPolicy(max_retries=2, retryable_errors=["timeout", "connection_error"])
    idempotency_key_fields = ["text", "language", "profile_id", "profile_name", "engine"]
    side_effects = ["writes audio file to output_path"]
    user_visible_verification = [
        "Listen to generated audio for intelligibility",
        "Check voice matches expected profile",
    ]

    def get_status(self) -> ToolStatus:
        try:
            import urllib.request
            req = urllib.request.Request(
                urljoin(VOICEBOX_BASE_URL, "/health"),
                method="GET",
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                if resp.status == 200:
                    return ToolStatus.AVAILABLE
        except Exception:
            pass
        return ToolStatus.UNAVAILABLE

    def estimate_cost(self, inputs: dict[str, Any]) -> float:
        return 0.0

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        base_url = inputs.get("base_url", VOICEBOX_BASE_URL)
        if self._check_health(base_url) is False:
            return ToolResult(
                success=False,
                error=(
                    f"Voicebox backend not reachable at {base_url}. "
                    f"Start it with: cd ~/dev/voicebox && just dev-backend"
                ),
            )

        start = time.time()
        try:
            result = self._generate(inputs, base_url)
        except Exception as exc:
            return ToolResult(success=False, error=f"Voicebox TTS failed: {exc}")

        result.duration_seconds = round(time.time() - start, 2)
        return result

    @staticmethod
    def _urlopen(request: Any, *, timeout: float):
        """Open a Voicebox request, bypassing environment proxies for loopback.

        Local Voicebox must never be routed through HTTP(S)_PROXY. urllib otherwise
        honors proxy environment variables even for 127.0.0.1 on some machines.
        """
        import urllib.request

        target = request.full_url if hasattr(request, "full_url") else str(request)
        hostname = (urlparse(target).hostname or "").lower()
        if hostname in {"127.0.0.1", "localhost", "::1"}:
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            return opener.open(request, timeout=timeout)
        return urllib.request.urlopen(request, timeout=timeout)

    @classmethod
    def _check_health(cls, base_url: str) -> bool:
        try:
            import urllib.request
            req = urllib.request.Request(
                urljoin(base_url, "/health"),
                method="GET",
            )
            with cls._urlopen(req, timeout=3) as resp:
                return resp.status == 200
        except Exception:
            return False

    @staticmethod
    def _parse_sse_payloads(raw: bytes | str) -> list[dict[str, Any]]:
        """Parse JSON payloads from a Voicebox ``text/event-stream`` body."""
        text = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else raw
        payloads: list[dict[str, Any]] = []
        for line in text.splitlines():
            line = line.strip()
            if not line.startswith("data:"):
                continue
            candidate = line[5:].strip()
            if not candidate:
                continue
            try:
                value = json.loads(candidate)
            except json.JSONDecodeError:
                continue
            if isinstance(value, dict):
                payloads.append(value)
        return payloads

    def _resolve_profile(
        self, profile_id: str | None, profile_name: str | None, base_url: str
    ) -> str | None:
        """Resolve profile name to ID if needed."""
        if profile_id:
            return profile_id
        if not profile_name:
            return None

        try:
            import urllib.request
            import json as _json

            req = urllib.request.Request(
                urljoin(base_url, "/profiles"),
                method="GET",
            )
            with self._urlopen(req, timeout=5) as resp:
                profiles = _json.loads(resp.read())

            for p in profiles:
                if p.get("name", "").lower() == profile_name.lower():
                    return p.get("id")
        except Exception:
            pass
        return None

    def _generate(self, inputs: dict[str, Any], base_url: str) -> ToolResult:
        import urllib.request
        import json as _json

        source_text = inputs["text"]
        from lib.pronunciation import apply_pronunciation_guides
        text, applied_pronunciations = apply_pronunciation_guides(
            source_text, inputs.get("pronunciation_guides")
        )
        language = inputs.get("language", "de")
        engine = inputs.get("engine", "qwen")
        model_size = inputs.get("model_size", "1.7B")
        instruct = inputs.get("instruct", "")
        seed = inputs.get("seed")
        normalize = inputs.get("normalize", True)

        profile_id = self._resolve_profile(
            inputs.get("profile_id"),
            inputs.get("profile_name"),
            base_url,
        )
        if not profile_id:
            return ToolResult(
                success=False,
                error=(
                    "No voice profile provided. Create one in Voicebox UI first, "
                    "then pass profile_id or profile_name."
                ),
            )

        output_path = Path(inputs.get("output_path", "voicebox_tts.wav"))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        payload: dict[str, Any] = {
            "text": text,
            "profile_id": profile_id,
            "language": language,
            "engine": engine,
            "model_size": model_size,
            "normalize": normalize,
        }
        if instruct:
            payload["instruct"] = instruct
        if seed is not None:
            payload["seed"] = seed

        data = _json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            urljoin(base_url, "/generate"),
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with self._urlopen(req, timeout=30) as resp:
            result = _json.loads(resp.read())

        generation_id = result.get("id")
        audio_path = result.get("audio_path", "")
        if not generation_id:
            return ToolResult(
                success=False,
                error="Voicebox returned no generation ID.",
            )

        if not audio_path:
            status = self._wait_for_generation(
                generation_id,
                base_url,
                timeout=int(inputs.get("status_timeout_seconds", 900)),
            )
            if not status.get("success"):
                return ToolResult(
                    success=False,
                    error=status.get("error", "Generation failed or timed out."),
                )
            audio_path = status.get("audio_path", "")

        # The status SSE intentionally omits audio_path. The supported contract is
        # /history/{id} for metadata and /audio/{id} for the actual bytes.
        if not audio_path:
            history = self._fetch_generation_history(generation_id, base_url)
            audio_path = str(history.get("audio_path") or "")
        if not audio_path:
            return ToolResult(
                success=False,
                error="Voicebox completed generation but returned no audio path.",
            )

        audio_url = urljoin(base_url.rstrip("/") + "/", f"audio/{generation_id}")
        self._download_audio(audio_url, output_path)

        audio_duration = None
        try:
            from tools.analysis.audio_probe import probe_duration
            audio_duration = probe_duration(output_path)
        except Exception:
            pass

        audio_url_final = audio_url if audio_path else None

        return ToolResult(
            success=True,
            data={
                "provider": self.provider,
                "engine": engine,
                "language": language,
                "profile_id": profile_id,
                "text_length": len(text),
                "display_text": source_text,
                "spoken_text": text,
                "pronunciation_guides_applied": applied_pronunciations,
                "audio_duration_seconds": round(audio_duration, 2) if audio_duration else None,
                "output": str(output_path),
                "audio_url": audio_url_final,
                "generation_id": generation_id,
                "format": "wav",
            },
            artifacts=[str(output_path)],
            model=f"{engine}:{language}",
        )

    def _wait_for_generation(
        self, generation_id: str, base_url: str, timeout: int = 900
    ) -> dict[str, Any]:
        """Read Voicebox SSE status until completion without spawning retries.

        A single GET may remain open while the job runs. If the transport closes
        before a terminal event, reconnect to the same generation ID; never POST a
        second generation.
        """
        import urllib.request

        deadline = time.time() + timeout
        last_error: str | None = None
        status_url = urljoin(
            base_url.rstrip("/") + "/",
            f"generate/{generation_id}/status",
        )
        while time.time() < deadline:
            remaining = max(1.0, deadline - time.time())
            try:
                req = urllib.request.Request(
                    status_url,
                    headers={"Accept": "text/event-stream"},
                    method="GET",
                )
                with self._urlopen(req, timeout=min(remaining + 5, 300)) as resp:
                    for raw_line in resp:
                        payloads = self._parse_sse_payloads(raw_line)
                        for payload in payloads:
                            state = str(payload.get("status") or "")
                            if state == "completed":
                                history = self._fetch_generation_history(
                                    generation_id, base_url
                                )
                                return {
                                    "success": True,
                                    "audio_path": history.get("audio_path"),
                                    "duration": history.get("duration"),
                                }
                            if state in {"failed", "not_found"}:
                                return {
                                    "success": False,
                                    "error": payload.get("error")
                                    or f"Voicebox generation {state}.",
                                }
                # Stream closed without terminal state; reconnect to the same ID.
            except Exception as exc:
                last_error = str(exc)
            time.sleep(1)

        suffix = f" Last transport error: {last_error}" if last_error else ""
        return {
            "success": False,
            "error": f"Generation timed out after {timeout}s.{suffix}",
        }

    def _fetch_generation_history(
        self, generation_id: str, base_url: str
    ) -> dict[str, Any]:
        import urllib.request

        history_url = urljoin(
            base_url.rstrip("/") + "/", f"history/{generation_id}"
        )
        req = urllib.request.Request(history_url, method="GET")
        with self._urlopen(req, timeout=15) as resp:
            value = json.loads(resp.read())
        if not isinstance(value, dict):
            raise RuntimeError("Voicebox history response was not an object.")
        return value

    def _download_audio(self, audio_url: str, output_path: Path) -> None:
        import urllib.request

        req = urllib.request.Request(audio_url, method="GET")
        with self._urlopen(req, timeout=120) as resp, output_path.open("wb") as target:
            shutil.copyfileobj(resp, target)
        if output_path.stat().st_size == 0:
            output_path.unlink(missing_ok=True)
            raise RuntimeError("Voicebox returned an empty audio file.")
