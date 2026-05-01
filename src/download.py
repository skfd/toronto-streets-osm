"""Download Toronto Centreline (TCL) GeoJSON from the Open Data portal."""

import os
from datetime import date, datetime

import requests

from src import config
from src.db import get_last_snapshot_headers, init_db


def download(force: bool = False):
    """Fetch today's TCL GeoJSON.

    Returns (status, data, headers):
        status:  "DOWNLOADED" or "SKIPPED"
        data:    filepath (downloaded) or reason string (skipped)
        headers: {"Last-Modified", "Content-Length"} dict on download, else None
    """
    os.makedirs(config.TCL_DIR, exist_ok=True)

    print("Checking for updates...")
    try:
        head = requests.head(config.TCL_DATASET_URL, timeout=10, allow_redirects=True)
        head.raise_for_status()
        remote = {
            "Last-Modified": head.headers.get("Last-Modified"),
            "Content-Length": _parse_int(head.headers.get("Content-Length")),
        }
    except requests.RequestException as e:
        print(f"Warning: could not check remote headers: {e}")
        remote = {}

    if not force and remote:
        init_db()
        last = get_last_snapshot_headers()
        if last and (
            remote.get("Last-Modified") == last.get("remote_last_modified")
            and remote.get("Content-Length") == last.get("remote_content_length")
        ):
            return "SKIPPED", "Remote file has not changed since last download.", None

    file_date = date.today()
    if remote.get("Last-Modified"):
        try:
            lm = datetime.strptime(remote["Last-Modified"], "%a, %d %b %Y %H:%M:%S %Z")
            file_date = lm.date()
        except ValueError:
            pass

    filename = f"centreline-{file_date.isoformat()}.geojson"
    filepath = os.path.join(config.TCL_DIR, filename)

    if os.path.exists(filepath) and not force:
        print(f"Already downloaded: {filepath}")
        return "DOWNLOADED", filepath, remote

    print(f"Downloading to {filepath} ...")
    resp = requests.get(config.TCL_DATASET_URL, stream=True, timeout=300)
    resp.raise_for_status()

    final_headers = {
        "Last-Modified": resp.headers.get("Last-Modified"),
        "Content-Length": _parse_int(resp.headers.get("Content-Length")),
    }
    total = int(resp.headers.get("content-length", 0))
    written = 0
    chunk = 1024 * 256
    with open(filepath, "wb") as f:
        for blob in resp.iter_content(chunk_size=chunk):
            f.write(blob)
            written += len(blob)
            if total:
                pct = written * 100 // total
                print(f"\r  {written // (1024 * 1024)} / {total // (1024 * 1024)} MB ({pct}%)", end="", flush=True)
    print(f"\nDone: {filepath} ({written // (1024 * 1024)} MB)")
    return "DOWNLOADED", filepath, final_headers


def _parse_int(val):
    try:
        return int(val)
    except (ValueError, TypeError):
        return None
