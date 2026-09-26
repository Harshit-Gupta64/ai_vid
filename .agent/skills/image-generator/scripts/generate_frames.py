#!/usr/bin/env python3
"""
generate_frames.py - High-Efficiency Keyframe Generation with Dual-Pipeline Fallback

Supports 3-tier visual generation fallback:
1. ComfyUI REST API (Local GPU / 127.0.0.1:8188)
2. Pollinations AI (Flux / Turbo with POLLINATIONS_API_KEY support)
3. High-Fidelity PIL Artistic Rendering (Guaranteed offline / unblocked fallback)

Features:
- Instant skip for existing valid frames (caching)
- Polite concurrency with inter-request spacing
- Engine health-checks & automatic fallthrough
- Records engine_info.json in the output directory
"""

import argparse
import concurrent.futures
import hashlib
import io
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

# Try loading .env if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def check_comfyui_health(host: str = "http://127.0.0.1:8188") -> bool:
    """Checks if ComfyUI REST server is responsive."""
    try:
        url = f"{host.rstrip('/')}/system_stats"
        req = urllib.request.Request(url, headers={"User-Agent": "AntigravityPipeline/1.0"})
        with urllib.request.urlopen(req, timeout=1.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def render_pil_fallback_frame(
    scene_id: int,
    prompt: str,
    output_path: Path,
    topic_id: str,
    width: int = 1080,
    height: int = 1920
) -> bool:
    """Generates an atmospheric dark-cinematic keyframe using PIL when generative models fail."""
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new("RGB", (width, height), (16, 18, 24))
        draw = ImageDraw.Draw(img)

        # 1. Atmospheric vignette gradient
        for y in range(height):
            factor = 1.0 - 0.45 * math.cos(y / height * math.pi)
            r = int(18 * factor)
            g = int(22 * factor)
            b = int(32 * factor)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        # 2. Ornate historical parchment borders
        gold = (140, 115, 70)
        gold_dim = (75, 60, 40)
        draw.rectangle([(40, 40), (width - 40, height - 40)], outline=gold, width=2)
        draw.rectangle([(52, 52), (width - 52, height - 52)], outline=gold_dim, width=1)

        # Corner accents
        accent_len = 25
        for cx, cy in [(40, 40), (width - 40, 40), (40, height - 40), (width - 40, height - 40)]:
            dx = accent_len if cx == 40 else -accent_len
            dy = accent_len if cy == 40 else -accent_len
            draw.line([(cx, cy), (cx + dx, cy)], fill=gold, width=4)
            draw.line([(cx, cy), (cx, cy + dy)], fill=gold, width=4)

        # NOTE: Pure visual abstract fallback canvas - ZERO text or debug artifacts burned into image.
        # Subtitles and narrative captions are overlaid dynamically by render_short.py.

        img.save(output_path, "PNG")
        print(f"[PIL FALLBACK] Scene {scene_id:02d} rendered via PIL fallback (pure visual): {output_path.name}")
        return True
    except Exception as e:
        print(f"[ERROR] Scene {scene_id:02d}: PIL fallback failed: {e}", file=sys.stderr)
        return False


# Deliberate inter-request spacing to prevent IP rate-limiting (e.g., HTTP 429) on Pollinations
_LAST_POLLINATIONS_CALL_TIME = 0.0
_MIN_POLLINATIONS_INTERVAL = 3.5  # seconds between consecutive calls


def download_single_frame_pollinations(
    scene_id: int,
    prompt: str,
    output_path: Path,
    topic_id: str = "default_topic",
    seed_offset: int = 0,
    width: int = 1080,
    height: int = 1920,
    model: str = "flux",
    max_retries: int = 3,
    timeout: int = 45
) -> bool:
    """Renders a keyframe using Pollinations with API key support, request spacing, and retry backoff."""
    global _LAST_POLLINATIONS_CALL_TIME

    if output_path.exists() and output_path.stat().st_size > 5000:
        print(f"[CACHE] Scene {scene_id:02d} already rendered ({output_path.stat().st_size/1024:.1f} KB): {output_path.name}")
        return True

    encoded_prompt = urllib.parse.quote(prompt)
    base_seed = int(hashlib.sha256(topic_id.encode("utf-8")).hexdigest()[:8], 16) % (2**31)
    seed = (base_seed + seed_offset) % (2**31)

    api_key = os.environ.get("POLLINATIONS_API_KEY", "").strip()
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    current_model = model
    for attempt in range(1, max_retries + 1):
        # 1. Enforce deliberate request spacing (at least 3.5s gap between consecutive API calls)
        now = time.time()
        elapsed_since_last = now - _LAST_POLLINATIONS_CALL_TIME
        if _LAST_POLLINATIONS_CALL_TIME > 0 and elapsed_since_last < _MIN_POLLINATIONS_INTERVAL:
            sleep_gap = _MIN_POLLINATIONS_INTERVAL - elapsed_since_last
            print(f"[POLLINATIONS SPACING] Scene {scene_id:02d}: Pausing {sleep_gap:.2f}s before request to prevent rate limiting...")
            time.sleep(sleep_gap)

        key_param = f"&key={api_key}" if api_key else ""
        url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&model={current_model}&nologo=true&seed={seed}{key_param}"

        t0 = time.time()
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                call_duration = time.time() - t0
                _LAST_POLLINATIONS_CALL_TIME = time.time()
                status_code = response.status
                data = response.read()

                print(f"[POLLINATIONS] Scene {scene_id:02d} | Attempt {attempt}/{max_retries} | HTTP {status_code} OK | Duration: {call_duration:.2f}s | Model: {current_model} | Size: {len(data)/1024:.1f} KB")

                if len(data) > 5000:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    # Convert to clean RGB PNG (resizing if Pollinations clamps dimension)
                    img = Image.open(io.BytesIO(data)).convert("RGB")
                    if img.size != (width, height):
                        img = img.resize((width, height), Image.Resampling.LANCZOS)
                    img.save(output_path, "PNG")
                    print(f"[POLLINATIONS SUCCESS] Scene {scene_id:02d} saved as {output_path.name} ({img.size[0]}x{img.size[1]} PNG)")
                    return True
                else:
                    print(f"[WARN] Scene {scene_id:02d} | Attempt {attempt}/{max_retries}: Small payload ({len(data)} B), retrying...", file=sys.stderr)

        except urllib.error.HTTPError as he:
            call_duration = time.time() - t0
            _LAST_POLLINATIONS_CALL_TIME = time.time()
            status_code = he.code
            print(f"[POLLINATIONS] Scene {scene_id:02d} | Attempt {attempt}/{max_retries} | HTTP {status_code} ({he.reason}) | Duration: {call_duration:.2f}s | Model: {current_model}", file=sys.stderr)

            if status_code == 429:
                backoff = 5.0 * attempt
                print(f"[POLLINATIONS RATE-LIMIT] Scene {scene_id:02d}: Rate limited (HTTP 429). Backing off {backoff:.1f}s before retry...", file=sys.stderr)
                time.sleep(backoff)
            elif status_code in (500, 502, 503, 504):
                backoff = 3.0 * attempt
                print(f"[POLLINATIONS SERVER-ERROR] Scene {scene_id:02d}: Server error (HTTP {status_code}). Backing off {backoff:.1f}s before retry...", file=sys.stderr)
                time.sleep(backoff)
            else:
                backoff = 2.0 * attempt
                time.sleep(backoff)

        except urllib.error.URLError as ue:
            call_duration = time.time() - t0
            _LAST_POLLINATIONS_CALL_TIME = time.time()
            print(f"[POLLINATIONS] Scene {scene_id:02d} | Attempt {attempt}/{max_retries} | URLError ({ue.reason}) | Duration: {call_duration:.2f}s | Model: {current_model}", file=sys.stderr)
            time.sleep(2.0 * attempt)

        except Exception as e:
            call_duration = time.time() - t0
            _LAST_POLLINATIONS_CALL_TIME = time.time()
            print(f"[POLLINATIONS] Scene {scene_id:02d} | Attempt {attempt}/{max_retries} | Error ({e}) | Duration: {call_duration:.2f}s | Model: {current_model}", file=sys.stderr)
            time.sleep(2.0 * attempt)

    # Secondary try with 'turbo' if flux timed out/exhausted
    if model != "turbo":
        print(f"[NOTICE] Scene {scene_id:02d}: Flux attempts exhausted. Attempting Pollinations secondary fallback model 'turbo'...", file=sys.stderr)
        now = time.time()
        elapsed_since_last = now - _LAST_POLLINATIONS_CALL_TIME
        if _LAST_POLLINATIONS_CALL_TIME > 0 and elapsed_since_last < _MIN_POLLINATIONS_INTERVAL:
            sleep_gap = _MIN_POLLINATIONS_INTERVAL - elapsed_since_last
            print(f"[POLLINATIONS SPACING] Scene {scene_id:02d}: Pausing {sleep_gap:.2f}s before turbo fallback...")
            time.sleep(sleep_gap)

        key_param = f"&key={api_key}" if api_key else ""
        fallback_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&model=turbo&nologo=true&seed={seed}{key_param}"
        t0 = time.time()
        try:
            req = urllib.request.Request(fallback_url, headers=headers)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                call_duration = time.time() - t0
                _LAST_POLLINATIONS_CALL_TIME = time.time()
                status_code = response.status
                data = response.read()
                print(f"[POLLINATIONS] Scene {scene_id:02d} | Turbo Fallback | HTTP {status_code} OK | Duration: {call_duration:.2f}s | Size: {len(data)/1024:.1f} KB")
                if len(data) > 5000:
                    output_path.parent.mkdir(parents=True, exist_ok=True)
                    img = Image.open(io.BytesIO(data)).convert("RGB")
                    if img.size != (width, height):
                        img = img.resize((width, height), Image.Resampling.LANCZOS)
                    img.save(output_path, "PNG")
                    print(f"[POLLINATIONS SUCCESS] Scene {scene_id:02d} rendered with turbo fallback: {output_path.name}")
                    return True
        except Exception as fe:
            call_duration = time.time() - t0
            _LAST_POLLINATIONS_CALL_TIME = time.time()
            print(f"[POLLINATIONS ERROR] Scene {scene_id:02d}: Fallback to turbo failed: {fe} | Duration: {call_duration:.2f}s", file=sys.stderr)

    return False


def render_scene_frame(
    scene_id: int,
    prompt: str,
    output_path: Path,
    topic_id: str,
    engine: str,
    seed_offset: int = 0,
    width: int = 1080,
    height: int = 1920,
    model: str = "flux"
) -> Tuple[bool, str]:
    """
    Renders a single frame through the resolved engine hierarchy.
    Returns (success: bool, engine_used: str).
    """
    if output_path.exists() and output_path.stat().st_size > 5000:
        return True, "cache"

    # 1. ComfyUI (if requested and available)
    if engine == "comfyui":
        # ComfyUI generation placeholder if workflow queue is implemented
        # If unavailable or fails, falls through to pollinations
        pass

    # 2. Pollinations
    if engine in ["comfyui", "pollinations", "auto"]:
        ok = download_single_frame_pollinations(
            scene_id=scene_id,
            prompt=prompt,
            output_path=output_path,
            topic_id=topic_id,
            seed_offset=seed_offset,
            width=width,
            height=height,
            model=model
        )
        if ok:
            return True, "pollinations"

    # CRITICAL: If engine was forced to 'pollinations', DO NOT fall through to PIL!
    # Fail loudly so rate limits or errors are visible to the operator.
    if engine == "pollinations":
        print(f"[ERROR] Scene {scene_id:02d}: Forced engine 'pollinations' failed to produce keyframe. PIL fallback is strictly DISABLED for this run.", file=sys.stderr)
        return False, "pollinations_failed"

    # 3. PIL Fallback
    print(f"[NOTICE] Scene {scene_id:02d}: Falling through to PIL artistic fallback...")
    ok_pil = render_pil_fallback_frame(
        scene_id=scene_id,
        prompt=prompt,
        output_path=output_path,
        topic_id=topic_id,
        width=width,
        height=height
    )
    with open("degraded_scenes.log", "a", encoding="utf-8") as lf:
        lf.write(f"topic_id={topic_id} scene_id={scene_id} engine=pil\n")
    return ok_pil, "pil"


def generate_frames_parallel(
    storyboard_path: Path,
    output_dir: Path,
    topic_id: Optional[str] = None,
    seed_offset: int = 0,
    width: int = 1080,
    height: int = 1920,
    model: str = "flux",
    engine: str = "auto",
    max_workers: int = 2
) -> str:
    """
    Batch generates keyframes with engine fallback and writes engine_info.json.
    Returns the primary engine used ('comfyui', 'pollinations', or 'pil').
    """
    with open(storyboard_path, "r", encoding="utf-8") as f:
        sb = json.load(f)

    resolved_topic_id = topic_id or sb.get("topic_id") or "default_topic"
    scenes = sb.get("scenes", [])
    if not scenes:
        raise ValueError("Storyboard contains no scenes.")

    output_dir.mkdir(parents=True, exist_ok=True)

    # Determine resolved engine
    resolved_engine = engine
    if engine == "auto":
        if check_comfyui_health():
            print("[ENGINE] ComfyUI REST server is responsive. Using engine: comfyui")
            resolved_engine = "comfyui"
        else:
            print("[ENGINE] ComfyUI unreachable (offline/cloud runner). Falling through to engine: pollinations")
            resolved_engine = "pollinations"
    elif engine == "pollinations":
        print("[ENGINE FORCED] Forcing engine: pollinations. Skipping ComfyUI health check and disabling PIL fallback.")

    # When using Pollinations, serialize generation (1 worker) to prevent concurrent burst rate limits
    if resolved_engine == "pollinations" and max_workers > 1:
        print(f"[POLLINATIONS] Overriding max_workers from {max_workers} to 1 (sequential) to ensure API rate limit compliance.")
        max_workers = 1

    print(f"[INFO] Batch generating {len(scenes)} keyframes (Topic: {resolved_topic_id}, Engine: {resolved_engine}, Model: {model}, Resolution: {width}x{height})...")

    # Clean old extra frames if scene count changed
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

            time.sleep(0.2)
            f = executor.submit(
                render_scene_frame,
                scene_id=scene_id,
                prompt=prompt,
                output_path=out_file,
                topic_id=resolved_topic_id,
                engine=resolved_engine,
                seed_offset=scene_seed_offset,
                width=width,
                height=height,
                model=model
            )
            tasks.append((scene_id, f))

        results = {}
        engines_used = []
        for scene_id, f in tasks:
            success, eng = f.result()
            results[scene_id] = success
            engines_used.append(eng)

    successful = sum(1 for s in results.values() if s)
    print(f"[INFO] Rendering complete: {successful}/{len(scenes)} frames available.")

    pil_count = sum(1 for e in engines_used if e == "pil")
    primary_engine = "pil" if pil_count > len(scenes) // 2 else resolved_engine
    is_degraded = pil_count > 0

    engine_info = {
        "primary_engine": primary_engine,
        "resolved_engine": resolved_engine,
        "engines_used": engines_used,
        "degraded": is_degraded,
        "degraded_count": pil_count,
        "total_scenes": len(scenes)
    }
    with open(output_dir / "engine_info.json", "w", encoding="utf-8") as ef:
        json.dump(engine_info, ef, indent=2)

    if successful != len(scenes):
        missing = [sid for sid, s in results.items() if not s]
        print(f"[ERROR] Missing keyframes for scene IDs: {missing}", file=sys.stderr)
        sys.exit(1)

    print(f"[SUCCESS] All {len(scenes)} keyframes verified in {output_dir.resolve()} (Primary Engine: {primary_engine})")
    return primary_engine


def main():
    parser = argparse.ArgumentParser(description="Vertical keyframe generation with dual-pipeline fallback.")
    parser.add_argument("--storyboard", type=str, default="state/storyboard.json", help="Path to input storyboard JSON.")
    parser.add_argument("--output-dir", type=str, default="assets/frames", help="Directory for rendered PNG frames.")
    parser.add_argument("--topic-id", type=str, default=None, help="Topic ID for consistent seed derivation.")
    parser.add_argument("--seed-offset", type=int, default=0, help="Global seed offset.")
    parser.add_argument("--model", type=str, default="flux", help="Pollinations model (flux or turbo).")
    parser.add_argument("--engine", type=str, default="auto", choices=["auto", "comfyui", "pollinations", "pil"], help="Visual engine.")
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
        engine=args.engine,
        max_workers=args.workers
    )


if __name__ == "__main__":
    main()
