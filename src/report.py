"""Render the compare data into docs/index.html.

The "Filter rules" popup in the template is generated from the live
`config` frozensets at render time, so it stays in sync with the actual
filter as long as edits land in src/config.py.
"""

import os

from jinja2 import Environment, FileSystemLoader

from src import config


def _rules_context() -> dict:
    """Snapshot of the filter rules used by the comparison, for the report popup."""
    return {
        "osm_highway_kept": sorted(config.OSM_HIGHWAY_TYPES),
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
