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

# Same bbox the sibling project uses; covers City of Toronto.
TORONTO_BBOX = (43.58, -79.64, 43.86, -79.11)

# OSM highway types kept by the extract: drivable + pedestrian, both with name=*.
OSM_HIGHWAY_TYPES = frozenset({
    "motorway", "trunk", "primary", "secondary", "tertiary",
    "residential", "unclassified", "service", "living_street",
    "pedestrian", "footway",
})
