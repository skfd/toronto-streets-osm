"""SQLite SCD2 store for Toronto Centreline (TCL) snapshots.

Schema mirrors the addresses-import shape: snapshots table + a streets table
where each row represents a TCL segment valid across a [min_snapshot_id,
max_snapshot_id] range. Unchanged segments extend their max on each import;
new or modified segments insert a fresh row.
"""

import json
import os
import sqlite3
from datetime import datetime

from src import config

DB_PATH = config.DB_PATH

# TCL columns we promote to real DB columns. The rest land in `extra` as JSON.
TRACKED_COLUMNS = [
    "CENTRELINE_ID",
    "LINEAR_NAME_ID",
    "LINEAR_NAME_FULL",
    "LINEAR_NAME",
    "LINEAR_NAME_TYPE",
    "LINEAR_NAME_DIR",
    "FEATURE_CODE",
    "FEATURE_CODE_DESC",
    "ONEWAY_DIR_CODE_DESC",
    "JURISDICTION",
]

# Compared during diff. Excludes the PK (centreline_id).
COMPARE_COLUMNS = [
    "linear_name_id",
    "linear_name_full",
    "linear_name",
    "linear_name_type",
    "linear_name_dir",
    "feature_code",
    "feature_code_desc",
    "oneway_dir_code_desc",
    "jurisdiction",
    "bbox_minlat",
    "bbox_minlon",
    "bbox_maxlat",
    "bbox_maxlon",
]


