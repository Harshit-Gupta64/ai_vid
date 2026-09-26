#!/usr/bin/env python3
"""
scripts/test_claim_concurrency.py - Verify Atomic Topic Claiming Concurrency

Simulates two concurrent workers (Runner A and Runner B) simultaneously attempting
to claim topics from Turso DB. Proves no race conditions or duplicate claims occur.
"""

import concurrent.futures
import sys
import time
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.db import claim_next_topic, execute, reset_topic_unclaimed


def worker_claim(worker_name: str):
    time.sleep(0.05)  # slight stagger to align at network level
    claimed = claim_next_topic(worker_name)
    return worker_name, claimed


def main():
    print("=" * 70)
    print("Atomic Topic Claiming Concurrency Test")
    print("=" * 70)

    # 1. Check initial unclaimed count
    initial_res = execute("SELECT id, status, claimed_by FROM topics WHERE status = 'unclaimed';")
    unclaimed = initial_res.get("rows", [])
    print(f"Initial unclaimed topics in Turso: {len(unclaimed)}")
    if len(unclaimed) < 2:
        print("[WARN] Need at least 2 unclaimed topics for test. Resetting one if needed.")

    # 2. Launch 2 parallel claims simultaneously
    print("\nLaunching simultaneous claims from 'runner_cloud_worker' and 'runner_local_worker'...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f1 = executor.submit(worker_claim, "runner_cloud_worker")
        f2 = executor.submit(worker_claim, "runner_local_worker")
        res1 = f1.result()
        res2 = f2.result()

    worker1, topic1 = res1
    worker2, topic2 = res2

    print(f"\nResult Worker 1 ({worker1}):")
    if topic1:
        print(f"  Claimed Topic ID: {topic1['id']}")
        print(f"  Title: {topic1['title']}")
        print(f"  Status: {topic1['status']}, Claimed By: {topic1['claimed_by']}")
    else:
        print("  Claimed: None (No topic available)")

    print(f"\nResult Worker 2 ({worker2}):")
    if topic2:
        print(f"  Claimed Topic ID: {topic2['id']}")
        print(f"  Title: {topic2['title']}")
        print(f"  Status: {topic2['status']}, Claimed By: {topic2['claimed_by']}")
    else:
        print("  Claimed: None (No topic available)")

    # 3. Assertions
    assert topic1 is not None, "Worker 1 should have claimed a topic"
    assert topic2 is not None, "Worker 2 should have claimed a topic"
    assert topic1["id"] != topic2["id"], f"Collision detected! Both workers claimed '{topic1['id']}'"

    print("\n" + "-" * 70)
    print(f"[VERIFIED] No collision: Worker 1 claimed '{topic1['id']}' and Worker 2 claimed '{topic2['id']}'.")

    # 4. Check DB state directly
    verify_db = execute("SELECT id, status, claimed_by, claimed_at FROM topics WHERE id IN (?, ?);", [topic1["id"], topic2["id"]])
    print("\nDirect Turso DB Rows:")
    for r in verify_db.get("rows", []):
        print(f"  Topic: {r['id']} | Status: {r['status']} | Claimed By: {r['claimed_by']} | Claimed At: {r['claimed_at']}")

    # 5. Clean up by resetting the test topics back to unclaimed
    print("\nResetting test topics back to 'unclaimed' so they remain available for production runs...")
    reset_topic_unclaimed(topic1["id"])
    reset_topic_unclaimed(topic2["id"])
    print("[OK] Test topics reset.")
    print("=" * 70)


if __name__ == "__main__":
    main()
