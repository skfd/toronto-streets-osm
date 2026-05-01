"""Diff two snapshots to find added, removed, and modified TCL segments."""

import sqlite3

from src import config
from src.db import COMPARE_COLUMNS

DB_PATH = config.DB_PATH


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def compute_diff(old_snapshot_id: int, new_snapshot_id: int) -> dict:
    """Diff two snapshots by centreline_id. Returns {added, removed, modified}."""
    conn = _connect()

    added = conn.execute("""
        SELECT n.* FROM streets n
        WHERE n.min_snapshot_id <= ? AND n.max_snapshot_id >= ?
          AND NOT EXISTS (
            SELECT 1 FROM streets o
            WHERE o.centreline_id = n.centreline_id
              AND o.min_snapshot_id <= ? AND o.max_snapshot_id >= ?
          )
    """, (new_snapshot_id, new_snapshot_id, old_snapshot_id, old_snapshot_id)).fetchall()

    removed = conn.execute("""
        SELECT o.* FROM streets o
        WHERE o.min_snapshot_id <= ? AND o.max_snapshot_id >= ?
          AND NOT EXISTS (
            SELECT 1 FROM streets n
            WHERE n.centreline_id = o.centreline_id
              AND n.min_snapshot_id <= ? AND n.max_snapshot_id >= ?
          )
    """, (old_snapshot_id, old_snapshot_id, new_snapshot_id, new_snapshot_id)).fetchall()

    modified_rows = conn.execute(f"""
        SELECT o.centreline_id,
               {', '.join(f'o.{c} AS old_{c}' for c in COMPARE_COLUMNS)},
               {', '.join(f'n.{c} AS new_{c}' for c in COMPARE_COLUMNS)}
        FROM streets o
        JOIN streets n ON n.centreline_id = o.centreline_id
        WHERE o.min_snapshot_id <= ? AND o.max_snapshot_id >= ?
          AND n.min_snapshot_id <= ? AND n.max_snapshot_id >= ?
          AND o.min_snapshot_id != n.min_snapshot_id
    """, (old_snapshot_id, old_snapshot_id, new_snapshot_id, new_snapshot_id)).fetchall()

    conn.close()

    modified = []
    for row in modified_rows:
        changes = []
        for col in COMPARE_COLUMNS:
            old_val = row[f"old_{col}"]
            new_val = row[f"new_{col}"]
            if _values_differ(old_val, new_val):
                changes.append({"field": col, "old": old_val, "new": new_val})
        if changes:
            modified.append({
                "centreline_id": row["centreline_id"],
                "linear_name_full": row["new_linear_name_full"] or row["old_linear_name_full"] or "",
                "feature_code_desc": row["new_feature_code_desc"] or row["old_feature_code_desc"] or "",
                "changes": changes,
            })

    return {
        "old_snapshot_id": old_snapshot_id,
        "new_snapshot_id": new_snapshot_id,
        "added": [dict(r) for r in added],
        "removed": [dict(r) for r in removed],
        "modified": modified,
    }


def _values_differ(a, b):
    if a is None and b is None:
        return False
    if (a == 0 and b is None) or (a is None and b == 0):
        return False
    if a is None or b is None:
        return True
    return str(a) != str(b)
