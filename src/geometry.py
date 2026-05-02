"""Build the per-street polyline sidecar consumed by the report's map panel.

Output: `docs/streets-geom.json`, shape `{street_norm: [[[lon,lat], ...], ...]}`.
Only streets in the missing-or-extra buckets are included (matched is excluded
intentionally -- the map only previews single-sided streets).

Sources:
    missing -> latest TCL GeoJSON (data/tcl/centreline-*.geojson), filtered to
               the same FEATURE_CODE_DESC set used by the comparison.
    extra   -> data/osm/toronto-streets.json. Requires the `geometry` field on
               each way; run `python run.py refresh-osm --rebuild` after pulling
               this change to populate it.
"""
from __future__ import annotations

import json
import os
from collections import defaultdict

from src import compare, config
from src.normalize import normalize_street


def _round_polyline(coords) -> list[list[float]]:
    return [[round(float(lon), 5), round(float(lat), 5)] for lon, lat in coords]


def _tcl_geoms(missing_set: set[str]) -> dict[str, list[list[list[float]]]]:
    if not missing_set:
        return {}
    path = compare._latest_tcl_file()
    if not path:
        return {}
    keep_codes = config.TCL_FEATURE_CODES
    out: dict[str, list[list[list[float]]]] = defaultdict(list)
    for feat in compare._iter_features(path):
        props = feat.get("properties") or {}
        if props.get("FEATURE_CODE_DESC") not in keep_codes:
            continue
        norm = normalize_street(props.get("LINEAR_NAME_FULL"))
        if not norm or norm not in missing_set:
            continue
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates") or []
        if gtype == "LineString":
            if coords:
                out[norm].append(_round_polyline(coords))
        elif gtype == "MultiLineString":
            for line in coords:
                if line:
                    out[norm].append(_round_polyline(line))
    return out


def _osm_geoms(extra_set: set[str]) -> dict[str, list[list[list[float]]]]:
    if not extra_set:
        return {}
    if not os.path.exists(config.OSM_STREETS_JSON):
        return {}
    elements = json.loads(open(config.OSM_STREETS_JSON, "r", encoding="utf-8").read())
    out: dict[str, list[list[list[float]]]] = defaultdict(list)
    saw_geom = False
    for el in elements:
        if el.get("type") != "way":
            continue
        tags = el.get("tags") or {}
        norm = normalize_street(tags.get("name"))
        if not norm or norm not in extra_set:
            continue
        geom = el.get("geometry")
        if not geom:
            continue
        saw_geom = True
        out[norm].append([[float(lon), float(lat)] for lon, lat in geom])
    if not saw_geom:
        print(
            "warning: data/osm/toronto-streets.json has no `geometry` field; "
            "extra streets will not draw on the map. "
            "Run `python run.py refresh-osm --rebuild` to backfill."
        )
    return out


def build_sidecar(compare_data: dict) -> str:
    missing_set = {row["street_norm"] for row in compare_data.get("missing") or []}
    extra_set = {row["street_norm"] for row in compare_data.get("extra") or []}

    geoms: dict[str, list[list[list[float]]]] = {}
    geoms.update(_tcl_geoms(missing_set))
    geoms.update(_osm_geoms(extra_set))

    os.makedirs(config.DOCS_DIR, exist_ok=True)
    out_path = os.path.join(config.DOCS_DIR, "streets-geom.json")
    body = json.dumps(geoms, separators=(",", ":"))
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(body)
    print(f"Wrote {out_path} ({len(body):,} bytes, {len(geoms)} streets)")
    return out_path
