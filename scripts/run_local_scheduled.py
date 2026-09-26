#!/usr/bin/env python3
"""
scripts/run_local_scheduled.py - Local Scheduled Runner for Windows Task Scheduler

Triggered 3x daily by Windows Task Scheduler (e.g. 09:00, 15:00, 21:00 local time).
Claims the next unclaimed topic from Turso DB, executes the full pipeline locally
(checking local ComfyUI instance first), archives release, uploads to Google Drive,
sends Telegram notification, and records run in Turso published_runs table.
"""

import argparse
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.pipeline_core import run_pipeline_scheduled, execute_pipeline_for_topic
from scripts.db import execute


def main():
    parser = argparse.ArgumentParser(description="Local scheduled video generation runner.")
    parser.add_argument("--runner-id", type=str, default="windows_local_scheduler", help="Unique runner identifier.")
    parser.add_argument("--engine", type=str, default="auto", choices=["auto", "comfyui", "pollinations", "pil"], help="Visual engine preference.")
    parser.add_argument("--topic-id", type=str, default=None, help="Force execution of a specific topic ID rather than claiming next unclaimed.")

    args = parser.parse_args()

    if args.topic_id:
        print(f"[LOCAL RUNNER] Explicit topic override requested: {args.topic_id}")
        res = execute("SELECT * FROM topics WHERE id = ?;", [args.topic_id])
        if not res.get("rows"):
            print(f"[ERROR] Topic '{args.topic_id}' not found in Turso database.", file=sys.stderr)
            sys.exit(1)
        topic = res["rows"][0]
        # Mark as claimed by this runner
        execute("UPDATE topics SET status = 'claimed', claimed_by = ?, claimed_at = CURRENT_TIMESTAMP WHERE id = ?;", [args.runner_id, args.topic_id])
        success = execute_pipeline_for_topic(topic, runner_id=args.runner_id, engine_preference=args.engine)
    else:
        success = run_pipeline_scheduled(runner_id=args.runner_id, engine_preference=args.engine)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
