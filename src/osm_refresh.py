"""Filter the shared Geofabrik Ontario PBF to named highway ways.

The PBF is not downloaded here. ~/Code/osm-extracts fetches it into the shared
store (config.OSM_DATA_DIR); this module runs that fetcher, reads
ontario/latest.json, and filters the dated file it names.

Output:

  data/osm/toronto-streets.json        filtered way list (Overpass-`out center;` shape)
  data/osm/meta.json                    source URL + timestamps + sha256 + counts
  data/osm/refresh.lock                 PID of the running refresh (only while running)
  data/osm/refresh.log                  stdout+stderr of the last refresh

Each kept way matches:
    highway in OSM_HIGHWAY_TYPES (drivable public roads + service, see config)
    AND name is set
    AND the way's bounding box intersects the Toronto bbox
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path

from src import boundary, config

_CHUNK = 1 << 20


def _iso_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_meta() -> dict | None:
    p = Path(config.OSM_META_PATH)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def is_refresh_running() -> tuple[bool, int | None]:
    lock = Path(config.OSM_LOCK_PATH)
    if not lock.exists():
        return False, None
    try:
        pid = int(lock.read_text(encoding="utf-8").strip())
    except Exception:
        return False, None
    return (_pid_alive(pid), pid)


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            import ctypes

            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            h = ctypes.windll.kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not h:
                return False
            ctypes.windll.kernel32.CloseHandle(h)
            return True
        except Exception:
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def _log(msg: str) -> None:
    print(f"[{_iso_now()}] {msg}", flush=True)


def _bounds_intersect(b: dict, bbox: tuple[float, float, float, float]) -> bool:
    return (
        b["minlat"] <= bbox[2]
        and b["maxlat"] >= bbox[0]
        and b["minlon"] <= bbox[3]
        and b["maxlon"] >= bbox[1]
    )


def _filter(pbf_path: Path, bbox: tuple[float, float, float, float]) -> tuple[list[dict], dict[str, int]]:
    """Single pyosmium pass over the PBF -- keeps named highway ways whose
    centroid lies inside the City of Toronto polygon.

    Output shape per way matches Overpass `out center;`:
        {"type": "way", "id": N, "tags": {...},
         "bounds": {"minlat": .., "minlon": .., "maxlat": .., "maxlon": ..},
         "center": {"lat": ..., "lon": ...}}
    """
    import osmium  # imported lazily so the install can succeed without osmium for tests

    polygons = boundary.load()  # [(bbox, rings), ...]
    elements: list[dict] = []
    counts = {
        "ways_seen": 0, "ways_kept": 0,
        "outside_bbox": 0, "outside_city": 0,
        "no_name": 0, "wrong_type": 0,
    }
    keep_types = config.OSM_EXTRACT_HIGHWAY_TYPES

    class Handler(osmium.SimpleHandler):
        def way(self, w):
            tags = w.tags
            if "highway" not in tags:
                return
            counts["ways_seen"] += 1
            if tags.get("highway") not in keep_types:
                counts["wrong_type"] += 1
                return
            if "name" not in tags:
                counts["no_name"] += 1
                return
            lats: list[float] = []
            lons: list[float] = []
            for wn in w.nodes:
                if wn.location.valid():
                    lats.append(wn.location.lat)
                    lons.append(wn.location.lon)
            if not lats:
                return
            b = {
                "minlat": min(lats), "minlon": min(lons),
                "maxlat": max(lats), "maxlon": max(lons),
            }
            if not _bounds_intersect(b, bbox):
                counts["outside_bbox"] += 1
                return
            clat = (b["minlat"] + b["maxlat"]) / 2
            clon = (b["minlon"] + b["maxlon"]) / 2
            if not boundary.is_inside(clat, clon, polygons):
                counts["outside_city"] += 1
                return
            elements.append({
                "type": "way",
                "id": w.id,
                "tags": {t.k: t.v for t in tags},
                "bounds": b,
                "center": {"lat": clat, "lon": clon},
                "geometry": [[round(lon, 5), round(lat, 5)] for lat, lon in zip(lats, lons)],
            })
            counts["ways_kept"] += 1

    Handler().apply_file(str(pbf_path), locations=True)
    return elements, counts


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(_CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def _acquire_lock(lock: Path) -> None:
    lock.parent.mkdir(parents=True, exist_ok=True)
    if lock.exists():
        try:
            pid = int(lock.read_text(encoding="utf-8").strip())
        except Exception:
            pid = -1
        if _pid_alive(pid):
            raise RuntimeError(f"refresh already running (pid {pid}); remove {lock} if stale")
        _log(f"clearing stale lock (pid {pid} not alive)")
        lock.unlink(missing_ok=True)
    lock.write_text(str(os.getpid()), encoding="utf-8")


def _release_lock(lock: Path) -> None:
    try:
        lock.unlink(missing_ok=True)
    except Exception:
        pass


def _fetch() -> None:
    """Let osm-extracts refresh the store. It HEAD-checks Geofabrik and only
    downloads a changed extract, so this is cheap on a day with nothing new."""
    _log(f"fetch: {config.OSM_EXTRACTS_TOOL} fetch {config.OSM_REGION}")
    rc = subprocess.run([sys.executable, config.OSM_EXTRACTS_TOOL, "fetch", config.OSM_REGION]).returncode
    if rc != 0:
        raise RuntimeError(f"osm-extracts fetch {config.OSM_REGION} exited {rc}")


def _read_latest() -> dict:
    p = Path(config.OSM_LATEST_JSON)
    if not p.exists():
        raise FileNotFoundError(
            f"no {p}; run: python {config.OSM_EXTRACTS_TOOL} fetch {config.OSM_REGION}")
    return json.loads(p.read_text(encoding="utf-8"))


def _extract_time(latest: dict) -> str:
    """When the extract's OSM data was taken, as an ISO stamp. Stored as
    meta's downloaded_at: compare shows it as the page's "OSM extract" stamp
    and history dates its row by it, so it must belong to the extract, not to
    the day this repo happened to filter it.

    The PBF's replication timestamp comes first: Geofabrik can publish a day
    after the data it holds (ontario-2026-10-10 went up 2026-10-11 21:43 GMT),
    and the store names the file by the data's day, not the upload's."""
    if latest.get("replication_timestamp"):
        return latest["replication_timestamp"]
    if latest.get("data_date"):
        return latest["data_date"]
    try:
        return parsedate_to_datetime(latest["source_last_modified"]).isoformat()
    except (KeyError, TypeError, ValueError):
        return latest.get("fetched_at") or _iso_now()


def run(force: bool = False, dry_run: bool = False, rebuild: bool = False) -> dict:
    """Refresh the shared extract (unless rebuild/dry_run) and filter it if it
    differs from the one last filtered. Returns the meta dict written to disk."""
    json_out = Path(config.OSM_STREETS_JSON)
    meta_path = Path(config.OSM_META_PATH)
    lock = Path(config.OSM_LOCK_PATH)
    json_out.parent.mkdir(parents=True, exist_ok=True)

    if dry_run:
        latest = _read_latest()
        prior = read_meta()
        unchanged = _same_extract(prior, latest) and json_out.exists()
        _log(f"dry-run: stored latest is {latest.get('file')}; would_filter={not unchanged or force}"
             " (the store itself is not checked against Geofabrik)")
        return {"would_filter": (not unchanged) or force, "prior": prior}

    _acquire_lock(lock)
    t_start = time.monotonic()
    try:
        if rebuild:
            _log("rebuild: skipping fetch, re-filtering the stored latest extract")
        else:
            _fetch()
        latest = _read_latest()
        pbf = Path(config.OSM_REGION_DIR) / latest["file"]
        _log(f"extract: {pbf} (Last-Modified {latest.get('source_last_modified') or '(unknown)'})")

        prior = read_meta()
        if not (force or rebuild) and _same_extract(prior, latest) and json_out.exists():
            _log("extract unchanged since last refresh; skipping filter (pass --force to override)")
            return prior or {}

        elements, counts = _filter(pbf, config.TORONTO_BBOX)
        body = json.dumps(elements)
        json_out.write_text(body, encoding="utf-8")
        json_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        _log(f"wrote {json_out} (counts={counts})")

        meta = {
            "source_url": latest.get("source_url"),
            "source_last_modified": latest.get("source_last_modified", ""),
            "source_bytes": latest.get("bytes") or pbf.stat().st_size,
            "pbf_file": latest["file"],
            "pbf_sha256": latest.get("sha256") or _sha256_file(pbf),
            "json_sha256": json_sha,
            "json_bytes": len(body),
            "element_counts": counts,
            "toronto_bbox": list(config.TORONTO_BBOX),
            "downloaded_at": _extract_time(latest),
            "filtered_at": _iso_now(),
            "total_duration_s": round(time.monotonic() - t_start, 2),
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        _log("done")
        return meta
    finally:
        _release_lock(lock)


def _same_extract(prior: dict | None, latest: dict) -> bool:
    return (
        prior is not None
        and prior.get("source_last_modified") == latest.get("source_last_modified")
        and prior.get("pbf_sha256") == latest.get("sha256")
    )

def _cli() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.osm_refresh",
        description="Filter Toronto streets from the shared Geofabrik Ontario PBF.",
    )
    parser.add_argument("--force", action="store_true",
                        help="Re-filter even if the extract is unchanged since the last refresh.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Don't fetch; say whether the stored extract would be filtered.")
    parser.add_argument("--rebuild", action="store_true",
                        help="Re-filter the stored latest extract (skip the fetch).")
    args = parser.parse_args()
    try:
        run(force=args.force, dry_run=args.dry_run, rebuild=args.rebuild)
        return 0
    except Exception as e:
        _log(f"ERROR: {e!r}")
        return 1


if __name__ == "__main__":
    sys.exit(_cli())
