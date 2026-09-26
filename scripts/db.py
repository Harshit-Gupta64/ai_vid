#!/usr/bin/env python3
"""
scripts/db.py - Turso libSQL Client for Topic Pipeline & Publishing Log

Provides atomic topic claiming, status tracking, and published run logging
over the Turso HTTP Pipeline v2 API.
"""

import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional
import requests

# Try to load local .env if present
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


def get_turso_config():
    url = os.environ.get("TURSO_DB_URL", "").strip()
    token = os.environ.get("TURSO_AUTH_TOKEN", "").strip()
    if not url:
        raise ValueError("Missing TURSO_DB_URL in environment.")
    if not token:
        raise ValueError("Missing TURSO_AUTH_TOKEN in environment.")

    # Convert libsql:// to https:// and format pipeline endpoint
    base_url = url.replace("libsql://", "https://").rstrip("/")
    if not base_url.endswith("/v2/pipeline"):
        pipeline_url = f"{base_url}/v2/pipeline"
    else:
        pipeline_url = base_url

    return pipeline_url, token


def _encode_arg(v: Any) -> Dict[str, Any]:
    if v is None:
        return {"type": "null"}
    elif isinstance(v, bool):
        return {"type": "integer", "value": "1" if v else "0"}
    elif isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    elif isinstance(v, float):
        return {"type": "float", "value": v}
    else:
        return {"type": "text", "value": str(v)}


def _parse_result(result_dict: Dict[str, Any]) -> Dict[str, Any]:
    cols = [c["name"] for c in result_dict.get("cols", [])]
    rows = []
    for r in result_dict.get("rows", []):
        row = {}
        for idx, cell in enumerate(r):
            col_name = cols[idx]
            ctype = cell.get("type")
            cval = cell.get("value")
            if ctype == "null":
                row[col_name] = None
            elif ctype == "integer" and cval is not None:
                row[col_name] = int(cval)
            elif ctype == "float" and cval is not None:
                row[col_name] = float(cval)
            else:
                row[col_name] = cval
        rows.append(row)
    return {
        "rows": rows,
        "affected_row_count": result_dict.get("affected_row_count", 0),
        "last_insert_rowid": result_dict.get("last_insert_rowid")
    }


def execute(sql: str, args: Optional[List[Any]] = None) -> Dict[str, Any]:
    pipeline_url, token = get_turso_config()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    stmt: Dict[str, Any] = {"sql": sql}
    if args:
        stmt["args"] = [_encode_arg(a) for a in args]

    payload = {
        "requests": [
            {"type": "execute", "stmt": stmt},
            {"type": "close"}
        ]
    }

    resp = requests.post(pipeline_url, json=payload, headers=headers, timeout=20)
    if resp.status_code != 200:
        raise RuntimeError(f"Turso API HTTP {resp.status_code}: {resp.text}")

    data = resp.json()
    first_res = data.get("results", [{}])[0]
    if first_res.get("type") == "error":
        err_msg = first_res.get("error", {}).get("message", "Unknown Turso error")
        raise RuntimeError(f"Turso SQL execution error: {err_msg}")

    inner_resp = first_res.get("response", {})
    inner_result = inner_resp.get("result", {})
    return _parse_result(inner_result)


