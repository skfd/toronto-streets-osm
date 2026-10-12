"""CLI entry point for toronto-streets-osm.

Subcommands:
  download         TCL GeoJSON download (HEAD-cache by Last-Modified date)
  refresh-osm      Geofabrik PBF + filter to highway=*
  compare          TCL vs OSM bucketing -> data/compare.json + docs/index.html
                   (+ the extract's row in docs/history.jsonl -> docs/history.html)
  backfill         Rebuild past history rows from the pages committed to git
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
from src import history
from src.report import render as render_streets, render_history


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
    row = history.record(result)
    t = result["totals"]
    print(f"missing={t['missing']} extra={t['extra']} matched={t['matched']} "
          f"(tcl_streets={t['tcl_streets']} osm_streets={t['osm_streets']})")
    _geometry.build_sidecar(result)
    render_streets(result)
    render_history()
    return row["date"]


def cmd_backfill(args):
    added = history.backfill()
    print(f"Added {added} row(s) to {config.HISTORY_PATH}")
    render_history()


def cmd_update(args):
    """The scheduled entry point. Any step that fails ends the run with exit
    code 1 and an ERROR line, so Task Scheduler sees the failure and retries
    instead of logging a month with no comparison as a success."""
    from src import osm_refresh

    steps = (
        ("Download", lambda: cmd_download(args)),
        ("OSM refresh", lambda: osm_refresh.run(force=False, dry_run=False, rebuild=False)),
        ("Compare", lambda: cmd_compare(args)),
    )
    for name, step in steps:
        print(f"=== {name} ===")
        try:
            day = step()  # the last step, compare, returns its row's date
        except Exception as e:
            _fail(f"{name} failed: {e!r}")
        print()
    if day is None:  # compare found no input and recorded nothing
        _fail("Compare recorded no history row")
    print("=== Git Commit & Push ===")
    _autopush_docs(day)


def _fail(msg):
    from datetime import datetime
    stamp = datetime.now().isoformat(timespec="seconds")
    print(f"ERROR [{stamp}] update: {msg}", file=sys.stderr, flush=True)
    sys.exit(1)


def _autopush_docs(day=None):
    """Stage docs/, commit as "data <day>", push. A no-op when there's nothing
    to commit; a failed commit or push ends the run with exit code 1. The day
    is the history row's -- the OSM extract's -- so the commit and the point
    it adds to the chart carry the same date."""
    import subprocess
    from datetime import date

    day = day or date.today().isoformat()
    subprocess.run(["git", "add", "docs/"], check=False)
    if subprocess.run(["git", "diff", "--cached", "--quiet", "--", "docs/"]).returncode == 0:
        print("Nothing to commit.")
        return
    result = subprocess.run(
        ["git", "commit", "-m", f"data {day}"],
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        _fail(f"git commit failed: {(result.stderr or result.stdout).strip()}")
    print(result.stdout.strip())
    push = subprocess.run(["git", "push"], capture_output=True, text=True)
    if push.returncode != 0:
        _fail(f"git push failed: {push.stderr.strip()}")
    print("Changes pushed.")


def main():
    parser = argparse.ArgumentParser(description="Toronto streets vs OSM")
    sub = parser.add_subparsers(dest="command")

    dl = sub.add_parser("download", help="Download today's TCL GeoJSON")
    dl.add_argument("--force", action="store_true")

    osm = sub.add_parser("refresh-osm", help="Fetch the shared Geofabrik PBF + filter highway=*")
    osm.add_argument("--force", action="store_true")
    osm.add_argument("--dry-run", action="store_true")
    osm.add_argument("--rebuild", action="store_true")

    sub.add_parser("compare", help="TCL vs OSM streets bucketing")

    up = sub.add_parser("update", help="download + refresh-osm + compare + push docs")
    up.add_argument("--force", action="store_true")

    sub.add_parser("backfill", help="Rebuild past history rows from committed pages")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return

    handlers = {
        "download": cmd_download,
        "refresh-osm": cmd_refresh_osm,
        "compare": cmd_compare,
        "update": cmd_update,
        "backfill": cmd_backfill,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
