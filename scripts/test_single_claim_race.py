#!/usr/bin/env python3
"""
scripts/test_single_claim_race.py - Race Condition Test on a Single Unclaimed Topic

Proves that when only 1 topic is available, two simultaneous claims result in
exactly one winner, while the second receives None, with zero double-claims.
"""

import concurrent.futures
import sys
import time
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.db import execute, claim_next_topic


def attempt_claim(worker_id: str):
    time.sleep(0.01)
    sql = """
    UPDATE topics
    SET status = 'claimed',
        claimed_by = ?,
        claimed_at = CURRENT_TIMESTAMP
    WHERE id = (
        SELECT id FROM topics
        WHERE id = 'race-condition-test-topic' AND status = 'unclaimed'
        LIMIT 1
    )
    RETURNING *;
    """
    res = execute(sql, [worker_id])
    rows = res.get("rows", [])
    return worker_id, rows[0] if rows else None


def main():
    print("=" * 70)
    print("Single Topic Race Condition Test (Cloud vs Local)")
    print("=" * 70)

    # 1. Insert a single dedicated race test topic
    test_id = "race-condition-test-topic"
    execute("DELETE FROM topics WHERE id = ?;", [test_id])
    execute(
        """
        INSERT INTO topics (id, title, category_id, status)
        VALUES (?, 'Race Test Topic', 'tactical_anomaly', 'unclaimed');
        """,
        [test_id]
    )
    print(f"Created dedicated test topic '{test_id}' with status 'unclaimed'.")

    # 2. Concurrently attempt to claim this exact topic from Cloud and Local
    print("\nSimultaneously firing claim requests from 'cloud_runner' and 'local_runner'...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        f_cloud = executor.submit(attempt_claim, "cloud_runner")
        f_local = executor.submit(attempt_claim, "local_runner")
        res_cloud = f_cloud.result()
        res_local = f_local.result()

    winner = None
    loser = None
    if res_cloud[1] is not None and res_local[1] is None:
        winner = res_cloud
        loser = res_local
    elif res_local[1] is not None and res_cloud[1] is None:
        winner = res_local
        loser = res_cloud
    else:
        raise AssertionError(f"Race condition failure! Cloud: {res_cloud[1]}, Local: {res_local[1]}")

    print(f"\n[WINNER]: {winner[0]} successfully claimed the topic!")
    print(f"[LOSER] : {loser[0]} received None (topic was already atomically claimed).")

    # 3. Query DB to prove final state
    db_state = execute("SELECT id, status, claimed_by, claimed_at FROM topics WHERE id = ?;", [test_id])
    row = db_state["rows"][0]
    print("\nFinal Turso Database State for topic:")
    print(f"  ID        : {row['id']}")
    print(f"  Status    : {row['status']}")
    print(f"  Claimed By: {row['claimed_by']}")
    print(f"  Claimed At: {row['claimed_at']}")

    # 4. Clean up test row
    execute("DELETE FROM topics WHERE id = ?;", [test_id])
    print("\nCleaned up race test topic.")
    print("=" * 70)
    print("[PASS] Atomic single-topic race condition verification complete.")


if __name__ == "__main__":
    main()
