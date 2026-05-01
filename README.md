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

There is no history. Each `update` run overwrites the page with today's snapshot.

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
```

`update` is the one-shot cron entry point.

## Layout

```
src/
  config.py       # paths, bbox, dataset URLs
  download.py     # TCL CKAN fetcher
  osm_refresh.py  # Geofabrik PBF -> filtered streets JSON
  normalize.py    # normalize_street (mirrors t2/conflate.py)
  compare.py      # TCL vs OSM bucketing
  report.py       # Jinja2 -> docs/index.html
templates/
  streets.html    # the single page
docs/
  index.html      # GitHub Pages serves this
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

## License

MIT.
