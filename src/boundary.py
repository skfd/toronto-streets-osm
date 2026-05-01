"""City of Toronto boundary, used to clip the OSM extract.

The boundary comes from the City's 158-neighbourhood polygon layer (Open Data
package `neighbourhoods`). Their union *is* the city outline — same dataset the
sibling tile-builder uses. We don't dissolve the polygons; we just check
whether a point lies inside any of them, which is equivalent for membership.

Each polygon is stored as `(bbox, rings)` where:

  bbox  = (minlat, minlon, maxlat, maxlon)  -- cheap pre-filter
  rings = [outer, hole1, hole2, ...]        -- each ring = list of (lat, lon)

`is_inside(lat, lon, polygons)` returns True iff the point is inside any
polygon's outer ring AND not inside any of its holes.
"""
from __future__ import annotations

import json
import os

import requests

from src import config


def ensure_downloaded() -> str:
    """Fetch the neighbourhoods GeoJSON if it's not already on disk. Returns the path."""
    path = config.BOUNDARY_GEOJSON_PATH
    if os.path.exists(path):
        return path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    print(f"Downloading Toronto neighbourhoods boundary -> {path}")
    r = requests.get(config.BOUNDARY_URL, timeout=60)
    r.raise_for_status()
    with open(path, "wb") as f:
        f.write(r.content)
    return path


def load() -> list[tuple[tuple[float, float, float, float], list[list[tuple[float, float]]]]]:
    """Return [(bbox, rings), ...] for every neighbourhood polygon."""
    ensure_downloaded()
    data = json.loads(open(config.BOUNDARY_GEOJSON_PATH, "r", encoding="utf-8").read())
    out: list = []
    for feat in data.get("features") or []:
        geom = feat.get("geometry") or {}
        gtype = geom.get("type")
        coords = geom.get("coordinates") or []
        polygons: list = []
        if gtype == "Polygon":
            polygons.append(coords)
        elif gtype == "MultiPolygon":
            polygons.extend(coords)
        else:
            continue
        for poly in polygons:
            rings = [[(pt[1], pt[0]) for pt in ring] for ring in poly]
            lats = [p[0] for ring in rings for p in ring]
            lons = [p[1] for ring in rings for p in ring]
            if not lats:
                continue
            out.append(((min(lats), min(lons), max(lats), max(lons)), rings))
    return out


def is_inside(lat: float, lon: float, polygons) -> bool:
    for (minlat, minlon, maxlat, maxlon), rings in polygons:
        if not (minlat <= lat <= maxlat and minlon <= lon <= maxlon):
            continue
        if _point_in_polygon(lat, lon, rings):
            return True
    return False


def _point_in_polygon(lat: float, lon: float, rings) -> bool:
    """Inside outer ring, and not inside any hole."""
    if not rings:
        return False
    if not _point_in_ring(lat, lon, rings[0]):
        return False
    for hole in rings[1:]:
        if _point_in_ring(lat, lon, hole):
            return False
    return True


def _point_in_ring(lat: float, lon: float, ring) -> bool:
    """Standard ray-cast, treating x=lon, y=lat."""
    n = len(ring)
    if n < 3:
        return False
    inside = False
    j = n - 1
    for i in range(n):
        lat_i, lon_i = ring[i]
        lat_j, lon_j = ring[j]
        if (lat_i > lat) != (lat_j > lat):
            denom = lat_j - lat_i
            if denom != 0:
                x_at_lat = lon_i + (lat - lat_i) * (lon_j - lon_i) / denom
                if lon < x_at_lat:
                    inside = not inside
        j = i
    return inside
