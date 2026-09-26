#!/usr/bin/env python3
"""
scripts/pipeline_core.py - Unified Pipeline Execution Engine

Orchestrates the entire video production pipeline from atomic Turso claim
to multi-vector Deep QA, Google Drive upload, and Telegram notification.
Used by both the local Windows Task Scheduler runner and the GitHub Actions cloud runner.
"""

import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

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
        "--voice", "en-US-ChristopherNeural",
        "--rate", "+20%"
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

    # 8. Archive Release Bundle
    release_dir = out_dir / "releases" / topic_id
    release_dir.mkdir(parents=True, exist_ok=True)
    if out_video.exists():
        shutil.copy2(out_video, release_dir / f"{topic_id}.mp4")
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
    try:
        log("[DELIVERY] Uploading release package to Google Drive...")
        drive_folder_id = upload_to_drive(release_dir, postable=is_postable)
        log(f"[DELIVERY] Uploaded to Google Drive Folder: {drive_folder_id}")
    except Exception as de:
        log(f"[WARN] Google Drive upload encountered an error: {de}")

    try:
        log("[DELIVERY] Sending notification to Telegram...")
        hashtags = ["#MilitaryHistory", "#TacticalWarfare", f"#{category.replace('_', '')}", "#Shorts"]
        telegram_message_id = send_telegram_notification(
            title=title,
            hashtags=hashtags,
            postable=is_postable,
            video_path_or_drive_link=release_dir / f"{topic_id}.mp4",
            drive_folder_id=drive_folder_id
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
