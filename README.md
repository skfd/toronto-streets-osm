# toronto-streets-osm

A point-in-time comparison of [Toronto Centreline (TCL)](https://open.toronto.ca/dataset/toronto-centreline-tcl/)
road segments against named highway ways in [OpenStreetMap](https://www.openstreetmap.org/),
joined by normalized street name. Live page: <https://skfd.github.io/toronto-streets-osm/>.

Sister projects in `~/Code/`:

- [`toronto-addresses-import`](https://github.com/skfd/toronto-addresses-import) — daily change tracker for Toronto address points.
- [`toronto-2-address-import`](https://github.com/skfd/toronto-2-address-import) — proposes the missing addresses to OSM via a manual review queue + uploader.

This project is **read-only**: it never edits OSM. The output is a data quality view.

## What it produces

A single page (`docs/index.html`) with three buckets:

- **Missing in OSM** — TCL has the street, OSM does not.
- **Extra in OSM** — OSM has the street, TCL does not.
- **Matched** — both sides have it.

Each `update` run overwrites that page with today's snapshot. The counts are kept:
a second page (`docs/history.html`) charts them over time — see [History](#history).

## Setup

Python 3.11+:

```bash
cd ~/Code/toronto-streets-osm
python -m venv .venv
.venv\Scripts\activate    # PowerShell / cmd
pip install -r requirements.txt
```

## Pipeline

```bash
python run.py download     # TCL GeoJSON  -> data/tcl/centreline-YYYY-MM-DD.geojson
python run.py refresh-osm  # Geofabrik PBF + filter -> data/osm/toronto-streets.json
python run.py compare      # join + bucket -> data/compare.json + docs/index.html
python run.py update       # download + refresh-osm + compare + git push docs/
python run.py backfill     # rebuild past history rows from pages committed to git
```

`update` is the one-shot cron entry point.

## History

Every `compare` adds one row of totals to `docs/history.jsonl` (a second compare
the same day replaces that day's row) and renders `docs/history.html`: a chart of
local streets missing from OSM and OSM streets extra to TCL, plus a table of every
field. The record lives in `docs/`, not `data/`, so the daily `data YYYY-MM-DD`
commit carries it and GitHub Pages publishes it beside the chart.

`python run.py backfill` fills in the time before the record from this repo's own
git history: each commit that touched `docs/index.html` holds a rendered page with
the totals. Rows are dated by the page's OSM extract, the last page for a date wins,
and dates already on record are skipped, so re-running is harmless. Those rows are
marked `git` and shaded on the chart as reconstructed; they count under the rules
of their day, so early steps can be rule changes rather than mapping. Fields a page
predates are left out, not zeroed.

## Layout

```
src/
  config.py       # paths, bbox, dataset URLs
  download.py     # TCL CKAN fetcher
  osm_refresh.py  # Geofabrik PBF -> filtered streets JSON
  normalize.py    # normalize_street (mirrors t2/conflate.py)
  compare.py      # TCL vs OSM bucketing
  report.py       # Jinja2 -> docs/index.html, docs/history.html
  history.py      # history record + git backfill
templates/
  streets.html    # the streets page
  history.html    # the history page
  history.js      # its chart, copied to docs/
docs/
  index.html      # GitHub Pages serves this
  history.*       # history page, chart script, and the record (history.jsonl)
data/
  tcl/            # raw GeoJSON downloads (gitignored)
  osm/            # PBF + filtered JSON + meta.json (gitignored)
  compare.json    # latest comparison cache (gitignored)
```

## Scheduling (Windows)

Two PowerShell scripts manage a Windows Task Scheduler entry. Run them as Administrator.

**Add** — registers a daily task that runs `update` at 12:30 PM and appends output to `logs\scheduler.log`:

```powershell
.\schedule-add.ps1
```

**Remove**:

```powershell
.\schedule-remove.ps1
```

The task is named `TorontoStreetsOSM` and can also be managed via the Task Scheduler GUI (`taskschd.msc`).

## Data sources & attribution

- **Toronto Open Data** — "Toronto Centreline (TCL) — Version 2", under the [Open Government Licence – Toronto](https://open.toronto.ca/open-data-licence/).
- **OpenStreetMap** — © OpenStreetMap contributors, [ODbL 1.0](https://www.openstreetmap.org/copyright).
- **Geofabrik** — Ontario `.osm.pbf` extract, redistributed under ODbL.

The Open Government Licence – Toronto is **ODbL-compatible for OpenStreetMap**: the OSMF Licensing Working Group reviewed and approved it (LWG minutes 2024-04-08, listed under [OGL Canada and local variants](https://osmfoundation.org/wiki/OGL_Canada_and_local_variants)). So TCL data may legally be used as a source for OSM edits, with attribution. (This repo never edits OSM — it is read-only data quality — but the clearance applies to anyone acting on these findings.)

## License

MIT.
