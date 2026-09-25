#!/usr/bin/env python3
"""
run_batch.py - Multi-Hour Unattended Batch Orchestration Engine

Sequentially processes a queue of topics with:
- Per-topic try/except isolation (failure on topic K does not abort K+1..N)
- Resumable state persistence (state/batch_progress.json)
- Dynamic variable pacing & Ken Burns compilation
- Final markdown summary reporting (out/BATCH_REPORT.md)
"""

import argparse
import datetime
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[4]


def load_batch_queue(queue_file: Path, cli_topics: str = None) -> list[str]:
    """Resolves topic list from CLI argument or batch queue JSON."""
    if cli_topics:
        return [t.strip() for t in cli_topics.split(",") if t.strip()]

    if queue_file.exists():
        try:
            with open(queue_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                return data
            return data.get("topics", [])
        except Exception as e:
            print(f"[WARN] Failed to read queue file '{queue_file}': {e}", file=sys.stderr)

    return ["archimedes-claw", "battle-of-carrhae-camel-train"]


def load_progress(progress_file: Path) -> dict:
    """Loads existing progress state or initializes a new batch manifest."""
    if progress_file.exists():
        try:
            with open(progress_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            print(f"[WARN] Corrupt progress file '{progress_file}', reinitializing: {e}", file=sys.stderr)

    return {
        "batch_id": f"batch_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}",
        "started_at": datetime.datetime.now().isoformat(),
        "last_updated": datetime.datetime.now().isoformat(),
        "total_topics": 0,
        "completed": [],
        "failed": [],
        "in_progress": None,
        "pending": []
    }


def save_progress(progress: dict, progress_file: Path):
    """Atomically saves progress manifest."""
    progress["last_updated"] = datetime.datetime.now().isoformat()
    progress_file.parent.mkdir(parents=True, exist_ok=True)
    temp_file = progress_file.with_suffix(".tmp")
    with open(temp_file, "w", encoding="utf-8") as f:
        json.dump(progress, f, indent=2, ensure_ascii=False)
    temp_file.replace(progress_file)


def check_gemini_preflight(model: str = "gemini-3.6-flash") -> tuple[bool, str]:
    """Lightweight test call to verify Gemini API key and model availability."""
    try:
        from google import genai
        # Resolve key
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        if not key and sys.platform == "win32":
            try:
                import winreg
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Environment") as env_key:
                    try:
                        val, _ = winreg.QueryValueEx(env_key, "GEMINI_API_KEY")
                        if val:
                            key = val
                            os.environ["GEMINI_API_KEY"] = val
                    except WindowsError:
                        pass
            except Exception:
                pass
        if not key:
            return False, "No GEMINI_API_KEY found in environment or registry."
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(
            model=model,
            contents="ping"
        )
        if resp.text:
            return True, f"Gemini API confirmed operational (model: {model})."
        return False, "Gemini API returned empty response."
    except Exception as e:
        return False, f"Gemini API probe failed: {e}"


def generate_batch_report(progress: dict, report_path: Path):
    """Generates an executive markdown report summarizing the batch run with engine transparency."""
    report_path.parent.mkdir(parents=True, exist_ok=True)
    completed = progress.get("completed", [])
    failed = progress.get("failed", [])
    total = len(completed) + len(failed) + len(progress.get("pending", []))

    lines = [
        "# Unattended Production & Quality Assurance Batch Report",
        f"**Batch ID**: `{progress.get('batch_id')}`  ",
        f"**Started**: {progress.get('started_at')}  ",
        f"**Last Updated**: {progress.get('last_updated')}  ",
        f"**Execution Summary**: {len(completed)} / {total} Completed ({len(failed)} Failed)",
        "",
        "---",
        "",
        "## Production Table",
        "| Topic ID | Generation Engine | Model / Details | Status | Duration | Cuts | Duration Variance (Min-Max) | QA Status | Master File |",
        "| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |"
    ]

    for item in completed:
        tid = item.get("topic_id", "unknown")
        engine = item.get("generation_engine", "gemini_llm")
        model = item.get("generation_model") or ("gemini-3.6-flash" if engine == "gemini_llm" else "N/A (Algorithmic)")
        is_degraded = (engine == "algorithmic_fallback")
        status_badge = "⚠️ DEGRADED" if is_degraded else "✅ SUCCESS"
        dur = f"{item.get('duration', 0.0):.1f}s"
        cuts = item.get("scene_count", 0)
        v = item.get("duration_variance", {})
        var_str = f"{v.get('min', 0.0):.1f}s - {v.get('max', 0.0):.1f}s (σ={v.get('std_dev', 0.0):.2f})"
        qa = item.get("qa_status", "PASS")
        vpath = item.get("video_path", "")
        engine_label = "`algorithmic_fallback`" if is_degraded else "`gemini_llm`"
        lines.append(f"| `{tid}` | {engine_label} | `{model}` | {status_badge} | {dur} | {cuts} | {var_str} | {qa} | `{vpath}` |")

    for item in failed:
        tid = item.get("topic_id", "unknown")
        stage = item.get("stage", "unknown")
        err = item.get("error", "Error")[:40]
        lines.append(f"| `{tid}` | `unknown` | `N/A` | ❌ FAILED | - | - | - | Stage: {stage} ({err}) | - |")

    if failed:
        lines.extend([
            "",
            "## Incident Log (Failed Topics)",
            "| Topic ID | Stage | Error Detail | Timestamp |",
            "| :--- | :--- | :--- | :--- |"
        ])
        for item in failed:
            lines.append(f"| `{item.get('topic_id')}` | `{item.get('stage')}` | {item.get('error')} | {item.get('timestamp')} |")

    lines.append("")
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    print(f"[REPORT] Batch report updated: {report_path.resolve()}")


def execute_topic_pipeline(topic_id: str, skip_qa: bool = False) -> dict:
    """
    Executes the end-to-end 6-stage video production pipeline for a single topic.
    Returns metrics dictionary upon success; raises RuntimeError on failure.
    """
    python_bin = sys.executable

    # Setup isolated paths for this topic
    topic_dir = REPO_ROOT / "state" / "batch" / topic_id
    topic_dir.mkdir(parents=True, exist_ok=True)

    topic_json = topic_dir / "topic.json"
    storyboard_json = topic_dir / "storyboard.json"
    audio_dir = REPO_ROOT / "assets" / "audio" / topic_id
    audio_dir.mkdir(parents=True, exist_ok=True)
    voiceover_wav = audio_dir / "voiceover.wav"
    timestamps_json = audio_dir / "timestamps.json"
    frames_dir = REPO_ROOT / "assets" / "frames" / topic_id
    frames_dir.mkdir(parents=True, exist_ok=True)
    output_dir = REPO_ROOT / "out" / "releases_v4" / topic_id
    output_dir.mkdir(parents=True, exist_ok=True)
    final_video = output_dir / f"{topic_id}.mp4"

    # Stage 1: Mine/Structure Topic
    print(f"\n[{topic_id}] STAGE 1: Structuring Topic...")
    s1_cmd = [
        python_bin, str(REPO_ROOT / ".agent" / "skills" / "topic-miner" / "scripts" / "mine_topics.py"),
        "--topic-id", topic_id,
        "--output", str(topic_json.resolve())
    ]
    r1 = subprocess.run(s1_cmd, capture_output=True, text=True)
    if r1.returncode != 0:
        raise RuntimeError(f"Topic mining failed: {r1.stderr.strip() or r1.stdout.strip()}")

    # Stage 2: Storyboard Generation (Gemini with Beat-Type Pacing)
    print(f"[{topic_id}] STAGE 2: Generating Storyboard with Variable Beat Pacing...")
    s2_cmd = [
        python_bin, str(REPO_ROOT / ".agent" / "skills" / "video-scriptor" / "scripts" / "generate_storyboard.py"),
        "--topic", str(topic_json.resolve()),
        "--output", str(storyboard_json.resolve()),
        "--model", "gemini-3.6-flash"
    ]
    r2 = subprocess.run(s2_cmd, capture_output=True, text=True)
    if r2.returncode != 0:
        raise RuntimeError(f"Storyboard generation failed: {r2.stderr.strip() or r2.stdout.strip()}")

    # Stage 3: TTS Narration & Timestamp Alignment
    print(f"[{topic_id}] STAGE 3: Synthesizing Narration & Aligning Timestamps...")
    s3_cmd = [
        python_bin, str(REPO_ROOT / ".agent" / "skills" / "tts-audio-generator" / "scripts" / "synthesize.py"),
        "--storyboard", str(storyboard_json.resolve()),
        "--output-audio", str(voiceover_wav.resolve()),
        "--output-timestamps", str(timestamps_json.resolve()),
        "--rate", "+14%"
    ]
    r3 = subprocess.run(s3_cmd, capture_output=True, text=True)
    if r3.returncode != 0:
        raise RuntimeError(f"TTS Synthesis failed: {r3.stderr.strip() or r3.stdout.strip()}")

    # Stage 4: Keyframe Generation (Pollinations Flux with Topic Seed)
    print(f"[{topic_id}] STAGE 4: Generating Vertical Keyframes...")
    s4_cmd = [
        python_bin, str(REPO_ROOT / ".agent" / "skills" / "image-generator" / "scripts" / "generate_frames.py"),
        "--storyboard", str(storyboard_json.resolve()),
        "--output-dir", str(frames_dir.resolve()),
        "--topic-id", topic_id,
        "--workers", "1"
    ]
    r4 = subprocess.run(s4_cmd, capture_output=True, text=True)
    if r4.returncode != 0:
        raise RuntimeError(f"Keyframe generation failed: {r4.stderr.strip() or r4.stdout.strip()}")

    # Stage 5: Video Compilation (Normalized Ken Burns + Sidechain Ducking)
    print(f"[{topic_id}] STAGE 5: Compiling Short-Form Video...")
    s5_cmd = [
        python_bin, str(REPO_ROOT / ".agent" / "skills" / "remotion-video-compiler" / "scripts" / "render_short.py"),
        "--storyboard", str(storyboard_json.resolve()),
        "--topic", str(topic_json.resolve()),
        "--audio", str(voiceover_wav.resolve()),
        "--timestamps", str(timestamps_json.resolve()),
        "--frames-dir", str(frames_dir.resolve()),
        "--output", str(final_video.resolve()),
        "--topic-id", topic_id
    ]
    r5 = subprocess.run(s5_cmd, capture_output=True, text=True)
    if r5.returncode != 0:
        raise RuntimeError(f"Video compilation failed: {r5.stderr.strip() or r5.stdout.strip()}")

    # Stage 6: Deep QA Inspector Audit
    mean_volume = None
    qa_status = "SKIPPED"
    if not skip_qa:
        print(f"[{topic_id}] STAGE 6: Deep QA Inspection...")
        s6_cmd = [
            python_bin, str(REPO_ROOT / ".agent" / "skills" / "video-verifier" / "scripts" / "deep_qa_inspector.py"),
            "--video", str(final_video.resolve()),
            "--storyboard", str(storyboard_json.resolve()),
            "--timestamps", str(timestamps_json.resolve())
        ]
        r6 = subprocess.run(s6_cmd, capture_output=True, text=True)
        if r6.returncode != 0:
            raise RuntimeError(f"Deep QA failed: {r6.stderr.strip() or r6.stdout.strip()}")
        qa_status = "PASS"

    # Read metadata and compute duration variance statistics from updated storyboard
    with open(storyboard_json, "r", encoding="utf-8") as f:
        final_sb = json.load(f)

    gen_engine = final_sb.get("generation_engine", "gemini_llm")
    gen_model = final_sb.get("generation_model")

    durations = [float(s.get("target_duration", 3.0)) for s in final_sb.get("scenes", [])]
    total_duration = sum(durations)
    avg_dur = total_duration / len(durations) if durations else 0.0
    var_sq = sum((d - avg_dur) ** 2 for d in durations) / len(durations) if durations else 0.0
    std_dev = var_sq ** 0.5

    return {
        "topic_id": topic_id,
        "generation_engine": gen_engine,
        "generation_model": gen_model,
        "duration": round(total_duration, 2),
        "scene_count": len(durations),
        "duration_variance": {
            "min": round(min(durations), 2),
            "max": round(max(durations), 2),
            "avg": round(avg_dur, 2),
            "std_dev": round(std_dev, 2)
        },
        "mean_volume": mean_volume,
        "qa_status": qa_status,
        "video_path": str(final_video.relative_to(REPO_ROOT)).replace("\\", "/")
    }


def run_batch(
    queue_file: Path,
    progress_file: Path,
    report_file: Path,
    cli_topics: str = None,
    force: bool = False,
    skip_qa: bool = False
):
    topics = load_batch_queue(queue_file, cli_topics)
    progress = load_progress(progress_file)

    # Initialize or reconcile pending topics
    completed_ids = {c["topic_id"] for c in progress.get("completed", [])}
    if force:
        completed_ids.clear()
        progress["completed"] = []
        progress["failed"] = []

    pending = [t for t in topics if t not in completed_ids]
    progress["total_topics"] = len(topics)
    progress["pending"] = pending
    save_progress(progress, progress_file)

    # Pre-flight Gemini API check
    llm_ok, llm_msg = check_gemini_preflight(model="gemini-3.6-flash")
    if llm_ok:
        print(f"[PREFLIGHT] [OK] {llm_msg}")
    else:
        print(f"[PREFLIGHT] [WARN] {llm_msg} (Batch will engage algorithmic fallback if needed)", file=sys.stderr)

    print(f"[INFO] Batch initialized: {len(topics)} total topics ({len(completed_ids)} already completed, {len(pending)} pending).")

    for idx, topic_id in enumerate(pending, 1):
        print(f"\n=======================================================")
        print(f" PROCESSING TOPIC {idx}/{len(pending)}: {topic_id}")
        print(f"=======================================================")

        progress["in_progress"] = topic_id
        save_progress(progress, progress_file)

        start_time = time.time()
        try:
            metrics = execute_topic_pipeline(topic_id, skip_qa=skip_qa)
            metrics["timestamp"] = datetime.datetime.now().isoformat()
            metrics["elapsed_seconds"] = round(time.time() - start_time, 1)

            progress["completed"].append(metrics)
            progress["pending"] = [t for t in progress["pending"] if t != topic_id]
            progress["in_progress"] = None
            save_progress(progress, progress_file)
            generate_batch_report(progress, report_file)
            print(f"[SUCCESS] Topic '{topic_id}' completed in {metrics['elapsed_seconds']}s.")

        except Exception as e:
            err_msg = str(e)
            print(f"[ERROR] Topic '{topic_id}' failed: {err_msg}", file=sys.stderr)
            progress["failed"].append({
                "topic_id": topic_id,
                "error": err_msg,
                "timestamp": datetime.datetime.now().isoformat(),
                "elapsed_seconds": round(time.time() - start_time, 1)
            })
            progress["pending"] = [t for t in progress["pending"] if t != topic_id]
            progress["in_progress"] = None
            save_progress(progress, progress_file)
            generate_batch_report(progress, report_file)
            print(f"[ISOLATION] Quarantined failure on '{topic_id}'. Proceeding to next topic in queue.")

    print(f"\n[COMPLETE] Batch run complete. Final report saved to: {report_file.resolve()}")


def main():
    parser = argparse.ArgumentParser(description="Multi-Hour Unattended Short-Form Video Batch Runner.")
    parser.add_argument("--queue", type=str, default="state/batch_queue.json", help="Path to input topics queue JSON.")
    parser.add_argument("--topics", type=str, default=None, help="Comma-separated topic IDs to override queue file.")
    parser.add_argument("--progress", type=str, default="state/batch_progress.json", help="State file tracking batch progress.")
    parser.add_argument("--report", type=str, default="out/BATCH_REPORT.md", help="Destination markdown summary report.")
    parser.add_argument("--force", action="store_true", help="Re-run topics even if previously completed.")
    parser.add_argument("--skip-qa", action="store_true", help="Skip deep QA inspection stage.")

    args = parser.parse_args()

    run_batch(
        queue_file=Path(args.queue),
        progress_file=Path(args.progress),
        report_file=Path(args.report),
        cli_topics=args.topics,
        force=args.force,
        skip_qa=args.skip_qa
    )


if __name__ == "__main__":
    main()
