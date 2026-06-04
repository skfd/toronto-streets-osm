"""TCL vs OSM streets comparison: bucket every street into missing/extra/matched.

Source side: every TCL feature in the latest GeoJSON file under data/tcl/,
grouped by `normalize_street(LINEAR_NAME_FULL)` -- count of segments + sample
raw name + feature class.

OSM side: every named highway way in `data/osm/toronto-streets.json`, grouped
by `normalize_street(name)` -- count of ways + sample raw name + highway type.

Bucket rules:
    missing: TCL has the street, OSM does not.
    extra:   OSM has the street, TCL does not.
    matched: both sides have it (both raws + both counts shown).
"""
from __future__ import annotations

import json
import os
from collections import defaultdict
from datetime import datetime, timezone

from src import config, osm_refresh
from src.normalize import normalize_street


def _latest_tcl_file() -> str | None:
    if not os.path.isdir(config.TCL_DIR):
        return None
    files = sorted(f for f in os.listdir(config.TCL_DIR) if f.endswith(".geojson"))
    if not files:
        return None
    return os.path.join(config.TCL_DIR, files[-1])


def _tcl_streets() -> dict[str, dict]:
    path = _latest_tcl_file()
    if not path:
        raise FileNotFoundError(
            "No TCL GeoJSON in data/tcl/. Run `python run.py download` first."
        )
    counts: dict[str, int] = defaultdict(int)
    raws: dict[str, str] = {}
    feature_descs: dict[str, str] = {}
    jurisdictions: dict[str, str] = {}
    keep_codes = config.TCL_FEATURE_CODES
    for feat in _iter_features(path):
        props = feat.get("properties") or {}
        if props.get("FEATURE_CODE_DESC") not in keep_codes:
            continue
        raw = (props.get("LINEAR_NAME_FULL") or "").strip()
        if not raw:
            continue
        norm = normalize_street(raw)
        if not norm:
            continue
        counts[norm] += 1
        raws.setdefault(norm, raw)
        feature_descs.setdefault(norm, props["FEATURE_CODE_DESC"])
        jurisdictions.setdefault(norm, props.get("JURISDICTION") or "")
    return {
        norm: {
            "raw": raws[norm],
            "count": n,
            "feature_desc": feature_descs.get(norm),
            "jurisdiction": jurisdictions.get(norm),
        }
        for norm, n in counts.items()
    }


def _iter_features(path: str):
    """Yield Features from either a single FeatureCollection JSON or NDJSON."""
    with open(path, "r", encoding="utf-8") as f:
        try:
            data = json.load(f)
            for feat in data.get("features") or []:
                yield feat
            return
        except json.JSONDecodeError:
            pass
    import re
    with open(path, "r", encoding="utf-8") as f:
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


def _choose_osm_bucket(tags: dict, tcl_norms: set[str]) -> tuple[str, str, str] | None:
    """Pick the (norm, source, raw) bucket for one OSM way.

    A way belongs to one bucket. Prefer the primary `name`; only when that
    name doesn't appear in TCL do we look at `alt_name` (OSM-convention
    `;`-separated) for a salvage match against TCL. If nothing salvages,
    fall back to the primary `name` so the way still surfaces as Extra.
    Returns None when neither tag normalizes to anything.
    """
    name_raw = (tags.get("name") or "").strip()
    alt_raw = (tags.get("alt_name") or "").strip()
    primary_norm = normalize_street(name_raw) if name_raw else ""
    if primary_norm and primary_norm in tcl_norms:
        return (primary_norm, "name", name_raw)
    if alt_raw:
        for piece in alt_raw.split(";"):
            piece = piece.strip()
            if not piece:
                continue
            a = normalize_street(piece)
            if a and a in tcl_norms:
                return (a, "alt_name", piece)
    if primary_norm:
        return (primary_norm, "name", name_raw)
    return None


