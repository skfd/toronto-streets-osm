"""Static HTML reports: TCL diff and TCL vs OSM comparison.

Two report kinds, both generated under `docs/reports/`:

  report-YYYY-MM-DD.html        diff between two TCL snapshots
  compare-YYYY-MM-DD.html       TCL vs OSM comparison snapshot

`docs/reports/metadata.json` indexes both kinds for the home page.
"""

import json
import os
import re
from datetime import datetime

from jinja2 import Environment, FileSystemLoader

from src import config


def _env() -> Environment:
    return Environment(loader=FileSystemLoader(config.TEMPLATES_DIR), autoescape=True)


def _friendly_date(date_str: str) -> str:
    try:
        dt = datetime.strptime((date_str or "")[:10], "%Y-%m-%d")
        return dt.strftime("%A, %b %d, %Y")
    except (ValueError, TypeError):
        return date_str or ""


def _date_from_filename(filename: str | None) -> str | None:
    if not filename:
        return None
    m = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
    return m.group(1) if m else None


def generate_report(diff_result: dict, old_snapshot: dict, new_snapshot: dict) -> str:
    """Render an HTML report for a TCL snapshot diff."""
    os.makedirs(config.REPORTS_DIR, exist_ok=True)

    date_part = _date_from_filename(new_snapshot.get("filename")) \
        or (new_snapshot.get("downloaded") or "")[:10] \
        or datetime.now().strftime("%Y-%m-%d")
    filename = f"report-{date_part}.html"
    outpath = os.path.join(config.REPORTS_DIR, filename)

    context = {
        "generated": datetime.now().strftime("%b %d, %Y at %I:%M %p"),
        "old_snapshot": dict(old_snapshot),
        "new_snapshot": dict(new_snapshot),
        "old_date_friendly": _friendly_date((old_snapshot.get("downloaded") or "")[:10]),
        "new_date_friendly": _friendly_date(date_part),
        "added": diff_result["added"],
        "removed": diff_result["removed"],
        "modified": diff_result["modified"],
        "added_count": len(diff_result["added"]),
        "removed_count": len(diff_result["removed"]),
        "modified_count": len(diff_result["modified"]),
    }
    html = _env().get_template("report.html").render(**context)
    with open(outpath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Report written: {outpath}")

    _update_metadata(
        key=f"tcl-{new_snapshot['id']}",
        date=date_part,
        kind="tcl",
        filename=f"reports/{filename}",
        summary=f"{len(diff_result['added'])} added, "
                f"{len(diff_result['removed'])} removed, "
                f"{len(diff_result['modified'])} modified",
    )
    update_index()
    return outpath


def generate_compare_report(compare_data: dict) -> str:
    """Render an HTML report for the latest TCL vs OSM comparison."""
    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    date_part = (compare_data.get("computed_at") or "")[:10] \
        or datetime.now().strftime("%Y-%m-%d")
    filename = f"compare-{date_part}.html"
    outpath = os.path.join(config.REPORTS_DIR, filename)

    context = {
        "generated": datetime.now().strftime("%b %d, %Y at %I:%M %p"),
        "data": compare_data,
        "date_friendly": _friendly_date(date_part),
    }
    html = _env().get_template("compare.html").render(**context)
    with open(outpath, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Compare report written: {outpath}")

    t = compare_data["totals"]
    _update_metadata(
        key=f"compare-{date_part}",
        date=date_part,
        kind="cmp",
        filename=f"reports/{filename}",
        summary=f"{t['missing']} missing in OSM, {t['extra']} extra in OSM, "
                f"{t['matched']} matched",
    )
    update_index()
    return outpath


def _update_metadata(key: str, date: str, kind: str, filename: str, summary: str) -> None:
    os.makedirs(config.REPORTS_DIR, exist_ok=True)
    meta_path = os.path.join(config.REPORTS_DIR, "metadata.json")
    data = {}
    if os.path.exists(meta_path):
        try:
            data = json.loads(open(meta_path, "r", encoding="utf-8").read())
        except json.JSONDecodeError:
            data = {}
    data[key] = {"date": date, "kind": kind, "filename": filename, "summary": summary}
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def update_index() -> None:
    meta_path = os.path.join(config.REPORTS_DIR, "metadata.json")
    if not os.path.exists(meta_path):
        return
    data = json.loads(open(meta_path, "r", encoding="utf-8").read())

    reports = list(data.values())
    for r in reports:
        r["friendly_date"] = _friendly_date(r["date"])
    # Newest first; for same-date entries, comparison reports below diff reports.
    kind_rank = {"tcl": 0, "cmp": 1}
    reports.sort(key=lambda r: (r["date"], kind_rank.get(r["kind"], 99)), reverse=True)

    html = _env().get_template("index.html").render(reports=reports)
    os.makedirs(config.DOCS_DIR, exist_ok=True)
    out = os.path.join(config.DOCS_DIR, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Index updated: {out}")
