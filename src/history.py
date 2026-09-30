"""Keep the totals of every compare run, and rebuild the past from git.

Each compare writes one row to docs/history.jsonl: the date, the day the OSM
extract was taken, and the totals. A second compare on the same day replaces
that day's row, so the record holds one point per day. docs/ is committed by
`update`, so the record travels with the page and needs no other backup.

The past before the record began is recovered from the repo itself: every
commit that touched docs/index.html holds a rendered page with the totals in
its header and tab labels. ``backfill`` reads them, marks the rows "git", and
the history page shades those points as reconstructed.
"""

import json
import os
import re
import subprocess
from datetime import date, datetime

from src import config

FIELDS = ("missing", "extra", "missing_private", "missing_major", "missing_ln",
          "missing_ramp", "matched", "tcl_streets", "osm_streets")


def record(result, day=None):
    """Add today's row from a compare result, replacing an earlier one today."""
    day = day or date.today().isoformat()
    row = {"date": day,
           "osm_date": _local_date(result.get("osm_extract_downloaded")) or day,
           "source": "live",
           **{k: result["totals"][k] for k in FIELDS if k in result["totals"]}}
    rows = [r for r in load() if r["date"] != day] + [row]
    _write(rows)
    print(f"History: recorded {day} ({len(rows):,} runs on record).")
    return row


def load():
    """All rows, oldest first. An absent file is an empty history."""
    if not os.path.isfile(config.HISTORY_PATH):
        return []
    with open(config.HISTORY_PATH, encoding="utf-8") as f:
        rows = [json.loads(line) for line in f if line.strip()]
    return sorted(rows, key=lambda r: r["date"])


def backfill(pages=None):
    """Add rows for past dates from the pages committed to git.

    ``pages`` is (hash, commit date, html) oldest first; by default every
    commit that touched docs/index.html. Most of those are re-renders of the
    same data while the rules were being tuned, so rows are keyed by the data
    date and the last page for a date wins -- the one closest to today's
    rules. Dates already on record are skipped, so re-running adds nothing.
    Returns the number of rows added.
    """
    pages = _git_pages() if pages is None else pages
    by_date = {}
    for commit, commit_date, html in pages:
        row = parse_page(html, commit_date)
        if row is None:
            continue
        row["commit"] = commit
        by_date[row["date"]] = row
    have = {r["date"] for r in load()}
    new = [r for d, r in by_date.items() if d not in have]
    if new:
        _write(load() + new)
    for r in sorted(new, key=lambda r: r["date"]):
        print(f"History: {r['date']} from {r['commit']}: "
              f"missing={r.get('missing', '-')} extra={r.get('extra', '-')}")
    return len(new)


def parse_page(html, commit_date):
    """The row a rendered page states, or None if it shows no tab counts.

    Counts come from the tab buttons (`data-tab="missing-ln">Laneways (2255)`),
    whose data-tab names have stayed the totals keys while the labels changed.
    Fields a page predates are left out, not zeroed. The date is the local day
    the OSM extract was taken (the page's "Computed" stamp is render time,
    refreshed by cosmetic re-renders), else the commit date.
    """
    counts = {k.replace("-", "_"): int(n) for k, n in
              re.findall(r'data-tab="([\w-]+)">[^<(]*\((\d+)\)</button>', html)}
    if not counts:
        return None
    for key, label in (("tcl_streets", "TCL streets"), ("osm_streets", "OSM streets")):
        m = re.search(label + r" <strong>(\d+)</strong>", html)
        if m:
            counts[key] = int(m.group(1))
    m = re.search(r"OSM extract (\S+)", html)
    day = (m and _local_date(m.group(1))) or commit_date
    return {"date": day, "osm_date": day, "source": "git",
            **{k: counts[k] for k in FIELDS if k in counts}}


def _git_pages():
    def git(*args):
        return subprocess.run(["git", *args], cwd=config.ROOT, check=True,
                              capture_output=True, text=True,
                              encoding="utf-8").stdout
    log = git("log", "--reverse", "--format=%h %cs", "--", "docs/index.html")
    for line in log.splitlines():
        commit, commit_date = line.split()
        yield commit, commit_date, git("show", f"{commit}:docs/index.html")


def _local_date(stamp):
    # Same local-day basis as date.today() here and the "data YYYY-MM-DD"
    # commits: an extract taken 20:59 EDT is that day's, not tomorrow's (UTC).
    try:
        return datetime.fromisoformat(stamp).astimezone().date().isoformat()
    except (TypeError, ValueError):
        return None


def _write(rows):
    rows = sorted(rows, key=lambda r: r["date"])
    os.makedirs(os.path.dirname(config.HISTORY_PATH), exist_ok=True)
    with open(config.HISTORY_PATH, "w", encoding="utf-8", newline="\n") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
