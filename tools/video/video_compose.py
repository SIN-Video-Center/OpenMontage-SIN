"""Video composition tool — FFmpeg + Remotion + HyperFrames (runtime-aware).

Pipeline-facing orchestration surface for composition. Takes `edit_decisions`,
`asset_manifest`, and audio, and delegates to the technical runtime chosen
at proposal stage.

Routing is driven by `edit_decisions.render_runtime` (locked at proposal):

- `remotion`   → React-based frame-accurate render via `npx remotion render`.
                 Supports either the templated scene-component stack or a
                 project-local Atelier composition, as locked at proposal.
- `hyperframes` → HTML/CSS/GSAP render via `hyperframes_compose`.
                 Handles kinetic typography, product promos, website-to-video,
                 registry blocks. Added in the parallel-runtime initiative.
- `ffmpeg`     → FFmpeg concat/trim. Used only for simple video cuts without
                 composition, or when the approved path explicitly names FFmpeg.

Authoring mode is orthogonal to runtime. Setting
`edit_decisions.composition_mode = "atelier"` (or `renderer_family="bespoke"`)
means the composition is hand-authored rather than assembled from stock scene
components. Runtime still wins first: HyperFrames atelier routes through
`hyperframes_compose`, FFmpeg stays FFmpeg-only, and only Remotion atelier uses
`_render_via_atelier` for a project-local Remotion entry that bypasses the
cut-schema and stock scene-type registry.

Silent runtime swaps are forbidden by governance. If the chosen runtime is
unavailable or fails, this tool surfaces a structured blocker and waits for
the agent to re-ask the user rather than substituting a different engine.
"""

from __future__ import annotations

import json
import logging
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

RENDERED_MOTION_THRESHOLD = 0.001


def _rendered_motion_mask(differences: list[float]) -> list[bool]:
    """Classify low-resolution frame deltas as visible editorial motion."""
    return [difference >= RENDERED_MOTION_THRESHOLD for difference in differences]


def _timeline_scene_id(
    cut_windows: list[tuple[float, float, str]], timestamp: float
) -> str | None:
    """Return the scene owning a timestamp for cross-scene repetition QA."""
    for start, end, cut_id in cut_windows:
        if start <= timestamp < end:
            return cut_id
    return None


from tools.base_tool import (
    BaseTool,
    Determinism,
    ExecutionMode,
    ResourceProfile,
    RetryPolicy,
    ResumeSupport,
    ToolResult,
    ToolStability,
    ToolTier,
)


