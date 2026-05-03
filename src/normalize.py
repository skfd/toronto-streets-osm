"""Street name normalization, mirrored from toronto-2-address-import/t2/conflate.py.

Both sides of the comparison (TCL `LINEAR_NAME_FULL`, OSM `name`) get pushed through
the same function so "Yonge Street" and "Yonge St" collapse to one bucket.
"""

STREET_SUFFIXES = {
    "STREET": "ST", "ROAD": "RD", "AVENUE": "AVE", "BOULEVARD": "BLVD",
    "DRIVE": "DR", "LANE": "LN", "COURT": "CT", "PLACE": "PL",
    "TERRACE": "TER", "CRESCENT": "CRES", "SQUARE": "SQ", "GATE": "GTE",
    "CIRCLE": "CIR", "WAY": "WAY", "TRAIL": "TRL", "PARKWAY": "PKWY",
    "HIGHWAY": "HWY", "EXPRESSWAY": "EXPY",
    "CRT": "CT", "CRCL": "CIR", "GT": "GTE",
    "GARDENS": "GDNS", "GROVE": "GRV", "HEIGHTS": "HTS",
    "PATHWAY": "PTWY", "CIRCUIT": "CRCT", "BRIDGE": "BDGE", "LAWN": "LWN",
    "PARK": "PK", "ROADWAY": "RDWY",
}
DIRS = {"NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W"}


def normalize_street(name: str | None) -> str:
    if not name:
        return ""
    text = name.upper().replace(".", "").replace("'", "").replace("’", "")
    parts = text.split()
    out = []
    i = 0
    while i < len(parts):
        p = parts[i]
        if p in ("MC", "MAC") and i + 1 < len(parts):
            out.append(p + parts[i + 1])
            i += 2
            continue
        if p == "SAINT":
            out.append("ST")
        elif p in STREET_SUFFIXES:
            out.append(STREET_SUFFIXES[p])
        elif p in DIRS:
            out.append(DIRS[p])
        else:
            out.append(p)
        i += 1
    return " ".join(out)
