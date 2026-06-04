"""Project paths, dataset URLs, and the Toronto bbox used to clip the OSM extract."""
import os

ROOT = os.path.dirname(os.path.dirname(__file__))

DATA_DIR = os.path.join(ROOT, "data")
TCL_DIR = os.path.join(DATA_DIR, "tcl")
OSM_DIR = os.path.join(DATA_DIR, "osm")
DB_PATH = os.path.join(DATA_DIR, "streets.db")
COMPARE_JSON_PATH = os.path.join(DATA_DIR, "compare.json")

DOCS_DIR = os.path.join(ROOT, "docs")
REPORTS_DIR = os.path.join(DOCS_DIR, "reports")
TEMPLATES_DIR = os.path.join(ROOT, "templates")

# TCL package + WGS84 GeoJSON resource on Toronto Open Data CKAN.
# Looked up via package_show?id=toronto-centreline-tcl.
TCL_PACKAGE_ID = "1d079757-377b-4564-82df-eb5638583bfb"
TCL_RESOURCE_ID = "7bc94ccf-7bcf-4a7d-88b1-bdfc8ec5aaf1"
TCL_FILENAME = "centreline-version-2-4326.geojson"
TCL_DATASET_URL = (
    f"https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/"
    f"{TCL_PACKAGE_ID}/resource/{TCL_RESOURCE_ID}/download/{TCL_FILENAME}"
)

# Geofabrik Ontario extract, same source the address tooling uses.
OSM_PBF_URL = "https://download.geofabrik.de/north-america/canada/ontario-latest.osm.pbf"
OSM_PBF_PATH = os.path.join(OSM_DIR, "ontario-latest.osm.pbf")
OSM_STREETS_JSON = os.path.join(OSM_DIR, "toronto-streets.json")
OSM_META_PATH = os.path.join(OSM_DIR, "meta.json")
OSM_LOCK_PATH = os.path.join(OSM_DIR, "refresh.lock")
OSM_LOG_PATH = os.path.join(OSM_DIR, "refresh.log")

# Toronto boundary, derived from the union of the 158 neighbourhood polygons
# published by the City. Same dataset the sibling tile-builder uses.
BOUNDARY_URL = (
    "https://ckan0.cf.opendata.inter.prod-toronto.ca/dataset/"
    "fc443770-ef0a-4025-9c2c-2cb558bfab00/resource/"
    "0719053b-28b7-48ea-b863-068823a93aaa/download/neighbourhoods-4326.geojson"
)
BOUNDARY_DIR = os.path.join(DATA_DIR, "boundary")
BOUNDARY_GEOJSON_PATH = os.path.join(BOUNDARY_DIR, "neighbourhoods-4326.geojson")

# Cheap prefilter: a way's bounding box must intersect this rectangle before
# the more-expensive point-in-polygon city-boundary check runs.
TORONTO_BBOX = (43.58, -79.64, 43.86, -79.11)

# OSM highway types kept by the extract. Liberal-include policy: any value
# where OSM could plausibly tag a TCL drivable road by that name. Beyond the
# obvious drivable classes we also keep pedestrian/footway/track (a TCL
# street can show up under any of these in OSM) and construction/proposed
# (in-progress roads). Excludes ramps (*_link, by request), rec trails
# (cycleway, path), and inherently-undrivable types (steps, busway, bus_stop,
# bridleway, corridor, platform). name=* still required.
#
# Source of truth for the "Filter rules" popup in the rendered report --
# templates/streets.html reads this set via the `rules` context. Edit here
# and re-run `python run.py compare` to update the popup.
OSM_HIGHWAY_TYPES = frozenset({
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "residential", "service",
    "living_street", "pedestrian", "footway", "track",
    "construction", "proposed",
})

# Salvage-only highway types: kept in the extract so they can confirm a TCL
# match (rescuing a street from "Missing"), but never surface on their own as
# "Extra". OSM commonly tags ordinary municipal roads `unclassified` and maps
# Toronto laneways/walkways as `path`; we want those to vouch for a TCL street
# without flooding the OSM-only bucket (a `path` that matches no TCL street is
# just a rec trail and is dropped). See src/compare.py::_osm_streets.
OSM_SALVAGE_HIGHWAY_TYPES = frozenset({"unclassified", "path"})

# What the PBF filter actually keeps: the Extra-eligible types plus the
# salvage-only types. osm_refresh.py uses this union.
OSM_EXTRACT_HIGHWAY_TYPES = OSM_HIGHWAY_TYPES | OSM_SALVAGE_HIGHWAY_TYPES

# TCL FEATURE_CODE_DESC values kept on the TCL side of the comparison.
# Drivable public roads + Laneway + expressway/major-arterial ramps. Excludes
# Trail, Walkway, Busway, Railway, River, Hydro Line, Shoreline, Creek, Ferry.
# Also surfaced in the report's Filter rules popup -- edit here, popup follows.
# Note: the OSM side still excludes *_link; ramps surface only as TCL-only
# entries in the "Missing Major" tab, which is the intent.
TCL_FEATURE_CODES = frozenset({
    "Local", "Collector", "Major Arterial", "Minor Arterial",
    "Expressway", "Expressway Ramp", "Major Arterial Ramp",
    "Laneway",
    "Other", "Pending",
})
