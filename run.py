"""CLI entry point for toronto-streets-osm.

Subcommands:
  download         TCL GeoJSON download (HEAD-cache by Last-Modified date)
  refresh-osm      Geofabrik PBF + filter to highway=*
  compare          TCL vs OSM bucketing -> data/compare.json + docs/index.html
  update           download + refresh-osm + compare + auto-push docs/
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from src import config
from src.download import download
from src import compare as _compare
from src import geometry as _geometry
from src.report import render as render_streets


def cmd_download(args):
    status, data, _headers = download(force=args.force)
    if status == "SKIPPED":
        print(f"Skipped: {data}")
    else:
        print(f"GeoJSON ready: {data}")


def cmd_refresh_osm(args):
    from src import osm_refresh
    osm_refresh.run(force=args.force, dry_run=args.dry_run, rebuild=args.rebuild)


def cmd_compare(args):
    if not os.path.exists(config.OSM_STREETS_JSON):
        print(f"Missing {config.OSM_STREETS_JSON}. Run 'refresh-osm' first.")
        return
    if not _compare._latest_tcl_file():
        print("No TCL GeoJSON in data/tcl/. Run 'download' first.")
        return
    result = _compare.regenerate()
    t = result["totals"]
    print(f"missing={t['missing']} extra={t['extra']} matched={t['matched']} "
          f"(tcl_streets={t['tcl_streets']} osm_streets={t['osm_streets']})")
    _geometry.build_sidecar(result)
    render_streets(result)


def cmd_update(args):
    print("=== Download ===")
    cmd_download(args)
    print()
    print("=== OSM refresh ===")
    from src import osm_refresh
    try:
        osm_refresh.run(force=False, dry_run=False, rebuild=False)
    except Exception as e:
        print(f"OSM refresh failed: {e}")
        return
    print()
    print("=== Compare ===")
    cmd_compare(args)
    print()
    print("=== Git Commit & Push ===")
    _autopush_docs()


def _autopush_docs():
    """Stage docs/, commit, push. Silent no-op when there's nothing to commit."""
    import subprocess
    from datetime import date

    today = date.today().isoformat()
    subprocess.run(["git", "add", "docs/"], check=False)
    result = subprocess.run(
        ["git", "commit", "-m", f"data {today}"],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        print(result.stdout.strip())
        push = subprocess.run(["git", "push"], capture_output=True, text=True)
        if push.returncode == 0:
            print("Changes pushed.")
        else:
            print(f"Push failed: {push.stderr.strip()}")
    else:
        print("Nothing to commit.")


def main():
    parser = argparse.ArgumentParser(description="Toronto streets vs OSM")
    sub = parser.add_subparsers(dest="command")

    dl = sub.add_parser("download", help="Download today's TCL GeoJSON")
    dl.add_argument("--force", action="store_true")

    osm = sub.add_parser("refresh-osm", help="Download Geofabrik PBF + filter highway=*")
    osm.add_argument("--force", action="store_true")
    osm.add_argument("--dry-run", action="store_true")
    osm.add_argument("--rebuild", action="store_true")

    sub.add_parser("compare", help="TCL vs OSM streets bucketing")

    up = sub.add_parser("update", help="download + refresh-osm + compare + push docs")
    up.add_argument("--force", action="store_true")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return

    handlers = {
        "download": cmd_download,
        "refresh-osm": cmd_refresh_osm,
        "compare": cmd_compare,
        "update": cmd_update,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
