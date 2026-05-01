"""Render the compare data into docs/index.html."""

import os

from jinja2 import Environment, FileSystemLoader

from src import config


def render(compare_data: dict) -> str:
    env = Environment(loader=FileSystemLoader(config.TEMPLATES_DIR), autoescape=True)
    html = env.get_template("streets.html").render(data=compare_data)
    os.makedirs(config.DOCS_DIR, exist_ok=True)
    out = os.path.join(config.DOCS_DIR, "index.html")
    with open(out, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"Wrote {out}")
    return out
