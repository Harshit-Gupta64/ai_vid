#!/usr/bin/env python3
"""
scripts/pipeline_core.py - Unified Pipeline Execution Engine

Orchestrates the entire video production pipeline from atomic Turso claim
to multi-vector Deep QA, climax thumbnail extraction, title/hashtags generation,
Google Drive packaging, and dual Telegram notification (photo + video).
Used by both the local Windows Task Scheduler runner and the GitHub Actions cloud runner.
"""

import io
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from PIL import Image, ImageStat

# Try loading .env if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.db import (
    claim_next_topic,
    mark_topic_completed,
    mark_topic_failed,
    record_published_run
)
from scripts.delivery import (
    upload_to_drive,
    send_telegram_notification
)


def log(msg: str):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)


def run_command_step(cmd: list, desc: str) -> bool:
    log(f"Executing: {desc}...")
    start = time.time()
    res = subprocess.run(cmd, cwd=str(ROOT_DIR))
    dur = time.time() - start
    if res.returncode != 0:
        log(f"[ERROR] Step '{desc}' failed with exit code {res.returncode} ({dur:.1f}s)")
        return False
    log(f"[SUCCESS] Completed '{desc}' ({dur:.1f}s)")
    return True


def extract_climax_thumbnail(video_path: Path, storyboard_path: Path, output_path: Path) -> Path:
    """
    Selects the highest-contrast, most legible frame from the climax_impact beat
    using pixel intensity variance across candidate timestamps.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    scenes = []
    if storyboard_path.exists():
        try:
            with open(storyboard_path, "r", encoding="utf-8") as f:
                sb = json.load(f)
                scenes = sb.get("scenes", [])
        except Exception:
            pass

    # Find climax beat ranges
    cur_t = 0.0
    climax_ranges = []
    for idx, s in enumerate(scenes):
        dur = float(s.get("target_duration", 3.0))
        beat = s.get("beat_type", "").lower()
        if "climax" in beat:
            climax_ranges.append((cur_t, cur_t + dur, s.get("scene_id", idx + 1)))
        cur_t += dur

    # Fallback to scenes 8-11 if no explicit climax beat labeled
    if not climax_ranges and len(scenes) >= 6:
        cur_t = 0.0
        for idx, s in enumerate(scenes):
            dur = float(s.get("target_duration", 3.0))
            if idx >= len(scenes) // 2 and idx < len(scenes) - 2:
                climax_ranges.append((cur_t, cur_t + dur, s.get("scene_id", idx + 1)))
            cur_t += dur

    if not climax_ranges:
        climax_ranges = [(15.0, 25.0, 1)]

    candidates = []
    for start, end, sid in climax_ranges:
        dur = max(end - start, 0.5)
        for ratio in [0.25, 0.5, 0.75]:
            candidates.append((start + dur * ratio, sid))

    best_score = -1.0
    best_bytes = None
    best_t = candidates[0][0]

    for t, sid in candidates:
        cmd = [
            "ffmpeg", "-y", "-ss", f"{t:.3f}",
            "-i", str(video_path.resolve()),
            "-vframes", "1",
            "-f", "image2pipe",
            "-vcodec", "png", "-"
        ]
        p = subprocess.run(cmd, capture_output=True)
        if p.returncode == 0 and p.stdout:
            try:
                img = Image.open(io.BytesIO(p.stdout)).convert("L")
                stat = ImageStat.Stat(img)
                contrast = stat.stddev[0]
                if contrast > best_score:
                    best_score = contrast
                    best_bytes = p.stdout
                    best_t = t
            except Exception:
                pass

    if best_bytes:
        with open(output_path, "wb") as f:
            f.write(best_bytes)
        log(f"[THUMBNAIL] Selected highest-contrast climax frame at t={best_t:.2f}s (score: {best_score:.2f}) -> {output_path.name}")
    else:
        # Emergency frame capture
        subprocess.run(["ffmpeg", "-y", "-ss", "10.0", "-i", str(video_path), "-vframes", "1", str(output_path)], capture_output=True)
        log(f"[THUMBNAIL] Extracted default thumbnail at t=10.0s -> {output_path.name}")

    return output_path


def generate_title_and_hashtags(topic: Dict[str, Any], release_dir: Path) -> Tuple[str, str]:
    """Generates platform-compressed title.txt and categorized hashtags.txt."""
    hook = topic.get("hook_hookline", "").strip()
    title = topic.get("title", "").strip()
    cat = topic.get("category") or topic.get("category_id", "tactical_anomaly")
    era = topic.get("historical_era", "")

    # Format platform title under 75 chars
    if hook and len(hook) <= 75:
        short_title = hook
    elif title and len(title) <= 75:
        short_title = title
    else:
        first_clause = (hook or title).split(".")[0].split("—")[0].strip()
        short_title = first_clause[:75].strip()

    title_file = release_dir / "title.txt"
    with open(title_file, "w", encoding="utf-8") as f:
        f.write(short_title + "\n")
    log(f"[METADATA] Generated {title_file.name}: '{short_title}'")

    # Format hashtags
    tags = ["#MilitaryHistory", "#TacticalWarfare", "#HistoryShorts", "#Shorts"]
    cat_tag = "#" + "".join(c for c in cat.replace("_", " ").title() if c.isalnum())
    if cat_tag:
        tags.append(cat_tag)
    era_tag = "#" + "".join(c for c in era.split("(")[0].replace("-", " ").title() if c.isalnum())
    if era_tag:
        tags.append(era_tag)
    tid_tag = "#" + "".join(c for c in topic.get("id", "").replace("-", " ").title() if c.isalnum())
    if tid_tag:
        tags.append(tid_tag)

    hashtags_str = " ".join(tags)
    hashtags_file = release_dir / "hashtags.txt"
    with open(hashtags_file, "w", encoding="utf-8") as f:
        f.write(hashtags_str + "\n")
    log(f"[METADATA] Generated {hashtags_file.name}: '{hashtags_str}'")

    return short_title, hashtags_str


def execute_pipeline_for_topic(
    topic: Dict[str, Any],
    runner_id: str,
    engine_preference: str = "auto"
) -> bool:
    topic_id = topic["id"]
    title = topic.get("title", topic_id)
    category = topic.get("category_id") or topic.get("category", "tactical_anomaly")
    start_time = time.time()

    log(f"====================================================================")
    log(f" Starting Production Pipeline for Topic: {title} ({topic_id})")
    log(f" Runner: {runner_id} | Engine Preference: {engine_preference}")
    log(f"====================================================================")

    # 1. Write topic.json to state/topic.json
    state_dir = ROOT_DIR / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    topic_file = state_dir / "topic.json"
    with open(topic_file, "w", encoding="utf-8") as f:
        json.dump(topic, f, indent=2, ensure_ascii=False)
    log(f"[STEP 1] Saved topic configuration to {topic_file}")

    # 2. Generate Storyboard with dynamic pacing
    storyboard_file = state_dir / "storyboard.json"
    cmd_storyboard = [
        sys.executable, ".agent/skills/video-scriptor/scripts/generate_storyboard.py",
        "--topic", str(topic_file),
        "--output", str(storyboard_file)
    ]
    if not run_command_step(cmd_storyboard, "Storyboard Generation"):
        mark_topic_failed(topic_id)
        return False

    # 3. Narration Synthesis (Voiceover & Timestamps)
    audio_dir = ROOT_DIR / "assets" / "audio" / topic_id
    audio_dir.mkdir(parents=True, exist_ok=True)
    voiceover_wav = audio_dir / "voiceover.wav"
    timestamps_json = audio_dir / "timestamps.json"

    cmd_tts = [
        sys.executable, ".agent/skills/tts-audio-generator/scripts/synthesize.py",
        "--storyboard", str(storyboard_file),
        "--output-audio", str(voiceover_wav),
        "--output-timestamps", str(timestamps_json),
        "--engine", "auto",
        "--voice", "am_adam",
        "--rate", "+14%"
    ]
    if not run_command_step(cmd_tts, "Voiceover Narration Synthesis"):
        mark_topic_failed(topic_id)
        return False

    # 4. Keyframe Image Generation (ComfyUI -> Pollinations -> PIL fallback)
    frames_dir = ROOT_DIR / "assets" / "frames" / topic_id
    frames_dir.mkdir(parents=True, exist_ok=True)

    cmd_frames = [
        sys.executable, ".agent/skills/image-generator/scripts/generate_frames.py",
        "--storyboard", str(storyboard_file),
        "--output-dir", str(frames_dir),
        "--topic-id", topic_id,
        "--engine", engine_preference,
        "--model", "flux",
        "--workers", "2"
    ]
    if not run_command_step(cmd_frames, "Keyframe Generation"):
        mark_topic_failed(topic_id)
        return False

    # Read engine info
    engine_info_path = frames_dir / "engine_info.json"
    engine_used = engine_preference
    is_degraded = False
    if engine_info_path.exists():
        try:
            with open(engine_info_path, "r", encoding="utf-8") as ef:
                edata = json.load(ef)
                engine_used = edata.get("primary_engine", engine_preference)
                is_degraded = edata.get("degraded", False)
        except Exception:
            pass

    # 5. Visual Contact Sheet
    contact_sheet_path = frames_dir / "storyboard_grid.png"
    cmd_sheet = [
        sys.executable, ".agent/skills/image-generator/scripts/create_contact_sheet.py",
        "--frames-dir", str(frames_dir),
        "--storyboard", str(storyboard_file),
        "--output", str(contact_sheet_path),
        "--cols", "4"
    ]
    run_command_step(cmd_sheet, "Contact Sheet Compilation")

    # 6. Render Final Short Video
    out_dir = ROOT_DIR / "out"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_video = out_dir / f"{topic_id}.mp4"
    bgm_path = ROOT_DIR / "assets" / "bgm" / "soundtrack.wav"

    cmd_render = [
        sys.executable, ".agent/skills/remotion-video-compiler/scripts/render_short.py",
        "--storyboard", str(storyboard_file),
        "--topic", str(topic_file),
        "--audio", str(voiceover_wav),
        "--timestamps", str(timestamps_json),
        "--frames-dir", str(frames_dir),
        "--bgm", str(bgm_path),
        "--output", str(out_video)
    ]
    if not run_command_step(cmd_render, "Video Compilation & Rendering"):
        mark_topic_failed(topic_id)
        return False

    # 7. Multi-Vector Scrutiny Inspector (Deep QA)
    qa_report_path = out_dir / f"{topic_id}_qa.json"
    cmd_qa = [
        sys.executable, ".agent/skills/video-verifier/scripts/deep_qa_inspector.py",
        "--video", str(out_video),
        "--storyboard", str(storyboard_file),
        "--timestamps", str(timestamps_json),
        "--report", str(qa_report_path)
    ]
    log(f"Running Multi-Vector QA Inspector on {out_video}...")
    qa_proc = subprocess.run(cmd_qa, cwd=str(ROOT_DIR))
    qa_passed = (qa_proc.returncode == 0)

    qa_report_data = {}
    if qa_report_path.exists():
        try:
            with open(qa_report_path, "r", encoding="utf-8") as qf:
                qa_report_data = json.load(qf)
        except Exception:
            pass

    is_postable = qa_passed and not is_degraded
    log(f"[QA VERDICT] Topic '{topic_id}': QA Passed={qa_passed}, Degraded={is_degraded} -> Postable={is_postable}")

    # 8. Archive & Bundle Deliverables
    release_dir = out_dir / "releases" / topic_id
    release_dir.mkdir(parents=True, exist_ok=True)

    # Required deliverable 1: final_short.mp4
    if out_video.exists():
        shutil.copy2(out_video, release_dir / "final_short.mp4")
        shutil.copy2(out_video, release_dir / f"{topic_id}.mp4")

    # Required deliverable 2: thumbnail.png (highest-contrast climax frame)
    thumbnail_file = release_dir / "thumbnail.png"
    extract_climax_thumbnail(out_video, storyboard_file, thumbnail_file)

    # Required deliverables 3 & 4: title.txt and hashtags.txt
    short_title, hashtags_str = generate_title_and_hashtags(topic, release_dir)

    # Additional archival artifacts
    if contact_sheet_path.exists():
        shutil.copy2(contact_sheet_path, release_dir / "storyboard_grid.png")
    if storyboard_file.exists():
        shutil.copy2(storyboard_file, release_dir / "storyboard.json")
    if topic_file.exists():
        shutil.copy2(topic_file, release_dir / "topic.json")
    if timestamps_json.exists():
        shutil.copy2(timestamps_json, release_dir / "timestamps.json")
    if voiceover_wav.exists():
        shutil.copy2(voiceover_wav, release_dir / "voiceover.wav")
    if engine_info_path.exists():
        shutil.copy2(engine_info_path, release_dir / "engine_info.json")

    with open(release_dir / "QA_REPORT.json", "w", encoding="utf-8") as qrf:
        json.dump(qa_report_data, qrf, indent=2)

    total_duration = time.time() - start_time

    # 9. Deliver via Google Drive & Telegram
    drive_folder_id = None
    telegram_message_id = None

    log(f"[DELIVERY] Uploading 4 deliverables (final_short.mp4, thumbnail.png, title.txt, hashtags.txt) + metadata to Google Drive...")
    try:
        drive_folder_id, uploaded_items = upload_to_drive(release_dir, postable=is_postable)
        log(f"[DELIVERY] Upload process complete. Destination folder ID: {drive_folder_id}")
    except Exception as de:
        log(f"[WARN] Google Drive delivery encountered an issue: {de}")

    try:
        log("[DELIVERY] Sending notification with photo thumbnail and video to Telegram...")
        telegram_message_id = send_telegram_notification(
            title=short_title or title,
            hashtags=hashtags_str,
            postable=is_postable,
            video_path_or_drive_link=release_dir / "final_short.mp4",
            drive_folder_id=drive_folder_id,
            thumbnail_path=thumbnail_file
        )
        log(f"[DELIVERY] Telegram notification sent (Message ID: {telegram_message_id})")
    except Exception as te:
        log(f"[WARN] Telegram notification encountered an error: {te}")

    # 10. Record Published Run in Turso DB
    try:
        run_id = record_published_run(
            topic_id=topic_id,
            engine=engine_used,
            postable=is_postable,
            drive_folder_id=drive_folder_id,
            telegram_message_id=telegram_message_id,
            run_duration_sec=round(total_duration, 2)
        )
        log(f"[DB] Recorded run ID #{run_id} in published_runs table.")
    except Exception as dbe:
        log(f"[ERROR] Failed to record published run in Turso DB: {dbe}")

    # 11. Mark Topic Completed
    try:
        mark_topic_completed(topic_id)
        log(f"[DB] Marked topic '{topic_id}' as completed.")
    except Exception as me:
        log(f"[ERROR] Failed to mark topic completed: {me}")

    log(f"====================================================================")
    log(f" Completed Pipeline for {title} in {total_duration:.1f}s")
    log(f"====================================================================")
    return True


def run_pipeline_scheduled(runner_id: str, engine_preference: str = "auto") -> bool:
    """Entry point for scheduled executions: claims next unclaimed topic and executes pipeline."""
    log(f"Scheduled pipeline triggered by runner '{runner_id}'")
    topic = claim_next_topic(runner_id)
    if not topic:
        log("[IDLE] No unclaimed topics remaining in Turso database. Exiting cleanly.")
        return True

    log(f"[CLAIMED] Successfully claimed topic '{topic['id']}' ({topic.get('title')})")
    success = execute_pipeline_for_topic(topic, runner_id=runner_id, engine_preference=engine_preference)
    return success