def _osm_streets(tcl_norms: set[str]) -> dict[str, dict]:
    """Bucket OSM ways by normalized street name. Each way contributes to a
    single bucket -- see `_choose_osm_bucket`. `via` records whether the
    bucket was reached via `name` (the default) or via an `alt_name` salvage."""
    if not os.path.exists(config.OSM_STREETS_JSON):
        raise FileNotFoundError(
            f"{config.OSM_STREETS_JSON} missing; run `python run.py refresh-osm` first."
        )
    elements = json.loads(open(config.OSM_STREETS_JSON, "r", encoding="utf-8").read())
    counts: dict[str, int] = defaultdict(int)
    raws: dict[str, str] = {}
    highways: dict[str, str] = {}
    via: dict[str, str] = {}
    non_salvage: set[str] = set()
    salvage_types = config.OSM_SALVAGE_HIGHWAY_TYPES
    for el in elements:
        if el.get("type") != "way":
            continue
        tags = el.get("tags") or {}
        chosen = _choose_osm_bucket(tags, tcl_norms)
        if not chosen:
            continue
        norm, source, raw = chosen
        counts[norm] += 1
        raws.setdefault(norm, raw)
        if source == "name":
            via[norm] = "name"
        else:
            via.setdefault(norm, "alt_name")
        hw = tags.get("highway")
        if hw:
            highways.setdefault(norm, hw)
            if hw not in salvage_types:
                non_salvage.add(norm)
    out: dict[str, dict] = {}
    for norm, n in counts.items():
        # Salvage-only names (every contributing way is a salvage highway type,
        # e.g. unclassified) can confirm a TCL match but never stand alone as
        # Extra -- drop them when no TCL street shares the name.
        if norm not in non_salvage and norm not in tcl_norms:
            continue
        out[norm] = {
            "raw": raws[norm],
            "count": n,
            "highway": highways.get(norm),
            "via": via.get(norm, "name"),
        }
    return out


def compute() -> dict:
    tcl = _tcl_streets()
    osm = _osm_streets(tcl_norms=set(tcl.keys()))

    missing_all = [
        {"street_norm": k, "street_raw": v["raw"], "tcl_segments": v["count"],
         "feature_desc": v.get("feature_desc"),
         "jurisdiction": v.get("jurisdiction")}
        for k, v in tcl.items() if k not in osm
    ]
    _RAMP = {"Expressway Ramp", "Major Arterial Ramp"}
    _MAJOR = {"Expressway", "Major Arterial"}

    def _bucket(r):
        if r["street_raw"].startswith("Ln "):
            return "ln"
        if r.get("jurisdiction") == "PRIVATE":
            return "private"
        if r.get("feature_desc") in _RAMP:
            return "ramp"
        if r.get("feature_desc") in _MAJOR:
            return "major"
        return "missing"

    missing_ln = [r for r in missing_all if _bucket(r) == "ln"]
    missing_private = [r for r in missing_all if _bucket(r) == "private"]
    missing_ramp = [r for r in missing_all if _bucket(r) == "ramp"]
    missing_major = [r for r in missing_all if _bucket(r) == "major"]
    missing = [r for r in missing_all if _bucket(r) == "missing"]
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
            "osm_match_via": osm[k].get("via", "name"),
        }
        for k, v in tcl.items() if k in osm
    ]

    missing.sort(key=lambda r: (-r["tcl_segments"], r["street_norm"]))
    missing_ln.sort(key=lambda r: (-r["tcl_segments"], r["street_norm"]))
    missing_ramp.sort(key=lambda r: (-r["tcl_segments"], r["street_norm"]))
    missing_major.sort(key=lambda r: (-r["tcl_segments"], r["street_norm"]))
    missing_private.sort(key=lambda r: (-r["tcl_segments"], r["street_norm"]))
    extra.sort(key=lambda r: (-r["osm_ways"], r["street_norm"]))
    matched.sort(key=lambda r: (-(r["tcl_segments"] + r["osm_ways"]), r["street_norm"]))

    osm_meta = osm_refresh.read_meta() or {}
    tcl_path = _latest_tcl_file()
    tcl_filename = os.path.basename(tcl_path) if tcl_path else None

    return {
        "computed_at": datetime.now(timezone.utc).isoformat(),
        "tcl_filename": tcl_filename,
        "osm_extract_downloaded": osm_meta.get("downloaded_at"),
        "osm_extract_json_sha256": osm_meta.get("json_sha256"),
        "toronto_bbox": list(config.TORONTO_BBOX),
        "totals": {
            "tcl_streets": len(tcl),
            "osm_streets": len(osm),
            "missing": len(missing),
            "missing_ln": len(missing_ln),
            "missing_ramp": len(missing_ramp),
            "missing_major": len(missing_major),
            "missing_private": len(missing_private),
            "extra": len(extra),
            "matched": len(matched),
        },
        "missing": missing,
        "missing_ln": missing_ln,
        "missing_ramp": missing_ramp,
        "missing_major": missing_major,
        "missing_private": missing_private,
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
