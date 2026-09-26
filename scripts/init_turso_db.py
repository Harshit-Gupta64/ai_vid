#!/usr/bin/env python3
"""
scripts/init_turso_db.py - Idempotent Database Initialization & Topic Seeder

Creates categories, topics, and published_runs tables in Turso libSQL DB.
Seeds default categories and catalog topics.
Prints out verified live schema and row counts.
"""

import sys
from pathlib import Path

# Add project root to sys.path
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from scripts.db import (
    init_schema,
    seed_categories,
    seed_topics_from_catalog,
    get_schema,
    get_topics,
    execute
)

try:
    from agent.skills.topic_miner.scripts.mine_topics import TOPIC_CATALOG
except ImportError:
    # Try alternate import path
    sys.path.insert(0, str(ROOT_DIR / ".agent" / "skills" / "topic-miner" / "scripts"))
    from mine_topics import TOPIC_CATALOG


def main():
    print("=" * 70)
    print("Initializing Turso libSQL Database Schema & Seeding Topics")
    print("=" * 70)

    print("\n1. Applying DDL schema (idempotent CREATE TABLE IF NOT EXISTS)...")
    init_schema()
    print("   [OK] Tables 'categories', 'topics', 'published_runs' verified.")

    print("\n2. Seeding default tactical categories...")
    seed_categories()
    print("   [OK] Categories seeded.")

    print(f"\n3. Seeding {len(TOPIC_CATALOG)} catalog topics into 'topics' table...")
    seed_topics_from_catalog(TOPIC_CATALOG)
    print("   [OK] Topics catalog synchronized.")

    print("\n4. Verifying created database schema from sqlite_master:")
    schema_rows = get_schema()
    for row in schema_rows:
        print(f"\n--- [{row['type'].upper()}] {row['name']} ---")
        print(row["sql"])

    print("\n" + "=" * 70)
    print("Table Row Counts Summary:")
    for tbl in ["categories", "topics", "published_runs"]:
        res = execute(f"SELECT COUNT(*) as count FROM {tbl};")
        count = res["rows"][0]["count"] if res["rows"] else 0
        print(f"  - {tbl}: {count} rows")

    print("\nTopic Breakdown by Status:")
    res_status = execute("SELECT status, COUNT(*) as count FROM topics GROUP BY status;")
    for row in res_status.get("rows", []):
        print(f"  - {row['status']}: {row['count']}")

    print("=" * 70)
    print("[SUCCESS] Turso database initialization complete.")


if __name__ == "__main__":
    main()
