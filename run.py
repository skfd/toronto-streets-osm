"""CLI entry point for toronto-streets-osm.

Subcommands:
  download         TCL GeoJSON download (HEAD-cache)
  refresh-osm      Geofabrik PBF + filter to highway=*
  import           GeoJSON -> SCD2 streets DB
  diff             show counts of added/removed/modified between latest two snapshots
  report           generate the latest TCL diff report HTML
  report-all       regenerate every historical TCL report
  compare          TCL vs OSM bucketing -> data/compare.json + compare-*.html
  update           download + import + report + refresh-osm + compare
  rebuild          delete DB and reimport everything in data/tcl/
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from src import config
from src.download import download
from src.db import (
    import_geojson, get_latest_snapshots, init_db, record_skipped_snapshot,
)
from src.diff import compute_diff
from src.report import generate_report, generate_compare_report, update_index


def cmd_download(args):
    status, data, _headers = download(force=args.force)
    if status == "SKIPPED":
        print(f"Skipped: {data}")
    else:
        print(f"GeoJSON ready: {data}")


def cmd_import(args):
    if args.file:
        import_geojson(args.file)
        return
    if not os.path.isdir(config.TCL_DIR):
        print("No data/tcl/ directory. Run 'download' first.")
        return
    files = sorted(f for f in os.listdir(config.TCL_DIR) if f.endswith(".geojson"))
    if not files:
        print("No GeoJSON files in data/tcl/. Run 'download' first.")
        return
    import_geojson(os.path.join(config.TCL_DIR, files[-1]))


def cmd_diff(args):
    init_db()
    snaps = get_latest_snapshots(2)
    if len(snaps) < 2:
        print("Need at least 2 snapshots to diff. Import more data first.")
        return None
    old, new = snaps[0], snaps[1]
    print(f"Diffing snapshot {old['id']} -> {new['id']} ...")
    result = compute_diff(old["id"], new["id"])
    print(f"  Added:    {len(result['added']):,}")
    print(f"  Removed:  {len(result['removed']):,}")
    print(f"  Modified: {len(result['modified']):,}")
    return result, old, new


def cmd_report(args):
    out = cmd_diff(args)
    if not out:
        return
    result, old, new = out
    generate_report(result, old, new)


def cmd_report_all(args):
    init_db()
    snaps = [s for s in get_latest_snapshots(9999) if not s.get("skipped")]
    if not snaps:
        print("No snapshots found.")
        return
    snaps.sort(key=lambda s: s["id"])
    for i in range(1, len(snaps)):
        old, new = snaps[i - 1], snaps[i]
        print(f"[{(new.get('downloaded') or '')[:10]}] diffing {old['id']} -> {new['id']} ...")
        result = compute_diff(old["id"], new["id"])
        generate_report(result, old, new)
    update_index()
    print("All reports regenerated.")


def cmd_refresh_osm(args):
    from src import osm_refresh
    osm_refresh.run(force=args.force, dry_run=args.dry_run, rebuild=args.rebuild)


def cmd_compare(args):
    from src import compare as _compare
    if not os.path.exists(config.OSM_STREETS_JSON):
        print(f"Missing {config.OSM_STREETS_JSON}. Run 'refresh-osm' first.")
        return
    if not os.path.exists(config.DB_PATH):
        print(f"Missing {config.DB_PATH}. Run 'download' + 'import' first.")
        return
    result = _compare.regenerate()
    t = result["totals"]
    print(f"missing={t['missing']} extra={t['extra']} matched={t['matched']} "
          f"(tcl_streets={t['tcl_streets']} osm_streets={t['osm_streets']})")
    generate_compare_report(result)


def cmd_update(args):
    print("=== Download ===")
    status, data, headers = download(force=args.force)
    if status == "SKIPPED":
        print(f"Skipped: {data}")
        record_skipped_snapshot("skipped-download", data)
    else:
        print()
        print("=== Import ===")
        import_geojson(data, headers=headers)
        print()
        print("=== TCL diff report ===")
        cmd_report(args)

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
    """Stage docs/, commit, and push. Silent no-op when there's nothing to commit."""
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


def cmd_rebuild(args):
    if os.path.exists(config.DB_PATH):
        print(f"Deleting existing database: {config.DB_PATH}")
        os.remove(config.DB_PATH)
        for suffix in ("-shm", "-wal"):
            extra = config.DB_PATH + suffix
            if os.path.exists(extra):
                os.remove(extra)
    if not os.path.isdir(config.TCL_DIR):
        print("No data/tcl/ directory found.")
        return
    files = sorted(f for f in os.listdir(config.TCL_DIR) if f.endswith(".geojson"))
    if not files:
        print("No GeoJSON files found in data/tcl/.")
        return
    print(f"Found {len(files)} snapshots to import. Rebuilding...")
    for fn in files:
        import_geojson(os.path.join(config.TCL_DIR, fn))
    print("Rebuild complete.")


def main():
    parser = argparse.ArgumentParser(description="Toronto streets vs OSM")
    sub = parser.add_subparsers(dest="command")

    dl = sub.add_parser("download", help="Download today's TCL GeoJSON")
    dl.add_argument("--force", action="store_true")

    imp = sub.add_parser("import", help="Import a TCL GeoJSON into the database")
    imp.add_argument("--file", help="Path to GeoJSON file (default: latest in data/tcl/)")

    sub.add_parser("diff", help="Show diff between latest two snapshots")
    sub.add_parser("report", help="Generate HTML report for latest diff")
    sub.add_parser("report-all", help="Regenerate every historical report")

    osm = sub.add_parser("refresh-osm", help="Download Geofabrik PBF + filter highway=*")
    osm.add_argument("--force", action="store_true")
    osm.add_argument("--dry-run", action="store_true")
    osm.add_argument("--rebuild", action="store_true")

    sub.add_parser("compare", help="TCL vs OSM streets bucketing")

    up = sub.add_parser("update", help="download + import + report + refresh-osm + compare")
    up.add_argument("--force", action="store_true")

    sub.add_parser("rebuild", help="Delete DB and reimport all GeoJSON in data/tcl/")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        return

    handlers = {
        "download": cmd_download,
        "import": cmd_import,
        "diff": cmd_diff,
        "report": cmd_report,
        "report-all": cmd_report_all,
        "refresh-osm": cmd_refresh_osm,
        "compare": cmd_compare,
        "update": cmd_update,
        "rebuild": cmd_rebuild,
    }
    handlers[args.command](args)


if __name__ == "__main__":
    main()
