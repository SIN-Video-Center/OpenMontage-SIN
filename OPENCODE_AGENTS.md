# OpenMontage — OpenCode Agent Integration

> This file enables OpenCode (SIN-Code / MiMo Code) agents to drive OpenMontage video production pipelines.

## Quick Start

```bash
cd /path/to/OpenMontage
source .venv/bin/activate

# Check available tools
python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu_summary(), indent=2))"
```

## Agent Contract

**Every video production request goes through a pipeline. No exceptions.**

1. **Identify the pipeline** — match the request to `pipeline_defs/*.yaml`
2. **Read the pipeline manifest** — know stages, tools, quality gates
3. **Run preflight** — discover tools via registry, present capability menu
4. **Execute stage by stage** — read each stage's director skill BEFORE doing work
5. **Read Layer 3 skills** before calling any generation tool

## Available Pipelines

| Pipeline | Best For | File |
|----------|----------|------|
| animated-explainer | Topic to explainer video | `pipeline_defs/animated-explainer.yaml` |
| cinematic | Trailer, teaser | `pipeline_defs/cinematic.yaml` |
| animation | Motion graphics | `pipeline_defs/animation.yaml` |
| screen-demo | Screen recordings | `pipeline_defs/screen-demo.yaml` |
| hybrid | Source footage + support | `pipeline_defs/hybrid.yaml` |
| avatar-spokesperson | Presenter videos | `pipeline_defs/avatar-spokesperson.yaml` |

## Tool Discovery (MANDATORY before any work)

```bash
# Human-readable capability summary
python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.provider_menu_summary(), indent=2))"

# Full tool catalog
python -c "from tools.tool_registry import registry; import json; registry.discover(); print(json.dumps(registry.capability_catalog(), indent=2))"
```

## Composition Runtimes

| Runtime | Use For | Requires |
|---------|---------|----------|
| FFmpeg | Simple cuts, concat, trim | `ffmpeg` binary |
| Remotion | React-based animation, text cards, charts | Node.js + `remotion-composer/` |
| HyperFrames | HTML/CSS/GSAP motion graphics | Node.js ≥ 22 + FFmpeg |

**Runtime is locked at proposal and cannot be changed without user approval.**

## Key Commands

```bash
# Initialize a project
python -c "from lib.checkpoint import init_project; init_project('my-project', title='My Video', pipeline_type='animated-explainer')"

# Generate TTS narration (Piper — free, local)
echo "Text here" | piper --model ~/.piper/models/de_DE-thorsten-medium.onnx --output_file output.wav

# Render with FFmpeg
ffmpeg -f concat -safe 0 -i concat.txt -i narration.wav -vf "scale=1920:1080" -c:v libx264 -c:a aac output.mp4

# Check video properties
ffprobe -v quiet -show_entries format=duration,size -of json output.mp4
```

## Skill Layers

1. **Layer 1: Tools** (`tools/`) — What exists, cost, runtime, status
2. **Layer 2: Skills** (`skills/`) — How OpenMontage uses them in pipelines
3. **Layer 3: Vendor skills** (`.agents/skills/`) — How the technology works

**Always read Layer 2 before executing a pipeline stage. Always read Layer 3 before calling a generation tool.**

## Project Structure

```
projects/<project-name>/
├── artifacts/          # JSON artifacts (script, scene_plan, etc.)
├── assets/
│   ├── images/         # Screenshots, generated images
│   ├── audio/          # Narration, music
│   └── subtitles.srt
└── renders/
    └── final.mp4       # The deliverable
```

## Style Playbooks

| Playbook | Best For |
|----------|----------|
| clean-professional | Corporate, educational |
| flat-motion-graphics | Social media, TikTok |
| minimalist-diagram | Technical deep-dives |

## Budget Control

- Default budget: $2.00 per production
- Single action approval: $0.50
- Mode: `warn` (log overruns) or `cap` (hard limit)
- Configure in `config.yaml`

## Common Patterns

### Image-based video with narration (FREE)
1. Use existing screenshots/images as source
2. Generate narration with Piper TTS (local, free)
3. Compose with FFmpeg concat + audio mux
4. Total cost: $0

### AI-generated video (PAID)
1. Generate images via FLUX/Imagen/DALL-E ($0.01-0.05/image)
2. Generate narration via ElevenLabs/OpenAI TTS ($0.01-0.03/1000 chars)
3. Optional: Generate music via Suno ($0.05-0.10/song)
4. Compose with Remotion
5. Total cost: $0.50-3.00

### Documentary montage (FREE)
1. Build corpus from Archive.org, NASA, Wikimedia (free)
2. CLIP-search for relevant footage
3. Edit with FFmpeg
4. Total cost: $0

## Troubleshooting

### Piper TTS voice not found
Download the voice model:
```bash
curl -L -o ~/.piper/models/de_DE-thorsten-medium.onnx "https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx"
curl -L -o ~/.piper/models/de_DE-thorsten-medium.onnx.json "https://huggingface.co/rhasspy/piper-voices/resolve/main/de/de_DE/thorsten/medium/de_DE-thorsten-medium.onnx.json"
```

### Remotion images not found
Copy images to `remotion-composer/public/`:
```bash
cp assets/images/*.png remotion-composer/public/
```

### Video too short
Check that narration audio is being mixed. The FFmpeg concat demuxer needs the audio track separately muxed in.
