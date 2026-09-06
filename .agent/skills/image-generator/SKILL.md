---
name: image-generator
description: Generate 9:16 vertical keyframe images for each scene in the storyboard via ComfyUI REST API, Diffusers, or automated local rendering.
---

# Image Generator Skill

This skill reads `state/storyboard.json`, extracts each scene's `diffusion_prompt` (guaranteed to contain `--ar 9:16, dark atmospheric oil painting, volumetric lighting, high fidelity`), and generates high-resolution vertical keyframe images at `assets/frames/scene_{id}.png` (1080x1920).

## Supported Generation Backends

1. **ComfyUI API (Local / HTTP)**:
   - Queries `http://127.0.0.1:8188/prompt`.
   - Sends SDXL or SD1.5/SD3 workflow nodes with vertical dimensions (1080x1920 or 832x1472 upscaled).
   - Polls WebSocket or `/history` endpoint and saves outputs to `assets/frames/scene_{id}.png`.

2. **Diffusers (PyTorch Local Pipeline)**:
   - Uses `diffusers.AutoPipelineForText2Image` (e.g., `stabilityai/stable-diffusion-xl-base-1.0` or local checkpoint).
   - Generates 9:16 frames with EulerDiscreteScheduler or DPM++ 2M Karras.

3. **Autonomous Artistic Canvas Fallback**:
   - When external GPU daemons are offline or initializing, creates dark atmospheric oil painting aesthetic compositions with dynamic volumetric fog, vignetted chiaroscuro lighting, and scene title cues via Pillow.
   - Ensures the pipeline never crashes and outputs valid 1080x1920 PNGs for immediate compilation.

## Output Specification

- Path: `assets/frames/scene_{scene_id}.png`
- Format: PNG, RGB
- Resolution: 1080x1920 (9:16 aspect ratio)

## Usage

```bash
python .agent/skills/image-generator/scripts/generate_frames.py \
  --storyboard state/storyboard.json \
  --output-dir assets/frames \
  --backend auto \
  --width 1080 \
  --height 1920
```

## Visual QA Contact Sheet Generation

After generating keyframes, generate a composite contact sheet preview:
```bash
python .agent/skills/image-generator/scripts/create_contact_sheet.py \
  --frames-dir assets/frames \
  --storyboard state/storyboard.json \
  --output assets/frames/storyboard_grid.png \
  --cols 5
```
- Outputs `assets/frames/storyboard_grid.png` displaying all scene thumbnails stamped with scene ID, timecode, camera motion, and shot description for quick visual auditing.

