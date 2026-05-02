"""Download a Geofabrik Ontario PBF and filter it to named highway ways.

Output:

  data/osm/ontario-latest.osm.pbf       raw PBF download
  data/osm/toronto-streets.json         filtered way list (Overpass-`out center;` shape)
  data/osm/meta.json                    source URL + timestamps + sha256 + counts
  data/osm/refresh.lock                 PID of the running refresh (only while running)
  data/osm/refresh.log                  stdout+stderr of the last refresh

Each kept way matches:
    highway in OSM_HIGHWAY_TYPES (drivable public roads, see config)
    AND name is set
    AND the way's bounding box intersects the Toronto bbox
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import requests

from src import boundary, config

_CHUNK = 1 << 20
_HTTP_TIMEOUT = 60


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


def _head(url: str) -> dict[str, str]:
    r = requests.head(url, allow_redirects=True, timeout=_HTTP_TIMEOUT)
    r.raise_for_status()
    return dict(r.headers)


def _download(url: str, dest: Path) -> tuple[str, int]:
    h = hashlib.sha256()
    total = 0
    next_log = 25 * _CHUNK
    tmp = dest.with_suffix(dest.suffix + ".partial")
    with requests.get(url, stream=True, timeout=_HTTP_TIMEOUT) as r:
        r.raise_for_status()
        size = int(r.headers.get("Content-Length") or 0)
        with tmp.open("wb") as f:
            for chunk in r.iter_content(chunk_size=_CHUNK):
                if not chunk:
                    continue
                f.write(chunk)
                h.update(chunk)
                total += len(chunk)
                if total >= next_log:
                    pct = f" ({100 * total // size}%)" if size else ""
                    _log(f"downloaded {total // (1 << 20)} MiB{pct}")
                    next_log += 25 * _CHUNK
    tmp.replace(dest)
    return h.hexdigest(), total


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
    keep_types = config.OSM_HIGHWAY_TYPES

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


def run(force: bool = False, dry_run: bool = False, rebuild: bool = False) -> dict:
    """Download (if needed) and filter the PBF. Returns the meta dict written to disk."""
    pbf = Path(config.OSM_PBF_PATH)
    json_out = Path(config.OSM_STREETS_JSON)
    meta_path = Path(config.OSM_META_PATH)
    lock = Path(config.OSM_LOCK_PATH)
    pbf.parent.mkdir(parents=True, exist_ok=True)

    if rebuild:
        if not pbf.exists():
            raise FileNotFoundError(f"--rebuild requires {pbf} to exist; run without --rebuild first.")
        prior = read_meta() or {}
        _acquire_lock(lock)
        t_start = time.monotonic()
        try:
            _log(f"rebuild: reusing {pbf} ({pbf.stat().st_size} bytes)")
            pbf_sha = prior.get("pbf_sha256") or _sha256_file(pbf)
            elements, counts = _filter(pbf, config.TORONTO_BBOX)
            body = json.dumps(elements)
            json_out.write_text(body, encoding="utf-8")
            json_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
            meta = {
                "source_url": prior.get("source_url", config.OSM_PBF_URL),
                "source_last_modified": prior.get("source_last_modified", ""),
                "source_bytes": prior.get("source_bytes", pbf.stat().st_size),
                "pbf_sha256": pbf_sha,
                "json_sha256": json_sha,
                "json_bytes": len(body),
                "element_counts": counts,
                "toronto_bbox": list(config.TORONTO_BBOX),
                "downloaded_at": prior.get("downloaded_at", _iso_now()),
                "rebuilt_at": _iso_now(),
                "total_duration_s": round(time.monotonic() - t_start, 2),
            }
            meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
            _log(f"wrote {json_out} (counts={counts})")
            return meta
        finally:
            _release_lock(lock)

    _log(f"HEAD {config.OSM_PBF_URL}")
    headers = _head(config.OSM_PBF_URL)
    source_last_modified = headers.get("Last-Modified", "")
    content_length = int(headers.get("Content-Length") or 0)
    _log(f"source last-modified: {source_last_modified or '(unknown)'} size: {content_length} bytes")

    prior = read_meta()
    unchanged = (
        prior is not None
        and prior.get("source_last_modified") == source_last_modified
        and json_out.exists()
    )

    if dry_run:
        _log(f"dry-run: would_download={not unchanged or force}")
        return {"would_download": (not unchanged) or force, "prior": prior}

    if unchanged and not force:
        _log("source unchanged since last refresh; skipping download (pass --force to override)")
        return prior or {}

    _acquire_lock(lock)
    t_start = time.monotonic()
    try:
        _log(f"downloading to {pbf}")
        pbf_sha, pbf_bytes = _download(config.OSM_PBF_URL, pbf)
        _log(f"downloaded {pbf_bytes} bytes, sha256 {pbf_sha[:16]}...")

        elements, counts = _filter(pbf, config.TORONTO_BBOX)
        body = json.dumps(elements)
        json_out.write_text(body, encoding="utf-8")
        json_sha = hashlib.sha256(body.encode("utf-8")).hexdigest()
        _log(f"wrote {json_out} (counts={counts})")

        meta = {
            "source_url": config.OSM_PBF_URL,
            "source_last_modified": source_last_modified,
            "source_bytes": pbf_bytes,
            "pbf_sha256": pbf_sha,
            "json_sha256": json_sha,
            "json_bytes": len(body),
            "element_counts": counts,
            "toronto_bbox": list(config.TORONTO_BBOX),
            "downloaded_at": _iso_now(),
            "total_duration_s": round(time.monotonic() - t_start, 2),
        }
        meta_path.write_text(json.dumps(meta, indent=2), encoding="utf-8")
        _log("done")
        return meta
    finally:
        _release_lock(lock)


def _cli() -> int:
    parser = argparse.ArgumentParser(
        prog="python -m src.osm_refresh",
        description="Download + filter Toronto streets from a Geofabrik Ontario PBF.",
    )
    parser.add_argument("--force", action="store_true",
                        help="Re-download even if Geofabrik Last-Modified is unchanged.")
    parser.add_argument("--dry-run", action="store_true",
                        help="Only HEAD-check the source; print what would happen.")
    parser.add_argument("--rebuild", action="store_true",
                        help="Re-filter the existing PBF (skip download).")
    args = parser.parse_args()
    try:
        run(force=args.force, dry_run=args.dry_run, rebuild=args.rebuild)
        return 0
    except Exception as e:
        _log(f"ERROR: {e!r}")
        return 1


if __name__ == "__main__":
    sys.exit(_cli())
