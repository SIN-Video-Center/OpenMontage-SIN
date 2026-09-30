#!/usr/bin/env python3
"""Generate a character-consistent image using SIN-OmniRoute with ComfyUI linked references.

Usage:
    python3 scripts/generate-character-image.py         --image /tmp/teddy-golden-reference.png         --alias character_image_production         --prompt "A cute cartoon teddy bear sitting and reading a book..."
"""
import sys, json, time
from pathlib import Path
import tools.base_tool
from tools._comfyui.client import ComfyUIClient

def generate_character_image(ref_path: Path, alias: str, prompt: str,
                              size: str = "1024x1024") -> Path:
    client = ComfyUIClient()

    # 1. Upload reference to ComfyUI server (get server-side filename)
    uploaded_name = client.upload_image(ref_path, ref_path.name)
    print(f"Uploaded reference: {uploaded_name}")

    # 2. Build workflow with LoadImage priming node
    wf = {
        "1": {
            "class_type": "SINOmniRouteImage",
            "inputs": {
                "alias": alias,
                "prompt": prompt,
                "size": size,
                "references": ["2", 0],
            },
        },
        "2": {
            "class_type": "LoadImage",
            "inputs": {"image": uploaded_name},
        },
    }

    # 3. Submit and poll
    t0 = time.time()
    pid = client.submit(wf)
    print(f"Submitted workflow: {pid}")
    entry = client.poll(pid, timeout=300, interval=8)
    print(f"Completed in {time.time()-t0:.1f}s")

    # 4. Download output
    out = entry["outputs"]["1"]
    imgs = out.get("images", [])
    if not imgs:
        raise RuntimeError(f"No output images. Text output: {out.get('text', [])}")

    dest = Path("/tmp/teddy-character-shot.png")
    p = client.download(imgs[0]["filename"], imgs[0].get("subfolder", ""),
                        dest, imgs[0].get("type", "output"))
    print(f"Saved: {p} ({p.stat().st_size} bytes)")

    # 5. Print provenance
    artifacts = out.get("text", [])
    print(f"Provenance: {artifacts}")
    return p

if __name__ == "__main__":
    ref_path = Path("/tmp/teddy-golden-reference.png")
    alias = "character_image_production"
    prompt = "A cute cartoon teddy bear sitting and reading a book"
    generate_character_image(ref_path, alias, prompt)
