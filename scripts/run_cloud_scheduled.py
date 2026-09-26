#!/usr/bin/env python3
"""
scripts/run_cloud_scheduled.py - Cloud Scheduled Runner for GitHub Actions

Triggered 4x daily via cron (or workflow_dispatch) on GitHub Actions.
Claims the next unclaimed topic from Turso DB. ComfyUI health check safely falls
through to Pollinations AI (with API key) and PIL fallback.
Archives release, uploads to Google Drive, sends Telegram notification,
and records run in Turso published_runs table.
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.pipeline_core import run_pipeline_scheduled, execute_pipeline_for_topic
from scripts.db import execute


def main():
    parser = argparse.ArgumentParser(description="Cloud scheduled video generation runner.")
    run_id = os.environ.get("GITHUB_RUN_ID", "cloud_runner")
    runner_id_default = f"github_actions_{run_id}"

    parser.add_argument("--runner-id", type=str, default=runner_id_default, help="Unique runner identifier.")
    parser.add_argument("--engine", type=str, default="auto", choices=["auto", "comfyui", "pollinations", "pil"], help="Visual engine preference.")
    parser.add_argument("--topic-id", type=str, default=None, help="Force execution of a specific topic ID.")

    args = parser.parse_args()

    if args.topic_id:
        print(f"[CLOUD RUNNER] Explicit topic override requested: {args.topic_id}")
        res = execute("SELECT * FROM topics WHERE id = ?;", [args.topic_id])
        if not res.get("rows"):
            print(f"[ERROR] Topic '{args.topic_id}' not found in Turso database.", file=sys.stderr)
            sys.exit(1)
        topic = res["rows"][0]
        execute("UPDATE topics SET status = 'claimed', claimed_by = ?, claimed_at = CURRENT_TIMESTAMP WHERE id = ?;", [args.runner_id, args.topic_id])
        success = execute_pipeline_for_topic(topic, runner_id=args.runner_id, engine_preference=args.engine)
    else:
        success = run_pipeline_scheduled(runner_id=args.runner_id, engine_preference=args.engine)

    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
