"""TCL vs OSM streets comparison: bucket every street into missing/extra/matched.

Source side: every active TCL segment (latest non-skipped snapshot) grouped by
`normalize_street(linear_name_full)` -- count of segments + sample raw name.

OSM side: every named highway way in `data/osm/toronto-streets.json` grouped by
`normalize_street(name)` -- count of ways + sample raw name.

Bucket rules (mirrors t2/streets.py):
    missing: TCL has the street, OSM does not.
    extra:   OSM has the street, TCL does not.
    matched: both sides have it (both raws + both counts shown).

Output: `data/compare.json` plus an HTML report under `docs/reports/`.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone

from src import config, db as _db, osm_refresh
from src.normalize import normalize_street


def _tcl_streets() -> dict[str, dict]:
    """Active-snapshot streets grouped by normalized name."""
    counts: dict[str, int] = defaultdict(int)
    raws: dict[str, str] = {}
    feature_descs: dict[str, str] = {}
    for row in _db.get_active_streets():
        raw = (row.get("linear_name_full") or "").strip()
        if not raw:
            continue
        norm = normalize_street(raw)
        if not norm:
            continue
        counts[norm] += 1
        raws.setdefault(norm, raw)
        if row.get("feature_code_desc"):
            feature_descs.setdefault(norm, row["feature_code_desc"])
    return {
        norm: {"raw": raws[norm], "count": n, "feature_desc": feature_descs.get(norm)}
        for norm, n in counts.items()
    }


def _osm_streets() -> dict[str, dict]:
    """Named highway ways grouped by normalized name."""
    if not os.path.exists(config.OSM_STREETS_JSON):
        raise FileNotFoundError(
            f"{config.OSM_STREETS_JSON} missing; run `python run.py refresh-osm` first."
        )
    elements = json.loads(open(config.OSM_STREETS_JSON, "r", encoding="utf-8").read())
    counts: dict[str, int] = defaultdict(int)
    raws: dict[str, str] = {}
    highways: dict[str, str] = {}
    for el in elements:
        if el.get("type") != "way":
            continue
        tags = el.get("tags") or {}
        raw = (tags.get("name") or "").strip()
        if not raw:
            continue
        norm = normalize_street(raw)
        if not norm:
            continue
        counts[norm] += 1
        raws.setdefault(norm, raw)
        if tags.get("highway"):
            highways.setdefault(norm, tags["highway"])
    return {
        norm: {"raw": raws[norm], "count": n, "highway": highways.get(norm)}
        for norm, n in counts.items()
    }


def compute() -> dict:
    tcl = _tcl_streets()
    osm = _osm_streets()

    missing = [
        {"street_norm": k, "street_raw": v["raw"], "tcl_segments": v["count"],
         "feature_desc": v.get("feature_desc")}
        for k, v in tcl.items() if k not in osm
    ]
    extra = [
        {"street_norm": k, "street_raw": v["raw"], "osm_ways": v["count"],
         "highway": v.get("highway")}
        for k, v in osm.items() if k not in tcl
    ]
    matched = [
        {
            "street_norm": k,
            "tcl_raw": v["raw"],
            "osm_raw": osm[k]["raw"],
            "tcl_segments": v["count"],
            "osm_ways": osm[k]["count"],
            "feature_desc": v.get("feature_desc"),
            "highway": osm[k].get("highway"),
        }
        for k, v in tcl.items() if k in osm
    ]

    missing.sort(key=lambda r: (-r["tcl_segments"], r["street_norm"]))
    extra.sort(key=lambda r: (-r["osm_ways"], r["street_norm"]))
    matched.sort(key=lambda r: (-(r["tcl_segments"] + r["osm_ways"]), r["street_norm"]))

    snaps = _db.get_latest_snapshots(1)
    snap = snaps[-1] if snaps else None
    osm_meta = osm_refresh.read_meta() or {}

    return {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "tcl_snapshot_id": snap["id"] if snap else None,
        "tcl_snapshot_filename": snap["filename"] if snap else None,
        "tcl_snapshot_downloaded": snap["downloaded"] if snap else None,
        "osm_extract_downloaded": osm_meta.get("downloaded_at"),
        "osm_extract_json_sha256": osm_meta.get("json_sha256"),
        "toronto_bbox": list(config.TORONTO_BBOX),
        "totals": {
            "tcl_streets": len(tcl),
            "osm_streets": len(osm),
            "missing": len(missing),
            "extra": len(extra),
            "matched": len(matched),
        },
        "missing": missing,
        "extra": extra,
        "matched": matched,
    }


def regenerate() -> dict:
    result = compute()
    os.makedirs(os.path.dirname(config.COMPARE_JSON_PATH), exist_ok=True)
    with open(config.COMPARE_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2)
    return result


def read() -> dict | None:
    if not os.path.exists(config.COMPARE_JSON_PATH):
        return None
    try:
        return json.loads(open(config.COMPARE_JSON_PATH, "r", encoding="utf-8").read())
    except Exception:
        return None
