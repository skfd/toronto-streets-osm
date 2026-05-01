# toronto-streets-osm

Tracks the City of Toronto's [Toronto Centreline (TCL)](https://open.toronto.ca/dataset/toronto-centreline-tcl/) road centreline dataset over time, and compares it against named road geometry in OpenStreetMap. Produces:

- A daily change report for the TCL dataset (added / removed / modified street segments).
- A point-in-time **missing / extra / matched** report between TCL and OSM.

Sister projects in `~/Code/`:

- [`toronto-addresses-import`](../toronto-addresses-import) — same shape, but tracks Toronto's address-points dataset.
- [`toronto-2-address-import`](../toronto-2-address-import) — proposes the missing addresses to OSM via a manual review queue + uploader.

This project is **read-only**: it never edits OSM. The output is a data quality view.

## Why?

OSM mapping coverage for Toronto streets is hard to read at a glance. Address-point comparisons miss whole streets that exist in OSM only as `highway=*` ways with no per-house address features. A direct centreline-vs-highway comparison gives a clean answer to "is this street known to OSM at all?"

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
python run.py download         # TCL GeoJSON → data/tcl/centreline-YYYY-MM-DD.geojson
python run.py import           # GeoJSON → data/streets.db (SCD2)
python run.py report           # Latest TCL change report → docs/reports/report-*.html
python run.py refresh-osm      # Geofabrik PBF → data/osm/toronto-streets.json
python run.py compare          # TCL ↔ OSM by normalized name → docs/reports/compare-*.html
python run.py update           # download + import + report + compare in one go
python run.py rebuild          # delete DB, reimport everything in data/tcl/
python run.py report-all       # regenerate every historical report
```

## Layout

```
src/
  config.py         # paths, bbox, dataset URLs
  download.py       # TCL CKAN fetcher (HEAD-cache)
  db.py             # SCD2 streets table
  diff.py           # added / removed / modified between two snapshots
  osm_refresh.py    # Geofabrik PBF → filtered streets JSON
  normalize.py      # normalize_street (mirrors t2/conflate.py)
  compare.py        # TCL ↔ OSM bucketing
  report.py         # Jinja2 → docs/
templates/          # report.html, compare.html, index.html
docs/               # GitHub Pages output (index + reports)
data/
  tcl/              # raw GeoJSON downloads
  osm/              # PBF, filtered JSON, meta.json
  streets.db        # SCD2 SQLite
```

## Scheduling (Windows)

Two PowerShell scripts manage a Windows Task Scheduler entry. Run them as
Administrator.

**Add** — registers a daily task that runs `update` at 12:30 PM and appends
output to `logs\scheduler.log`:

```powershell
.\schedule-add.ps1
```

**Remove**:

```powershell
.\schedule-remove.ps1
```

The task is named `TorontoStreetsOSM` and can also be managed via the Task
Scheduler GUI (`taskschd.msc`).

## Data sources & attribution

- **Toronto Open Data** — "Toronto Centreline (TCL) — Version 2", under the [Open Government Licence – Toronto](https://open.toronto.ca/open-data-licence/).
- **OpenStreetMap** — © OpenStreetMap contributors, [ODbL 1.0](https://www.openstreetmap.org/copyright).
- **Geofabrik** — Ontario `.osm.pbf` extract, redistributed under ODbL.

## License

MIT.
