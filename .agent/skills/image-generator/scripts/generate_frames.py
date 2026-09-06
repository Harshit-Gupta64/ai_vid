#!/usr/bin/env python3
"""
generate_frames.py - High-Efficiency Keyframe Generation with Cache & Rate-Limit Fallback

Batch-generates high-fidelity 9:16 vertical keyframe images (1080x1920) for micro-scenes.
Features:
- Instant skip for existing valid frames (caching)
- Polite concurrency (2 workers) with inter-request spacing
- Exponential backoff on HTTP 429
- Automatic model fallback from Flux to Turbo when Flux rate limits
"""

import argparse
import concurrent.futures
import hashlib
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path


def download_single_frame(
    scene_id: int,
    prompt: str,
    output_path: Path,
    topic_id: str = "default_topic",
    seed_offset: int = 0,
    width: int = 1080,
    height: int = 1920,
    model: str = "flux",
    max_retries: int = 4,
    timeout: int = 45
) -> bool:
    # 1. Cache check
    if output_path.exists() and output_path.stat().st_size > 5000:
        print(f"[CACHE] Scene {scene_id:02d} already rendered ({output_path.stat().st_size/1024:.1f} KB): {output_path.name}")
        return True

    encoded_prompt = urllib.parse.quote(prompt)
    base_seed = int(hashlib.sha256(topic_id.encode("utf-8")).hexdigest()[:8], 16) % (2**31)
    seed = (base_seed + seed_offset) % (2**31)

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    current_model = model
    for attempt in range(1, max_retries + 1):
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&model={current_model}&nologo=true&seed={seed}"
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    data = response.read()
                    if len(data) > 5000:
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(output_path, "wb") as f:
                            f.write(data)
                        print(f"[SUCCESS] Scene {scene_id:02d} rendered ({len(data)/1024:.1f} KB, {current_model}): {output_path.name}")
                        return True
                    else:
                        print(f"[WARN] Scene {scene_id:02d} attempt {attempt}: Small payload ({len(data)} B), retrying...", file=sys.stderr)
                else:
                    print(f"[WARN] Scene {scene_id:02d} attempt {attempt}: HTTP {response.status}, retrying...", file=sys.stderr)
        except Exception as e:
            err_str = str(e)
            if "429" in err_str:
                backoff_delay = 10 * attempt
                print(f"[WARN] Scene {scene_id:02d} attempt {attempt}: Rate limited (429). Retrying {current_model} in {backoff_delay}s...", file=sys.stderr)
                time.sleep(backoff_delay)
            else:
                retry_delay = 2 * attempt
                print(f"[WARN] Scene {scene_id:02d} attempt {attempt} failed: {e}. Retrying in {retry_delay}s...", file=sys.stderr)
                time.sleep(retry_delay)

    # Fallback to turbo as an absolute last resort if all retries of the requested model failed
    if model != "turbo":
        print(f"[WARN] Scene {scene_id:02d}: All {max_retries} attempts with '{model}' exhausted. Attempting last-resort fallback to 'turbo'...", file=sys.stderr)
        fallback_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&model=turbo&nologo=true&seed={seed}"
        try:
            req = urllib.request.Request(fallback_url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                if response.status == 200:
                    data = response.read()
                    if len(data) > 5000:
                        output_path.parent.mkdir(parents=True, exist_ok=True)
                        with open(output_path, "wb") as f:
                            f.write(data)
                        print(f"[FALLBACK] Scene {scene_id:02d} rendered with turbo fallback ({len(data)/1024:.1f} KB): {output_path.name}")
                        with open("degraded_scenes.log", "a", encoding="utf-8") as lf:
                            lf.write(f"topic_id={topic_id} scene_id={scene_id}\n")
                        return True
        except Exception as fe:
            print(f"[ERROR] Scene {scene_id:02d}: Fallback to turbo failed: {fe}", file=sys.stderr)

    print(f"[ERROR] Scene {scene_id:02d} failed after {max_retries} attempts and fallback.", file=sys.stderr)
    return False


def generate_frames_parallel(
    storyboard_path: Path,
    output_dir: Path,
    topic_id: str = None,
    seed_offset: int = 0,
    width: int = 1080,
    height: int = 1920,
    model: str = "flux",
    max_workers: int = 2
):
    with open(storyboard_path, "r", encoding="utf-8") as f:
        sb = json.load(f)

    resolved_topic_id = topic_id or sb.get("topic_id") or "default_topic"
    scenes = sb.get("scenes", [])
    if not scenes:
        raise ValueError("Storyboard contains no scenes.")

    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"[INFO] Batch generating {len(scenes)} keyframes (Topic: {resolved_topic_id}, Base Offset: {seed_offset}, Workers: {max_workers}, Model: {model}, Resolution: {width}x{height})...")

    # Clean old frames if scene count changed
    existing_files = list(output_dir.glob("scene_*.png"))
    if len(existing_files) > len(scenes):
        for f in existing_files:
            try:
                sid = int(f.stem.replace("scene_", ""))
                if sid > len(scenes):
                    f.unlink()
            except Exception:
                pass

    tasks = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
        for scene in scenes:
            scene_id = scene.get("scene_id", 1)
            out_file = output_dir / f"scene_{scene_id}.png"
            prompt = scene.get("diffusion_prompt") or scene.get("visual_prompt") or scene.get("visual_description", "")
            scene_seed_offset = scene.get("seed_offset", seed_offset)

            # Submit with staggered start to prevent initial spike
            time.sleep(0.3)
            f = executor.submit(
                download_single_frame,
                scene_id=scene_id,
                prompt=prompt,
                output_path=out_file,
                topic_id=resolved_topic_id,
                seed_offset=scene_seed_offset,
                width=width,
                height=height,
                model=model
            )
            tasks.append((scene_id, f))

        results = {}
        for scene_id, f in tasks:
            results[scene_id] = f.result()

    successful = sum(1 for s in results.values() if s)
    print(f"[INFO] Rendering complete: {successful}/{len(scenes)} frames available.")

    if successful != len(scenes):
        missing = [sid for sid, s in results.items() if not s]
        print(f"[ERROR] Missing keyframes for scene IDs: {missing}", file=sys.stderr)
        sys.exit(1)

    print(f"[SUCCESS] All {len(scenes)} keyframes verified in {output_dir.resolve()}")


