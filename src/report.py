"""Render the compare data into docs/index.html.

The "Filter rules" popup in the template is generated from the live
`config` frozensets at render time, so it stays in sync with the actual
filter as long as edits land in src/config.py.
"""

import json
import os
import shutil

from jinja2 import Environment, FileSystemLoader

from src import config, history


def _rules_context() -> dict:
    """Snapshot of the filter rules used by the comparison, for the report popup."""
    return {
        "osm_highway_kept": sorted(config.OSM_HIGHWAY_TYPES),
        "osm_salvage_only": sorted(config.OSM_SALVAGE_HIGHWAY_TYPES),
        "tcl_feature_codes_kept": sorted(config.TCL_FEATURE_CODES),
    }


def render(compare_data: dict) -> str:
    env = Environment(loader=FileSystemLoader(config.TEMPLATES_DIR), autoescape=True)
    html = env.get_template("streets.html").render(
        data=compare_data,
        rules=_rules_context(),
    )
    os.makedirs(config.DOCS_DIR, exist_ok=True)
    out = os.path.join(config.DOCS_DIR, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {out}")
    return out


def render_history() -> str:
    """Render docs/history.html from the history rows alone.

    Needs no compare result, so `backfill` can redraw the chart without
    re-running the comparison. The rows are inlined for the chart (no second
    request); docs/history.jsonl, the record itself, sits beside the page.
    """
    rows = history.load()
    env = Environment(loader=FileSystemLoader(config.TEMPLATES_DIR), autoescape=True)
    html = env.get_template("history.html").render(
        rows=list(reversed(rows)),
        first_date=rows[0]["date"] if rows else None,
        last_date=rows[-1]["date"] if rows else None,
        # Emitted unescaped inside <script>; "<\/" keeps a "</" from ending it.
        rows_json=json.dumps(rows).replace("</", "<\\/"),
    )
    os.makedirs(config.DOCS_DIR, exist_ok=True)
    out = os.path.join(config.DOCS_DIR, "history.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    shutil.copy(os.path.join(config.TEMPLATES_DIR, "history.js"),
                os.path.join(config.DOCS_DIR, "history.js"))
    print(f"Wrote {out} ({len(rows)} runs)")
    return out