class VideoCompose(BaseTool):
    name = "video_compose"
    version = "0.1.0"
    tier = ToolTier.CORE
    capability = "video_post"
    provider = "ffmpeg"
    stability = ToolStability.EXPERIMENTAL
    execution_mode = ExecutionMode.SYNC
    determinism = Determinism.DETERMINISTIC

    dependencies = ["cmd:ffmpeg"]
    install_instructions = "Install FFmpeg: https://ffmpeg.org/download.html"
    agent_skills = ["remotion-best-practices", "remotion", "ffmpeg"]

    capabilities = [
        "compose_cuts",
        "burn_subtitles",
        "overlay_assets",
        "encode_profile",
        "remotion_render",
    ]

    input_schema = {
        "type": "object",
        "required": ["operation"],
        "properties": {
            "operation": {
                "type": "string",
                "enum": ["compose", "render", "remotion_render", "burn_subtitles", "overlay", "encode"],
                "description": (
                    "compose: low-level concat cuts + audio + subtitles. "
                    "render: high-level governed render — preserves the runtime and "
                    "composition mode locked at proposal, resolves assets/audio, runs "
                    "pre-compose validation, renders, and executes blocking final QA. "
                    "remotion_render: render via Remotion (Node.js). "
                    "burn_subtitles: burn subtitle file into existing video. "
                    "overlay: composite overlays onto base video. "
                    "encode: re-encode to a target profile/codec."
                ),
            },
            "input_path": {"type": "string"},
            "output_path": {"type": "string"},
            "edit_decisions": {
                "type": "object",
                "description": "Full edit_decisions artifact (required for compose/render)",
            },
            "asset_manifest": {
                "type": "object",
                "description": (
                    "Full asset_manifest artifact (required for render). "
                    "Used to resolve asset IDs in cuts[].source to file paths."
                ),
            },
            "proposal_packet": {
                "type": "object",
                "description": (
                    "Full proposal_packet artifact. Required by the compose director "
                    "for runtime, quality-tier, and delivery-promise preservation."
                ),
            },
            "scene_plan": {
                "type": "object",
                "description": (
                    "Full scene_plan artifact. Required for operation='render'; the "
                    "pre-compose gate validates real visual beats instead of trying "
                    "to reconstruct weak metadata from cuts."
                ),
            },
            "narration_transcript_path": {
                "type": "string",
                "description": (
                    "Optional fallback transcript JSON. Final review first attempts "
                    "to transcribe the actual rendered output; this path is used only "
                    "when rendered-output transcription is unavailable. Hero/broadcast "
                    "delivery still requires the rendered-output transcript."
                ),
            },
            "semantic_visual_review_path": {
                "type": "string",
                "description": (
                    "Path to a rendered semantic visual_review artifact generated by "
                    "visual_review_loop. Hero/overview delivery can require this in "
                    "proposal_packet.production_plan.semantic_visual_review."
                ),
            },
            "script_path": {
                "type": "string",
                "description": (
                    "Path to the source narration script (plain text). "
                    "Used by transcript_comparison to diff against the "
                    "transcribed audio. Provide this OR script_text."
                ),
            },
            "script_text": {
                "type": "string",
                "description": (
                    "Inline source narration script. Used by "
                    "transcript_comparison when a file path is unavailable."
                ),
            },
            "subtitle_path": {"type": "string"},
            "subtitle_style": {
                "type": "object",
                "description": "ASS subtitle styling. Also extracted from edit_decisions.subtitles if not provided.",
                "properties": {
                    "font": {"type": "string", "default": "Arial"},
                    "font_size": {"type": "integer", "default": 24},
                    "primary_color": {"type": "string", "default": "&HFFFFFF"},
                    "outline_color": {"type": "string", "default": "&H000000"},
                    "outline_width": {"type": "number", "default": 2},
                    "margin_v": {"type": "integer", "default": 40},
                    "alignment": {"type": "integer", "default": 2},
                },
            },
            "overlays": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "asset_path": {"type": "string"},
                        "x": {"type": "number"},
                        "y": {"type": "number"},
                        "width": {"type": "number"},
                        "height": {"type": "number"},
                        "start_seconds": {"type": "number"},
                        "end_seconds": {"type": "number"},
                        "opacity": {"type": "number", "minimum": 0, "maximum": 1},
                    },
                },
            },
            "audio_path": {"type": "string", "description": "Mixed audio to mux into output"},
            "profile": {
                "type": "string",
                "description": (
                    "Media profile name from media_profiles.py "
                    "(e.g. youtube_landscape, tiktok, instagram_reels). "
                    "Applied in render and encode operations."
                ),
            },
            "options": {
                "type": "object",
                "description": "Render options (used by the render operation)",
                "properties": {
                    "subtitle_burn": {"type": "boolean", "default": True},
                    "two_pass_encode": {"type": "boolean", "default": False},
                },
            },
            "codec": {"type": "string", "default": "libx264"},
            "crf": {"type": "integer", "default": 23},
            "preset": {"type": "string", "default": "medium"},
            "remotion_timeout_ms": {
                "type": "integer",
                "description": (
                    "Remotion render timeout in milliseconds, passed through as "
                    "`--timeout` (governs headless-browser setup and delayRender). "
                    "Raise this when the browser is slow to start (e.g. restricted "
                    "networks). The subprocess timeout is widened to match."
                ),
            },
        },
    }

    resource_profile = ResourceProfile(
        cpu_cores=4, ram_mb=2048, vram_mb=0, disk_mb=5000, network_required=False
    )

    # Remotion scene types that trigger React-based rendering
    _REMOTION_COMPONENTS = [
        "text_card", "hero_title", "stat_card", "callout", "comparison",
        "progress_bar", "bar_chart", "line_chart", "pie_chart", "kpi_grid",
        "anime_scene", "terminal_scene", "screenshot_scene",
    ]

    best_for = [
        "Final render for explainer and animation pipelines",
        "Draft/standard image-to-video animatics with explicit camera-only classification (Remotion)",
        "Animated text cards, stat cards, charts (Remotion)",
        "Complex transitions between scenes (Remotion)",
        "Pure video concat and trim (FFmpeg)",
    ]
    retry_policy = RetryPolicy(max_retries=1, retryable_errors=["Conversion failed"])
    resume_support = ResumeSupport.FROM_START
    idempotency_key_fields = ["operation", "input_path", "edit_decisions"]
    side_effects = ["writes video file to output_path"]
    user_visible_verification = [
        "Play the composed output and verify cuts, subtitles, and overlays",
    ]

    def _remotion_available(self) -> bool:
        """Check if Remotion rendering is available (requires npx + composer project + node_modules)."""
        import shutil as _shutil

        if not _shutil.which("npx"):
            return False
        composer_dir = Path(__file__).resolve().parent.parent.parent / "remotion-composer"
        if not composer_dir.exists() or not (composer_dir / "package.json").exists():
            return False
        # Check that node_modules are actually installed — without this,
        # npx remotion render will fail even though the project exists.
        if not (composer_dir / "node_modules").exists():
            return False
        return True

    def _ffmpeg_available(self) -> bool:
        """Check if the ffmpeg binary is actually resolvable on PATH."""
        import shutil as _shutil

        return bool(_shutil.which("ffmpeg"))

    def _hyperframes_available(self) -> bool:
        """Check if HyperFrames rendering is available.

        Delegates to the dedicated tool so the availability check stays in
        one place (node 22 floor, ffmpeg + npx on PATH).
        """
        try:
            from tools.video.hyperframes_compose import HyperFramesCompose
            return bool(HyperFramesCompose()._runtime_check()["runtime_available"])
        except Exception:
            return False

    def get_info(self) -> dict[str, Any]:
        """Extend base get_info to surface all available render runtimes.

        Preflight reports each runtime's availability separately so the agent
        can choose an appropriate `render_runtime` at proposal stage. Silent
        fallback between runtimes is forbidden.
        """
        info = super().get_info()
        ffmpeg_ok = self._ffmpeg_available()
        remotion_ok = self._remotion_available()
        hyperframes_ok = self._hyperframes_available()
        info["render_engines"] = {
            "ffmpeg": ffmpeg_ok,
            "remotion": remotion_ok,
            "hyperframes": hyperframes_ok,
        }
        # Backwards-compat alias — some proposal skills inspect this name.
        info["render_runtimes"] = info["render_engines"]

        if remotion_ok:
            info["remotion_components"] = self._REMOTION_COMPONENTS
            info["remotion_note"] = (
                "Remotion is available for React-based rendering. Proposal routing "
                "decides between templated draft/standard composition and project-local "
                "Atelier authoring. Stock cards/charts are not a hero-quality default; "
                "their information must progressively change with the narration."
            )
        else:
            composer_dir = Path(__file__).resolve().parent.parent.parent / "remotion-composer"
            if composer_dir.exists() and (composer_dir / "package.json").exists() and not (composer_dir / "node_modules").exists():
                info["remotion_note"] = (
                    "Remotion project exists but node_modules are NOT installed. "
                    "Run 'cd remotion-composer && npm install' to enable Remotion rendering."
                )
            else:
                info["remotion_note"] = (
                    "Remotion is NOT available (needs Node.js/npx + remotion-composer + node_modules)."
                )

        if hyperframes_ok:
            info["hyperframes_note"] = (
                "HyperFrames is available for HTML/CSS/GSAP composition. Use it "
                "for kinetic typography, product promos, launch reels, "
                "website-to-video, and registry-block-driven scenes. Consumed via "
                "'npx hyperframes' (npm package: 'hyperframes'). "
                "Before locking render_runtime='hyperframes' at the proposal stage, "
                "verify the runtime with `hyperframes_compose` operation='doctor' "
                "or `make hyperframes-doctor`. An 'available' flag from the runtime "
                "check means node + ffmpeg + the npm package all resolve; it does "
                "not guarantee a render will succeed on the first specific "
                "composition."
            )
        else:
            info["hyperframes_note"] = (
                "HyperFrames is NOT available. Requires Node.js >= 22, FFmpeg, "
                "npx on PATH, and the 'hyperframes' npm package to be resolvable. "
                "Run `make hyperframes-doctor` to see the specific missing piece, "
                "or call `hyperframes_compose` operation='doctor' directly."
            )

        # Governance note — agents and reviewers consume this.
        info["runtime_governance"] = (
            "render_runtime is locked at proposal stage and carried unchanged "
            "through edit_decisions. Silent swaps are forbidden. If the "
            "chosen runtime fails, surface a structured blocker and wait for "
            "user approval before switching."
        )
        return info

    def execute(self, inputs: dict[str, Any]) -> ToolResult:
        operation = inputs["operation"]
        start = time.time()

        try:
            if operation == "compose":
                result = self._compose(inputs)
            elif operation == "render":
                result = self._render(inputs)
            elif operation == "remotion_render":
                result = self._remotion_render(inputs)
            elif operation == "burn_subtitles":
                result = self._burn_subtitles(inputs)
            elif operation == "overlay":
                result = self._overlay(inputs)
            elif operation == "encode":
                result = self._encode(inputs)
            else:
                return ToolResult(success=False, error=f"Unknown operation: {operation}")
        except Exception as e:
            return ToolResult(success=False, error=str(e))

        result.duration_seconds = round(time.time() - start, 2)
        return result

    _IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".tif", ".webp"}

    @staticmethod
    def _is_image(path: Path) -> bool:
        """Check if a file is a still image (routes to Remotion, not FFmpeg)."""
        return path.suffix.lower() in VideoCompose._IMAGE_EXTENSIONS

    @staticmethod
    def _has_audio_stream(path: Path) -> bool:
        """Return True iff ffprobe reports at least one audio stream.

        Many stock video clips (especially from Pexels) ship with no audio
        stream at all. If we blindly tell ffmpeg to transcode the 0:a stream
        on such a file it errors out. This helper lets the segment builder
        branch on stream presence so it can synthesize a silent track when
        needed, keeping the concat segment layout consistent.
        """
        try:
            out = subprocess.check_output(
                [
                    "ffprobe", "-v", "error",
                    "-select_streams", "a",
                    "-show_entries", "stream=codec_type",
                    "-of", "default=nw=1:nk=1",
                    str(path),
                ],
                stderr=subprocess.STDOUT,
                text=True,
            )
            return "audio" in out
        except Exception:
            return False

    def _compose(self, inputs: dict[str, Any]) -> ToolResult:
        """FFmpeg composition: concat video cuts, add audio, burn subtitles.

        Handles video sources only. Still images and animated scene types
        are routed to Remotion via the render operation — call compose
        directly only for pure video pipelines (e.g. talking-head).
        """
        edit_decisions = inputs.get("edit_decisions")
        if not edit_decisions:
            return ToolResult(success=False, error="edit_decisions required for compose")

        output_path = Path(inputs.get("output_path", "composed_output.mp4"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        audio_path = inputs.get("audio_path")
        subtitle_path = inputs.get("subtitle_path")
        codec = inputs.get("codec", "libx264")
        crf = inputs.get("crf", 23)
        preset = inputs.get("preset", "medium")
        profile_name = inputs.get("profile")

        # Resolve target resolution + fit mode. Priority: explicit `profile`
        # arg > edit_decisions.metadata.compose_target > default (landscape HD).
        # compose_target = {"width": W, "height": H, "fit": "pad"|"cover"} lets a
        # caller request vertical (9:16) or any aspect without a named profile.
        # fit="pad" letterboxes (no content loss, the historical default);
        # fit="cover" scales-to-fill and centre-crops (better for vertical social).
        resolution = "1920x1080"
        fit_mode = "pad"
        compose_target = (edit_decisions.get("metadata") or {}).get("compose_target")
        if isinstance(compose_target, dict):
            try:
                resolution = f"{int(compose_target['width'])}x{int(compose_target['height'])}"
            except (KeyError, ValueError, TypeError):
                pass
            if compose_target.get("fit") in ("pad", "cover"):
                fit_mode = compose_target["fit"]
        if profile_name:
            try:
                from lib.media_profiles import get_profile
                p = get_profile(profile_name)
                resolution = f"{p.width}x{p.height}"
            except (ImportError, ValueError):
                pass
        try:
            target_w, target_h = (int(v) for v in resolution.split("x"))
        except ValueError:
            target_w, target_h = 1920, 1080

        cuts = edit_decisions.get("cuts", [])
        if not cuts:
            return ToolResult(success=False, error="No cuts in edit_decisions")

        # Resolve subtitle style using the layered priority resolver
        # (explicit > edit_decisions > playbook > defaults)
        playbook_data = inputs.get("playbook")
        resolved_sub_style = self._resolve_subtitle_style(
            inputs.get("subtitle_style"),
            edit_decisions,
            playbook_data,
        )
        inputs = dict(inputs)
        inputs["subtitle_style"] = resolved_sub_style

        ed_subs = edit_decisions.get("subtitles", {})
        if ed_subs.get("source") and not subtitle_path:
            subtitle_path = ed_subs["source"]

        temp_dir = output_path.parent / ".compose_tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        temp_segments: list[Path] = []
        concat_path: Path | None = None
        concat_out: Path | None = None

        try:
            for i, cut in enumerate(cuts):
                source = Path(cut["source"])
                if not source.exists():
                    return ToolResult(success=False, error=f"Cut source not found: {source}")

                seg_path = temp_dir / f"seg_{i:04d}.mp4"
                timeline_start = float(cut["in_seconds"])
                timeline_end = float(cut["out_seconds"])
                duration = timeline_end - timeline_start
                source_in = float(cut.get("source_in_seconds", 0) or 0)
                speed = cut.get("speed", 1.0)

                if duration <= 0:
                    return ToolResult(
                        success=False,
                        error=f"Cut {cut.get('id', i)!r} has non-positive timeline duration",
                    )
                if i > 0:
                    previous_end = float(cuts[i - 1]["out_seconds"])
                    if abs(timeline_start - previous_end) > 0.001:
                        relation = "overlaps" if timeline_start < previous_end else "leaves a gap after"
                        return ToolResult(
                            success=False,
                            error=(
                                f"FFmpeg sequential compose {relation} cut "
                                f"{cuts[i - 1].get('id', i - 1)!r}: previous end="
                                f"{previous_end}, next start={timeline_start}. Use Remotion/"
                                "HyperFrames for overlapping layers or explicitly fill timeline gaps."
                            ),
                        )

                if self._is_image(source):
                    return ToolResult(
                        success=False,
                        error=(
                            f"Still image '{source.name}' in cuts. "
                            "Use operation='render' (auto-routes to Remotion) "
                            "or operation='remotion_render' for compositions "
                            "with images, animations, or component scenes."
                        ),
                    )
                else:
                    # Video source: trim to segment.
                    #
                    # Semantics:
                    #   timeline_start/end define placement in the final video.
                    #   source_in_seconds defines the trim point inside source media.
                    #   -ss BEFORE -i   → fast input-level seek to source_in
                    #   -t  AFTER  -i   → play for `duration` seconds.
                    #
                    # We MUST re-encode here — `-c copy` cannot do frame-accurate
                    # cuts because it snaps to keyframes. With sparse GOPs (common
                    # in Pexels / AI-generated clips), stream-copy can produce
                    # segments significantly longer than `duration`, breaking the
                    # target timeline. Re-encoding with libx264/AAC is slower but
                    # gives exact cut boundaries. Same resolution in → same
                    # resolution out, so same-res inputs concat cleanly.
                    cmd = [
                        "ffmpeg", "-y",
                        "-ss", str(source_in),
                        "-t", str(duration),
                        "-i", str(source),
                    ]

                    # Normalize every segment to a consistent container so the
                    # concat-copy step is always safe. The concat demuxer with
                    # `-c copy` requires identical codec / resolution / fps /
                    # pix_fmt / sar across ALL segments — otherwise it throws
                    # "Non-monotonous DTS" or silently produces corrupt output.
                    #
                    # Target is target_w x target_h @ 30fps, yuv420p, sar=1
                    # (default 1920x1080; overridable via `profile` or
                    # edit_decisions.metadata.compose_target — see above).
                    # fit="pad" letterboxes to preserve all content; fit="cover"
                    # scales-to-fill then centre-crops (no bars, for vertical social).
                    if fit_mode == "cover":
                        geom = [
                            f"scale={target_w}:{target_h}:force_original_aspect_ratio=increase",
                            f"crop={target_w}:{target_h}",
                        ]
                    else:
                        geom = [
                            f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease",
                            f"pad={target_w}:{target_h}:(ow-iw)/2:(oh-ih)/2:color=black",
                        ]
                    vf_parts: list[str] = [*geom, "setsar=1", "fps=30"]
                    af_parts: list[str] = []
                    if speed != 1.0:
                        vf_parts.append(f"setpts={1.0/speed}*PTS")
                        af_parts.append(self._build_atempo(speed))

                    cmd.extend(["-filter:v", ",".join(vf_parts)])
                    if af_parts:
                        cmd.extend(["-filter:a", ",".join(af_parts)])

                    cmd.extend([
                        "-c:v", codec,
                        "-crf", str(crf),
                        "-preset", preset,
                        "-pix_fmt", "yuv420p",
                        "-r", "30",
                    ])

                    # Audio handling: some source clips have no audio stream
                    # (Pexels stock often ships silent). If we unconditionally
                    # ask ffmpeg to copy/encode the 0:a stream it errors out.
                    # Probe for an audio stream first — if present, transcode
                    # to AAC; if absent, synthesize a silent stereo track so
                    # concat segments have a consistent stream layout.
                    has_audio = self._has_audio_stream(source)
                    if has_audio:
                        cmd.extend(["-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"])
                    else:
                        # Inject silent audio via lavfi before the output.
                        # We have to rebuild cmd to add the lavfi input
                        # before the output path and map streams explicitly.
                        cmd = [
                            "ffmpeg", "-y",
                            "-ss", str(source_in),
                            "-t", str(duration),
                            "-i", str(source),
                            "-f", "lavfi",
                            "-t", str(duration),
                            "-i", "anullsrc=channel_layout=stereo:sample_rate=48000",
                            "-filter:v", ",".join(vf_parts),
                        ]
                        if af_parts:
                            cmd.extend(["-filter:a", ",".join(af_parts)])
                        cmd.extend([
                            "-map", "0:v:0",
                            "-map", "1:a:0",
                            "-c:v", codec,
                            "-crf", str(crf),
                            "-preset", preset,
                            "-pix_fmt", "yuv420p",
                            "-r", "30",
                            "-c:a", "aac",
                            "-b:a", "192k",
                            "-ar", "48000",
                            "-ac", "2",
                        ])

                    cmd.append(str(seg_path))
                    self.run_command(cmd)

                temp_segments.append(seg_path)

            # Step 2: Concat segments
            concat_path = temp_dir / "concat_list.txt"
            with open(concat_path, "w", encoding="utf-8") as f:
                for seg in temp_segments:
                    safe = str(seg.resolve()).replace("\\", "/")
                    f.write(f"file '{safe}'\n")

            concat_out = temp_dir / "concat.mp4"
            cmd = [
                "ffmpeg", "-y",
                "-f", "concat", "-safe", "0",
                "-i", str(concat_path),
                "-c", "copy",
                str(concat_out),
            ]
            self.run_command(cmd)

            # Step 3: Apply subtitles and/or replace audio
            final_input = concat_out
            vfilters = []

            if subtitle_path and Path(subtitle_path).exists():
                style = inputs.get("subtitle_style", {})
                ass_style = self._build_subtitle_style(style)
                sub_escaped = str(Path(subtitle_path).resolve()).replace("\\", "/").replace(":", "\\:")
                vfilters.append(f"subtitles='{sub_escaped}':force_style='{ass_style}'")

            cmd = ["ffmpeg", "-y", "-i", str(final_input)]

            if audio_path and Path(audio_path).exists():
                cmd.extend(["-i", audio_path])

            # Determine if profile requires re-encoding (resize/fps change)
            # This must be checked BEFORE choosing copy vs encode, because
            # -s and -r are incompatible with -c:v copy.
            profile_flags: list[str] = []
            if profile_name:
                try:
                    from lib.media_profiles import get_profile
                    p = get_profile(profile_name)
                    profile_flags = ["-s", f"{p.width}x{p.height}", "-r", str(p.fps)]
                except (ImportError, ValueError):
                    pass

            needs_reencode = bool(vfilters) or bool(profile_flags)

            if needs_reencode:
                if vfilters:
                    cmd.extend(["-vf", ",".join(vfilters)])
                cmd.extend(["-c:v", codec, "-crf", str(crf), "-preset", preset])
                cmd.extend(profile_flags)
            else:
                cmd.extend(["-c:v", "copy"])

            if audio_path and Path(audio_path).exists():
                # Use type-based selectors (0:v, 1:a) instead of index-based
                # (0:v:0) because source videos may have audio as stream 0
                # and video as stream 1 (e.g. Kling-generated clips).
                cmd.extend(["-map", "0:v", "-map", "1:a", "-c:a", "aac", "-shortest"])
            else:
                cmd.extend(["-c:a", "copy"])

            cmd.append(str(output_path))
            self.run_command(cmd)

            return ToolResult(
                success=True,
                data={
                    "operation": "compose",
                    "cut_count": len(cuts),
                    "has_subtitles": subtitle_path is not None,
                    "has_mixed_audio": audio_path is not None,
                    "profile": profile_name,
                    "output": str(output_path),
                },
                artifacts=[str(output_path)],
            )
        finally:
            # Cleanup temp files
            for f in temp_segments:
                if f.exists():
                    f.unlink()
            for f in [concat_path, concat_out]:
                if f is not None and f.exists():
                    f.unlink()
            if temp_dir.exists():
                try:
                    temp_dir.rmdir()
                except OSError:
                    pass

    _REMOTION_SCENE_TYPES = {
        "text_card", "hero_title", "stat_card", "callout", "comparison",
        "progress_bar", "bar_chart", "line_chart", "pie_chart", "kpi_grid",
        "anime_scene", "terminal_scene", "screenshot_scene",
    }

    # Maps renderer_family (set at proposal stage) to Remotion composition ID.
    # Each family MUST map to a distinct composition — collapsing defeats visual grammar.
    # Maps renderer_family → Remotion composition ID.
    # Only compositions registered in remotion-composer/src/Root.tsx are valid.
    # Current compositions: Explainer, CinematicRenderer, TalkingHead
    RENDERER_FAMILY_MAP = {
        "explainer-data": "Explainer",
        "explainer-teacher": "Explainer",
        "cinematic-trailer": "CinematicRenderer",
        "documentary-montage": "CinematicRenderer",
        "product-reveal": "Explainer",
        "screen-demo": "Explainer",
        "presenter": "TalkingHead",
        "animation-first": "Explainer",
    }

    @classmethod
    def _get_composition_id(cls, renderer_family: str) -> str:
        """Resolve renderer_family to Remotion composition ID.

        Raises ValueError if renderer_family is not recognized — the caller
        must set it at proposal stage.
        """
        comp = cls.RENDERER_FAMILY_MAP.get(renderer_family)
        if comp is None:
            raise ValueError(
                f"Unknown renderer_family {renderer_family!r}. "
                f"Valid families: {sorted(cls.RENDERER_FAMILY_MAP)}. "
                f"Set renderer_family at proposal stage."
            )
        return comp

    def _render_via_atelier(
        self,
        inputs: dict[str, Any],
        edit_decisions: dict[str, Any],
    ) -> ToolResult:
        """Render a hand-authored, project-local Remotion composition ("atelier" mode).

        Unlike the cut-schema path, atelier mode does NOT route through the
        stock Explainer/CinematicRenderer compositions, the cut.type scene
        registry, or RENDERER_FAMILY_MAP. The agent hand-authors a bespoke
        composition — its own scenes, theme, and motion — and points this
        renderer at the project-local entry. This is the deliberate
        "hand-stitched every time" path: zero reusable creative components,
        a fresh visual language per video.

        Contract — edit_decisions["bespoke"] = {
            "entry":          <path to the project-local Remotion entry .tsx;
                               MUST live under remotion-composer/ so the
                               Remotion bundler can resolve node_modules.
                               Convention: remotion-composer/projects/<slug>/index.tsx>,
            "composition_id": <id registered in that entry's Root>,
            "props_path":     <optional absolute path to a props JSON (--props)>,
            "public_dir":     <optional path to a SMALL per-project public dir,
                               avoids copying the bloated shared public/>,
            "scale":          <optional float, e.g. 0.5 for a fast draft>,
            "crf":            <optional int, e.g. 18 for a crisp final>,
            "concurrency":    <optional int>,
        }
        """
        bespoke = edit_decisions.get("bespoke") or {}
        entry = bespoke.get("entry")
        comp_id = bespoke.get("composition_id")
        if not entry or not comp_id:
            return ToolResult(
                success=False,
                error=(
                    "atelier mode requires edit_decisions.bespoke.entry (path to the "
                    "project-local Remotion entry .tsx) and edit_decisions.bespoke."
                    "composition_id (the id registered in that entry's Root)."
                ),
            )

        composer_dir = Path(__file__).resolve().parent.parent.parent / "remotion-composer"
        if not composer_dir.exists() or not (composer_dir / "node_modules").exists():
            return ToolResult(
                success=False,
                error=(
                    f"remotion-composer or its node_modules is missing at {composer_dir}. "
                    f"Run `cd remotion-composer && npm install` first."
                ),
            )

        entry_path = Path(entry)
        if not entry_path.is_absolute():
            # Resolve relative to repo root first, then to the composer dir.
            repo_root = composer_dir.parent
            cand = (repo_root / entry).resolve()
            entry_path = cand if cand.exists() else (composer_dir / entry).resolve()
        entry_path = entry_path.resolve()
        if not entry_path.exists():
            return ToolResult(success=False, error=f"atelier entry not found: {entry_path}")

        # Remotion's bundler resolves `remotion` and friends by walking up from the
        # entry file to find node_modules — so the entry must live under
        # remotion-composer/ at render time. But OpenMontage's project convention is
        # repo-root projects/<slug>/, where artifacts/assets/renders/ already live.
        # Resolution: keep the source of truth under projects/<slug>/ and auto-stage
        # a directory junction (Windows) / symlink (Unix) at
        # remotion-composer/projects/<slug>/ → projects/<slug>/ so the bundler sees
        # the entry inside the composer tree without us copying files. Junctions are
        # weightless, idempotent across renders, and need no admin/dev-mode on Windows.
        try:
            entry_path.relative_to(composer_dir)
            effective_entry = entry_path
        except ValueError:
            try:
                effective_entry = self._stage_atelier_project(entry_path, composer_dir)
            except Exception as e:
                return ToolResult(
                    success=False,
                    error=(
                        f"atelier auto-stage failed for entry {entry_path}: {e}. "
                        f"Either place the entry under {composer_dir}/projects/<slug>/ "
                        f"directly, or fix the staging permission issue."
                    ),
                )

        output_path = Path(inputs.get("output_path", "renders/output.mp4")).resolve()
        output_path.parent.mkdir(parents=True, exist_ok=True)

        cmd = ["npx", "remotion", "render", str(effective_entry), str(comp_id), str(output_path)]

        props_path = bespoke.get("props_path")
        if props_path:
            pp = Path(props_path).resolve()
            if not pp.exists():
                return ToolResult(success=False, error=f"atelier props_path not found: {pp}")
            # Equals form is required for cross-platform path parsing (see _remotion_render).
            cmd.append(f"--props={pp}")

        public_dir = bespoke.get("public_dir")
        if public_dir:
            pd = Path(public_dir).resolve()
            if pd.exists():
                cmd.append(f"--public-dir={pd}")

        if bespoke.get("scale"):
            cmd.append(f"--scale={bespoke['scale']}")
        if bespoke.get("crf") is not None:
            cmd.append(f"--crf={bespoke['crf']}")
        if bespoke.get("concurrency"):
            cmd.append(f"--concurrency={bespoke['concurrency']}")

        try:
            # Run from inside the composer dir so npx resolves the local
            # remotion binary (mirrors _remotion_render).
            self.run_command(cmd, timeout=1800, cwd=composer_dir)
        except Exception as e:
            return ToolResult(success=False, error=f"Atelier (bespoke) Remotion render failed: {e}")

        if not output_path.exists():
            return ToolResult(
                success=False,
                error=f"Atelier render completed but output file missing: {output_path}",
            )

        # --- Atelier post-render review -------------------------------------
        # The cut-schema paths run _run_final_review (technical/visual/audio
        # probes + transcript-vs-script). Atelier MUST do the same so hero
        # renders aren't shipped without the safety net — and additionally
        # enforce the bespoke doctrine: no stock-registry imports, an
        # art-direction declaration must exist. The distinctness review
        # ("could this be any other product's video?") stays human; what we
        # automate here is the *doctrine bypass*, not the taste call.
        review_edit_decisions = json.loads(json.dumps(edit_decisions))
        if not review_edit_decisions.get("cuts"):
            scene_plan = inputs.get("scene_plan") or {}
            scenes = scene_plan.get("scenes", []) if isinstance(scene_plan, dict) else scene_plan
            review_edit_decisions["cuts"] = [
                {
                    "id": scene.get("id", f"scene-{index}"),
                    "source": "",
                    "type": scene.get("type", "animation"),
                    "in_seconds": scene.get("start_seconds", 0),
                    "out_seconds": scene.get("end_seconds", 0),
                    "motion_class": scene.get("motion_class"),
                    "primary_subject": scene.get("primary_subject"),
                    "visual_state_before": scene.get("visual_state_before"),
                    "visual_action": scene.get("visual_action"),
                    "visual_state_after": scene.get("visual_state_after"),
                    "semantic_purpose": scene.get("semantic_purpose"),
                    "approved_hold_reason": scene.get("approved_hold_reason"),
                }
                for index, scene in enumerate(scenes)
            ]

        final_review = self._run_final_review(
            output_path=output_path,
            edit_decisions=review_edit_decisions,
            proposal_packet=inputs.get("proposal_packet"),
            narration_transcript_path=inputs.get("narration_transcript_path"),
            script_text=inputs.get("script_text") or self._read_text_file(
                inputs.get("script_path")
            ),
            semantic_visual_review_path=inputs.get("semantic_visual_review_path"),
        )

        atelier_checks = self._run_atelier_checks(entry_path, bespoke)
        final_review.setdefault("checks", {})["atelier"] = atelier_checks
        final_review["issues_found"] = list(final_review.get("issues_found", [])) + atelier_checks.get("issues", [])

        # Atelier doctrine is executable: stock reuse, missing art direction, or
        # repeated scene scaffolding blocks delivery instead of becoming a warning.
        if (
            atelier_checks.get("stock_reuse_detected")
            or not atelier_checks.get("art_direction_declared")
            or atelier_checks.get("scene_distinctness_failed")
        ):
            final_review["status"] = "fail"
            final_review["recommended_action"] = "re_author"

        data: dict[str, Any] = {
            "operation": "render",
            "composition_mode": "atelier",
            "entry": str(entry_path),
            "effective_entry": str(effective_entry) if effective_entry != entry_path else None,
            "composition_id": comp_id,
            "output": str(output_path),
            "final_review": final_review,
            "final_review_status": final_review.get("status"),
        }

        if final_review.get("status") != "pass":
            return ToolResult(
                success=False,
                error=(
                    "Atelier render produced an invalid output:\n"
                    + "\n".join(f"  • {i}" for i in final_review.get("issues_found", []))
                ),
                data=data,
                artifacts=[str(output_path)],
            )

        return ToolResult(success=True, data=data, artifacts=[str(output_path)])

    # Source-file extensions that get staged into the composer tree at render time.
    # Anything not in this set lives only under the real project dir (assets, renders,
    # artifacts) and is referenced via --public-dir or absolute paths.
    _ATELIER_STAGE_EXTS = {".tsx", ".ts", ".jsx", ".js", ".css"}

    def _stage_atelier_project(self, entry_path: Path, composer_dir: Path) -> Path:
        """Auto-stage a bespoke project under remotion-composer/projects/<slug>/.

        The source of truth lives under the repo-root `projects/<slug>/` (where
        artifacts/, assets/, renders/ already are). Remotion's webpack bundler,
        however, resolves modules (`remotion`, `@remotion/*`) by walking up from
        the entry's REAL location — so a directory junction/symlink would
        dereference and webpack would fail to find node_modules. We copy the
        source files into a sibling dir inside the composer tree instead.

        mtime-skip semantics make repeat renders cheap (typical project is a
        handful of small .tsx files). Non-source files (assets, renders, props
        JSON) stay only in the real project dir and are referenced via
        --public-dir or absolute paths in props.

        Resolves the slug as the first path segment under a `projects/` ancestor;
        falls back to the entry's parent directory name. Returns the staged entry
        path.
        """
        import shutil

        real_project_dir = entry_path.parent.resolve()

        # Derive a stable slug. Prefer the first segment under a `projects/` ancestor.
        slug = real_project_dir.name
        try:
            parts = real_project_dir.parts
            if "projects" in parts:
                i = parts.index("projects")
                if i + 1 < len(parts):
                    slug = parts[i + 1]
        except Exception:
            pass

        staging_root = composer_dir / "projects"
        staging_root.mkdir(parents=True, exist_ok=True)
        staging_dir = staging_root / slug

        # If a stale junction/symlink is in the way from an earlier (failed) attempt,
        # remove it before creating a real staging directory.
        if staging_dir.is_symlink() or (staging_dir.exists() and staging_dir.is_dir()
                                        and staging_dir.resolve() != staging_dir):
            try:
                staging_dir.unlink()
            except (OSError, PermissionError):
                # Some Windows junctions need rmdir
                import subprocess as _sp
                _sp.run(["cmd", "/c", "rmdir", str(staging_dir)], check=True)

        staging_dir.mkdir(parents=True, exist_ok=True)

        # mtime-skip copy of source files only. Mirrors directory structure so
        # relative imports work identically.
        for src in real_project_dir.rglob("*"):
            if not src.is_file():
                continue
            if src.suffix.lower() not in self._ATELIER_STAGE_EXTS:
                continue
            rel = src.relative_to(real_project_dir)
            dst = staging_dir / rel
            try:
                if dst.exists() and dst.stat().st_mtime >= src.stat().st_mtime:
                    continue
            except OSError:
                pass
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)

        return staging_dir / entry_path.name

    # Stock-registry import patterns that violate the atelier doctrine.
    # Any of these inside a bespoke project tree means a creative component
    # was reused instead of hand-stitched. Engine knowledge (the `remotion`
    # package, `@remotion/*`, project-local files) is fine.
    _ATELIER_STOCK_IMPORT_RE = (
        r"""from\s+["']("""
        # parent-traversed paths into the stock src/
        r"""(?:\.\./)+src/(?:components|Explainer|CinematicRenderer|"""
        r"""TitledVideo|TalkingHead|CollageBurst|LyricOverlay|cinematic|crucix|phantom)"""
        # or absolute-ish paths into the same
        r"""|remotion-composer/src/(?:components|Explainer|CinematicRenderer|"""
        r"""TitledVideo|TalkingHead|CollageBurst|LyricOverlay|cinematic|crucix|phantom)"""
        r""")"""
    )

    def _run_atelier_checks(self, entry_path: Path, bespoke: dict[str, Any]) -> dict[str, Any]:
        """Doctrine-enforcement checks specific to atelier mode.

        Returns a dict with two checks:
          - stock_reuse_detected (bool) + offending_imports (list) — CRITICAL,
            fails the render. Catches `import X from "../../src/components/..."`
            and similar reuse of stock creative components.
          - art_direction_declared (bool) + art_direction (str|None) — CRITICAL.
          - scene_distinctness_failed (bool) — CRITICAL when inventory is missing,
            primary subjects repeat, or the signature device is overused.
        """
        import re as _re

        issues: list[str] = []
        offending: list[dict[str, str]] = []
        project_dir = entry_path.parent
        pat = _re.compile(self._ATELIER_STOCK_IMPORT_RE)

        try:
            for f in project_dir.rglob("*"):
                if not f.is_file() or f.suffix.lower() not in {".tsx", ".ts", ".jsx", ".js"}:
                    continue
                try:
                    txt = f.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                for m in pat.finditer(txt):
                    offending.append({"file": str(f.relative_to(project_dir)), "import": m.group(1)})
        except Exception as e:  # pragma: no cover — never let the check itself break a render
            issues.append(f"atelier stock-reuse scan errored: {e}")

        stock_reuse_detected = bool(offending)
        if stock_reuse_detected:
            issues.append(
                "atelier doctrine violation: bespoke project imports from the stock "
                "creative registry. Hand-author the scene instead — the registry is "
                "a mechanics codex, not a parts bin. Offending imports: "
                + ", ".join(f"{o['file']} → {o['import']}" for o in offending[:5])
                + ("…" if len(offending) > 5 else "")
            )

        art_direction = bespoke.get("art_direction") or bespoke.get("art_direction_note")
        art_direction_declared = bool(art_direction and str(art_direction).strip())
        if not art_direction_declared:
            issues.append(
                "atelier doctrine violation: no bespoke.art_direction declared. Per "
                "skills/meta/bespoke-composition.md step 1, every atelier piece must "
                "commit to a fresh art direction (palette, type, motion, signature "
                "device) before authoring."
            )

        inventory = bespoke.get("scene_inventory") or []
        normalized_subjects = [
            str(item.get("primary_subject", "")).strip().lower()
            for item in inventory
            if str(item.get("primary_subject", "")).strip()
        ]
        duplicate_subjects = sorted({
            subject for subject in normalized_subjects
            if normalized_subjects.count(subject) > 1
        })
        signature_count = sum(
            1 for item in inventory if item.get("signature_device_present") is True
        )
        scene_distinctness_failed = bool(duplicate_subjects or signature_count > 2 or not inventory)
        if not inventory:
            issues.append(
                "atelier doctrine violation: bespoke.scene_inventory is missing. "
                "Record each scene's primary subject and signature-device usage before render."
            )
        if duplicate_subjects:
            issues.append(
                "atelier scene distinctness violation: repeated primary subjects: "
                + ", ".join(duplicate_subjects)
            )
        if signature_count > 2:
            issues.append(
                f"atelier signature device appears in {signature_count} scenes; maximum is 2. "
                "It may not become the visual scaffolding of the whole film."
            )

        return {
            "stock_reuse_detected": stock_reuse_detected,
            "offending_imports": offending,
            "art_direction_declared": art_direction_declared,
            "art_direction": str(art_direction) if art_direction else None,
            "scene_inventory_count": len(inventory),
            "duplicate_primary_subjects": duplicate_subjects,
            "signature_device_scene_count": signature_count,
            "scene_distinctness_failed": scene_distinctness_failed,
            "issues": issues,
        }

    @staticmethod
    def _build_theme_from_playbook(
        playbook_name: str | None,
        composition_data: dict | None,
    ) -> dict[str, Any] | None:
        """Derive a Remotion ThemeConfig from a playbook's actual color values.

        Instead of passing a playbook name and hoping Remotion has a matching
        preset, we read the playbook YAML and extract concrete colors/fonts.
        This means custom playbooks, overridden palettes, and per-project
        styles all flow through to Remotion automatically.

        Falls back to extracting colors from edit_decisions metadata if
        no playbook is loadable.
        """
        theme: dict[str, Any] = {}

        # Try to load the playbook YAML
        playbook: dict[str, Any] = {}
        if playbook_name:
            try:
                from styles.playbook_loader import load_playbook
                playbook = load_playbook(playbook_name)
            except Exception:
                pass

        if playbook:
            vl = playbook.get("visual_language", {})
            palette = vl.get("color_palette", {})
            typo = playbook.get("typography", {})

            # Extract primary/accent — may be a list (gradient stops) or string
            primary_raw = palette.get("primary", ["#2563EB"])
            accent_raw = palette.get("accent", ["#F59E0B"])
            primary = primary_raw[0] if isinstance(primary_raw, list) else primary_raw
            accent = accent_raw[0] if isinstance(accent_raw, list) else accent_raw

            bg = palette.get("background", "#FFFFFF")
            text = palette.get("text", "#1F2937")
            surface = palette.get("surface", bg)
            muted = palette.get("muted_text", "#6B7280")

            # Build chart colors from all palette entries
            chart_colors = []
            for key in ["primary", "accent", "secondary", "success", "warning", "info"]:
                val = palette.get(key)
                if val:
                    chart_colors.append(val[0] if isinstance(val, list) else val)
            if len(chart_colors) < 3:
                chart_colors = [primary, accent, "#10B981", "#8B5CF6", "#EC4899", "#06B6D4"]

            theme = {
                "primaryColor": primary,
                "accentColor": accent,
                "backgroundColor": bg,
                "surfaceColor": surface,
                "textColor": text,
                "mutedTextColor": muted,
                "headingFont": typo.get("heading", {}).get("font", "Inter"),
                "bodyFont": typo.get("body", {}).get("font", "Inter"),
                "monoFont": typo.get("code", {}).get("font", "JetBrains Mono"),
                "chartColors": chart_colors[:6],
                "springConfig": {"damping": 20, "stiffness": 120, "mass": 1},
                "transitionDuration": 0.4,
            }

            # Derive caption colors from the palette
            theme["captionHighlightColor"] = primary
            # Caption background: semi-transparent version of the bg color
            theme["captionBackgroundColor"] = (
                f"rgba(255, 255, 255, 0.85)" if bg.upper() in ("#FFFFFF", "#FAFAFA", "#F9FAFB")
                else f"rgba(15, 23, 42, 0.75)"
            )

            # Motion style from playbook
            motion = playbook.get("motion", {})
            pace = motion.get("pace", "moderate")
            if pace == "fast":
                theme["springConfig"] = {"damping": 12, "stiffness": 80, "mass": 1}
                theme["transitionDuration"] = 0.3
            elif pace == "slow":
                theme["springConfig"] = {"damping": 25, "stiffness": 150, "mass": 1}
                theme["transitionDuration"] = 0.6

        # Fallback: try to extract from edit_decisions metadata
        if not theme and composition_data:
            meta = composition_data.get("metadata", {})
            if meta.get("primary_color"):
                theme = {
                    "primaryColor": meta["primary_color"],
                    "accentColor": meta.get("accent_color", "#F59E0B"),
                    "backgroundColor": meta.get("background_color", "#FFFFFF"),
                    "surfaceColor": meta.get("surface_color", "#F9FAFB"),
                    "textColor": meta.get("text_color", "#1F2937"),
                    "mutedTextColor": "#6B7280",
                    "headingFont": meta.get("heading_font", "Inter"),
                    "bodyFont": meta.get("body_font", "Inter"),
                    "monoFont": "JetBrains Mono",
                    "chartColors": meta.get("chart_colors", ["#2563EB", "#F59E0B", "#10B981"]),
                    "springConfig": {"damping": 20, "stiffness": 120, "mass": 1},
                    "transitionDuration": 0.4,
                    "captionHighlightColor": meta["primary_color"],
                    "captionBackgroundColor": "rgba(255, 255, 255, 0.85)",
                }

        return theme if theme else None

    def _needs_remotion(self, cuts: list[dict]) -> bool:
        """Determine whether Remotion should handle this composition.

        This helper is reached only after `render_runtime="remotion"` was locked
        at proposal. It decides whether the selected Remotion path is available;
        it does not choose Remotion over another approved runtime.

        Returns False only when Remotion is unavailable, which is handled as a
        blocker by the governed render path rather than a silent creative swap.

        This "Remotion-first" policy means mixed content (video clips +
        animated stills + text cards) is always composed in Remotion, which
        can embed <OffthreadVideo> alongside React components natively.
        """
        # This helper reports availability only. Governed render never uses a
        # False result to select another runtime automatically.
        if not self._remotion_available():
            return False

        # Any rich content → Remotion (fast path, catches the obvious cases)
        for cut in cuts:
            source = cut.get("source", "")
            if source and Path(source).suffix.lower() in self._IMAGE_EXTENSIONS:
                return True
            if cut.get("type") in self._REMOTION_SCENE_TYPES:
                return True
            if cut.get("animation") or cut.get("transition_in") or cut.get("transition_out"):
                return True
            transform = cut.get("transform", {})
            if transform and transform.get("animation"):
                return True

        # Even for pure-video cuts, default to Remotion — it handles video
        # clips natively via <OffthreadVideo> and gives us transitions,
        # overlays, and profile scaling for free.
        return True

    def _pre_compose_validation(
        self,
        edit_decisions: dict[str, Any],
        resolved_cuts: list[dict],
        scene_plan: list[dict] | dict[str, Any] | None = None,
        script_text: str | None = None,
    ) -> ToolResult | None:
        """Pre-compose quality gate — blocks render on critical violations.

        Checks include delivery-promise preservation, slideshow risk, renderer
        contract completeness, caption-safe layout, and viewer-facing text quality.
        Subtitle occlusion and German ASCII transliterations are blocking failures.

        Returns a failed ToolResult if render should be blocked, None if OK to proceed.
        """
        log = logging.getLogger("video_compose")
        warnings: list[str] = []
        blocks: list[str] = []

        # --- 1. Delivery promise check ---
        delivery_data = edit_decisions.get("metadata", {}).get("delivery_promise")
        if not delivery_data:
            # Also check top-level (proposal_packet nests it at top level)
            delivery_data = edit_decisions.get("delivery_promise")

        if delivery_data:
            try:
                from lib.delivery_promise import DeliveryPromise
                promise = DeliveryPromise.from_dict(delivery_data)
                result = promise.validate_cuts(resolved_cuts)
                if not result["valid"]:
                    for v in result["violations"]:
                        blocks.append(f"Delivery promise violation: {v}")
            except Exception as e:
                log.warning("Could not validate delivery promise: %s", e)
        else:
            warnings.append("No delivery_promise in edit_decisions — skipping promise validation")

        # --- 2. Slideshow risk check ---
        renderer_family = edit_decisions.get("renderer_family")
        scene_plan_data = scene_plan if isinstance(scene_plan, dict) else {}
        scenes = (
            scene_plan_data.get("scenes", [])
            if scene_plan_data
            else (scene_plan or [])
        )
        quality_tier = (
            scene_plan_data.get("quality_tier")
            or (edit_decisions.get("metadata") or {}).get("quality_tier")
            or "standard"
        )
        edit_video_category = str(edit_decisions.get("video_category") or "").strip()
        scene_video_category = str(scene_plan_data.get("video_category") or "").strip()
        video_category = edit_video_category or scene_video_category
        if edit_video_category and scene_video_category and edit_video_category != scene_video_category:
            blocks.append(
                f"video_category changed from scene plan {scene_video_category!r} "
                f"to EDL {edit_video_category!r}"
            )
        if video_category and video_category != "overview-video":
            blocks.append(f"Unsupported active video_category {video_category!r}")

        # --- 2a. Premium frame-first contract (hero / overview) ---
        try:
            from lib.premium_visual_contract import validate_premium_scene_plan
            premium = validate_premium_scene_plan(
                scene_plan_data if scene_plan_data else scenes,
                quality_tier=str(quality_tier),
                video_category=video_category,
            )
            if premium.get("active"):
                blocks.extend(
                    f"Premium visual contract violation: {issue}"
                    for issue in premium.get("violations", [])
                )
                warnings.extend(
                    f"Premium visual contract: {issue}"
                    for issue in premium.get("warnings", [])
                )
        except Exception as e:
            log.warning("Could not validate premium visual contract: %s", e)

        # Legacy/internal callers may still omit scene_plan, but operation='render'
        # rejects that before reaching this gate. Keep reconstruction only for direct
        # unit-level calls to this method.
        if not scenes and resolved_cuts:
            scenes = [
                {
                    "type": c.get("type", ""),
                    "description": c.get("reason", ""),
                    "shot_language": c.get("shot_language", {}),
                    "shot_intent": c.get("shot_intent"),
                    "narrative_role": c.get("narrative_role"),
                    "information_role": c.get("information_role"),
                    "hero_moment": c.get("hero_moment", False),
                }
                for c in resolved_cuts
            ]

        if scenes:
            try:
                from lib.slideshow_risk import score_slideshow_risk
                render_runtime = edit_decisions.get("render_runtime")
                risk = score_slideshow_risk(
                    scenes, edit_decisions, renderer_family, render_runtime
                )
                quality_floor = (
                    (delivery_data or {}).get("quality_floor")
                    or "presentable"
                )
                composition_mode = edit_decisions.get("composition_mode", "templated")
                hero_gate = (
                    quality_tier == "hero"
                    or composition_mode == "atelier"
                    or quality_floor == "broadcast"
                )
                if risk["verdict"] == "fail":
                    blocks.append(
                        f"Slideshow risk score {risk['average']:.1f}/5.0 (verdict: fail). "
                        "Video plan looks like a slideshow — revise scene plan before rendering."
                    )
                elif risk["verdict"] == "revise":
                    if quality_floor != "draft" or hero_gate:
                        blocks.append(
                            f"Slideshow risk score {risk['average']:.1f}/5.0 (verdict: revise) "
                            f"is blocking for quality_tier={quality_tier}, "
                            f"quality_floor={quality_floor}, composition_mode={composition_mode}."
                        )
                    else:
                        warnings.append(
                            f"Draft/animatic slideshow risk is {risk['average']:.1f}/5.0 "
                            "(revise); final rendering remains blocked until improved."
                        )
                elif hero_gate and risk["average"] >= 2.0:
                    blocks.append(
                        f"Hero/atelier slideshow risk {risk['average']:.1f}/5.0 exceeds "
                        "the maximum allowed 2.0. Increase semantic motion and scene variety."
                    )
            except Exception as e:
                log.warning("Could not compute slideshow risk: %s", e)

        # --- 3. Missing renderer_family (BLOCK — must be set at proposal) ---
        if not renderer_family:
            blocks.append(
                "No renderer_family in edit_decisions. "
                "renderer_family must be set at proposal stage and locked before compose. "
                "Re-run the proposal stage with a renderer_family selection."
            )

        # --- 4. Caption-safe layout contract ---------------------------------
        subtitles = edit_decisions.get("subtitles") or {}
        subtitles_enabled = bool(subtitles.get("enabled"))
        if subtitles_enabled:
            required_caption_fields = (
                "language_code",
                "unicode_normalization",
                "layout_policy",
                "preferred_zone",
                "safe_margin_px",
                "protected_regions",
                "visual_treatment",
                "full_width_background",
            )
            missing_caption_fields = [
                field for field in required_caption_fields
                if subtitles.get(field) in (None, "")
            ]
            if missing_caption_fields:
                blocks.append(
                    "Subtitle layout contract is incomplete: missing "
                    + ", ".join(missing_caption_fields)
                )

            layout_policy = subtitles.get("layout_policy")
            preferred_zone = subtitles.get("preferred_zone")
            global_regions = subtitles.get("protected_regions") or []
            if layout_policy not in {"reserved-rail", "adaptive-regions"}:
                blocks.append(
                    "subtitles.layout_policy must be 'reserved-rail' or "
                    "'adaptive-regions'"
                )
            if preferred_zone not in {"top", "bottom"}:
                blocks.append("subtitles.preferred_zone must be 'top' or 'bottom'")
            if subtitles.get("unicode_normalization") != "NFC":
                blocks.append("subtitles.unicode_normalization must be 'NFC'")
            if not global_regions:
                blocks.append(
                    "subtitles.protected_regions must declare every time-coded visual "
                    "area captions may never cover"
                )

            rail_ratio = subtitles.get("reserved_rail_height_ratio")
            if layout_policy == "reserved-rail":
                if rail_ratio is None and subtitles.get("reserved_rail_height_px") is None:
                    blocks.append(
                        "reserved-rail subtitles require reserved_rail_height_ratio "
                        "or reserved_rail_height_px"
                    )
                if rail_ratio is not None and not 0.10 <= float(rail_ratio) <= 0.30:
                    blocks.append(
                        "subtitles.reserved_rail_height_ratio must be between 0.10 and 0.30"
                    )

            if video_category == "overview-video":
                if not subtitles_enabled:
                    blocks.append("Overview-Video requires enabled subtitles")
                if subtitles.get("visual_treatment") != "integrated-field":
                    blocks.append(
                        "Overview-Video captions require visual_treatment='integrated-field'"
                    )
                if subtitles.get("full_width_background") is not False:
                    blocks.append(
                        "Overview-Video captions forbid a full-width caption background; "
                        "set full_width_background=false"
                    )
                opacity = subtitles.get("background_opacity")
                if opacity is not None and float(opacity) > 0.18:
                    blocks.append(
                        "Overview-Video integrated caption backing opacity may not exceed 0.18"
                    )

            for scene in scenes:
                scene_id = str(scene.get("id", "unknown-scene"))
                scene_regions = scene.get("protected_regions") or []
                caption_layout = scene.get("caption_layout") or {}
                if not scene_regions:
                    blocks.append(
                        f"Scene {scene_id!r} has no protected_regions; caption occlusion "
                        "cannot be proven safe"
                    )
                    continue
                if caption_layout.get("preferred_zone") not in {"top", "bottom"}:
                    blocks.append(
                        f"Scene {scene_id!r} has no valid caption_layout.preferred_zone"
                    )
                for region in scene_regions:
                    try:
                        x = float(region["x"])
                        y = float(region["y"])
                        width = float(region["width"])
                        height = float(region["height"])
                    except (KeyError, TypeError, ValueError):
                        blocks.append(
                            f"Scene {scene_id!r} contains an invalid protected region"
                        )
                        continue
                    if (
                        x < 0 or y < 0 or width <= 0 or height <= 0
                        or x + width > 1.0001 or y + height > 1.0001
                    ):
                        blocks.append(
                            f"Scene {scene_id!r} protected region "
                            f"{region.get('id', '<unnamed>')!r} exceeds normalized frame bounds"
                        )
                    if layout_policy == "reserved-rail" and rail_ratio is not None:
                        ratio = float(rail_ratio)
                        intersects_rail = (
                            preferred_zone == "bottom" and y + height > 1 - ratio + 1e-6
                        ) or (
                            preferred_zone == "top" and y < ratio - 1e-6
                        )
                        if intersects_rail:
                            blocks.append(
                                f"Scene {scene_id!r} protected region "
                                f"{region.get('id', '<unnamed>')!r} intersects the "
                                f"reserved {preferred_zone} caption rail"
                            )

        # --- 5. Unicode and German display-text quality -----------------------
        language_code = str(
            (edit_decisions.get("subtitles") or {}).get("language_code")
            or (edit_decisions.get("metadata") or {}).get("language_code")
            or ""
        )
        if language_code or script_text:
            try:
                from lib.text_quality import iter_string_values, validate_display_text

                text_sources: list[tuple[str, str]] = []
                if script_text:
                    text_sources.append(("approved script", script_text))
                if scene_plan:
                    text_sources.extend(
                        ("scene plan", value) for value in iter_string_values(scene_plan)
                    )
                text_sources.extend(
                    ("captions", value)
                    for value in iter_string_values(edit_decisions.get("captions") or [])
                )

                subtitle_source = subtitles.get("source") if subtitles_enabled else None
                if subtitle_source:
                    subtitle_path = Path(str(subtitle_source))
                    if subtitle_path.exists():
                        text_sources.append(
                            (f"subtitle source {subtitle_path}", subtitle_path.read_text(encoding="utf-8"))
                        )

                bespoke_entry = (edit_decisions.get("bespoke") or {}).get("entry")
                if bespoke_entry:
                    entry_path = Path(str(bespoke_entry))
                    if entry_path.exists():
                        text_sources.append(
                            (f"Atelier entry {entry_path}", entry_path.read_text(encoding="utf-8"))
                        )

                seen_text_issues: set[tuple[str, str, str]] = set()
                for source_name, text in text_sources:
                    for issue in validate_display_text(
                        text, language_code=language_code or None
                    ):
                        key = (source_name, issue.token, issue.replacement)
                        if key in seen_text_issues:
                            continue
                        seen_text_issues.add(key)
                        if issue.rule == "unicode_not_nfc":
                            blocks.append(
                                f"{source_name} is not Unicode NFC normalized"
                            )
                        else:
                            blocks.append(
                                f"German display text in {source_name} uses ASCII "
                                f"substitution {issue.token!r}; write {issue.replacement!r}"
                            )
            except Exception as exc:
                blocks.append(f"Display-text quality validation failed: {exc}")

        # Log warnings
        for w in warnings:
            log.warning("[pre-compose] %s", w)

        # Block on critical violations
        if blocks:
            return ToolResult(
                success=False,
                error=(
                    "Pre-compose validation failed — render blocked.\n"
                    + "\n".join(f"  • {b}" for b in blocks)
                    + ("\n\nWarnings:\n" + "\n".join(f"  • {w}" for w in warnings) if warnings else "")
                ),
            )

        return None

    def _render(self, inputs: dict[str, Any]) -> ToolResult:
        """Governed final render using the runtime and authoring mode approved at proposal.

        The caller passes proposal_packet, approved script, complete scene_plan,
        edit_decisions, and any applicable asset manifest. The method validates
        contract preservation, resolves assets/audio, executes the selected runtime,
        and returns success only after measured final_review status is ``pass``.

        There is no default runtime and no automatic fallback. Remotion,
        HyperFrames, and FFmpeg each run only when explicitly approved.
        """
        edit_decisions = inputs.get("edit_decisions")
        asset_manifest = inputs.get("asset_manifest")
        if not edit_decisions:
            return ToolResult(success=False, error="edit_decisions required for render")

        # --- Runtime routing: honor render_runtime locked at proposal ---
        # Silent swaps are forbidden by governance. Resolve this before any
        # composition-mode branching so `composition_mode="atelier"` cannot
        # accidentally force the Remotion atelier path when HyperFrames or
        # FFmpeg was approved.
        render_runtime = (edit_decisions.get("render_runtime") or "").strip().lower()

        if not render_runtime:
            return ToolResult(
                success=False,
                error=(
                    "render_runtime is not set in edit_decisions. Per governance, "
                    "it MUST be locked at proposal stage (proposal_packet."
                    "production_plan.render_runtime) and carried forward through "
                    "edit_decisions.render_runtime. Valid values: 'remotion', "
                    "'hyperframes', 'ffmpeg'. Re-run the proposal stage with an "
                    "explicit runtime choice — do NOT default this field."
                ),
            )

        if render_runtime not in {"remotion", "hyperframes", "ffmpeg"}:
            return ToolResult(
                success=False,
                error=(
                    f"Unknown render_runtime {render_runtime!r}. "
                    f"Valid values: remotion, hyperframes, ffmpeg. "
                    f"render_runtime must be set at proposal stage."
                ),
            )

        proposal_packet = inputs.get("proposal_packet")
        if not proposal_packet:
            return ToolResult(
                success=False,
                error=(
                    "proposal_packet is required for operation='render'. The compose "
                    "gate must verify the approved runtime, quality floor, delivery "
                    "promise, and composition mode; silent reconstruction is forbidden."
                ),
            )

        scene_plan = inputs.get("scene_plan")
        if not scene_plan or not (
            scene_plan.get("scenes") if isinstance(scene_plan, dict) else scene_plan
        ):
            return ToolResult(
                success=False,
                error=(
                    "scene_plan is required for operation='render' and must contain "
                    "scenes. Pre-compose validation evaluates the approved visual beat "
                    "map; it may not infer quality metadata from cuts."
                ),
            )

        approved_script_text = inputs.get("script_text") or self._read_text_file(
            inputs.get("script_path")
        )
        production_plan = proposal_packet.get("production_plan", {})
        proposal_delivery = production_plan.get("delivery_promise") or {}
        scene_plan_data = scene_plan if isinstance(scene_plan, dict) else {}

        contract_mismatches: list[str] = []
        proposal_runtime = str(production_plan.get("render_runtime", "")).strip().lower()
        proposal_mode = str(production_plan.get("composition_mode", "")).strip().lower()
        proposal_family = str(production_plan.get("renderer_family", "")).strip()
        proposal_quality = str(production_plan.get("quality_tier", "")).strip().lower()
        proposal_delivery_kind = str(production_plan.get("delivery_kind", "")).strip().lower()
        proposal_motion = str(production_plan.get("motion_expectation", "")).strip().lower()
        proposal_category = str(production_plan.get("video_category", "")).strip().lower()
        scene_category = str(scene_plan_data.get("video_category", "")).strip().lower()
        edit_category = str(edit_decisions.get("video_category", "")).strip().lower()

        if not proposal_runtime:
            contract_mismatches.append("proposal_packet.production_plan.render_runtime is missing")
        elif proposal_runtime != render_runtime:
            contract_mismatches.append(
                f"render_runtime changed from proposal {proposal_runtime!r} to EDL {render_runtime!r}"
            )
        if not proposal_mode:
            contract_mismatches.append("proposal_packet.production_plan.composition_mode is missing")
        elif proposal_mode != str(edit_decisions.get("composition_mode", "")).strip().lower():
            contract_mismatches.append(
                "composition_mode changed from proposal "
                f"{proposal_mode!r} to EDL {edit_decisions.get('composition_mode')!r}"
            )
        if not proposal_family:
            contract_mismatches.append("proposal_packet.production_plan.renderer_family is missing")
        elif proposal_family != str(edit_decisions.get("renderer_family", "")).strip():
            contract_mismatches.append(
                f"renderer_family changed from proposal {proposal_family!r} to "
                f"EDL {edit_decisions.get('renderer_family')!r}"
            )

        for key, proposal_value in (
            ("quality_tier", proposal_quality),
            ("delivery_kind", proposal_delivery_kind),
            ("motion_expectation", proposal_motion),
        ):
            scene_value = str(scene_plan_data.get(key, "")).strip().lower()
            if not proposal_value:
                contract_mismatches.append(f"proposal_packet.production_plan.{key} is missing")
            elif not scene_value:
                contract_mismatches.append(f"scene_plan.{key} is missing")
            elif proposal_value != scene_value:
                contract_mismatches.append(
                    f"{key} changed from proposal {proposal_value!r} to scene_plan {scene_value!r}"
                )

        if proposal_category:
            if proposal_category != "overview-video":
                contract_mismatches.append(
                    f"video_category {proposal_category!r} is not active"
                )
            if not scene_category:
                contract_mismatches.append("scene_plan.video_category is missing")
            elif scene_category != proposal_category:
                contract_mismatches.append(
                    f"video_category changed from proposal {proposal_category!r} "
                    f"to scene_plan {scene_category!r}"
                )
            if not edit_category:
                contract_mismatches.append("edit_decisions.video_category is missing")
            elif edit_category != proposal_category:
                contract_mismatches.append(
                    f"video_category changed from proposal {proposal_category!r} "
                    f"to EDL {edit_category!r}"
                )

        if proposal_quality == "hero":
            if proposal_delivery_kind != "bespoke":
                contract_mismatches.append("hero quality requires delivery_kind='bespoke'")
            if proposal_mode != "atelier":
                contract_mismatches.append("hero quality requires composition_mode='atelier'")
            if not production_plan.get("art_direction"):
                contract_mismatches.append("hero quality requires production_plan.art_direction")

        if contract_mismatches:
            return ToolResult(
                success=False,
                error=(
                    "Approved production contract mismatch — render blocked.\n"
                    + "\n".join(f"  • {item}" for item in contract_mismatches)
                ),
                data={"contract_mismatches": contract_mismatches},
            )

        if (
            proposal_quality == "hero"
            or proposal_delivery.get("quality_floor") == "broadcast"
        ) and not approved_script_text:
            return ToolResult(
                success=False,
                error=(
                    "Hero/broadcast render requires script_text or a readable script_path. "
                    "Final QA must transcribe the rendered output and compare it to the "
                    "approved script."
                ),
            )
        if approved_script_text and not inputs.get("script_text"):
            inputs = dict(inputs)
            inputs["script_text"] = approved_script_text

        # --- Atelier (bespoke) mode -------------------------------------
        # Hand-authored, project-local Remotion composition. Deliberately
        # bypasses the cut-schema, the stock scene-type registry, and the
        # RENDERER_FAMILY_MAP. This is the "hand-stitched every time" path:
        # the agent writes a fresh composition (its own scenes, theme, motion)
        # under remotion-composer/projects/<slug>/ and points this renderer at
        # it. No reusable creative components; a new visual language per video.
        # Triggered by composition_mode="atelier" (or renderer_family="bespoke").
        remotion_atelier_requested = (
            edit_decisions.get("composition_mode") == "atelier"
            or edit_decisions.get("renderer_family") == "bespoke"
        )
        if render_runtime == "remotion" and remotion_atelier_requested:
            atelier_scenes = (
                scene_plan.get("scenes", [])
                if isinstance(scene_plan, dict)
                else scene_plan
            )
            synthetic_cuts = [
                {
                    "id": s.get("id", f"scene-{i}"),
                    "source": "",
                    "type": s.get("type", "animation"),
                    "in_seconds": s.get("start_seconds", 0),
                    "out_seconds": s.get("end_seconds", 0),
                    "motion_class": s.get("motion_class"),
                    "visual_state_before": s.get("visual_state_before"),
                    "visual_action": s.get("visual_action"),
                    "visual_state_after": s.get("visual_state_after"),
                    "semantic_purpose": s.get("semantic_purpose"),
                }
                for i, s in enumerate(atelier_scenes)
            ]
            validation_block = self._pre_compose_validation(
                edit_decisions, synthetic_cuts, scene_plan, approved_script_text
            )
            if validation_block is not None:
                return validation_block
            return self._render_via_atelier(inputs, edit_decisions)

        composition_mode = str(edit_decisions.get("composition_mode", "templated")).lower()
        if not asset_manifest and composition_mode != "atelier":
            return ToolResult(success=False, error="asset_manifest required for templated render")

        output_path = Path(inputs.get("output_path", "renders/output.mp4"))
        output_path.parent.mkdir(parents=True, exist_ok=True)

        # Atelier compositions may own project-local assets. Templated work resolves
        # all manifest IDs before invoking the selected runtime.
        asset_lookup = {
            a["id"]: a for a in (asset_manifest or {}).get("assets", [])
        }

        cuts = edit_decisions.get("cuts", [])
        if not cuts and composition_mode != "atelier":
            return ToolResult(success=False, error="No cuts in templated edit_decisions")

        # Resolve asset IDs in cuts to file paths
        resolved_cuts = []
        for cut in cuts:
            source_id = cut.get("source", "")
            resolved_cut = dict(cut)
            if source_id in asset_lookup:
                resolved_cut["source"] = asset_lookup[source_id]["path"]
            resolved_cuts.append(resolved_cut)

        # Resolve audio asset IDs and normalize the schema aliases consumed by
        # Remotion. The EDL remains provider-neutral; the render props contain paths.
        resolved_edit_decisions = json.loads(json.dumps(edit_decisions))
        resolved_edit_decisions["cuts"] = resolved_cuts
        audio = resolved_edit_decisions.setdefault("audio", {})
        if resolved_edit_decisions.get("music") and not audio.get("music"):
            audio["music"] = resolved_edit_decisions["music"]

        def _resolve_audio_ref(layer: dict[str, Any]) -> None:
            asset_id = layer.get("asset_id")
            if asset_id in asset_lookup and not layer.get("src"):
                layer["src"] = asset_lookup[asset_id]["path"]
            if "fade_in_seconds" in layer and "fadeInSeconds" not in layer:
                layer["fadeInSeconds"] = layer["fade_in_seconds"]
            if "fade_out_seconds" in layer and "fadeOutSeconds" not in layer:
                layer["fadeOutSeconds"] = layer["fade_out_seconds"]

        narration = audio.get("narration") or {}
        if isinstance(narration, dict):
            _resolve_audio_ref(narration)
            for segment in narration.get("segments", []) or []:
                if isinstance(segment, dict):
                    _resolve_audio_ref(segment)
        music = audio.get("music") or {}
        if isinstance(music, dict):
            _resolve_audio_ref(music)
        for sfx in audio.get("sfx", []) or []:
            if isinstance(sfx, dict):
                _resolve_audio_ref(sfx)

        edit_decisions = resolved_edit_decisions

        # --- Pre-compose validation gate ---
        validation_block = self._pre_compose_validation(
            edit_decisions, resolved_cuts, scene_plan, approved_script_text
        )
        if validation_block is not None:
            return validation_block

        # Also accept profile as "output_profile" (skill convention) or "profile"
        profile = inputs.get("profile") or inputs.get("output_profile")

        if render_runtime == "hyperframes":
            return self._render_via_hyperframes(
                inputs=inputs,
                edit_decisions=edit_decisions,
                asset_manifest=asset_manifest,
                resolved_cuts=resolved_cuts,
                output_path=output_path,
                profile=profile,
            )
        if render_runtime == "ffmpeg":
            # Caller explicitly asked for FFmpeg — don't auto-upgrade to Remotion.
            return self._render_via_ffmpeg(
                inputs=inputs,
                edit_decisions=edit_decisions,
                resolved_cuts=resolved_cuts,
                output_path=output_path,
                profile=profile,
            )
        # --- Explicit Remotion path (render_runtime == 'remotion') ---
        # Content simplicity never authorizes a runtime swap. A governed Remotion
        # final either renders in Remotion or returns a blocker.
        if not self._remotion_available():
            return ToolResult(
                success=False,
                error=(
                    "render_runtime='remotion' was locked at proposal, but Remotion "
                    "is unavailable. Automatic fallback to FFmpeg is forbidden. "
                    "Install/fix Remotion or obtain approval for a new proposal decision."
                ),
                data={
                    "runtime_selection": {
                        "requested": "remotion",
                        "actual": None,
                        "fallback_blocked": True,
                    }
                },
            )

        remotion_inputs: dict[str, Any] = {
            "edit_decisions": dict(edit_decisions, cuts=resolved_cuts),
            "output_path": str(output_path),
        }
        if profile:
            remotion_inputs["profile"] = profile
        if inputs.get("remotion_timeout_ms") is not None:
            remotion_inputs["remotion_timeout_ms"] = inputs["remotion_timeout_ms"]
        render_result = self._remotion_render(remotion_inputs)

        if not render_result.success:
            renderer_family = edit_decisions.get("renderer_family", "unknown")
            return ToolResult(
                success=False,
                error=(
                    f"Remotion render failed for renderer_family={renderer_family!r}. "
                    f"Underlying error: {render_result.error}. The approved runtime "
                    "may not be replaced automatically; fix Remotion or obtain approval "
                    "for a new proposal/runtime decision."
                ),
                data={
                    "runtime_selection": {
                        "requested": "remotion",
                        "actual": None,
                        "fallback_blocked": True,
                    }
                },
            )

        # --- Post-render: mandatory final self-review ---
        if render_result.success and output_path.exists():
            final_review = self._run_final_review(
                output_path,
                edit_decisions,
                inputs.get("proposal_packet"),
                narration_transcript_path=inputs.get("narration_transcript_path"),
                script_text=inputs.get("script_text") or self._read_text_file(
                    inputs.get("script_path")
                ),
                semantic_visual_review_path=inputs.get("semantic_visual_review_path"),
            )

            # Attach final_review to the ToolResult data so the compose-director
            # skill can include it in the checkpoint alongside the render_report.
            if render_result.data is None:
                render_result.data = {}
            render_result.data["final_review"] = final_review
            render_result.data["final_review_status"] = final_review["status"]

            # Final delivery is allowed only on an explicit pass. `revise` means
            # the output exists but must be corrected and rendered again.
            if final_review["status"] != "pass":
                return ToolResult(
                    success=False,
                    error=(
                        f"Post-render self-review BLOCKED delivery ({final_review['status']}).\n"
                        + "\n".join(f"  • {i}" for i in final_review.get("issues_found", []))
                    ),
                    data=render_result.data,
                )

        return render_result

    @staticmethod
    def _validate_bespoke_scene_inventory(
        bespoke: dict[str, Any],
        *,
        runtime: str,
        workspace_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Validate runtime-neutral Atelier doctrine before and after render."""
        issues: list[str] = []
        art_direction = bespoke.get("art_direction") or bespoke.get("art_direction_note")
        art_direction_declared = bool(art_direction and str(art_direction).strip())
        if not art_direction_declared:
            issues.append(
                f"{runtime} Atelier doctrine violation: bespoke.art_direction is missing"
            )

        inventory = bespoke.get("scene_inventory") or []
        normalized_subjects = [
            str(item.get("primary_subject", "")).strip().lower()
            for item in inventory
            if str(item.get("primary_subject", "")).strip()
        ]
        duplicate_subjects = sorted({
            subject for subject in normalized_subjects
            if normalized_subjects.count(subject) > 1
        })
        signature_count = sum(
            1 for item in inventory if item.get("signature_device_present") is True
        )
        if not inventory:
            issues.append(
                f"{runtime} Atelier doctrine violation: bespoke.scene_inventory is missing"
            )
        if duplicate_subjects:
            issues.append(
                f"{runtime} Atelier scene distinctness violation: repeated primary "
                "subjects: " + ", ".join(duplicate_subjects)
            )
        if signature_count > 2:
            issues.append(
                f"{runtime} Atelier signature device appears in {signature_count} "
                "scenes; maximum is 2"
            )

        workspace_exists: bool | None = None
        if workspace_path is not None:
            path = Path(workspace_path).expanduser()
            if not path.is_absolute():
                path = (Path(__file__).resolve().parents[2] / path).resolve()
            else:
                path = path.resolve()
            workspace_exists = path.is_dir() and (path / "index.html").is_file()
            if not workspace_exists:
                issues.append(
                    f"{runtime} Atelier workspace/index.html not found: {path}"
                )

        return {
            "runtime": runtime,
            "art_direction_declared": art_direction_declared,
            "art_direction": str(art_direction) if art_direction else None,
            "scene_inventory_count": len(inventory),
            "duplicate_primary_subjects": duplicate_subjects,
            "signature_device_scene_count": signature_count,
            "workspace_exists": workspace_exists,
            "scene_distinctness_failed": bool(
                not inventory or duplicate_subjects or signature_count > 2
            ),
            "issues": issues,
        }

    def _render_via_hyperframes(
        self,
        *,
        inputs: dict[str, Any],
        edit_decisions: dict[str, Any],
        asset_manifest: dict[str, Any],
        resolved_cuts: list[dict],
        output_path: Path,
        profile: Optional[str],
    ) -> ToolResult:
        """Delegate to hyperframes_compose and run the mandatory final self-review.

        Governance: if HyperFrames is unavailable or fails, return a structured
        blocker — do NOT silently route to Remotion or FFmpeg. The agent must
        surface the blocker and get user approval before any runtime swap.
        """
        if not self._hyperframes_available():
            return ToolResult(
                success=False,
                error=(
                    "render_runtime='hyperframes' was locked at proposal, but "
                    "the HyperFrames runtime is not available on this machine. "
                    "Per governance this is a BLOCKER — surface it to the user "
                    "per AGENT_GUIDE.md > 'Escalate Blockers Explicitly' and wait "
                    "for approval before switching runtime. Requirements: "
                    "Node.js >= 22, FFmpeg, and npx on PATH. See "
                    "tools/video/hyperframes_compose.py for the specific missing piece."
                ),
            )

        try:
            from tools.video.hyperframes_compose import HyperFramesCompose
        except Exception as e:
            return ToolResult(
                success=False,
                error=f"Could not import hyperframes_compose: {e}",
            )

        workspace_path = (
            inputs.get("workspace_path")
            or str(output_path.parent.parent / "hyperframes")
        )

        # Pass the playbook through so the style bridge can emit CSS vars.
        playbook_data = inputs.get("playbook")
        if not playbook_data:
            playbook_name = (
                inputs.get("playbook_name")
                or (edit_decisions.get("metadata") or {}).get("playbook")
            )
            if playbook_name:
                try:
                    from styles.playbook_loader import load_playbook  # type: ignore
                    playbook_data = load_playbook(playbook_name)
                except Exception:
                    playbook_data = None

        composition_mode = str(edit_decisions.get("composition_mode", "templated")).lower()
        bespoke = edit_decisions.get("bespoke") or {}
        if composition_mode == "atelier":
            workspace_path = bespoke.get("workspace_path") or inputs.get("workspace_path")
            atelier_checks = self._validate_bespoke_scene_inventory(
                bespoke,
                runtime="hyperframes",
                workspace_path=workspace_path,
            )
            if atelier_checks["issues"]:
                return ToolResult(
                    success=False,
                    error=(
                        "HyperFrames Atelier contract failed before render:\n"
                        + "\n".join(f"  • {issue}" for issue in atelier_checks["issues"])
                    ),
                    data={"atelier_checks": atelier_checks},
                )
        else:
            atelier_checks = None

        if composition_mode == "atelier":
            scene_plan = inputs.get("scene_plan") or {}
            scenes = scene_plan.get("scenes", []) if isinstance(scene_plan, dict) else scene_plan
            synthetic_cuts = [
                {
                    "id": scene.get("id", f"scene-{index}"),
                    "source": "",
                    "type": scene.get("type", "animation"),
                    "in_seconds": scene.get("start_seconds", 0),
                    "out_seconds": scene.get("end_seconds", 0),
                    "motion_class": scene.get("motion_class"),
                    "primary_subject": scene.get("primary_subject"),
                    "visual_state_before": scene.get("visual_state_before"),
                    "visual_action": scene.get("visual_action"),
                    "visual_state_after": scene.get("visual_state_after"),
                    "semantic_purpose": scene.get("semantic_purpose"),
                    "approved_hold_reason": scene.get("approved_hold_reason"),
                }
                for index, scene in enumerate(scenes)
            ]
            hf_edit_decisions = dict(edit_decisions, cuts=synthetic_cuts)
            if not hf_edit_decisions.get("total_duration_seconds"):
                hf_edit_decisions["total_duration_seconds"] = max(
                    (float(scene.get("end_seconds", 0) or 0) for scene in scenes),
                    default=0,
                )
        else:
            hf_edit_decisions = dict(edit_decisions, cuts=resolved_cuts)

        # Use the QA-enriched contract for all remaining HyperFrames checks while
        # leaving the hand-authored workspace itself untouched.
        edit_decisions = hf_edit_decisions

        hf_inputs: dict[str, Any] = {
            "operation": "render",
            "workspace_path": workspace_path,
            "output_path": str(output_path),
            "edit_decisions": hf_edit_decisions,
            "asset_manifest": asset_manifest or {"assets": []},
            "strict": True,
        }
        if playbook_data:
            hf_inputs["playbook"] = playbook_data
        if profile:
            hf_inputs["profile"] = profile
        if "quality" in inputs:
            hf_inputs["quality"] = inputs["quality"]
        if "fps" in inputs:
            hf_inputs["fps"] = inputs["fps"]
        if "strict" in inputs:
            hf_inputs["strict"] = inputs["strict"]
        if "skip_contrast" in inputs:
            hf_inputs["skip_contrast"] = inputs["skip_contrast"]

        render_result = HyperFramesCompose().execute(hf_inputs)

        if not render_result.success:
            return ToolResult(
                success=False,
                error=(
                    f"HyperFrames render failed: {render_result.error}. "
                    "Per governance: do NOT silently fall back to Remotion or "
                    "FFmpeg. Surface the failure to the user along with the "
                    "hyperframes_compose step log before proposing a swap."
                ),
                data=render_result.data,
            )

        # Post-render: mandatory final self-review (identical contract to the Remotion path).
        if output_path.exists():
            final_review = self._run_final_review(
                output_path,
                edit_decisions,
                inputs.get("proposal_packet"),
                narration_transcript_path=inputs.get("narration_transcript_path"),
                script_text=inputs.get("script_text") or self._read_text_file(
                    inputs.get("script_path")
                ),
                semantic_visual_review_path=inputs.get("semantic_visual_review_path"),
            )
            if render_result.data is None:
                render_result.data = {}
            render_result.data["final_review"] = final_review
            render_result.data["final_review_status"] = final_review["status"]
            if final_review["status"] != "pass":
                return ToolResult(
                    success=False,
                    error=(
                        f"Post-render self-review BLOCKED delivery (HyperFrames: {final_review['status']}).\n"
                        + "\n".join(f"  • {i}" for i in final_review.get("issues_found", []))
                    ),
                    data=render_result.data,
                )

        return render_result

    def _render_via_ffmpeg(
        self,
        *,
        inputs: dict[str, Any],
        edit_decisions: dict[str, Any],
        resolved_cuts: list[dict],
        output_path: Path,
        profile: Optional[str],
    ) -> ToolResult:
        """Explicit FFmpeg-only render path.

        Use when the proposal locked `render_runtime="ffmpeg"` — e.g. simple
        source-footage concat/trim jobs that don't benefit from composition.
        Still runs the mandatory final self-review.
        """
        options = inputs.get("options", {})
        subtitle_burn = options.get("subtitle_burn", True)

        subtitle_path = inputs.get("subtitle_path")
        if subtitle_burn and not subtitle_path:
            ed_subs = edit_decisions.get("subtitles", {})
            if ed_subs.get("enabled") and ed_subs.get("source"):
                subtitle_path = ed_subs["source"]

        compose_inputs = dict(inputs)
        compose_inputs["edit_decisions"] = dict(edit_decisions, cuts=resolved_cuts)
        compose_inputs["output_path"] = str(output_path)
        if subtitle_path:
            compose_inputs["subtitle_path"] = subtitle_path
        if profile:
            compose_inputs["profile"] = profile

        render_result = self._compose(compose_inputs)

        if render_result.success and output_path.exists():
            final_review = self._run_final_review(
                output_path,
                edit_decisions,
                inputs.get("proposal_packet"),
                narration_transcript_path=inputs.get("narration_transcript_path"),
                script_text=inputs.get("script_text") or self._read_text_file(
                    inputs.get("script_path")
                ),
                semantic_visual_review_path=inputs.get("semantic_visual_review_path"),
            )
            if render_result.data is None:
                render_result.data = {}
            render_result.data["final_review"] = final_review
            render_result.data["final_review_status"] = final_review["status"]
            if final_review["status"] != "pass":
                return ToolResult(
                    success=False,
                    error=(
                        f"Post-render self-review BLOCKED delivery (FFmpeg: {final_review['status']}).\n"
                        + "\n".join(f"  • {i}" for i in final_review.get("issues_found", []))
                    ),
                    data=render_result.data,
                )

        return render_result

    def _remotion_render(self, inputs: dict[str, Any]) -> ToolResult:
        """Render via Remotion (requires Node.js + npx).

        Handles compositions with still images, animated scenes, component
        types, and transitions using React-based frame-accurate rendering.
        Accepts edit_decisions (with resolved file paths) or raw composition_data.
        """
        import shutil

        if not shutil.which("npx"):
            return ToolResult(
                success=False,
                error="npx not found. Install Node.js to use Remotion rendering.",
            )

        composition_data = inputs.get("edit_decisions") or inputs.get("composition_data")
        if not composition_data:
            return ToolResult(
                success=False,
                error="edit_decisions or composition_data required for remotion_render",
            )

        output_path = Path(inputs.get("output_path", "renders/remotion_output.mp4"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        # Absolutise so the CLI can resolve the output regardless of cwd.
        output_path = output_path.resolve()

        # Deep-copy props so we don't mutate the original
        props = json.loads(json.dumps(composition_data))

        # Resolve source paths for Remotion's Img and OffthreadVideo components.
        # Remotion serves files from remotion-composer/public/ via staticFile().
        # Relative paths (e.g. "01-home.png") work via staticFile() in public/.
        # Absolute paths must be converted to file:// URIs since Remotion's
        # dev server can only serve files from public/.
        # DO NOT resolve relative paths to absolute — that breaks staticFile().
        for cut in props.get("cuts", []):
            source = cut.get("source", "")
            if not source or source.startswith(("http://", "https://", "file://")):
                continue
            resolved = Path(source).resolve()
            if resolved.exists():
                # Absolute path on disk — convert to file:// URI
                posix = resolved.as_posix()
                cut["source"] = f"file:///{posix}" if not posix.startswith("/") else f"file://{posix}"
            # else: relative path — leave as-is for staticFile() in public/

        # Build a custom themeConfig from the playbook's actual colors.
        # This ensures every video gets a unique visual identity derived
        # from its production decisions — not picked from a preset menu.
        if "themeConfig" not in props:
            playbook_name = (
                props.get("playbook")
                or props.get("theme")
                or props.get("metadata", {}).get("playbook")
            )
            theme_config = self._build_theme_from_playbook(playbook_name, composition_data)
            if theme_config:
                props["themeConfig"] = theme_config

        # Write props to temp file for Remotion CLI
        props_path = output_path.parent / ".remotion_props.json"
        with open(props_path, "w", encoding="utf-8") as f:
            json.dump(props, f)

        # remotion-composer lives at project root
        composer_dir = Path(__file__).resolve().parent.parent.parent / "remotion-composer"
        if not composer_dir.exists():
            return ToolResult(
                success=False,
                error=f"Remotion composer project not found at {composer_dir}",
            )

        # Route to the correct Remotion composition based on renderer_family.
        # This prevents all pipelines from collapsing into the Explainer visual grammar.
        renderer_family = (composition_data or {}).get("renderer_family", "explainer-data")
        composition_id = self._get_composition_id(renderer_family)

        cmd = [
            "npx", "remotion", "render",
            str(composer_dir / "src" / "index.tsx"),
            composition_id,
            str(output_path),
            # Use the `--props=<path>` equals form rather than two separate
            # args. On Windows, passing `--props` and the path separately makes
            # Remotion mis-parse the value (quote escaping differs), failing
            # with "neither valid JSON nor a file path". The equals form is the
            # API Remotion recommends for file paths and is cross-platform safe.
            f"--props={props_path}",
        ]

        # Apply media profile dimensions
        profile_name = inputs.get("profile")
        if profile_name:
            try:
                from lib.media_profiles import get_profile
                p = get_profile(profile_name)
                cmd.extend(["--width", str(p.width), "--height", str(p.height)])
            except (ImportError, ValueError):
                pass

        # Optional creator-facing render timeout. Remotion's `--timeout` (ms)
        # governs headless-browser setup and delayRender(); on slow machines or
        # restricted networks the default 30s browser setup times out with an
        # opaque failure. Pass it through and give the subprocess enough headroom
        # so run_command() does not kill Remotion before its own timeout fires.
        remotion_timeout_ms = inputs.get("remotion_timeout_ms")
        subprocess_timeout = 600
        if remotion_timeout_ms:
            try:
                ms = int(remotion_timeout_ms)
                cmd.append(f"--timeout={ms}")
                subprocess_timeout = max(subprocess_timeout, ms // 1000 + 60)
            except (TypeError, ValueError):
                pass

        try:
            # Invoke from inside the composer dir so npx can resolve the
            # local remotion binary via node_modules/.bin. Without this,
            # Windows npx cannot locate the CLI and returns "could not
            # determine executable to run".
            self.run_command(cmd, timeout=subprocess_timeout, cwd=composer_dir)
        except subprocess.CalledProcessError as e:
            # run_command uses check=True + capture_output, so the useful
            # Remotion diagnostics live in stderr/stdout — surface the tail
            # instead of the bare "returned non-zero exit status 1".
            detail = (e.stderr or e.stdout or "").strip()
            tail = "\n".join(detail.splitlines()[-25:]) if detail else "(no output captured)"
            return ToolResult(
                success=False,
                error=f"Remotion render failed (exit {e.returncode}):\n{tail}",
            )
        except subprocess.TimeoutExpired as e:
            return ToolResult(
                success=False,
                error=(
                    f"Remotion render timed out after {e.timeout}s. If the headless "
                    "browser is slow to start, raise remotion_timeout_ms (ms)."
                ),
            )
        except Exception as e:
            return ToolResult(success=False, error=f"Remotion render failed: {e}")
        finally:
            if props_path.exists():
                props_path.unlink()

        if not output_path.exists():
            return ToolResult(
                success=False,
                error=f"Remotion render completed but output file missing: {output_path}",
            )

        return ToolResult(
            success=True,
            data={
                "operation": "remotion_render",
                "output": str(output_path),
                "profile": profile_name,
            },
            artifacts=[str(output_path)],
        )

    # ------------------------------------------------------------------
    # Final self-review — mandatory post-render inspection
    # ------------------------------------------------------------------

    # Punctuation/SSML-leak words that should NEVER appear in rendered audio.
    # When a TTS engine reads a literal "..." as the word "dot", or a "—" as
    # "hyphen", those leak into the transcript. Catching these in the final
    # review is the difference between catching a bad voice render in-tool
    # vs. shipping a video that says "dot dot dot" twelve times. CRITICAL.
    _TTS_PUNCTUATION_LEAK_WORDS = {
        "dot", "dots", "ellipsis", "period", "periods",
        "comma", "commas", "semicolon", "colon",
        "dash", "hyphen", "emdash", "endash",
        "parenthesis", "bracket", "brace",
        "asterisk", "slash", "backslash",
        "exclamation", "question mark",
    }

    @staticmethod
    def _read_text_file(path: str | Path | None) -> str | None:
        """Read a small text file if given a path; None-safe and exception-safe."""
        if not path:
            return None
        try:
            return Path(path).read_text(encoding="utf-8")
        except Exception:
            return None

    @classmethod
    def _tokenize(cls, text: str) -> list[str]:
        """Split text into comparable word tokens (lowercased, punctuation
        stripped, numeric-word-aware). Empty tokens dropped."""
        import re

        # Preserve hyphenated words as single tokens ("many-worlds" -> "many-worlds").
        # Drop everything except letters, digits, hyphens, apostrophes.
        cleaned = re.sub(r"[^A-Za-z0-9\-' ]+", " ", text.lower())
        return [t for t in cleaned.split() if t and t != "-"]

    @classmethod
    def _compare_transcript_to_script(
        cls,
        transcript_path: Path,
        script_text: str,
    ) -> dict[str, Any]:
        """Compare a word-level transcript against the source script.

        Purpose: catch TTS failures that look fine on audio-volume/duration
        checks but produce garbage content. The canonical example is
        Chirp3-HD reading ellipses ("...") literally as the word "dot" — our
        volume check says "narration present, not clipped" and the video
        ships. This check diffs the actual transcribed audio against what
        was supposed to be said, and flags:

        - Spurious punctuation-leak words ("dot", "comma", "hyphen", etc.)
          that appear in audio but not script → CRITICAL
        - Overall word-accuracy ratio against script → SUGGESTION if < 0.9

        Returns the transcript_comparison section of final_review, or a
        placeholder with an issue describing why the check couldn't run
        (missing transcript, missing script) so the review never goes
        silently quiet on this contract.
        """
        result: dict[str, Any] = {
            "transcript_matches_script": False,
            "word_accuracy": None,
            "script_word_count": 0,
            "transcript_word_count": 0,
            "spurious_punctuation_words": [],
            "issues": [],
        }

        if not transcript_path or not Path(transcript_path).is_file():
            result["issues"].append(
                "transcript_comparison skipped: narration_transcript not provided"
            )
            return result
        if not script_text:
            result["issues"].append(
                "transcript_comparison skipped: script_text not provided"
            )
            return result

        try:
            transcript_data = json.loads(Path(transcript_path).read_text(encoding="utf-8"))
        except Exception as e:
            result["issues"].append(f"transcript_comparison could not parse transcript: {e}")
            return result

        transcript_words = [
            w.get("word", "").strip() for w in transcript_data.get("word_timestamps", [])
        ]
        transcript_tokens = cls._tokenize(" ".join(transcript_words))
        script_tokens = cls._tokenize(script_text)

        result["script_word_count"] = len(script_tokens)
        result["transcript_word_count"] = len(transcript_tokens)

        if not script_tokens or not transcript_tokens:
            result["issues"].append(
                f"transcript_comparison: empty token set "
                f"(script={len(script_tokens)}, transcript={len(transcript_tokens)})"
            )
            return result

        # --- Punctuation-leak detection (TTS reading literal punctuation) ---
        script_set = set(script_tokens)
        leak_occurrences: dict[str, int] = {}
        for token in transcript_tokens:
            if token in cls._TTS_PUNCTUATION_LEAK_WORDS and token not in script_set:
                leak_occurrences[token] = leak_occurrences.get(token, 0) + 1

        if leak_occurrences:
            formatted = ", ".join(
                f"{w!r}×{n}" for w, n in sorted(leak_occurrences.items(), key=lambda x: -x[1])
            )
            result["spurious_punctuation_words"] = [
                {"word": w, "count": n} for w, n in leak_occurrences.items()
            ]
            result["issues"].append(
                f"TTS punctuation leak: transcript contains {formatted} — "
                f"these words are NOT in the script, which means the voice "
                f"engine is reading literal punctuation aloud. Rewrite the "
                f"script to eliminate the corresponding characters (ellipses, "
                f"em-dashes, etc.) and regenerate narration."
            )

        # --- Word accuracy via set overlap (cheap & ordering-insensitive) ---
        # We don't penalize small word-order differences or minor TTS
        # hallucinations; we just want to know "did 90%+ of the script's
        # content make it into the audio." Using set overlap on the script
        # side is robust to transcription noise.
        matched = sum(1 for t in script_tokens if t in set(transcript_tokens))
        accuracy = matched / max(1, len(script_tokens))
        result["word_accuracy"] = round(accuracy, 3)
        result["transcript_matches_script"] = accuracy >= 0.9 and not leak_occurrences

        if accuracy < 0.9:
            result["issues"].append(
                f"Low transcript-to-script match: only {accuracy:.0%} of script "
                f"words appear in the transcribed audio ({matched}/"
                f"{len(script_tokens)}). Narration may be truncated, mispronounced, "
                f"or the wrong script was used."
            )

        return result

    def _run_final_review(
        self,
        output_path: Path,
        edit_decisions: dict[str, Any] | None = None,
        proposal_packet: dict[str, Any] | None = None,
        narration_transcript_path: str | Path | None = None,
        script_text: str | None = None,
        semantic_visual_review_path: str | Path | None = None,
    ) -> dict[str, Any]:
        """Run post-render self-review and produce a final_review artifact.

        This is the governance contract: the compose runtime MUST inspect
        the actual rendered output before marking the stage complete.
        Never claim a video is ready without a real probe + frame sample.

        When `proposal_packet` is provided, its
        `production_plan.render_runtime` is compared against
        `edit_decisions.render_runtime` so `runtime_swap_detected` can
        actually flip. Without it, we fall back to
        `edit_decisions.metadata.proposal_render_runtime` (which the edit
        director can set explicitly to opt into swap detection).

        Returns a dict conforming to final_review.schema.json.
        """
        log = logging.getLogger("video_compose.final_review")
        issues: list[str] = []

        # --- 1. Technical probe via ffprobe ---
        technical_probe: dict[str, Any] = {
            "valid_container": False,
            "issues": [],
        }
        try:
            cmd = [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", str(output_path),
            ]
            proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if proc.returncode == 0:
                probe_data = json.loads(proc.stdout)
                fmt = probe_data.get("format", {})
                streams = probe_data.get("streams", [])
                video_stream = next(
                    (s for s in streams if s.get("codec_type") == "video"), {}
                )
                audio_stream = next(
                    (s for s in streams if s.get("codec_type") == "audio"), {}
                )

                duration = float(fmt.get("duration", 0))
                width = int(video_stream.get("width", 0))
                height = int(video_stream.get("height", 0))
                fps_str = video_stream.get("r_frame_rate", "0/1")
                fps = self._parse_probe_fps(fps_str)

                technical_probe = {
                    "valid_container": bool(video_stream),
                    "duration_seconds": round(duration, 2),
                    "resolution": f"{width}x{height}",
                    "fps": fps,
                    "has_audio": bool(audio_stream),
                    "codec": video_stream.get("codec_name", "unknown"),
                    "file_size_bytes": int(fmt.get("size", 0)),
                    "issues": [],
                }

                # Sanity checks
                if duration < 1.0:
                    technical_probe["issues"].append(
                        f"Output is only {duration:.1f}s — suspiciously short"
                    )

                # Check target duration from edit_decisions
                target_dur = None
                if edit_decisions:
                    target_dur = (
                        edit_decisions.get("total_duration_seconds")
                        or edit_decisions.get("metadata", {}).get("target_duration_seconds")
                    )
                if target_dur and target_dur > 0:
                    drift_pct = abs(duration - target_dur) / target_dur
                    if drift_pct > 0.25:
                        technical_probe["issues"].append(
                            f"Duration drift: rendered {duration:.1f}s vs target {target_dur}s "
                            f"({drift_pct:.0%} off). Review pacing or trim."
                        )
                    technical_probe["target_duration"] = target_dur
                    technical_probe["duration_drift_pct"] = round(drift_pct * 100, 1)
                if width < 320 or height < 240:
                    technical_probe["issues"].append(
                        f"Resolution {width}x{height} is very low"
                    )
                if not audio_stream:
                    technical_probe["issues"].append("No audio stream in output")
            else:
                technical_probe["issues"].append(
                    f"ffprobe failed with exit code {proc.returncode}"
                )
        except FileNotFoundError:
            technical_probe["issues"].append("ffprobe not found — cannot validate output")
        except Exception as e:
            technical_probe["issues"].append(f"ffprobe error: {e}")

        issues.extend(technical_probe.get("issues", []))

        # --- 2. Render-based visual QA ---------------------------------
        # Inspect scene boundaries and a 2-FPS low-resolution stream. This turns
        # motion/freeze/repetition checks into measurements of the rendered video
        # rather than trusting declarations in the scene plan.
        visual_spotcheck: dict[str, Any] = {
            "frames_sampled": 0,
            "frame_paths": [],
            "scene_boundary_frames": [],
            "contact_sheet_path": None,
            "sample_fps": 2.0,
            "motion_frames_analyzed": 0,
            "motion_coverage_ratio": 0.0,
            "required_motion_coverage_ratio": 0.0,
            "mean_frame_difference": 0.0,
            "freeze_segments": [],
            "repeated_layout_pairs": [],
            "black_frames_detected": False,
            "broken_overlays": False,
            "missing_assets": False,
            "unreadable_text": False,
            "automated_text_collision_check": False,
            "issues": [],
        }
        production_plan = (proposal_packet or {}).get("production_plan", {})
        delivery_contract = (
            (edit_decisions or {}).get("delivery_promise")
            or (edit_decisions or {}).get("metadata", {}).get("delivery_promise")
            or production_plan.get("delivery_promise")
            or {}
        )
        quality_tier = (
            production_plan.get("quality_tier")
            or (edit_decisions or {}).get("metadata", {}).get("quality_tier")
            or "standard"
        )
        quality_floor = delivery_contract.get("quality_floor", "presentable")
        motion_required = bool(delivery_contract.get("motion_required"))
        if quality_tier == "hero" or quality_floor == "broadcast":
            required_rendered_motion_ratio = 0.65
        elif motion_required and quality_floor != "draft":
            required_rendered_motion_ratio = 0.40
        else:
            required_rendered_motion_ratio = 0.0
        visual_spotcheck["required_motion_coverage_ratio"] = required_rendered_motion_ratio

        approved_hold_windows: list[dict[str, Any]] = []
        if edit_decisions:
            for cut in edit_decisions.get("cuts", []) or []:
                reason = cut.get("approved_hold_reason")
                if cut.get("motion_class") == "static_hold" and reason:
                    approved_hold_windows.append({
                        "start": float(cut.get("in_seconds", 0) or 0),
                        "end": float(cut.get("out_seconds", 0) or 0),
                        "reason": str(reason),
                    })

        duration = technical_probe.get("duration_seconds", 0)
        if duration > 0 and technical_probe.get("valid_container"):
            try:
                from PIL import Image, ImageDraw
                import numpy as np

                frame_dir = output_path.parent / ".final_review_frames"
                frame_dir.mkdir(parents=True, exist_ok=True)

                # Opening/middle/ending plus every scene boundary. Offset boundary
                # samples slightly inward to avoid measuring a transition midpoint
                # as the representative state of either scene.
                timestamps: set[float] = {
                    round(duration * 0.10, 3),
                    round(duration * 0.35, 3),
                    round(duration * 0.65, 3),
                    round(duration * 0.90, 3),
                }
                boundary_timestamps: set[float] = set()
                if edit_decisions:
                    for cut in edit_decisions.get("cuts", []) or []:
                        start = float(cut.get("in_seconds", 0) or 0)
                        end = float(cut.get("out_seconds", start) or start)
                        cut_duration = max(0.0, end - start)
                        inward = min(0.10, cut_duration * 0.10)
                        for raw in (start + inward, end - inward):
                            ts = max(0.0, min(float(duration) - 0.02, raw))
                            rounded = round(ts, 3)
                            boundary_timestamps.add(rounded)
                            timestamps.add(rounded)
                ordered_timestamps = sorted(t for t in timestamps if 0 <= t < duration)
                # Prevent pathological artifacts with thousands of micro-scenes.
                if len(ordered_timestamps) > 120:
                    step = max(1, len(ordered_timestamps) // 120)
                    ordered_timestamps = ordered_timestamps[::step][:120]

                frame_paths: list[str] = []
                frame_records: list[tuple[str, float]] = []
                boundary_paths: list[dict[str, Any]] = []
                for i, ts in enumerate(ordered_timestamps):
                    frame_path = frame_dir / f"review_{i:03d}_{ts:.3f}s.png"
                    cmd = [
                        "ffmpeg", "-y", "-ss", str(ts),
                        "-i", str(output_path),
                        "-frames:v", "1", "-q:v", "2",
                        str(frame_path),
                    ]
                    subprocess.run(cmd, capture_output=True, timeout=60)
                    if frame_path.exists():
                        frame_paths.append(str(frame_path))
                        frame_records.append((str(frame_path), ts))
                        if ts in boundary_timestamps:
                            boundary_paths.append({"timestamp_seconds": ts, "path": str(frame_path)})
                        with Image.open(frame_path) as image:
                            rgb = np.asarray(image.convert("RGB").resize((64, 36)), dtype=np.float32)
                            luminance = rgb.mean(axis=2) / 255.0
                            if float(luminance.mean()) < 0.01 and float(luminance.std()) < 0.01:
                                visual_spotcheck["black_frames_detected"] = True

                visual_spotcheck["frames_sampled"] = len(frame_paths)
                visual_spotcheck["frame_paths"] = frame_paths
                visual_spotcheck["scene_boundary_frames"] = boundary_paths

                # Contact sheet with timestamps for a human or vision-model pass.
                if frame_paths:
                    thumb_w, thumb_h = 320, 180
                    columns = 4
                    rows = (len(frame_paths) + columns - 1) // columns
                    sheet = Image.new("RGB", (columns * thumb_w, rows * (thumb_h + 24)), "black")
                    draw = ImageDraw.Draw(sheet)
                    for i, (path, ts) in enumerate(frame_records):
                        with Image.open(path) as image:
                            image = image.convert("RGB")
                            image.thumbnail((thumb_w, thumb_h))
                            x = (i % columns) * thumb_w
                            y = (i // columns) * (thumb_h + 24)
                            sheet.paste(image, (x, y))
                            draw.text((x + 5, y + thumb_h + 4), f"{ts:.2f}s", fill="white")
                    contact_sheet = frame_dir / "contact_sheet.jpg"
                    sheet.save(contact_sheet, quality=88)
                    visual_spotcheck["contact_sheet_path"] = str(contact_sheet)

                # Extract a contiguous low-res 2-FPS sequence for motion analysis.
                motion_dir = frame_dir / "motion"
                motion_dir.mkdir(parents=True, exist_ok=True)
                for old in motion_dir.glob("motion_*.png"):
                    old.unlink()
                motion_cmd = [
                    "ffmpeg", "-y", "-i", str(output_path),
                    "-vf", "fps=2,scale=320:-2:flags=area",
                    str(motion_dir / "motion_%06d.png"),
                ]
                subprocess.run(motion_cmd, capture_output=True, timeout=max(60, int(duration * 3)))
                motion_paths = sorted(motion_dir.glob("motion_*.png"))
                # Bound analysis memory while preserving the documented 2-FPS
                # extraction. For very long videos, analyze an even sample.
                if len(motion_paths) > 1800:
                    stride = max(1, len(motion_paths) // 1800)
                    motion_paths = motion_paths[::stride][:1800]

                grayscale_frames: list[np.ndarray] = []
                hashes: list[np.ndarray] = []
                for path in motion_paths:
                    with Image.open(path) as image:
                        gray = np.asarray(image.convert("L").resize((64, 36)), dtype=np.float32) / 255.0
                        grayscale_frames.append(gray)
                        hash_gray = np.asarray(image.convert("L").resize((8, 8)), dtype=np.float32)
                        hashes.append(hash_gray > hash_gray.mean())

                visual_spotcheck["motion_frames_analyzed"] = len(grayscale_frames)
                if len(grayscale_frames) >= 2:
                    differences = [
                        float(np.mean(np.abs(grayscale_frames[i] - grayscale_frames[i - 1])))
                        for i in range(1, len(grayscale_frames))
                    ]
                    # Mean luminance difference is intentionally measured on a
                    # 64×36 downsample. At this resolution, H.264 jitter in static
                    # dark UI frames remains below 0.001 while controlled editorial
                    # camera pushes cross it reliably.
                    moving = _rendered_motion_mask(differences)
                    eligible_indices = [
                        i for i in range(len(moving))
                        if not any(
                            window["start"] <= ((i + 0.5) / 2.0) <= window["end"]
                            for window in approved_hold_windows
                        )
                    ]
                    rendered_motion_ratio = (
                        sum(1 for i in eligible_indices if moving[i]) / len(eligible_indices)
                        if eligible_indices
                        else 1.0
                    )
                    visual_spotcheck["motion_coverage_ratio"] = round(rendered_motion_ratio, 3)
                    visual_spotcheck["mean_frame_difference"] = round(float(np.mean(differences)), 5)

                    # Freeze runs are consecutive sub-threshold differences. Five
                    # differences at 2 FPS correspond to 2.5 seconds.
                    freeze_segments: list[dict[str, Any]] = []
                    run_start: int | None = None
                    for i, is_moving in enumerate(moving):
                        if not is_moving and run_start is None:
                            run_start = i
                        if (is_moving or i == len(moving) - 1) and run_start is not None:
                            run_end = i if is_moving else i + 1
                            freeze_duration = (run_end - run_start) / 2.0
                            if freeze_duration >= 2.5:
                                freeze_start = round(run_start / 2.0, 2)
                                freeze_end = round(run_end / 2.0, 2)
                                approved_window = next(
                                    (
                                        window for window in approved_hold_windows
                                        if freeze_start >= window["start"] - 0.25
                                        and freeze_end <= window["end"] + 0.25
                                    ),
                                    None,
                                )
                                freeze_segments.append({
                                    "start_seconds": freeze_start,
                                    "end_seconds": freeze_end,
                                    "duration_seconds": round(freeze_duration, 2),
                                    "approved": bool(approved_window),
                                    "approved_hold_reason": (
                                        approved_window["reason"] if approved_window else None
                                    ),
                                })
                            run_start = None
                    visual_spotcheck["freeze_segments"] = freeze_segments

                    # Perceptual hashes reveal repeated templates between
                    # different scenes. Frames within one scene are expected to
                    # retain the same layout while the camera or focus state moves;
                    # comparing them produced false positives for premium product
                    # films with deliberate visual continuity.
                    cut_windows: list[tuple[float, float, str]] = []
                    if edit_decisions:
                        for cut in edit_decisions.get("cuts", []) or []:
                            cut_windows.append((
                                float(cut.get("in_seconds", 0) or 0),
                                float(cut.get("out_seconds", 0) or 0),
                                str(cut.get("id") or ""),
                            ))

                    repeated_pairs: list[dict[str, Any]] = []
                    for i in range(len(hashes)):
                        first_seconds = i / 2.0
                        first_cut_id = _timeline_scene_id(cut_windows, first_seconds)
                        for j in range(i + 6, len(hashes)):
                            second_seconds = j / 2.0
                            second_cut_id = _timeline_scene_id(cut_windows, second_seconds)
                            if (
                                cut_windows
                                and first_cut_id is not None
                                and first_cut_id == second_cut_id
                            ):
                                continue
                            distance = int(np.count_nonzero(hashes[i] != hashes[j]))
                            if distance <= 2:
                                repeated_pairs.append({
                                    "first_seconds": round(first_seconds, 2),
                                    "second_seconds": round(second_seconds, 2),
                                    "first_scene_id": first_cut_id,
                                    "second_scene_id": second_cut_id,
                                    "hamming_distance": distance,
                                })
                                if len(repeated_pairs) >= 25:
                                    break
                        if len(repeated_pairs) >= 25:
                            break
                    visual_spotcheck["repeated_layout_pairs"] = repeated_pairs

                if len(frame_paths) < 4:
                    visual_spotcheck["issues"].append(
                        f"Only {len(frame_paths)} representative frames extracted"
                    )
                if visual_spotcheck["black_frames_detected"]:
                    visual_spotcheck["issues"].append(
                        "Black frame detected — possible missing asset or failed render segment"
                    )
                for freeze in visual_spotcheck["freeze_segments"]:
                    if freeze.get("approved"):
                        continue
                    visual_spotcheck["issues"].append(
                        "Freeze/non-semantic hold from "
                        f"{freeze['start_seconds']:.2f}s to {freeze['end_seconds']:.2f}s "
                        f"({freeze['duration_seconds']:.2f}s)"
                    )
                if (
                    visual_spotcheck["motion_frames_analyzed"] < 2
                    and required_rendered_motion_ratio > 0
                ):
                    visual_spotcheck["issues"].append(
                        "Render-based motion analysis produced fewer than two frames"
                    )
                elif (
                    visual_spotcheck["motion_coverage_ratio"]
                    < required_rendered_motion_ratio
                ):
                    visual_spotcheck["issues"].append(
                        "Rendered motion coverage "
                        f"{visual_spotcheck['motion_coverage_ratio']:.0%} is below the "
                        f"required {required_rendered_motion_ratio:.0%} for "
                        f"quality_tier={quality_tier}, quality_floor={quality_floor}"
                    )
                if len(visual_spotcheck["repeated_layout_pairs"]) >= 8:
                    visual_spotcheck["issues"].append(
                        "Repeated-layout detector found at least 8 near-identical "
                        "non-adjacent frame pairs; inspect the contact sheet for template repetition"
                    )
            except Exception as e:
                visual_spotcheck["issues"].append(f"Render-based visual QA error: {e}")

        issues.extend(visual_spotcheck.get("issues", []))

        # --- 3. Audio spotcheck ---
        audio_spotcheck: dict[str, Any] = {
            "narration_present": False,
            "music_present": False,
            "unexpected_silence": False,
            "clipping_detected": False,
            "mix_intelligible": True,
            "integrated_loudness_lufs": None,
            "true_peak_db": None,
            "loudness_range_lu": None,
            "ducking_expected": False,
            "ducking_configured": False,
            "issues": [],
        }
        if edit_decisions:
            audio_contract = edit_decisions.get("audio") or {}
            narration_contract = audio_contract.get("narration") or {}
            music_contract = audio_contract.get("music") or {}
            audio_spotcheck["ducking_expected"] = bool(narration_contract and music_contract)
            ducking = music_contract.get("ducking") if isinstance(music_contract, dict) else None
            audio_spotcheck["ducking_configured"] = bool(
                ducking is True or (isinstance(ducking, dict) and ducking.get("enabled", True))
            )
            if audio_spotcheck["ducking_expected"] and not audio_spotcheck["ducking_configured"]:
                audio_spotcheck["issues"].append(
                    "Narration and music are both present but audio.music.ducking is not enabled"
                )
        if technical_probe.get("has_audio") and duration > 0:
            try:
                # Use ffmpeg volumedetect to check audio levels
                cmd = [
                    "ffmpeg", "-i", str(output_path),
                    "-af", "volumedetect", "-f", "null", "-",
                ]
                proc = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=60
                )
                stderr = proc.stderr or ""
                # Parse mean_volume and max_volume
                mean_vol = None
                max_vol = None
                for line in stderr.split("\n"):
                    if "mean_volume:" in line:
                        try:
                            mean_vol = float(line.split("mean_volume:")[1].strip().split()[0])
                        except (ValueError, IndexError):
                            pass
                    if "max_volume:" in line:
                        try:
                            max_vol = float(line.split("max_volume:")[1].strip().split()[0])
                        except (ValueError, IndexError):
                            pass

                if mean_vol is not None:
                    if mean_vol < -60:
                        audio_spotcheck["unexpected_silence"] = True
                        audio_spotcheck["issues"].append(
                            f"Mean volume {mean_vol:.1f} dB — effectively silent"
                        )
                    # Assume narration present if mean volume is reasonable
                    if mean_vol > -40:
                        audio_spotcheck["narration_present"] = True
                    # Assume music present if audio exists (conservative)
                    if mean_vol > -50:
                        audio_spotcheck["music_present"] = True

                if max_vol is not None and max_vol > -0.5:
                    audio_spotcheck["clipping_detected"] = True
                    audio_spotcheck["issues"].append(
                        f"Max volume {max_vol:.1f} dB — possible clipping"
                    )

                # EBU R128-style loudness/true-peak measurement from loudnorm's
                # first pass. This validates the delivered mix rather than only
                # checking that an audio stream exists.
                loudnorm_cmd = [
                    "ffmpeg", "-i", str(output_path),
                    "-af", "loudnorm=I=-16:TP=-1.5:LRA=11:print_format=json",
                    "-f", "null", "-",
                ]
                loudnorm_proc = subprocess.run(
                    loudnorm_cmd, capture_output=True, text=True, timeout=120
                )
                loudnorm_text = loudnorm_proc.stderr or ""
                json_start = loudnorm_text.rfind("{")
                json_end = loudnorm_text.rfind("}")
                if json_start >= 0 and json_end > json_start:
                    metrics = json.loads(loudnorm_text[json_start:json_end + 1])
                    integrated = float(metrics.get("input_i"))
                    true_peak = float(metrics.get("input_tp"))
                    loudness_range = float(metrics.get("input_lra"))
                    audio_spotcheck["integrated_loudness_lufs"] = round(integrated, 2)
                    audio_spotcheck["true_peak_db"] = round(true_peak, 2)
                    audio_spotcheck["loudness_range_lu"] = round(loudness_range, 2)
                    if true_peak > -1.0:
                        audio_spotcheck["clipping_detected"] = True
                        audio_spotcheck["issues"].append(
                            f"True peak {true_peak:.1f} dBTP exceeds the -1.0 dBTP delivery ceiling"
                        )
                    if integrated < -24 or integrated > -10:
                        audio_spotcheck["issues"].append(
                            f"Integrated loudness {integrated:.1f} LUFS is outside the broad -24 to -10 LUFS delivery range"
                        )
            except Exception as e:
                audio_spotcheck["issues"].append(f"Audio analysis error: {e}")

        issues.extend(audio_spotcheck.get("issues", []))

        # --- 4. Promise preservation ---
        review_video_category = str(
            production_plan.get("video_category")
            or (edit_decisions or {}).get("video_category")
            or ""
        ).strip()
        promise_preservation: dict[str, Any] = {
            "delivery_promise_honored": True,
            "silent_downgrade_detected": False,
            "runtime_swap_detected": False,
            "video_category_used": review_video_category or None,
            "category_contract_honored": True,
            "issues": [],
        }
        if review_video_category and review_video_category != "overview-video":
            promise_preservation["category_contract_honored"] = False
            promise_preservation["issues"].append(
                f"Unsupported active video_category {review_video_category!r}"
            )
        if edit_decisions:
            renderer_family = edit_decisions.get("renderer_family", "")
            promise_preservation["renderer_family_used"] = renderer_family

            # Runtime governance — record what actually ran and flag a swap.
            # Three sources of truth, in priority order:
            #   1. proposal_packet.production_plan.render_runtime (authoritative)
            #   2. edit_decisions.metadata.proposal_render_runtime (if edit stage
            #      explicitly copied it to opt into in-tool swap detection)
            #   3. edit_decisions.render_runtime itself (cannot detect a swap in
            #      this case — reviewer does cross-artifact comparison instead)
            render_runtime_edit = (edit_decisions.get("render_runtime") or "").strip().lower()
            if render_runtime_edit:
                promise_preservation["render_runtime_used"] = render_runtime_edit

                proposal_runtime: str | None = None
                runtime_source: str | None = None
                if proposal_packet:
                    pp_runtime = (
                        (proposal_packet.get("production_plan") or {}).get("render_runtime")
                        or ""
                    ).strip().lower()
                    if pp_runtime:
                        proposal_runtime = pp_runtime
                        runtime_source = "proposal_packet.production_plan.render_runtime"
                if proposal_runtime is None:
                    md_runtime = (
                        (edit_decisions.get("metadata") or {}).get("proposal_render_runtime")
                        or ""
                    ).strip().lower()
                    if md_runtime:
                        proposal_runtime = md_runtime
                        runtime_source = "edit_decisions.metadata.proposal_render_runtime"

                if proposal_runtime is None:
                    promise_preservation["runtime_swap_check"] = (
                        "skipped — no proposal_packet or proposal_render_runtime "
                        "metadata provided. Reviewer skill does cross-artifact "
                        "comparison separately."
                    )
                elif proposal_runtime != render_runtime_edit:
                    promise_preservation["runtime_swap_detected"] = True
                    promise_preservation["runtime_swap_check"] = (
                        f"detected — source: {runtime_source}"
                    )
                    promise_preservation["issues"].append(
                        f"render_runtime changed between proposal ({proposal_runtime}) "
                        f"and compose ({render_runtime_edit}) — this is a contract "
                        f"violation unless a render_runtime_selection decision was logged."
                    )
                else:
                    promise_preservation["runtime_swap_check"] = (
                        f"ok — proposal and edit agree ({runtime_source})"
                    )

            delivery_data = (
                edit_decisions.get("metadata", {}).get("delivery_promise")
                or edit_decisions.get("delivery_promise")
            )
            if delivery_data:
                try:
                    from lib.delivery_promise import DeliveryPromise
                    promise = DeliveryPromise.from_dict(delivery_data)
                    cuts = edit_decisions.get("cuts", [])
                    result = promise.validate_cuts(cuts)
                    motion_ratio = result.get("motion_ratio", 0)
                    promise_preservation["motion_ratio_actual"] = round(motion_ratio, 3)

                    if not result["valid"]:
                        promise_preservation["delivery_promise_honored"] = False
                        for v in result["violations"]:
                            promise_preservation["issues"].append(v)

                    # Detect silent downgrade: motion-led promise but <50% motion
                    if (delivery_data.get("promise_type") == "motion_led"
                            and motion_ratio < 0.5):
                        promise_preservation["silent_downgrade_detected"] = True
                        promise_preservation["issues"].append(
                            f"Motion-led promise but only {motion_ratio:.0%} motion — "
                            f"silent downgrade to still-led"
                        )
                except Exception as e:
                    promise_preservation["issues"].append(
                        f"Could not validate delivery promise: {e}"
                    )

        issues.extend(promise_preservation.get("issues", []))

        # --- 5. Subtitle check ---
        subtitle_check: dict[str, Any] = {
            "subtitles_expected": False,
            "subtitles_present": False,
            "layout_policy_declared": False,
            "protected_regions_checked": False,
            "occlusion_free": False,
            "collision_count": 0,
            "unicode_text_ok": True,
            "visual_treatment_declared": False,
            "caption_background_continuity": False,
            "full_width_caption_bar_detected": False,
            "issues": [],
        }
        if edit_decisions:
            ed_subs = edit_decisions.get("subtitles", {})
            subtitle_check["subtitles_expected"] = bool(ed_subs.get("enabled"))
            subtitle_check["visual_treatment_declared"] = ed_subs.get("visual_treatment") in {
                "integrated-field", "local-pill", "surface"
            }
            declared_full_width = ed_subs.get("full_width_background") is True
            subtitle_check["full_width_caption_bar_detected"] = declared_full_width
            subtitle_check["caption_background_continuity"] = bool(
                ed_subs.get("visual_treatment") == "integrated-field"
                and not declared_full_width
            )
            subtitle_check["layout_policy_declared"] = ed_subs.get("layout_policy") in {
                "reserved-rail", "adaptive-regions"
            }
            protected_regions = ed_subs.get("protected_regions") or []
            subtitle_check["protected_regions_checked"] = bool(protected_regions)
            subtitle_check["occlusion_free"] = bool(
                subtitle_check["layout_policy_declared"]
                and subtitle_check["protected_regions_checked"]
            )
            if subtitle_check["subtitles_expected"] and not subtitle_check["layout_policy_declared"]:
                subtitle_check["issues"].append(
                    "Subtitle layout policy is missing; visual occlusion was not governed"
                )
            if subtitle_check["subtitles_expected"] and not subtitle_check["protected_regions_checked"]:
                subtitle_check["issues"].append(
                    "Subtitle protected regions are missing; zero-overlap cannot be proven"
                )

            if subtitle_check["subtitles_expected"] and not subtitle_check["visual_treatment_declared"]:
                subtitle_check["issues"].append(
                    "Subtitle visual treatment is missing; geometry and appearance were not separated"
                )

            # Render-based full-width bar detection for integrated caption fields.
            # Compare narrow strips at the reserved-field boundary across representative
            # frames; a repeated abrupt dark full-width edge is evidence of a rail.
            if (
                review_video_category == "overview-video"
                and ed_subs.get("layout_policy") == "reserved-rail"
                and visual_spotcheck.get("frame_paths")
            ):
                try:
                    from PIL import Image
                    import numpy as np

                    rail_ratio = float(ed_subs.get("reserved_rail_height_ratio") or 0)
                    if not rail_ratio and ed_subs.get("reserved_rail_height_px"):
                        rail_ratio = float(ed_subs["reserved_rail_height_px"]) / max(
                            1.0, float(technical_probe.get("resolution", "0x1080").split("x")[-1])
                        )
                    detections = 0
                    inspected = 0
                    if 0.10 <= rail_ratio <= 0.30:
                        for frame_path in visual_spotcheck["frame_paths"]:
                            with Image.open(frame_path) as frame_image:
                                rgb = np.asarray(
                                    frame_image.convert("RGB").resize((320, 180)), dtype=np.float32
                                )
                            y = int(rgb.shape[0] * (1.0 - rail_ratio))
                            if y < 10 or y >= rgb.shape[0] - 10:
                                continue
                            upper = rgb[y - 6:y].mean(axis=(0, 1))
                            lower = rgb[y:y + 6].mean(axis=(0, 1))
                            rail = rgb[y:].mean(axis=2)
                            visual = rgb[:y].mean(axis=2)
                            edge_delta = float(np.mean(np.abs(upper - lower)))
                            rail_mean = float(rail.mean())
                            visual_mean = float(visual.mean())
                            inspected += 1
                            if edge_delta > 22.0 and rail_mean + 12.0 < visual_mean:
                                detections += 1
                    detected = bool(inspected and detections >= max(2, int(inspected * 0.4)))
                    subtitle_check["full_width_caption_bar_detected"] = detected or declared_full_width
                    subtitle_check["caption_background_continuity"] = bool(
                        subtitle_check["visual_treatment_declared"]
                        and ed_subs.get("visual_treatment") == "integrated-field"
                        and not subtitle_check["full_width_caption_bar_detected"]
                    )
                except Exception as exc:
                    subtitle_check["caption_background_continuity"] = False
                    subtitle_check["issues"].append(
                        f"Caption background continuity analysis failed: {exc}"
                    )

            if review_video_category == "overview-video":
                if ed_subs.get("visual_treatment") != "integrated-field":
                    subtitle_check["issues"].append(
                        "Overview-Video requires an integrated caption field"
                    )
                if subtitle_check["full_width_caption_bar_detected"]:
                    subtitle_check["issues"].append(
                        "Full-width caption bar detected; move meaningful graphics above "
                        "the reading field and continue the scene background through it"
                    )
                if not subtitle_check["caption_background_continuity"]:
                    subtitle_check["issues"].append(
                        "Caption reading field does not preserve continuous scene background"
                    )

            try:
                from lib.text_quality import iter_string_values, validate_display_text

                language_code = ed_subs.get("language_code")
                review_text = [script_text or ""]
                review_text.extend(iter_string_values(edit_decisions.get("captions") or []))
                text_issues = [
                    issue
                    for value in review_text
                    for issue in validate_display_text(
                        value, language_code=language_code
                    )
                ]
                subtitle_check["unicode_text_ok"] = not text_issues
                if text_issues:
                    subtitle_check["issues"].append(
                        "Viewer-facing text failed Unicode/German orthography lint: "
                        + ", ".join(
                            f"{issue.token!r}→{issue.replacement!r}"
                            for issue in text_issues[:8]
                        )
                    )
            except Exception as exc:
                subtitle_check["unicode_text_ok"] = False
                subtitle_check["issues"].append(
                    f"Viewer-facing text quality check failed: {exc}"
                )

            rendered_captions = edit_decisions.get("captions", []) or []
            if subtitle_check["subtitles_expected"] and rendered_captions:
                # Remotion's CaptionOverlay burns the supplied caption words into
                # the video, so no subtitle stream or external source file exists.
                subtitle_check["subtitles_present"] = True
                subtitle_check["coverage_ratio"] = 1.0
                subtitle_check["render_mode"] = "burned_in_caption_overlay"

            # Check if output has subtitle stream
            if technical_probe.get("valid_container"):
                try:
                    cmd = [
                        "ffprobe", "-v", "quiet", "-print_format", "json",
                        "-show_streams", "-select_streams", "s",
                        str(output_path),
                    ]
                    proc = subprocess.run(
                        cmd, capture_output=True, text=True, timeout=15
                    )
                    if proc.returncode == 0:
                        sub_data = json.loads(proc.stdout)
                        sub_streams = sub_data.get("streams", [])
                        subtitle_check["subtitles_present"] = len(sub_streams) > 0

                    # If subtitles were expected but not found as a stream,
                    # they may be burned in (which is fine — not a failure)
                    if (subtitle_check["subtitles_expected"]
                            and not subtitle_check["subtitles_present"]):
                        # Check if subtitle_path was used (burned in)
                        sub_source = ed_subs.get("source")
                        if sub_source and Path(sub_source).exists():
                            # Burned-in subtitles are not detectable as streams
                            subtitle_check["subtitles_present"] = True
                            subtitle_check["coverage_ratio"] = 1.0
                        else:
                            subtitle_check["issues"].append(
                                "Subtitles expected but not found in output and "
                                "no subtitle source file exists for burn-in"
                            )
                except Exception as e:
                    subtitle_check["issues"].append(f"Subtitle check error: {e}")

        visual_spotcheck["automated_text_collision_check"] = bool(
            subtitle_check.get("occlusion_free")
        )
        issues.extend(subtitle_check.get("issues", []))

        # --- 6. Rendered-audio transcript vs source script ----------------
        # Prefer transcribing the actual rendered output. A pre-render narration
        # transcript cannot reveal truncation, wrong audio muxing, or render-time
        # punctuation leaks.
        transcript_path: Path | None = None
        transcript_source = "unavailable"
        transcript_generation_issue: str | None = None
        if script_text and technical_probe.get("has_audio"):
            try:
                from tools.analysis.transcriber import Transcriber

                transcript_dir = output_path.parent / ".final_review_transcript"
                transcribe_result = Transcriber().execute({
                    "input_path": str(output_path),
                    "model_size": "base",
                    "diarize": False,
                    "output_dir": str(transcript_dir),
                })
                if transcribe_result.success and transcribe_result.artifacts:
                    transcript_path = Path(transcribe_result.artifacts[0])
                    transcript_source = "rendered_output"
                else:
                    transcript_generation_issue = (
                        "Rendered transcript generation failed: "
                        + str(transcribe_result.error or "unknown transcriber error")
                    )
            except Exception as e:
                transcript_generation_issue = f"Rendered transcript generation failed: {e}"

        if transcript_path is None and narration_transcript_path:
            transcript_path = Path(narration_transcript_path)
            transcript_source = "caller_provided_fallback"

        transcript_comparison = self._compare_transcript_to_script(
            transcript_path,
            script_text,
        )
        transcript_comparison["transcript_source"] = transcript_source
        transcript_comparison["transcript_path"] = (
            str(transcript_path) if transcript_path else None
        )
        if transcript_generation_issue:
            transcript_comparison.setdefault("issues", []).insert(
                0, transcript_generation_issue
            )
        issues.extend(transcript_comparison.get("issues", []))

        # --- 7. Rendered semantic visual review ---------------------------
        semantic_contract = (
            production_plan.get("semantic_visual_review")
            or (edit_decisions or {}).get("semantic_visual_review")
            or (edit_decisions or {}).get("metadata", {}).get("semantic_visual_review")
            or {}
        )
        semantic_required = bool(
            isinstance(semantic_contract, dict) and semantic_contract.get("required")
        )
        configured_review_path = semantic_visual_review_path
        if not configured_review_path and isinstance(semantic_contract, dict):
            configured_review_path = semantic_contract.get("path")
        semantic_visual_review: dict[str, Any] = {
            "required": semantic_required,
            "present": False,
            "path": str(configured_review_path) if configured_review_path else None,
            "status": "unavailable",
            "gate_valid": False,
            "human_approval_required": bool(
                isinstance(semantic_contract, dict)
                and semantic_contract.get("human_approval_required", False)
            ),
            "human_approval_status": "pending",
            "issues": [],
        }
        if configured_review_path:
            try:
                from lib.visual_review_gate import validate_visual_review
                from schemas.artifacts import validate_artifact

                semantic_path = Path(str(configured_review_path)).expanduser()
                if not semantic_path.is_file():
                    raise FileNotFoundError(f"Semantic visual review not found: {semantic_path}")
                semantic_data = json.loads(semantic_path.read_text(encoding="utf-8"))
                canonical_data = {
                    key: value for key, value in semantic_data.items()
                    if key not in {"governance_gate", "automatic_loop_status"}
                }
                validate_artifact("visual_review", canonical_data)
                gate = validate_visual_review(
                    semantic_data,
                    quality_tier=str(quality_tier),
                    video_category=str(review_video_category),
                    require_human_approval=bool(
                        semantic_visual_review["human_approval_required"]
                    ),
                )
                approval = semantic_data.get("human_approval") or {}
                semantic_visual_review.update({
                    "present": True,
                    "status": semantic_data.get("status", "unavailable"),
                    "gate_valid": bool(gate.get("valid")),
                    "human_approval_status": approval.get("status", "pending"),
                    "model": (semantic_data.get("reviewer") or {}).get("model"),
                    "iteration": semantic_data.get("iteration"),
                    "critical_count": gate.get("critical_count", 0),
                    "high_count": gate.get("high_count", 0),
                    "issues": list(gate.get("violations", [])),
                    "warnings": list(gate.get("warnings", [])),
                })
            except Exception as exc:
                semantic_visual_review["issues"].append(
                    f"Semantic visual review validation failed: {exc}"
                )
        elif semantic_required:
            semantic_visual_review["issues"].append(
                "Rendered semantic visual review is required but no visual_review artifact was provided"
            )

        issues.extend(semantic_visual_review.get("issues", []))

        # --- 8. Determine overall status ---
        # `revise` is a blocking state in every render path. Build it from
        # structured checks first, then from unmistakably critical messages.
        critical_issues: list[str] = []

        if not promise_preservation.get("delivery_promise_honored", True):
            critical_issues.extend(promise_preservation.get("issues", []))
        if promise_preservation.get("silent_downgrade_detected"):
            critical_issues.extend(promise_preservation.get("issues", []))
        if promise_preservation.get("runtime_swap_detected"):
            critical_issues.extend(promise_preservation.get("issues", []))
        if not promise_preservation.get("category_contract_honored", True):
            critical_issues.extend(promise_preservation.get("issues", []))
        if semantic_required and not semantic_visual_review.get("gate_valid"):
            critical_issues.extend(semantic_visual_review.get("issues", []))
        if visual_spotcheck.get("black_frames_detected"):
            critical_issues.extend(visual_spotcheck.get("issues", []))
        if visual_spotcheck.get("freeze_segments"):
            critical_issues.extend(
                i for i in visual_spotcheck.get("issues", [])
                if "freeze/non-semantic hold" in i.lower()
            )
        if len(visual_spotcheck.get("repeated_layout_pairs", [])) >= 8:
            critical_issues.extend(
                i for i in visual_spotcheck.get("issues", [])
                if "repeated-layout" in i.lower()
            )
        if audio_spotcheck.get("ducking_expected") and not audio_spotcheck.get("ducking_configured"):
            critical_issues.extend(
                i for i in audio_spotcheck.get("issues", [])
                if "ducking" in i.lower()
            )
        if audio_spotcheck.get("clipping_detected"):
            critical_issues.extend(
                i for i in audio_spotcheck.get("issues", [])
                if "peak" in i.lower() or "clipping" in i.lower()
            )
        audio_contract = (edit_decisions or {}).get("audio") or {}
        audio_expected = bool(
            audio_contract.get("narration")
            or audio_contract.get("music")
            or audio_contract.get("sfx")
        )
        if (
            technical_probe.get("valid_container")
            and not technical_probe.get("has_audio")
            and audio_expected
        ):
            critical_issues.append("No audio stream in final output")
        render_transcript_required = bool(
            script_text
            and audio_expected
            and (quality_tier == "hero" or quality_floor == "broadcast")
        )
        if (
            render_transcript_required
            and transcript_comparison.get("transcript_source") != "rendered_output"
        ):
            critical_issues.append(
                "Hero/broadcast final review requires a transcript generated from "
                "the rendered output, but rendered-output transcription was unavailable"
            )
            critical_issues.extend(
                i for i in transcript_comparison.get("issues", [])
                if "rendered transcript generation failed" in i.lower()
            )
        if subtitle_check.get("subtitles_expected") and not subtitle_check.get("subtitles_present"):
            critical_issues.extend(subtitle_check.get("issues", []))
        if subtitle_check.get("subtitles_expected") and not subtitle_check.get("occlusion_free"):
            critical_issues.extend(subtitle_check.get("issues", []))
        if not subtitle_check.get("unicode_text_ok", True):
            critical_issues.extend(subtitle_check.get("issues", []))
        if review_video_category == "overview-video" and (
            subtitle_check.get("full_width_caption_bar_detected")
            or not subtitle_check.get("caption_background_continuity")
            or not subtitle_check.get("visual_treatment_declared")
        ):
            critical_issues.extend(subtitle_check.get("issues", []))
        if transcript_comparison.get("spurious_punctuation_words"):
            critical_issues.extend(transcript_comparison.get("issues", []))

        for issue in issues:
            if any(kw in issue.lower() for kw in [
                "effectively silent",
                "ffprobe failed",
                "suspiciously short",
                "tts punctuation leak",
                "duration drift",
                "render-based visual qa error",
                "motion analysis produced fewer than two frames",
                "rendered motion coverage",
                "audio analysis error",
            ]):
                critical_issues.append(issue)

        # De-duplicate while preserving order for readable failure reports.
        critical_issues = list(dict.fromkeys(critical_issues))

        if not technical_probe.get("valid_container"):
            status = "fail"
            recommended_action = "re_render"
        elif critical_issues:
            status = "revise"
            recommended_action = "re_render"
        else:
            status = "pass"
            recommended_action = "present_to_user"

        final_review = {
            "version": "1.0",
            "output_path": str(output_path),
            "status": status,
            "checks": {
                "technical_probe": technical_probe,
                "visual_spotcheck": visual_spotcheck,
                "audio_spotcheck": audio_spotcheck,
                "promise_preservation": promise_preservation,
                "subtitle_check": subtitle_check,
                "transcript_comparison": transcript_comparison,
                "semantic_visual_review": semantic_visual_review,
            },
            "issues_found": issues,
            "recommended_action": recommended_action,
        }

        log.info(
            "Final review: status=%s, issues=%d, action=%s",
            status, len(issues), recommended_action,
        )

        return final_review

    @staticmethod
    def _parse_probe_fps(fps_str: str) -> float:
        """Parse ffprobe fps string like '30/1' or '24000/1001'."""
        try:
            if "/" in fps_str:
                num, den = fps_str.split("/")
                return round(int(num) / max(int(den), 1), 2)
            return float(fps_str)
        except (ValueError, ZeroDivisionError):
            return 0.0

    def _burn_subtitles(self, inputs: dict[str, Any]) -> ToolResult:
        """Burn subtitle file into video."""
        input_path = Path(inputs["input_path"])
        subtitle_path = Path(inputs["subtitle_path"])
        output_path = Path(inputs.get("output_path", str(input_path.with_stem(f"{input_path.stem}_subtitled"))))

        if not input_path.exists():
            return ToolResult(success=False, error=f"Input not found: {input_path}")
        if not subtitle_path.exists():
            return ToolResult(success=False, error=f"Subtitle file not found: {subtitle_path}")

        style = inputs.get("subtitle_style", {})
        ass_style = self._build_subtitle_style(style)
        sub_escaped = str(subtitle_path.resolve()).replace("\\", "/").replace(":", "\\:")
        codec = inputs.get("codec", "libx264")
        crf = inputs.get("crf", 23)

        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-vf", f"subtitles='{sub_escaped}':force_style='{ass_style}'",
            "-c:v", codec, "-crf", str(crf),
            "-c:a", "copy",
            str(output_path),
        ]

        self.run_command(cmd)

        return ToolResult(
            success=True,
            data={
                "operation": "burn_subtitles",
                "output": str(output_path),
            },
            artifacts=[str(output_path)],
        )

    def _overlay(self, inputs: dict[str, Any]) -> ToolResult:
        """Composite overlay images/videos on top of base video."""
        input_path = Path(inputs["input_path"])
        overlays = inputs.get("overlays", [])
        output_path = Path(inputs.get("output_path", str(input_path.with_stem(f"{input_path.stem}_overlay"))))
        codec = inputs.get("codec", "libx264")
        crf = inputs.get("crf", 23)

        if not input_path.exists():
            return ToolResult(success=False, error=f"Input not found: {input_path}")
        if not overlays:
            return ToolResult(success=False, error="No overlays provided")

        # Build complex filter for each overlay
        input_args = ["-i", str(input_path)]
        filter_parts = []
        prev_label = "0:v"

        for i, ov in enumerate(overlays):
            asset_path = Path(ov["asset_path"])
            if not asset_path.exists():
                return ToolResult(success=False, error=f"Overlay asset not found: {asset_path}")

            input_args.extend(["-i", str(asset_path)])

            x = int(ov.get("x", 0))
            y = int(ov.get("y", 0))
            start = ov.get("start_seconds", 0)
            end = ov.get("end_seconds")
            opacity = ov.get("opacity", 1.0)

            overlay_input = f"{i + 1}:v"

            # Scale overlay if dimensions specified
            if "width" in ov and "height" in ov:
                w = int(ov["width"])
                h = int(ov["height"])
                filter_parts.append(f"[{overlay_input}]scale={w}:{h}[ov_scaled_{i}]")
                overlay_input = f"ov_scaled_{i}"

            # Build enable expression for timed overlays
            enable = f"between(t,{start},{end})" if end else f"gte(t,{start})"
            out_label = f"v{i}"

            filter_parts.append(
                f"[{prev_label}][{overlay_input}]overlay={x}:{y}:enable='{enable}'[{out_label}]"
            )
            prev_label = out_label

        filter_complex = ";".join(filter_parts)

        cmd = ["ffmpeg", "-y"]
        cmd.extend(input_args)
        cmd.extend(["-filter_complex", filter_complex])
        cmd.extend(["-map", f"[{prev_label}]", "-map", "0:a?"])
        cmd.extend(["-c:v", codec, "-crf", str(crf), "-c:a", "copy"])
        cmd.append(str(output_path))

        self.run_command(cmd)

        return ToolResult(
            success=True,
            data={
                "operation": "overlay",
                "overlay_count": len(overlays),
                "output": str(output_path),
            },
            artifacts=[str(output_path)],
        )

    def _encode(self, inputs: dict[str, Any]) -> ToolResult:
        """Re-encode video with a specific profile/codec settings."""
        input_path = Path(inputs["input_path"])
        output_path = Path(inputs.get("output_path", str(input_path.with_stem(f"{input_path.stem}_encoded"))))
        codec = inputs.get("codec", "libx264")
        crf = inputs.get("crf", 23)
        preset = inputs.get("preset", "medium")
        profile_name = inputs.get("profile")

        if not input_path.exists():
            return ToolResult(success=False, error=f"Input not found: {input_path}")

        cmd = [
            "ffmpeg", "-y",
            "-i", str(input_path),
            "-c:v", codec, "-crf", str(crf), "-preset", preset,
            "-c:a", "aac", "-b:a", "192k",
        ]

        # Apply media profile if specified
        if profile_name:
            try:
                from lib.media_profiles import get_profile, ffmpeg_output_args
                profile = get_profile(profile_name)
                cmd.extend(["-s", f"{profile.width}x{profile.height}"])
                cmd.extend(["-r", str(profile.fps)])
            except (ImportError, ValueError):
                pass  # proceed without profile

        cmd.append(str(output_path))
        self.run_command(cmd)

        return ToolResult(
            success=True,
            data={
                "operation": "encode",
                "codec": codec,
                "crf": crf,
                "profile": profile_name,
                "output": str(output_path),
            },
            artifacts=[str(output_path)],
        )

    @staticmethod
    def _resolve_subtitle_style(
        explicit_style: dict | None,
        edit_decisions: dict | None,
        playbook: dict | None,
    ) -> dict:
        """Resolve subtitle style with layered priority.

        Priority: explicit_style > edit_decisions.subtitles.style > playbook > defaults.
        This prevents every video from looking identical (Arial bold white).
        """
        # Start with minimal fallback defaults
        resolved = {
            "font": "Inter",
            "font_size": 28,
            "bold": True,
            "outline_width": 2,
            "shadow": 0,
            "margin_v": 40,
            "alignment": 2,
        }

        # Layer 1: Playbook-derived style
        if playbook:
            typo = playbook.get("typography", {})
            colors = playbook.get("visual_language", {}).get("color_palette", {})
            if typo.get("body", {}).get("family"):
                resolved["font"] = typo["body"]["family"]
            if colors.get("text"):
                resolved["primary_color"] = colors["text"]
            if colors.get("background"):
                resolved["outline_color"] = colors["background"]
                # Semi-transparent background for readability
                bg = colors["background"]
                resolved["back_color"] = bg

        # Layer 2: edit_decisions subtitle style
        if edit_decisions:
            ed_style = edit_decisions.get("subtitles", {}).get("style", {})
            if isinstance(ed_style, dict):
                for k, v in ed_style.items():
                    if v is not None:
                        resolved[k] = v

        # Layer 3: Explicit override (highest priority)
        if explicit_style:
            for k, v in explicit_style.items():
                if v is not None:
                    resolved[k] = v

        return resolved

    @staticmethod
    def _build_subtitle_style(style: dict) -> str:
        """Build ASS force_style string from style dict."""
        parts = []
        parts.append(f"FontName={style.get('font', 'Inter')}")
        parts.append(f"FontSize={style.get('font_size', 28)}")
        parts.append(f"Bold={1 if style.get('bold', True) else 0}")
        if style.get("primary_color"):
            parts.append(f"PrimaryColour={style['primary_color']}")
        if style.get("outline_color"):
            parts.append(f"OutlineColour={style['outline_color']}")
        if style.get("back_color"):
            parts.append(f"BackColour={style['back_color']}")
        border_style = style.get("border_style", 1)
        parts.append(f"BorderStyle={border_style}")
        parts.append(f"Outline={style.get('outline_width', 2)}")
        parts.append(f"Shadow={style.get('shadow', 0)}")
        parts.append(f"MarginV={style.get('margin_v', 40)}")
        parts.append(f"Alignment={style.get('alignment', 2)}")
        return ",".join(parts)

    @staticmethod
    def _build_atempo(factor: float) -> str:
        """Build atempo filter chain for audio speed adjustment."""
        filters = []
        remaining = factor
        while remaining > 100.0:
            filters.append("atempo=100.0")
            remaining /= 100.0
        while remaining < 0.5:
            filters.append("atempo=0.5")
            remaining /= 0.5
        filters.append(f"atempo={remaining:.4f}")
        return ",".join(filters)