def execute_batch(statements: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    pipeline_url, token = get_turso_config()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

    requests_payload = []
    for s in statements:
        stmt: Dict[str, Any] = {"sql": s["sql"]}
        if s.get("args"):
            stmt["args"] = [_encode_arg(a) for a in s["args"]]
        requests_payload.append({"type": "execute", "stmt": stmt})
    requests_payload.append({"type": "close"})

    payload = {"requests": requests_payload}
    resp = requests.post(pipeline_url, json=payload, headers=headers, timeout=30)
    if resp.status_code != 200:
        raise RuntimeError(f"Turso API HTTP {resp.status_code}: {resp.text}")

    data = resp.json()
    parsed_results = []
    for res in data.get("results", [])[:-1]:
        if res.get("type") == "error":
            err_msg = res.get("error", {}).get("message", "Unknown Turso batch error")
            raise RuntimeError(f"Turso batch SQL execution error: {err_msg}")
        inner = res.get("response", {}).get("result", {})
        parsed_results.append(_parse_result(inner))

    return parsed_results


def init_schema():
    """Create categories, topics, and published_runs tables idempotently."""
    ddl_statements = [
        """
        CREATE TABLE IF NOT EXISTS categories (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS topics (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            category_id TEXT,
            historical_era TEXT,
            core_anomaly TEXT,
            hook_hookline TEXT,
            key_facts TEXT,
            visual_motifs TEXT,
            status TEXT DEFAULT 'unclaimed',
            claimed_by TEXT,
            claimed_at DATETIME,
            completed_at DATETIME,
            FOREIGN KEY(category_id) REFERENCES categories(id)
        );
        """,
        """
        CREATE TABLE IF NOT EXISTS published_runs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id TEXT,
            engine TEXT,
            postable BOOLEAN,
            drive_folder_id TEXT,
            telegram_message_id TEXT,
            run_duration_sec REAL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(topic_id) REFERENCES topics(id)
        );
        """
    ]
    for ddl in ddl_statements:
        execute(ddl.strip())


def seed_categories():
    """Seed standard categories if they don't already exist."""
    categories = [
        ("tactical_anomaly", "Tactical Anomaly", "Unorthodox battle maneuvers, psychological warfare, and deceptive stratagems."),
        ("siege_engine", "Siege Engine & Superweapons", "Extreme siege machinery, fortified assault tools, and ancient super-weapons."),
        ("bizarre_invention", "Bizarre Invention & Naval Tech", "Unconventional prototypes, incendiary devices, and specialized military technology.")
    ]
    for cat_id, name, desc in categories:
        execute(
            "INSERT OR IGNORE INTO categories (id, name, description) VALUES (?, ?, ?);",
            [cat_id, name, desc]
        )


def seed_topics_from_catalog(catalog: List[Dict[str, Any]]):
    """Seed topics into the topics table without overwriting existing state."""
    for t in catalog:
        t_id = t["id"]
        title = t["title"]
        cat_id = t.get("category", "tactical_anomaly")
        era = t.get("historical_era", "")
        core_anomaly = t.get("core_anomaly", "")
        hook = t.get("hook_hookline", "")
        key_facts = json.dumps(t.get("key_facts", []))
        visual_motifs = json.dumps(t.get("visual_motifs", []))

        execute(
            """
            INSERT OR IGNORE INTO topics (
                id, title, category_id, historical_era, core_anomaly,
                hook_hookline, key_facts, visual_motifs, status
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'unclaimed');
            """,
            [t_id, title, cat_id, era, core_anomaly, hook, key_facts, visual_motifs]
        )


def claim_next_topic(runner_id: str) -> Optional[Dict[str, Any]]:
    """
    Atomically claims a single unclaimed topic for this runner.
    Uses UPDATE ... WHERE id = (SELECT id FROM topics WHERE status = 'unclaimed' ORDER BY RANDOM() LIMIT 1) RETURNING *
    Returns the claimed topic row dictionary, or None if no unclaimed topics remain.
    """
    sql = """
    UPDATE topics
    SET status = 'claimed',
        claimed_by = ?,
        claimed_at = CURRENT_TIMESTAMP
    WHERE id = (
        SELECT id FROM topics
        WHERE status = 'unclaimed'
        ORDER BY RANDOM()
        LIMIT 1
    )
    RETURNING *;
    """
    res = execute(sql, [runner_id])
    rows = res.get("rows", [])
    if not rows:
        return None

    row = rows[0]
    # Parse JSON fields if string
    for json_col in ["key_facts", "visual_motifs"]:
        val = row.get(json_col)
        if isinstance(val, str):
            try:
                row[json_col] = json.loads(val)
            except Exception:
                pass
    return row


def mark_topic_completed(topic_id: str):
    """Mark a claimed topic as successfully completed."""
    execute(
        """
        UPDATE topics
        SET status = 'completed',
            completed_at = CURRENT_TIMESTAMP
        WHERE id = ?;
        """,
        [topic_id]
    )


def mark_topic_failed(topic_id: str):
    """Mark a claimed topic as failed so it can be audited or retried."""
    execute(
        """
        UPDATE topics
        SET status = 'failed'
        WHERE id = ?;
        """,
        [topic_id]
    )


def reset_topic_unclaimed(topic_id: str):
    """Reset a topic back to unclaimed state."""
    execute(
        """
        UPDATE topics
        SET status = 'unclaimed',
            claimed_by = NULL,
            claimed_at = NULL,
            completed_at = NULL
        WHERE id = ?;
        """,
        [topic_id]
    )


def record_published_run(
    topic_id: str,
    engine: str,
    postable: bool,
    drive_folder_id: Optional[str],
    telegram_message_id: Optional[str],
    run_duration_sec: float
) -> int:
    """Record a completed or attempted pipeline run into published_runs."""
    sql = """
    INSERT INTO published_runs (
        topic_id, engine, postable, drive_folder_id, telegram_message_id, run_duration_sec
    ) VALUES (?, ?, ?, ?, ?, ?)
    RETURNING id;
    """
    res = execute(sql, [
        topic_id, engine, postable, drive_folder_id, str(telegram_message_id) if telegram_message_id else None, run_duration_sec
    ])
    rows = res.get("rows", [])
    if rows and "id" in rows[0]:
        return int(rows[0]["id"])
    return res.get("last_insert_rowid") or 0


def get_schema() -> List[Dict[str, Any]]:
    """Retrieve the current schema of user tables and views from SQLite master."""
    sql = "SELECT name, type, sql FROM sqlite_master WHERE type IN ('table', 'view') AND name NOT LIKE 'sqlite_%' ORDER BY name;"
    res = execute(sql)
    return res.get("rows", [])


def get_topics(status: Optional[str] = None) -> List[Dict[str, Any]]:
    """List topics, optionally filtered by status."""
    if status:
        res = execute("SELECT * FROM topics WHERE status = ? ORDER BY id;", [status])
    else:
        res = execute("SELECT * FROM topics ORDER BY id;")
    return res.get("rows", [])


def get_published_runs(limit: int = 10) -> List[Dict[str, Any]]:
    """List most recent published runs."""
    res = execute(f"SELECT * FROM published_runs ORDER BY id DESC LIMIT {int(limit)};")
    return res.get("rows", [])