def _connect():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _connect()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS snapshots (
            id                      INTEGER PRIMARY KEY AUTOINCREMENT,
            downloaded              TEXT NOT NULL,
            row_count               INTEGER NOT NULL DEFAULT 0,
            filename                TEXT NOT NULL,
            remote_last_modified    TEXT,
            remote_content_length   INTEGER,
            skipped                 INTEGER DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS streets (
            min_snapshot_id     INTEGER NOT NULL REFERENCES snapshots(id),
            max_snapshot_id     INTEGER NOT NULL REFERENCES snapshots(id),
            centreline_id       INTEGER NOT NULL,
            linear_name_id      INTEGER,
            linear_name_full    TEXT,
            linear_name         TEXT,
            linear_name_type    TEXT,
            linear_name_dir     TEXT,
            feature_code        INTEGER,
            feature_code_desc   TEXT,
            oneway_dir_code_desc TEXT,
            jurisdiction        TEXT,
            bbox_minlat         REAL,
            bbox_minlon         REAL,
            bbox_maxlat         REAL,
            bbox_maxlon         REAL,
            extra               TEXT,
            PRIMARY KEY (centreline_id, min_snapshot_id)
        );

        CREATE INDEX IF NOT EXISTS idx_streets_active
            ON streets(max_snapshot_id, linear_name_full);

        CREATE INDEX IF NOT EXISTS idx_streets_validity
            ON streets(min_snapshot_id, max_snapshot_id);
    """)
    conn.commit()
    conn.close()


def _parse_int(val):
    if val is None or val == "" or val == "None":
        return None
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return None


def _parse_float(val):
    if val is None or val == "" or val == "None":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _clean_str(val):
    if val is None or val == "None" or val == "":
        return None
    return str(val).strip()


def _bbox_of_linestring(coords):
    """Return (minlat, minlon, maxlat, maxlon) for a LineString or MultiLineString.

    GeoJSON coords are [lon, lat]. Returns (None,)*4 on empty/malformed input.
    """
    lats = []
    lons = []

    def walk(c):
        if not c:
            return
        if isinstance(c[0], (int, float)):
            lons.append(c[0])
            lats.append(c[1])
        else:
            for sub in c:
                walk(sub)

    walk(coords)
    if not lats:
        return None, None, None, None
    return min(lats), min(lons), max(lats), max(lons)


def get_last_snapshot_headers():
    """Last-Modified / Content-Length of the most recent non-skipped snapshot."""
    init_db()
    conn = _connect()
    row = conn.execute(
        "SELECT remote_last_modified, remote_content_length "
        "FROM snapshots WHERE skipped = 0 ORDER BY id DESC LIMIT 1"
    ).fetchone()
    conn.close()
    return dict(row) if row else None


def record_skipped_snapshot(filename, reason):
    init_db()
    conn = _connect()
    existing = conn.execute(
        "SELECT id FROM snapshots WHERE filename = ? AND skipped = 1", (filename,)
    ).fetchone()
    if existing:
        conn.close()
        return
    conn.execute(
        "INSERT INTO snapshots (downloaded, row_count, filename, skipped) VALUES (?, 0, ?, 1)",
        (datetime.now().isoformat(), filename),
    )
    conn.commit()
    conn.close()
    print(f"Recorded skipped snapshot: {filename} ({reason})")


def import_geojson(filepath, headers=None):
    """Load a TCL GeoJSON file as a new snapshot using SCD2 delta logic."""
    init_db()
    conn = _connect()

    filename = os.path.basename(filepath)
    headers = headers or {}

    existing = conn.execute(
        "SELECT id FROM snapshots WHERE filename = ?", (filename,)
    ).fetchone()
    if existing:
        print(f"Already imported: {filename} (snapshot {existing['id']})")
        conn.close()
        return existing["id"]

    prev = conn.execute(
        "SELECT MAX(id) FROM snapshots WHERE skipped = 0"
    ).fetchone()[0]
    print(f"Importing {filename} (prev_snapshot={prev}) ...")

    cur = conn.execute(
        "INSERT INTO snapshots (downloaded, row_count, filename, "
        "remote_last_modified, remote_content_length) VALUES (?, 0, ?, ?, ?)",
        (
            datetime.now().isoformat(),
            filename,
            headers.get("Last-Modified"),
            headers.get("Content-Length"),
        ),
    )
    curr_id = cur.lastrowid

    # Staging mirrors the streets columns minus the snapshot range.
    conn.execute("DROP TABLE IF EXISTS staging_streets")
    conn.execute("""
        CREATE TEMPORARY TABLE staging_streets (
            centreline_id       INTEGER,
            linear_name_id      INTEGER,
            linear_name_full    TEXT,
            linear_name         TEXT,
            linear_name_type    TEXT,
            linear_name_dir     TEXT,
            feature_code        INTEGER,
            feature_code_desc   TEXT,
            oneway_dir_code_desc TEXT,
            jurisdiction        TEXT,
            bbox_minlat         REAL,
            bbox_minlon         REAL,
            bbox_maxlat         REAL,
            bbox_maxlon         REAL,
            extra               TEXT
        )
    """)

    col_names = [
        "centreline_id", "linear_name_id", "linear_name_full", "linear_name",
        "linear_name_type", "linear_name_dir", "feature_code", "feature_code_desc",
        "oneway_dir_code_desc", "jurisdiction",
        "bbox_minlat", "bbox_minlon", "bbox_maxlat", "bbox_maxlon", "extra",
    ]

    row_count = 0
    batch = []
    BATCH_SIZE = 5000

    with open(filepath, "r", encoding="utf-8") as f:
        # Toronto's GeoJSON files are typically a single FeatureCollection. Try
        # to load whole-file first; fall back to line-by-line for newline-delim
        # files (the addresses-import file is one Feature per line).
        try:
            data = json.load(f)
            features = data.get("features") or []
        except json.JSONDecodeError:
            f.seek(0)
            features = _iter_jsonl_features(f)

        for feat in features:
            props = feat.get("properties", {}) or {}
            geom = feat.get("geometry") or {}
            coords = geom.get("coordinates") or []
            cid = _parse_int(props.get("CENTRELINE_ID"))
            if cid is None:
                continue

            minlat, minlon, maxlat, maxlon = _bbox_of_linestring(coords)

            extra_keys = set(props.keys()) - set(TRACKED_COLUMNS) - {"_id"}
            extra = {k: props[k] for k in sorted(extra_keys) if props.get(k) is not None}

            batch.append((
                cid,
                _parse_int(props.get("LINEAR_NAME_ID")),
                _clean_str(props.get("LINEAR_NAME_FULL")),
                _clean_str(props.get("LINEAR_NAME")),
                _clean_str(props.get("LINEAR_NAME_TYPE")),
                _clean_str(props.get("LINEAR_NAME_DIR")),
                _parse_int(props.get("FEATURE_CODE")),
                _clean_str(props.get("FEATURE_CODE_DESC")),
                _clean_str(props.get("ONEWAY_DIR_CODE_DESC")),
                _clean_str(props.get("JURISDICTION")),
                minlat, minlon, maxlat, maxlon,
                json.dumps(extra) if extra else None,
            ))
            row_count += 1
            if len(batch) >= BATCH_SIZE:
                _insert_staging(conn, batch, col_names)
                batch = []
                if row_count % 50000 == 0:
                    print(f"  Buffered {row_count:,} rows ...")

    if batch:
        _insert_staging(conn, batch, col_names)

    conn.execute("CREATE INDEX idx_staging_id ON staging_streets(centreline_id)")

    if row_count == 0:
        print("ERROR: imported 0 rows. Aborting snapshot creation.")
        conn.close()
        raise ValueError("Import failed: 0 rows found in GeoJSON.")

    if prev is None:
        print("  First import: bulk inserting all rows...")
        cols_str = ", ".join(col_names)
        conn.execute(
            f"INSERT INTO streets (min_snapshot_id, max_snapshot_id, {cols_str}) "
            f"SELECT ?, ?, {cols_str} FROM staging_streets",
            (curr_id, curr_id),
        )
        inserted_count = row_count
    else:
        print("  Detecting changes...")
        compare_cols = col_names[1:]  # skip centreline_id
        match_clause = " AND ".join(f"(streets.{c} IS s.{c})" for c in compare_cols)

        upd = conn.execute(f"""
            UPDATE streets SET max_snapshot_id = ?
            WHERE max_snapshot_id = ?
              AND EXISTS (
                SELECT 1 FROM staging_streets s
                WHERE s.centreline_id = streets.centreline_id
                  AND {match_clause}
              )
        """, (curr_id, prev))
        print(f"  Unchanged: {upd.rowcount:,} (extended validity)")

        cols_str = ", ".join(col_names)
        ins = conn.execute(f"""
            INSERT INTO streets (min_snapshot_id, max_snapshot_id, {cols_str})
            SELECT ?, ?, {cols_str} FROM staging_streets s
            WHERE s.centreline_id NOT IN (
                SELECT centreline_id FROM streets WHERE max_snapshot_id = ?
            )
        """, (curr_id, curr_id, curr_id))
        inserted_count = ins.rowcount
        print(f"  New/Modified: {inserted_count:,}")

    if inserted_count == 0 and prev is not None:
        print(f"  No changes detected vs snapshot {prev}. Rolling back new snapshot.")
        conn.rollback()
        if headers.get("Last-Modified"):
            conn.execute(
                "UPDATE snapshots SET remote_last_modified = ?, remote_content_length = ? "
                "WHERE id = ?",
                (headers.get("Last-Modified"), headers.get("Content-Length"), prev),
            )
            conn.commit()
        conn.close()
        return prev

    conn.execute("UPDATE snapshots SET row_count = ? WHERE id = ?", (row_count, curr_id))
    conn.execute("DROP TABLE staging_streets")
    conn.commit()
    conn.close()
    print(f"Imported {row_count:,} segments as snapshot {curr_id}")
    return curr_id


def _iter_jsonl_features(f):
    """Yield Features from a newline-delimited GeoJSON file (one Feature per line)."""
    import re
    for line in f:
        line = line.strip().rstrip(",")
        if '"type": "Feature"' not in line:
            continue
        line = re.sub(r",\s*]", "]", line)
        line = re.sub(r",\s*}", "}", line)
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def _insert_staging(conn, batch, cols):
    placeholders = ", ".join(["?"] * len(cols))
    sql = f"INSERT INTO staging_streets ({', '.join(cols)}) VALUES ({placeholders})"
    conn.executemany(sql, batch)


def get_snapshots():
    conn = _connect()
    rows = conn.execute("SELECT * FROM snapshots ORDER BY downloaded").fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_latest_snapshots(n=2):
    """Return the last n non-skipped snapshots, oldest first."""
    conn = _connect()
    rows = conn.execute(
        "SELECT * FROM snapshots WHERE skipped = 0 ORDER BY downloaded DESC LIMIT ?",
        (n,),
    ).fetchall()
    conn.close()
    return [dict(r) for r in reversed(rows)]


def get_active_streets(snapshot_id=None):
    """Return all streets valid in the given snapshot (default: latest)."""
    conn = _connect()
    if snapshot_id is None:
        row = conn.execute(
            "SELECT MAX(id) FROM snapshots WHERE skipped = 0"
        ).fetchone()
        snapshot_id = row[0] if row else None
    if snapshot_id is None:
        conn.close()
        return []
    rows = conn.execute(
        "SELECT * FROM streets WHERE min_snapshot_id <= ? AND max_snapshot_id >= ?",
        (snapshot_id, snapshot_id),
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]