def main():
    parser = argparse.ArgumentParser(description="Vertical keyframe generation with caching and rate limit fallback.")
    parser.add_argument("--storyboard", type=str, default="state/storyboard.json", help="Path to input storyboard JSON.")
    parser.add_argument("--output-dir", type=str, default="assets/frames", help="Directory for rendered PNG frames.")
    parser.add_argument("--topic-id", type=str, default=None, help="Topic ID for consistent seed derivation (defaults to topic_id in storyboard.json).")
    parser.add_argument("--seed-offset", type=int, default=0, help="Global seed offset to nudge generated frames (default: 0).")
    parser.add_argument("--model", type=str, default="flux", help="Pollinations model (flux or turbo).")
    parser.add_argument("--width", type=int, default=1080, help="Output image width.")
    parser.add_argument("--height", type=int, default=1920, help="Output image height.")
    parser.add_argument("--workers", type=int, default=2, help="Max parallel download workers.")

    args = parser.parse_args()

    sb_path = Path(args.storyboard)
    if not sb_path.exists():
        print(f"[ERROR] Storyboard file '{sb_path}' not found.", file=sys.stderr)
        sys.exit(1)

    generate_frames_parallel(
        storyboard_path=sb_path,
        output_dir=Path(args.output_dir),
        topic_id=args.topic_id,
        seed_offset=args.seed_offset,
        width=args.width,
        height=args.height,
        model=args.model,
        max_workers=args.workers
    )


if __name__ == "__main__":
    main()
